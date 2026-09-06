# Delta-hedged long gamma — the first options structure on SOXL that pays

Every structure tested in this directory so far sold premium, and every one
lost, for one reason: SOXL's variance risk premium is negative. This is the
trade that measurement actually implies — **buy** the underpriced vol and strip
the direction out by hedging delta.

**It works, at one hedging frequency, and the frequency is the whole result.**

| hedge schedule | hedges | gross | costs | **net** |
|---|---:|---:|---:|---:|
| every 5 min | 39,308 | +$6,837 | $39,410 | **−$32,573** |
| every 15 min | 13,714 | — | $15,457 | −$9,103 |
| every 30 min | 7,043 | +$6,704 | $8,790 | −$2,087 |
| hourly | 3,859 | — | $5,491 | +$303 |
| delta band ±20 | 789 | — | $2,454 | +$11,288 |
| once/day (BS delta) | 605 | — | $1,825 | +$22,851 |
| **once/day (real EOD delta)** | **625** | **+$23,544** | **$1,773** | **+$21,771** |

Engine: `gamma_scalp_backtest.py`. Report `qa/gamma_scalp_report.txt`, grid
`gamma_scalp_grid.csv`, cycles `gamma_scalp_cycles.csv`. **18 runs, 0 QA
reconciliation failures.** Reproduce with `git lfs pull && python3
gamma_scalp_backtest.py`.

---

## 1. The result

Base structure: buy a 60-DTE ATM straddle from the real EOD chain on a $15,000
premium budget, hedge to delta-neutral with SOXL shares, rehedge once daily at
the close, hold to expiry, settle at intrinsic, unwind the shares. Cycles run
back to back with no overlap, 2024-01-02 → 2026-06-18.

| | |
|---|---:|
| cycles | 15 |
| net P&L | **+$21,771** |
| mean per cycle | **+10.4% of premium** |
| win rate | **67%** |
| t-statistic | **1.62** |
| P&L excluding the single best cycle | **+$11,560** |
| worst cycle | −$4,624 |
| friction | $1,773 (625 hedges) |

**The predicted mechanism is confirmed.** Mean entry implied vol 94.9% against
112.3% subsequently realized — a **+17.4 vol-point** edge, positive in 11 of 15
cycles. And unlike every prior structure here, the driver the theory names
actually explains the outcome:

> **corr(vol edge, cycle P&L) = +0.69**

That is the sentence this whole investigation has been missing. In the condor,
calendar and weekly-premium engines, the thing the thesis said should drive P&L
had no relationship to it. Here it does.

**It is not one lucky cycle, one tenor, or one structure:**

| variant (all hedged daily) | cycles | net | mean %prem | t | ex-best |
|---|---:|---:|---:|---:|---:|
| 30-DTE straddle | 26 | +$38,227 | +11.1% | 1.64 | +$24,889 |
| 60-DTE straddle | 15 | +$21,771 | +10.4% | 1.62 | +$11,560 |
| 90-DTE straddle | 9 | +$14,622 | +11.7% | 1.36 | +$4,892 |
| 60-DTE call only | 15 | +$20,538 | +9.4% | 1.37 | +$9,434 |
| 60-DTE put only | 15 | +$24,728 | +11.3% | 1.79 | +$13,908 |

Every tenor, both rights, positive in all of them, and positive after removing
each one's best cycle. The mirror also holds: at 30-minute hedging **every**
tenor turns negative (−$2,787 / −$2,087 / −$1,420).

---

## 2. Why hedging frequency decides it

Two distinct effects, and only one is the obvious one.

**Friction scales with hedge count** — $1,773 daily against $39,410 at 5-minute,
a 22× increase, charged at the same IBKR Pro Fixed rates `band_lab` uses for the
live engine ($0.005/share, $1.00 minimum, half of a 1.0c spread on every
crossing market order, SEC and FINRA fees on sells).

**But frequent hedging also captures less edge before any cost is charged.**
Gross P&L at 5-minute is **+$6,837** against **+$23,544** daily — less than a
third, with zero friction in either. The reason is in the realized-vol column:

| sampling | annualized realized vol |
|---|---:|
| daily close-to-close | **112.3%** |
| hourly | 106.8% |
| 30 min | 107.6% |
| 5 min | 108.1% |
| *(entry implied)* | *94.9%* |

Gamma P&L is quadratic in the move — it pays `(ΔS)²`. One 5% daily move pays far
more than thirteen 0.4% moves that sum to the same displacement. SOXL trended
within the day across this window, so daily sampling collected materially more
variance than intraday sampling did. `vol_anatomy` measured the same asymmetry
from the other side: 5-minute intraday RV annualizes to ~80–92% while
close-to-close runs ~115–117%, because **37–41% of the variance sits in the
overnight gap** — which no hedging schedule can trade through, and which the
daily hedger is therefore paid for in full.

