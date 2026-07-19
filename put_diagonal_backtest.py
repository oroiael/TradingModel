#!/usr/bin/env python3
"""
R1 -- Put Diagonal Income Engine backtest
=========================================

Structure (per STRATEGY_RECOMMENDATIONS.md, strategy R1):

    * ANCHOR  : own N puts, 120-180 DTE, strike = nearest whole strike to
                `anchor_mness` x spot.  Rolled when DTE <= `anchor_roll_dte`
                or spot has drifted +/- `anchor_roll_drift` from the spot at
                anchor entry (drift roll monetizes crash gains).
    * SHORT   : sell N puts every week at `short_delta` target in that
                week's expiry (3-7 DTE from the first trade day of the
                week); held to expiration and cash-settled at intrinsic
                using the expiry-day close from the 5-min file.
    * DEFENSE : optional.  Any EOD between decision days where the live
                short put's |delta| >= 0.50: buy it back (20% rule) and
                re-sell at the delta target 7-14 DTE out ("roll down and
                out").  EOD is the best available proxy for the intraday
                trigger in the Active-Version spec -- flagged in output.

Execution: project-standard 20%-of-spread rule from REAL quotes only
(sell = bid + 0.20*(ask-bid); buy = ask - 0.20*(ask-bid); bid=0 rejected).
No Black-Scholes anywhere.  Option quotes are EOD snapshots, so all
decisions are EOD (the Monday-10:00 spec cannot be priced from this data --
see report header note).

Capital (original project rules): start $150,000; deploy `invest_frac`=75%;
sweep 25% of each week's positive net realized P&L to a side account.
Sizing modes:
    notional : contracts = invest_frac*equity / (short strike * 100)
               (cash-secured-put sizing; default, conservative)
    premium  : contracts = invest_frac*equity / (anchor cost * 100)
               (aggressive: budget deployed into anchor premium)

Outputs:
    put_diagonal_ledger.csv   weekly per-leg ledger (base config)
    put_diagonal_grid.csv     parameter-permutation summary
    qa/put_diagonal_report.txt

QA: hard invariants are asserted during the run (cash never negative,
wealth reconciliation from raw cash flows at the end); results print
PASS/FAIL in the report.
"""

from dataclasses import dataclass, asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import ROOT
from volatility_pricing_lab import load_options, load_bars, daily_frame

QA_DIR = Path(__file__).resolve().parent / "qa"
COMMISSION = 0.65          # $/contract, charged on traded opens/closes only
EPS = 1e-6


@dataclass(frozen=True)
class Config:
    short_delta: float = 0.225      # 20-25d midpoint target
    anchor_mness: float = 1.00      # anchor strike as fraction of spot
    anchor_dte: int = 150           # target DTE inside [120, 180]
    anchor_dte_lo: int = 120
    anchor_dte_hi: int = 180
    anchor_roll_dte: int = 45
    anchor_roll_drift: float = 0.10
    roll_up: bool = True            # False: drift-roll only on down moves
    short_ratio: float = 1.0        # shorts per anchor (>1 = ratio diagonal;
                                    # the excess shorts are naked)
    no_anchor: bool = False         # attribution control: shorts only
    delta_defense: bool = False
    defense_trigger: float = 0.50
    sizing: str = "notional"        # or "premium"
    invest_frac: float = 0.75
    sweep_frac: float = 0.25
    start_capital: float = 150_000.0

    def label(self):
        return (f"d{self.short_delta:.0%}_m{self.anchor_mness:.0%}_"
                f"t{self.anchor_dte}_{self.sizing}"
                f"_r{self.anchor_roll_drift:.0%}"
                f"{'' if self.roll_up else '_dnonly'}"
                f"{'_def' if self.delta_defense else ''}"
                + (f"_x{self.short_ratio:g}" if self.short_ratio != 1 else "")
                + ("_NOANCHOR" if self.no_anchor else ""))


