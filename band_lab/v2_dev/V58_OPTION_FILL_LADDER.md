# V58 — The option fill ladder. The last assumption, varied at last.

Every option result in this project — V22 through V57, roughly 1,400 priced
configurations — charges the same fill: sell at the bid, buy at the ask, cross
the whole quote, every leg, every time. That assumption was never varied once.

On the equity side it was varied, exactly once, in `V26_FILL_LADDER.md`, and the
six conventions there spanned **+122.57 to −14.46 bp per day** — a range wider
than any parameter in the grid. This runs the same experiment on the options.

    python3 band_lab/v2_dev/option_fill_ladder.py
    python3 band_lab/v2_dev/short_vol_backtest.py  --side long --fill 0.0
    python3 band_lab/v2_dev/credit_spread_backtest.py --fill 0.0

## Verdict

**Nothing becomes adoptable at any achievable fill.** The short straddle needs a
fill *better than the mid* before its best cell even turns positive; the credit
spreads never clear the bar at any rung including the impossible one; and the
long straddle — the nearest miss — needs to be filled **beyond the mid, on the
far side, on every leg** before it reaches t > 2.0, and fails B5 even there.

But the ladder answers a second question that matters more than the verdict, and
it answers it cleanly. See "the joint" below.

## The dial, and the regression that proves nothing else changed

One parameter, `k`, the number of half-spreads a fill gives up against the mid:

    sell = mid − k · half_spread            buy = mid + k · half_spread

snapped to a whole tick measured **from the touch** — $0.01 under $3.00, $0.05
at or above it. That regime was measured on the file, not assumed: below a
$3.00 mid, 100% of bids sit on the penny grid and only 20% on the nickel; at or
above it, 99.4% of bids and 100% of asks sit on the nickel grid.

Snapping from the touch rather than an absolute grid has two consequences:

- **k = 1.0 returns the touch exactly**, for every quote, including awkward ones
  like 2.98/3.10 that an absolute-grid snap would move. That is what makes the
  regression exact rather than approximate.
- **A market one tick wide has nothing inside it.** At k = 0 on a 3.85/3.90
  quote the fill is 3.85 — the bid. You cannot rest an order inside a one-tick
  market and the model does not pretend you can.

At k = 1.0 the refactored code reproduces all three published grids to
**machine zero** — max |Δmean| = 0.00e+00 and identical cycle counts against
V54 (short straddle), V57 (long straddle) and V56 (credit spreads). The ledger
CSVs come back byte-identical under `git diff --quiet`. So every difference
below is the fill convention and nothing else.

## What each rung actually buys

Measured on the **6,068 straddle legs the structures actually select**, not on
every quote in the tenor window — averaging the window would be dominated by
deep in-the-money strikes with dollar-wide markets that nothing here trades.

Mean half-spread on those legs 30.6c, median 7.5c, mean mid $4.96; the median
half-spread is **2.7% of the option's own mid**.

| rung | k | improvement/leg | of the half-spread |
|---|---|---|---|
| **A CEILING** — every fill at the far touch (impossible) | −1.00 | +61.19c | 200% |
| B mid on both sides | 0.00 | +29.89c | **92%** |
| C 30% of a half-spread off the mid | +0.30 | +20.07c | 55% |
| D 20% of the spread inside each touch (the V22 convention) | +0.60 | +11.00c | 26% |
| **E PUBLISHED** — cross the whole quote (V54/V56/V57) | +1.00 | 0.00c | 0% |
| F cross, plus a tick of slippage | +1.30 | −10.63c | −47% |

The dial is coarse, and honestly so: k = 0 delivers 92% of the half-spread
rather than 100%, and k = 0.30 delivers 55% rather than 70%, because ticks are
discrete and a narrow market has nothing inside it. **The nominal k is not what
the trader gets.**

## The ladder — best cell in each grid, per cycle

`band` is where the row sits between the published cross (0%) and the ceiling
(100%), the same convention as V26.

### Short straddle — ceiling +1.07%, published −3.10%

