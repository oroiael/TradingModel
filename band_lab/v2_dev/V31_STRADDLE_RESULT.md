# V31 — Long ATM straddle, delta-hedged daily: the result. **v1**

Tests V29 Tier 1 #1 against the bar committed in `V30_STRADDLE_BAR.md` before
the code was run.

    python3 band_lab/v2_dev/straddle_backtest.py --grid
    python3 band_lab/v2_dev/straddle_backtest.py --trace 3

## Verdict

**Not adopted. B1, B2 and B4 all fail. Zero of the nine prespecified grid cells
has a positive mean return.**

| bar | test | result | |
|---|---|---|---|
| B1 | mean return/cycle > 0, t > 2.0 | **−2.94%, t = −1.10** | **FAIL** |
| B2 | positive in ≥ 4 of 5 calendar years | **2 of 5** | **FAIL** |
| B3 | all four costs charged | yes | PASS |
| B4 | ≥ 7 of 9 grid cells positive | **0 of 9** | **FAIL** |
| B5 | headline within 1 se of grid median | 0.42 se | PASS |
| B6 | benchmark reported | yes | PASS |
| B7 | max drawdown < 35% | −19.8% | PASS |

B5 and B7 passing is not consolation: B5 says the headline is not a cherry-pick
of a bad grid, and B7 says the losing is orderly.

## The headline run

77 cycles, 2022-01-03 → 2026-07-02, 10 contracts per leg, enter nearest 37 DTE,
roll at 14 DTE, hedge once daily at the close.

| component | per cycle | % of premium |
|---|---|---|
| option P&L (bought the ask, sold the bid) | −$518 | −4.3% |
| delta hedge P&L | +$922 | +2.2% |
| **= gross** | **+$404** | **−2.2%** |
| hedge friction | −$31 | −0.3% |
| option commission | −$26 | −0.4% |
| **= NET** | **+$347** | **−2.94%** |

Mean return −2.94% per cycle, t = −1.10, 95% CI [−8.18%, +2.31%]. Median
−6.09%. 43% of cycles profitable. Sharpe −0.13. At 5% of capital in premium per
cycle the equity curve ends −11.2% with a −19.8% drawdown, against SOXL's
+151.3% over the same window.

**The dollar column and the percentage column have opposite signs, and the
percentage one is correct.** See correction C1.

## Why it failed — the mechanism works, the price is wrong

**The machine is sound.** Correlation between a cycle's return and
(realised − implied) over that cycle is **+0.85**. The hedge does what it is
supposed to: when realised volatility beats implied, the strategy makes money.

**The edge is real and V30's prediction was accurate.**

| | V30 predicted | measured |
|---|---|---|
| realised minus implied | +11.8 vol pts | **+11.5** |
| round-trip spread | −8.1 vol pts | **−10.6** |
| **net** | **+3.7** | **+1.0** |

The edge came in within 0.3 vol points of the prediction. **The spread did not.**

### The spread error, and where it came from

V28 measured the ATM option round trip at **8.1 vol points** and V29 carried
that into the estimate. That figure was a **median**. The distribution is
strongly right-skewed:

| | vol points |
|---|---|
| median | 6.0 |
| **mean** | **10.6** |
| p75 | 14.2 |
| p95 | 33.7 |

**A strategy pays the mean, not the median.** V29's arithmetic used the wrong
statistic, and it is worth 2.5 vol points — most of the predicted edge.

### And the vol-point arithmetic overstates even so

Predicted P&L from (net vol points × opening vega) is +$787/cycle. Actual is
+$347. **Ratio 0.44.** Vega is a linear approximation taken at the open; a
straddle held 15 sessions moves far from at-the-money, where vega collapses.
The first-order arithmetic in V29 was optimistic by roughly a factor of two on
top of the spread error.

### The number that settles it

Net vol points per cycle: **mean +1.0, median −5.2.** A typical cycle loses 5.2
volatility points. The positive mean is a handful of large winners. That is why
only 43% of cycles are profitable and the mean return is still negative — the
few big winners are not big enough to pay for the many small losers **after**
the spread.

## By year

