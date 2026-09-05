#!/usr/bin/env python3
"""
R4 -- Calendar / Diagonal term-structure backtest
=================================================

Tests the one short-premium structure that SOXL's own surface argues for.

The thesis (harvest_blueprint/README.md, qa/pricing_lab_report.txt S2/S3):

    * ATM term structure is INVERTED on 67-68% of days -- the front week
      averages +6.7 IV points over 30d and +9.6 over 180d.
    * The 7-day tenor is the ONLY one whose variance risk premium is not
      negative (+0.7 pts). At 30/90/180d the VRP is -14/-22/-29 pts, i.e.
      the back months are systematically CHEAP.

    => sell the one tenor that is not underpriced, own the tenor that is
       most underpriced. Sell the front, own the back.

Structure (one "unit"):

    LONG  1 back-month option, right R, strike = `long_mness` x spot,
          DTE targeted at `long_dte` inside [long_dte_lo, long_dte_hi].
          Rolled when DTE <= `long_roll_dte`, or when spot has drifted
          more than `restrike_drift` from the spot at entry (0 = never).
    SHORT 1 front-week option, same right, in that week's expiry (3-7 DTE),
          struck `short_offset` further OTM than the long leg
          (0.0 = pure calendar, same strike; >0 = diagonal).
          Held to expiration, cash-settled at intrinsic against the
          expiry-day close from the 5-min file.  Re-sold every week for as
          long as the long leg is alive.

Risk is DEFINED BY CONSTRUCTION. The short leg is never struck closer to
the money than the long leg (calls: K_short >= K_long; puts: K_short <=
K_long), and the long always has more time, so the spread cannot be worth
less than zero: max loss = the net debit paid. Sizing therefore risks
`risk_frac` of equity per unit-cohort by construction.

CONTROLS (this is the point of the exercise -- the PMCC engine's own
LONGONLY control is what revealed its short leg destroyed $150k of value):

    LONGONLY   own the back month, never sell the front. Same risk_frac.
               If the calendar cannot beat this, the short leg is a cost.
    SHORTONLY  sell the naked weekly, no long leg (cash-secured sizing;
               a different sizing basis by necessity -- flagged).
    BUYHOLD    SOXL shares.

Execution: project-standard 20%-of-spread rule from REAL quotes only
(sell = bid + 0.20*spread, buy = ask - 0.20*spread; bid=0 or inverted
rejected). No Black-Scholes anywhere. Option quotes are EOD snapshots so
every decision is EOD.

Capital: $150,000 start; sweep `sweep_frac` of each week's positive net
realized P&L to a side account; commissions $0.65/contract/leg.

Outputs:
    calendar_ledger.csv        weekly per-leg ledger (base config)
    calendar_grid.csv          permutation + control summary
    qa/calendar_report.txt
"""

from dataclasses import dataclass, asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from put_diagonal_backtest import Market, COMMISSION, EPS

ROOT = Path(__file__).resolve().parent
QA_DIR = ROOT / "qa"


@dataclass(frozen=True)
class Config:
    right: str = "CALL"             # CALL or PUT
    long_mness: float = 1.00        # long strike as a fraction of spot
    long_dte: int = 90              # target DTE for the long leg
    long_dte_lo: int = 60
    long_dte_hi: int = 120
    long_roll_dte: int = 30         # roll the long when DTE <= this
    restrike_drift: float = 0.0     # roll if |spot/entry_spot - 1| > this
    short_offset: float = 0.0       # short strike OTM beyond long (0=calendar)
    short_atm: bool = False         # re-centre the short on SPOT each week
                                    # instead of leaving it at the (possibly
                                    # stale) long strike -- still clamped by
                                    # the defined-risk constraint below
    risk_frac: float = 0.25         # equity fraction at risk (= net debit)
    unit_mode: bool = False         # hold exactly ONE contract per leg: no
                                    # sizing, no compounding, no capital
                                    # constraint. Terminal P&L is then the
                                    # structure's own economics, free of the
                                    # sizing and compounding artifacts that
                                    # make wealth curves incomparable.
    size_on: str = "net"            # "net" = size on the unit's net debit;
                                    # "long" = size on the long cost alone, so
                                    # a calendar and its LONGONLY control hold
                                    # identical contracts (clean attribution)
    no_short: bool = False          # LONGONLY control
    no_long: bool = False           # SHORTONLY control
    invest_frac: float = 0.75       # used only by the SHORTONLY control
    sweep_frac: float = 0.25
    start_capital: float = 150_000.0

    def label(self):
        if self.no_long:
            return f"SHORTONLY_{self.right[0]}_o{self.short_offset:.0%}"
        kind = "CAL" if self.short_offset == 0 else "DIAG"
        p = [kind, self.right[0], f"m{self.long_mness:.0%}",
             f"t{self.long_dte}", f"o{self.short_offset:.0%}",
             f"r{self.risk_frac:.0%}"]
        if self.restrike_drift:
            p.append(f"dr{self.restrike_drift:.0%}")
        if self.size_on == "long":
            p.append("szL")
        if self.short_atm:
            p.append("atm")
        if self.unit_mode:
            p.append("1x")
        if self.no_short:
            p.insert(0, "LONGONLY")
        return "_".join(p)


