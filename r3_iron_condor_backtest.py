#!/usr/bin/env python3
"""
R3 -- Asymmetric Weekly Iron Condor backtest
============================================

Structure (per STRATEGY_RECOMMENDATIONS.md, strategy R3):

    Every week, in that week's expiry (3-7 DTE from the first trade day):
        * sell 1 put  at `put_delta`  target (default 0.225 = 20-25d band)
        * sell 1 call at `call_delta` target (default 0.125 = 10-15d band)
        * buy  1 put  wing at the nearest LIQUID strike at or below
          short_put_strike  * (1 - width_pct)
        * buy  1 call wing at the nearest LIQUID strike at or above
          short_call_strike * (1 + width_pct)
    Hold to expiration; every leg cash-settles at intrinsic against the
    expiry-day close from the 5-min file.  `put_only` / `call_only` run the
    corresponding credit spread alone (attribution + asymmetric variants).

    Optional STOP: on any EOD between entry and expiry, if the cost to
    close the whole structure (20%-rule prices) exceeds `stop_mult` x the
    credit received, close everything and stand aside until next week.
    (EOD proxy for an intraday stop -- flagged.)

Sizing / margin: fully cash-collateralized.  IBKR requirement per condor
is max(put width, call width) x 100 minus the net credit; contracts are
sized so the requirement uses `margin_frac` of current equity (default
25%).  Max weekly loss is therefore capped near margin_frac of equity by
construction -- this is the "defined risk" in R3.

Execution: project-standard 20%-of-spread rule from REAL quotes; quotes
with bid=0 or inverted are rejected and the next nearest liquid strike is
used (project rule).  Capital: $150k start; sweep 25% of each week's
positive net realized P&L.  Commissions $0.65/contract/leg.

Outputs:
    r3_condor_ledger.csv      weekly per-leg ledger (base config)
    r3_condor_grid.csv        permutation summary
    qa/r3_condor_report.txt
"""

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import ROOT
from put_diagonal_backtest import Market, COMMISSION, EPS

QA_DIR = Path(__file__).resolve().parent / "qa"


@dataclass(frozen=True)
class Config:
    put_delta: float = 0.225
    call_delta: float = 0.125
    width_pct: float = 0.08         # wing distance as fraction of spot
    margin_frac: float = 0.25       # equity fraction used as condor margin
    put_only: bool = False          # bull put spread only
    call_only: bool = False         # bear call spread only
    stop_mult: float = 0.0          # e.g. 2.0: close if loss >= 2x credit
    min_credit_ratio: float = 0.0   # skip week if credit < ratio*max width
    sweep_frac: float = 0.25
    start_capital: float = 150_000.0

    def label(self):
        side = "IC"
        if self.put_only:
            side = "PUTSPREAD"
        if self.call_only:
            side = "CALLSPREAD"
        parts = [side, f"p{self.put_delta:.0%}" if not self.call_only
                 else "", f"c{self.call_delta:.0%}" if not self.put_only
                 else "", f"w{self.width_pct:.0%}",
                 f"m{self.margin_frac:.0%}"]
        if self.stop_mult:
            parts.append(f"stop{self.stop_mult:g}x")
        if self.min_credit_ratio:
            parts.append(f"mincr{self.min_credit_ratio:.0%}")
        return "_".join(p for p in parts if p)


def pick_by_delta(chain, right, target, max_dist=0.15):
    g = chain[(chain["right"] == right) & chain["liquid"] &
              (chain["sell_px"] >= 0.03)]
    g = g[g["delta"] < 0] if right == "PUT" else g[g["delta"] > 0]
    whole = g[g["strike"] % 1 == 0]
    if len(whole):
        g = whole
    if g.empty:
        return None
    g = g.assign(dist=(g["delta"].abs() - target).abs())
    row = g.loc[g["dist"].idxmin()]
    return None if row["dist"] > max_dist else row


