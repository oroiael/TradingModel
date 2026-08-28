# V23 — The option backtest, every day an entry, benchmark on every path

**Status: BAR PRESPECIFIED, COMMITTED BEFORE THE HARNESS EXISTS.**

## What changed

LFS access restored. The option sample is no longer 627 days of one melt-up:

```
  1,516,524 quotes   1,128 trading days   2022-01-03 -> 2026-07-02
  intraday timestamps, bid/ask/size, full greeks, implied_vol, underlying_price

  2022   -86.6%  BEAR      2023  +235.8%  BULL     2024   -2.5%  flat
  2025   +51.7%  BULL      2026  +283.0%  BULL
  full period +151.3%, CAGR +22.8%, max drawdown -90.3%
```

V22 found that the previous study's fatal flaw was never printing the
underlying's return beside its own. Its window (2024-2026) implied a benchmark
of +86% CAGR. The honest full-sample benchmark is **+22.8%**.

## Design

**D1. Every trading day is an entry.** For each day D, start the strategy on D,
run it H days, record the outcome. ~1,000 overlapping paths, not one.

**D2. Every path carries its own benchmark.** Same start day, same horizon,
buy-and-hold SOXL. The recorded number is `strategy - benchmark`. This column is
mandatory and its absence is what V22 was about.

**D3. Report the distribution, never the mean.** Median excess, quintiles, and
the share of start dates that beat buy-and-hold.

**D4. Regime tag per window** — what the underlying did over that window, and
its realized vol. Excess return is reported within regime.

**D5. Honest error bars.** Overlapping windows are heavily correlated. Block
bootstrap over non-overlapping blocks; print effective sample size next to n.

**D6. Trade-by-trade CSVs and a `--verify` that rebuilds every summary number
from them.** Same as V21. A summary that cannot be reconstructed is not a result.

**D7. Fills.** Sell at the bid, buy at the ask — full spread crossed. The prior
study assumed 20% price improvement; that is a fill nobody is owed. A
sensitivity row at bid+0.20*spread is reported beside it, never alone.

## The bar — fixed before any number exists

**A1. The benchmark is buy-and-hold SOXL over the identical window.** Not cash,
not zero. A strategy that returns +50% while SOXL returns +150% lost.

**A2. Adoption requires beating the benchmark on BOTH return and drawdown, in
the MEDIAN path, in at least 4 of 5 calendar years.** Beating it on Sharpe or
MAR alone is reported but is not adoption — it is a statement about sizing, and
sizing down the benchmark is free.

**A3. 2022 is the test that matters.** SOXL fell 86.6% that year. Any structure
holding long exposure will lose. The question is whether it loses less than
buy-and-hold, and the 2022 row is reported first, before the totals.

**A4. If the strategy wins only in BULL windows, it is beta.** Report it as
beta, not as an edge, and say so in those words.

**A5. No parameter is tuned. One configuration, declared in advance:**
R2 / PMCC — long call 120-180 DTE at 0.75 delta, roll at <=45 DTE; short weekly
call at 0.175 delta; no defense leg; full spread crossed. This is the config the
prior study already ran, so V23 is a re-measurement against an honest benchmark
over a longer sample, not a search.

**A6. A grid may be run ONLY after the single declared config is reported, and
every grid result carries the count of configurations tried and the expected
false-positive count beside it.**

**A7. Falsification of the harness.** If buy-and-hold computed inside the
harness does not reproduce the +151.3% / +22.8% CAGR figure computed
independently from the 5-minute file, the harness is wrong and nothing it
produces counts.

---

# RESULTS

*(appended after the run)*

## VERDICT: **REJECTED under A2. It beat buy-and-hold on 11% of start dates.**

876 paths, every trading day an entry, 2022-01-03 to 2025-07-01, 252-day
horizon, full spread crossed, $0.65/contract. 88,932 trades, `--verify` OK,
**A7 PASS** (harness benchmark reproduces an independent computation to 1.8e-15).

```
  A3 — 2022 FIRST, before any total
    251 paths starting in 2022
    strategy median -55.1%   benchmark median +26.1%   excess -61.4%
    beat buy-and-hold in 0 of 251

    year  paths   strat med   bench med  excess med  win rate
    2022    251      -55.1%      +26.1%      -61.4%        0%
    2023    250       -5.8%     +120.7%     -111.7%        0%
    2024    252      -60.6%      -26.7%      -23.2%        8%
    2025    123     +316.3%     +237.2%      +38.8%       59%
     ALL    876      -23.5%      +52.9%      -40.9%       11%

  excess distribution:  p05 -193.6%   p25 -109.0%   p50 -40.9%
                        p75  -19.1%   p95  +93.2%
```

**A2: the median path beat buy-and-hold in 1 year of 4. Adoption needs 4 of 5.
Not adopted.**

**A4 fires. This is beta, and the word is required.** The only year the strategy
wins is 2025, whose paths run into the 2026 melt-up — benchmark +237.2%,
strategy +316.3%. Every window that does not contain a violent rally loses, and
loses badly: −61.4% excess in 2022, −111.7% in 2023, −23.2% in 2024. A deep-ITM
call is leveraged long exposure. When the underlying rips it beats the
underlying; the rest of the time the premium and the short-call cap eat it.

## A correction to how the year column reads

The 2022 row is not "the bear market". A 252-day window opened in 2022 mostly
closes inside the 2023 recovery, which is why its benchmark median is **+26.1%**
rather than negative. Start-year is a label for when a path *opened*, not the
regime it lived through. The smoke test on the first five January-2022 starts —
whose windows closed in early January 2023, before the bounce — showed a −83.0%
benchmark, and that is the genuinely bearish slice.

The design flaw is mine: D4 asked for a regime tag on the window and the run
tags by start year instead. It does not change the verdict — 11% of 876 starts
is not a near miss — but any future run should tag windows by what the
underlying actually did over them.

## What this settles

The prior study reported R2/PMCC at **+257.3%** and called it the second-best
recommendation. That number came from one start date inside a +383% window. Run
from 876 start dates across a sample that includes a bear year, the same
structure loses to simply owning the shares on 89% of them.

The difference is not the fill model, the roll rules, or the deltas. It is the
benchmark column, exactly as V22 said.
