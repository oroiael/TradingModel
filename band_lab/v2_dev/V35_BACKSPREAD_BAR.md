# V35 — Call backspread (V29 Tier 1 #3). Bar, written before the code.

Buy **2× 25-delta call**, sell **1× ATM call**, same expiry. Net long one option,
part financed by the short leg. Committed before `straddle_backtest.py` learns
the structure.

## Two corrections to V29's case, measured first

V29 argued for #3 on skew: *"the 25-delta call trades at 94.2% while ATM is
95.0% — you are buying vol 0.8 points cheaper than the vol you sell."* That came
from a pooled median across all quotes. Paired **per trade date**, which is how a
structure actually trades, over 1,125 dates:

| | V29 cited | **measured per date** |
|---|---|---|
| ATM call IV | 95.0% | 96.7% |
| 25-delta call IV | 94.2% | 93.8% |
| **skew (25d − ATM)** | **−0.8** | **−2.92 vol pts** (median −3.95) |
| dates the 25d call is cheaper | — | **81%** |

**The skew is 3.6× better than V29 claimed.** That is the correction in the
structure's favour.

## And the arithmetic that kills it anyway

| | |
|---|---|
| strike width K2 − K1 | $9.16 |
| net debit at mid | **−$1.00** (a credit) |
| max loss per share | $8.16 |
| **gross spread, 3 legs** | **$1.67** |
| net vega (2×25d − ATM) | +2.557 per 1.00 vol |
| spread as % of max loss | 19.6% |

The skew edge is worth `2.92 vol pts × 2.557 net vega ÷ 100 = **$0.075/share**`.
The entry spread is **$1.67/share**. **The spread is 22× the skew edge.**

### The structural reason, stated in the unit that has settled everything else

Converting each structure's entry spread into volatility points of its own net
vega:

| | spread | net vega | **spread in vol points of net vega** |
|---|---|---|---|
| ATM straddle (V32, measured live) | $5.00 | 26.97 | **18.5** |
| **call backspread** | $1.67 | 2.557 | **65.3** |

**The backspread pays 3.5× the straddle's spread per unit of volatility
exposure.** Against a gross edge measured at +11.5 vol points (V31), it is
underwater by roughly 5.5×.

The cause is structural and worth naming: **selling an option to finance a long
volatility position cancels most of the vega you are paying for, but none of the
spread you pay to sell it.** The short ATM leg removes 13.5 of vega and costs
$2.90 of spread. That is the whole trade.

## The prediction

**#3 loses, and by more than #1 or #2.** If the backtest disagrees by a wide
margin, the simulator is wrong and I will look for the bug rather than report the
result — the same rule V30 set and V31's C7 justified.

The 5.5× shortfall is well outside the 2.3× optimism the vol-point arithmetic has
historically shown against realised P&L (V31: predicted +$787, actual +$347), so
the screen is not close enough to the line for that error to rescue it.

**This bar is written knowing the answer is probably no.** It is run anyway
because a screen is not a result — V29's own skew figure was wrong by 3.6× and
only measuring caught it.

## Prespecified grid

Headline: **long 25-delta, 2:1 ratio, enter nearest 37 DTE, hold to expiry.**

- long-leg delta: **0.20, 0.25, 0.30** — 3
- exit: **hold to expiry**, **roll at 14 DTE** — 2

Six cells. Ratio fixed at 2:1 as V29 specified. Exit-at-expiry is the headline
because V34 measured not crossing the exit spread as worth +6.65 points a cycle,
the largest single effect found in this line of work.

## Adoption bars

| # | bar | note |
|---|---|---|
| **B1** | mean return per cycle > 0 with **t > 2.0** | on return over MAX LOSS |
| **B2** | positive in **≥ 4 of 5** calendar years | |
| **B3** | every cost charged: 3-leg entry spread, 3 commissions, assignment and exercise at expiry | |
| **B4** | **≥ 5 of 6** cells positive | |
| **B5** | headline within **1 standard error** of the grid median | caught V34's outlier |
| **B6** | benchmark via `research_kit.Result` | |
| **B7** | max drawdown **< 35%** | |

## The denominator, chosen before seeing results

**Return is measured against MAX LOSS**, `(K2 − K1) × 100 + net debit`, not
against premium. A backspread is partly financed, so its net premium is near zero
and sometimes a credit — dividing by it produces infinities and sign flips. Max
loss is also approximately the margin the broker holds, so it is the capital
actually committed.

## New assumptions this test introduces

| # | assumption | kind |
|---|---|---|
| A18 | **The short ATM call can be assigned early.** SOXL pays distributions, and an American call is assignable at any time. The backtest does not model early assignment; it assumes the short survives to expiry. This **flatters** the structure. | `[ASSUMED]` — and unlike V30 A9, assignment risk here is real, because there is a short leg |
| A19 | At expiry the position settles at intrinsic: `2·max(S−K2,0) − max(S−K1,0)`. Any ITM leg exercises or is assigned into stock, liquidated at the measured 6.70 bp. | `[ASSUMED]` mechanics, `[MEASURED]` cost |
| A20 | Margin equals max loss. Reg-T on the embedded short call spread is `(K2−K1)×100`; portfolio margin would be less. Not looked up. | `[ASSUMED]` |
| A21 | The V32 measured spread shortfall (7.2 vol pts round trip on an ATM straddle) applies **per leg scaled by that leg's vega**. The OTM legs' shortfall has **not been measured** and out-of-the-money option spreads are typically wider in vol terms, so this likely **understates** the cost. | `[ASSUMED]` |

V30 A1–A12 carry over. A9 (no assignment risk) is **void** — see A18.

## What would make me discard the result

- Any cycle whose expiry payoff differs from `2·max(S−K2,0) − max(S−K1,0)`.
- A cycle where the short strike is not below both long strikes.
- Entry cost below `2×(ask of long) − (bid of short) + 3 commissions`.
- A positive result. Not because positives are forbidden, but because the screen
  above says it should lose by 5.5×, and a positive would mean the simulator is
  crediting something the arithmetic says is not there. It would be investigated
  before it was believed.
