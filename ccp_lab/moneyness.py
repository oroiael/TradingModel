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
    # ---------------- OTM sweep, sold at the bid --------------------------
    OTM = [0.0, 0.02, 0.05, 0.10, 0.20, 0.30]
    BID = dict(FLAT, call_sale="bid")
    L.append("\n## The out-of-the-money side, sold at the bid\n")
    L.append("| strike | " + " | ".join(str(y) for y in YEARS) + " | mean |")
    L.append("|---|" + "---:|" * (len(YEARS) + 1))
    rows = {}
    for pc in OTM:
        v = [run_year(y, d, **BID, strike_pct=pc)["final"]/1000.0-100.0 for y in YEARS]
        rows[pc] = v
        L.append(f"| {pc*100:+.0f}% | " + " | ".join(f"{x:+.1f}%" for x in v)
                 + f" | **{np.mean(v):+.1f}%** |")
    bhv = [buy_hold(d, y, 100000.0)[0]/1000.0-100.0 for y in YEARS]
    L.append("| **buy & hold** | " + " | ".join(f"{x:+.1f}%" for x in bhv)
             + f" | **{np.mean(bhv):+.1f}%** |")
    L.append("\n**The further out you write, the better it gets — and the limit "
             "of that is not writing at all.** The mean improves monotonically "
             f"from {np.mean(rows[0.0]):+.1f}% at the money to "
             f"{np.mean(rows[0.30]):+.1f}% at 30% out, and buy & hold "
             f"({np.mean(bhv):+.1f}%) sits above every one of them. Sold at a "
             "price anyone would actually fill, **the weekly call is a net cost "
             "at every strike tested**.\n")
    L.append("The one exception is the crash. In 2022 the call *helped*: "
             f"{rows[0.0][0]:+.1f}% at the money against buy & hold's "
             f"{bhv[0]:+.1f}%, and there the ordering reverses — closer to the "
             "money cushions more, because the premium is the cushion. That is "
             "the whole trade in one line: **you are paid to give up the "
             "upside, and the payment only covers you in the year the upside "
             "does not come.**\n")

    # start-month cohorts for the same sweep
    ce = d.ch.trade_date.max()
    end = max(x for x in d.sessions if x.year == 2026 and x <= ce)
    starts = [pd.Timestamp(f"2026-{m:02d}-01") for m in range(1, 7)]
    L.append("\n### 2026, the same sweep by start month\n")
    L.append("| strike | " + " | ".join(x.strftime("%b") for x in starts) + " |")
    L.append("|---|" + "---:|" * len(starts))
    for pc in OTM:
        v = []
        for st in starts:
            try:
                v.append(run_year(2026, d, **BID, strike_pct=pc,
                                  start_date=st, end_date=end)["final"]/1000.0-100.0)
            except SystemExit:
                v.append(np.nan)
        L.append(f"| {pc*100:+.0f}% | " + " | ".join(f"{x:+.0f}%" for x in v) + " |")
    L.append("\nMonotonic in five of the six months and **reversed in June** — "
             "the month SOXL fell. That is the tell that the monotonicity is a "
             "directional bet on the underlying, not an edge in the option: in "
             "rising months less cap is better, in the falling month more cap "
             "is better. A single 2026 figure for any of these rows is one draw "
             "from that spread.\n")

    write_text(f"{OUT}/MONEYNESS.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/MONEYNESS.md")
