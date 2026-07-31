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

## 8. Priority note

V17 is **not** the highest-value next action. `PHASE2_PARITY.md` S11's residual
— how much of the remaining edge survives sub-minute sequencing — is what gates
every number in this project, and only real fills settle it. V17 is worth doing
in parallel with the paper run, not instead of it, and its C2/C3 criteria are
precisely the questions live fills would answer directly.
