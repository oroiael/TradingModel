# V8 Test Program — Direction & Concurrency for the Churn Harvester Core

Current value: **long only, one position at a time.** Never tested — the
short side is unexplored (not rejected), and single-position is an
assumption inherited from the first prototype. Context for what a short
sleeve is up against: the long edge on gated days is +44.9 bp/day
(breaker-2 core), SOXL has structural upward drift long-term but its
*downside* churn is real — steep drops cluster in the same high-vol bursts
the gate selects for.

Discipline (same as V11): every parameter below is fixed by this document
before anything runs. The short side inherits the long side's locked
parameters mirrored — no fresh tuning cycle on the short side, because
that would restart the data-snooping clock on half the sample.

---

## T1. Mirror-image short (diagnostic — run first)

**Mechanic.** Exact reflection of the locked core on the same SOXL bars:
from 10:30, sell short 1% **above** the intraday rolling **low**; cover at
−1% (price falls to target); stop at +4%; 5 trades or 2 buy-in stop-outs;
flat at close; same orq5 filter and ATR5 ≥ 6 gate. Ignores borrow cost and
SSR entirely — this is a *diagnostic* for whether downside churn edge
exists at all, not a tradable spec. Also produce the by-year table and the
edge-by-trade-number curve (does the deeper-rally escalation mirror the
long side's?).

**Data now:** fully sufficient (same 5-min bars, same harness — the sim
is the long sim with signs flipped).
**Better with:** nothing at this depth.
**Depth:** shallow — hours.
**Max upside:** if reversion is symmetric, a second ~20–40 bp/day stream.
**Max downside:** none — it's a measurement. Most likely finding, honestly:
materially weaker than the long side, because the gated-day tape has
positive drift (the long side's +44.9 bp is part reversion, part drift,
and the short side pays the drift instead of earning it).

## T2. SOXS-long as the tradable short (the implementation vehicle)

**Mechanic.** Same signals as T1 (generated on SOXL bars), executed by
**buying SOXS** (−3x inverse, 5-min data already in the repo): when the
T1 sim says "short SOXL here," buy SOXS at its concurrent bar price; exit
on the SOXL-side target/stop signals; flat at close. No borrow, no SSR,
PDT-friendly. The T2-minus-T1 gap *measures the implementation drag*
(SOXS tracking slippage, wider spread, intraday decay) — that number is
the real cost of expressing shorts via the inverse ETF.

**Data now:** sufficient — `SOXS_5min_6Years.csv` (2020-07-23 onward,
back-adjusted, verified clean); needs bar-level timestamp alignment
between the two files (both IBKR 5-min RTH, so alignment should be
near-perfect; days present in one and not the other get dropped).
**Better with:** SOXS quote/spread history (its spread is wider than
SOXL's — a per-side bp estimate materially changes thin edges).
**Depth:** medium — a day including the alignment plumbing.
**Max upside:** turns any T1 edge into something actually tradable.
**Max downside:** the drag measurement itself; if T1 shows +20 bp and T2
shows +5 bp, the short side dies on implementation, which is a legitimate
and useful verdict.

## T3. Two-sided operation (concurrency across directions)

**Mechanic.** Run the locked long core and the T2 short sleeve
simultaneously on the same days, two variants:
  a. **independent** — each side trades its own signals, can be on at the
     same time (momentarily ~market-neutral when both are on);
  b. **one-at-a-time** — a side can only enter when the other is flat
     (capital-cheaper, path-dependent).
Report the correlation of the two daily P&L streams, combined Sharpe at
50/50 capital, and the capital peak (both-on days need 2× capital in
variant a).

**Data now:** sufficient (products of T1/T2).
**Depth:** shallow once T2 exists — it's portfolio arithmetic plus one
concurrency rule in the sim.
**Max upside:** if the streams are near-zero or negatively correlated, a
50/50 book could push combined Sharpe from 2.25 toward 3 — the single
biggest prize available in this program. **Max downside:** doubled trade
count and costs for a correlation that turns out strongly positive
(both sides harvesting the same swings), in which case two-sided adds
nothing — again a cheap, decisive verdict.

## T4. Pyramiding (concurrency within the long side)

**Mechanic.** Allow a second unit while a position is open: add at 1%
below the first entry (i.e., a 2% total dip — the V11 escalation finding
says deeper dips carry MORE edge: trade #3+ earns ~20 bp vs #1's 6.8 bp).
Prespecified variants, nothing else:
  a. add-at-1%-deeper, each unit f/2, shared exits (both exit at first
     unit's target/stop levels);
  b. same but per-unit targets (+1% from each unit's own entry);
  c. max depth 2 units only, breaker counts unit-stops.
Compare against the locked core at equal total capital (f/2 per unit vs
f single) so the test isolates *structure*, not size.

**Data now:** sufficient.
**Better with:** 1-min bars — two units mean more intra-bar sequencing
ambiguity (first unit's stop vs second unit's fill inside one 5-min bar).
**Depth:** medium-deep — real sim-logic surgery plus breaker interaction;
half a day.
**Max upside:** captures the deeper-dip escalation systematically; guessed
+5–15% relative bp/day at equal capital with Sharpe roughly flat.
**Max downside:** both units stopping together concentrates the worst
day (mitigated by equal-total-capital design: worst case ≈ current −8%
breaker-2 worst day, not worse, since total exposure is unchanged — the
risk is subtler: more days *near* the worst case).

## T5. Excursion-day momentum mode (direction of a different kind)

**Mechanic.** The orq5 filter currently discards ~150 days per 6 years —
the trend/excursion-signature days. Test a separate prespecified mode on
exactly that cohort: buy a break of OR-high + 0.25×OR (long momentum);
stop at OR mid; hold to close. Down-breaks (below OR-low − 0.25×OR) via
SOXS-long, same shape, only if T2 shows the vehicle works. No dip-buying
on these days — this is the "plan FOR the breakout" leg from the original
band-lab brief, now scoped to the days the core refuses to trade.

**Data now:** sufficient (the cohort and OR levels come straight from
existing daily stats; round-1 measured ungated breakout rides at
+0.27%/day mean — encouraging but unfiltered).
**Depth:** medium — hours to a half-day.
**Max upside:** converts dead days into a third stream that is *long
volatility expansion* — the natural complement to a mean-reversion book;
even +20 bp/day on 25 days/yr adds ~5% annually at full size.
**Max downside:** late-entry momentum on a 3x ETF has an ugly failure
mode (buy the top of a spike, stopped at OR mid = −2 to −4%); bounded by
the cohort's small day count.

## T6. Short-side reality audit (assumptions, not a backtest)

**Mechanic.** Before any live short-SOXL implementation (if T1/T2 favor
it): (a) compute SSR frequency from existing data — days where SOXL
trades ≤ 90% of prior close trigger the uptick rule for that day + the
next; count what fraction of *gated* days are SSR-bound (guess: a large
minority — the gate selects crashy weeks); (b) bound borrow-fee drag
using a 1–10% annualized hard-to-borrow range prorated intraday;
(c) confirm the SOXS route (T2) sidesteps both, which is why T2 — not
actual shorting — is the recommended vehicle.

**Data now:** (a) fully computable; (b) needs external historical borrow
data (IBKR sec-lending history) — without it, use the bounding range;
(c) free.
**Depth:** shallow — hours.
**Up/downside:** none directly; it prevents adopting a short sleeve that
backtests well but can't be executed on the worst (best) days.

---

## Program summary

| test | depth | data now | decisive question | best case | worst case |
|---|---|---|---|---|---|
| T1 mirror short | hours | ✅ | does downside churn edge exist? | 2nd 20–40 bp stream | edge ≈ 0, program narrows to T4/T5 |
| T2 SOXS vehicle | ~1 day | ✅ (spread data better) | does it survive implementation? | tradable short sleeve | drag eats it — clean kill |
| T3 two-sided | hours after T2 | ✅ | stream correlation? | combined Sharpe → ~3 | correlated, adds nothing |
| T4 pyramiding | half-day | ✅ (1-min better) | is deeper-dip escalation capturable? | +5–15% rel. return, flat risk | more near-worst days |
| T5 excursion momentum | half-day | ✅ | do skipped days pay as momentum? | 3rd stream, long-vol complement | small cohort, noisy verdict |
| T6 short reality audit | hours | ⚠️ borrow data external | is shorting executable at all? | validates T2 route | — |

**Recommended order: T1 → T2 → T6 → T3 → T4 → T5.** T1 is the gating
diagnostic — if the mirror edge is ≈ 0, T2/T3/T6 collapse and the program
shrinks to T4 + T5. Decision gate (same as V11): nothing is adopted unless
it beats the locked core (or measurably improves the combined book) OOS in
the by-year table, net of the still-pending cost model — and the short
side must additionally clear the T6 executability audit.

**Aggregate bounds:** best case — a second (and third) income stream at low
correlation lifts combined Sharpe from 2.25 toward ~3 and adds 10–20%
relative return at equal risk. Worst case — the short side has no edge
after drift and drag (the likeliest single outcome), pyramiding and
momentum come back marginal, and the program's value is four clean
negative verdicts that permanently close the V8 question for the cost of
~two days of work. Like V11, nothing here can damage the existing core —
every test is additive-or-reject.
