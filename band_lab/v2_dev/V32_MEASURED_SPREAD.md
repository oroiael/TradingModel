# V32 — Gap #1 closed. The real spread is worse, and it settles V31.

V31's verdict rested on a spread of **10.6 volatility points**, taken from
end-of-day vendor snapshots. Assumption A1 paid that spread in full on every
fill, and the open question was whether the *midday* spread is tighter — because
if it were, −2.94%/cycle was too harsh and the strategy might survive.

**It is not tighter. It is worse.** Measured from live IBKR `BID_ASK` ticks.

    python band_lab/v2_dev/option_spread_probe.py --check
    python band_lab/v2_dev/option_spread_probe.py --collect --sessions 10
    python band_lab/v2_dev/option_spread_probe.py --analyse
    python band_lab/v2_dev/straddle_backtest.py --grid --extra-spread 7.2

## The measurement

9,066 ticks, 9 sessions (2026-08-17 → 08-28), 126 straddle observations, ATM at
35–39 DTE — the same contract-selection rule the backtest uses.

| time | spread $ | % of mid | **vol points** | bid size |
|---|---|---|---|---|
| 09:30 | 6.16 | 16.1% | **20.4** | 577 |
| 10:00 | 5.64 | 15.2% | 18.8 | 418 |
| 11:00 | 5.48 | 14.6% | 18.1 | 548 |
| 12:00 | 5.39 | 14.5% | 17.8 | 624 |
| 13:00 | 5.33 | 14.3% | 17.6 | 555 |
| 14:00 | 5.00 | 13.7% | 16.6 | 455 |
| 15:00 | 4.50 | 11.5% | **14.9** | 566 |
| **15:45** | 6.54 | 17.9% | **21.7** | **3** |
| **ALL** | **5.38** | **14.6%** | **17.8** | 512 |

| | vol points |
|---|---|
| **measured intraday, mean** | **17.8** |
| measured intraday, median | 18.0 |
| V28 end-of-day, mean — what V31 charged | 10.6 |
| V28 end-of-day, median | 6.0 |
| **understated by** | **7.2** |

The spread tightens steadily through the session and then **blows out at the
close** — 14.9 vol points at 15:00, 21.7 at 15:45, with depth collapsing from
566 contracts to **3**. The strategy hedges and rolls at the close, so it trades
at the single worst moment of the day. **17.8 is therefore itself generous for
this strategy.**

## What it does to V31

Charging the measured 7.2-point shortfall against each cycle's own vega:

| | V31 (EOD spread) | **V32 (measured)** |
|---|---|---|
| mean return per cycle | −2.94% | **−10.11%** |
| t | −1.10 | **−3.76** |
| 95% CI | [−8.18%, +2.31%] | **[−15.38%, −4.85%]** |
| cycles profitable | 43% | **25%** |
| equity at 5% sizing | −11.2% | −32.7% |
| max drawdown | −19.8% | **−35.9%** |

**The verdict changes character.** V31 said "loses, but not distinguishable from
zero." With the real spread it is **significantly negative** — t = −3.76, and
the confidence interval no longer contains zero.

Every grid cell, all nine, now negative *and* significant:

| entry/roll | return/cycle | t |
|---|---|---|
| 30/7 | −9.50% | −3.46 |
| 30/14 | −11.20% | −4.66 |
| 30/21 | −13.33% | −11.36 |
| 37/7 | −8.73% | −2.55 |
| **37/14** | **−10.11%** | **−3.76** |
| 37/21 | −12.52% | −6.83 |
| 45/7 | −7.55% | −2.15 |
| 45/14 | −11.32% | −3.67 |
| 45/21 | −11.64% | −4.83 |

| bar | V31 | V32 |
|---|---|---|
| B1 t > 2.0 | FAIL (−1.10) | **FAIL (−3.76)** |
| B2 ≥ 4 of 5 years | FAIL (2/5) | **FAIL (0/5)** |
| B4 ≥ 7 of 9 cells | FAIL (0/9) | FAIL (0/9) |
| B7 drawdown < 35% | PASS (−19.8%) | **FAIL (−35.9%)** |

## The number that ends it

Return moves **−0.996% per cycle for every volatility point of spread**. Setting
V31's −2.94% to zero:

**Break-even spread = 7.65 vol points.**

- measured intraday: **17.8** — 2.3× the break-even
- end-of-day vendor: 10.6 — still above it
- end-of-day *median*: 6.0 — the only figure below break-even, and a median is
  not what a strategy pays

Even the most optimistic spread estimate in this repository except the median
leaves the strategy losing. There is no plausible fill assumption that rescues
it.

## Two corrections to the record

**The "bid size 1" alarm was wrong.** V31's IBKR section flagged an ATM SOXL
call quoting bid size 1 and suggested the backtest's 10 contracts might walk the
book. That was a **frozen Saturday quote**. Live median depth at the touch is
**512 contracts**. V30 assumption A6 holds comfortably. I raised an alarm from a
weekend quote and should have discounted it as one at the time.

**The direction of the open question was wrong.** V31 named gap #1 as "the
single assumption that could revive this." It could have, and it did the
opposite. Closing it was still right — the point of measuring is that you do not
know the sign in advance — but the framing implied an upside that was not there.

## What remains unmeasured

The 9 sessions are all August 2026, a period when SOXL moved 10% in a day and
implied vol ran 110–125%. **Spreads widen with volatility**, so 17.8 may
overstate a calm-market average. That cuts toward the strategy. It does not cut
far enough: the gap between 17.8 and the 7.65 break-even is 10 vol points, and
the end-of-day series — which spans 2022–2026 including quiet 2023 — already
sits at 10.6, above break-even on its own.

Also still unmeasured: whether a worked limit order fills inside the touch. This
measures the **quoted** spread, not fill quality. But the arithmetic above means
price improvement would have to average better than 10 of 17.8 vol points —
capturing 57% of the spread on every leg of every trade — merely to reach zero.
