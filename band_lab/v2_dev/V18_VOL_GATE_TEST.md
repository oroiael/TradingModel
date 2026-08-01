# V18 — The volatility gate (V10): cutoff and lookback

**Line:** v2.0-dev (DEVELOPMENT). Nothing here changes v1.0 production.

**Status: PROPOSED — awaiting sign-off. Not yet run.**
The adoption bar in §7 is fixed at sign-off and is not edited after results.

---

## 1. Why V10, and why now

Two independent results point here.

**From the earlier prioritisation** — edge retention (1-min ÷ 5-min) by ATR5
quartile *within* the currently-gated population, measured, gross:

| ATR5 quartile | SOXL 5-min → 1-min | retained | SOXS 5-min → 1-min | retained |
|---|---|---:|---|---:|
| Q1 (lowest) | 59.5 → 44.5 | 75% | 22.9 → **2.8** | **12%** |
| Q2 | 47.2 → 23.0 | 49% | 51.2 → 17.6 | 34% |
| Q3 | 40.5 → 26.0 | 64% | 58.6 → 32.9 | 56% |
| Q4 (highest) | 119.9 → **76.5** | 64% | 119.5 → **83.7** | 70% |

SOXS is monotone: the lowest-volatility gated days earn **2.8 bp gross**,
which is **negative after SOXS's ~9.6 bp/ON-day costs**. SOXL is *not*
monotone — its Q1 is the second-best band. The sleeves disagree again.

**From V17 R5** — the entire edge comes from the ~30% of ON days that reach
the trade cap; the other ~70% lose money (−31.0 bp/day SOXL, −91.2 SOXS).
Day selection therefore dominates every churn parameter, and V10 is the
day-selection variable that runs on information available at 06:00.

Together: **if ATR5 predicts which days join the profitable cohort, the gate
is the highest-value dial left. If it does not, V10 closes and the answer is
that day quality is not forecastable from volatility.** Either is worth
knowing.

## 2. The metric trap — the single most important design decision here

**`bp/ON-day` is an invalid metric for a gate test.** The gate changes the
denominator: any tightening that removes below-average days raises bp/ON-day
mechanically, whether or not it adds a single dollar. Optimising it would
select the tightest gate on the grid and call it an improvement.

**The primary metric is net bp per *calendar* day** — total P&L over all
sessions in the window, including days the gate stands down (which contribute
exactly 0). That is the number an account actually earns, and it is the only
one that penalises a gate for sitting out profitable days.

Every figure is also reported per ON-day, but per-ON-day may never decide an
adoption. This is criterion D1, stated so the metric cannot be swapped after
seeing results.

## 3. What we test

### T1 — Marginal-day profile (the core diagnostic)

Decile the ON days by ATR5. Per decile, at 1-minute resolution, **net of
costs**: day count, mean net bp/day, share of days reaching the trade cap
(the V17 R5 profitable cohort), and contribution in bp per calendar day.

This is V17's marginal-*trade* analysis asked of marginal *days*. If the
bottom deciles are negative net, a higher cutoff is justified on its face; if
they are positive, no amount of sweep result should override that.

### T2 — Does ATR5 predict the profitable cohort? (the mechanism)

V17 R5 established that days reaching the cap carry all the P&L. T2 asks
whether ATR5, known at 06:00, forecasts membership: within each ATR5 decile,
the fraction of days that reach 5 fills, and the net bp/day of that cohort
versus the rest.

**This is what decides whether V10 is a real lever or a coincidence.** A gate
that improves returns without shifting cohort membership is fitting noise.

### T3 — Cutoff × lookback sweep

Tested jointly, on the V16 argument: a longer lookback smooths ATR5, so a
given cutoff means something different at each lookback. Sweeping the cutoff
at a fixed 5-day lookback would condition on a lookback chosen under the same
inflated P&L.

### T4 — Per-year sign test

Not selection-based walk-forward. V16 R4.2 established that selection WF is
not protective on this dataset — the rejected winner passed 5 of 5 held-out
years, because a bias present in every year is identical in every fold.

