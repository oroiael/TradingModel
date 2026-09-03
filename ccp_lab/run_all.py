#!/usr/bin/env python3
"""Run every year and write the cross-year rollup (ccp_lab/out/SUMMARY_ALL.md)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from ccp_lab.engine import Data, run_year, TARGET_PCT
from ccp_lab.report import write, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]

if __name__ == "__main__":
    data = Data()
    rows = []
    for y in YEARS:
        res = run_year(y, data)
        s = write(res, data)
        s.pop("text")
        rows.append(s)
        print(f"{y}: ${s['final']:>10,.0f}  {s['ret']:+7.1f}%   "
              f"buy&hold {s['bh_ret']:+8.1f}%   "
              f"median premium {s['med_prem_pct']:.2f}%   "
              f"{s['assigned']}/{s['assigned']+s['expired']} called away")
    df = pd.DataFrame(rows)
    df.to_csv(f"{OUT}/summary_all.csv", index=False)

    L = ["# SOXL covered call + 90-day protective put — all years\n",
         f"Each year is an independent run: $100,000 in on the first Monday, "
         f"everything liquidated at the last close. Premium target "
         f"{TARGET_PCT*100:.0f}% of the underlying value.\n",
         "\n## Year by year\n",
         "| year | final | return | buy & hold | max DD | median premium | median strike | called away |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in df.iterrows():
        L.append(f"| {int(r.year)} | ${r.final:,.0f} | **{r.ret:+.1f}%** | "
                 f"{r.bh_ret:+.1f}% | {r.maxdd:.1f}% | {r.med_prem_pct:.2f}% | "
                 f"{r.med_otm_pct:+.2f}% OTM | "
                 f"{int(r.assigned)}/{int(r.assigned+r.expired)} |")
    L.append("\n## P&L by leg\n")
    L.append("| year | shares | short calls | long puts | fees | total |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for _, r in df.iterrows():
        L.append(f"| {int(r.year)} | ${r.pnl_shares:+,.0f} | ${r.pnl_calls:+,.0f} | "
                 f"${r.pnl_puts:+,.0f} | ${-r.fees:+,.0f} | "
                 f"${r.final-100000:+,.0f} |")
    tot = df[["pnl_shares", "pnl_calls", "pnl_puts", "fees"]].sum()
    L.append(f"| **all** | **${tot.pnl_shares:+,.0f}** | **${tot.pnl_calls:+,.0f}** | "
             f"**${tot.pnl_puts:+,.0f}** | **${-tot.fees:+,.0f}** | "
             f"**${df.final.sum()-100000*len(df):+,.0f}** |")
    L.append("\nEach year starts fresh at $100,000, so the totals are the sum of five "
             "independent $100k experiments, not a compounded track record.\n")
    open(f"{OUT}/SUMMARY_ALL.md", "w").write("\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/SUMMARY_ALL.md")
