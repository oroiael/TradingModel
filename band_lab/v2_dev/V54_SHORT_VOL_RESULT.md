# V54 — Short vol, measured. Not adopted.

Tested against `V53_SHORT_VOL_BAR.md`, committed before the code existed.

    python3 band_lab/v2_dev/short_vol_backtest.py
    python3 band_lab/v2_dev/short_vol_backtest.py --structure strangle

1,336,996 quotes, 1,128 trade dates, 2022-01-03 → 2026-07-02. 680 straddle
cycles and 668 strangle cycles, non-overlapping, entry at the bid, early exits
at the ask, expiry settled at intrinsic, $0.65 a contract a side throughout.

## Verdict

**Not adopted. 0 of 18 grid cells positive. B1 fails on every one.**

| bar | test | straddle | strangle | |
|---|---|---|---|---|
| B1 | best-cell mean > 0, t > 2.0 | **−3.102%, t = −8.84** | **−1.600%, t = −2.69** | **FAIL** |
| B2 | positive in ≥ 4 of 5 years | **0 of 5** | **1 of 5** | **FAIL** |
| B3 | every cost charged | $1,462, 100% of cycles | $1,408, 100% | PASS |
| B4 | ≥ 7 of 9 cells positive | **0 of 9** | **0 of 9** | **FAIL** |
| B5 | headline within 1 SE of grid median | **9.51 SE** | **4.60 SE** | **FAIL** |
| B6 | max drawdown < 50% | **−729%** | **−163%** | **FAIL** |
| B7 | beat buy-and-hold on MAR | 1.00 vs **1.67** | 0.99 vs **2.23** | **FAIL** |

Every tenor, every exit rule, both structures, every calendar year but one.

## Why, in one line

**Median credit 21.0% of spot against a median cost of 22.2%.** You are paid
less than the move costs, at the median, before a cent of fee — and then the
tail arrives.

That is the negative variance risk premium V27 measured on this underlying
(realised 110-116% against implied 98.6%), showing up exactly where it should.
The screen said the short straddle nets roughly −30 volatility points and the
backtest agrees on sign and rough magnitude. **This is the first time in this
sequence that the screen and the measurement have agreed.**

## The tail is not a rounding error

6 of 680 cycles lose more than the notional the straddle controls. The worst,
verified line by line against the minute tape:

| | |
|---|---|
| entry 2026-03-30, SOXL | $40.62 |
| strike | 41.0 |
| credit collected | $14.05 |
| expiry 2026-05-15, SOXL | **$164.23** |
| intrinsic owed | $123.23 |
| **cycle return** | **−268.8%** |

SOXL rose **304% in 46 days**. No management rule in the grid survives that, and
the 50%-profit and 21-DTE exits do not help: they close winners early and leave
the losers running, which is why their means are less negative but their worst
cycles are not.

## What the exit rules did

Holding to expiry avoids the closing spread entirely and still loses most, at
−6.6% and −5.0% per cycle, because the tail is uncapped. Rolling at 21 DTE cuts
the mean loss roughly in half and multiplies the cycle count fourfold, so the
same negative expectancy is simply paid more often — its t of −8.84 is the most
statistically certain result in this whole project, and it is certain in the
wrong direction.

## What this settles

Long vol was backtested five times here and failed. Short vol has now been
backtested and failed harder, with a worse tail and a stronger t.

**Both sides of the SOXL volatility trade lose to their own transaction costs
and to a variance premium that points the wrong way for sellers.** That is the
same conclusion the screens reached, now reached by measurement, with the bar
written first.

## Known omissions, as named in V53

Early assignment is not modelled and would make the short side worse. Margin is
not modelled, so B6's drawdown is on fixed notional rather than on capital; a
compounded curve is undefined here because 0.9% of cycles lose more than the
position controls. No IV-rank gate — that was P3 and is now moot.
