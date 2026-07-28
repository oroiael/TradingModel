# V9 Test Program — Day-Filter Boundary for the Churn Harvester Core

Current value: **skip the day when OR30 ≥ the trailing 80th percentile of
OR30** (OR30 = 09:30–10:00 high-low range / open; threshold recomputed
monthly from ~2 years, currently ≈5.4%). What IS tested: the filter
*family* — orq5 beat gap2, no-filter, and combinations, and both
survived walk-forward selection. What is NOT tested: the **80** itself
(chosen as "top quintile" by round number), the **form** of the
threshold (percentile vs absolute vs ATR-relative), the **direction
blindness** (a violent up-morning and a violent down-morning are
filtered identically), and the **recompute cadence**. The filter
discards ~20% of days (~300 over the sample) — V8-T5 already proved
those days don't pay as momentum longs, but not that all of them
deserve discarding for the dip-buy.

Discipline as always: every parameter below is fixed by this document
before running; thresholds in every test are computed from trailing data
only (the boundary is exactly the kind of knob where full-sample
quantiles smuggle in lookahead); corrected engine, start 11:00, breaker
on.

---

## T1 runs FIRST — edge-by-OR30 map (measurement)

**Mechanic.** Run the core with the OR30 filter OFF (gate ON) and bucket
daily P&L by OR30 **decile** (trailing-computed decile assignment). One
table shows exactly where the dip-buy edge dies as the morning gets more
violent — pricing every possible boundary at once. Second cut: the
coarse joint map OR30-tercile × ATR5-tercile, because the gate and the
filter both measure "violence" and their interaction is unmeasured — a
big OR30 on a huge-ATR week may be normal weather, while the same OR30
in a quiet week is an anomaly.

**Data now:** sufficient. **Depth:** hours. **Downside:** none.
**Expected shape (guess):** flat-to-positive edge through deciles 1–7,
deteriorating in 8–9, clearly negative in 10 — which would imply the
true boundary is nearer the 90th percentile than the 80th and the
filter is currently over-discarding.

## T2. Boundary sweep

**Mechanic.** Skip-threshold percentile ∈ {60, 70, 75, **80**, 85, 90,
95, 100 = no filter}, threshold always the trailing 2-year percentile
(no lookahead). Report bp/day, Sharpe, worst day, days discarded, and
the by-year table per cell. Verdict by the plateau rule: a new boundary
wins only with better Sharpe, no-worse worst-day, neighbor support, and
a consistent year table.

**Data now:** sufficient. **Depth:** hours.
**Max upside:** if T1 shows over-discarding, moving 80 → 85–90 re-admits
~75–150 days carrying positive edge — guessed +1–4 bp/day overall.
**Max downside:** none structural; worst case 80 is confirmed on a
plateau and the boundary stops being a round-number choice.

## T3. Threshold form — percentile vs absolute vs ATR-relative

**Mechanic.** Three forms, same sweep protocol:
  a. **trailing percentile** (incumbent form);
  b. **absolute**: skip if OR30 > X%, X ∈ {4, 5, 6, 7};
  c. **ATR-relative**: skip if OR30 > k × ATR5, k ∈ {0.5, 0.65, 0.8,
     1.0} — "the morning has already spent the day's range budget."
     This is the theoretically-motivated form: OR30 predicts day range
     at 1.9×, and scaling by ATR5 removes the regime level so the
     filter measures *surprise* rather than raw size.
Forms are compared on identical days; the winner must also win the
day-overlap analysis (see T5) to prove it differs by design rather than
by which handful of edge-case days it happens to flip.

**Data now:** sufficient. **Depth:** half-day.
**Max upside:** the ATR-relative form filtering better in BOTH calm and
violent regimes — cleaner than any fixed percentile; guessed +0–3
bp/day plus robustness. **Max downside:** three forms × sweeps is the
program's biggest multiple-comparison surface — contained by the
plateau rule and by requiring the winner to beat the incumbent OOS in
the T5 walk-forward, not in-sample.

## T4. Direction-aware filter (one prespecified refinement)

**Mechanic.** Measure first: split currently-filtered days (big OR30)
by where the 10:00 print sits in the opening range — bottom third
("violent down morning") vs top third ("violent up morning") — and
compare rest-of-day dip-buy P&L for the two cohorts. If the conditional
split shows the harm concentrated in down-mornings, test the single
rule: **skip only if OR30 ≥ threshold AND the 10:00 close sits in the
bottom two-thirds of the opening range** (i.e., re-admit violent
up-mornings). No other variants.

**Data now:** sufficient. **Depth:** hours.
**Max upside:** violent up-mornings are ~half the filtered days; if
they trade normally, +1–3 bp/day. **Max downside:** up-morning violence
may mean blow-off tops that reverse — the conditional split answers
this before the rule runs; contained the usual way.

## T5. Validation protocol (meta-test)

**Mechanic.** For the winning boundary/form: (a) yearly walk-forward —
boundary AND form selected on prior years only, OOS table decides
(adoption bar: OOS ≥4 of 5 years no worse than the incumbent's OOS);
(b) plateau report — the winner's neighbors within noise; (c)
**day-overlap analysis** — which actual days each candidate flips vs
the incumbent, so the verdict names its mechanism (re-admitting
up-mornings? mid-size ORs in violent regimes?) instead of just its
score; (d) recompute-cadence sensitivity — monthly vs quarterly vs
annual threshold refresh (the desk currently says monthly; if results
swing on cadence, the filter is fragile and the absolute form wins by
default); (e) desk-rule restatement — whatever wins must reduce to one
sentence computable at 10:00 with no lookahead.

**Data now:** sufficient. **Depth:** hours (harness exists).

---

## Program summary

| test | depth | data now | decisive question | best case | worst case |
|---|---|---|---|---|---|
| **T1 OR30-decile map** | hours | ✅ | where does the edge actually die? | prices all boundaries at once | — (measurement) |
| T2 boundary sweep | hours | ✅ | is 80 the right percentile? | +1–4 bp/day from re-admitted days | 80 confirmed on a plateau |
| T3 threshold form | half-day | ✅ | percentile, absolute, or ATR-relative? | regime-robust filter | multiple-comparison noise (contained) |
| T4 direction-aware | hours | ✅ | do violent UP mornings deserve filtering? | +1–3 bp/day | blow-off reversals say yes they do |
| T5 validation | hours | ✅ | does the winner survive OOS + mechanism review? | adoption evidence | reverts to incumbent |

**Recommended order: T1 → T2 → T3 → T4 → T5.**

**Aggregate bounds:** best case — a re-tuned, possibly ATR-relative,
possibly direction-aware filter re-admits 50–150 tradable days and adds
~2–6 bp/day with better regime robustness; realistic case — the boundary
moves modestly (80 → 85-ish) for +1–2 bp/day; worst case — the incumbent
is confirmed at every step and V9 graduates from "partially tested" to
closed, with the boundary's mechanism documented for the first time.
Nothing here can damage the core: the filter only decides which days to
sit out, and every candidate is benchmarked against sitting out exactly
the days we sit out today. Total cost: about a day.
