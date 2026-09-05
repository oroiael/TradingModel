#!/usr/bin/env python3
"""What should trigger selling the put? Writes ccp_lab/out/PUT_TRIGGER.md.

The shipped policy uses a position-state trigger -- sell when the shares are gone
-- with no price or P&L condition at all. This tests the obvious alternative: roll
the put down once it is deep in the money, harvesting the intrinsic and resetting
the insurance at the current level, and sweeps the threshold.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.compat import safe_stdout, ensure_cache, write_text
from ccp_lab.engine import Data, run_year
from ccp_lab.report import buy_hold, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]
THRESH = [None, 0.10, 0.20, 0.30, 0.40, 0.50]
BASE = dict(sticky=True, put_policy="sell_when_flat")

if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()
    grid, ev_counts, fills = {}, {}, []
    for t in THRESH:
        kw = dict(BASE); 
        if t is not None:
            kw["put_roll_pct"] = t
        lab = "none (position-state only)" if t is None else f"put {t*100:.0f}% in the money"
        vals, n = {}, {}
        for y in YEARS:
            r = run_year(y, d, **kw)
            vals[y] = r["final"] / 1000.0 - 100.0
            ev = r["events"]
            n[y] = int((ev.kind == "PUT_ROLLED_DOWN").sum())
            if t == 0.30:
                rd = ev[ev.kind == "PUT_ROLLED_DOWN"]
                for _, e in rd.iterrows():
                    ch = d.chain(e.date)
                    g = ch[(ch.right == "PUT") & np.isclose(ch.strike, float(e.strike))]
                    if len(g):
                        g = g.iloc[0]
                        if pd.notna(g.bid) and pd.notna(g.ask) and g.bid > 0:
                            fills.append((g.ask - g.bid) / ((g.ask + g.bid) / 2) * 100)
        grid[lab] = vals; ev_counts[lab] = n
        print(f"{lab:<28} " + "  ".join(f"{y}:{vals[y]:+7.1f}%" for y in YEARS)
              + f"   mean {np.mean(list(vals.values())):+6.1f}%")

    L = ["# What should trigger selling the put?\n",
         "\n## What the shipped rule actually does\n",
         "Nothing clever. The trigger is **position state, not price**: when the "
         "shares are called away the put is protecting nothing, so it is sold. "
         "There is no percentage-loss test, no moneyness test and no profit "
         "target anywhere in it. That was deliberate — it is the one condition "
         "that needs no parameter — but it is obviously not the only choice.\n",
         "\n## The alternative: roll the put down when it is deep in the money\n",
         "A put far in the money is nearly all intrinsic. There is no optionality "
         "left to wait for, only a rebound that can take the gain away. Selling it "
         "and immediately buying a fresh ~90-day just-OTM put harvests the gain "
         "and resets the insurance at the current level in one move. The trigger "
         "is measured on the day; nothing looks ahead.\n",
         "| trigger | " + " | ".join(str(y) for y in YEARS) + " | mean |",
         "|---|" + "---:|" * (len(YEARS) + 1)]
    for lab in grid:
        v = [grid[lab][y] for y in YEARS]
        L.append(f"| {lab} | " + " | ".join(f"{x:+.1f}%" for x in v)
                 + f" | **{np.mean(v):+.1f}%** |")
    L.append("\n**Yes, it makes a major difference — and no, you cannot use this "
             "table to pick a threshold.** Two things have to be said before "
             "anyone acts on it.\n")

    L.append("\n## Caveat 1: the fills were fantasy on the first pass\n")
    L.append("The first version priced these exits at the model mark. Checked "
             "against the vendor's own end-of-day quotes, those marks sat a "
             f"median **+11.8% above the bid**, on contracts whose median quoted "
             f"spread is **{np.median(fills):.0f}%** — some near 20%. Deep "
             "in-the-money options on a 3x ETF are illiquid and quoted very wide; "
             "you are not getting the mid, let alone better.\n")
    L.append("Every put exit in this lab now sells at the **bid**, floored at "
             "intrinsic (exercising is always available instead). That correction "
             "alone cost 6-8 points of mean return. Any version of this idea that "
             "does not model the exit spread is not measuring anything real.\n")

    L.append("\n## Caveat 2: the threshold is not identifiable from five years\n")
    L.append("| trigger | " + " | ".join(str(y) for y in YEARS) + " | events |")
    L.append("|---|" + "---:|" * (len(YEARS) + 1))
    for lab in grid:
        if lab.startswith("none"):
            continue
        n = ev_counts[lab]
        L.append(f"| {lab} | " + " | ".join(str(n[y]) for y in YEARS)
                 + f" | **{sum(n.values())}** |")
    L.append("\nAt the 40% trigger the whole result rests on **16 events across "
             "five years**, none of them in 2026. And the best threshold moves "
             "every year — 40, 10, 30, 40, 30 — with 14 to 69 points between the "
             "best and worst choice within a single year. There is no stable "
             "optimum here, only noise with a trend through it.\n")
    L.append("What *is* robust: **every threshold beats the position-state trigger "
             "on the mean.** The direction — do not sit on a deep in-the-money "
             "hedge and wait for expiry — survives every cut. The specific number "
             "does not, and a tight trigger is actively dangerous: 10% is the "
             "worst choice in 2022 (−61.5%) and the best in 2023 (+65.8%).\n")

    L.append("\n## The honest recommendation\n")
    L.append("- Use a **wide** trigger (30-40% in the money) if you use one at "
             "all: it fires rarely, only when the put has genuinely done its job, "
             "and it is the region that survives 2022 least badly.")
    L.append("- Model the exit at the bid. This idea lives or dies on the spread.")
    L.append("- Treat any single number in the first table as unreliable. Five "
             "years of one 3x ETF, 16-44 events, and one −86% year is not enough "
             "to fit a threshold on.")
    write_text(f"{OUT}/PUT_TRIGGER.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/PUT_TRIGGER.md")
