#!/usr/bin/env python3
"""Sticky strike + selling the put once the shares are gone, together.

Writes ccp_lab/out/COMBO.md. The two fixes address the two halves of the same
event -- being called away at a strike the stock has already fallen below:
  * sticky      stops the cap being re-set down to the depressed price
  * sell-put    stops the hedge decaying unwatched after it has already paid
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.compat import safe_stdout, ensure_cache, write_text
from ccp_lab.engine import Data, run_year
from ccp_lab.report import buy_hold, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]
MODES = [("base — re-strike weekly, hold the put (the rule)", {}),
         ("sticky strike only", dict(sticky=True)),
         ("sell the put when flat only", dict(put_policy="sell_when_flat")),
         ("sticky + sell the put when flat",
          dict(sticky=True, put_policy="sell_when_flat"))]

if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()
    grid, rows = {}, []
    for name, kw in MODES:
        vals = {}
        for y in YEARS:
            r = run_year(y, d, **kw)
            lg, ev = r["ledger"], r["events"]
            w = lg.dropna(subset=["call_strike"])
            nw = int(lg["no_write_reason"].notna().sum()) if "no_write_reason" in lg else 0
            vals[y] = r["final"] / 1000.0 - 100.0
            rows.append(dict(mode=name, year=y, ret=vals[y],
                             premium=float(w.call_premium.sum()),
                             med_prem=float(w.prem_pct.median()) if len(w) else 0.0,
                             no_write=nw, weeks=len(lg),
                             assigned=int((ev.kind == "CALL_ASSIGNED").sum()),
                             pnl_sh=r["pnl"]["shares"], pnl_c=r["pnl"]["calls"],
                             pnl_p=r["pnl"]["puts"]))
        grid[name] = vals
        print(f"{name:<48} " + "  ".join(f"{y}:{vals[y]:+7.1f}%" for y in YEARS)
              + f"   mean {np.mean(list(vals.values())):+6.1f}%")
    bh = {y: buy_hold(d, y, 100000.0)[0] / 1000.0 - 100.0 for y in YEARS}
    grid["buy & hold SOXL"] = bh
    print(f"{'buy & hold SOXL':<48} " + "  ".join(f"{y}:{bh[y]:+7.1f}%" for y in YEARS)
          + f"   mean {np.mean(list(bh.values())):+6.1f}%")
    D = pd.DataFrame(rows)
    D.to_csv(f"{OUT}/combo.csv", index=False)
    C = D[D["mode"] == MODES[3][0]].set_index("year")
    A = D[D["mode"] == MODES[0][0]].set_index("year")

    b = np.array([grid[MODES[0][0]][y] for y in YEARS])
    s = np.array([grid[MODES[1][0]][y] for y in YEARS])
    p = np.array([grid[MODES[2][0]][y] for y in YEARS])
    c = np.array([grid[MODES[3][0]][y] for y in YEARS])

    L = ["# Sticky strike + selling the put when flat\n",
         "Both fixes attack the same event — being called away at a strike the "
         "stock has already fallen below. Sticky stops the cap being re-set down "
         "to the depressed price; selling the put stops the hedge decaying "
         "unwatched after it has already paid off.\n",
         "\n## Together\n",
         "| variant | " + " | ".join(str(y) for y in YEARS) + " | mean |",
         "|---|" + "---:|" * (len(YEARS) + 1)]
    for name in [m[0] for m in MODES] + ["buy & hold SOXL"]:
        v = [grid[name][y] for y in YEARS]
        L.append(f"| {name} | " + " | ".join(f"{x:+.1f}%" for x in v)
                 + f" | **{np.mean(v):+.1f}%** |")
    L.append("\nThe combination is the best of the four, and **2025 is the first "
             "time any variant beats buy & hold in an up year** (+55.6% against "
             "+45.4%). The mean across the five years goes from **−29.0% to "
             "+10.2%**.\n")

    L.append("\n## They overlap — this is not two independent fixes\n")
    L.append("| | " + " | ".join(str(y) for y in YEARS) + " | mean |")
    L.append("|---|" + "---:|" * (len(YEARS) + 1))
    for lab, v in [("sticky alone adds", s - b), ("selling the put alone adds", p - b),
                   ("sum of the two", (s - b) + (p - b)),
                   ("**actually delivered**", c - b),
                   ("overlap", (c - b) - ((s - b) + (p - b)))]:
        L.append(f"| {lab} | " + " | ".join(f"{x:+.1f}" for x in v)
                 + f" | {np.mean(v):+.1f} |")
    L.append("\nSub-additive on average: both rules are triggered by the same "
             "assignments, so fixing one reduces how much damage is left for the "
             "other to fix. 2024 is the exception, where they reinforce.\n")

    L.append("\n## What it costs, and what it is not\n")
    L.append("| year | premium, base | premium, combo | median weekly %, base | median weekly %, combo | Mondays with nothing sellable |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for y in YEARS:
        L.append(f"| {y} | ${A.loc[y,'premium']:,.0f} | ${C.loc[y,'premium']:,.0f} | "
                 f"{A.loc[y,'med_prem']:.2f}% | **{C.loc[y,'med_prem']:.2f}%** | "
                 f"{int(C.loc[y,'no_write'])} of {int(C.loc[y,'weeks'])} |")
    L.append(f"\n**This is not the strategy as specified.** Across the five years "
             f"{int(C.no_write.sum())} of {int(C.weeks.sum())} Mondays "
             f"({C.no_write.sum()/C.weeks.sum()*100:.0f}%) have no call worth "
             f"selling at all — the stranded strike is bid at zero, so there is "
             f"no trade and the shares run uncapped that week. That is where much "
             f"of the gain comes from, and it is the opposite of a weekly income "
             f"rule. If 5% a week is the objective, this variant does not "
             f"deliver it.\n")

    L.append("\n## Caveats\n")
    L.append("- Still loses to buy & hold on average (+10.2% vs +64.1%), and in "
             "every year except 2024 and 2025.")
    L.append("- 2022 remains bad (−44.8%). Sticky is a bet that declines "
             "mean-revert, and in 2022 the decline did not.")
    L.append("- Five years, one instrument, containing one −86% year and one "
             "+141% half-year. The ranking is worth more than any single number.")
    L.append("- No variant looks ahead: every rule fires on that day's data only.")
    write_text(f"{OUT}/COMBO.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/COMBO.md")