### T5 — The gate input (diagnostic only, no adoption)

`STRATEGY_SPEC.md`'s variable board records V10 as *"ATR5 ≥ 6% (5d, cliff,
**SOXL input**)"*, but the as-built engine computes each sleeve's ATR5 from
**its own** range history (`spec_engine.py:222`, `replay.py:180`). For SOXL
these coincide; for SOXS they do not. T5 reports both series and the ON-day
sets they produce. **No change is proposed** — this resolves whether the doc
or the engine is wrong, which is a Phase 1-style description defect, not a
strategy question.

## 4. What is NOT being tested

V10's other sub-variables — **form** (cliff vs scaled), **hysteresis**, and
the **input** choice (T5 is diagnostic only). All were confirmed by the
original V10 program and none is implicated by the evidence in §1. Adding
them would triple the search space for no stated hypothesis, which is the
V16 failure.

V9 (the day filter) is not tested here despite also being day-selection. It
deserves its own program; testing both at once would make attribution
impossible, since they filter overlapping day populations.

## 5. Grid

| axis | values | note |
|---|---|---|
| V10 cutoff `GATE_ATR5_MIN` | 4, 5, **6**, 7, 8, 9, 10, 12 % | 6 = incumbent, interior. 4 and 5 included so the grid can find the gate should be *loosened*. |
| V10 lookback `ATR_LOOKBACK` | 3, **5**, 10, 20 sessions | 5 = incumbent, interior |
| everything else | §12 locked | V1 1%, V3 1%, V4 4%, V7 5, V11 flat f + 2-stop |

32 cells per sleeve, 64 runs. Fill model: 1-minute, `spec`,
`target_delay=fill_bar`. Window 2022-01-03+. Features always from the full
5-minute record.

**A caveat on the loosening direction:** the §1 quartile evidence describes
days that already passed the 6% gate, so it says nothing about days below 6%.
Cutoffs of 4 and 5 explore genuinely unobserved territory and their results
carry less prior support than the tightening direction.

## 6. Costs

Per fill, as in V16/V17: SOXL 1.167 bp, SOXS 2.857 bp. This matters
particularly here — the marginal days the gate removes are low-volatility
days, which generate few fills, so their gross and net figures diverge in the
direction that decides the test. SOXS's Q1 is +2.8 gross and **negative** net.

## 7. Adoption bar — PRESPECIFIED, fixed at sign-off

A cell is adopted only if it clears **all seven**:

| # | criterion |
|---|---|
| **D1** | **Primary metric.** Beats the incumbent on **net bp per calendar day**. Per-ON-day figures are reported but may never decide an adoption (§2). |
| **D2** | **Removed days must not be profitable.** The ATR5 band(s) the new cutoff excludes must have a net contribution ≤ 0 per calendar day, in the sleeve being changed. Removing profitable days to flatter an average is rejected regardless of the total. |
| **D3** | **Mechanism (T2).** The adopted gate must measurably raise the share of retained days that reach the trade cap. A return improvement with no cohort shift is fitting noise and is rejected. |
| **D4** | **Risk.** Calmar must improve **and** MaxDD must not worsen by more than 2 percentage points. Calmar rather than MaxDD alone, because a tighter gate reduces exposure and so improves MaxDD almost automatically — that is not evidence of skill. |
| **D5** | **Sample sufficiency.** At least **300 ON days** retained per sleeve (~44% of the current ~680). A gate that leaves 150 days can look excellent by luck; this is the small-sample analogue of a plateau. |
| **D6** | **Plateau and interior.** Neighbours ±1 step in each axis average ≥90% of the cell's net bp/calendar day, and the cell is not on a grid boundary. |
| **D7** | **Effect size, for multiple comparisons.** The improvement must be **≥10% and ≥2 bp per calendar day**. This is pass **four** over the same 679/691 sessions (V16, V17, V18). Small edges are exactly what repeated searching manufactures, so a marginal win is treated as noise by construction. |

