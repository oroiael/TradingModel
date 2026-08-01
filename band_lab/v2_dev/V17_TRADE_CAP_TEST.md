# V17 — The trade cap (V7), tested at the margin

**Line:** v2.0-dev (DEVELOPMENT). Nothing here changes v1.0 production.

**Status: PROPOSED — awaiting sign-off. Not yet run.**
The adoption bar in §6 is fixed at sign-off and is not edited after results.

---

## 1. Why V7, and why it is the only survivor of V16

V16 tested V1 × V3 × V7 jointly and adopted nothing. V7 was the only one of
the three that failed *narrowly* rather than structurally:

| | V16 outcome |
|---|---|
| **V1** dip depth | **Structural failure.** SOXL wants it shallower, SOXS is already at its own optimum. The sleeves disagree in *direction* — no single value can be right for both. Closed. |
| **V3** profit target | **Structural failure.** Every tighter target that earns more raises same-bar reliance; every looser one that lowers reliance earns less. The trade-off is monotonic and runs straight through the mechanism test. Closed. |
| **V7** trade cap | **Narrow failure.** +7.6 to +12.5 bp/ON-day, monotonic on SOXL, and the *same direction in both sleeves* — the only lever with that property. Failed B6 by 1–4 points of same-bar share on SOXL, and B5 by 0.3–4 points of drawdown on SOXS. |

V7 is also structurally different from V1 and V3, which is the real argument
for one more look: **the cap does not move any price.** V1 and V3 change
*where* the strategy buys and sells, so raising their churn rate manufactures
new re-entries at new levels. The cap changes only *whether trade number 6 is
allowed to happen at all*. It is a truncation rule, not a level rule.

That makes the question answerable in a much sharper form than a grid sweep
can express: **is the Nth trade of the day worth taking?** V17 asks that
directly.

## 2. Scoping — measured, and it reframes the test

Run uncapped (cap 20) on the 1-minute data, 2022+:

| | SOXL | SOXS |
|---|---:|---:|
| mean fills/day, uncapped | 3.84 | 4.19 |
| median | 3 | 3 |
| **days where cap 5 binds** | **136 of 679 (20.0%)** | **178 of 691 (25.8%)** |
| trades suppressed by cap 5 | 450 (17.3%) | 603 (20.8%) |
| days where cap 8 binds | 43 (6.3%) | 57 (8.2%) |
| days where cap 10 binds | 24 (3.5%) | 33 (4.8%) |

**This is the single most important fact for the test design.** The cap is
irrelevant on 80% of days. V16's headline "+7.6 bp/ON-day" is therefore not a
broad improvement — it is roughly **+38 bp concentrated on the 20% of days
where the cap binds**, averaged across all days.

And those are not random days. A day where the strategy wants 6+ round trips
is by definition a high-oscillation day — which is exactly where same-bar
re-entry is most frequent and where the residual 1-minute fill uncertainty is
largest. **The V7 gain is concentrated in the days we trust least.** That is a
testable claim, and T2 tests it.

## 3. What we test

### T1 — Marginal trade profile (the core diagnostic)

Run uncapped. For each trade ordinal *n* = 1…12 within a session, measure, at
both 5-minute and 1-minute fill resolution:

- number of trades at that ordinal
- mean net return per trade, and win rate
- contribution in bp/ON-day
- **same-bar share of that ordinal's P&L**
- retention (1-min ÷ 5-min) for that ordinal alone

This is the question the cap is actually asking. If ordinals 6–8 look like
ordinals 3–5 — comparable win rate, comparable same-bar share, positive net —
then the cap at 5 is arbitrary truncation and should move. If they degrade,
the cap is doing real work.

### T2 — Are cap-binding days the low-trust days?

For the 136 SOXL / 178 SOXS days where cap 5 binds, versus all other ON days:

- ATR5 and OR30 distribution
- **edge retention (1-min ÷ 5-min) on those days specifically**
- same-bar share on those days

**This is the veto test.** If cap-binding days retain materially less of their
5-minute edge than the average day, then raising the cap loads capital into
the worst-measured part of the sample, and V17 should stop there regardless of
what T1 and T3 say.

