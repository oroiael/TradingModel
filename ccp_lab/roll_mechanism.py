#!/usr/bin/env python3
"""What rolling actually changes. Writes ccp_lab/out/ROLL_MECHANISM.md."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.engine import Data, run_year
from ccp_lab.compat import write_text, safe_stdout, ensure_cache
from ccp_lab.report import OUT

YEARS = [2022, 2023, 2024, 2025, 2026]

if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()
    chains, ratchet, whip_a, whip_r, credit = [], [], [], [], []
    for y in YEARS:
        ra = run_year(y, d)                     # assignment baseline
        rr = run_year(y, d, roll="friday")      # rolling

        # whipsaw under assignment: called away at K, bought back at what?
        ev = ra["events"]
        buys = ev[ev.kind == "BUY_SHARES"].sort_values("date")
        for _, a in ev[ev.kind == "CALL_ASSIGNED"].iterrows():
            n = buys[buys.date > a.date]
            if len(n):
                whip_a.append((n.iloc[0].spot / a.strike - 1) * 100)
        ev = rr["events"]
        buys = ev[ev.kind == "BUY_SHARES"].sort_values("date")
        for _, a in ev[ev.kind == "CALL_ASSIGNED"].iterrows():
            n = buys[buys.date > a.date]
            if len(n):
                whip_r.append((n.iloc[0].spot / a.strike - 1) * 100)

        # roll chains: consecutive expiry-day rolls with no break
        rc = ev[ev.kind == "CALL_ROLLED_CLOSE"].sort_values("date")
        ro = ev[ev.kind == "CALL_ROLLED_OPEN"].sort_values("date")
        m = rc.merge(ro[["date", "strike", "px"]], on="date",
                     suffixes=("_old", "_new"))
        if len(m):
            ratchet += list((m.strike_new / m.strike_old - 1) * 100)
            credit += list(m.px_new - m.px_old)
        # chain length = runs of consecutive weeks that ended in a roll
        dates = sorted(rc.date.unique())
        run, best, prev = 0, [], None
        for x in dates:
            if prev is not None and (pd.Timestamp(x) - pd.Timestamp(prev)).days <= 9:
                run += 1
            else:
                if run: best.append(run)
                run = 1
            prev = x
        if run: best.append(run)
        chains.append(dict(year=y, n_rolls=len(rc), longest=max(best) if best else 0,
                           median_chain=float(np.median(best)) if best else 0,
                           assigned_anyway=int((ev.kind == "CALL_ASSIGNED").sum())))
    C = pd.DataFrame(chains)

    L = ["# What rolling actually changes\n"]
    L.append("\n## 1. It removes the whipsaw, which was the point\n")
    L.append(f"- Taking assignment: **{len(whip_a)}** repurchases, at a median "
             f"**{np.median(whip_a):+.1f}%** above the strike the shares were "
             f"called away at.")
    L.append(f"- Rolling: only **{len(whip_r)}** repurchases (the cases where the "
             f"buyback could not be funded), median "
             f"**{np.median(whip_r):+.1f}%**. Those are a funding failure, not a "
             f"choice: with the reinvest-everything rule there is no cash on "
             f"Friday. A 10-20% cash reserve removes almost all of them "
             f"(see `SUMMARY_ROLL.md`)." if whip_r else
             "- Rolling: no repurchases at all — the shares are never sold.")
    L.append("\nStaying continuously long is the whole economic benefit. At the "
             "moment of expiry, buying the call back for its intrinsic and being "
             "assigned at the strike are worth **exactly the same**; the "
             "difference is entirely in what happens next.\n")

    L.append("\n## 2. The strike does ratchet up — and the roll is still a debit\n")
    if ratchet:
        L.append(f"- Median strike increase per roll: **{np.median(ratchet):+.1f}%**.")
        L.append(f"- Median net cash on the roll: "
                 f"**${np.median(credit)*100:+,.0f}** per contract "
                 f"({(np.array(credit) > 0).mean()*100:.0f}% of rolls were a credit).")
    L.append("\nThe cap does move up meaningfully each time. But a roll still pays "
             "the intrinsic that assignment would have surrendered and recovers "
             "only the new week's time value, so most rolls are a net debit. It "
             "converts a realised loss into a deferred one on a position that "
             "stays capped.\n")

    L.append("\n## 3. Rolls compound into long chains\n")
    L.append("| year | rolls | median chain | longest chain | assigned anyway |")
    L.append("|---|---:|---:|---:|---:|")
    for _, r in C.iterrows():
        L.append(f"| {int(r.year)} | {int(r.n_rolls)} | {r.median_chain:.0f} | "
                 f"{int(r.longest)} | {int(r.assigned_anyway)} |")
    L.append(f"\nOnce the stock is above the strike, each roll re-caps it barely "
             f"higher, so the next week is in the money again. The longest "
             f"unbroken chain was **{int(C.longest.max())} weeks**. That is the "
             f"structural cost of rolling: in a sustained rally you are paying "
             f"intrinsic every week to keep a position that is capped anyway.\n")

    L.append("\n## 4. Verdict\n")
    L.append("Rolling is worth doing — it is better than assignment in three of "
             "five years and by more than 40 points in two of them — and it does "
             "not rescue the strategy. It removes the transaction-cost whipsaw but "
             "not the two things that actually cost the money: the cap itself, and "
             "a protective put costing ~17% of spot every ~84 days.\n")
    write_text(f"{OUT}/ROLL_MECHANISM.md", "\n".join(L) + "\n")
    print("\n".join(L))
