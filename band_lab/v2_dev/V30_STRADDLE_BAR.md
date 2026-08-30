# V30 — Long ATM straddle, delta-hedged daily. Adoption bar, written before running.

This file is committed BEFORE `straddle_backtest.py` is run for the first time.
Everything below is a commitment, not a description of a result.

## The strategy under test — Tier 1 #1 from V29

1. Buy an at-the-money SOXL straddle: the strike closest to spot, the listed
   expiry whose DTE is closest to the target. Pay the **ask** on both legs.
2. Every session close, recompute the straddle's delta and trade SOXL to return
   the position to delta-neutral.
3. When the straddle's DTE falls to the roll threshold, sell both legs at the
   **bid**, close the stock hedge, and open the next straddle the same day.
4. Repeat over the whole sample. One straddle open at a time.

## The prediction being tested

V27 measured 30-day ATM implied vol at 98.6% against 110.4% realised
close-to-close over the following 30 sessions: **+11.8 volatility points**.
V28 measured the round-trip bid-ask on those options at **8.1 volatility
points**. Hedging once a day tracks close-to-close variance, so the prediction
is a **net edge near +3.7 volatility points per cycle, before commissions and
before hedge friction.**

If the strategy comes in near zero, the vol-point arithmetic was first-order and
the path-dependence ate it. If it comes in far above +3.7, something in the
simulator is wrong and I should look for it rather than celebrate.

## Prespecified parameter grid

Headline configuration, fixed now: **target 37 DTE at entry, roll at 14 DTE,
hedge once daily at the close.**

Robustness grid, all nine reported whatever they show:
- target DTE at entry: **30, 37, 45**
- roll threshold: **7, 14, 21 DTE**

No other parameter will be swept. If a parameter not on this list turns out to
matter, that is a finding to report, not a knob to turn.

## Adoption bars

| # | bar | why |
|---|---|---|
| **B1** | mean P&L per cycle > 0, **t > 2.0** | one-sided noise is the default explanation |
| **B2** | positive in **at least 4 of 5** calendar years | V27 showed 2023 was negative on vol; one bad year is expected, two is a regime dependence |
| **B3** | net of **all four** costs: option spread, option commission, hedge friction, hedge commission | the band strategy died to an unpriced cost |
| **B4** | **at least 7 of the 9** grid cells positive | a result living in one corner is a fit |
| **B5** | headline result within **1 standard error** of the grid median | the headline must not be the best cell |
| **B6** | benchmark reported via `research_kit.Result` | T23, not optional |
| **B7** | max drawdown of the cycle-return equity curve **< 35%** | a long-vol strategy bleeds; unbounded bleed is not tradeable |

**B1–B5 must all pass for this to be worth live testing.** B6 is procedural.
B7 failing alone would mean "real but not sizeable as specified."

If a bar fails I will report the failure, not reinterpret the bar.

## Assumptions, stated before they can be tuned

Each is labelled by where it comes from. `[MEASURED]` has a number behind it in
this repo. `[VENDOR]` is taken from the data files. `[ASSUMED]` is a choice I am
making with no measurement behind it — these are the ones that can be wrong.

| # | assumption | kind |
|---|---|---|
| A1 | Buy at the ask, sell at the bid. No price improvement, ever. | `[ASSUMED]` conservative |
| A2 | Option quotes, `underlying_price` and the greeks are all from the same moment (the close). | `[MEASURED]` — `bs.py` reproduces the file's IV to 0.19 vol pts, delta to 0.0002, vega to 0.1%, at r=4%, q=0 |
| A3 | The stock hedge fills at that same close price. | `[ASSUMED]` — self-consistent with A2, but a real hedge sent at 15:59 fills at a slightly different price |
| A4 | Hedge trade cost = 0.495 bp commission + 2.85 bp half-spread = **3.35 bp one way**. | `[MEASURED]` from the IBKR statement and live fills |
| A5 | Option commission **$0.65 per contract**, charged on open and close. | `[ASSUMED]` — IBKR's published retail rate. **The user's statement contains no option trades, so this is the one cost figure with nothing measured behind it.** |
| A6 | Depth is sufficient to fill the traded size at the quote. | `[VENDOR]` — measured depth is 28 bid / 30 ask contracts, so this holds for small size and fails for large |
| A7 | No dividends. SOXL distributions are ignored on the stock hedge. | `[ASSUMED]` — a short hedge pays them, so this **flatters** the strategy |
| A8 | No financing. Cash balances earn and cost nothing. | `[ASSUMED]` |
| A9 | European pricing. No early exercise. | `[ASSUMED]` — safe here: the position is long-only, so there is no assignment risk |
| A10 | If a held contract has no quote on a session, that session is skipped and the hedge is carried unchanged. | `[ASSUMED]` — the alternative is inventing a price |
| A11 | One straddle at a time, constant size, no compounding. | `[ASSUMED]` — isolates the edge from the sizing rule |
| A12 | r = 4%, q = 0 for any model-computed greek. | `[MEASURED]` — best fit of 12 combinations tested in `bs.py` |

## What would make me throw the result out rather than believe it

- A cycle P&L that beats +3.7 vol points of vega by a wide margin, unexplained.
- Any cycle whose option P&L implies a fill better than the quoted bid/ask.
- A hedge whose share count changes without the delta changing.
- Total costs that come out below `2 x spread + 4 x $0.65 + hedge friction`.

These are asserted in code as run-time checks, not read off a table afterwards.
