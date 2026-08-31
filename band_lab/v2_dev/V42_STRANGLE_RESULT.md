# V42 — Asymmetric strangle (V29 Tier 2 #7). Result: **not adopted.**

Tested against `V41_STRANGLE_BAR.md`, committed before the code existed.

    python3 band_lab/v2_dev/straddle_backtest.py --v41

## Verdict

**B1b fails 0 of 6.** At the measured spread the strangle loses to the straddle
in every cell.

| hedge | call δ | straddle | strangle | difference | B1b |
|---|---|---|---|---|---|
| daily | 0.20 | −10.22% | −11.40% | **−1.19%** | FAIL |
| daily | 0.25 | −10.22% | −10.95% | **−0.73%** | FAIL |
| daily | 0.30 | −10.22% | −10.50% | **−0.28%** | FAIL |
| none | 0.20 | −12.06% | −21.92% | **−9.86%** | FAIL |
| none | 0.25 | −12.06% | −18.79% | **−6.73%** | FAIL |
| none | 0.30 | −12.06% | −21.54% | **−9.48%** | FAIL |

## The screen was right, and this is the cleanest confirmation in the series

V41 predicted **+0.94 volatility points** of structural advantage, worth roughly
**+0.94% per cycle** on V32's conversion. At the vendor spread, hedged:

| call δ | straddle | strangle | difference |
|---|---|---|---|
| 0.20 | −2.94% | −2.81% | **+0.13%** |
| 0.25 | −2.94% | −2.39% | **+0.55%** |
| 0.30 | −2.94% | −1.98% | **+0.96%** |

**+0.96% at the widest call, against a predicted +0.94%.** Monotone in call
delta, as the skew argument requires: the wider the call, the cheaper the vol
bought, the larger the advantage. The mechanism V29 proposed is real and it
behaves exactly as the arithmetic said it would.

**It is also far too small.** V32 put the straddle's deficit at −6.3 vol points.
An advantage of +0.94 closes 15% of it, and the structure still loses.

## Why the sign flips once the real spread is charged

At the vendor spread the strangle wins by +0.13 to +0.96. Charging V32's measured
shortfall flips every cell to −0.28 to −1.19.

The shortfall is charged in proportion to **vega**, while the return is measured
against **premium**. The strangle has **more vega per dollar of premium** than
the straddle — vega 8.14 against 9.16, but a materially cheaper premium, because
one leg is out of the money. So a vol-point-denominated cost lands harder on it
as a percentage of the capital at risk.

**A structure that looks cheaper because it costs less to buy is not cheaper if
its costs scale with vega and its returns scale with premium.** That is a general
point about comparing option structures and it is the useful thing this test
produced.

## Unhedged, it is not a volatility structure at all

Losses of −6.73% to −9.86% per cycle against the straddle. V41 named this in
advance: **net delta −0.25** into a fund that rose **152.8%** over the sample.
That is a directional loss with nothing to do with skew, and it is why the
hedged column is the only fair test of the claim.

## The structure comparison, which outlives the verdict

| structure | vega-wtd IV | spread (vol pts) | net delta |
|---|---|---|---|
| straddle (ATM + ATM) | 97.31% | 13.9 | −0.00 |
| symmetric strangle (25d + 25d) | 99.97% | **10.6** | +0.00 |
| asymmetric (ATM put + 25d call) | **96.07%** | 14.1 | −0.25 |

The wing skew is **+12.35 vol points** (25d put 106.2% vs 25d call 93.8%), larger
than the 11.6 V29 cited from a pooled median. And yet **all three structures land
within one volatility point of each other** once spread is netted against implied
vol. The symmetric strangle is the cheapest to trade and buys the priciest vol;
the asymmetric one is the dearest to trade and buys the cheapest vol. **A large
skew and large spread differences, offsetting.**

## Two imprecisions in this run, disclosed

1. **A27 was applied uniformly.** The bar said the strangle's shortfall should be
   scaled 14.1/13.9 relative to the straddle's 7.2; the code set one global value
   and charged both 7.30. The straddle is therefore shown ~0.11 points worse than
   it should be, which would widen every headline difference to about −0.39 to
   −1.30. **No cell changes sign** and the verdict is unaffected.
2. **The output carried a `net delta` column that was never populated** — a
   header promising a number the code did not compute. Removed rather than left
   as an empty column that reads like a measured zero.

## Where the catalogue stands

| | verdict | on what |
|---|---|---|
| #1 straddle, hedged daily at the close | **rejected** | −10.11%/cycle, t = −3.76 |
| #2 straddle, unhedged | **not adopted** | −0.22%/cycle, one outlier cell |
| #3 call backspread | **not adopted** | −5.46% trimmed, three cycles carried it |
| #4 long-dated straddle | **inconclusive** | CI [−50%, +189%] on 9 cycles |
| #6 hedge at the open | **not adopted** | −1.03 pp/cycle vs #1, 0 of 3 |
| **#7 asymmetric strangle** | **not adopted** | −0.73 pp/cycle vs #1, 0 of 6 |

**Five structures resolved, all against. One unresolvable on this data.**

Only **#5** remains — long both SOXL and SOXS, unrebalanced — and it needs the
same purchased pre-2022 history that #4 does, for the same reason: its mean rests
on a handful of large moves and 4.49 years does not contain enough of them.

## The one sentence this whole catalogue supports

Every structure tested buys the same volatility edge, and every one of them pays
more than the edge is worth to get it. The edge is real, was predicted to within
0.3 volatility points, and is smaller than the bid-ask spread on the instruments
required to collect it.