**Per-year consistency (T4)** is folded into D1: the candidate must beat the
incumbent on net bp/calendar day in **≥4 of 5 years** in the sleeve adopted.

**Sleeve-specific cutoffs are permitted**, as in V17 — V16 and §1 both show
the sleeves genuinely differ — but each sleeve must clear D1–D7 independently.

**Two specification rules, learned from V17:**

- **No criterion may be a ratio whose denominator can approach zero.** V17's
  C3 compared retention on one day-group against another whose 5-minute edge
  was ~0, producing "4257%" and a meaningless FAIL. Every criterion above is
  a difference or a bounded share.
- **If a criterion turns out to be badly formed, it is disclosed and the
  verdict stands.** It is not repaired to change the outcome; that requires a
  new program.

**If nothing clears the bar, V10's cutoff and lookback close for this
dataset.** As with V17, that is a valid and useful outcome.

## 8. Projection — written before the run

**SOXL: expected to fail (my estimate ~70%).** Its ATR5 response is not
monotone — Q1 is its second-best band at 44.5 bp gross, comfortably positive
net. Raising the cutoff removes profitable days and should fail **D2** on its
face. Note this revives the U-shape the original V10 program closed as
"era-noise"; if it reappears cleanly here that is itself a result worth
recording.

**SOXS: the plausible candidate (~50% to clear D1–D4, less after D7).** Its
response is monotone and Q1 is negative net (+2.8 gross against ~9.6 bp costs).
Removing ~170 of ~690 ON days at roughly −7 bp each recovers on the order of
**+1 bp per calendar day** — which is real but **below D7's ≥2 bp floor**.
So the most likely SOXS outcome is *a genuine but too-small improvement,
rejected on effect size*. I would rather reject a real 1 bp edge on the fourth
pass over one sample than adopt it.

**Most likely overall verdict: NOT ADOPTED, with a documented finding** that
day quality is only weakly forecastable from ATR5 in SOXL and modestly so in
SOXS.

**The outcome that would change my mind:** T2 showing a strong,
year-consistent relationship between ATR5 and trade-cap-cohort membership. If
ATR5 deciles separate the 30%-of-days that carry all the P&L, that is a large
effect and would clear D7 comfortably. I do not expect it — if volatility
predicted churn that strongly, the original V10 sweep would likely have found
a much higher cutoff — but it is exactly the question worth asking, and it is
the reason to run this rather than declare it settled.

**What I am not projecting:** the loosening direction (cutoffs 4–5). There is
no prior evidence either way, since those days have never been in the sample.

---
---

# RESULTS

*(appended after the run; the bar in §7 was not edited)*

## VERDICT: **NOT ADOPTED in either sleeve. V10 stands at 6.0% / 5 days.**

Per §7, V10's cutoff and lookback close for this dataset. The incumbent came
out of this stronger than it went in.

---

## R1. §2 was the whole test, and it was decisive

The metric trap was not hypothetical. SOXL at a 10% cutoff:

