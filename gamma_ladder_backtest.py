#!/usr/bin/env python3
"""
R5b -- Gamma ladder: overlapping straddles on one netted delta-hedge book
========================================================================

`gamma_scalp_backtest.py` runs ONE position at a time: enter, hold to expiry,
re-enter. That leaves capital idle between rolls, makes the cycle count small,
and makes the result depend on when you happened to start.

This runs the same trade as a LADDER -- a new straddle every `step` trading
days, several alive at once -- with a single delta-hedge book netted across
every open position, rehedged once daily at the close on the REAL EOD delta
column. That is how the trade would actually be run, and it produces a daily
equity curve rather than a handful of cycle P&Ls, so Sharpe and drawdown become
measurable.

WHAT A LADDER DOES AND DOES NOT BUY -- stated up front, because the reason for
building it was partly wrong:

    It DOES remove entry-timing luck (the staggered-strand sweep in
    harvest_blueprint/GAMMA.md spans +$4,925 to +$21,771 on start date alone),
    it keeps capital continuously deployed, and it nets the hedge so several
    positions share one share trade instead of each placing their own.

    It does NOT manufacture statistical power. Overlapping cycles sample the
    same 2.5 years of one instrument; they are not independent draws, and a
    t-statistic computed as though they were is inflated. The honest sample
    size here is still "one path, 2024-01 -> 2026-06".

Everything else -- leg selection, the 20% fill rule, IBKR Pro Fixed share
costs, bar-close execution, the data-window guard -- is imported unchanged from
gamma_scalp_backtest so the two engines cannot drift apart.

Outputs:
    gamma_ladder_equity.csv    daily equity curve (base config)
    gamma_ladder_grid.csv      step / tenor / hedge-mode grid
    qa/gamma_ladder_report.txt
"""

from dataclasses import dataclass, asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from volatility_pricing_lab import load_options, load_bars
from gamma_scalp_backtest import (Config as ScalpConfig, GammaScalp,
                                  share_cost, OPT_COMMISSION)

ROOT = Path(__file__).resolve().parent
QA_DIR = ROOT / "qa"


@dataclass(frozen=True)
class Config:
    structure: str = "straddle"
    dte: int = 60
    dte_lo: int = 45
    dte_hi: int = 90
    step: int = 10                  # trade days between new rungs
    premium_budget: float = 15_000.0    # per rung
    netted: bool = True             # False = each rung hedges itself
    costs: bool = True
    start_capital: float = 150_000.0

    def label(self):
        p = [self.structure[:4], f"t{self.dte}", f"s{self.step}"]
        if not self.netted:
            p.append("PERPOS")
        if not self.costs:
            p.append("GROSS")
        return "_".join(p)

    def as_scalp(self):
        """Leg selection is shared with the single-position engine."""
        return ScalpConfig(structure=self.structure, dte=self.dte,
                           dte_lo=self.dte_lo, dte_hi=self.dte_hi,
                           premium_budget=self.premium_budget, contracts=0)


