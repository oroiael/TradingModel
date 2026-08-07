"""
The two questions that decide UVXY's fate: what does it cost, and what does
it do to the portfolio.

Costs use `band_lab/phase1/cost_model.py` unchanged — the same IBKR Pro Fixed
schedule, the same assumptions, the same $150K sleeve. The only new input is
UVXY's current tradeable price, which matters more than it sounds: IBKR bills
per *share*, so the cheaper the instrument the dearer the strategy, and UVXY
is the cheapest of the three by a wide margin.

Portfolio math treats each sleeve as the spec does — its own sub-account at
weight w, uncommitted capital in cash, no cross-funding — so an OFF day
contributes 0, not NaN.

Run:
    python3 vix_lab/uvxy_portfolio.py
"""

from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(ROOT, "band_lab", "live"),
           os.path.join(ROOT, "band_lab", "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cost_model import (CURRENT_PX, CostConfig, daily_cost_series,  # noqa: E402
                        trade_cost_usd)

OUT = os.path.join(_HERE, "out")
SLEEVE_CAPITAL = 150_000.0

#: Last close in each 1-minute file — the price you would actually trade at.
#: UVXY's is from 2026-07-31; the others match `cost_model.CURRENT_PX`.
PX = dict(CURRENT_PX, UVXY=23.26)


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


def load(sym: str) -> tuple[pd.Series, pd.DataFrame]:
    on = pd.read_csv(os.path.join(OUT, f"daily_{sym}.csv"),
                     index_col=0, parse_dates=True).iloc[:, 0]
    tr = pd.read_csv(os.path.join(OUT, f"trades_{sym}.csv"), parse_dates=["date"])
    return on, tr