# --------------------------------------------------------------------------
# leg selection
# --------------------------------------------------------------------------
def pick_long(mkt, td, cfg):
    """Back-month leg: expiry nearest long_dte in-window, strike nearest
    long_mness x spot among liquid whole strikes."""
    ch = mkt.chains[td]
    g = ch[(ch["right"] == cfg.right) & ch["liquid"] &
           (ch["dte"] >= cfg.long_dte_lo) & (ch["dte"] <= cfg.long_dte_hi)]
    if g.empty:      # widen once if the window is empty on this date
        g = ch[(ch["right"] == cfg.right) & ch["liquid"] &
               (ch["dte"] >= 30) & (ch["dte"] <= 250)]
    if g.empty:
        return None
    exp = g.loc[(g["dte"] - cfg.long_dte).abs().idxmin(), "expiration"]
    g = g[(g["expiration"] == exp) & (g["buy_px"] > 0.05)]
    whole = g[g["strike"] % 1 == 0]
    if len(whole):
        g = whole
    if g.empty:
        return None
    tgt = cfg.long_mness * mkt.spot(td)
    return g.loc[(g["strike"] - tgt).abs().idxmin()]


def pick_short(chain, cfg, long_strike, spot=None):
    """Front-week leg, struck short_offset further OTM than the long.

    The defined-risk constraint is enforced here and is not optional:
    calls must satisfy K_short >= K_long, puts K_short <= K_long.
    """
    g = chain[(chain["right"] == cfg.right) & chain["liquid"] &
              (chain["sell_px"] >= 0.02)]
    if long_strike is not None:
        # reference the short off spot when re-centring, else off the long
        ref = spot if (cfg.short_atm and spot is not None) else long_strike
        if cfg.right == "CALL":
            g = g[g["strike"] >= long_strike - EPS]
            tgt = ref * (1 + cfg.short_offset)
        else:
            g = g[g["strike"] <= long_strike + EPS]
            tgt = ref * (1 - cfg.short_offset)
    else:                                   # SHORTONLY control
        return None
    whole = g[g["strike"] % 1 == 0]
    if len(whole):
        g = whole
    if g.empty:
        return None
    return g.loc[(g["strike"] - tgt).abs().idxmin()]