| | bp/ON-day | bp/**calendar** day |
|---|---:|---:|
| incumbent 6.0% / 5d | 39.3 | **23.4** |
| cutoff 10.0% / 5d | **93.9** (+139%) | **10.9 (−54%)** |

**On the per-ON-day metric this looks like the best result in the entire
project. It more than halves what the account actually earns**, because ON
days collapse from 679 to 132. Every tightening shows the same pattern.

Had V18 optimised bp/ON-day — the metric every prior program in this
repository reports — it would have adopted a change that cuts returns in half
and called it a doubling. That is the single most useful thing this program
produced.

## R2. SOXL: the incumbent is the best cell on the grid

**Zero of 32 cells beat 6.0% / 5d on net bp/calendar day.** Not a marginal
win — an outright one. The nearest challengers:

| cutoff / lookback | bp/cal | vs inc | bp/ON | ON days | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| **6.0% / 5d (locked)** | **23.4** | — | 39.3 | 679 | −40.6% | 1.66 |
| 6.0% / 10d | 23.2 | −0.3 | 37.7 | 700 | −32.7% | 2.02 |
| 7.0% / 20d | 21.9 | −1.5 | 50.7 | 493 | −24.5% | 2.59 |
| 5.0% / 5d | 20.4 | −3.1 | 26.9 | 863 | −37.3% | 1.42 |
| 9.0% / 5d | 15.6 | −7.9 | **80.2** | 221 | −22.1% | 1.96 |

Note 6.0%/10d and 7.0%/20d have materially **better Calmar** (2.02, 2.59 vs
1.66) at slightly lower return — a genuine risk/return trade the primary
metric does not capture. That is a legitimate observation for a future
risk-budgeting decision, not an adoption: D1 is the return metric and these
do not beat it.

## R3. SOXS: three cells beat the incumbent, all on a grid boundary

| cutoff / lookback | bp/cal | vs inc | interior? |
|---|---:|---:|---|
| 6.0% / **3d** | 20.9 | **+2.6** | no — lookback boundary |
| 7.0% / **3d** | 20.6 | **+2.3** | no — lookback boundary |
| 6.0% / **20d** | 19.6 | +1.3 | no — lookback boundary |
| **best interior cell** | **18.3** | **+0.0** | **the incumbent** |

All three sit on the lookback axis boundary, which under D6 means the optimum
may lie outside the tested range — unresolved, not a result. They also fail on
substance: 6.0%/3d fails **D4** (MaxDD −43.4% against a −38.5% floor);
7.0%/3d fails **D1** (3 of 5 years).

**Disclosed grid-design limitation.** `LOOKBACKS = [3, 5, 10, 20]` has only
**two** interior values (5 and 10), so the lookback axis could only ever adopt
one of two settings. That is thin, and all three SOXS winners wanting to leave
5 is a signal the axis was under-sampled. It does not overturn the verdict —
a boundary optimum is unresolved by construction, and the best *interior* cell
is the incumbent in both sleeves — but a future program on the lookback should
use a denser axis. Reported rather than repaired, per §7.

## R4. T2 — ATR5 predicts churn strongly, and profit not at all

The result I said would change my mind **appeared**, cleanly and monotonically
in both sleeves: the share of days reaching the 5-trade cap (V17 R5's
profitable cohort) rises with ATR5 without a single reversal.

| ATR5 decile | SOXL cap share | SOXL net bp/ON-day | SOXS cap share | SOXS net bp/ON-day |
|---|---:|---:|---:|---:|
| 1 (lowest) | 10% | **+63.1** | 20% | +10.8 |
| 2 | 10% | +40.3 | 16% | −46.6 |
| 3 | 13% | +39.2 | 20% | +48.0 |
| 4 | 19% | **−16.9** | 19% | −15.5 |
| 5 | 26% | +16.1 | 32% | +41.0 |
| 6 | 36% | +21.4 | 41% | +67.0 |
| 7 | 32% | **−13.5** | 43% | −0.4 |
| 8 | 40% | +70.7 | 39% | +41.0 |
| 9 | 44% | +72.4 | 59% | +84.9 |
| 10 (highest) | **57%** | +100.4 | **67%** | +73.1 |

**Cap share is monotone. Profitability is not.** SOXL's *lowest* ATR5 decile
has the lowest churn (10% cap share) and the **fourth-highest** net return
(+63.1 bp/ON-day). The mechanism V17 R5 identified is real, but ATR5 does not
select for profit through it.

## R5. Why — the low-volatility days are profitable for the opposite reason

Exit mix by ATR5 decile explains the whole result:

| ATR5 decile | SOXL stop % | SOXL target % | SOXL flatten % |
|---|---:|---:|---:|
| 1 (lowest) | **6%** | 63% | **31%** |
| 5 | 14% | 68% | 18% |
| 10 (highest) | **14%** | 79% | **7%** |

SOXS is the same shape (6% → 12–13% stops, 34% → 7% flattens).

**Two different profitable regimes:**

- **Low ATR5:** few round trips, but the −4% stop is rarely reached (6%) and
  a third of positions are simply flattened at the close near breakeven.
  Quietly positive with little tail.
- **High ATR5:** many round trips and a high target-hit rate (79–82%), paying
  for a stop rate that has more than doubled.

The gate cannot be tightened because it would delete the first regime, which
is profitable through *safety* rather than through churn. That is why D2
failed for every tightening on SOXL, and it is a better reason than the sweep
alone gives.

**The U-shape returns.** `STRATEGY_SPEC.md` records V10's original program
closing a U-shape as "era-noise". It reappears here in SOXL on independent
1-minute data, with a mechanism attached. **But it does not replicate in
SOXS** — that sleeve's middle deciles are erratic rather than U-shaped, and at
~68–69 days per decile the standard error is large enough that a single decile
means little. So: suggestive, not established, and consistent with the
original "era-noise" verdict being right.

It points at V10's **form** (a band rather than a cliff), which §4 explicitly
excluded from this program and which was not prespecified. Testing it would be
a **fifth** pass over the same 679/691 sessions. It should not be run on this
data.

## R6. T5 — the doc/engine discrepancy is immaterial

`STRATEGY_SPEC.md`'s variable board records V10 as *"SOXL input"*; the engine
uses each sleeve's own ATR5. On the 1,140 shared SOXS sessions:

| | ON days |
|---|---:|
| SOXS's own ATR5 (as built) | 859 |
| SOXL's ATR5 (as documented) | 843 |

The two agree on **1,104 of 1,140 sessions (97%)**, correlation **0.991**.

**No change proposed.** The engine's behaviour is the validated one — every
published number was produced with per-sleeve ATR5 — so this is a description
defect. `STRATEGY_SPEC.md`'s variable board should be corrected to read
"own-symbol input", the same class of fix Phase 1 made to §2.1.

## R7. Projection scorecard (§8, written before the run)

| projected | outcome |
|---|---|
| "SOXL expected to fail (~70%), on D2, because its lowest band is profitable" | **Correct, and stronger than projected** — the incumbent is the single best cell of 32 ✓ |
| "SOXS the plausible candidate, ~+1 bp/calendar day" | **Magnitude close** (+2.6 actual) ✓ |
| "SOXS most likely rejected on effect size (D7)" | **Wrong criterion.** SOXS *passed* D7 (+2.6 bp, 14.2%); it failed D4, D6 ✗ |
| "The U-shape may reappear; that would itself be a result" | **Reappeared in SOXL, not in SOXS** ✓ |
| "What would change my mind: T2 showing ATR5 separating the cohort" | **It did — monotonically in both sleeves.** The conclusion held anyway, for a reason I had not anticipated (R5) ✗ |

The last row is the one worth keeping: the evidence I had nominated as
decisive arrived, and the decision did not change, because churn and profit
turned out to be separable. Nominating decisive evidence in advance is still
right — it just has to be allowed to lose.

## R8. Recommendation

1. **Adopt nothing. V10 stands at 6.0% / 5 days**, now with materially better
   support than it had: on the correct metric it is the best of 32 cells in
   SOXL and the best interior cell in SOXS.
2. **Correct `STRATEGY_SPEC.md`'s variable board** to say own-symbol ATR5
   input (R6). Documentation fix, no strategy change.
3. **Stop sweeping this dataset.** V16, V17 and V18 have adopted nothing across
   four passes and ~1,040 cells. That is the correct outcome each time, and it
   is also the signal: the locked parameters are not the binding constraint.
   The S11 residual is, and only live fills settle it.
4. Record for a future risk-budgeting discussion (not an adoption): SOXL at
   6.0%/10d gives Calmar 2.02 against the incumbent's 1.66 for −0.3 bp/cal-day.

---

## 9. Priority note

Unchanged from V16 and V17: this is **not** the critical path. The paper run
is, and `band_lab/live` Stages 2–4 are now built for it. V18 is cheap (64
runs, ~2 minutes) and answerable offline, so it is worth running in parallel —
but the S11 residual that gates every figure in this project is settled by
real fills, not by a fourth sweep.
