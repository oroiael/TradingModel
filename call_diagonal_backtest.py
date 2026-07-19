#!/usr/bin/env python3
"""
R2 -- Call Diagonal / Poor Man's Covered Call (PMCC) backtest
=============================================================

Structure (per STRATEGY_RECOMMENDATIONS.md, strategy R2):

    * LONG LEG : deep-ITM call (`long_delta` target, default 0.75),
                 120-180 DTE -- the stock-replacement leg, priced off the
                 F5 finding that SOXL synthetic longs are ~2-3%/yr cheaper
                 than shares.  Rolled out to ~`long_dte` when DTE <=
                 `long_roll_dte`.  Optional re-strikes: "harvest" when
                 delta >= `restrike_hi` (roll up, banking ITM value) and
                 "repair" when delta <= `restrike_lo` (roll down to restore
                 the delta target).
    * SHORT LEG: sell N weekly calls at `short_delta` target (default
                 0.175 = the 15-20d band) in that week's expiry; held to
                 expiration, cash-settled at intrinsic off the expiry-day
                 close from the 5-min file.  Always 1:1 covered by the
                 long leg (no naked upside -- S1 shows the up-tail is the
                 fat one).
    * DEFENSE  : optional EOD proxy of the intraday roll trigger -- if the
                 short call's delta >= `defense_trigger` mid-week, buy it
                 back (20% rule) and re-sell 7-14 DTE out at the target
                 delta.

The same engine also runs the CONTROLS by swapping the long leg / short
leg on or off (`long_kind`, `no_short`):

    pmcc          long_kind="call",   shorts on   <- the R2 strategy
    long_only     long_kind="call",   shorts off  (stock-replacement alone)
    covered_call  long_kind="shares", shorts on   (the classic to beat)
    buy_hold      long_kind="shares", shorts off  (the benchmark)

Execution: project-standard 20%-of-spread rule from REAL quotes (no
Black-Scholes).  Shares trade at the option file's EOD underlying price.
Option quotes are EOD snapshots, so all decisions are EOD.

Capital: start $150,000; deploy `invest_frac`=75%; sweep 25% of each
week's positive net realized P&L.  Sizing modes:
    share_repl : contracts = invest_frac*equity / (spot*100)
                 (same notional as a 75% share position; the unspent
                 premium difference stays in cash -- earning
                 `cash_apy`, default 0% = conservative)
    premium    : contracts = invest_frac*equity / (long call cost*100)
                 (aggressive; ~2-3x share notional)

Outputs:
    call_diagonal_ledger.csv   weekly per-leg ledger (base config)
    call_diagonal_grid.csv     permutations + controls summary
    qa/call_diagonal_report.txt

QA: cash-flow reconciliation asserted on every run (start capital + all
realized P&L + interest - commissions == final cash + sweep).
"""

from dataclasses import dataclass, asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import ROOT
from put_diagonal_backtest import Market, COMMISSION, EPS

QA_DIR = Path(__file__).resolve().parent / "qa"


@dataclass(frozen=True)
class Config:
    long_kind: str = "call"         # "call" (PMCC) or "shares" (controls)
    no_short: bool = False          # disable the weekly short-call leg
    short_delta: float = 0.175      # 15-20d band midpoint
    long_delta: float = 0.75        # deep-ITM target for the long call
    long_dte: int = 150
    long_dte_lo: int = 120
    long_dte_hi: int = 180
    long_roll_dte: int = 45
    restrike_hi: float = 0.0        # e.g. 0.93: roll up to harvest; 0 = off
    restrike_lo: float = 0.0        # e.g. 0.55: roll down to repair; 0 = off
    delta_defense: bool = False
    defense_trigger: float = 0.50
    sizing: str = "share_repl"      # or "premium"
    invest_frac: float = 0.75
    sweep_frac: float = 0.25
    cash_apy: float = 0.0           # interest on idle positive cash
    start_capital: float = 150_000.0

    def label(self):
        if self.long_kind == "shares":
            base = "BUYHOLD" if self.no_short else "COVERED_CALL"
            return f"{base}_c{self.short_delta:.0%}" if not self.no_short \
                else base
        parts = [f"pmcc_c{self.short_delta:.0%}",
                 f"L{self.long_delta:.0%}", f"t{self.long_dte}",
                 self.sizing]
        if self.no_short:
            parts.insert(0, "LONGONLY")
        if self.restrike_hi:
            parts.append(f"h{self.restrike_hi:.0%}")
        if self.restrike_lo:
            parts.append(f"lo{self.restrike_lo:.0%}")
        if self.delta_defense:
            parts.append("def")
        if self.cash_apy:
            parts.append(f"apy{self.cash_apy:.0%}")
        return "_".join(parts)