| year | cycles | mean return | win% | IV at open | realised | edge |
|---|---|---|---|---|---|---|
| 2022 | 18 | **+5.5%** | 56% | 111.0% | 129.5% | +18.6 |
| 2023 | 17 | −7.2% | 35% | 83.0% | 82.1% | −0.9 |
| 2024 | 17 | −6.4% | 41% | 89.8% | 102.2% | +12.4 |
| 2025 | 17 | −7.1% | 29% | 97.5% | 107.3% | +9.7 |
| 2026 | 8 | **+3.4%** | 62% | 123.6% | 147.8% | +24.2 |

2024 and 2025 both had a **positive** volatility edge (+12.4 and +9.7 points)
and both lost money. That is the spread, arriving twice a month.

## The prespecified grid — all nine cells

| entry DTE | roll DTE | cycles | return/cycle | t | equity | win% |
|---|---|---|---|---|---|---|
| 30 | 7 | 75 | −2.20% | −0.81 | −8.4% | 44% |
| 30 | 14 | 113 | −4.06% | −1.68 | −21.2% | 32% |
| 30 | 21 | 221 | −6.02% | −5.11 | −49.1% | 28% |
| 37 | 7 | 54 | −1.52% | −0.45 | −4.4% | 44% |
| **37** | **14** | **77** | **−2.94%** | **−1.10** | **−11.2%** | 43% |
| 37 | 21 | 114 | −5.33% | −2.90 | −26.6% | 31% |
| 45 | 7 | 43 | −0.40% | −0.11 | −1.1% | 47% |
| 45 | 14 | 57 | −4.13% | −1.33 | −11.5% | 44% |
| 45 | 21 | 77 | −4.54% | −1.88 | −16.4% | 39% |

Monotone in the right direction: the shorter the hold, the fewer rolls, the
fewer spreads paid, the less it loses. The best cell (45/7, −0.40%) is the one
that trades least. That is a cost curve, not an edge.

**Caveat on the roll-at-7 cells:** they abandon 11, 28 and 48 cycles
respectively because the held contract has no two-sided quote at ≤ 7 DTE. For
45/7 that is 48 abandoned against 43 completed — **more than half**. Those cells
are heavily filtered by data availability and their returns are not comparable
to the others. They are reported because they were prespecified, not because
they are trustworthy.

---

# Corrections made between the first run and v1

Seven. The first is the one that changed a conclusion; the last is a real bug.

### C1 — the primary metric was wrong, and the two metrics disagreed in sign
The first run reported **dollars**. SOXL went from an average $24 in 2022 to
$109 in 2026, so a 2026 straddle cost **6×** a 2022 one and a dollar sum weights
2026 six times as heavily.

| | first run | corrected |
|---|---|---|
| mean P&L per cycle | **+$35, t = +0.64** | — |
| mean return per cycle | — | **−2.94%, t = −1.10** |

Positive on one metric, negative on the other. **Return on premium is the
correct one** and every bar is now tested on it.

### C2 — one contract made whole-share rounding a 3% error
An ATM straddle's net delta is near zero, so with 1 contract the hedge was ~16
shares and rounding to whole shares was ~3% per hedge, on 1,155 hedge trades.
Raised to 10 contracts; the error drops to 0.3%. Size does not affect the edge —
this is a numerical fix, not a knob.

### C3 — the −99.8% drawdown measured the sizing rule, not the strategy
The first run compounded 100% of capital into each straddle 77 times running.
Replaced with 5% of capital in premium per cycle: drawdown −19.8%.

### C4 — realised volatility came from the wrong series
It was computed from the option file's `underlying_price` on the subset of days
**both legs happened to be quoted**. Skipped days made log returns span gaps
while still scaling by √252, understating volatility exactly where data is thin.
Now taken from SOXL's own daily closes across the whole hold window. (2022
realised moved 127.3% → 129.5%, 2026 149.4% → 147.8%.)

### C5 — expiry printed as `1970-01-20`
The expiry key is int64 nanoseconds; the trace printed it as a date without
conversion. Display only.

