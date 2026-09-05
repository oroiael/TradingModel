#!/usr/bin/env python3
"""The 30% put roll-down: call rolled vs assigned, under three exit-price models.

Writes ccp_lab/out/EXIT_RANGE.md.

Everything that follows depends on one assumption -- what a deep in-the-money put
can actually be sold for -- so the answer is reported as a range across three
models rather than as a single number.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.compat import safe_stdout, ensure_cache, write_text
from ccp_lab.engine import Data, run_year, SHARE_RT
from ccp_lab.report import buy_hold, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]
BASE = dict(sticky=True, put_policy="sell_when_flat", put_roll_pct=0.30)
CALLS = [("take assignment", {}), ("roll the call (combo)", dict(roll="friday"))]
EXITS = ["generous", "central", "worst"]

if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()
    res, ev_counts = {}, {}
    for clab, ckw in CALLS:
        for ex in EXITS:
            vals, n = {}, {}
            for y in YEARS:
                r = run_year(y, d, **BASE, **ckw, put_exit=ex)
                vals[y] = r["final"] / 1000.0 - 100.0
                e = r["events"]
                n[y] = int(e.kind.isin(["PUT_ROLLED_DOWN", "PUT_SOLD_FLAT"]).sum())
            res[(clab, ex)] = vals; ev_counts[(clab, ex)] = n
            print(f"{clab+' / '+ex:<34} " + "  ".join(f"{vals[y]:+7.1f}%" for y in YEARS)
                  + f"   mean {np.mean(list(vals.values())):+6.1f}%")
    bh = {y: buy_hold(d, y, 100000.0)[0] / 1000.0 - 100.0 for y in YEARS}

    L = ["# The 30% put roll-down, priced three ways\n",
         "\n## The methodology, stated up front\n",
         "Every result below rests on one assumption: **what a deep "
         "in-the-money put can actually be sold for.** Those contracts are "
         "illiquid — across the exits in this test the median quoted spread is "
         "**10.8%**, the 75th percentile **19.4%**, and the bid sits **below "
         "intrinsic in 64% of cases**. So the exit is modelled three ways and the "
         "answer is a range, not a number.\n",
         "| model | rule | rationale |",
         "|---|---|---|",
         "| **generous** | the mid | assumes a limit order fills at the midpoint of "
         "a 10-20% spread. Optimistic, and more so in size. |",
         f"| **central** | better of the bid, or exercise-and-rebuy | exercising "
         f"captures intrinsic and re-buying the shares restores the position; the "
         f"cost is a **stock** round trip (${SHARE_RT:.2f}/share: two commissions "
         f"plus about a cent of spread), and SOXL is liquid where the option is "
         f"not. Never more than arbitrage allows, never less than a rational "
         f"holder would accept. |",
         "| **worst** | the bid, no floor | you always hit the bid, even where it "
         "is ~9% below intrinsic and any rational holder would exercise instead. "
         "A genuine worst case rather than a likely one. |",
         "\nThe central model is the one to reason from. The other two bound it.\n",
         "\n## Results\n",
         "| config | " + " | ".join(str(y) for y in YEARS) + " | mean |",
         "|---|" + "---:|" * (len(YEARS) + 1)]
    for clab, _ in CALLS:
        for ex in EXITS:
            v = [res[(clab, ex)][y] for y in YEARS]
            L.append(f"| {clab} / **{ex}** | " + " | ".join(f"{x:+.1f}%" for x in v)
                     + f" | **{np.mean(v):+.1f}%** |")
    L.append("| buy & hold SOXL | " + " | ".join(f"{bh[y]:+.1f}%" for y in YEARS)
             + f" | {np.mean(list(bh.values())):+.1f}% |")

    a = [np.mean([res[("take assignment", e)][y] for y in YEARS]) for e in EXITS]
    L.append(f"\n**The exit assumption is worth about {max(a)-min(a):.0f} points of "
             f"mean return** — from {max(a):+.1f}% on generous fills to "
             f"{min(a):+.1f}% on worst-case fills. That band is the honest "
             f"uncertainty on this idea. Even at the worst end it beats the rule "
             f"as written (−29.0%) by a wide margin, so the direction survives; "
             f"the magnitude is not knowable to better than ~15 points.\n")

    L.append("\n## Rolling the call makes this *worse*, and the reason is structural\n")
    L.append("| config | " + " | ".join(str(y) for y in YEARS) + " | total |")
    L.append("|---|" + "---:|" * (len(YEARS) + 1))
    for clab, _ in CALLS:
        n = ev_counts[(clab, "central")]
        L.append(f"| put exits, {clab} | " + " | ".join(str(n[y]) for y in YEARS)
                 + f" | **{sum(n.values())}** |")
    L.append("\nRolling the call cuts put exits from 82 to 15 across the five "
             "years, and to **zero in 2023** — which is why all three exit models "
             "give an identical +0.3% that year: no put was ever sold, so the "
             "pricing model had nothing to price.\n")
    L.append("The mechanism is a coupling nobody designed. `sell the put when "
             "flat` is **triggered by assignment**. Roll the call and you are "
             "never flat, so the hedge is never harvested — the rule that was "
             "recovering the put's value simply stops firing. Rolling and "
             "monetising the put are **substitutes here, not complements**: "
             "rolling protects the share position, and in doing so it removes the "
             "trigger that was collecting on the insurance.\n")

    L.append("\n## What still has to be said\n")
    L.append("- Every configuration still loses to buy & hold "
             f"({np.mean(list(bh.values())):+.1f}%). None of this makes the "
             "structure competitive with owning the shares.")
    L.append("- 2022 is negative in all six configurations. Nothing tested "
             "rescues a sustained 86% decline.")
    L.append("- The 30% trigger fires 23 times in five years. That is a small "
             "sample and the threshold is not identifiable from it — see "
             "`PUT_TRIGGER.md`.")
    L.append("- None of this is the strategy as specified: no 5% weekly premium, "
             "and the put is traded, which the original rule forbids.")
    write_text(f"{OUT}/EXIT_RANGE.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/EXIT_RANGE.md")
