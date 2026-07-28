# V1/V3 Test Program — Adaptive Dip & Target Levels

Current values: **dip 1%, target 1%, both fixed** — swept as constants
(dip 1–3%, target 1–2%, both plateau-optimal at 1%) but never allowed to
scale with the day's band. The motivating tension: a 1% dip is a third of
a quiet day's range and a twelfth of a wild one's, yet the strategy
treats them identically. Everything needed to scale is already measured:
expected day range ≈ **1.9 × OR30** (known at 10:00, corr 0.62) or via
ATR5 (known pre-open); the churn counts scale with vol (15 ≥1% swings on
the average day, ~6 ≥2%); and V11 found per-trade edge RISES with dip
depth (trade #3+ ≈ 20 bp vs #1's 7 bp) — deeper dips are better dips,
which adaptive sizing would seek systematically.

This is the highest-dimensional program yet (scaling source × coefficient
× which leg scales × stop geometry), so the dimensionality control is the
plan's core feature: **T1 is a go/no-go measurement** — if the optimal
fixed pair does not migrate across band regimes, adaptivity is dead on
arrival and the program stops there; asymmetric dip/target combinations
are forbidden unless BOTH single-knob tests win independently; and
adoption requires a mechanism, not just a score.

Baseline: locked core (V9 direction filter, gate 6, start 11:00,
breaker) = **65.6 bp/traded-day, Sharpe 3.09**. Corrected engine. Stop
stays −4% except where T4 explicitly varies its geometry.

---

## T1 runs FIRST — does the optimum migrate? (go/no-go measurement)

**Mechanic.** Run the nine fixed pairs {dip, target} ∈ {1, 1.5, 2}² and
slice each day's P&L by **expected-band tercile** (E[range] = 1.9 × OR30,
computed at 10:00; repeated with ATR5 terciles as the pre-open view).
Produce the 3×3 best-pair table per tercile. Decisive readout:
- optimum is {1, 1} in every tercile → **adaptivity is dead**; program
  ends, V1/V3 close as confirmed-fixed, total cost a morning;
- optimum migrates (e.g., {1, 1} on narrow days → {2, 1.5} on wide days)
  → the migration pattern itself specifies which leg should scale and
  roughly how fast, and T2–T4 proceed with that prior.

**Data now:** sufficient. **Depth:** hours (9 sims + slicing).
**Downside:** none — measurement. **Expected (guess):** partial
migration — the dip optimum drifts up with band width (the V11
deeper-dip finding predicts this), the target optimum stays near 1%
(EOD truncation punishes big targets late in the day).

## T2. Adaptive dip, single knob

**Mechanic.** dip_d = α × E[range]_d, α ∈ {0.15, 0.20, 0.25}, floored at
0.75% (5-min bars cannot cleanly resolve sub-¾% triggers) and capped at
3%. Target fixed at 1%, stop fixed at −4%. Two E[range] sources run in
parallel: 1.9×OR30 (10:00 info, sharper) and ATR5 (pre-open, smoother) —
the source comparison is part of the test. On the median day (range
6.7%) α = 0.15 ⇒ dip ≈ 1.0% — the incumbent is nested inside the grid,
which is deliberate: the fixed rule must be a special case the adaptive
rule can fall back to.

**Data now:** sufficient; 1-min data would matter only if quiet-day
optima press against the 0.75% floor — flagged, not blocking.
**Depth:** half-day.
**Max upside:** wide days stop being churn-chased with too-shallow
entries; guessed +2–6 bp/day concentrated in the top band tercile.
**Max downside:** fewer trades on wide days (deeper triggers fire less)
— the per-day edge can fall even if per-trade edge rises; both reported.

## T3. Adaptive target, single knob

**Mechanic.** target_d = γ × E[range]_d, γ ∈ {0.15, 0.20, 0.25}, floor
0.75%, cap 2.5%; dip fixed 1%, stop −4%. Reported with target-hit rate
and forced-EOD-exit rate per band tercile — the V6 anatomy says
truncation costs ~83 bp per affected trade, and bigger targets on big
days will raise the truncation rate; the test must show the bigger wins
beat the extra truncations.

**Data now:** sufficient. **Depth:** half-day.
**Max upside:** wide-day swings are ~2%+; collecting 1% of a 12% band
leaves money — guessed +0–5 bp/day. **Max downside:** truncation drag
turns it negative; the per-tercile hit-rate table shows exactly where.

## T4. Joint symmetric + stop geometry (only if T2 or T3 wins)

**Mechanic.** Two prespecified variants only:
  a. **tied-symmetric**: dip = target = α* × E[range] (α* = T2/T3
     winner), stop fixed −4%;
  b. same, **stop = 4 × target** (preserves the locked 4:1 geometry —
     V4 confirmed 4% against 1% levels, so scaled levels must re-ask
     whether it is the ratio or the absolute that mattered).
Asymmetric dip≠target grids are out of scope by rule unless both T2 AND
T3 won independently (they would then define the one asymmetric pair
allowed to run).