def metrics(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    return {"bp": r.mean() * 1e4, "sharpe": r.mean() / r.std() * np.sqrt(252)
            if r.std() else float("nan"), "dd": dd,
            "worst": r.min(), "n": len(r)}


def main() -> int:
    syms = ("SOXL", "SOXS", "UVXY")
    on, tr = {}, {}
    for s in syms:
        on[s], tr[s] = load(s)

    # ------------------------------------------------------------- costs
    hdr("1. Cost per round trip — the project's own model, UVXY added")
    print("IBKR Pro Fixed: $0.005/share with a $1.00 order minimum. $150K of a")
    print("$23 ETF is 6,449 shares; of a $158 ETF, 946. The commission scales")
    print("with share count, so the cost in bp scales with 1/price.\n")
    cfg = CostConfig()
    print(f"{'sleeve':<8}{'price':>9}{'shares':>9}{'exit':>9}{'comm$':>9}"
          f"{'reg$':>8}{'exec$':>8}{'total$':>9}{'bp':>8}")
    for s in syms:
        for outcome in ("target", "stop"):
            c = trade_cost_usd(PX[s], outcome, cfg, SLEEVE_CAPITAL)
            print(f"{s:<8}{PX[s]:>9.2f}{int(c['qty']):>9}{outcome:>9}"
                  f"{c['commission']:>9.2f}{c['regulatory']:>8.2f}"
                  f"{c['execution']:>8.2f}{c['total']:>9.2f}"
                  f"{c['total'] / SLEEVE_CAPITAL * 1e4:>8.2f}")

    hdr("2. Gross vs net edge, per ON-day")
    print(f"{'sleeve':<8}{'ON days':>9}{'trades/d':>10}{'gross bp':>10}"
          f"{'cost bp':>9}{'NET bp':>9}{'net Sharpe':>12}")
    net = {}
    rows = []
    for s in syms:
        cost = daily_cost_series(tr[s], PX[s], cfg, on[s].index, SLEEVE_CAPITAL)
        n = on[s] - cost
        net[s] = n
        tpd = len(tr[s]) / len(on[s])
        sh = n.mean() / n.std() * np.sqrt(252) if n.std() else float("nan")
        print(f"{s:<8}{len(on[s]):>9}{tpd:>10.2f}{on[s].mean() * 1e4:>10.1f}"
              f"{cost.mean() * 1e4:>9.1f}{n.mean() * 1e4:>9.1f}{sh:>12.2f}")
        rows.append({"sleeve": s, "on_days": len(on[s]), "trades_per_day": tpd,
                     "gross_bp": on[s].mean() * 1e4, "cost_bp": cost.mean() * 1e4,
                     "net_bp": n.mean() * 1e4, "net_sharpe": sh})
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "net_edge.csv"), index=False)
    print("\nThe published SOXL/SOXS net figures (62.4 / 49.2) were struck")
    print("against the 5-minute gross edge. These are struck against the")
    print("1-minute gross edge, which S11 established is the honest one.")

    # ------------------------------------------- 3. portfolio combinations
    hdr("3. What a third leg does to the portfolio")
    print("Each sleeve is its own sub-account at weight w; an OFF day earns 0")
    print("on that sleeve's capital. Portfolio return = sum(w_i * r_i).")
    print("Costs included. Calendar = every session any sleeve could trade.\n")
    cal = sorted(set().union(*[set(v.index) for v in net.values()]))
    R = pd.DataFrame({s: net[s].reindex(cal).fillna(0.0) for s in syms})
    R.to_csv(os.path.join(OUT, "net_daily_all.csv"))

    combos = [
        ("SOXL+SOXS  (INCUMBENT)", {"SOXL": .50, "SOXS": .50}),
        ("SOXL+SOXS+UVXY  1/3", {"SOXL": 1 / 3, "SOXS": 1 / 3, "UVXY": 1 / 3}),
        ("SOXL+SOXS+UVXY .4/.4/.2", {"SOXL": .40, "SOXS": .40, "UVXY": .20}),
        ("SOXL+UVXY (UVXY for SOXS)", {"SOXL": .50, "UVXY": .50}),
        ("SOXS+UVXY (UVXY for SOXL)", {"SOXS": .50, "UVXY": .50}),
        ("SOXL alone", {"SOXL": .50}),
        ("UVXY alone", {"UVXY": .50}),
    ]
    print(f"{'portfolio':<28}{'bp/session':>12}{'ann %':>9}{'Sharpe':>9}"
          f"{'maxDD':>9}{'worst day':>11}")
    for name, w in combos:
        r = sum(R[s] * wt for s, wt in w.items())
        m = metrics(r)
        ann = (1 + r).prod() ** (252 / len(r)) - 1
        print(f"{name:<28}{m['bp']:>12.1f}{ann * 100:>9.1f}{m['sharpe']:>9.2f}"
              f"{m['dd'] * 100:>9.1f}{m['worst'] * 100:>11.2f}")
    print("\n'bp/session' is per calendar session, not per ON-day, so it is")
    print("directly comparable across rows with different ON rates.")

    hdr("4. Correlation of NET daily P&L (all sessions, OFF days = 0)")
    print(f"{'':<8}", end="")
    for s in syms:
        print(f"{s:>9}", end="")
    print()
    for a in syms:
        print(f"{a:<8}", end="")
        for b in syms:
            print(f"{R[a].corr(R[b]):>9.3f}", end="")
        print()
    print("\nUVXY is a long-volatility instrument and SOXS is a short-")
    print("semiconductor one. Both rise when risk appetite falls, so a")
    print("dip-buying sleeve on each wins on the same days. That is the")
    print("opposite of what a third leg is supposed to supply.")

    hdr("5. Marginal test — does UVXY add anything SOXS does not already?")
    print("Regress the UVXY sleeve's daily P&L on the two incumbents. What is")
    print("left over (alpha) is the only thing a third leg can contribute.\n")
    X = np.column_stack([np.ones(len(R)), R["SOXL"].to_numpy(), R["SOXS"].to_numpy()])
    y = R["UVXY"].to_numpy()
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    r2 = 1 - resid.var() / y.var()
    print(f"  UVXY = {beta[0] * 1e4:+.2f} bp  {beta[1]:+.3f}*SOXL  "
          f"{beta[2]:+.3f}*SOXS     R^2 = {r2:.3f}")
    t = beta[0] / (resid.std() / np.sqrt(len(R)))
    print(f"  alpha {beta[0] * 1e4:+.2f} bp/session, t = {t:+.2f}")
    print(f"  residual sd {resid.std() * 1e4:.1f} bp/session")
    if abs(t) < 2:
        print("\n  The alpha is not distinguishable from zero. Whatever UVXY")
        print("  earns, a combination of the two existing sleeves already")
        print("  earns — and earns more cheaply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
