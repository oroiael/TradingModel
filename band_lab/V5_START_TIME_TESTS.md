# V5 Test Program — Start Time for the Churn Harvester Core

Current value: **10:30** (bar 12). This was *derived*, never tested: the
range-completion curve says 68% of the day's band is set by 10:30, and 58%
of excursions fire in the first hour, so 10:30 was chosen by argument. It
is the same species of assumption as the trade cap was — plausible,
load-bearing, unswept. The cap survived its test; the start time gets the
same treatment.

Interactions to hold fixed (discipline): the orq5 filter is known by 10:00
and stays as-is; the dip anchor already includes pre-start highs (a 10:00
start does NOT change the anchor definition, only when entries may fire);
cap 5 / 2-stop breaker unchanged; per-day AND per-trade metrics reported
side by side, because moving the start changes trade counts and a per-day
comparison alone would conflate edge with exposure.

---

## T2 runs FIRST — measure where the edge lives before sweeping

**Mechanic.** Regenerate per-trade logs with the earliest feasible start
(9:35, bar 1) and bucket every trade by its **entry time** (30-min
buckets): mean return, stop rate, target rate, EOD-exit rate per bucket.
This is the V11-style "conditional stat before the rule" step: it shows
directly which part of the day pays for dip-buying and which part is the
excursion minefield — and it prices every possible start time in one
table instead of seven sims. (Same logic that made the 2-stop breaker an
obvious adopt before its sim ran.)

**Data now:** sufficient (5-min bars regenerate all trades).
**Better with:** 1-min bars for the 9:35–10:00 region specifically — the
day's most violent 5-min buckets are the coarsest relative to their vol.
**Depth:** hours. **Downside:** none — measurement.
**Expected shape (guess):** negative or wild 9:35–10:00, strong mid-day,
weakening after ~14:30 as EOD-forced exits truncate late entries.

## T1. Plain start-time sweep

**Mechanic.** Start ∈ {09:35, 10:00, 10:15, **10:30**, 11:00, 11:30,
12:00, 13:00}, everything else locked. Report bp/day, per-trade bp,
trades/day, Sharpe, worst day, by-year table. Verdict standard: a
different start wins only if better on Sharpe AND not worse on worst-day,
with the by-year table ≥ as consistent — otherwise 10:30 stands (plateau
logic: neighbors within noise round to the incumbent).

**Data now:** sufficient. **Depth:** hours (8 sims of existing code).
**Max upside:** if 10:00 or 09:35 wins, more trades on the same gated
days — guessed +5–15% relative bp/day; the breaker already caps the
morning-excursion tail at 2 stops (−8%), which is what makes an earlier
start survivable at all (this test was more dangerous before V11).
**Max downside:** none structural — worst case confirms 10:30 on a
plateau, closing V5 the way V8 closed the short side.

## T4. Last-entry cutoff (the other end of the window)

**Mechanic.** Keep start fixed at the T1 winner; sweep a **no-new-entries
after** cutoff ∈ {14:00, 15:00, 15:30, none (baseline)}. Rationale: a
15:40 entry has ~4 bars to reach +1% before the forced EOD exit turns it
into a coin flip; T2's EOD-exit-rate-by-entry-time column says exactly how
big this effect is before the sweep runs. Positions opened before the
cutoff still run to target/stop/close as usual.

