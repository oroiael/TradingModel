
# V46 — Does the volatility premium scale with the volatility level? Result.

Bar: `V45_PREMIUM_SCALING_BAR.md`, written before the code.
Code: `vol_premium_scaling.py`. Both prespecified checks pass.

## Summary

**V44's favourable arithmetic was wrong, and this corrects it.** SMH's expected
edge is about **+3.7 volatility points against its 2.9 spread — net +0.8**, not
the +8.0 that V44's comparison implied. SMH survives as the only candidate in
the catalogue, by a margin too small for anything measured so far to confirm.

## The error being corrected

V44 concluded:

> "The straddle's +11.5 edge exceeds SMH's entire 2.9 spread — first favourable
> arithmetic in the project."

**That subtracts SMH's spread from SOXL's edge.** Both are quoted in volatility
points, which made them look subtractable. They are not, because these two
underlyings differ in volatility by a factor of three:

| | ann. vol, 2021-09 → 2026-08 | total return |
|---|---|---|
| SMH | **36.7%** | +310.7% |
| SOXX | 38.5% | +228.0% |
| SOXL | **114.5%** | +143.6% |

*IBKR daily closes, 1,253 sessions. Cross-checked against this repo's own
`SOXL_5min_6Years.csv`: median relative difference 0.088% on 1,224 shared dates.*

**SOXL / SOXX = 2.98×** — C2 passes. SOXL is a 3× fund on the index SOXX tracks,
and it measures 3×.

## C1 — the reimplementation reproduces V37 exactly

| | implied | realised | edge |
|---|---|---|---|
| V37 published | 99.2% | 110.2% | +10.9 |
| **this file** | **99.2%** | **110.2%** | **+10.9** |

1,125 matched dates, 2022-01-03 to 2026-06-30. Max deviation 0.05 points against
a 0.3 tolerance. The pipeline is the same one V37 used.

## The regression does NOT resolve the question

    RV = a + b · IV       additive ⇒ b = 1, a = +10.9
                          proportional ⇒ a = 0, b = 1.11

| sample | a (intercept) | b (slope) | R² |
|---|---|---|---|
| all dates (overlapping) | −2.07 | 1.131 | 0.366 |
| **non-overlapping, median of 21 offsets** | **−3.43** | **1.126** | 0.352 |
| standard error (C4, valid) | **22.19** | **0.219** | |
| range across offsets | −35.15 to +31.34 | 0.790 to 1.475 | |

- Is the slope 1 (additive)? b − 1 = +0.126, **t = +0.58. Cannot reject.**
- Is the intercept 0 (proportional)? a = −3.43, **t = −0.15. Cannot reject.**

**Neither model is rejected.** The point estimate is proportional (b = 1.13 with
an intercept indistinguishable from zero), but the intercept's standard error is
**22 volatility points** — it is not identified, because SOXL's implied vol
spans 64.4% to 192.8% and never goes near zero, so the fit has no leverage on
where the line crosses the axis. 54 independent windows cannot separate b = 1.00
from b = 1.11 when the standard error on b is 0.219.

**This is the discard condition V45 prespecified**, and it fired:

> "R² low enough that the slope is not identified … the correct answer is 'this
> data cannot resolve it' rather than a number."

## The quintile table does not resolve it either

| IV quintile | dates | implied | realised | edge pts | edge / IV |
|---|---|---|---|---|---|
| Q1 lowest | 225 | 75.7% | 89.0% | **+13.4** | 17.7% |
| Q2 | 226 | 85.4% | 90.3% | +4.8 | 5.6% |
| Q3 | 224 | 95.8% | 104.7% | +8.9 | 9.3% |
| Q4 | 225 | 107.4% | 119.3% | +11.9 | 11.1% |
| Q5 highest | 225 | 131.8% | 147.6% | **+15.8** | 12.0% |

Additive predicts a flat `edge pts` column; proportional predicts a flat
`edge / IV` column. **Neither is flat.** From Q2 to Q5 the edge rises
monotonically with the vol level, which leans proportional. Q1 breaks it — the
lowest implied vol carries the second-highest edge, which is the familiar
pattern of quiet periods immediately preceding volatility spikes, not evidence
about the functional form.

So both empirical tests lean proportional and **neither settles it.**

## What settles it: the leverage identity

SOXL's daily return is 2.98× SOXX's *by construction*. Its volatility is
therefore 2.98× SOXX's at every horizon — realised **and implied**. That is
mechanical, not statistical. Now impose an additive premium of the same +10.9
points on both:

```
IV_SOXX = 38.5 − 10.9 =  27.6%
IV_SOXL = 114.5 − 10.9 = 103.6%

but a 2.98x fund's options must price at 2.98 x the index's vol:
2.98 x 27.6 = 82.1%
```

**Those disagree by 21.5 volatility points** — exactly (leverage − 1) × 10.9. An
additive premium on both legs of a levered pair requires the market to price
SOXL volatility at **3.76×** the index's while the fund delivers **2.98×**: a
22-point relative-value gap, sitting permanently in the two most liquid
semiconductor option chains in the market.

**It does not exist. So the premium cannot be additive.** It scales with the
volatility level — which is what both empirical tests leaned toward and neither
could establish.

**This is an arbitrage argument, not a measurement from this data, and it is
labelled as such.** It is stronger than the regression precisely because it does
not depend on 54 noisy windows.

## What it implies, against each symbol's OWN spread

| symbol | realised | implied | edge | spread | **net** | clears? |
|---|---|---|---|---|---|---|
| SOXL | 114.5% | 103.1% | +11.4 | 18.5 | **−7.1** | no |
| SOXX | 38.5% | 34.6% | +3.8 | 8.0 | **−4.2** | no |
| **SMH** | 36.7% | 33.0% | **+3.7** | **2.9** | **+0.8** | **YES** |

*Proportional model, a = 0, b = 1.111 (SOXL's own realised/implied ratio). The
fitted line, whose intercept is not identified, puts SMH at −1.8 instead — that
spread between −1.8 and +0.8 is the honest remaining uncertainty.*

Three things worth stating plainly:

1. **SOXL's own deficit is confirmed at −7.1 points**, consistent with V32's −6.3
   and V31's measured −10.11%/cycle. Nothing here rescues SOXL.
2. **SOXX fails despite having SMH's volatility**, because its options cost 2.8×
   as much to trade. The spread, not the premium, is what kills it.
3. **SMH clears by +0.8 volatility points.** That is the whole finding, and it is
   thin. V32 measured a 7.2-point shortfall between end-of-day quoted spreads
   and real intraday round trips on SOXL; **an equivalent shortfall on SMH would
   erase +0.8 several times over.** It has never been measured on SMH.

## Assumption carried

**[A28]** Every SMH figure here carries SOXL's premium down to a volatility level
~28 points below anything in the fitted sample. **This is not a measurement of
SMH.** `vol_premium_ibkr.py` measures SMH itself and is what should settle it.

## What is still unmeasured, in priority order

1. **SMH's own premium.** Part B of `vol_premium_ibkr.py`.
2. **The same-moment IV ratio SOXL/SOXX.** Part A. Proportional predicts 2.98,
   additive 3.76 — a direct test of the argument above, needing no forward data.
3. **The intraday spread shortfall on SMH.** V32 measured 7.2 points on SOXL.
   If it is anywhere near that on SMH, the +0.8 is gone and the catalogue is
   empty. This is the number most likely to overturn the conclusion.