### T3 — Cap sweep, with the stop-breaker interaction measured

Cap ∈ {4, 5, 6, 7, 8, 9, 10, 12}, V1/V3 at locked values, both sleeves,
1-minute fills, `target_delay=fill_bar`, net of costs. 16 runs.

Additionally measured at each cap — **not swept, because V11 is locked** — the
2-stop breaker interaction: the share of ON days that terminate on `MAX_STOPS`
rather than on the fill cap or the clock. More permitted trades means more
opportunities to collect a second stop, so a cap raise could deliver its extra
trades disproportionately as losing days. V16 did not measure this.

### T4 — Year-by-year sign consistency (replaces walk-forward selection)

For each candidate cap, does it beat cap 5 in **each** year, in each sleeve?

V16 established that selection-based walk-forward is not protective on this
dataset: the rejected winner passed 5 of 5 held-out years in both sleeves,
because a bias present in every year is identical in every fold. A direct
per-year sign test is weaker in theory but harder to game, and it exposes the
SOXS non-monotonicity that V16's aggregate hid (SOXS: cap 5 = 30.3,
6 = 38.0, 8 = 35.8, 10 = 41.4 — not monotonic, which is a noise signature).

## 4. Grid

| axis | values | note |
|---|---|---|
| V7 `max_fills` | 4, 5, 6, 7, 8, 9, 10, 12 | 5 = incumbent; 4 included so the incumbent is interior |
| V1 `dip_pct` | 1.00% (locked) | not under test — closed by V16 |
| V3 `target_pct` | 1.00% (locked) | not under test — closed by V16 |
| V4 `stop_pct` | 4.00% (locked) | not under test |
| V11 `max_stops` | 2 (locked) | measured, not swept |

16 runs for T3, 2 uncapped runs for T1/T2. Small by design: **one variable,
eight values.** V16's 672-cell search is what produced a corner solution that
passed walk-forward and was still wrong.

## 5. What is NOT being tested

No re-sweep of V1 or V3 — both closed by V16, and re-running them on the same
679/691 days would be fitting to data we have already seen. No change to the
decision clock, the gate, the filter, the stop, or the sizing rule.

## 6. Adoption bar — PRESPECIFIED, fixed at sign-off

A cap is adopted only if it clears **all six**:

| # | criterion |
|---|---|
| **C1** | **Marginal ordinals stand alone.** Every ordinal from 6 through the proposed cap has a positive mean net return at 1-minute resolution, in both sleeves. A cap that is profitable only in aggregate is rejected. |
| **C2** | **Mechanism at the margin.** Same-bar share of P&L for ordinals 6…cap must not exceed that of ordinals 1–5 by more than **5 percentage points**, in both sleeves. This is V16's B6 sharpened: the aggregate version diluted the marginal trades against the first five. |
| **C3** | **Low-trust concentration (the veto).** Edge retention (1-min ÷ 5-min) on cap-binding days must be at least **0.80×** the retention on non-binding days, in both sleeves. If the extra trades live where the measurement is worst, no other result matters. |
| **C4** | **Risk.** MaxDD must not worsen by more than **2 percentage points** vs cap 5, in either sleeve. (This is what failed SOXS at caps 6, 8 and 10 in V16 — the bar is unchanged, deliberately.) |
| **C5** | **Stop-breaker.** Share of ON days terminating on the 2-stop breaker must not rise by more than **3 percentage points** vs cap 5. |
| **C6** | **Consistency and plateau.** Beats cap 5 on net bp/ON-day in **≥4 of 5 years in both sleeves**, and the adopted value is interior to {4…12} with both neighbours within 90% of it. |

**Sleeve-specific caps are permitted in V17**, unlike V16's B3 — but only if
each sleeve independently clears C1–C6, and the deviation is recorded as two
values of one parameter, not two strategies. V16 showed the sleeves genuinely
differ; pretending otherwise cost us the V1 result.

**If nothing clears the bar, V7 closes for this dataset** and is not revisited
until sub-minute fills or live fills exist. This is a stopping rule, not a
pause: we have now looked at these 679/691 days repeatedly, and each
additional pass raises the chance of fitting them.

