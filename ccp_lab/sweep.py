#!/usr/bin/env python3
"""How much does the 5% target itself cost? Sweep the premium target.

Writes ccp_lab/out/SWEEP.md.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.engine import Data, run_year
from ccp_lab.report import OUT

YEARS = [2022, 2023, 2024, 2025, 2026]
TARGETS = [0.01, 0.02, 0.03, 0.04, 0.05]

if __name__ == "__main__":
    d = Data()
    out = {}
    for t in TARGETS:
        row = {}
        for y in YEARS:
            r = run_year(y, d, target_pct=t)
            w = r["ledger"].dropna(subset=["call_strike"])
            row[y] = r["final"] / 1000.0 - 100.0
            row[f"otm{y}"] = float(w.otm_pct.median()) if len(w) else np.nan
        out[t] = row
        print(f"target {t*100:.0f}%: " +
              "  ".join(f"{y}:{row[y]:+7.1f}%" for y in YEARS))

    L = ["# Sensitivity — what the 5% target itself costs\n",
         "Same rule, same data, same put. Only the premium the weekly call is "
         "written for changes. A lower target means a strike further out of the "
         "money, so less income but less of the upside capped away.\n",
         "| premium target | " + " | ".join(str(y) for y in YEARS) + " |",
         "|---|" + "---:|" * len(YEARS)]
    for t in TARGETS:
        L.append(f"| {t*100:.0f}% of underlying | " +
                 " | ".join(f"{out[t][y]:+.1f}%" for y in YEARS) + " |")
    L.append("\nMedian strike distance the target forces, by year:\n")
    L.append("| premium target | " + " | ".join(str(y) for y in YEARS) + " |")
    L.append("|---|" + "---:|" * len(YEARS))
    for t in TARGETS:
        L.append(f"| {t*100:.0f}% | " +
                 " | ".join(f"{out[t][f'otm{y}']:+.1f}%" for y in YEARS) + " |")
    L.append("\nThe 5% target is the most expensive setting tested in most years: "
             "it pins the strike closest to the money, which maximises both the "
             "premium and the frequency with which the stock is called away.\n")
    open(f"{OUT}/SWEEP.md", "w").write("\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/SWEEP.md")