# --------------------------------------------------------------------------
# data access helpers
# --------------------------------------------------------------------------
class Market:
    def __init__(self):
        opt = load_options()
        self.chains = dict(tuple(opt.groupby("trade_date")))
        self.dates = sorted(self.chains)
        self.quote_idx = opt.set_index(
            ["trade_date", "expiration", "strike", "right"]).sort_index()
        bars = load_bars()
        self.daily_close = daily_frame(bars)["close"]

    def quote(self, td, exp, strike, right="PUT"):
        try:
            q = self.quote_idx.loc[(td, exp, strike, right)]
        except KeyError:
            return None
        if isinstance(q, pd.DataFrame):
            q = q.iloc[0]
        return q

    def spot(self, td):
        return self.chains[td]["underlying_price"].iloc[0]

    def settle_close(self, exp):
        """Underlying close on expiry day (last trading day <= exp)."""
        idx = self.daily_close.index[self.daily_close.index <= exp]
        return float(self.daily_close.loc[idx[-1]]) if len(idx) else None

    def week_expiry_chain(self, td, lo=3, hi=7):
        ch = self.chains[td]
        wk = ch[(ch["dte"] >= lo) & (ch["dte"] <= hi)]
        if wk.empty:
            wk = ch[(ch["dte"] >= 1) & (ch["dte"] <= 10)]
        if wk.empty:
            return None
        exp = wk.loc[wk["dte"].idxmin(), "expiration"]
        return wk[wk["expiration"] == exp]

    def pick_short_put(self, chain, delta_target):
        g = chain[(chain["right"] == "PUT") & chain["liquid"] &
                  (chain["sell_px"] >= 0.05) & (chain["delta"] < 0)]
        whole = g[g["strike"] % 1 == 0]
        if len(whole):
            g = whole
        if g.empty:
            return None
        g = g.assign(dist=(g["delta"].abs() - delta_target).abs())
        row = g.loc[g["dist"].idxmin()]
        return None if row["dist"] > 0.15 else row

    def pick_anchor(self, td, cfg):
        ch = self.chains[td]
        g = ch[(ch["right"] == "PUT") & ch["liquid"] &
               (ch["dte"] >= cfg.anchor_dte_lo) &
               (ch["dte"] <= cfg.anchor_dte_hi)]
        if g.empty:  # widen if the window is empty on this date
            g = ch[(ch["right"] == "PUT") & ch["liquid"] &
                   (ch["dte"] >= 100) & (ch["dte"] <= 240)]
        if g.empty:
            return None
        exp = g.loc[(g["dte"] - cfg.anchor_dte).abs().idxmin(), "expiration"]
        g = g[g["expiration"] == exp]
        tgt = cfg.anchor_mness * self.spot(td)
        whole = g[g["strike"] % 1 == 0]
        if len(whole):
            g = whole
        return g.loc[(g["strike"] - tgt).abs().idxmin()]


