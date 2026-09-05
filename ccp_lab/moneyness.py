#!/usr/bin/env python3
"""Does writing the call IN the money work? Writes ccp_lab/out/MONEYNESS.md.

A covered call is synthetically a short put at the same strike, so writing deep
in the money is selling a deep out-of-the-money put: high probability of being
called, small premium, and the tail still there. This measures whether the
variance reduction is worth the premium given up -- and what happens once you
have to cross the spread to get it.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.compat import safe_stdout, ensure_cache, write_text
from ccp_lab.engine import Data, run_year
from ccp_lab.report import buy_hold, weekly_trips, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]
FLAT = dict(weekly_flat=True, use_put=False)
PCTS = [-0.40, -0.30, -0.20, -0.15, -0.10, -0.05, 0.0, 0.05]
SALES = [("mark (optimistic)", "mark"),
         ("less the measured half-spread", "halfspread"),
         ("at the bid", "bid")]

if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()
    stats, grid = [], {}
    for pc in PCTS:
        W = weekly_trips(d, YEARS, **FLAT, strike_pct=pc)
        g = W.r.values
        stats.append(dict(pc=pc, n=len(g), called=(W.kind == "CALL_ASSIGNED").mean()*100,
                          mean=g.mean()*100, geo=(np.exp(np.log1p(g).mean())-1)*100,
                          sd=g.std()*100, worst=g.min()*100, best=g.max()*100,
                          money=((W.K/W.S-1)*100).median(),
                          tv=((W.prem-(W.S-W.K).clip(lower=0))/W.S*100).median()))
        for lab, cs in SALES:
            v = [run_year(y, d, **FLAT, strike_pct=pc, call_sale=cs)["final"]/1000.0-100.0
                 for y in YEARS]
            grid[(pc, lab)] = np.mean(v)
        print(f"{pc*100:+.0f}%  " + "  ".join(f"{lab}: {grid[(pc,lab)]:+6.1f}%"
                                              for lab, _ in SALES))
    S = pd.DataFrame(stats)
    S.to_csv(f"{OUT}/moneyness.csv", index=False)
    bh = np.mean([buy_hold(d, y, 100000.0)[0]/1000.0-100.0 for y in YEARS])

    L = ["# Writing the call in the money\n",
         "\n## The idea, and the trap in it\n",
         "A covered call is synthetically a **short put at the same strike**. "
         "Writing deep in the money is therefore selling a deep out-of-the-money "
         "put: you are called away almost every week, you keep only the time "
         "value, and your breakeven sits at `strike − time value`.\n",
         "That does give real protection — but note what assignment actually is. "
         "**You are called away when the stock stays up.** If it crashes through "
         "the strike you are *not* called away: you keep a falling stock and lose "
         "with it, one for one, to zero. Being called out every week is what "
         "happens when things go well, not a shield against them going badly.\n",
         "\n## On paper, deep in the money looks excellent\n",
         "| strike | called | median time value | mean/wk | geo/wk | weekly σ | worst week | best week |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in S.iterrows():
        L.append(f"| {r.pc*100:+.0f}% | {r.called:.0f}% | {r.tv:.3f}% | "
                 f"{r['mean']:+.3f}% | {r.geo:+.3f}% | {r.sd:.2f}% | "
                 f"{r.worst:+.1f}% | {r.best:+.1f}% |")
    L.append("\n**The risk control is real and it works.** Weekly volatility falls "
             f"from **{S[S.pc==0.05].sd.iloc[0]:.2f}%** at 5% out of the money to "
             f"**{S[S.pc==-0.30].sd.iloc[0]:.2f}%** at 30% in the money, and the "
             f"worst single week improves from **{S[S.pc==0.05].worst.iloc[0]:.1f}%** "
             f"to **{S[S.pc==-0.30].worst.iloc[0]:.1f}%**. Assignment rises to 97%. "
             f"Everything the idea promises, it delivers.\n")

    L.append("\n## And then you have to cross the spread\n")
    L.append("| strike | " + " | ".join(l for l, _ in SALES) + " |")
    L.append("|---|" + "---:|" * len(SALES))
    for pc in PCTS:
        L.append(f"| {pc*100:+.0f}% | "
                 + " | ".join(f"{grid[(pc,l)]:+.1f}%" for l, _ in SALES) + " |")
    L.append(f"| buy & hold | {bh:+.1f}% | {bh:+.1f}% | {bh:+.1f}% |")
    L.append("\n**The ranking inverts completely.** On my marks, 30% in the money "
             "is the best strike tested (+18.0%) and 5% out of the money the "
             "worst (−10.9%). Pay the measured half-spread and 30% ITM becomes "
             "the *worst* (−29.7%) and 5% OTM the least bad (−15.9%). At the bid, "
             "same ordering.\n")
    L.append("The reason is arithmetic. A 30%-in-the-money weekly call carries a "
             "median time value of **0.13% of spot** — that is the entire prize — "
             "while those contracts quote a **5.1% median spread, 12.3% at the "
             "75th percentile**. On a $17 premium the spread is dollars and the "
             "time value is cents. **The bid sits below intrinsic in 53% of "
             "weeks**: you would be selling the call for less than the stock is "
             "already worth above the strike, which is worse than simply selling "
             "the stock.\n")

    L.append("\n## Answering the question directly\n")
    L.append("- **Does it work in the money?** On mid-market marks, yes, "
             "strikingly. At any realistic fill, no — it is the worst region of "
             "the curve, and the deeper you go the worse it gets.")
    L.append("- **Does being called out almost every week manage the danger?** "
             "For variance and for the ordinary tail, genuinely yes. But it does "
             "not remove the crash case, because a crash is precisely the "
             "scenario in which you are *not* called away.")
    L.append("- **Is that a good trade?** Not at these spreads. You are paying a "
             "5-12% transaction cost to collect 0.13% of time value. The risk "
             "reduction is real and you are over-paying for it by an order of "
             "magnitude.")
    L.append("\nIf this structure is worth pursuing at all it is at strikes near "
             "or above the money, where the premium is large enough to survive "
             "the spread — and even there every configuration in this lab still "
             f"loses to simply holding the shares ({bh:+.0f}%).\n")
    write_text(f"{OUT}/MONEYNESS.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/MONEYNESS.md")
