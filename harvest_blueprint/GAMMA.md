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

> **Correction, from the strand sweep in §3:** +10.4% per cycle is the *best*
> entry timing, not the typical one. Run the identical trade from 12 different
> start dates and the mean is **+6.5% per cycle**, with a range of +2.4% to
> +11.1%. All 12 are positive — the sign is robust — but the headline above is
> entry-timing luck and the honest central estimate is **~6.5%**.

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

## 4. This does not contradict `band_lab` — it complements it

`band_lab` earns ~40 bp/ON-day trading SOXL's *intraday reversals* in shares.
This engine finds that the *intraday* scale is the worst place to harvest gamma.
Both are true and they are not in tension:

- **Gamma** pays for large displacement — the daily and overnight moves.
- **`band_lab`** pays for oscillation — the small intraday reversals, monetized
  directionally by buying dips beneath a stale high, not by hedging convexity.

They harvest different frequencies of the same volatility, and the measurement
that makes one work is the measurement that makes the other fail.

---

## 4b. What it is worth, honestly

The "+10.4% of premium per cycle" figure flatters the trade, because premium is
not the only capital committed. The share hedge reached a **mean peak notional
of $65,725 per cycle** (max $111,687) against a mean premium of $14,490. Against
premium plus a 30% haircut on the peak hedge — roughly **$34,000 of capital at
work** — the result is:

> **+64% total over 2.5 years, or about +22%/yr.**

Real, but a long way from the headline. Quote the second number.

---

## 3. Overlapping ladders — what they actually bought

Running the same trade from 12 staggered start dates (each strand internally
non-overlapping, `start_offset` in the engine):

| | strands |
|---|---|
| positive | **12 of 12** |
| P&L range | **+$4,925 → +$21,771** |
| mean per cycle | **+6.5% of premium** (range +2.4% to +11.1%) |
| win rate range | 36% – 67% |
| positive excluding own best cycle | 11 of 12 |

**The sign is robust to entry timing; the magnitude is not.** A 4.4× spread on
start date alone is the single most important calibration in this document.

`gamma_ladder_backtest.py` then runs it as a real portfolio — a new straddle
every 10 trade days, ~3.2 alive at once, one delta book netted across all of
them, rehedged daily on real EOD deltas. 8 runs, 0 QA failures (the last equity
row and the cash left after closing the book agree to the cent).

| | base ladder | SOXL buy-and-hold, same window |
|---|---:|---:|
| CAGR | **+13.2%** | +111.7% |
| max drawdown | **−19.5%** | −88.0% |
| Sharpe | **0.66** | 1.23 |
| annualized vol | **22.5%** | 120.2% |
| **beta to SOXL** | **−0.053** | 1.00 |

| variant | rungs | P&L | CAGR | max DD | Sharpe | mean premium at risk |
|---|---:|---:|---:|---:|---:|---:|
| every 5 days | 94 | +$76,353 | +18.0% | −30.6% | 0.61 | $82,261 |
| **every 10 days (base)** | 53 | **+$54,140** | +13.2% | −19.5% | **0.66** | $45,591 |
| every 20 days | 28 | +$41,013 | +10.2% | −14.6% | **0.79** | $23,946 |
| every 41 days (≈ sequential) | 15 | +$17,791 | +4.6% | −7.4% | 0.57 | $13,811 |
| 30-DTE rungs | 62 | +$50,958 | +12.5% | −22.1% | 0.63 | $29,166 |
| 90-DTE rungs | 42 | +$66,663 | +15.9% | −16.1% | 0.74 | $57,506 |

**By year, all three positive** — 2024 +$21,556, 2025 +$3,623, 2026 +$24,408.
Laddering repaired the flat 2025 of the single-position engine, which is exactly
the entry-timing diversification working.

### Three things this settles

**Denser laddering is leverage, not edge.** Going from every-20-days to
every-5-days nearly doubles P&L and nearly doubles premium at risk, while
Sharpe *falls* (0.79 → 0.61) and drawdown doubles. The 20-day rung is the best
risk-adjusted point tested.

**Netting the hedge book barely matters.** It was one of the stated reasons for
building this, and it is worth **$743** — 15% of the $4,911 friction bill, 1.4%
of P&L. Spread cost scales with shares traded, not with order count, so netting
only saves the per-order minimums. That rationale was wrong.

**The delta hedge genuinely works.** Beta to SOXL is **−0.053** and the ladder's
own vol is **22.5%** against the underlying's 120.2%. This is a real
uncorrelated return stream, not a disguised long position — which is precisely
what every other long-premium structure in this repo failed to be.

### And one thing it does not settle

I said building this would move t = 1.62 toward significance. **That was wrong,
and it is worth being explicit about why.** Overlapping rungs are not
independent draws — they sample the same 2.5 years of one instrument, so a
t-statistic computed across them is inflated by construction. A ladder removes
entry-timing luck and smooths the equity curve; it cannot manufacture
information about the true expectancy. The honest sample is still one path,
2024-01 → 2026-06, and only out-of-sample time or another instrument can change
that.

### How to read the benchmark

Buy-and-hold beat the ladder on Sharpe over this window (1.23 vs 0.66), and
that comparison should not be waved away — but it is not apples to apples. The
window contains the 2026 melt-up, which is close to the best conceivable tape
for owning a 3× fund, and it carried an **−88% drawdown** to get there. The
ladder earned less at a fifth of the volatility and essentially zero beta. As a
standalone bet it lost this window; as a diversifier against the very drawdown
that makes SOXL unholdable, it is doing something buy-and-hold structurally
cannot.

---

## 4c. TQQQ — the out-of-sample instrument test, and it failed

