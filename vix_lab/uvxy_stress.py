"""
Two ways UVXY could still deserve a place, tested rather than assumed.

1. **The cost objection is a price artifact.** IBKR bills per share, so the
   18.1 bp/ON-day charge is really a statement that UVXY trades at $23. UVXY
   reverse-splits every year or two and each split divides the charge. If the
   cost is the only thing wrong, a split fixes it. Sweep the price and find
   out what is left.

2. **The gate may simply be mis-set for this instrument.** README §4 says the
   ATR5 gate "is not a risk-avoidance trick — it's where the edge lives".
   If UVXY's edge concentrates in its own high-volatility tail the way SOXL's
   does, a different threshold would find it. This is measurement, not a
   proposal: §12 is locked and V16-V18 rejected every re-tuning they tried.

Run:
    python3 vix_lab/uvxy_stress.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(ROOT, "band_lab", "live"),
           os.path.join(ROOT, "band_lab", "phase1"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cost_model import CostConfig, daily_cost_series  # noqa: E402
from strategy_core import session_stats  # noqa: E402
from uvxy_portfolio import PX, SLEEVE_CAPITAL, hdr, load, metrics  # noqa: E402
from uvxy_strategy import WINDOW, decision_from_1min  # noqa: E402

OUT = os.path.join(_HERE, "out")


def main() -> int:
    syms = ("SOXL", "SOXS", "UVXY")
    on, tr = {}, {}
    for s in syms:
        on[s], tr[s] = load(s)
    cfg = CostConfig()

    # ------------------------------------------------- 1. price sensitivity
    hdr("1. If UVXY reverse-split, would it pay? (cost vs share price)")
    print("UVXY closed at $23.26 on 2026-07-31. A 1:5 split puts it near $116,")
    print("a 1:10 near $233. Gross edge is scale-free, so only the cost moves.\n")
    print(f"{'UVXY price':>12}{'shares':>9}{'cost bp/ON-day':>16}"
          f"{'NET bp/ON-day':>15}{'net Sharpe':>12}")
    rows = []
    for px in (23.26, 46.52, 58.15, 116.30, 232.60, 465.20):
        c = daily_cost_series(tr["UVXY"], px, cfg, on["UVXY"].index, SLEEVE_CAPITAL)
        n = on["UVXY"] - c
        sh = n.mean() / n.std() * np.sqrt(252) if n.std() else float("nan")
        tag = "  <- today" if abs(px - 23.26) < .01 else (
            "  <- after 1:5" if abs(px - 116.30) < .01 else (
                "  <- after 1:10" if abs(px - 232.60) < .01 else ""))
        print(f"{px:>12.2f}{int(SLEEVE_CAPITAL // px):>9}{c.mean() * 1e4:>16.1f}"
              f"{n.mean() * 1e4:>15.1f}{sh:>12.2f}{tag}")
        rows.append({"price": px, "cost_bp": c.mean() * 1e4,
                     "net_bp": n.mean() * 1e4, "net_sharpe": sh})
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "uvxy_price_sensitivity.csv"),
                              index=False)
    print("\nCosts do vanish. What they uncover is the 16.3 bp gross edge —")
    print("against SOXL's 42.1 and SOXS's 32.2 on the same engine, same days,")
    print("same 1-minute fills. Even free, UVXY is the weakest of the three.")

    print("\nSame comparison with ALL THREE sleeves costed at zero, so the")
    print("instrument is judged on edge alone:")
    print(f"{'sleeve':<8}{'gross bp/ON-day':>18}{'gross Sharpe':>14}"
          f"{'ON rate':>10}{'bp/session':>12}")
    dec = {s: decision_from_1min(s) for s in syms}
    for s in syms:
        elig = len([d for d, _ in dec[s] if d >= WINDOW])
        sh = on[s].mean() / on[s].std() * np.sqrt(252)
        print(f"{s:<8}{on[s].mean() * 1e4:>18.1f}{sh:>14.2f}"
              f"{len(on[s]) / elig:>10.1%}"
              f"{on[s].mean() * 1e4 * len(on[s]) / elig:>12.1f}")

    # -------------------------------------------------- 2. gate conditioning
    hdr("2. Is UVXY's edge hiding in a higher volatility tail?")
    print("README §4 on SOXL: ATR5 quartile 1 loses -9 bp/day, quartile 4")
    print("makes +51. If UVXY behaved the same way, a higher gate would find")
    print("its edge. Quintiles of ATR5 among each sleeve's own ON-days.\n")
    for s in syms:
        rng = pd.Series({d: session_stats(b).range_pct for d, b in dec[s]})
        atr5 = rng.rolling(5).mean().shift(1)
        j = pd.DataFrame({"pnl": on[s], "atr5": atr5}).dropna()
        q = pd.qcut(j["atr5"], 5, labels=False, duplicates="drop")
        print(f"{s}  (n={len(j)})")
        print(f"{'  ATR5 quintile':<18}{'range':>16}{'n':>6}{'bp/ON-day':>12}"
              f"{'Sharpe':>9}")
        for k in sorted(set(q.dropna())):
            g = j[q == k]
            sh = g.pnl.mean() / g.pnl.std() * np.sqrt(252) if g.pnl.std() else float("nan")
            print(f"{'  Q' + str(int(k) + 1):<18}"
                  f"{f'{g.atr5.min():.1f}-{g.atr5.max():.1f}%':>16}{len(g):>6}"
                  f"{g.pnl.mean() * 1e4:>12.1f}{sh:>9.2f}")
        print()

    # ---------------------------------------------------- 3. why 2023 broke
    hdr("3. UVXY's worst year — was 2023 bad luck or a regime it cannot trade?")
    o = on["UVXY"]
    print(f"{'year':<7}{'ON days':>9}{'bp/ON-day':>11}{'med ATR5':>10}"
          f"{'mean intraday drift bp':>24}")
    rng = pd.Series({d: session_stats(b).range_pct for d, b in dec["UVXY"]})
    atr5 = rng.rolling(5).mean().shift(1)
    sess = {d: b for d, b in dec["UVXY"]}
    for y, g in o.groupby(o.index.year):
        drift = np.mean([np.log(next((x.close for x in reversed(sess[d])
                                      if x.idx <= 77), sess[d][-1].close)
                                / sess[d][0].open) for d in g.index]) * 1e4
        print(f"{y:<7}{len(g):>9}{g.mean() * 1e4:>11.1f}"
              f"{atr5.reindex(g.index).median():>10.2f}{drift:>24.1f}")
    print("\nThe strategy is long-only. A year in which UVXY bleeds down")
    print("through every session is a year in which buying dips off the")
    print("session high has nothing to recover to.")
    print("\nCorrelation across UVXY's ON-days between the day's intraday")
    print("drift and the sleeve's P&L:")
    dr = pd.Series({d: np.log(next((x.close for x in reversed(sess[d])
                                    if x.idx <= 77), sess[d][-1].close)
                              / sess[d][0].open) for d in o.index})
    print(f"  UVXY {o.corr(dr):+.3f}", end="")
    for s in ("SOXL", "SOXS"):
        ss = {d: b for d, b in dec[s]}
        d2 = pd.Series({d: np.log(next((x.close for x in reversed(ss[d])
                                        if x.idx <= 77), ss[d][-1].close)
                                  / ss[d][0].open) for d in on[s].index})
        print(f"   {s} {on[s].corr(d2):+.3f}", end="")
    print("\n  -> all three sleeves are strongly directional. The strategy is")
    print("     not a market-neutral churn harvester; it is a long bet that")
    print("     pays when its instrument rises during the day. That is why")
    print("     SOXL and SOXS are run as a PAIR, and it is why a third leg")
    print("     that leans the same way as SOXS adds risk, not diversity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
