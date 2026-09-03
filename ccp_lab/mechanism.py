#!/usr/bin/env python3
"""Why the rule loses — the two mechanisms, measured. Writes out/MECHANISM.md."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.engine import Data, run_year
from ccp_lab.report import OUT

YEARS = [2022, 2023, 2024, 2025, 2026]

if __name__ == "__main__":
    d = Data()
    calls, puts, whip = [], [], []
    for y in YEARS:
        r = run_year(y, d)
        lg, ev = r["ledger"], r["events"]
        w = lg.dropna(subset=["call_strike"])
        assigned = ev[ev.kind == "CALL_ASSIGNED"]
        intrinsic = float((assigned.qty * (assigned.spot - assigned.strike)).sum()) \
            if len(assigned) else 0.0
        calls.append(dict(year=y, premium=float(w.call_premium.sum()),
                          intrinsic=intrinsic, net=r["pnl"]["calls"],
                          n_assigned=len(assigned), n_writes=len(w),
                          med_prem_pct=float(w.prem_pct.median()),
                          med_otm=float(w.otm_pct.median())))
        bp = ev[ev.kind == "BUY_PUT"]
        paid = float((bp.qty * 100 * bp.px).sum()) if len(bp) else 0.0
        puts.append(dict(year=y, paid=paid, net=r["pnl"]["puts"],
                         n=len(bp),
                         med_cost_pct=float((bp.px / bp.spot * 100).median()) if len(bp) else np.nan,
                         med_dte=float(bp.dte.median()) if len(bp) else np.nan))
        # whipsaw: called away at K, what did the next repurchase cost?
        buys = ev[ev.kind == "BUY_SHARES"].sort_values("date")
        for _, a in assigned.iterrows():
            nxt = buys[buys.date > a.date]
            if len(nxt):
                whip.append(dict(year=y, out=a.strike, back=float(nxt.iloc[0].spot),
                                 gap=(float(nxt.iloc[0].spot) / a.strike - 1) * 100))
    C, P, W = pd.DataFrame(calls), pd.DataFrame(puts), pd.DataFrame(whip)

    L = ["# Why the rule loses — the mechanisms, measured\n"]
    L.append("\n## 1. The short call: premium collected vs intrinsic surrendered\n")
    L.append("| year | writes | premium collected | assigned | intrinsic paid on assignment | net call P&L |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for _, r in C.iterrows():
        L.append(f"| {int(r.year)} | {int(r.n_writes)} | ${r.premium:,.0f} | "
                 f"{int(r.n_assigned)} | ${r.intrinsic:,.0f} | ${r.net:+,.0f} |")
    L.append(f"| **all** | {int(C.n_writes.sum())} | **${C.premium.sum():,.0f}** | "
             f"{int(C.n_assigned.sum())} | **${C.intrinsic.sum():,.0f}** | "
             f"**${C.net.sum():+,.0f}** |")
    L.append("\nThe premium is enormous — and it is not enough. Writing at or barely "
             "above the money means roughly half of all weeks finish in the money, "
             "and the weeks that do finish far in the money.\n")

    L.append("\n## 2. The protective put: what the insurance costs\n")
    L.append("| year | puts bought | premium paid | median cost, % of spot | median DTE | net put P&L |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for _, r in P.iterrows():
        L.append(f"| {int(r.year)} | {int(r.n)} | ${r.paid:,.0f} | "
                 f"{r.med_cost_pct:.1f}% | {r.med_dte:.0f} | ${r.net:+,.0f} |")
    L.append(f"| **all** | {int(P.n.sum())} | **${P.paid.sum():,.0f}** | "
             f"{P.med_cost_pct.median():.1f}% | {P.med_dte.median():.0f} | "
             f"**${P.net.sum():+,.0f}** |")
    L.append(f"\nA just-out-of-the-money put on a 3× semiconductor ETF costs a median "
             f"**{P.med_cost_pct.median():.1f}% of spot per ~{P.med_dte.median():.0f} "
             f"days**. Reloaded roughly four times a year, that is on the order of "
             f"**50-60% of the position's value per year** in insurance premium alone.\n")

    L.append("\n## 3. The whipsaw: called away low, bought back high\n")
    if len(W):
        L.append(f"- {len(W)} assignments were followed by a repurchase.")
        L.append(f"- The shares went back on at a **median {W.gap.median():+.1f}%** "
                 f"above the strike they were called away at.")
        L.append(f"- The repurchase was higher than the strike in "
                 f"**{(W.gap > 0).mean()*100:.0f}%** of cases.")
        L.append("\n| year | assignments repurchased | median repurchase vs strike |")
        L.append("|---|---:|---:|")
        for y, g in W.groupby("year"):
            L.append(f"| {int(y)} | {len(g)} | {g.gap.median():+.1f}% |")
    L.append("\nSelling at a fixed strike on Friday and rebuying at the market on "
             "Monday is a sell-low/buy-high rule by construction whenever the stock "
             "is trending up.\n")

    L.append("\n## 4. Was the 5% premium ever actually collected?\n")
    L.append("| year | median premium, % of underlying | median strike vs spot |")
    L.append("|---|---:|---:|")
    for _, r in C.iterrows():
        L.append(f"| {int(r.year)} | {r.med_prem_pct:.2f}% | {r.med_otm:+.2f}% |")
    L.append("\nThe rule asks for 5%. Outside the highest-volatility stretches the "
             "market does not offer it at any strike at or above spot, so the engine "
             "writes the closest it can find — which is essentially at the money, and "
             "that is what drives the assignment rate.\n")

    L.append("\n## 5. Why a live trader may report something very different\n")
    L.append("Nothing here says the traders are wrong. It says the rule *as written* "
             "is not the rule they are running. The measured gaps, in order of size:\n")
    L.append("**a. They roll; this rule does not.** The rule holds the call to expiry "
             "and takes assignment. That happened "
             f"{int(C.n_assigned.sum())} times in five years and cost "
             f"${C.intrinsic.sum():,.0f} in intrinsic. A trader who rolls a "
             "threatened call up and out never books that, never sells the shares, "
             "and never pays the repurchase gap measured in section 3 "
             f"(median +{W.gap.median():.1f}%). Rolling is a different strategy with "
             "a different risk profile — it converts a capped position into a "
             "deferred loss — but it will not show these numbers.")
    L.append("\n**b. 5% is a target, not an outcome.** The market offered a 5% "
             "premium at or above spot on a minority of days in four of the five "
             "years. A trader who writes 'about 5%' when volatility allows and "
             "less otherwise is running a variable-distance rule, not this one.")
    L.append("\n**c. The put may not be reloaded at the money.** Reloading a "
             f"just-OTM 90-day put costs a median {P.med_cost_pct.median():.1f}% of "
             "spot each time. Traders often carry a much further out-of-the-money "
             "put, a put spread, or no standing hedge at all. `out/CONTROLS.md` "
             "shows removing the put alone turns 2023 from −17% to +63%.")
    L.append("\n**d. Short windows flatter this structure.** Any stretch in which "
             "the stock drifts sideways to slightly up pays the premium without "
             "triggering assignment. Judged quarter by quarter this rule has good "
             "quarters. It is the full-year path — the assignments and the four put "
             "reloads — that produces the numbers above.")
    L.append("\n**e. Prior backtests in this repo disagreed with each other.** "
             "`A2_Backtest_CCLDP_Strat_v1.py` read '5%' as a strike 5% above spot "
             "and multiplies premium by 100× the share count "
             "(`exec_price * 100 * portfolio['shares']`, line 121). `cc_lp_lab` used "
             "'2 strikes out, sticky'. Neither is the 5%-premium rule. The two QA "
             "reports at the repo root document double-counted premium, missing "
             "roll costs and clamped losses in the older engines. Inconsistent "
             "answers came from inconsistent questions.")

    open(f"{OUT}/MECHANISM.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L))