| rung | k | best cell | t | positive | median | band |
|---|---|---|---|---|---|---|
| A | −1.00 | **+1.07%** | 3.19 | 2/9 | −3.46% | 100% |
| B | 0.00 | −1.09% | −3.38 | **0/9** | −4.99% | 48% |
| C | +0.30 | −1.78% | −5.45 | 0/9 | −5.48% | 32% |
| D | +0.60 | −2.41% | −7.21 | 0/9 | −5.91% | 17% |
| E | +1.00 | −3.10% | −8.84 | 0/9 | −6.44% | 0% |
| F | +1.30 | −3.90% | −10.58 | 0/9 | −6.93% | −19% |

**Fill quality was never what killed the short straddle.** Hand the trader the
entire spread as a gift on every leg of every fill — the impossible rung A — and
7 of 9 cells are still negative. V54's verdict is robust to execution.

### Long straddle — ceiling +16.51%, published +14.40%

| rung | k | best cell | t | positive | median | band |
|---|---|---|---|---|---|---|
| A | −1.00 | +16.51% | **2.09** | 9/9 | +6.32% | 100% |
| B | 0.00 | +15.40% | 1.96 | 8/9 | +3.48% | 47% |
| C | +0.30 | +15.02% | 1.92 | 8/9 | +2.17% | 29% |
| D | +0.60 | +14.70% | 1.88 | 7/9 | +2.64% | 14% |
| E | +1.00 | +14.40% | 1.84 | 6/9 | +2.93% | 0% |
| F | +1.30 | +13.94% | 1.79 | 5/9 | +1.04% | −22% |

The long side barely moves: 14.40% to 16.51% across the whole band, 2.1 points
on a 15-point number. It holds to expiry, so it pays **one** spread, on the
entry only — half the exposure of anything managed. The t-statistic crawls from
1.79 to 2.09 and the count of positive cells is the only thing that really
responds, 5/9 to 9/9.

### Credit spreads — ceiling +97.57%, published −1.56%

| rung | k | best cell | t | positive | median | band |
|---|---|---|---|---|---|---|
| A | −1.00 | +97.57% | **1.24** | 21/27 | +9.78% | 100% |
| B | 0.00 | +6.39% | 1.29 | 5/27 | −3.34% | 8% |
| C | +0.30 | +1.99% | 0.37 | 3/27 | −6.01% | 4% |
| D | +0.60 | +0.16% | 0.04 | 1/27 | −7.41% | 2% |
| E | +1.00 | −1.56% | −0.16 | 0/27 | −9.48% | 0% |
| F | +1.30 | −3.18% | −0.34 | 0/27 | −11.54% | −2% |

Four legs means four spreads to open and four to close, so this is the structure
most sensitive to the rung — and it is the only one where **not even the
impossible ceiling clears B1**, at t = 1.24 on 21 of 27 cells positive.

The ceiling's +97.57% is not a denominator artifact — credit/width only moves
from 19% to 25% across the whole ladder, so max loss does not collapse. It is
plain arithmetic on four legs of gifted spread, compounded by a take-profit that
fires 2.4× as often (n = 144 at the ceiling against 61 at the published rung).

## The joint — what the ladder actually establishes

V57 found that the short and long straddle **sum to the spread rather than to
zero**: −2.40% at the expiry exit (one spread paid) and −5.05% at roll-21 (two),
a ratio of 2.11×. Run that same cut at every rung:

| k | expiry (1 spread) | roll21 (2 spreads) | ratio |
|---|---|---|---|
| −1.00 ceiling | **+2.17%** | **+4.62%** | 2.13× |
| **0.00 mid** | **−0.20%** | **−0.38%** | 1.91× |
| +0.30 | −0.98% | −2.01% | 2.05× |
| +0.60 | −1.65% | −3.44% | 2.08× |
| +1.00 published | −2.40% | −5.05% | 2.11× |
| +1.30 | −3.28% | −6.90% | 2.11× |

Three things fall out of this table, and they are the point of the exercise.

**1. At the mid the joint loss vanishes.** −0.20% and −0.38% against −2.40% and
−5.05%. What is left is commissions plus the 8% of the half-spread that tick
snapping refuses to give back. The entire joint loss in V57 was the spread. Not
mostly — essentially all of it.