## 7. Projection — what I expect, and on what basis

Stated before the run so it can be judged against the outcome.

**Measured inputs from V16** (net bp/ON-day, 1-min, others locked):

| cap | SOXL | SOXL same-bar | SOXL MaxDD | SOXS | SOXS same-bar | SOXS MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| 5 | 39.3 | 66% | −40.6% | 30.3 | 102% | −36.5% |
| 6 | 47.0 | 70% | −40.1% | 38.0 | 103% | −38.8% |
| 8 | 49.3 | 67% | −40.7% | 35.8 | 98% | −42.6% |
| 10 | 51.8 | 68% | −41.3% | 41.4 | 92% | −42.6% |

**Most likely outcome — NOT ADOPTED, or SOXL-only (my estimate: ~55%).**
SOXS already fails C4 at every raised cap tested (−38.8% at cap 6 against a
−38.5% floor; −42.6% at 8 and 10). Nothing in T1–T4 changes a drawdown that is
already measured. So SOXS almost certainly stays at 5. SOXL's risk is fine
(−40.1% to −41.3%, all within tolerance) and its fate rests entirely on C2 and
C3, both of which are genuinely unknown until T1 and T2 run.

**Second — SOXL cap moves to 6 or 7 (~30%).** If ordinals 6–7 have same-bar
shares near SOXL's 66% baseline and cap-binding days retain normally, SOXL
clears. Value: **+7.6 bp/ON-day on SOXL (39.3 → 47.0, +19%)**, roughly
**+4 bp/day on the 50/50 pair**. On the pair's current 66.2% CAGR that is an
estimated **low-70s% CAGR** — an estimate from the bp figures, not a run
result, and it would need the actual run to state properly.

**Third — hard close (~15%).** T1 shows ordinals 6+ are predominantly same-bar
re-entries, or T2 shows cap-binding days retain far worse than average. Either
kills V7 cleanly and permanently for this dataset. **This is the most useful
outcome of the three**, because it converts a recurring open question into a
closed one.

**What I do not expect:** a large adopted gain in both sleeves. Nothing in the
V16 data supports it, and SOXS's non-monotonic cap response (30.3 → 38.0 →
35.8 → 41.4) reads as noise rather than signal.

**Honest summary of the odds:** the most probable result is that we spend the
run confirming the cap stays at 5, with a modest chance of a SOXL-only
increase worth about a fifth of that sleeve's edge. That is still worth doing
— it is cheap, it is bounded, and a documented close is worth more than an
open question — but it is not a large expected gain, and it should not be
allowed to delay the paper run.

---
---

# RESULTS

*(appended after the run; the bar in §6 was not edited)*

## VERDICT: **NOT ADOPTED in either sleeve. V7 stays at 5.**

Per §6's stopping rule, V7 closes for this dataset until sub-minute or live
fills exist. But two things must be reported alongside that verdict: **one of
my criteria was badly specified**, and the test surfaced a finding much larger
than the cap question.

---

## R1. C3 was mis-specified. Disclosed, not quietly fixed.

C3 read: *"retention on cap-binding days must be at least 0.80× the retention
on non-binding days."* Retention is a ratio of 1-minute to 5-minute edge. On
non-binding days the 5-minute edge is **approximately zero**, so that
denominator is unstable and the resulting ratio is meaningless:

| | days | 5-min bp | 1-min bp | "retention" |
|---|---:|---:|---:|---:|
| SOXL binding | 136 | 445.1 | 349.9 | 79% |
| SOXL non-binding | 543 | **−0.4** | −16.9 | **4257%** ← degenerate |
| SOXS binding | 178 | 436.5 | 361.6 | 83% |
| SOXS non-binding | 513 | −26.3 | −52.2 | 199% |

C3 mechanically returns FAIL (ratios 0.02 and 0.42). **Those numbers carry no
information.** The criterion divides by a quantity that is ~0 by construction.

**The substantive question C3 was asking does have a clean answer, and it is
the opposite of the hypothesis §2 proposed.** Cap-binding days retain **79%
(SOXL) and 83% (SOXS)** of their 5-minute edge, against **64% and 54%** for
the sample as a whole. Binding days are the **best**-measured days in the
sample, not the worst. The concern in §2 — that raising the cap loads capital
into badly-measured territory — is **not supported**. I was wrong about that.

