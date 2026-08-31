
# V39 — Straddle hedged at the OPEN (V29 Tier 2 #6). Bar, before the code.

V29 proposed: *"48% of variance is overnight. Hedge to flat at 09:30 and leave
it, and you own the gap without paying to chase the intraday chop."*

## The premise is wrong, and the measurement says so

A delta-hedged option's gamma P&L accumulates the squared underlying return over
**each hedge interval**. Hedging once a day therefore captures a full 24-hour
window **regardless of the hour it is placed**. Hedging at 09:30 gives
open-to-open; hedging at 15:59 gives close-to-close. Both contain the gap *and*
the session. Neither isolates anything.

Measured directly, 1,146 sessions, 2022–2026:

| sampling | variance | ann. vol | vs close |
|---|---|---|---|
| close-to-close | 0.005549 | 118.2% | — |
| **open-to-open** | 0.005307 | **115.6%** | **−4.35%** |
| twice daily (open + close) | 0.005411 | 116.8% | −2.5% |

**Hedging at the open captures 4.35% LESS variance than hedging at the close** —
about **−2.6 volatility points** for a gamma buyer. #6 does not improve on the
V31/V32 baseline; it is strictly worse, and the baseline schedule already turns
out to be the best of the three.

The whole difference is which covariance term falls inside the window:

| | |
|---|---|
| close-to-close contains Cov(overnight_t, intraday_t) | **+0.000069** |
| open-to-open contains Cov(intraday_t, overnight_t+1) | **−0.000051** |

## And a correction to V27

V27 reported *"overnight, market closed — 80.4% vol, 48% of variance, NOT
hedgeable."* That was a **residual**: total variance minus the 1-minute intraday
*path* variance. A residual absorbs everything the subtraction misses, including
intraday autocorrelation.

Measured directly from the actual overnight return, `log(open_t / close_{t−1})`:

| | V27 (residual) | **measured directly** |
|---|---|---|
| overnight vol | 80.4% | **71.7%** |
| share of close-to-close variance | 48% | **36.7%** |

**"48% of SOXL's variance happens overnight" is an overstatement. The figure is
36.7%.** The direction of V27's argument survives — the gap is a large,
unhedgeable share of total variance — but the number was inflated by the residual
method and has been repeated three times since.

## The prediction

**#6 loses to the V31/V32 baseline by roughly 2.6 vol points**, on top of a
deficit V32 measured at ~7 vol points. It cannot rescue anything.

## Prespecified grid

Headline: **nearest 37 DTE, roll at 14 DTE, hedge once daily at the OPEN**,
against V31/V32's identical configuration hedged at the close.

- hedge time: **open**, **close** — 2
- entry DTE: **30, 37, 45** — 3

Six cells, both spread regimes. Nothing else swept.

## Adoption bars

| # | bar | note |
|---|---|---|
| **B1** | return/cycle > 0 with **t > 2.0** | unchanged |
| **B1b** | **the open-hedged cell must beat the close-hedged cell at the same DTE** | this is the actual claim #6 makes |
| **B3** | every cost charged | |
| **B4** | ≥ 5 of 6 cells positive | |
| **B7** | max drawdown < 35% | |

**B1b is the bar that matters.** #6 is not a new strategy — it is a scheduling
change to #1. If it does not beat #1 at the same parameters it has no reason to
exist, whatever its absolute number.

## New assumption

| # | assumption | kind |
|---|---|---|
| A25 | The option's delta at 09:30 is computed by Black-Scholes from the 09:30 spot and the **prior close's** implied vol. The vendor file is end-of-day only, so no quoted delta exists at the open. `bs.py` reproduces the vendor's delta to 0.0002 at the close, so the model is sound; carrying the prior IV forward one session is the approximation. | `[ASSUMED]` |

## What would make me discard the result

- The open-hedged cell beating the close-hedged cell by more than the 4.35%
  variance difference can explain. That would mean the hedge is picking up
  something other than gamma, and I would look for the bug.
