# V22 — Audit of the options study, against the benchmark it never used

**Status: AUDIT COMPLETE. No new strategy proposed.**

The band strategy died because a simulator booked fills nobody could get. Before
building anything on `STRATEGY_RECOMMENDATIONS.md`, the same scrutiny had to be
applied to it. This is that pass.

## 1. The fill rule — optimistic, disclosed, not the problem

`volatility_pricing_lab.py:36-38`:

```
sell  = bid + 0.20 * (ask - bid)
buy   = ask - 0.20 * (ask - bid)
```

Every fill is assumed to land 20% inside the spread. That is a patient-limit
assumption and it is not free: an order priced inside the spread may never fill,
and nothing here models the unfilled case or the cost of chasing.

But it is **bounded and stated**. The lab prints its own friction —
"round-trip friction at the 20% rule is 0.6 x spread%; a 14% spread costs ~8.4%
of premium round trip" — and F9 reports the spread surface honestly (12-16% of
mid at 20-40 delta weekly, 66% at 0-10 delta). Crossing the full spread instead
would cost 1.0x rather than 0.6x, a difference of ~5.6% of premium.

**This is not the same class of defect as the same-minute re-buy.** That one
booked a price that had already traded. This one books a plausible price that
might not fill. Worth tightening; not fatal.

`qa_wealth_recon: PASS` on every row of every grid. The accounting reconciles.

## 2. The finding that matters: nothing was measured against the underlying

SOXL over the identical 131-week window, from the same 5-minute file:

```
  2024-01-02   28.01     ->   2026-07-17   135.29
  +383.0% total    +86.0% CAGR    max drawdown -88.0%    vol 120.8%
```

Against that:

| strategy | total | CAGR | max DD | vs buy-and-hold |
|---|---|---|---|---|
| **R1 put diagonal** (the top recommendation) | **-65.0%** | -34.1% | -65.1% | **-448 points** |
| **R2 call diagonal / PMCC** | +257.3% | +65.8% | -40.8% | **-126 points** |
| put policy, baseline | +180.5% | — | -24.5% | -203 points |
| put policy, no_hedge | +230.4% | — | -67.4% | -153 points |

**R1 lost 65% of capital while the thing it was written on rose 383%.** Every
one of the 23 grid configurations is negative, the best at -32.9%. The
mechanism is in its own ledger: `short_prem_collected +105,370`,
`short_realized -30,028`, **`anchor_realized -64,810`**. The long-dated put —
F2's "cheap tenor", F8's "cheap insurance" — bled to death in a market that went
up fourfold. F8 measured its bleed at $0.21/week over a sample containing two
crashes. Over the full window the crashes never paid for the carry.

**R2 is the more interesting case and should not be called a failure.** It
returns less than the underlying but takes far less risk: MAR 1.61
(65.8/40.8) against buy-and-hold's 0.98 (86.0/88.0). A deep-ITM call is a
leveraged long, so most of its return is beta — but it is beta with a defined
floor, which is a real thing to want. It was never presented that way because
the benchmark was never computed.

The `active_lab` and `blend_lab` results do beat buy-and-hold on both axes
(CAGR 114.6%, max DD -35.0%, MAR 3.27). They are also the top rows of sorted
grids, over 131 weeks, with returns concentrated in one episode — `meltup26`
contributes +326% to the leader. That is the profile the band strategy had
before it collapsed.

## 3. The problem underneath all of it

**2024-2026 was a +383% melt-up in SOXL.** Every number in the options study —
the VRP by tenor, the skew, the strategy backtests — is measured inside a
once-in-a-decade bull market in the underlying. F2's headline that long-dated
volatility is underpriced by 29 points is a statement about a period in which
realized volatility was extraordinary because the price quadrupled.

A study that never printed the underlying's own return alongside its strategies
cannot tell you whether it found an edge or a beta. This one didn't, and R1's
-65% is what that omission costs.

## 4. What this does NOT establish

- The VRP measurements may well be correct as measurements. They are quotes
  against subsequent realized vol, and 919,090 of them.
- R2's risk-adjusted result survives the benchmark and deserves a fair test.
- No bug of the S10 class was found. The audit looked and did not find one.

## 5. Recommendation

Do not build R1. It was already built and it lost.

Before anything else is built on this data, every backtest in the repo needs
the underlying's return printed next to it, over the identical window. That is
one column, and its absence is how a -65% strategy came to be the top
recommendation in a document full of real measurements.