### C6 — added the diagnostic that tests V30's actual prediction
Per-cycle realised-minus-implied and round-trip spread, both in volatility
points, against V30's +11.8 / −8.1 / +3.7. Without it the study would have
reported a number without checking the mechanism it claimed to be measuring.

### C7 — **a bug that hid a third of the grid and manufactured the only winner**

```python
if recv is None:
    break          # WRONG: ends the entire backtest
```

A cycle that opens and never finds a closing quote at or under the roll
threshold ended the **whole run**, not that one cycle. Consequences:

- All three `roll at 7 DTE` cells produced **zero cycles** and silently vanished.
  The grid was printed as **6 cells** and nobody counted that it should be 9.
- Cell (45, 14) terminated after **5 cycles** and reported **+15.88%, t = 2.77,
  80% win rate** — the single positive cell in the grid.

With the bug fixed, (45, 14) runs 57 cycles and returns **−4.13%**. **The only
positive result in the study was the backtest stopping early.** Fixed to abandon
the one cycle and continue, and the abandoned count is now printed so a run that
discards many is visible rather than quiet.

---

# Assumptions that remain, and which way each one leans

From V30, with the direction of the error marked. `[ASSUMED]` items have nothing
measured behind them.

| # | assumption | leans |
|---|---|---|
| A1 | buy the ask, sell the bid, never any price improvement | **against** the strategy — a real trader works the mid and would do better |
| A5 | option commission $0.65/contract `[ASSUMED]` — **the user's IBKR statement contains no option trades, so this is the one cost with no measurement behind it** | small either way: −0.4% of premium |
| A7 | no dividends on the stock hedge `[ASSUMED]` | **flatters** the strategy — a short hedge pays distributions |
| A8 | no financing on cash `[ASSUMED]` | flatters slightly at 4% rates |
| A3 | the hedge fills at the same close as the option quote `[ASSUMED]` | unknown sign; real hedges go at 15:59:xx |
| A6 | depth sufficient at the quote — measured 28 bid / 30 ask | 10 contracts is inside that; 100 would not be |
| A10 | a session with no quote for the held pair is skipped, hedge carried | costs realism on thin days |

**A1 is the one worth revisiting.** Paying the full spread every time is the
most conservative possible assumption, and the result is only −2.94%/cycle
against a 10.6 vol point round trip. Capturing even half the spread by working
the order would move the arithmetic by ~5 vol points, which is more than the
whole deficit. **That is the single test that could revive this**, and it needs
real option fills, not this data.

## What would be needed to overturn this

1. **Midday option spreads, measured.** These quotes are end-of-day. If the
   spread at midday is materially tighter than 10.6 vol points mean, the
   conclusion changes.
2. **Actual fills between the bid and ask.** A1 assumes none, ever.
3. Neither is answerable from the files in this repository. Both are answerable
   from the paper account in a week of quoting straddles.

---

# Verification: the re-run, and the three runs compared

## Run A vs run B — determinism

`straddle_backtest.py --grid` was run twice, back to back, with no changes.

```
stdout diff (A vs B):      IDENTICAL — 0 differing lines
cycles CSV diff:           IDENTICAL — 0 differing rows
md5  runA.txt   a551474c758f631339adaa4922cda556
md5  runB.txt   a551474c758f631339adaa4922cda556
md5  cyclesA.csv fc48e1fbecd1e503d9f9a930f205e3ac
md5  cyclesB.csv fc48e1fbecd1e503d9f9a930f205e3ac
```

Byte-identical. **This proves only that there is no randomness in the pipeline.**
It is necessary and it is weak: a deterministic wrong answer reproduces
perfectly. The check below is the one that carries weight.

## Independent recomputation

Every headline figure recomputed from the stored cycle file using separate
arithmetic, not by calling `summarize()` again:

| quantity | reported | recomputed |
|---|---|---|
| cycles | 77 | 77 |
| mean return per cycle | −2.94% | **−2.9387%** |
| t-statistic | −1.10 | **−1.0984** |
| median return | −6.09% | **−6.0852%** |
| win rate | 43% | **42.86%** |
| years positive | 2/5 | **2/5** |
| equity at 5% sizing | −11.2% | **−11.17%** |
| max drawdown | −19.8% | **−19.80%** |