Every limitation above reduced to one: a single instrument over a single
2.5-year path. TQQQ's chains cover exactly the same window with an identical
schema, so `gamma_tqqq_backtest.py` runs the same engines on it with **no code
changes** — that file supplies data only.

**The prediction was stated before the run.** `vol_anatomy` measured TQQQ's VRP
as negative at the same tenors and nearly the same margin as SOXL's (30d −9.9
vs −10.3 pts), while its vol *level* is roughly half. Since gamma P&L scales
with `rv² − iv²`, TQQQ should be **positive but smaller**.

**It came back negative.**

| | entry IV | realized | edge (pts) | `rv²−iv²` | rel. to SOXL | net | % of premium |
|---|---:|---:|---:|---:|---:|---:|---:|
| **SOXL** | 0.949 | 1.123 | **+17.4** | 0.361 | 1.00 | **+$21,771** | **+10.4%** |
| **TQQQ** (pre-split) | 0.530 | 0.595 | +6.5 | 0.073 | **0.20** | **−$3,651** | **−2.4%** |
| **TQQQ** (post-split) | 0.689 | 0.501 | −18.8 | −0.224 | −0.62 | −$10,048 | −22.9% |

Strand sweeps say it is not entry-timing luck in either direction: SOXL is
**positive in 12 of 12** start dates, TQQQ **positive in 0 of 12** (pre-split
range −$5,222 to −$891; post-split 0 of 12, −$12,942 to −$826). The ladder
agrees — TQQQ pre-split runs −$28,338 at Sharpe −0.52 against SOXL's +$54,140
at +0.66. The SOXL figures reproduce to the dollar through this separate code
path, which is the regression check that the refactor changed nothing.

### The prediction was wrong, and friction is not the excuse

TQQQ pre-split is **negative gross** — −$2,579 with every cost switched off.
So this is not a friction story, and the honest reading is that a positive
aggregate vol edge is **necessary but not sufficient**. TQQQ pre-split realized
6.5 vol points *more* than implied and still lost money before costs.

The reason is the one flagged for SOXL's flat 2025: gamma P&L is
**gamma-weighted**, not variance-weighted. It pays for moves that arrive while
the position sits near its strike, not for aggregate variance however measured.
A surface can realize more than it implied and still hand a delta-hedged holder
nothing, if the movement shows up in the wrong places.

There is a quantitative story that partly rescues the mechanism: TQQQ's
variance edge is **20% of SOXL's** (0.073 vs 0.361), so the predicted return
was roughly a fifth of SOXL's +10%, i.e. ~+2% per cycle — and the fixed drag
that gamma-weighting imposes was evidently larger than that. **But this is
post-hoc.** I am explaining a failed prediction after seeing the answer, and it
should be read as a hypothesis for the next test, not as a defence of this one.

### What this does to the SOXL result

The SOXL numbers are unchanged and were not contradicted — TQQQ is a different
surface, not a replication of the same one. But the claim that mattered was
never "it worked on SOXL"; it was "this is a property of negative-VRP leveraged
ETFs." **That claim now has one test and it failed.** Treat the SOXL result as
a single-instrument finding whose generality is unproven, and weight it well
below where §1 of this document left it.

The next test that would actually settle it is a *third* instrument with a
large `rv²−iv²` — the falsifiable form being that the trade pays where the
variance edge is large and fails where it is small, independent of ticker.

### A data defect worth recording

The first TQQQ run returned **+170% of premium per cycle** at Sharpe 2.25, and
it was entirely fabricated. `TQQQ_IBKR_3YR_EOD.csv` is split- and
dividend-**adjusted**; the chain's `underlying_price` and its strikes are
**raw**. The two disagree by a factor of **2.0533** before TQQQ's 2:1 split on
**2025-11-20** and by 1.0000 after it. The engine was picking a $48 strike and
settling it against a $23 close.

The tell was that the result contradicted the prediction in the *favourable*
direction, and that TQQQ appeared to realize **155% vol** when its true vol is
~56%. SOXL is unaffected — its two sources agree to 1.0001, which is why the
defect never surfaced before. The fix is to take spot from the chain's own
`underlying_price`, which matches the strikes by construction, and to run
either side of the split so that no cycle spans it (option contracts are
themselves adjusted at a split, which the engine does not model).

`find_splits()` now detects this by *comparing the two sources* rather than by
move size — the distinction that matters, since 2025-04-09's +30% appears in
both series (real) while 2025-11-20's −77% appears in only one (a split).

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
* **Entry timing moves the answer a lot.** 12 staggered strands span +$4,925 to
  +$21,771. All positive, but quote **+6.5% per cycle**, not +10.4%.
* **The ladder adds robustness, not statistical power.** Overlapping rungs are
  not independent observations; the sample is still one path over 2.5 years.
* **Not modelled:** early exercise (both legs are long, so this is an option we
  hold rather than a liability), borrow cost or dividends on the short share
  leg, and any intraday re-strike of the straddle as spot drifts.
* **The one out-of-sample instrument test failed** (§4c). TQQQ is negative on
  the same engines over the same window, gross as well as net, and in 0 of 12
  entry timings. The SOXL result stands as measured; its generality does not.
* **One window,** 2024-01 → 2026-06, containing the 2026 melt-up. The negative
  VRP that powers this trade is a measured property of this window, not a law.
* **Adjusted vs raw price sources are a live hazard** in this repo, not a
  hypothetical: mixing them fabricated a +170%/cycle result on the first TQQQ
  run. Any new instrument must pass the chain-spot-vs-bar-close ratio check
  before its numbers mean anything.

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