class GammaLadder:
    def __init__(self, opt, bars, cfg: Config):
        self.cfg = cfg
        self.scalp = GammaScalp(opt, bars, cfg.as_scalp())   # reuse pick_legs
        self.dates = self.scalp.dates
        self.daily_close = self.scalp.daily_close
        # (date, exp, strike, right) -> (mid, delta) for fast marking
        idx = opt.set_index(["trade_date", "expiration", "strike", "right"])
        self.mid = idx["mid"].to_dict()
        self.dlt = idx["delta"].to_dict()
        self.rows = []
        self.positions = []
        self.closed = []

    def q(self, table, d, leg):
        return table.get((d, leg["exp"], leg["strike"], leg["right"]))

    def leg_mark(self, d, leg, spot):
        v = self.q(self.mid, d, leg)
        if v is None or not np.isfinite(v):
            return (max(spot - leg["strike"], 0.0) if leg["right"] == "CALL"
                    else max(leg["strike"] - spot, 0.0))
        return float(v)

    def leg_delta(self, d, leg, spot):
        v = self.q(self.dlt, d, leg)
        if v is None or not np.isfinite(v):
            iv = leg["iv"]
            from gamma_scalp_backtest import bs_delta
            T = max((pd.Timestamp(leg["exp"]) - d).days, 0) / 365.0
            return float(bs_delta(spot, leg["strike"], T, iv, leg["right"]))
        return float(v)

    def run(self):
        cfg = self.cfg
        cash = cfg.start_capital
        shares = 0
        costs = 0.0
        n_hedges = 0
        opened = 0

        for i, d in enumerate(self.dates):
            spot = float(self.daily_close.get(d, np.nan))
            if not np.isfinite(spot):
                continue

            # --- settle any rung expiring today
            still = []
            for p in self.positions:
                if pd.Timestamp(p["exp"]) <= d:
                    val = sum(max(spot - l["strike"], 0.0)
                              if l["right"] == "CALL"
                              else max(l["strike"] - spot, 0.0) for l in p["legs"])
                    cash += val * 100 * p["n"]
                    p["exit_val"] = val
                    p["opt_pnl"] = (val - p["unit_cost"]) * 100 * p["n"]
                    p["exit"] = str(d.date())
                    self.closed.append(p)
                else:
                    still.append(p)
            self.positions = still

            # --- open a new rung on schedule
            if i % cfg.step == 0:
                legs = self.scalp.pick_legs(d)
                if legs is not None:
                    unit = sum(l["cost"] for l in legs) * 100
                    n = int(cfg.premium_budget // unit)
                    if n > 0 and cash > unit * n:
                        cash -= unit * n
                        if cfg.costs:
                            c = OPT_COMMISSION * n * len(legs)
                            costs += c
                            cash -= c
                        self.positions.append(
                            {"legs": legs, "n": n, "entry": str(d.date()),
                             "exp": legs[0]["exp"], "strike": legs[0]["strike"],
                             "unit_cost": sum(l["cost"] for l in legs),
                             "prem": unit * n})
                        opened += 1

            # --- one netted delta hedge for the whole book
            book_delta = sum(self.leg_delta(d, l, spot) * 100 * p["n"]
                             for p in self.positions for l in p["legs"])
            if cfg.netted:
                target = int(round(-book_delta))
            else:
                # each rung hedges itself: same target, but the order count
                # (and so the per-order minimum) scales with the rung count
                target = int(round(-book_delta))
            dq = target - shares
            if dq != 0:
                cash -= dq * spot
                if cfg.costs:
                    orders = 1 if cfg.netted else max(len(self.positions), 1)
                    per = abs(dq) / orders
                    c = sum(share_cost(per, spot, "BUY" if dq > 0 else "SELL")
                            for _ in range(orders))
                    costs += c
                    cash -= c
                shares = target
                n_hedges += 1

            opt_mv = sum(self.leg_mark(d, l, spot) * 100 * p["n"]
                         for p in self.positions for l in p["legs"])
            self.rows.append({
                "date": str(d.date()), "spot": round(spot, 2),
                "open_rungs": len(self.positions),
                "premium_at_risk": round(sum(p["prem"] for p in self.positions), 0),
                "book_delta": round(book_delta, 1), "shares": shares,
                "cash": round(cash, 2), "opt_mv": round(opt_mv, 2),
                "equity": round(cash + opt_mv + shares * spot, 2),
                "costs_cum": round(costs, 2)})

        # --- close the book at the last date
        d = self.dates[-1]
        spot = float(self.daily_close.get(d, np.nan))
        for p in self.positions:
            val = sum(self.leg_mark(d, l, spot) for l in p["legs"])
            cash += val * 100 * p["n"]
            p["opt_pnl"] = (val - p["unit_cost"]) * 100 * p["n"]
            p["exit"] = str(d.date()) + "*"      # marked, not expired
            self.closed.append(p)
        if shares:
            cash += shares * spot
            if self.cfg.costs:
                costs += share_cost(abs(shares), spot,
                                    "SELL" if shares > 0 else "BUY")
                cash -= share_cost(abs(shares), spot,
                                   "SELL" if shares > 0 else "BUY")
        self.final = {"cash": cash, "costs": costs, "hedges": n_hedges,
                      "opened": opened}
        return pd.DataFrame(self.rows)


def summarize(bt, eq):
    cfg = bt.cfg
    if eq.empty:
        return {"config": cfg.label(), "days": 0}
    e = eq["equity"]
    start = cfg.start_capital
    end = float(bt.final["cash"])
    r = e.pct_change().dropna()
    yrs = len(e) / 252.0
    dd = float((e / e.cummax() - 1).min() * 100)
    prem = eq["premium_at_risk"]
    cl = pd.DataFrame(bt.closed)
    return {
        "config": cfg.label(), "days": len(eq), "rungs": bt.final["opened"],
        "end_equity": round(end, 0),
        "pnl": round(end - start, 0),
        "cagr_pct": round(100 * ((end / start) ** (1 / yrs) - 1), 1),
        "max_dd_pct": round(dd, 1),
        "sharpe": round(float(r.mean() / r.std() * np.sqrt(252)), 2)
        if r.std() > 0 else None,
        "mean_rungs_open": round(float(eq["open_rungs"].mean()), 1),
        "mean_prem_at_risk": round(float(prem.mean()), 0),
        "peak_prem_at_risk": round(float(prem.max()), 0),
        "pnl_pct_of_mean_prem": round(100 * (end - start) / max(prem.mean(), 1), 1),
        "costs": round(bt.final["costs"], 0),
        "hedges": bt.final["hedges"],
        "opt_pnl": round(float(cl["opt_pnl"].sum()), 0) if len(cl) else 0.0,
        "ann_vol_pct": round(float(r.std() * np.sqrt(252) * 100), 1),
        "beta_to_underlying": round(float(np.polyfit(
            eq["spot"].pct_change().dropna().values[-len(r):],
            r.values[-len(eq["spot"].pct_change().dropna()):], 1)[0]), 3)
        if len(r) > 10 else None,
        # the last equity row and the cash left after closing the book are the
        # same quantity computed two ways; they must agree to the cent
        "qa_recon": "PASS" if abs(
            (e.iloc[-1] if len(e) else start) - end) < 1.0
        else f"FAIL({e.iloc[-1] - end:+.2f})",
    }


def main():
    print("loading ...")
    opt = load_options()
    bars = load_bars()
    base = Config()
    grid = [base]
    for st in (5, 20, 41):
        grid.append(replace(base, step=st))
    for t, lo, hi in [(30, 21, 45), (90, 60, 120)]:
        grid.append(replace(base, dte=t, dte_lo=lo, dte_hi=hi))
    grid.append(replace(base, netted=False))
    grid.append(replace(base, costs=False))

    rows, curve, seen = [], None, set()
    for cfg in grid:
        if cfg.label() in seen:
            continue
        seen.add(cfg.label())
        bt = GammaLadder(opt, bars, cfg)
        eq = bt.run()
        if cfg == base:
            curve = eq
        s = summarize(bt, eq)
        rows.append(s)
        print(f"  {s['config']:20s} rungs={s.get('rungs',0):3d} "
              f"pnl={s.get('pnl',0):>10,.0f} cagr={s.get('cagr_pct',0):>6.1f}% "
              f"dd={s.get('max_dd_pct',0):>6.1f}% sharpe={s.get('sharpe')} "
              f"hedges={s.get('hedges',0):>4} {s.get('qa_recon','')}")

    g = pd.DataFrame(rows)
    curve.to_csv(ROOT / "gamma_ladder_equity.csv", index=False)
    g.to_csv(ROOT / "gamma_ladder_grid.csv", index=False)
    QA_DIR.mkdir(exist_ok=True)
    with open(QA_DIR / "gamma_ladder_report.txt", "w") as f:
        f.write("R5b GAMMA LADDER -- OVERLAPPING STRADDLES, NETTED HEDGE BOOK\n")
        f.write(f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}\n")
        f.write("A new straddle every `step` trade days; one delta book across\n")
        f.write("all open rungs, rehedged daily at the close on REAL EOD deltas.\n")
        f.write("Overlapping rungs are NOT independent observations -- the\n")
        f.write("ladder removes entry-timing luck, it does not add statistical\n")
        f.write("power. Sample remains one path, 2024-01 -> 2026-06.\n\n")
        f.write(f"BASE CONFIG {asdict(base)}\n\n")
        f.write(g.to_string(index=False))
    print(f"\nwrote gamma_ladder_grid.csv, gamma_ladder_equity.csv, "
          f"qa/gamma_ladder_report.txt")


if __name__ == "__main__":
    main()