Identities that must hold and do: `option_pnl == premium_recv − premium_paid`
on every cycle; `net == gross − hedge_cost − opt_commission` on every cycle;
option commission exactly $26 (4 legs × $0.65 × 10 contracts) on all 77; hedge
cost never negative; no negative premium anywhere.

## The check that actually validates the simulator

Split the 77 cycles by whether the volatility arithmetic said they should win:

| | cycles | profitable |
|---|---|---|
| (realised − implied − spread) **> 0** | 32 | **84%** |
| (realised − implied − spread) **< 0** | 45 | **13%** |

The screen separates winners from losers almost cleanly. **The simulator is
modelling the mechanism it claims to model.** The strategy does not fail because
the machine is broken; it fails because the sign is negative on 45 of 77 cycles
after the spread.

## The three runs compared

| | run 0 | intermediate | **v1 (final)** |
|---|---|---|---|
| contracts per leg | 1 | 10 | 10 |
| primary metric | **dollars** | return | return |
| realised vol source | option file, quoted days only | SOXL daily closes | SOXL daily closes |
| `recv is None` handling | `break` (whole run ends) | `break` | **`continue`** |
| headline | **+$35/cycle, t = +0.64** | −2.94%, t = −1.10 | −2.94%, t = −1.10 |
| max drawdown | **−99.8%** (100% reinvested) | −19.8% | −19.8% |
| grid cells run | not run | **6 of 9** | **9 of 9** |
| grid cells positive | — | **1 of 6** (45/14: +15.88%, t=2.77) | **0 of 9** (45/14: −4.13%) |
| verdict | would have read as ambiguous | ambiguous, one winner | **not adopted** |

Three things to take from that row-by-row:

1. **Run 0's headline had the opposite sign to v1's**, purely from reporting
   dollars on a series where the unit price ran 24 → 109.
2. **The intermediate run's single positive grid cell did not exist.** It was
   the backtest terminating after 5 cycles. Fixing the bug turned +15.88% at
   t = 2.77 into −4.13%.
3. **The verdict only became unambiguous after the last correction.** Two of the
   three runs would have supported "inconclusive, worth another look."

## Bottom line

The volatility edge on SOXL is real, was predicted correctly to within 0.3
volatility points, and is not large enough to pay the bid-ask spread on the
options needed to collect it. The strategy loses 2.94% of premium per cycle
across 77 cycles and every one of nine prespecified parameter settings.

The one assumption that could overturn it — A1, paying the full spread on every
fill, forever — is testable on the paper account and is not testable from these
files.

---

# CAGR and max drawdown (added in v2 — daily marking)

## The answer

| premium as % of capital per cycle | CAGR | max DD (daily) | max DD (cycle-end) | final equity | worst day |
|---|---|---|---|---|---|
| 2% | −1.0% | −8.9% | −8.4% | −4.5% | −0.8% |
| **5%** | **−2.6%** | **−20.9%** | −19.8% | −11.2% | −2.0% |
| 10% | −5.4% | −38.0% | −36.2% | −21.9% | −3.9% |
| 20% | −11.3% | −62.9% | −60.8% | −41.6% | −8.0% |
| 50% | −31.0% | −93.6% | −92.7% | −81.2% | −21.0% |
| 100% | −63.5% | −99.9% | −99.8% | −98.9% | −45.7% |

4.49 years, 77 cycles, 1,109 sessions marked, 17.1 cycles/year.

**CAGR is a choice, not a measurement.** A long straddle carries no natural
leverage, so nothing in the strategy says how much capital stands behind one.
Double the fraction and you roughly double both the loss rate and the drawdown.
The only scale-free fact is **−2.94% per cycle**.

Benchmark: SOXL returned **+151.3%** over the identical window.

## Two things the earlier numbers got wrong

**Daily marking barely moved the drawdown.** Cycle-end sampling saw the position
77 times; daily marking sees it 1,109 times, and the gap is about **one
percentage point** (−20.9% vs −19.8% at 5%). I expected worse. Intra-cycle
swings mostly resolve in the same direction by the roll, so the earlier
cycle-end figures were close to right. Reported because it was measured, not
because it changed anything.

