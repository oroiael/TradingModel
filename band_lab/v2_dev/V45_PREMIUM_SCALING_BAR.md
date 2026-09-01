
# V45 — Does the volatility premium scale with the volatility LEVEL? Bar, before the code.

## Why this exists: a mistake in V44

V44 ended on the first favourable arithmetic in the project:

> "Gross volatility edge +11.5. Option round trip: SMH 2.9, SOXX 8.0, SOXL 18.5,
> SOXS 37.6. **The straddle's +11.5 edge exceeds SMH's entire 2.9 spread.**"

**That sentence compares SOXL's edge against SMH's spread.** Both are quoted in
volatility points, which made them look subtractable. They are not, because a
volatility point is not the same quantity of money on two underlyings with
different volatility levels — and these two differ by a factor of three:

| | annualised vol, 2021-09 → 2026-08 | source |
|---|---|---|
| SMH | **36.7%** | IBKR daily closes, 1,253 bars |
| SOXX | 38.5% | same |
| SOXL | **114.5%** | same |

**SOXL / SOXX = 2.97×.** SOXL is a 3× fund on the ICE Semiconductor index, which
is what SOXX tracks, so this is the leverage doing exactly what it says.

So the SMH comparison in V44 is not evidence, and the honest version of the
question is: **what is SMH's OWN edge?** Nobody has measured it. But before
spending an IBKR session on it, there is a prior question that decides how to
read the answer, and it is answerable offline from data already in this repo.

## The question

V37 measured SOXL at one month: implied 99.2%, realised 110.2%, **edge +10.9
volatility points**. Carry that to an underlying with a third of the volatility.
Two models give answers that differ by a factor of three:

| model | form | SMH edge implied | vs SMH's 2.9 spread |
|---|---|---|---|
| **additive** — the premium is a fixed number of vol points | RV = IV + 10.9 | **+10.9** | clears by 8.0. Comfortable. |
| **proportional** — the premium is a fixed *fraction* | RV = 1.11 × IV | **≈ +3.5** | clears by 0.6. Marginal. |

V44 assumed additive without saying so. **Which one is true decides whether SMH
is a strategy or a rounding error**, and it is testable inside SOXL's own data:
SOXL's implied vol is not constant across the sample, so regressing forward
realised vol on implied vol separates the two.

    RV = a + b · IV

    additive      →  b ≈ 1,   a ≈ +10.9 points
    proportional  →  a ≈ 0,   b ≈ 1.11

## The prediction

**Proportional, or close to it: b > 1 and an intercept not distinguishable from
zero.** Implied and realised volatility are both scale parameters of the same
return distribution; a premium that stayed at 10.9 points whether vol was 60% or
200% would be a fixed charge unrelated to the size of the risk being transferred,
which is not how risk premia behave.

**If that is right, SMH's edge is about +3.5 points against a 2.9 spread, and
V44's favourable arithmetic mostly evaporates** — net +0.6 vol points per cycle,
inside the error bars, before any of the shortfalls V32 measured on the exit.

I am predicting against the result I want. That is the point of writing it first.

## Method

1. **SOXL premium, V37's exact 1-month method** — ATM implied vol (22–45 DTE,
   within 7% of spot, per-date median) against the next 21 sessions of
   close-to-close realised vol from 1-minute bars.
2. **Regress** forward RV on IV. Point estimate on all dates; standard errors on
   **non-overlapping** windows only, and the slope re-estimated at all 21
   possible offsets so the choice of offset is visible rather than hidden.
3. **Quintile table** by IV level — edge in points and edge as a fraction of IV.
   If the premium is additive the points column is flat; if proportional the
   fraction column is flat. This is the same question asked without a functional
   form, as a check on the regression.
4. **Extrapolate** to SMH and SOXX under the fitted relationship, and compare
   each to its OWN V43-measured spread.

## Adoption bars

This is a measurement, not a strategy, so the bars are about whether the
measurement is believable rather than whether something is adopted.

| # | bar | note |
|---|---|---|
| **C1** | the 1-month cell must reproduce V37: implied 99.2%, realised 110.2%, edge +10.9, within 0.3 points | same data and same method, so anything else means the reimplementation is wrong |
| **C2** | SOXL/SOXX realised vol ratio in **2.85–3.15** | a 3× fund that does not measure 3× means the price data is wrong |
| **C3** | the IV range spanned by the sample must be **reported**, and the extrapolation distance to SMH's ~33% stated in the same breath as any SMH number | |
| **C4** | slope standard errors on **non-overlapping** windows | 1,100 overlapping 21-day windows are ~53 observations |

## What would make me discard the result

- A slope so far above 1 that the fitted line implies negative implied vol
  anywhere inside the observed range — that is a sign the regression is fitting
  noise in a narrow IV band and extrapolating nonsense.
- The quintile table and the regression disagreeing about which model holds.
  They are the same question asked two ways; if they part company, neither is
  reportable.
- **R² low enough that the slope is not identified.** If IV barely moves in this
  sample, the regression cannot separate the two models at all, and the correct
  answer is "this data cannot resolve it" rather than a number.

## Assumption

| # | assumption | kind |
|---|---|---|
| A28 | The IV/RV relationship fitted on SOXL, at implied vols around 60–200%, extends down to SMH's ~33%. **This is an extrapolation well outside the fitted range and is the weakest link in the whole chain.** It is stated here so the SMH figure is never quoted without it. The direct measurement of SMH's own implied vol supersedes this entirely and is what `vol_premium_ibkr.py` exists to get. | `[ASSUMED]` |