def pick_wing(chain, right, short_strike, target_strike):
    """Nearest liquid strike at/beyond the target, past the short strike."""
    g = chain[(chain["right"] == right) & chain["liquid"]]
    if right == "PUT":
        g = g[g["strike"] < short_strike]
        g = g.assign(dist=(g["strike"] - target_strike).abs())
    else:
        g = g[g["strike"] > short_strike]
        g = g.assign(dist=(g["strike"] - target_strike).abs())
    if g.empty:
        return None
    return g.loc[g["dist"].idxmin()]


class IronCondorBacktest:
    def __init__(self, mkt: Market, cfg: Config):
        self.m, self.cfg = mkt, cfg
        self.cash = cfg.start_capital
        self.sweep = 0.0
        self.commissions = 0.0
        self.realized_log = []
        self.side_pnl = {"put": 0.0, "call": 0.0}
        self.week_rows = []

    def commission(self, contracts):
        c = COMMISSION * contracts
        self.commissions += c
        self.cash -= c

    # ------------------------------------------------------------------
    def build_condor(self, wk, spot):
        """Return dict of legs (each a quote row) or None + reason."""
        c = self.cfg
        legs = {}
        if not c.call_only:
            sp = pick_by_delta(wk, "PUT", c.put_delta)
            if sp is None:
                return None, "NO_SHORT_PUT"
            lp = pick_wing(wk, "PUT", sp["strike"],
                           sp["strike"] - c.width_pct * spot)
            if lp is None:
                return None, "NO_PUT_WING"
            legs |= {"sp": sp, "lp": lp}
        if not c.put_only:
            sc = pick_by_delta(wk, "CALL", c.call_delta)
            if sc is None:
                return None, "NO_SHORT_CALL"
            lc = pick_wing(wk, "CALL", sc["strike"],
                           sc["strike"] + c.width_pct * spot)
            if lc is None:
                return None, "NO_CALL_WING"
            legs |= {"sc": sc, "lc": lc}
        return legs, ""

    @staticmethod
    def leg_payoff(legs, px):
        """Intrinsic payoff per share at settlement price px, and the
        per-side short-leg P&L split (for attribution)."""
        pay, put_side, call_side = 0.0, 0.0, 0.0
        if "sp" in legs:
            v = (-max(legs["sp"]["strike"] - px, 0)
                 + max(legs["lp"]["strike"] - px, 0))
            pay += v
            put_side = v
        if "sc" in legs:
            v = (-max(px - legs["sc"]["strike"], 0)
                 + max(px - legs["lc"]["strike"], 0))
            pay += v
            call_side = v
        return pay, put_side, call_side

    def close_cost(self, td, legs):
        """Cost per share to close the structure at 20%-rule prices."""
        cost = 0.0
        for key, row in legs.items():
            right = "PUT" if key in ("sp", "lp") else "CALL"
            q = self.m.quote(td, row["expiration"], row["strike"], right)
            if q is None or not bool(q["liquid"]):
                return None
            cost += float(q["buy_px"]) if key in ("sp", "sc") \
                else -float(q["sell_px"])
        return cost

    # ------------------------------------------------------------------
    def run(self):
        c = self.cfg
        weeks = {}
        for d in self.m.dates:
            weeks.setdefault(d.to_period("W-SUN"), []).append(d)
        for wk_p in sorted(weeks):
            wdays = weeks[wk_p]
            d0 = wdays[0]
            spot = self.m.spot(d0)
            row = {"week_start": str(d0.date()),
                   "week_end": str(wdays[-1].date()),
                   "begin_cash": round(self.cash, 2),
                   "begin_sweep": round(self.sweep, 2),
                   "spot_monday": round(spot, 2)}
            chain = self.m.week_expiry_chain(d0)
            legs = None
            if chain is None:
                row["action"] = "SKIP_NO_EXPIRY"
            else:
                legs, why = self.build_condor(chain, spot)
                if legs is None:
                    row["action"] = f"SKIP_{why}"
            realized = 0.0
            if legs is not None:
                credit = sum(float(r["sell_px"]) for k, r in legs.items()
                             if k in ("sp", "sc"))
                credit -= sum(float(r["buy_px"]) for k, r in legs.items()
                              if k in ("lp", "lc"))
                pw = (legs["sp"]["strike"] - legs["lp"]["strike"]) \
                    if "sp" in legs else 0.0
                cw = (legs["lc"]["strike"] - legs["sc"]["strike"]) \
                    if "sc" in legs else 0.0
                maxw = max(pw, cw)
                req = maxw * 100 - credit * 100
                if credit <= 0.05 or req <= 0 or \
                        (c.min_credit_ratio and
                         credit < c.min_credit_ratio * maxw):
                    row["action"] = "SKIP_CREDIT_TOO_SMALL"
                    legs = None
                else:
                    n = int(min(c.margin_frac * (self.cash + 0),
                                self.cash * 0.95) // req)
                    if n <= 0:
                        row["action"] = "SKIP_NO_CAPITAL"
                        legs = None
                    else:
                        exp = next(iter(legs.values()))["expiration"]
                        self.cash += credit * 100 * n
                        self.commission(len(legs) * n)
                        row.update(
                            action="OPEN", n_condors=n,
                            credit=round(credit, 3),
                            credit_total=round(credit * 100 * n, 2),
                            margin_req=round(req * n, 2),
                            put_width=pw, call_width=cw,
                            expiration=str(exp.date()),
                            **{f"{k}_strike": float(r["strike"])
                               for k, r in legs.items()},
                            **{f"{k}_px": round(
                                float(r["sell_px" if k in ("sp", "sc")
                                        else "buy_px"]), 3)
                               for k, r in legs.items()},
                            legs_note=" | ".join(
                                f"{k}:K={r['strike']:g} "
                                f"bid={r['bid']:.2f} ask={r['ask']:.2f} "
                                f"d={r['delta']:.2f}"
                                for k, r in legs.items()))
                        # ---- hold through the week ----------------------
                        stopped = False
                        if c.stop_mult:
                            for d in wdays:
                                if d <= d0 or d >= exp:
                                    continue
                                cc = self.close_cost(d, legs)
                                if cc is None:
                                    continue
                                if cc - credit >= c.stop_mult * credit:
                                    self.cash -= cc * 100 * n
                                    self.commission(len(legs) * n)
                                    realized = (credit - cc) * 100 * n
                                    row["outcome"] = (
                                        f"STOPPED@{d.date()} "
                                        f"close_cost={cc:.2f}")
                                    stopped = True
                                    break
                        if not stopped:
                            px = self.m.settle_close(exp)
                            pay, ps, cs = self.leg_payoff(legs, px)
                            if pay < 0:
                                self.cash += pay * 100 * n
                            realized = (credit + pay) * 100 * n
                            self.side_pnl["put"] += ps * 100 * n
                            self.side_pnl["call"] += cs * 100 * n
                            row["settle_price"] = round(px, 2)
                            row["outcome"] = ("EXPIRED_MAX_PROFIT"
                                              if pay == 0 else
                                              f"SETTLED_ITM(pay {pay:.2f})")
                        self.realized_log.append((d0, realized))
            assert self.cash > -EPS, f"cash negative: {self.cash:.2f}"
            swept = 0.0
            if realized > 0:
                swept = min(c.sweep_frac * realized, self.cash)
                self.cash -= swept
                self.sweep += swept
            row.update(week_realized=round(realized, 2),
                       sweep_amount=round(swept, 2),
                       end_cash=round(self.cash, 2),
                       end_sweep=round(self.sweep, 2),
                       end_total_wealth=round(self.cash + self.sweep, 2))
            self.week_rows.append(row)
        return self.finish()

    # ------------------------------------------------------------------
    def finish(self):
        led = pd.DataFrame(self.week_rows)
        wealth = led["end_total_wealth"]
        yrs = len(led) / 52
        wk_ret = wealth.pct_change().dropna()
        dd = (wealth / wealth.cummax() - 1).min()
        realized = sum(a for _, a in self.realized_log)
        recon = self.cfg.start_capital + realized - self.commissions
        qa_ok = abs(recon - (self.cash + self.sweep)) < 0.01
        traded = led[led["action"] == "OPEN"]
        cagr = (((wealth.iloc[-1] / self.cfg.start_capital) ** (1 / yrs) - 1)
                * 100 if wealth.iloc[-1] > 0 else -100.0)
        stats = {
            "config": self.cfg.label(), "weeks": len(led),
            "weeks_traded": len(traded),
            "end_wealth": round(wealth.iloc[-1], 2),
            "total_ret_pct": round(
                (wealth.iloc[-1] / self.cfg.start_capital - 1) * 100, 1),
            "cagr_pct": round(cagr, 1),
            "max_dd_pct": round(dd * 100, 1),
            "worst_wk_pct": round(wk_ret.min() * 100, 1),
            "win_rate_pct": round(
                (traded["week_realized"] > 0).mean() * 100, 0),
            "avg_credit_total": round(traded["credit_total"].mean(), 0),
            "capture_pct": round(
                traded["week_realized"].sum()
                / traded["credit_total"].sum() * 100, 1)
            if traded["credit_total"].sum() else np.nan,
            "put_side_pnl": round(self.side_pnl["put"], 0),
            "call_side_pnl": round(self.side_pnl["call"], 0),
            "sweep_final": round(self.sweep, 2),
            "commissions": round(self.commissions, 0),
            "qa_recon": "PASS" if qa_ok else
                        f"FAIL({recon:.2f} vs {self.cash + self.sweep:.2f})",
        }
        return led, stats


# --------------------------------------------------------------------------
def run_grid(mkt):
    rows = []
    cfgs = []
    for pd_ in (0.20, 0.25, 0.30):
        for cd in (0.10, 0.15):
            for w in (0.05, 0.08):
                for mf in (0.25, 0.50):
                    cfgs.append(Config(put_delta=pd_, call_delta=cd,
                                       width_pct=w, margin_frac=mf))
    # side-only spreads (attribution + asymmetric play)
    for pd_ in (0.20, 0.25, 0.30):
        cfgs.append(Config(put_delta=pd_, put_only=True))
    for cd in (0.10, 0.15, 0.20):
        cfgs.append(Config(call_delta=cd, call_only=True))
    # management variants on the base
    cfgs += [Config(stop_mult=2.0), Config(stop_mult=3.0),
             Config(min_credit_ratio=0.15), Config(min_credit_ratio=0.25),
             Config(width_pct=0.12), Config(margin_frac=0.10),
             Config(stop_mult=2.0, margin_frac=0.50)]
    for cfg in cfgs:
        _, stats = IronCondorBacktest(mkt, cfg).run()
        rows.append(stats)
    return pd.DataFrame(rows).sort_values("end_wealth", ascending=False)


def main():
    QA_DIR.mkdir(exist_ok=True)
    print("loading data ...")
    mkt = Market()
    base = Config()
    led, stats = IronCondorBacktest(mkt, base).run()
    led.to_csv(ROOT / "r3_condor_ledger.csv", index=False)
    lines = ["R3 ASYMMETRIC WEEKLY IRON CONDOR -- BACKTEST REPORT",
             f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}",
             "EOD entries; stop checks are EOD proxies of intraday stops.",
             "", "BASE CONFIG " + str(asdict(base)), ""]
    lines += [f"  {k}: {v}" for k, v in stats.items()]
    print("\n".join(lines[4:]))

    print("\nrunning grid (37 permutations) ...")
    grid = run_grid(mkt)
    grid.to_csv(ROOT / "r3_condor_grid.csv", index=False)
    with pd.option_context("display.width", 220, "display.max_columns", 25):
        gtxt = grid.to_string(index=False)
    qa_fail = grid["qa_recon"].ne("PASS").sum()
    lines += ["", "GRID (sorted by end wealth)", gtxt, "",
              f"QA reconciliation failures: {qa_fail} of {len(grid)}"]
    (QA_DIR / "r3_condor_report.txt").write_text("\n".join(lines) + "\n")
    print(gtxt)
    print(f"\nledger -> r3_condor_ledger.csv; grid -> r3_condor_grid.csv; "
          f"QA failures: {qa_fail}")


if __name__ == "__main__":
    main()