**The capital requirement was understated.** The premium is not the capital —
the delta hedge is a stock position that needs margin on top:

| | |
|---|---|
| average premium per cycle | $10,000 |
| average hedge notional held | $5,934 |
| Reg-T margin on that at 50% | $2,967 |
| **capital per cycle** | **$12,967** |
| **ratio to premium alone** | **1.30×** |

**So every CAGR above overstates the return on capital the broker actually locks
up by ~30%.** At 5% the honest figure is nearer **−2.0%** than −2.6%. This is a
model, not a measurement — Reg-T versus portfolio margin has not been looked up.

## Data integrity, checked because these numbers depend on it

- Nearest listed strike to spot: median 0.36% away, p95 1.21%, max 3.03%. **Zero
  dates** where no strike sits within 5% of spot.
- Three day-over-day jumps above 30% in the option file's `underlying_price`
  (2022-11-10 +30.7%, 2025-04-09 +54.8%, 2026-06-05 −30.5%). All three appear at
  the same size in SOXL's independent 1-minute price file (+31.5%, +55.9%,
  −30.7%). **Real moves, not split artifacts.**
- A mishandled corporate action would show as a cluster of dates with no near
  strike, or an unexplained spot jump. Neither is present.

---

# What more data would be needed

Five gaps, ordered by how much they could change the answer.

### 1. Actual fill prices — could overturn the result

Assumption A1 pays the full quoted spread on every leg, every time, forever. The
round trip is **10.6 vol points mean** and the shortfall is under 3% of premium.
**Capturing even half the spread by working the order moves the arithmetic by
~5 vol points — more than the whole deficit.**

- *Not in this repository.* These are end-of-day quote snapshots.
- *Obtainable in a week* by quoting straddles on the paper account and recording
  where they actually fill against the touch.

### 2. Intraday option quotes — would fix the drawdown, not the return

Both drawdown columns above are EOD marks. A real intraday drawdown is worse
than either and cannot be measured from these files. On a 3× ETF whose worst
marked day at full sizing is −45.7%, that gap is not trivial.

- *Not in this repository* — V30 established these files are EOD snapshots
  (the `timestamp` column is 37% midnight placeholders and 61% unparseable in
  2024–2026; 0.07% carry a real intraday stamp).

### 3. More history — would settle significance

| | cycles | years | vs today |
|---|---|---|---|
| now | 77 | 4.49 | — |
| to reach \|t\| = 2.0 | **255** | **14.9** | 3.3× |
| to reach \|t\| = 2.6 | 431 | 25.2 | 5.6× |

**SOXL began trading 2010-03-11; these option files start 2022-01-03.** Twelve
more years exist to be bought. That would add ~206 cycles for ~283 total, cut
the standard error from 2.68% to ~1.40%, and take \|t\| to ~2.1 — just enough.

Note what this does and does not mean. The single-cell t of −1.10 is weak, but
**0 of 9 prespecified grid cells positive** is the stronger evidence, and those
cells overlap heavily so they cannot be treated as nine independent tests.

### 4. A margin schedule — needed for CAGR to mean anything

The 1.30× above is Reg-T at 50% applied by hand. IBKR's actual requirement on a
delta-hedged long straddle under portfolio margin is materially lower and has
not been looked up. *Obtainable from IBKR directly, not from any file.*

### 5. Dividends and financing — small, and both flatter the strategy

SOXL pays distributions; a short stock hedge owes them. Cash earns ~4%. Neither
is modelled (V30 A7, A8). Both are small next to a 2.94% per-cycle shortfall,
and both lean **against** the strategy, so correcting them makes the result
worse, not better. *SOXL's distribution history is public; the financing rate is
on the statement.*

## Which of these is worth doing

Only #1. It is the single assumption that could reverse the verdict, it costs a
week of paper-account quoting, and it needs no purchased data. Everything else
either sharpens a number that is already pointing the same way (#3, #4, #5) or
makes the loss look worse (#2, #5).