**Data now:** sufficient. **Depth:** hours on top of T2/T3 machinery.
**Max upside:** clean geometry preserved across regimes; the breaker's
worst-day guarantee changes with (b) — a scaled stop on a wide day can
exceed −4% per trade, so the (b) worst-day column is the adoption
gatekeeper. **Max downside:** (b) re-opens tail risk the breaker was
built to cap — it can win on Sharpe and still lose on the worst-day
standard.

## T5. Validation protocol

**Mechanic.** For any winner: (a) yearly walk-forward — rule (fixed vs
adaptive, source, coefficient) selected on prior years only; adoption
bar OOS ≥4 of 5 years no worse than fixed; (b) plateau in α (neighbors
within noise); (c) **mechanism requirement** — the win must live where
T1's migration said it should (day-overlap/tercile attribution); a win
scattered across regimes T1 called flat is treated as fitting and
rejected; (d) trade-count & cost re-accounting (adaptive dips change
fills/day, which changes the commission line and the breaker's bite);
(e) desk restatement — one sentence computable at 10:00, e.g. "dip and
target = 20% of (1.9 × OR30), floored at 0.75%, capped at 3%."

**Data now:** sufficient. **Depth:** hours (harness exists).

---

## Program summary

| test | depth | data now | decisive question | best case | worst case |
|---|---|---|---|---|---|
| **T1 migration map** | hours | ✅ | does the optimal pair move with band width? | specifies the whole program | adaptivity dead — program ends cheap |
| T2 adaptive dip | half-day | ✅ (1-min if floor binds) | scale entries to the band? | +2–6 bp/day on wide days | fewer trades eat the gain |
| T3 adaptive target | half-day | ✅ | scale exits to the band? | +0–5 bp/day | truncation drag |
| T4 joint + stop geometry | hours | ✅ | ratio or absolute stop? | clean scaled geometry | tail re-opened — worst-day gate |
| T5 validation | hours | ✅ | OOS + mechanism + costs | adoption evidence | reverts to fixed 1%/1% |

**Recommended order: T1 → (stop if flat) → T2 → T3 → T4 → T5.**

---

# RESULTS (run 2026-07-28, `v1v3_adaptive_tests.py` → `out/v1v3_results.csv`)

**Verdict: NO migration — fixed 1%/1% confirmed. V1 and V3 close.**

**T1 — the go/no-go came back flat.** Across E[range] terciles the best
fixed pair is {1%, 1%} in narrow, mid, AND wide; across ATR5 terciles
it is {1,1} in two of three (the mid tercile's marginal 1.5/1 preference,
22.6 vs 18.9 bp, is a lone low-signal cell). The dip-buy's optimal
levels do not breathe with the band: SOXL's intraday reversion appears
to operate at a ~1% grain regardless of how wide the day is — consistent
with the original churn stat (≥1% swings are 2.5× more numerous than ≥2%
swings on ALL day types).

**T2/T3/T4 — everything the grids offered fails the rules.** All
adaptive dips underperform (best 63.2 vs 65.6 bp). One adaptive target
cell (0.15×OR: 70.1 bp, Sharpe 3.08) beats the baseline in-sample, but
it fails BOTH prespecified bars: the mechanism requirement (T1 said the
target optimum does not migrate, and the cell's win concentrates in the
wide tercile where T1's grid explicitly preferred t=1%) and the
walk-forward (never picked; picks alternated fixed / dip-0.15×OR; ALL
OOS 66.6 bp, Sharpe 3.06 ≈ baseline). Recorded as the textbook example
of the in-sample cell the protocol exists to reject.

**T4's bonus finding upgrades V4.** Scaling the stop with the target
(4×tgt) destroyed the worst-day guarantee (−14.1% to −20.0% vs −8.0%)
without a Sharpe payoff. **It is the absolute −4% stop that matters, not
the 4:1 ratio** — the breaker's −8% day guarantee is arithmetic on the
absolute stop (2 × −4%), and any future levels experiment must hold the
absolute stop fixed.

## Decisions
1. V1 dip = 1% fixed: **confirmed** (adaptive rejected).
2. V3 target = 1% fixed: **confirmed** (adaptive rejected on mechanism
   + OOS).
3. V4 annotation strengthened: the stop is an absolute-risk rule, not a
   geometry rule; never scale it.
4. The variable register is now fully audited except V2 (entry-anchor
   family).

**Aggregate bounds:** best case — levels that breathe with the band add
~3–8 bp/day concentrated exactly where T1 predicts, with the fixed rule
nested as the quiet-day special case and the 4:1 geometry re-validated
in scaled form. Realistic case — partial adoption (adaptive dip only,
ATR5-sourced, small α) or a clean confirmation that the 1%/1% plateau
is genuinely flat across regimes. Worst case — T1 shows no migration
and the program closes the last open variables on the status board for
the cost of one morning. Nothing here can damage the core: fixed 1%/1%
is nested in every grid, and every candidate faces the same walk-forward
bar that has now rejected more ideas than it has adopted. After this
program, only V2 (entry-anchor family) remains open — the variable
register would then be fully audited.