def pick_short_naked(chain, cfg, spot):
    """SHORTONLY control: weekly leg at short_offset OTM from spot."""
    g = chain[(chain["right"] == cfg.right) & chain["liquid"] &
              (chain["sell_px"] >= 0.02)]
    tgt = spot * (1 + cfg.short_offset) if cfg.right == "CALL" \
        else spot * (1 - cfg.short_offset)
    whole = g[g["strike"] % 1 == 0]
    if len(whole):
        g = whole
    if g.empty:
        return None
    return g.loc[(g["strike"] - tgt).abs().idxmin()]


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------
class CalendarBacktest:
    def __init__(self, mkt: Market, cfg: Config):
        self.m, self.cfg = mkt, cfg
        self.cash = cfg.start_capital
        self.sweep = 0.0
        self.commissions = 0.0
        self.realized_log = []          # (date, leg, amount) audit trail
        self.long = None
        self.short = None
        self.blown = False
        self.week_rows = []
        self.wk = None
        self.long_rolls = 0
        self.short_premium = 0.0
        self.net_deltas = []            # net delta per unit at each short open

    # --- cash primitives -------------------------------------------------
    def realize(self, date, leg, amt):
        self.realized_log.append((date, leg, amt))
        self.wk[f"{leg}_realized"] = self.wk.get(f"{leg}_realized", 0.0) + amt

    def commission(self, contracts):
        c = COMMISSION * contracts
        self.commissions += c
        self.cash -= c

    # --- marks -----------------------------------------------------------
    def mark(self, td, pos):
        if pos is None:
            return 0.0
        q = self.m.quote(td, pos["exp"], pos["strike"], self.cfg.right)
        px = pos["last_mark"] if q is None else float(q["mid"])
        pos["last_mark"] = px
        return px

    def equity(self, td):
        eq = self.cash
        if self.long:
            eq += self.mark(td, self.long) * 100 * self.long["n"]
        if self.short:
            eq -= self.mark(td, self.short) * 100 * self.short["n"]
        return eq

    # --- long leg --------------------------------------------------------
    def close_long(self, td):
        if self.long is None:
            return
        q = self.m.quote(td, self.long["exp"], self.long["strike"],
                         self.cfg.right)
        px = float(q["sell_px"]) if (q is not None and bool(q["liquid"])) \
            else self.long["last_mark"]
        n = self.long["n"]
        self.cash += px * 100 * n
        self.commission(n)
        self.realize(td, "long", (px - self.long["cost"]) * 100 * n)
        self.wk["long_close_px"] = round(px, 3)
        self.long = None

    def open_long(self, td):
        cfg = self.cfg
        row = pick_long(self.m, td, cfg)
        if row is None:
            return "NO_LONG"
        cost = float(row["buy_px"])
        # size on the NET debit of the unit: long cost less one week's credit
        net = cost
        if not cfg.no_short:
            wk = self.m.week_expiry_chain(td)
            if wk is not None:
                s = pick_short(wk, cfg, float(row["strike"]),
                               self.m.spot(td))
                if s is not None:
                    net = max(cost - float(s["sell_px"]), 0.05)
        basis = cost if cfg.size_on == "long" else net
        eq = self.equity(td)
        n = 1 if cfg.unit_mode else \
            int(min(cfg.risk_frac * eq, self.cash * 0.95) // (basis * 100))
        if n <= 0:
            return "NO_CAPITAL"
        self.cash -= cost * 100 * n
        self.commission(n)
        self.long = {"exp": row["expiration"], "strike": float(row["strike"]),
                     "cost": cost, "n": n, "last_mark": cost,
                     "entry_spot": self.m.spot(td), "entry": td}
        self.long_rolls += 1
        self.wk.update(long_strike=float(row["strike"]),
                       long_exp=str(pd.Timestamp(row["expiration"]).date()),
                       long_dte=int(row["dte"]), long_px=round(cost, 3),
                       long_n=n, unit_net_debit=round(net, 3))
        return ""

    def long_needs_roll(self, td):
        if self.long is None:
            return True
        dte = (pd.Timestamp(self.long["exp"]) - td).days
        if dte <= self.cfg.long_roll_dte:
            return True
        if self.cfg.restrike_drift:
            drift = abs(self.m.spot(td) / self.long["entry_spot"] - 1)
            if drift > self.cfg.restrike_drift:
                return True
        return False

    # --- short leg -------------------------------------------------------
    def open_short(self, td):
        cfg = self.cfg
        wk = self.m.week_expiry_chain(td)
        if wk is None:
            return "NO_WEEK_EXPIRY"
        if cfg.no_long:
            row = pick_short_naked(wk, cfg, self.m.spot(td))
            if row is None:
                return "NO_SHORT"
            n = 1 if cfg.unit_mode else \
                int(cfg.invest_frac * self.equity(td)
                    // (float(row["strike"]) * 100))
        else:
            if self.long is None:
                return "NO_LONG_LEG"
            row = pick_short(wk, cfg, self.long["strike"],
                             self.m.spot(td))
            if row is None:
                return "NO_SHORT"
            n = self.long["n"]
        if n <= 0:
            return "NO_CAPITAL"
        px = float(row["sell_px"])
        self.cash += px * 100 * n
        self.commission(n)
        self.short_premium += px * 100 * n
        self.short = {"exp": row["expiration"], "strike": float(row["strike"]),
                      "credit": px, "n": n, "last_mark": px}
        # net delta per unit -- the structure's actual directional exposure
        nd = None
        if not cfg.no_long and self.long is not None:
            lq = self.m.quote(td, self.long["exp"], self.long["strike"],
                              cfg.right)
            if lq is not None and pd.notna(lq["delta"]) \
                    and pd.notna(row["delta"]):
                nd = float(lq["delta"]) - float(row["delta"])
                self.net_deltas.append(nd)
        self.wk.update(short_strike=float(row["strike"]),
                       short_exp=str(pd.Timestamp(row["expiration"]).date()),
                       short_px=round(px, 3), short_n=n,
                       short_credit=round(px * 100 * n, 2),
                       net_delta_per_unit=None if nd is None else round(nd, 3))
        return ""

    def settle_short(self, td):
        """Cash-settle the front leg at intrinsic on its expiry."""
        if self.short is None:
            return
        s = self.short
        settle = self.m.settle_close(s["exp"])
        if settle is None:
            return
        if self.cfg.right == "CALL":
            intrinsic = max(settle - s["strike"], 0.0)
        else:
            intrinsic = max(s["strike"] - settle, 0.0)
        n = s["n"]
        self.cash -= intrinsic * 100 * n
        self.realize(td, "short", (s["credit"] - intrinsic) * 100 * n)
        self.wk.update(settle_px=round(settle, 2),
                       short_intrinsic=round(intrinsic, 3))
        self.short = None

    def margin_call(self, td):
        """Cash negative after settlement: liquidate long contracts until
        it clears (what a broker would do), then mark blown if it cannot."""
        if self.cash >= -EPS or self.long is None:
            return
        q = self.m.quote(td, self.long["exp"], self.long["strike"],
                         self.cfg.right)
        px = float(q["sell_px"]) if (q is not None and bool(q["liquid"])) \
            else self.long["last_mark"]
        if px <= 0:
            self.blown = True
            return
        need = int(np.ceil(-self.cash / (px * 100)))
        k = min(need, self.long["n"])
        self.cash += px * 100 * k
        self.commission(k)
        self.realize(td, "long", (px - self.long["cost"]) * 100 * k)
        self.long["n"] -= k
        self.wk["margin_liquidated"] = k
        if self.long["n"] <= 0:
            self.long = None
        if self.cash < -EPS:
            self.blown = True

    def liquidate_all(self, td):
        """Account is gone: close everything so nothing is left unrealized."""
        self.close_long(td)
        if self.short is not None:
            q = self.m.quote(td, self.short["exp"], self.short["strike"],
                             self.cfg.right)
            px = float(q["buy_px"]) if (q is not None and bool(q["liquid"])) \
                else self.short["last_mark"]
            n = self.short["n"]
            self.cash -= px * 100 * n
            self.commission(n)
            self.realize(td, "short", (self.short["credit"] - px) * 100 * n)
            self.short = None

    # --- main loop -------------------------------------------------------
    def run(self):
        cfg = self.cfg
        weeks = {}
        for d in self.m.dates:
            weeks.setdefault(d.to_period("W-SUN"), []).append(d)
        for wk_p in sorted(weeks):
            wdays = weeks[wk_p]
            d0 = wdays[0]
            self.wk = {"week_start": str(d0.date()),
                       "week_end": str(wdays[-1].date()),
                       "begin_cash": round(self.cash, 2),
                       "begin_equity": round(self.equity(d0), 2),
                       "spot": round(self.m.spot(d0), 2)}
            if self.blown:
                self.wk.update(action="BLOWN", end_cash=round(self.cash, 2),
                               end_sweep=round(self.sweep, 2),
                               end_equity=round(self.cash, 2),
                               wealth=round(self.cash + self.sweep, 2))
                self.week_rows.append(self.wk)
                continue
            notes = []
            # 1. long leg: roll if due
            if not cfg.no_long:
                if self.long_needs_roll(d0):
                    self.close_long(d0)
                    why = self.open_long(d0)
                    if why:
                        notes.append(why)
            # 2. short leg for this week
            if not cfg.no_short:
                why = self.open_short(d0)
                if why:
                    notes.append(why)
            # 3. settle the front leg at its expiry
            self.settle_short(wdays[-1])
            self.margin_call(wdays[-1])
            # 4. weekly sweep of positive net realized
            wk_real = (self.wk.get("long_realized", 0.0)
                       + self.wk.get("short_realized", 0.0))
            if wk_real > 0 and cfg.sweep_frac and not cfg.no_long \
                    and not cfg.unit_mode:
                take = min(wk_real * cfg.sweep_frac, max(self.cash, 0.0))
                self.cash -= take
                self.sweep += take
                self.wk["swept"] = round(take, 2)
            eq = self.equity(wdays[-1])
            # Either blow-up path -- equity gone, or a margin call that could
            # not be met -- liquidates. Nothing may be left unrealized, or the
            # wealth series and the cash-flow audit stop agreeing.
            if eq + self.sweep <= 0 or self.blown:
                self.liquidate_all(wdays[-1])
                self.blown = True
                eq = self.cash
            self.wk.update(action=";".join(notes) or "OK",
                           week_realized=round(wk_real, 2),
                           end_cash=round(self.cash, 2),
                           end_sweep=round(self.sweep, 2),
                           end_equity=round(eq, 2),
                           wealth=round(eq + self.sweep, 2))
            self.week_rows.append(self.wk)
        return pd.DataFrame(self.week_rows)


# --------------------------------------------------------------------------
# controls and reporting
# --------------------------------------------------------------------------
def buyhold(mkt, start_capital=150_000.0):
    d0, dn = mkt.dates[0], mkt.dates[-1]
    px0, pxn = mkt.spot(d0), mkt.spot(dn)
    sh = int(start_capital // px0)
    end = start_capital - sh * px0 + sh * pxn
    curve = [sh * mkt.spot(d) + (start_capital - sh * px0) for d in mkt.dates]
    curve = pd.Series(curve, index=mkt.dates)
    dd = (curve / curve.cummax() - 1).min() * 100
    yrs = (dn - d0).days / 365.25
    return {"config": "BUYHOLD", "weeks": None, "blown": False,
            "end_wealth": round(end, 2),
            "total_ret_pct": round(100 * (end / start_capital - 1), 1),
            "cagr_pct": round(100 * ((end / start_capital) ** (1 / yrs) - 1), 1),
            "max_dd_pct": round(dd, 1), "worst_wk_pct": None,
            "short_premium": 0.0, "short_realized": 0.0,
            "long_realized": round(end - start_capital, 2),
            "long_rolls": 1, "sweep_final": 0.0, "commissions": 0.0,
            "qa_recon": "PASS"}


def summarize(bt, led):
    cfg = bt.cfg
    w = led["wealth"].dropna()
    start = cfg.start_capital
    end = float(w.iloc[-1]) if len(w) else start
    dd = float((w / w.cummax() - 1).min() * 100) if len(w) else 0.0
    wk_ret = w.pct_change().dropna()
    d0, dn = bt.m.dates[0], bt.m.dates[-1]
    yrs = (dn - d0).days / 365.25
    cagr = 100 * ((max(end, 1e-9) / start) ** (1 / yrs) - 1)
    long_r = sum(a for _, l, a in bt.realized_log if l == "long")
    short_r = sum(a for _, l, a in bt.realized_log if l == "short")
    # QA: wealth must reconcile from raw cash flows. Open positions
    # contribute their UNREALIZED P&L (mark vs entry), not their gross mark.
    unreal = 0.0
    if bt.long:
        unreal += (bt.long["last_mark"] - bt.long["cost"]) * 100 * bt.long["n"]
    if bt.short:
        unreal += (bt.short["credit"] - bt.short["last_mark"]) * 100 \
            * bt.short["n"]
    recon = start + long_r + short_r - bt.commissions + unreal
    ok = abs(recon - end) < 1.0
    nd = pd.Series(bt.net_deltas, dtype=float)
    return {"config": cfg.label(), "weeks": len(led), "blown": bt.blown,
            "end_wealth": round(end, 2),
            "total_ret_pct": round(100 * (end / start - 1), 1),
            "cagr_pct": round(cagr, 1), "max_dd_pct": round(dd, 1),
            "worst_wk_pct": round(float(wk_ret.min() * 100), 1)
            if len(wk_ret) else None,
            "short_premium": round(bt.short_premium, 0),
            "short_realized": round(short_r, 0),
            "long_realized": round(long_r, 0),
            "long_rolls": bt.long_rolls,
            "mean_abs_net_delta": round(float(nd.abs().mean()), 3)
            if len(nd) else None,
            "wks_delta_gt_25": round(float((nd.abs() > 0.25).mean() * 100), 1)
            if len(nd) else None,
            "sweep_final": round(bt.sweep, 2),
            "commissions": round(bt.commissions, 0),
            "qa_recon": "PASS" if ok else f"FAIL({recon - end:+.2f})"}


def main():
    mkt = Market()
    print(f"market: {len(mkt.dates)} trade dates "
          f"{mkt.dates[0].date()} -> {mkt.dates[-1].date()}")
    base = Config()
    rows, ledger = [], None

    grid = [base]
    # tenor of the long leg
    for t, lo, hi, rd in [(30, 21, 45, 10), (60, 45, 75, 21),
                          (90, 60, 120, 30), (150, 120, 180, 45)]:
        grid.append(replace(base, long_dte=t, long_dte_lo=lo,
                            long_dte_hi=hi, long_roll_dte=rd))
    # strike placement and right
    for r in ("CALL", "PUT"):
        for m in (0.90, 0.95, 1.00, 1.05, 1.10):
            grid.append(replace(base, right=r, long_mness=m))
    # calendar -> diagonal
    for o in (0.03, 0.05, 0.08):
        for r in ("CALL", "PUT"):
            grid.append(replace(base, right=r, short_offset=o))
    # re-centred short leg (a real calendar trader does not let it go stale)
    for r in ("CALL", "PUT"):
        for o in (0.0, 0.05):
            grid.append(replace(base, right=r, short_offset=o,
                                short_atm=True))
    # sizing
    for rf in (0.10, 0.50):
        grid.append(replace(base, risk_frac=rf))
    # re-strike discipline
    grid.append(replace(base, restrike_drift=0.15))
    # CONTROLS
    for r in ("CALL", "PUT"):
        grid.append(replace(base, right=r, no_short=True))          # LONGONLY
        grid.append(replace(base, right=r, no_long=True,
                            short_offset=0.05))                     # SHORTONLY
    # SIZING-FREE: one contract per leg, no compounding. The only comparison
    # in which the calendar and its LONGONLY control hold identical books for
    # the entire run, so the difference IS the short overlay.
    for r in ("CALL", "PUT"):
        for o in (0.0, 0.05):
            grid.append(replace(base, right=r, short_offset=o,
                                unit_mode=True))
            grid.append(replace(base, right=r, short_offset=o,
                                unit_mode=True, short_atm=True))
        grid.append(replace(base, right=r, no_short=True, unit_mode=True))
    # MATCHED-SIZE ATTRIBUTION: identical long book, short overlay on/off.
    # This is the only comparison that isolates the short leg, because both
    # sides of the pair then hold exactly the same contracts.
    for r in ("CALL", "PUT"):
        for o in (0.0, 0.05):
            grid.append(replace(base, right=r, short_offset=o,
                                size_on="long"))
        grid.append(replace(base, right=r, no_short=True,
                            size_on="long"))

    seen = set()
    for cfg in grid:
        if cfg.label() in seen:
            continue
        seen.add(cfg.label())
        bt = CalendarBacktest(mkt, cfg)
        led = bt.run()
        if cfg == base:
            ledger = led
        s = summarize(bt, led)
        rows.append(s)
        print(f"  {s['config']:34s} end={s['end_wealth']:>12,.0f}  "
              f"cagr={s['cagr_pct']:>7.1f}%  dd={s['max_dd_pct']:>6.1f}%  "
              f"{s['qa_recon']}")

    rows.append(buyhold(mkt))
    grid_df = pd.DataFrame(rows).sort_values("end_wealth", ascending=False)
    ledger.to_csv(ROOT / "calendar_ledger.csv", index=False)
    grid_df.to_csv(ROOT / "calendar_grid.csv", index=False)

    QA_DIR.mkdir(exist_ok=True)
    fails = (grid_df["qa_recon"] != "PASS").sum()
    with open(QA_DIR / "calendar_report.txt", "w") as f:
        f.write("R4 CALENDAR / DIAGONAL TERM-STRUCTURE -- BACKTEST REPORT\n")
        f.write(f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}\n")
        f.write("EOD decisions (option quotes are EOD snapshots).\n")
        f.write("Short leg held to expiry, cash-settled at intrinsic.\n")
        f.write("Risk defined by construction: K_short never closer to the\n"
                "money than K_long, so max loss = net debit paid.\n\n")
        f.write(f"BASE CONFIG {asdict(base)}\n\n")
        b = [r for r in rows if r["config"] == base.label()][0]
        for k, v in b.items():
            f.write(f"  {k}: {v}\n")
        f.write("\nGRID + CONTROLS (sorted by end wealth)\n")
        f.write(grid_df.to_string(index=False))
        f.write(f"\n\nQA reconciliation failures: {fails} of {len(grid_df)}\n")
    print(f"\nwrote calendar_grid.csv, calendar_ledger.csv, "
          f"qa/calendar_report.txt   (QA fails: {fails}/{len(grid_df)})")


if __name__ == "__main__":
    main()