So the practitioner's instinct that gamma scalping means hedging constantly is
exactly backwards on this instrument. **Hedge as rarely as the mandate allows.**

---

## 3. This does not contradict `band_lab` — it complements it

`band_lab` earns ~40 bp/ON-day trading SOXL's *intraday reversals* in shares.
This engine finds that the *intraday* scale is the worst place to harvest gamma.
Both are true and they are not in tension:

- **Gamma** pays for large displacement — the daily and overnight moves.
- **`band_lab`** pays for oscillation — the small intraday reversals, monetized
  directionally by buying dips beneath a stale high, not by hedging convexity.

They harvest different frequencies of the same volatility, and the measurement
that makes one work is the measurement that makes the other fail.

---

## 4. What it is worth, honestly

The "+10.4% of premium per cycle" figure flatters the trade, because premium is
not the only capital committed. The share hedge reached a **mean peak notional
of $65,725 per cycle** (max $111,687) against a mean premium of $14,490. Against
premium plus a 30% haircut on the peak hedge — roughly **$34,000 of capital at
work** — the result is:

> **+64% total over 2.5 years, or about +22%/yr.**

Real, but a long way from the headline. Quote the second number.

---

## 5. Honest limitations

* **The sample is small and the t-statistic is not significant.** 15 cycles,
  t = 1.62, p ≈ 0.13. The 30-DTE variant gives 26 cycles at t = 1.64. What
  carries conviction here is not any single t but the consistency — five
  tenor/structure variants, all positive, all surviving the loss of their best
  cycle, with a +0.69 mechanism correlation. Treat it as a well-supported
  hypothesis, not a validated edge.
* **2025 was flat** (−0.5% per cycle across 6 cycles) despite a +14-point vol
  edge that year, which is a direct reminder that aggregate realized-over-implied
  does not guarantee P&L: gamma P&L is *gamma-weighted*, so it matters where the
  strike sits when the moves arrive, not just how large they were. 2024 ran
  +16.5% per cycle and 2026 +21.6%.
* **The daily result uses no model; the intraday results do.** Every "daily"
  number rehedges on the **real `delta` column** from the EOD chain. Intraday
  schedules have no such data — the 5-minute option files carry trade prices and
  no greeks — so their deltas are Black-Scholes on the contract's own *prior*
  EOD implied vol (the last value observable when the hedge is placed; using the
  same day's close would be look-ahead). Measured error against the real EOD
  delta is **MAE 0.0178**, and the two once-per-day schedules — identical except
  for the delta source — land within $1,080 of each other. That validates the
  proxy, but the intraday conclusions remain weaker than the daily one.
* **Execution.** Hedges price at the **bar close**, never the bar high or low.
  `call_spread_lab/FINDINGS_6` is the cautionary tale: an intraday result there
  reversed sign entirely once fills stopped assuming foresight.
* **Sequential cycles only.** One position at a time, no overlapping ladder, so
  the cycle count is low by construction and capital sits idle between rolls.
* **Not modelled:** early exercise (both legs are long, so this is an option we
  hold rather than a liability), borrow cost or dividends on the short share
  leg, and any intraday re-strike of the straddle as spot drifts.
* **One instrument, one window,** 2024-01 → 2026-06, containing the 2026
  melt-up. The negative VRP that powers this trade is itself a measured property
  of this window, not a law.

---

## 6. What this changes

`README.md` §3 of this directory said "own the vol" and pointed at long
strangles and debit spreads. That stands, and this adds the delta-neutral member
of the family — the only one that isolates the vol edge from direction, which is
what made every other long-premium structure here a regime bet.

The scorecard is unchanged: **no short-premium structure on SOXL pays.** What
changes is the constructive half. There is now a measured options trade on this
instrument with a positive expectancy and a confirmed mechanism, and its single
most important parameter is the one the textbook gets backwards.

**Next, in order of value:**

1. **More cycles.** Overlapping ladders (a new straddle every two weeks rather
   than on expiry) would multiply the sample without changing the trade, and is
   the cheapest way to move t = 1.62 toward significance.
2. **A vol-percentile entry gate.** `harvest_blueprint/README.md` §2 showed
   IVP > 70 is where *selling* dies; the symmetric question — whether *buying*
   is best when IV is cheap — is untested and the data supports answering it.
3. **A smarter hedge trigger.** The band results (±20 delta beat ±5 and ±10) say
   the direction of travel is *less* hedging; a move-size trigger rather than a
   time trigger is the natural next test.
