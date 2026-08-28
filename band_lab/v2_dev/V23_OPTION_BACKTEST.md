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
