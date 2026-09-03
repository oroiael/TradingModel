#!/usr/bin/env python3
"""Every year, rolling the call, plus the assignment baseline for comparison.

Writes ccp_lab/out/SUMMARY_ROLL.md and the per-year summaries.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.engine import Data, run_year
from ccp_lab.report import write, buy_hold, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]
MODES = [("take assignment (baseline)", {}),
         ("buy back Friday, re-write Monday", dict(roll="rewrite")),
         ("roll as one combo order", dict(roll="friday"))]
RESERVES = [0.0, 0.05, 0.10, 0.20]

if __name__ == "__main__":
    d = Data()
    grid, detail = {}, []
    for name, kw in MODES:
        row = {}
        for y in YEARS:
            r = run_year(y, d, **kw)
            row[y] = r["final"] / 1000.0 - 100.0
            if kw.get("roll") == "friday":
                s = write(r, d, tag="_roll", label="rolling, never assigned")
                s.pop("text")
                detail.append(s)
        grid[name] = row
        print(f"{name:<34} " + "  ".join(f"{y}:{row[y]:+7.1f}%" for y in YEARS))
    bh = {y: buy_hold(d, y, 100000.0)[0] / 1000.0 - 100.0 for y in YEARS}
    grid["buy & hold SOXL"] = bh
    print(f"{'buy & hold SOXL':<34} " + "  ".join(f"{y}:{bh[y]:+7.1f}%" for y in YEARS))

    # how much dry powder does rolling need?
    sweep = {}
    for rp in RESERVES:
        row = {}
        for y in YEARS:
            r = run_year(y, d, roll="friday", reserve_pct=rp)
            ev = r["events"]
            row[y] = r["final"] / 1000.0 - 100.0
            row[f"a{y}"] = int((ev.kind == "CALL_ASSIGNED").sum())
        sweep[rp] = row

    D = pd.DataFrame(detail)
    D.to_csv(f"{OUT}/summary_roll.csv", index=False)

    L = ["# Rolling the call instead of taking assignment\n",
         "Same rule, same data, same put. The only change: on expiry day an "
         "in-the-money call is **bought back** rather than allowed to assign, and "
         "the far leg of the same combo order sells the following week's call "
         "(strike never below the old one, premium targeted at 5% of spot). Where "
         "the net debit cannot be funded from cash, the shares are still assigned "
         "and that is counted.\n",
         "\n## Headline\n",
         "| variant | " + " | ".join(str(y) for y in YEARS) + " |",
         "|---|" + "---:|" * len(YEARS)]
    for name in [m[0] for m in MODES] + ["buy & hold SOXL"]:
        L.append(f"| {name} | " +
                 " | ".join(f"{grid[name][y]:+.1f}%" for y in YEARS) + " |")
    L.append("\nRolling is a real improvement in three of the five years — 2025 and "
             "2026 swing by more than 40 points — and it is not a fix. The rule "
             "still loses money in 2022 and 2024, and still trails buy & hold in "
             "every year except the crash.\n")

    L.append("\n## What the rolls cost\n")
    L.append("| year | rolled | assigned anyway | paid to buy back | received on the far leg | net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for _, r in D.iterrows():
        L.append(f"| {int(r.year)} | {int(r.rolled)} | {int(r.assigned)} | "
                 f"${r.roll_cost:,.0f} | ${r.roll_credit:,.0f} | "
                 f"${r.roll_credit - r.roll_cost:+,.0f} |")
    L.append(f"| **all** | {int(D.rolled.sum())} | {int(D.assigned.sum())} | "
             f"**${D.roll_cost.sum():,.0f}** | **${D.roll_credit.sum():,.0f}** | "
             f"**${D.roll_credit.sum()-D.roll_cost.sum():+,.0f}** |")
    L.append("\nRolling does not make the loss go away — it **defers** it. The "
             "buyback pays the intrinsic that assignment would have surrendered, "
             "and the far leg only partly refunds it. What rolling actually buys "
             "is staying continuously long: the shares are never sold at the "
             "strike and never repurchased at Monday's higher open.\n")

    L.append("\n## How much cash does rolling need?\n")
    L.append("A buyback that cannot be funded is still an assignment, and the "
             "reinvest-everything rule leaves almost no cash on Friday. Holding "
             "back a share of equity fixes that:\n")
    L.append("| cash reserve | " + " | ".join(str(y) for y in YEARS) + " |")
    L.append("|---|" + "---:|" * len(YEARS))
    for rp in RESERVES:
        L.append(f"| {rp*100:.0f}% | " +
                 " | ".join(f"{sweep[rp][y]:+.1f}% ({sweep[rp][f'a{y}']} forced)"
                            for y in YEARS) + " |")
    L.append("\nThe reserve reliably removes the forced assignments, and barely "
             "moves the return. The funding constraint was real but it was never "
             "the thing driving the result.\n")
    open(f"{OUT}/SUMMARY_ROLL.md", "w").write("\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/SUMMARY_ROLL.md")