class CallMarket(Market):
    def pick_short_call(self, chain, delta_target):
        g = chain[(chain["right"] == "CALL") & chain["liquid"] &
                  (chain["sell_px"] >= 0.05) & (chain["delta"] > 0)]
        whole = g[g["strike"] % 1 == 0]
        if len(whole):
            g = whole
        if g.empty:
            return None
        g = g.assign(dist=(g["delta"] - delta_target).abs())
        row = g.loc[g["dist"].idxmin()]
        return None if row["dist"] > 0.15 else row

    def pick_long_call(self, td, cfg):
        ch = self.chains[td]
        g = ch[(ch["right"] == "CALL") & ch["liquid"] &
               (ch["dte"] >= cfg.long_dte_lo) & (ch["dte"] <= cfg.long_dte_hi)
               & (ch["delta"] > 0)]
        if g.empty:
            g = ch[(ch["right"] == "CALL") & ch["liquid"] &
                   (ch["dte"] >= 100) & (ch["dte"] <= 240) & (ch["delta"] > 0)]
        if g.empty:
            return None
        exp = g.loc[(g["dte"] - cfg.long_dte).abs().idxmin(), "expiration"]
        g = g[g["expiration"] == exp]
        whole = g[g["strike"] % 1 == 0]
        if len(whole):
            g = whole
        return g.loc[(g["delta"] - cfg.long_delta).abs().idxmin()]


