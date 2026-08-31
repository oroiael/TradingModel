# V34 — The unhedged straddle (V29 Tier 1 #2). Result.

Tested against `V33_UNHEDGED_BAR.md`, committed before the code existed.

    python3 band_lab/v2_dev/straddle_backtest.py --v33

## Verdict

**Not adopted. B1, B4 and B5 all fail.**

| bar | test | result | |
|---|---|---|---|
| B1 | mean return/cycle > 0, t > 2.0 | **+14.40%, t = +0.94** | **FAIL** |
| B3 | every cost charged on the taken exit path | yes | PASS |
| B4 | ≥ 5 of 6 unhedged cells positive | **1 of 6** | **FAIL** |
| B5 | headline within 1 se of grid median | **median −5.00%** | **FAIL** |
| B7 | max drawdown < 35% | −18% | PASS |

**B5 is the one that matters.** The headline cell prints +14.40% while its two
siblings print −1.54% and −13.53%. A 27-point spread across three adjacent entry
DTEs is not a finding, it is an outlier, and B5 exists to say so before the
number gets quoted.

## But it is by far the best result in this line of work

At the V32-measured spread, mean return per cycle averaged across entry DTEs:

| | return/cycle | |
|---|---|---|
| hedged daily, rolled at 14 DTE | **−10.88%** | V31/V32's arm |
| unhedged, rolled at 14 DTE | −6.86% | |
| **unhedged, held to expiry** | **−0.22%** | pays the entry half-spread only |

Dropping the hedge *and* holding to expiry moves the strategy from −10.88% to
**−0.22% per cycle** — from a decisive loser to roughly break-even. It still
does not make money, and −0.22% is not an edge, but the gap closed is 10.7
percentage points.

## Why — and V33 required this to be visible in advance

| | percentage points |
|---|---|
| worth of **not paying the exit spread** | **+6.65** |
| worth of **removing the hedge** | +4.01 |

**The spread is the bigger term, by 1.7×.** V33 said before running: *"If #2
beats #1, it is because of the spread, not because of the edge. That distinction
has to be visible in the output or the result is not interpretable."* It is
visible, and it is the spread.

That is consistent with everything since V28. The volatility edge on SOXL is
real and was predicted to within 0.3 vol points. **The cost of collecting it is
the entire problem**, and the single most effective change available is to stop
crossing the option spread twice.

## The full grid, both spread regimes

| hedge | exit | entry | cycles | vendor EOD | **measured spread** | t |
|---|---|---|---|---|---|---|
| none | expiry | 30 | 58 | +2.14% | −1.54% | −0.13 |
| **none** | **expiry** | **37** | **46** | **+18.06%** | **+14.40%** | **+0.94** |
| none | expiry | 45 | 39 | −9.91% | −13.53% | −0.97 |
| none | roll | 30 | 113 | −1.33% | −8.47% | −1.79 |
| none | roll | 37 | 77 | −4.78% | −11.96% | −2.21 |
| none | roll | 45 | 57 | +7.02% | −0.17% | −0.01 |
| daily | roll | 30 | 113 | −4.06% | −11.20% | −4.66 |
| daily | roll | 37 | 77 | −2.94% | −10.11% | −3.76 |
| daily | roll | 45 | 57 | −4.13% | −11.32% | −3.67 |

The measured-spread column moves each expiry cell by ~3.7 points and each roll
cell by ~7.2, exactly as it should: **the V32 shortfall is a round trip, and a
cycle held to expiry crosses once.** Charging the full amount to a position that
never sells would have invented a cost that cannot occur, which V33 called out
in advance.

## What removing the hedge costs you

V31 measured cycle return correlating **+0.85** with realised-minus-implied. The
hedge is the machinery that converts that correlation into money. Without it the
position is a bet on one endpoint:

| | standard error per cycle |
|---|---|
| hedged, 37/roll | **2.69%** |
| unhedged, 37/expiry | **15.36%** |

**5.7× the noise.** That is why a +14.40% mean carries t = 0.94 while a −10.11%
mean carries t = −3.76. The unhedged version cannot be shown to work or fail on
46 cycles; it would need roughly 30× the sample to resolve an effect this size.

## Three bugs found building this, one of which invalidates an earlier claim

**The expiry exit required a 0-DTE quote.** The chain almost never carries one:
801 of 816 cycles were abandoned, and the 15 that survived were the biased
subsample where an expiry-day quote happened to exist — printing −96.43% per
cycle. Held to expiry no quote is needed at all; the option settles at intrinsic
against the underlying's own close.

**The roll exit was not gated on the exit mode**, so it fired first at 14 DTE and
the expiry path never ran.

**`pd.Timestamp(expiry)` returned 1970-01-20 for every contract.** The
`expiration` column is `datetime64[us]`, so `.astype("int64")` yields
*microseconds* while `pd.Timestamp` reads a bare int as *nanoseconds*.

> **This is the same defect V31's correction C5 claimed to have fixed.** C5 said
> "the trace printed it as a date without conversion. Display only." The change
> moved the call site and left the conversion wrong, so the `expiry` column in
> `V30_straddle_cycles.csv` has been 1970 the entire time. Nothing read it and no
> published number moves — but **C5 was a false "fixed" in the record** and is
> corrected here rather than quietly repaired.

Also: every run wrote `V30_straddle_cycles.csv` regardless of configuration, so a
`--hedge none` smoke test silently replaced V31/V32's committed headline artifact
with unhedged data. Filenames are now mode-aware and the clobbered files were
restored from git.

## Where this leaves Tier 1

| | status |
|---|---|
| #1 daily-hedged straddle | **rejected** — V31/V32, −10.11%/cycle at t = −3.76 |
| #2 unhedged straddle | **not adopted** — B1, B4, B5 fail; but −0.22%/cycle |
| #3 call backspread | not yet tested |

**#2 is not a strategy, but it is a finding about cost structure.** Anything
built from here should cross the option spread as few times as possible — hold
to expiry rather than roll, and let the ITM leg exercise rather than sell it.
That single choice is worth 6.65 percentage points a cycle, more than the hedge
and more than any parameter swept so far.