**Data now:** sufficient. **Depth:** hours.
**Max upside:** small but clean — trimming coin-flip entries should lift
per-trade edge and slightly cut worst-day; guessed +0–5 bp/day.
**Max downside:** late entries might actually carry edge (the 15:00–16:00
hour is the day's second vol peak, 16% of excursions) — in which case the
cutoff costs money and dies by the same table.

## T3. Conditional start (signal-dependent window)

**Mechanic.** ONE prespecified rule, no variants, using only pre-10:00
information: **if |gap| < 1% AND OR30 < its trailing median → start
10:00; else start 11:00.** Logic: calm mornings finish building the band
early (start early, harvest more); violent mornings are the excursion
window (wait longer). Compared against the best fixed start from T1 on
the same days. This is the highest-overfit-risk test in the program —
hence exactly one rule, parameters fixed here, and adoption requires
beating the fixed start OOS in ≥5 of 7 years.

**Data now:** sufficient. **Depth:** half-day with the honesty checks.
**Max upside:** a few bp/day if the calm/violent split is real.
**Max downside:** a fitted rule that walk-forward will expose; contained
by prespecification and the 5-of-7 bar.

## T5. Robustness protocol (meta-test, runs on whatever wins)

**Mechanic.** Whatever T1–T4 produce: (a) yearly walk-forward with the
start time selected on prior years only — the OOS by-year table is the
adoption evidence; (b) plateau check — the winner's ±15-minute neighbors
must be within ~1 Sharpe-noise band (a spike start time that its
neighbors don't support is curve-fitting, rejected by rule); (c) cost
sensitivity note — morning spreads are the day's widest, so any
early-start winner gets re-checked when the cost module lands.

**Data now:** sufficient. **Depth:** hours (harness exists from the
cycle/day walk-forwards).

---

## Program summary

| test | depth | data now | decisive question | best case | worst case |
|---|---|---|---|---|---|
| **T2 edge-by-time map** | hours | ✅ (1-min better for 9:35–10:00) | where does the edge live intraday? | prices all starts in one table | — (measurement) |
| T1 start sweep | hours | ✅ | is 10:30 on the plateau optimum? | +5–15% rel. return from earlier start | 10:30 confirmed, V5 closed |
| T4 last-entry cutoff | hours | ✅ | do late entries carry edge? | +0–5 bp/day, cleaner tails | cutoff costs the 15:00 vol harvest |
| T3 conditional start | half-day | ✅ | should the window be signal-set? | few bp/day | fitted rule, killed by 5-of-7 bar |
| T5 robustness protocol | hours | ✅ | does the winner survive OOS + plateau? | adoption evidence | reverts to 10:30 |

**Recommended order: T2 → T1 → T4 → T3 → T5.** Measurement first (T2
prices every start before any sweep), the cheap sweeps next, the one
fitted rule last where its overfit risk is bracketed by the protocol.

**Aggregate bounds:** best case — an earlier start plus a late-entry
cutoff add ~5–15% relative return with tails still breaker-capped, and
T2's map becomes a permanent reference for every future timing question.
Worst case — 10:30 is confirmed as plateau-optimal and V5 closes with
evidence, which after the cap sweep's outcome (assumption confirmed at
the optimum by luck) would be the second time a derived guess survived
its audit. Total program cost: well under a day. Nothing here can damage
the locked core — every test is additive-or-reject against the incumbent.

---

# RESULTS (run 2026-07-28; `v5_start_time_tests.py`, then
# `v5_corrected_rerun.py` after the bug discovery)

## The program's biggest product: a lookahead bug, caught by its own smell

The first sweep printed start-09:35 at 127 bp/day, Sharpe 5.73, walk-
forward-stable — numbers too good to be true, and they weren't. Diagnosis:
the sim updated the rolling high with the CURRENT bar before the entry
check, so one bar with ≥1% range could set the trigger 1% below its own
high and then "fill" the +1% target with that very high — an unknowable
intrabar sequence booked as certain profit. The effect scales with bar
range: rampant 09:30–10:00, mild at midday. **Every band_lab number
before the corrected engine carried some of this.** Corrected rules:
trigger from prior bars only (a true resting limit), target fills from
the next bar onward, same-bar stop still allowed (conservative).

Corrected load-bearing numbers (all at the locked config, gated days):
- core 10:30 + breaker2: **53.8 bp/day, Sharpe 2.46, worst −8.0%**
  (the old engine UNDERSTATED the 10:30 core: 44.9/2.25 — the bug cut
  both ways at midday);
- breaker re-verified and now bigger: 53.8 vs 45.3 bp without it
  (worst day −8.0% vs −15.2%);
- 09:35 start collapses 127 → 67.9 bp (Sharpe 5.73 → 2.74).

## T1/T5 verdict on the corrected engine: start = 11:00

| start | bp/day | Sharpe | maxDD |
|---|---:|---:|---:|
| 09:35 | 67.9 | 2.74 | −46.0% |
| 10:00 | 40.4 | 1.68 | −53.7% |
| 10:30 (old) | 53.8 | 2.46 | −34.7% |
| **11:00** | **59.6** | **2.87** | **−32.1%** |
| 11:30 | 56.4 | 2.85 | −27.9% |
| 13:00 | 47.3 | 2.72 | −24.2% |

**Adopted: 11:00.** It beats the incumbent on return, Sharpe, and DD
simultaneously, sits on a genuine plateau (11:30 within noise, 10:30
adjacent), and the corrected walk-forward picks only from that plateau
(10:30/10:30/11:00/11:30/11:00 across the years; OOS 60.6 bp, Sharpe
2.76). **09:35 rejected** despite its raw numbers: it is a lone spike
whose immediate neighbor (10:00) is the sweep's worst cell — exactly the
curve-fit signature the prespecified plateau rule exists to catch — and
its trades live in the bars where touch-fill assumptions are least
believable (revisit only if 1-min data + cost model ever land).

## T4: no last-entry cutoff — rejected cleanly

At start 11:00 on the corrected engine, cutoffs cost money monotonically
(14:00 → 48.9 bp; none → 59.6 bp). Late entries carry real edge; the
worst-day is identical either way. The T2 map's late-day EOD-exit rates
looked scary but the breaker already absorbs the risk.

## T3: conditional start — rejected (dominated by fixed 11:00).

## Net effect of the V5 program

Start 10:30 → 11:00, +5.8 bp/day, Sharpe 2.46 → 2.87, maxDD −34.7% →
−32.1%, and an engine that no longer manufactures profit out of wide
bars. Flagged for re-verification on the corrected engine (relative
verdicts whose both arms shared the bug): pyramid-vs-flat, exact cap
values, cost estimates.