**I am not rewriting C3 to flip the verdict.** Retroactively repairing a
criterion after seeing that it blocks an otherwise-passing candidate is
precisely the failure this whole process exists to prevent, and it would be
indefensible for me to enforce that discipline on the data and exempt myself.
The verdict stands as NOT ADOPTED. What follows is the consequence.

## R2. SOXL caps 8 and 9 pass every other criterion

| cap | C1 | C2 | C3 | C4 | C5 | C6 | net bp |
|---|---|---|---|---|---|---|---:|
| 6 | ok | **FAIL** (88% vs 67%) | degen | ok | ok | **FAIL** (3/5) | 47.0 |
| 7 | ok | **FAIL** (86%) | degen | ok | ok | ok (4/5) | 47.8 |
| **8** | **ok** | **ok** (70% vs 67%) | degen | **ok** (−40.7%) | **ok** (+2.2p) | **ok** (4/5) | **49.3** |
| **9** | **ok** | **ok** (70%) | degen | **ok** (−41.3%) | **ok** (+2.2p) | **ok** (4/5) | **50.4** |
| 10 | ok | **FAIL** (72%) | degen | ok | ok | ok (4/5) | 51.8 |
| 12 | **FAIL** | **FAIL** (94%) | degen | ok | **FAIL** (+3.1p) | **FAIL** (boundary) | 51.3 |

SOXL cap 8 or 9 is blocked **only** by the degenerate criterion. That is a
live, unresolved question worth **+10.0 to +11.1 bp/ON-day on SOXL** (39.3 →
49.3/50.4, +25–28%).

It should be settled by a **new prespecified program (V18)** with a
properly-formed criterion, not by amending this one. V18 must also account for
the fact that we have now examined these 679 days repeatedly across V16 and
V17; the multiple-comparison cost is real and rising, and it argues for
settling this with live fills rather than a fourth pass over the same sample.

## R3. SOXS is cleanly and independently rejected

C4 (drawdown) fails at **every** raised cap: −38.8% at cap 6 against a −38.5%
floor, and −42.6% at caps 7 through 12 against an incumbent −36.5%. This is
independent of C3 and of any specification issue. C1 also fails from cap 7
upward — ordinals 7 and 8 have **negative** mean net returns (−6.5 and −7.7 bp).

**SOXS stays at 5.** This matches the §7 projection exactly.

## R4. T1 — the marginal trade profile

| ordinal | SOXL trades | SOXL mean net bp | SOXL win rate | SOXS trades | SOXS mean net bp | SOXS win rate |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 678 | 11.6 | 77.7% | 691 | **−5.2** | 72.8% |
| 2 | 580 | 14.4 | 74.3% | 581 | 7.6 | 73.1% |
| 3 | 416 | 13.5 | 74.0% | 442 | 16.1 | 74.7% |
| 4 | 287 | 10.4 | 72.8% | 330 | 25.3 | 76.7% |
| 5 | 196 | 9.4 | 73.5% | 246 | 19.1 | 75.2% |
| **6** | 136 | **38.1** | 80.1% | 178 | **30.1** | 78.7% |
| **7** | 100 | 5.5 | 73.0% | 139 | **−6.5** | 64.7% |
| **8** | 66 | 15.6 | 77.3% | 86 | **−7.7** | 66.3% |
| **9** | 43 | 17.7 | 69.8% | 57 | 24.9 | 78.9% |
| **10** | 30 | 31.4 | 76.7% | 42 | 58.4 | 85.7% |
| 11 | 24 | **−15.4** | 66.7% | 33 | **−15.7** | 66.7% |
| 12 | 16 | −0.9 | 81.2% | 20 | 43.3 | 70.0% |

Marginal trades are **not** systematically worse than the first five — on SOXL
the 6th trade is the best of any ordinal (38.1 bp, 80.1% win rate). But the
sample thins fast (136 → 16 trades) and the sign alternates from ordinal 7
onward in both sleeves, which reads as noise rather than structure. That
instability is the honest reason not to push the cap on this evidence, and it
is a better reason than C3 gave.

