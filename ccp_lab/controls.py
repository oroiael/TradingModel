#!/usr/bin/env python3
"""Controls — take the rule apart leg by leg so the result can be explained.

Writes ccp_lab/out/CONTROLS.md.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.engine import Data, run_year
from ccp_lab.compat import write_text, safe_stdout, ensure_cache
from ccp_lab.report import buy_hold, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]

VARIANTS = [
    ("CC + long put (the rule)", dict(use_call=True,  use_put=True)),
    ("covered call only",        dict(use_call=True,  use_put=False)),
    ("shares + long put only",   dict(use_call=False, use_put=True)),
    ("shares only",              dict(use_call=False, use_put=False)),
    ("5% = total gain if called", dict(use_call=True, use_put=True,
                                       target_mode="total")),
    ("the rule, frictionless",   dict(use_call=True,  use_put=True, costs=False)),
]

if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()
    res = {}
    for name, kw in VARIANTS:
        row = {}
        for y in YEARS:
            r = run_year(y, d, **kw)
            row[y] = r["final"] / 1000.0 - 100.0        # % return
        res[name] = row
        print(f"{name:<28} " + "  ".join(f"{y}:{row[y]:+7.1f}%" for y in YEARS))
    bh = {}
    for y in YEARS:
        f, _ = buy_hold(d, y, 100000.0)
        bh[y] = f / 1000.0 - 100.0
    res["buy & hold SOXL"] = bh
    print(f"{'buy & hold SOXL':<28} " + "  ".join(f"{y}:{bh[y]:+7.1f}%" for y in YEARS))

    df = pd.DataFrame(res).T[YEARS]
    df.to_csv(f"{OUT}/controls.csv")
    L = ["# Controls — which leg costs the money\n",
         "Each cell is a standalone $100,000 run for that calendar year, "
         "same data, same fills, one rule changed.\n",
         "| variant | " + " | ".join(str(y) for y in YEARS) + " |",
         "|---|" + "---:|" * len(YEARS)]
    for name in list(dict(VARIANTS).keys()) + ["buy & hold SOXL"]:
        L.append(f"| {name} | " +
                 " | ".join(f"{df.loc[name, y]:+.1f}%" for y in YEARS) + " |")
    write_text(f"{OUT}/CONTROLS.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/CONTROLS.md")
