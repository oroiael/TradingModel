
# V37 — Long-dated straddle (V29 Tier 2 #4). Bar, written before the code.

Buy an ATM straddle at **~180 DTE**, hold to expiry, no hedge. Committed before
`straddle_backtest.py` gains a long-tenor option.

## First: the missing input, now measured

V29 flagged that V27 only ever compared 30-day implied vol against 30 sessions
forward. Matched properly at each tenor, 2022–2026:

| tenor | implied | realised | **edge** | indep. windows | t |
|---|---|---|---|---|---|
| 1 week | 104.8% | 104.6% | **−0.2** | 224 | −0.08 |
| 1 month | 99.2% | 110.2% | **+10.9** | 53.6 | 2.52 |
| 3 months | 97.0% | 109.1% | +12.0 | 7.3 | 1.20 |
| **6 months** | **92.2%** | 108.0% | **+15.8** | **6.1** | **2.00** |
| 1 year | 87.8% | 108.5% | +20.7 | **1.0** | 1.16 |

**Implied vol falls with tenor while realised does not.** The market charges
104.8% for a week and 87.8% for a year, and the underlying delivers ~108% at
every horizon. So the premium is largest exactly where the spread is cheapest —
which is the whole case for #4.

Combining with V28's measured end-of-day spread per tenor:

| tenor | edge | spread | net | cycles/yr | **net/yr** |
|---|---|---|---|---|---|
| 1 month | +10.9 | −8.1 | +2.8 | 12.2 | +34.7 |
| 3 months | +12.0 | −6.5 | +5.5 | 4.1 | +22.5 |
| 6 months | +15.8 | −4.9 | **+10.9** | 2.0 | +22.1 |

The 1-month row is known to be wrong: V32 measured the real intraday spread at
17.8 vol points against the 10.6 those snapshots imply, and V31/V32 showed the
monthly straddle losing 10.11%/cycle once that is charged. If the same 1.68×
understatement applies at 6 months, the real spread there is ~8.2 points and the
net is **+7.6 per cycle, ~+15/yr** — still positive, and the first structure in
this whole catalogue whose arithmetic survives its own costs.

## The problem that dominates everything else

**4.49 years of data supports about 9 non-overlapping 180-day cycles.**

That is not a sample. Overlapping starts produce more rows but not more
information, and a t-statistic on overlapping windows at this tenor would be
roughly 11× too large.

**So this test is prespecified to be inconclusive, and that is the finding.**
The bars below are stated anyway, because a bar that only exists when it can pass
is not a bar. But the expected outcome is "cannot be resolved on this data",
which is a different result from #1, #2 and #3 — those were resolved, and they
failed.

## Prespecified grid

Headline: **nearest 180 DTE, hold to expiry, unhedged.**

- target DTE: **90, 180, 270** — 3
- hedge: **none**, **daily** — 2

Six cells. Hold-to-expiry throughout, since V34 and V36 both measured not
crossing the exit spread as the largest single effect available.

Both spread regimes reported: the vendor end-of-day spread, and that plus a
shortfall scaled from V32's measurement.

## Adoption bars

| # | bar | note |
|---|---|---|
| **B1** | mean return per cycle > 0 with **t > 2.0**, t computed on **independent** cycles | the overlap correction is the whole point |
| **B2** | positive in **≥ 4 of 5** calendar years | likely unmeasurable at 9 cycles; reported regardless |
| **B3** | every cost charged | |
| **B4** | **≥ 5 of 6** cells positive | |
| **B5** | headline within **1 se** of the grid median | |
| **B6** | benchmark via `research_kit.Result` | |
| **B7** | max drawdown **< 35%** | |

**B1 must use the non-overlapping cycle count.** Reporting t on overlapping
starts would be the same error V27's open-to-close estimator nearly made and
V31's C1 did make: a number that is arithmetically correct and evidentially
empty.

## New assumptions

| # | assumption | kind |
|---|---|---|
| A22 | The V32 spread shortfall scales proportionally across tenors (×1.68 on the vendor figure). **Not measured beyond ~35 DTE.** Long-dated spreads may be relatively wider or tighter. | `[ASSUMED]` |
| A23 | A 180-day option can be filled at the quoted touch in 10-contract size. V32 measured 512 contracts of depth at ~35 DTE; **long-dated depth is unmeasured and is certainly thinner**. This flatters the structure. | `[ASSUMED]` |
| A24 | No early exercise, no dividend adjustment across a 6-month hold. SOXL distributions over 180 days are larger than over 37 and are still ignored (V30 A7). Flatters the structure. | `[ASSUMED]` |

V30 A1–A12 carry over.

## What would make me discard the result

- A t-statistic reported on overlapping windows.
- Fewer than 5 independent cycles in the headline cell, reported as if it were a
  measurement rather than an anecdote.
- Any cycle whose payoff differs from `|S_T − K|` at expiry.
