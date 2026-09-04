#!/usr/bin/env python3
"""Sticky strike vs re-striking every Monday. Writes ccp_lab/out/STICKY.md.

The rule as stated re-strikes to the 5%-premium target every Monday, which after
a decline re-caps the position at the new, lower price. The sticky variant keeps
the previous strike for as long as the shares are held, and re-strikes only when
the position is re-established (called away, or put exercised) or when the stock
has climbed back through the old strike.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.compat import safe_stdout, ensure_cache, write_text
from ccp_lab.engine import Data, run_year
from ccp_lab.report import buy_hold, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]
MODES = [("re-strike every Monday (the rule)", {}),
         ("sticky strike",                     dict(sticky=True)),
         ("sticky + combo roll",               dict(sticky=True, roll="friday"))]

if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()
    grid, detail = {}, []
    for name, kw in MODES:
        row = {}
        for y in YEARS:
            r = run_year(y, d, **kw)
            lg, ev = r["ledger"], r["events"]
            w = lg.dropna(subset=["call_strike"])
            row[y] = r["final"] / 1000.0 - 100.0
            detail.append(dict(mode=name, year=y, ret=row[y],
                               premium=float(w.call_premium.sum()),
                               med_prem=float(w.prem_pct.median()),
                               dead_weeks=float((w.prem_pct < 1.0).mean() * 100),
                               med_otm=float(w.otm_pct.median()),
                               max_otm=float(w.otm_pct.max()),
                               assigned=int((ev.kind == "CALL_ASSIGNED").sum()),
                               pnl_sh=r["pnl"]["shares"], pnl_c=r["pnl"]["calls"],
                               pnl_p=r["pnl"]["puts"]))
        grid[name] = row
        print(f"{name:<36} " + "  ".join(f"{y}:{row[y]:+7.1f}%" for y in YEARS))
    bh = {y: buy_hold(d, y, 100000.0)[0] / 1000.0 - 100.0 for y in YEARS}
    grid["buy & hold SOXL"] = bh
    print(f"{'buy & hold SOXL':<36} " + "  ".join(f"{y}:{bh[y]:+7.1f}%" for y in YEARS))
    D = pd.DataFrame(detail)
    D.to_csv(f"{OUT}/sticky.csv", index=False)
    A = D[D["mode"] == MODES[0][0]].set_index("year")
    B = D[D["mode"] == MODES[1][0]].set_index("year")

    L = ["# Sticky strike — keeping the old cap instead of re-striking down\n",
         "The rule as written picks a new strike every Monday at the 5%-premium "
         "target. After a decline that re-caps the position at the new, lower "
         "price, so a recovery is sold at the bottom. The sticky variant keeps the "
         "previous strike while the shares are held, and re-strikes only when the "
         "position is re-established or the stock has climbed back through it.\n",
         "\n## Headline\n",
         "| variant | " + " | ".join(str(y) for y in YEARS) + " |",
         "|---|" + "---:|" * len(YEARS)]
    for name in [m[0] for m in MODES] + ["buy & hold SOXL"]:
        L.append(f"| {name} | " +
                 " | ".join(f"{grid[name][y]:+.1f}%" for y in YEARS) + " |")
    L.append("\n**Sticky wins in four of the five years, and loses badly in the "
             "fifth.** 2022 is the year SOXL fell 86% and never came back inside "
             "the year: holding a stranded strike means collecting no premium "
             "through the entire decline, which is exactly when the cushion is "
             "wanted. Sticky is, in effect, a bet that a decline will mean-revert. "
             "Four times out of five in this sample it did.\n")

    L.append("\n## What you give up: the income engine switches off\n")
    L.append("| year | premium, re-strike | premium, sticky | median weekly %, re-strike | median weekly %, sticky | sticky weeks under 1% |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for y in YEARS:
        L.append(f"| {y} | ${A.loc[y,'premium']:,.0f} | ${B.loc[y,'premium']:,.0f} | "
                 f"{A.loc[y,'med_prem']:.2f}% | **{B.loc[y,'med_prem']:.2f}%** | "
                 f"{B.loc[y,'dead_weeks']:.0f}% |")
    L.append("\nThis is the honest cost, and it is severe. In 2025 the median "
             "weekly premium falls from **3.91% to 0.33%** and the year's income "
             "roughly halves. **The sticky variant is not a 5%-a-week income "
             "strategy at all** — it is buy-and-hold carrying an occasional "
             "stranded cap. If weekly income is the point of the exercise, this "
             "variant does not deliver it, whatever it does for the total return.\n")

    L.append("\n## What you get: you stop selling the recovery\n")
    L.append("| year | called away, re-strike | called away, sticky | share P&L, re-strike | share P&L, sticky |")
    L.append("|---|---:|---:|---:|---:|")
    for y in YEARS:
        L.append(f"| {y} | {int(A.loc[y,'assigned'])} | {int(B.loc[y,'assigned'])} | "
                 f"${A.loc[y,'pnl_sh']:+,.0f} | ${B.loc[y,'pnl_sh']:+,.0f} |")
    L.append("\nAssignments fall by roughly two thirds. The share leg — the thing "
             "that lost $124,424 in 2025 under the stated rule — turns positive.\n")

    L.append("\n## The mechanism: the strike strands far above the stock\n")
    L.append("| year | median strike OTM, re-strike | median strike OTM, sticky | furthest sticky strike got |")
    L.append("|---|---:|---:|---:|")
    for y in YEARS:
        L.append(f"| {y} | {A.loc[y,'med_otm']:+.1f}% | **{B.loc[y,'med_otm']:+.1f}%** | "
                 f"{B.loc[y,'max_otm']:+.0f}% |")
    L.append("\nThat is the whole trick, and it is almost accidental. Once the "
             "stock has fallen away from the old strike the call is nearly "
             "worthless, so almost no premium is collected — but the entire "
             "rebound up to that strike belongs to the shareholder. The stranded "
             "strike is not an income rule; it is a *stop-capping-after-a-decline* "
             "rule wearing an income rule's clothes.\n")

    L.append("\n## Caveats\n")
    L.append("- Five years, one instrument, one −86% year and one +141% half-year. "
             "The ranking is more trustworthy than any single number.")
    L.append("- Sticky's edge comes entirely from declines that recovered. A "
             "decline that keeps going (2022) makes it worse than the stated rule.")
    L.append("- Adding the combo roll on top of sticky mostly does not help: if "
             "you are rarely called away, there is little left to roll.")
    write_text(f"{OUT}/STICKY.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/STICKY.md")
