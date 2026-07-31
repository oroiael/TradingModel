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

## 9. Priority note

Unchanged from V16 and V17: this is **not** the critical path. The paper run
is, and `band_lab/live` Stages 2–4 are now built for it. V18 is cheap (64
runs, ~2 minutes) and answerable offline, so it is worth running in parallel —
but the S11 residual that gates every figure in this project is settled by
real fills, not by a fourth sweep.