*The per-ordinal `retention` column in the raw output is unstable for the same
reason as C3 — near-zero denominators — and should not be read literally.*

## R5. The finding that matters more than V7

Investigating T2's arithmetic (it reconciles exactly: 136 × 349.9 + 543 ×
−16.9, over 679 days, = the 56.6 bp overall) surfaced this. **At the
production config — cap 5, 1-minute fills, net of costs:**

| SOXL | days | % of ON days | net bp/day | share of total P&L |
|---|---:|---:|---:|---:|
| 0–2 fills | 263 | 38.7% | **−69.8** | −69% |
| 3–4 fills | 220 | 32.4% | +15.5 | +13% |
| **5 fills (capped)** | **196** | **28.9%** | **+212.6** | **+156%** |

| SOXS | days | % of ON days | net bp/day | share of total P&L |
|---|---:|---:|---:|---:|
| 0–2 fills | 249 | 36.0% | **−147.5** | −175% |
| 3–4 fills | 196 | 28.4% | −19.6 | −18% |
| **5 fills (capped)** | **246** | **35.6%** | **+250.0** | **+294%** |

**The strategy's entire edge comes from the ~30% of ON days that reach the
trade cap. The other ~70% lose money** — −31.0 bp/day on SOXL and −91.2 on
SOXS.

The mechanism is the +1% / −4% asymmetry (V3 vs V4). A day that opens a
position and stops out books −4% with no churn to offset it; a day that cycles
five times books roughly +5%. Low-fill days are, by construction, the days
where the first trade went against the position.

This is not a fill-model artifact — it is a property of the locked strategy,
visible at both resolutions. It has three consequences worth raising:

1. **The "ON-day rate 52%" framing understates the concentration.** The
   strategy is effectively active — in P&L terms — on about 15% of all
   sessions (30% of the 52% that are ON).
2. **It reframes the day filter (V9) and vol gate (V10).** Those variables
   decide which days to trade, and the payoff to selecting well is far larger
   than the payoff to any churn parameter. That is where the remaining
   research value is, and it is Tier 2 in the earlier prioritisation.
3. **It is a live risk-management fact**, not a research curiosity: capital
   is exposed on ~70% of ON days for a negative expected contribution, to earn
   the right to be positioned on the other 30%.

## R6. Projection scorecard (§7, written before the run)

| projected | outcome |
|---|---|
| "NOT ADOPTED, or SOXL-only (~55%)" | **NOT ADOPTED** ✓ |
| "SOXS almost certainly stays at 5 — nothing changes an already-measured drawdown" | **Correct.** C4 failed at every cap, independently ✓ |
| "SOXL rests entirely on C2 and C3" | **Correct** — C2 passes at 8/9, C3 turned out degenerate ✓ |
| "Hard close (~15%), the most useful outcome" | Partially — closed on the specified bar, but SOXL 8/9 is a live near-miss, not a clean close ✗ |
| "cap-binding days are the days we trust least" (§2 hypothesis) | **Wrong.** They retain 79%/83% vs 64%/54% overall ✗ |

## R7. Recommendation

1. **Adopt nothing from V17.** V7 stays at 5 in both sleeves.
2. **SOXS: close V7 permanently.** The drawdown failure is robust and
   independent of the specification flaw.
3. **SOXL cap 8–9 is unresolved, not rejected.** Settle it with live fills, or
   with a fresh V18 carrying a correctly-formed criterion and an explicit
   multiple-comparison discount. Do not amend V17.
4. **Redirect research to day selection (V9/V10), not churn parameters.** R5
   shows the concentration of edge across days dwarfs anything the churn
   parameters can deliver.
5. The priority note in §8 stands, and R5 strengthens it.

---

## 8. Priority note

V17 is **not** the highest-value next action. `PHASE2_PARITY.md` S11's residual
— how much of the remaining edge survives sub-minute sequencing — is what gates
every number in this project, and only real fills settle it. V17 is worth doing
in parallel with the paper run, not instead of it, and its C2/C3 criteria are
precisely the questions live fills would answer directly.