**2. The ratio holds at 1.91–2.13× at every single rung.** The joint loss is
proportional to the *number of spreads crossed*, at every fill convention, over
a range of 5.4 points at the expiry exit and 11.5 at roll-21. Two spreads cost
twice one spread whatever the price. That is as clean a confirmation as this
data can produce that the cost term is the spread and nothing else is hiding
in it.

**3. Above the mid the joint turns positive.** +2.17% and +4.62% at the ceiling,
because there you *collect* the spread on both sides instead of paying it. The
sign of the joint is the sign of who crosses. Direction never enters.

## Where the break-even actually is — measured, not interpolated

| structure | first rung its best cell is positive | first rung it clears B1 (t > 2.0) |
|---|---|---|
| short straddle | k = −0.60 (146% of the half-spread) | k = −1.00, the ceiling |
| long straddle | positive at every rung tested | **k = −0.40** (125%) |
| credit spread | k = +0.60 (26%) | **never — not even at the ceiling** |

Only the credit spread's positive-cell threshold, k = +0.60, sits inside the
quote where an order can actually rest. Every other entry in that table is at
k < 0, which is **not merely optimistic — it does not exist**. You cannot sell
above the ask.

And the one B1 pass that is nearly reachable does not survive the rest of the
bar. The long straddle at k = −0.40:

    46-60d expiry   +15.75%   t = 2.00   n = 27   win 56%   maxDD −42%
    grid median +3.84%, SE 7.86%  ->  the best cell sits 1.52 SE above the
    median, so B5 FAILS

B5 exists precisely to catch a headline picked from nine cells. It fails at
**every rung on every structure** except the two rungs where the credit spread's
whole grid is so uniformly negative that its best cell is indistinguishable from
its median — which is a pass on a technicality, not a result.

## What this does not model

**An order resting inside the spread may never fill.** Nothing here models the
unfilled case: every cycle is assumed to trade at its rung's price. Fill
probability falls as k falls, and at k = 0 a resting order needs the market to
come to it — which, on a straddle, it does exactly when the trade is going
against you. Adverse selection is unmodelled and it moves the wrong way.

So no row below k = 1.0 is a strategy. The ladder answers **"how good would
execution have to be?"** and the answer is "better than possible" for two of the
three structures and "impossible" for the third.

Two further caveats, stated because they are real:

- **The rung changes the sample, not only the prices.** The entry premium screen
  and the take-profit trigger both read filled prices, so cycle counts move with
  k — credit spreads run 2,328 cycles at the ceiling and 1,748 at the published
  rung. The expiry column is the clean comparison: only the entry leg is
  repriced there, so its sample is nearly fixed.
- **The tick regime is applied from the quote's mid.** A quote straddling $3.00
  could be assigned the wrong grid. This cannot affect k = 1.0, which returns
  the touch by construction, and moves intermediate rungs by at most one tick.

## What it changes

| | before V58 | after V58 |
|---|---|---|
| V54 short straddle rejected | on crossed-spread costs | on the trade itself — 7 of 9 cells still lose at the impossible ceiling |
| V56 credit spreads rejected | 0 of 27 cells | never clears B1 at any fill, ceiling included |
| V57 "the sides sum to the spread" | one measurement at one convention | holds at 1.91–2.13× across six conventions and an 8.7-point range |
| the fill assumption itself | untested on options | **tested; ceiling to published is worth 4.6 points of joint P&L at the expiry exit and 9.7 at roll-21, and it rescues nothing** |

## One incidental fix

`credit_spread_backtest.py` shipped in V56 with a usage line advertising
`--structure condor`. That flag does not exist — the script loops over all three
structures internally — so the documented command errors out. It has been
replaced with the `--fill` example. No result changes; the flag was never
parsed, so nothing was ever run with it.

## Closing

The equity ladder in V26 found the published convention sitting at 63% of its
band and an edge that straddled zero on the fill convention alone. The option
ladder finds the opposite: the published convention is the honest end of the
band, and no structure here is close enough to zero for the convention to be
what decides it.