# --------------------------------------------------------------------------
# backtest engine
# --------------------------------------------------------------------------
class PutDiagonalBacktest:
    def __init__(self, mkt: Market, cfg: Config):
        self.m, self.cfg = mkt, cfg
        self.cash = cfg.start_capital
        self.sweep = 0.0
        self.commissions = 0.0
        self.realized_log = []          # (date, leg, amount) audit trail
        self.anchor = None              # dict per open anchor position
        self.short = None
        self.blown = False
        self.week_rows = []
        self.wk = None                  # ledger row being assembled

    # --- cash-flow primitives (every $ goes through these) ---------------
    def pay(self, amt, what, allow_negative=False):
        """Discretionary buys must fit in cash; settlements/buybacks may
        drive cash negative (an IBKR margin debit) which the next decision
        day clears by liquidating anchor contracts (margin_call_check)."""
        self.cash -= amt
        if not allow_negative and amt > 0:
            assert self.cash > -EPS, \
                f"cash negative after {what}: {self.cash:.2f}"

    def realize(self, date, leg, amt):
        self.realized_log.append((date, leg, amt))
        self.wk[f"{leg}_realized_pnl"] = self.wk.get(
            f"{leg}_realized_pnl", 0.0) + amt

    def commission(self, contracts):
        c = COMMISSION * contracts
        self.commissions += c
        self.pay(c, "commission", allow_negative=True)
        return c

    # --- position marks --------------------------------------------------
    def mark(self, td, pos):
        if pos is None:
            return 0.0
        q = self.m.quote(td, pos["exp"], pos["strike"])
        px = pos["last_mark"] if q is None else float(q["mid"])
        pos["last_mark"] = px
        return px

    def equity(self, td):
        eq = self.cash
        if self.anchor:
            eq += self.mark(td, self.anchor) * 100 * self.anchor["n"]
        if self.short:
            eq -= self.mark(td, self.short) * 100 * self.short["n"]
        return eq

    # --- anchor management -----------------------------------------------
    def size_contracts(self, td, anchor_row):
        eq = self.equity(td)
        budget = self.cfg.invest_frac * eq
        if self.cfg.sizing == "premium":
            per = float(anchor_row["buy_px"]) * 100
        else:
            wk = self.m.week_expiry_chain(td)
            sp = self.m.pick_short_put(wk, self.cfg.short_delta) \
                if wk is not None else None
            ref_k = float(sp["strike"]) if sp is not None \
                else 0.9 * self.m.spot(td)
            per = ref_k * 100
        n = int(budget // per)
        cost_cap = int((self.cash - 1) // (float(anchor_row["buy_px"]) * 100
                                           + COMMISSION))
        return max(min(n, cost_cap), 0)

    def buy_anchor(self, td, note):
        row = self.m.pick_anchor(td, self.cfg)
        if row is None:
            self.wk["anchor_action"] = "NO_QUOTE"
            return
        n = self.size_contracts(td, row)
        if n == 0:
            self.wk["anchor_action"] = "SKIP_NO_CAPITAL"
            return
        px = float(row["buy_px"])
        self.pay(px * 100 * n, "anchor buy")
        self.commission(n)
        self.anchor = {"strike": float(row["strike"]),
                       "exp": row["expiration"], "n": n, "entry_px": px,
                       "entry_spot": self.m.spot(td), "entry_date": td,
                       "last_mark": float(row["mid"])}
        self.wk.update(anchor_action=note, anchor_strike=row["strike"],
                       anchor_expiration=str(row["expiration"].date()),
                       anchor_contracts=n, anchor_buy_price=px,
                       anchor_cost=round(px * 100 * n, 2),
                       anchor_note=(f"REAL QUOTE bid={row['bid']:.2f} "
                                    f"ask={row['ask']:.2f} dte={row['dte']}"))

    def sell_anchor(self, td, why, force=False):
        q = self.m.quote(td, self.anchor["exp"], self.anchor["strike"])
        if q is None or not bool(q["liquid"]):
            if not force:
                return False  # keep holding; retry next decision day
            # final liquidation with no live quote: value at last mark
            px = self.anchor["last_mark"]
            why += "|VALUED_AT_LAST_MARK"
        else:
            px = float(q["sell_px"])
        n = self.anchor["n"]
        proceeds = px * 100 * n
        self.cash += proceeds
        self.commission(n)
        pnl = (px - self.anchor["entry_px"]) * 100 * n
        self.realize(td, "anchor", pnl)
        self.wk.update(anchor_sell_price=px,
                       anchor_proceeds=round(proceeds, 2),
                       anchor_roll_reason=why)
        self.anchor = None
        return True

    def manage_anchor(self, td):
        c = self.cfg
        if c.no_anchor:
            self.wk["anchor_action"] = "DISABLED"
            return
        if self.anchor is None:
            self.buy_anchor(td, "BUY")
            return
        dte = (self.anchor["exp"] - td).days
        drift = self.m.spot(td) / self.anchor["entry_spot"] - 1
        if dte <= c.anchor_roll_dte:
            why = f"ROLL_DTE({dte}d)"
        elif abs(drift) >= c.anchor_roll_drift and \
                (c.roll_up or drift < 0):
            why = f"ROLL_DRIFT({drift:+.1%})"
        else:
            self.wk["anchor_action"] = "HOLD"
            self.wk.update(anchor_strike=self.anchor["strike"],
                           anchor_expiration=str(self.anchor["exp"].date()),
                           anchor_contracts=self.anchor["n"])
            return
        if self.sell_anchor(td, why):
            self.buy_anchor(td, why)

    # --- short put management --------------------------------------------
    def sell_short(self, td, chain, note, n_override=None):
        row = self.m.pick_short_put(chain, self.cfg.short_delta)
        if row is None:
            self.wk["short_action"] = self.wk.get("short_action",
                                                  "") + "|NO_QUOTE"
            return
        if n_override:
            n = n_override
        elif self.cfg.no_anchor:
            n = int(self.cfg.invest_frac * self.equity(td)
                    // (float(row["strike"]) * 100))
        else:
            base_n = self.anchor["n"] if self.anchor else 0
            n = int(self.cfg.short_ratio * base_n)
        if n <= 0:
            self.wk["short_action"] = "SKIP_NO_ANCHOR"
            return
        px = float(row["sell_px"])
        self.cash += px * 100 * n
        self.commission(n)
        self.short = {"strike": float(row["strike"]),
                      "exp": row["expiration"], "n": n, "credit_px": px,
                      "last_mark": float(row["mid"])}
        prem_prev = self.wk.get("short_premium_received", 0.0)
        self.wk.update(short_action=note, short_strike=row["strike"],
                       short_expiration=str(row["expiration"].date()),
                       short_contracts=n, short_credit_price=px,
                       short_premium_received=round(prem_prev
                                                    + px * 100 * n, 2),
                       short_note=(f"REAL QUOTE bid={row['bid']:.2f} "
                                   f"ask={row['ask']:.2f} "
                                   f"delta={row['delta']:.3f} "
                                   f"dte={row['dte']}"))

    def settle_short(self, settle_date):
        s = self.short
        px = self.m.settle_close(s["exp"])
        intrinsic = max(s["strike"] - px, 0.0)
        if intrinsic > 0:
            self.pay(intrinsic * 100 * s["n"], "short settlement",
                     allow_negative=True)
            outcome = f"SETTLED_ITM(close {px:.2f})"
        else:
            outcome = f"EXPIRED_WORTHLESS(close {px:.2f})"
        self.realize(settle_date, "short",
                     (s["credit_px"] - intrinsic) * 100 * s["n"])
        self.wk.update(short_settle_price=round(px, 2),
                       short_settle_cost=round(intrinsic * 100 * s["n"], 2),
                       short_outcome=outcome)
        self.short = None

    def defense_check(self, td):
        """EOD proxy for the intraday |delta|>=0.50 roll trigger."""
        s = self.short
        q = self.m.quote(td, s["exp"], s["strike"])
        if q is None or not bool(q["liquid"]):
            return
        if abs(float(q["delta"])) < self.cfg.defense_trigger:
            return
        px = float(q["buy_px"])
        self.pay(px * 100 * s["n"], "defense buyback", allow_negative=True)
        self.commission(s["n"])
        self.realize(td, "short", (s["credit_px"] - px) * 100 * s["n"])
        self.wk["short_outcome"] = (f"DEFENSE_CLOSED@{td.date()} "
                                    f"delta={q['delta']:.2f} px={px:.2f}")
        n = s["n"]
        self.short = None
        ch = self.m.chains[td]
        nxt = ch[(ch["right"] == "PUT") & (ch["dte"] >= 7) &
                 (ch["dte"] <= 14)]
        if len(nxt):
            exp = nxt.loc[nxt["dte"].idxmin(), "expiration"]
            self.sell_short(td, nxt[nxt["expiration"] == exp],
                            "DEFENSE_ROLL", n_override=n)

    def margin_call(self, td):
        """Sell just enough anchor contracts at the 20% rule to clear a
        negative cash balance left by an ITM settlement."""
        if self.anchor is None:
            return  # negative cash carries as a margin loan; rare
        q = self.m.quote(td, self.anchor["exp"], self.anchor["strike"])
        if q is None or not bool(q["liquid"]):
            return
        px = float(q["sell_px"])
        if px <= 0:
            return
        k = min(int(np.ceil((-self.cash + 50) / (px * 100))),
                self.anchor["n"])
        if k <= 0:
            return
        self.cash += px * 100 * k
        self.commission(k)
        self.realize(td, "anchor", (px - self.anchor["entry_px"]) * 100 * k)
        self.anchor["n"] -= k
        self.wk["anchor_note"] = (f"MARGIN_CALL_SOLD {k}x@{px:.2f}"
                                  + ("|ANCHOR_EXHAUSTED"
                                     if self.anchor["n"] == 0 else ""))
        if self.anchor["n"] == 0:
            self.anchor = None

    # --- weekly loop ------------------------------------------------------
    def run(self):
        dates = self.m.dates
        weeks = {}
        for d in dates:
            weeks.setdefault(d.to_period("W-SUN"), []).append(d)
        week_list = sorted(weeks)
        for wi, wk_p in enumerate(week_list):
            wdays = weeks[wk_p]
            d0 = wdays[0]
            self.wk = {"week_start": str(d0.date()),
                       "week_end": str(wdays[-1].date()),
                       "begin_cash": round(self.cash, 2),
                       "begin_equity": round(self.equity(d0), 2),
                       "begin_sweep": round(self.sweep, 2),
                       "spot_monday": round(self.m.spot(d0), 2)}
            n_realized_before = len(self.realized_log)

            # 0. settle any short that expired before this week began
            #    (e.g. Friday expiry when Friday wasn't an option trade day)
            if self.short and self.short["exp"] < d0:
                self.settle_short(d0)

            # 0b. clear any margin debit by liquidating anchor contracts;
            #     halt the run if total equity is gone (account blown)
            if self.equity(d0) <= 0:
                self.wk["anchor_action"] = "ACCOUNT_BLOWN"
                self.blown = True
                self.week_rows.append(self.wk | {
                    "end_cash": round(self.cash, 2),
                    "end_sweep": round(self.sweep, 2),
                    "end_equity": round(self.equity(d0), 2),
                    "end_total_wealth": round(self.equity(d0) + self.sweep,
                                              2),
                    "week_realized": 0.0, "sweep_amount": 0.0})
                break
            if self.cash < -EPS:
                self.margin_call(d0)

            # 1. decision day: anchor first (defines contracts), then short
            self.manage_anchor(d0)
            if self.short is None:
                ch = self.m.week_expiry_chain(d0)
                if ch is not None:
                    self.sell_short(d0, ch, "SELL")
            elif (self.short["exp"] - d0).days > 7:
                self.wk["short_action"] = "HELD_FROM_DEFENSE_ROLL"

            # 2. walk the week's remaining days: defense + settlement
            for d in wdays:
                if self.short and self.cfg.delta_defense and \
                        d < self.short["exp"] and d > d0:
                    self.defense_check(d)
                if self.short and d >= self.short["exp"]:
                    self.settle_short(d)

            # 3. final liquidation on the very last week
            last_week = wi == len(week_list) - 1
            if last_week:
                dl = wdays[-1]
                if self.short:
                    q = self.m.quote(dl, self.short["exp"],
                                     self.short["strike"])
                    if q is not None and bool(q["liquid"]):
                        px = float(q["buy_px"])
                        self.pay(px * 100 * self.short["n"], "final buyback",
                                 allow_negative=True)
                        self.commission(self.short["n"])
                        self.realize(dl, "short",
                                     (self.short["credit_px"] - px) * 100
                                     * self.short["n"])
                        self.wk["short_outcome"] = f"FINAL_BUYBACK@{px:.2f}"
                        self.short = None
                if self.anchor:
                    self.sell_anchor(dl, "FINAL_LIQUIDATION", force=True)
                    self.wk["anchor_action"] = (
                        self.wk.get("anchor_action", "") + "|FINAL_SELL")

            # 4. weekly sweep of positive net realized
            wk_realized = sum(a for (_, _, a)
                              in self.realized_log[n_realized_before:])
            swept = 0.0
            if wk_realized > 0 and not last_week:
                swept = self.cfg.sweep_frac * wk_realized
                swept = min(swept, max(self.cash, 0.0))
                self.pay(swept, "sweep")
                self.sweep += swept

            dl = wdays[-1]
            self.wk.update(
                spot_friday=round(self.m.spot(dl), 2),
                week_realized=round(wk_realized, 2),
                sweep_amount=round(swept, 2),
                end_cash=round(self.cash, 2),
                end_sweep=round(self.sweep, 2),
                end_equity=round(self.equity(dl), 2),
                end_total_wealth=round(self.equity(dl) + self.sweep, 2))
            self.week_rows.append(self.wk)
        return self.finish()

    # --- reporting & QA ---------------------------------------------------
    def finish(self):
        led = pd.DataFrame(self.week_rows)
        wealth = led["end_total_wealth"]
        ret = wealth.iloc[-1] / self.cfg.start_capital - 1
        yrs = len(led) / 52
        wk_ret = wealth.pct_change().dropna()
        dd = (wealth / wealth.cummax() - 1).min()
        realized = pd.DataFrame(self.realized_log,
                                columns=["date", "leg", "amt"])
        by_leg = realized.groupby("leg")["amt"].sum()

        # QA reconciliation: wealth from raw flows must equal tracked wealth
        final_tracked = self.cash + self.sweep
        recon = (self.cfg.start_capital + realized["amt"].sum()
                 - self.commissions)
        qa_ok = abs(recon - final_tracked) < 0.01
        cagr = (((wealth.iloc[-1] / self.cfg.start_capital) ** (1 / yrs) - 1)
                * 100 if wealth.iloc[-1] > 0 else -100.0)
        stats = {
            "config": self.cfg.label(), "weeks": len(led),
            "blown": self.blown,
            "end_wealth": round(wealth.iloc[-1], 2),
            "total_ret_pct": round(ret * 100, 1),
            "cagr_pct": round(cagr, 1),
            "max_dd_pct": round(dd * 100, 1),
            "ann_vol_pct": round(wk_ret.std() * np.sqrt(52) * 100, 1),
            "worst_wk_pct": round(wk_ret.min() * 100, 1),
            "income_weeks": int((led["week_realized"] > 0).sum()),
            "loss_weeks": int((led["week_realized"] < 0).sum()),
            "short_prem_collected": round(
                led.get("short_premium_received",
                        pd.Series(dtype=float)).sum(), 0),
            "short_realized": round(by_leg.get("short", 0.0), 0),
            "anchor_realized": round(by_leg.get("anchor", 0.0), 0),
            "anchor_rolls": int(led.get("anchor_roll_reason",
                                        pd.Series(dtype=object))
                                .notna().sum()),
            "sweep_final": round(self.sweep, 2),
            "commissions": round(self.commissions, 0),
            "qa_wealth_recon": "PASS" if qa_ok else
                               f"FAIL({recon:.2f} vs {final_tracked:.2f})",
        }
        return led, stats


# --------------------------------------------------------------------------
def run_grid(mkt):
    rows = []
    for sd in (0.15, 0.20, 0.225, 0.25, 0.30):
        for mness in (0.85, 0.90, 1.00):
            for sizing in ("notional", "premium"):
                for defense in (False, True):
                    cfg = Config(short_delta=sd, anchor_mness=mness,
                                 sizing=sizing, delta_defense=defense)
                    _, stats = PutDiagonalBacktest(mkt, cfg).run()
                    rows.append(stats)
    # sensitivity: anchor DTE, drift-roll cadence, and down-only rolls --
    # the first run showed the +/-10% drift roll fires ~every other week
    # on a 115%-vol underlying, so cadence is the decisive knob
    extras = [Config(anchor_dte=120), Config(anchor_dte=180)]
    for drift in (0.15, 0.20, 0.30):
        for up in (True, False):
            extras.append(Config(anchor_roll_drift=drift, roll_up=up))
            extras.append(Config(anchor_roll_drift=drift, roll_up=up,
                                 anchor_mness=0.90))
    extras.append(Config(roll_up=False))
    extras.append(Config(roll_up=False, anchor_mness=0.90))
    # attribution + ratio-diagonal variants (excess shorts are naked --
    # delta-neutralizes the anchor at the cost of undefined risk)
    extras.append(Config(no_anchor=True))
    for ratio in (1.5, 2.0, 3.0):
        extras.append(Config(short_ratio=ratio))
        extras.append(Config(short_ratio=ratio, anchor_mness=0.90))
    for cfg in extras:
        _, stats = PutDiagonalBacktest(mkt, cfg).run()
        rows.append(stats)
    return pd.DataFrame(rows).sort_values("end_wealth", ascending=False)


def main():
    QA_DIR.mkdir(exist_ok=True)
    print("loading data ...")
    mkt = Market()
    base = Config()
    print(f"base config: {base}")
    led, stats = PutDiagonalBacktest(mkt, base).run()
    led.to_csv(ROOT / "put_diagonal_ledger.csv", index=False)
    lines = ["R1 PUT DIAGONAL INCOME ENGINE -- BACKTEST REPORT",
             f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}",
             "NOTE: EOD decisions (option data is EOD); Monday-10:00 spec "
             "needs intraday option data (already on the request list).",
             "", "BASE CONFIG " + str(asdict(base)), ""]
    lines += [f"  {k}: {v}" for k, v in stats.items()]
    print("\n".join(lines[4:]))

    print("\nrunning parameter grid (62 permutations) ...")
    grid = run_grid(mkt)
    grid.to_csv(ROOT / "put_diagonal_grid.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_columns", 25):
        gtxt = grid.to_string(index=False)
    lines += ["", "PARAMETER GRID (sorted by end wealth)", gtxt]
    qa_fail = grid["qa_wealth_recon"].ne("PASS").sum()
    lines += ["", f"QA: wealth reconciliation failures across grid: "
                  f"{qa_fail} of {len(grid)}"]
    (QA_DIR / "put_diagonal_report.txt").write_text("\n".join(lines) + "\n")
    print(gtxt)
    print(f"\nledger -> put_diagonal_ledger.csv ({len(led)} weeks); "
          f"grid -> put_diagonal_grid.csv; report -> "
          f"qa/put_diagonal_report.txt; QA failures: {qa_fail}")


if __name__ == "__main__":
    main()
