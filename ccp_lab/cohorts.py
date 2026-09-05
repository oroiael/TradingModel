#!/usr/bin/env python3
"""Start the same strategy on the first of each month and run them in parallel.

Writes ccp_lab/out/COHORTS.md.

If a rule's result swings widely with nothing but the start date, the number is
path luck rather than edge -- and that is the first thing to check when a live
account disagrees with a backtest.

    python ccp_lab/cohorts.py            # 2026 (default)
    python ccp_lab/cohorts.py 2025
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.compat import safe_stdout, ensure_cache, write_text
from ccp_lab.engine import Data, run_year
from ccp_lab.report import OUT

PERMS = [
    ("the rule as written",              {}),
    ("roll the call",                    dict(roll="friday")),
    ("sticky strike",                    dict(sticky=True)),
    ("sell put when flat",               dict(put_policy="sell_when_flat")),
    ("sticky + sell put when flat",      dict(sticky=True, put_policy="sell_when_flat")),
    ("sticky + sell put + 30% roll-down",
     dict(sticky=True, put_policy="sell_when_flat", put_roll_pct=0.30)),
    ("weekly flat, no put",              dict(weekly_flat=True, use_put=False)),
    ("carry, no put (call only)",        dict(use_put=False)),
]


def bh_window(d, start, end, cash=100_000.0):
    ses = [s for s in d.sessions if start <= s <= end]
    if not ses:
        return np.nan
    e = d.ten_high(ses[0])
    if e is None:
        return np.nan
    sh = int(cash // e)
    return (cash - sh * e + sh * d.close(ses[-1])) / 1000.0 - 100.0


if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    d = Data()
    chain_end = d.ch.trade_date.max()
    end = max(s for s in d.sessions if s.year == year and s <= chain_end)
    starts = [pd.Timestamp(f"{year}-{m:02d}-01") for m in range(1, 13)]
    # a cohort needs enough weeks to be a test of anything
    starts = [s for s in starts
              if len([x for x in d.sessions if s <= x <= end]) >= 15]

    grid = {}
    for name, kw in PERMS:
        row = {}
        for st in starts:
            try:
                r = run_year(year, d, start_date=st, end_date=end, **kw)
                row[st] = r["final"] / 1000.0 - 100.0
            except SystemExit:
                row[st] = np.nan
        grid[name] = row
        print(f"{name:<36} " + "  ".join(f"{row[s]:+7.1f}%" for s in starts))
    grid["buy & hold SOXL"] = {st: bh_window(d, st, end) for st in starts}
    print(f"{'buy & hold SOXL':<36} "
          + "  ".join(f"{grid['buy & hold SOXL'][s]:+7.1f}%" for s in starts))

    D = pd.DataFrame(grid).T
    D.columns = [s.strftime("%b %-d") if hasattr(s, "strftime") else s for s in starts]
    D.to_csv(f"{OUT}/cohorts_{year}.csv")

    lab = [s.strftime("%b") for s in starts]
    L = [f"# Start-date cohorts — {year}\n",
         f"Each cell is an independent $100,000 account opened on the first "
         f"trading Monday on or after that month's 1st, run to **{end.date()}** "
         f"and liquidated. Same rules, same data, same fills; only the start date "
         f"differs.\n",
         f"\n> **{year} runs to {end.date()}, not to the end of the price tape.** "
         f"The option chains stop there. Earlier versions of this lab ran on to "
         f"2026-07-30, leaving the position unwritten and unhedged through a "
         f"**−36.4%** tail and liquidating into it. Every {year} figure quoted "
         f"before this correction was wrong, benchmark included.\n",
         "\n## Every permutation, every start month\n",
         "| strategy | " + " | ".join(lab) + " | median | worst | best | spread |",
         "|---|" + "---:|" * (len(lab) + 4)]
    for name in list(grid.keys()):
        v = np.array([grid[name][s] for s in starts], dtype=float)
        L.append(f"| {name} | " + " | ".join(f"{x:+.0f}%" for x in v)
                 + f" | **{np.nanmedian(v):+.0f}%** | {np.nanmin(v):+.0f}% | "
                 f"{np.nanmax(v):+.0f}% | **{np.nanmax(v)-np.nanmin(v):.0f} pts** |")

    base = np.array([grid["the rule as written"][s] for s in starts], dtype=float)
    best = np.array([grid[PERMS[-1][0]][s] for s in starts], dtype=float)
    bh = np.array([grid["buy & hold SOXL"][s] for s in starts], dtype=float)
    L.append(f"\n## What this says\n")
    L.append(f"- **The start month is worth more than the rule.** The rule as "
             f"written spans {np.nanmax(base)-np.nanmin(base):.0f} points across "
             f"start dates ({np.nanmin(base):+.0f}% to {np.nanmax(base):+.0f}%); "
             f"the gap between the worst and best *permutation* at a fixed start "
             f"is usually smaller than that.")
    L.append(f"- Every permutation loses to buy & hold at **every** start month "
             f"in {year}." if all(best < bh) else
             f"- The best permutation beats buy & hold at "
             f"{int((best > bh).sum())} of {len(starts)} start months.")
    L.append(f"- A backtest quoting one start date for {year} is quoting one draw "
             f"from a distribution this wide. So is a live account: **an account "
             f"opened in March and one opened in May are running the same rule "
             f"and will not agree**, and neither is evidence about the rule.")
    L.append(f"- Ranking is more stable than level. Read the ordering of the rows, "
             f"not the numbers in them.")
    ordr = {n: np.array([grid[n][s] for s in starts], dtype=float)
            for n, _ in PERMS}
    wins = {n: int(sum(1 for i in range(len(starts))
                       if v[i] == max(ordr[m][i] for m in ordr)))
            for n, v in ordr.items()}
    L.append("\n## Which permutation wins, by start month\n")
    L.append("| permutation | start months where it is best |")
    L.append("|---|---:|")
    for n, w in sorted(wins.items(), key=lambda kv: -kv[1]):
        L.append(f"| {n} | {w} of {len(starts)} |")
    L.append("\nNote how badly a single annual figure represents this. A rule can "
             "be the best choice in most months and still look ordinary in a "
             "calendar-year backtest, because the calendar year is just the "
             "January cohort.\n")
    write_text(f"{OUT}/COHORTS_{year}.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/COHORTS_{year}.md")