class CallDiagonalBacktest:
    def __init__(self, mkt: CallMarket, cfg: Config):
        self.m, self.cfg = mkt, cfg
        self.cash = cfg.start_capital
        self.sweep = 0.0
        self.commissions = 0.0
        self.interest = 0.0
        self.realized_log = []
        self.long = None            # call contract or share lot
        self.short = None
        self.blown = False
        self.week_rows = []
        self.wk = None

    # --- primitives -------------------------------------------------------
    def pay(self, amt, what, allow_negative=False):
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

    # --- marks ------------------------------------------------------------
    def long_mark(self, td):
        if self.long is None:
            return 0.0
        if self.cfg.long_kind == "shares":
            # per-share mark; position value = mark * 100 * n_lots
            return self.m.spot(td)
        q = self.m.quote(td, self.long["exp"], self.long["strike"], "CALL")
        if q is not None:
            self.long["last_mark"] = float(q["mid"])
        return self.long["last_mark"]

    def equity(self, td):
        eq = self.cash
        if self.long:
            eq += self.long_mark(td) * 100 * self.long["n"]
        if self.short:
            q = self.m.quote(td, self.short["exp"], self.short["strike"],
                             "CALL")
            if q is not None:
                self.short["last_mark"] = float(q["mid"])
            eq -= self.short["last_mark"] * 100 * self.short["n"]
        return eq

    # --- long leg ---------------------------------------------------------
    def size_contracts(self, td, per_contract_cost):
        eq = self.equity(td)
        budget = self.cfg.invest_frac * eq
        if self.cfg.sizing == "premium" and self.cfg.long_kind == "call":
            per = per_contract_cost * 100
        else:
            per = self.m.spot(td) * 100          # share-notional sizing
        n = int(budget // per)
        cap = int((self.cash - 1) // (per_contract_cost * 100 + COMMISSION))
        return max(min(n, cap), 0)

    def buy_long(self, td, note):
        if self.cfg.long_kind == "shares":
            px = self.m.spot(td)                 # per share
            n = self.size_contracts(td, px)      # lots of 100 shares
            if n == 0:
                self.wk["long_action"] = "SKIP_NO_CAPITAL"
                return
            self.pay(px * 100 * n, "share buy")
            self.long = {"kind": "shares", "n": n, "entry_px": px,
                         "last_mark": px}
            self.wk.update(long_action=note, long_contracts=n,
                           long_buy_price=px,
                           long_cost=round(px * 100 * n, 2),
                           long_note=f"SHARES {n * 100} @ {px:.2f} (EOD "
                                     f"underlying price)")
            return
        row = self.m.pick_long_call(td, self.cfg)
        if row is None:
            self.wk["long_action"] = "NO_QUOTE"
            return
        px = float(row["buy_px"])
        n = self.size_contracts(td, px)
        if n == 0:
            self.wk["long_action"] = "SKIP_NO_CAPITAL"
            return
        self.pay(px * 100 * n, "long call buy")
        self.commission(n)
        self.long = {"kind": "call", "strike": float(row["strike"]),
                     "exp": row["expiration"], "n": n, "entry_px": px,
                     "last_mark": float(row["mid"])}
        self.wk.update(long_action=note, long_strike=row["strike"],
                       long_expiration=str(row["expiration"].date()),
                       long_contracts=n, long_buy_price=px,
                       long_cost=round(px * 100 * n, 2),
                       long_note=(f"REAL QUOTE bid={row['bid']:.2f} "
                                  f"ask={row['ask']:.2f} "
                                  f"delta={row['delta']:.3f} "
                                  f"dte={row['dte']}"))

    def sell_long(self, td, why, force=False):
        if self.cfg.long_kind == "shares":
            px = self.m.spot(td)
            n = self.long["n"]
            self.cash += px * 100 * n
            self.realize(td, "long",
                         (px - self.long["entry_px"]) * 100 * n)
            self.wk.update(long_sell_price=px, long_roll_reason=why)
            self.long = None
            return True
        q = self.m.quote(td, self.long["exp"], self.long["strike"], "CALL")
        if q is None or not bool(q["liquid"]):
            if not force:
                return False
            px = self.long["last_mark"]
            why += "|VALUED_AT_LAST_MARK"
        else:
            px = float(q["sell_px"])
        n = self.long["n"]
        self.cash += px * 100 * n
        self.commission(n)
        self.realize(td, "long", (px - self.long["entry_px"]) * 100 * n)
        self.wk.update(long_sell_price=px, long_roll_reason=why)
        self.long = None
        return True

    def manage_long(self, td):
        c = self.cfg
        if self.long is None:
            self.buy_long(td, "BUY")
            return
        if c.long_kind == "shares":
            self.wk.update(long_action="HOLD", long_contracts=self.long["n"])
            return
        dte = (self.long["exp"] - td).days
        q = self.m.quote(td, self.long["exp"], self.long["strike"], "CALL")
        delta = float(q["delta"]) if q is not None else None
        why = None
        if dte <= c.long_roll_dte:
            why = f"ROLL_DTE({dte}d)"
        elif delta is not None and c.restrike_hi and delta >= c.restrike_hi:
            why = f"RESTRIKE_HARVEST(delta={delta:.2f})"
        elif delta is not None and c.restrike_lo and delta <= c.restrike_lo:
            why = f"RESTRIKE_REPAIR(delta={delta:.2f})"
        if why is None:
            self.wk.update(long_action="HOLD",
                           long_strike=self.long["strike"],
                           long_expiration=str(self.long["exp"].date()),
                           long_contracts=self.long["n"])
            return
        if self.sell_long(td, why):
            self.buy_long(td, why)

    # --- short leg --------------------------------------------------------
    def sell_short(self, td, chain, note, n_override=None):
        row = self.m.pick_short_call(chain, self.cfg.short_delta)
        if row is None:
            self.wk["short_action"] = (self.wk.get("short_action", "")
                                       + "|NO_QUOTE")
            return
        n = n_override or (self.long["n"] if self.long else 0)
        if n <= 0:
            self.wk["short_action"] = "SKIP_NO_LONG"
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
        intrinsic = max(px - s["strike"], 0.0)
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
        s = self.short
        q = self.m.quote(td, s["exp"], s["strike"], "CALL")
        if q is None or not bool(q["liquid"]) or \
                float(q["delta"]) < self.cfg.defense_trigger:
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
        nxt = ch[(ch["right"] == "CALL") & (ch["dte"] >= 7) &
                 (ch["dte"] <= 14)]
        if len(nxt):
            exp = nxt.loc[nxt["dte"].idxmin(), "expiration"]
            self.sell_short(td, nxt[nxt["expiration"] == exp],
                            "DEFENSE_ROLL", n_override=n)

    def margin_call(self, td):
        """Clear a settlement debit by liquidating long-leg units."""
        if self.long is None:
            return
        if self.cfg.long_kind == "shares":
            px = self.m.spot(td)
        else:
            q = self.m.quote(td, self.long["exp"], self.long["strike"],
                             "CALL")
            if q is None or not bool(q["liquid"]):
                return
            px = float(q["sell_px"])
        if px <= 0:
            return
        k = min(int(np.ceil((-self.cash + 50) / (px * 100))), self.long["n"])
        if k <= 0:
            return
        self.cash += px * 100 * k
        if self.cfg.long_kind == "call":
            self.commission(k)
        self.realize(td, "long", (px - self.long["entry_px"]) * 100 * k)
        self.long["n"] -= k
        self.wk["long_note"] = f"MARGIN_CALL_SOLD {k}x@{px:.2f}"
        if self.long["n"] == 0:
            self.long = None

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
            n_before = len(self.realized_log)

            if self.cfg.cash_apy and self.cash > 0:
                i = self.cash * self.cfg.cash_apy / 52
                self.cash += i
                self.interest += i

            if self.short and self.short["exp"] < d0:
                self.settle_short(d0)
            if self.equity(d0) <= 0:
                self.wk["long_action"] = "ACCOUNT_BLOWN"
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

            self.manage_long(d0)
            if not self.cfg.no_short:
                if self.short is None:
                    ch = self.m.week_expiry_chain(d0)
                    if ch is not None:
                        self.sell_short(d0, ch, "SELL")
                elif (self.short["exp"] - d0).days > 7:
                    self.wk["short_action"] = "HELD_FROM_DEFENSE_ROLL"

            for d in wdays:
                if self.short and self.cfg.delta_defense and \
                        d > d0 and d < self.short["exp"]:
                    self.defense_check(d)
                if self.short and d >= self.short["exp"]:
                    self.settle_short(d)

            last_week = wi == len(week_list) - 1
            if last_week:
                dl = wdays[-1]
                if self.short:
                    q = self.m.quote(dl, self.short["exp"],
                                     self.short["strike"], "CALL")
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
                if self.long:
                    self.sell_long(dl, "FINAL_LIQUIDATION", force=True)
                    self.wk["long_action"] = (
                        self.wk.get("long_action", "") + "|FINAL_SELL")

            wk_realized = sum(a for (_, _, a)
                              in self.realized_log[n_before:])
            swept = 0.0
            if wk_realized > 0 and not last_week:
                swept = min(self.cfg.sweep_frac * wk_realized,
                            max(self.cash, 0.0))
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

    def finish(self):
        led = pd.DataFrame(self.week_rows)
        wealth = led["end_total_wealth"]
        yrs = len(led) / 52
        wk_ret = wealth.pct_change().dropna()
        dd = (wealth / wealth.cummax() - 1).min()
        realized = pd.DataFrame(self.realized_log,
                                columns=["date", "leg", "amt"])
        by_leg = (realized.groupby("leg")["amt"].sum()
                  if len(realized) else pd.Series(dtype=float))
        final_tracked = self.cash + self.sweep
        recon = (self.cfg.start_capital
                 + (realized["amt"].sum() if len(realized) else 0.0)
                 + self.interest - self.commissions)
        qa_ok = abs(recon - final_tracked) < 0.01
        cagr = (((wealth.iloc[-1] / self.cfg.start_capital) ** (1 / yrs) - 1)
                * 100 if wealth.iloc[-1] > 0 else -100.0)
        stats = {
            "config": self.cfg.label(), "weeks": len(led),
            "blown": self.blown,
            "end_wealth": round(wealth.iloc[-1], 2),
            "total_ret_pct": round(
                (wealth.iloc[-1] / self.cfg.start_capital - 1) * 100, 1),
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
            "long_realized": round(by_leg.get("long", 0.0), 0),
            "long_rolls": int(led.get("long_roll_reason",
                                      pd.Series(dtype=object))
                              .notna().sum()),
            "sweep_final": round(self.sweep, 2),
            "interest": round(self.interest, 0),
            "commissions": round(self.commissions, 0),
            "qa_recon": "PASS" if qa_ok else
                        f"FAIL({recon:.2f} vs {final_tracked:.2f})",
        }
        return led, stats


# --------------------------------------------------------------------------
def run_grid(mkt):
    rows = []
    # controls first: benchmark, covered call, long-call-only
    controls = [
        Config(long_kind="shares", no_short=True),                 # buy-hold
        Config(long_kind="shares", short_delta=0.175),             # CC 15-20d
        Config(long_kind="shares", short_delta=0.30),
        Config(no_short=True),                                     # long only
        Config(no_short=True, sizing="premium"),
    ]
    grid = []
    for sd in (0.10, 0.15, 0.175, 0.20, 0.25, 0.30):
        for ld in (0.70, 0.75, 0.80):
            for sizing in ("share_repl", "premium"):
                grid.append(Config(short_delta=sd, long_delta=ld,
                                   sizing=sizing))
    extras = [
        Config(delta_defense=True),
        Config(restrike_hi=0.93),
        Config(restrike_lo=0.55),
        Config(restrike_hi=0.93, restrike_lo=0.55),
        Config(restrike_hi=0.93, restrike_lo=0.55, delta_defense=True),
        Config(long_dte=120), Config(long_dte=180),
        Config(cash_apy=0.04),
        Config(sizing="premium", restrike_hi=0.93, restrike_lo=0.55),
    ]
    for cfg in controls + grid + extras:
        _, stats = CallDiagonalBacktest(mkt, cfg).run()
        rows.append(stats)
    return pd.DataFrame(rows).sort_values("end_wealth", ascending=False)


def main():
    QA_DIR.mkdir(exist_ok=True)
    print("loading data ...")
    mkt = CallMarket()
    base = Config()
    led, stats = CallDiagonalBacktest(mkt, base).run()
    led.to_csv(ROOT / "call_diagonal_ledger.csv", index=False)
    lines = ["R2 CALL DIAGONAL / PMCC -- BACKTEST REPORT",
             f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}",
             "NOTE: EOD decisions (option data is EOD).  cash_apy=0 in the "
             "base run (no interest invented); an apy4% sensitivity row is "
             "in the grid.",
             "", "BASE CONFIG " + str(asdict(base)), ""]
    lines += [f"  {k}: {v}" for k, v in stats.items()]
    print("\n".join(lines[4:]))

    print("\nrunning grid (50 runs incl. controls) ...")
    grid = run_grid(mkt)
    grid.to_csv(ROOT / "call_diagonal_grid.csv", index=False)
    with pd.option_context("display.width", 220, "display.max_columns", 25):
        gtxt = grid.to_string(index=False)
    qa_fail = grid["qa_recon"].ne("PASS").sum()
    lines += ["", "GRID + CONTROLS (sorted by end wealth)", gtxt,
              "", f"QA reconciliation failures: {qa_fail} of {len(grid)}"]
    (QA_DIR / "call_diagonal_report.txt").write_text("\n".join(lines) + "\n")
    print(gtxt)
    print(f"\nledger -> call_diagonal_ledger.csv ({len(led)} weeks); "
          f"grid -> call_diagonal_grid.csv; QA failures: {qa_fail}")


if __name__ == "__main__":
    main()
