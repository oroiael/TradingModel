# What precedes a UVXY move?

Four questions, measured on the 1,654-session 1-minute file plus IBKR daily
references. Short answers first:

| question | answer |
|---|---|
| Does it mean-revert against an SMA? | **No — not in price.** The strong-looking result is an overlapping-window artifact. **Volatility** mean-reverts hard, which is a different thing |
| Does it move before, during, or after FOMC? | **All three, in a specific and repeatable shape** — quiet before, 3× at 14:00, a *second* 2.5–3.8× shock at the 14:30 presser |
| Does it track FX? | **No.** Raw correlation ~0.13; controlling for SPY it vanishes; zero lead |
| What does drive it? | Same-day equities (R² 0.58, β −4.62, asymmetric 1.44×) and the futures curve — both **contemporaneous, not leading** |

The honest headline: **almost nothing leads UVXY.** The one exception is the
calendar — and the FOMC effect is stronger in SOXL and SOXS than in UVXY,
which makes it the only operationally useful finding here.

---

## 0. The trap that decides every answer

UVXY loses ~67%/yr. Any long-only statistic looks terrible and any short-only
statistic looks brilliant whether or not the signal carries information. So
every number below is a **spread between buckets of the same signal**, or is
quoted against the unconditional mean of the same sample.

A second trap caught my own first pass. A 20-day forward return sampled daily
overlaps 20:1, which inflates t-statistics by roughly √20. Both a
Newey-West correction and a non-overlapping resample are reported, and they
change the conclusion.

---

## 1. Mean reversion against an SMA — no

`vix_lab/drivers.py` §1, `fomc_and_drag.py` §B. Signal is the z-score of close
vs SMA_N, lagged one day. Top-quintile minus bottom-quintile forward return:

| signal | target | TOP−BOT | naive t | **Newey-West t** | **non-overlapping t** |
|---|---|---:|---:|---:|---:|
| SMA50 z | UVXY | −1,306 bp | −7.65 | −2.41 | **−1.77** |
| SMA50 z | VIXY | −875 bp | −6.52 | −2.28 | **−0.10** |
| SMA200 z | UVXY | −877 bp | −5.05 | −1.28 | **−0.41** |
| SMA200 z | VIXY | −429 bp | −3.38 | −0.88 | **−0.74** |
| term-structure z | UVXY | −1,625 bp | −7.57 | −2.59 | **−1.08** |
| term-structure z | VIXY | −1,023 bp | −6.83 | −2.43 | **−1.03** |

The naive column looks like a discovery. It is not. With ~60 genuinely
independent 20-day windows, **nothing reaches significance.** The signs are
all negative and consistent with theory, so there may be a real effect — the
sample simply cannot establish it.

At 1-day and 5-day horizons there is nothing at all: daily autocorrelation is
−0.061 at lag 1 and under 0.05 at every other lag, and no SMA quintile table
shows a monotone pattern.

### 1.1 But volatility mean-reverts violently

This is the real effect, and it is not the same claim:

| trailing 20d vol | → next 20d vol | ratio |
|---:|---:|---:|
| 0.32 | 0.65 | **2.02×** |
| 0.43 | 0.51 | 1.17× |
| 0.55 | 0.57 | 1.03× |
| 0.69 | 0.65 | 0.95× |
| 1.11 | 0.72 | **0.65×** |

corr(trailing, forward) = **0.152**. Trailing realised vol is close to a
*contrarian* indicator of forward vol at a one-month horizon.

### 1.2 What that mean reversion actually buys you: drag, not direction

A 1.5× daily-rebalanced fund gives up ≈ 0.375·σ² per unit time to
rebalancing, in every direction. Measuring UVXY's shortfall against 1.5×VIXY
and predicting it from **realised forward** vol:

| trailing vol | forward vol | actual shortfall | predicted −0.375σ²t |
|---:|---:|---:|---:|
| 0.32 | 0.65 | −176 bp | −125 bp |
| 0.43 | 0.51 | −101 | −76 |
| 0.55 | 0.57 | −129 | −97 |
| 0.69 | 0.65 | −167 | −127 |
| 1.11 | 0.72 | −193 | −152 |

Predicted lands at a consistent ~72–76% of actual in every bucket, the
remainder being expense and roll. **UVXY's underperformance of its own index
is arithmetic, not a forecastable trend.** Using *trailing* vol instead
misfits badly (−31 vs −176 at the low end, −366 vs −193 at the high end) —
and that misfit is itself the mean reversion in §1.1.

---

## 2. FOMC — the one thing that genuinely leads, because it is a calendar

`fomc_and_drag.py` §A. 52 scheduled statement days in sample. **The date list
validates itself against the data**: ranking all 1,654 sessions by the
14:00–14:05 move, FOMC days sit at median percentile **82.8%** against 48.9%
for every other session, and **21 of 52 land in the top decile** where chance
would put 5.

Mean |log return| by window, FOMC days ÷ all other sessions:

| window | UVXY | what it means |
|---|---:|---|
| 09:30–11:00 | 0.84× | quieter than normal |
| 11:00–13:00 | 0.64× | **much** quieter |
| 13:00–13:55 | 0.62× | quietest window of the day |
| **13:55–14:00** | **3.29×** | it starts *before* the release |
| **14:00–14:05** | **2.95×** | the statement |
| 14:05–14:30 | 1.19× | lull |
| **14:30–15:00** | **2.53×** | the press conference — a second, comparable shock |
| 15:00–15:55 | 1.89× | still elevated; largest signed move of the day (+108 bp) |

So: **before, during and after — but the "before" is a hush, not a move.**
UVXY drifts *down* into the announcement (−108 bp open→14:00, against −10 bp
on a normal day), which is the pre-event vol crush, then reprices in two
distinct steps at 14:00 and 14:30.

The 13:55–14:00 window is the single largest multiple in the table. That is
positioning ahead of a known release, not leakage.

Daily returns around the event (close-to-close):

| | t−2 | t−1 | t+0 | t+1 | t+2 |
|---|---:|---:|---:|---:|---:|
| mean bp | −97 | −115 | −105 | +133 | +40 |
| median bp | −187 | −37 | **−284** | −57 | −15 |

The median t+0 of −284 bp is the vol crush; the positive t+1 *mean* against a
negative median is a handful of outliers, not a tendency.

For contrast, the two unscheduled 2020 actions behaved nothing like this —
2020-03-03 ran **+1,383 bp before 14:00** and 2020-03-16 **+1,183 bp after**.
Scheduled and unscheduled Fed events are different animals.

### 2.1 This matters more for SOXL/SOXS than for UVXY

`fomc_and_drag.py` §C. The same signature is **stronger** in the two approved
sleeves:

| window | UVXY | **SOXL** | **SOXS** |
|---|---:|---:|---:|
| 09:30–11:00 | 0.84 | 0.64 | 0.65 |
| **11:00–13:55** | 0.56 | **0.48** | **0.50** |
| 13:55–14:00 | 3.31 | 3.52 | 3.51 |
| 14:00–14:05 | 2.97 | 3.16 | 3.38 |
| **14:30–15:00** | 2.55 | **3.62** | **3.79** |
| 15:00–15:55 | 1.90 | 2.21 | 2.26 |

§2.3 forbids orders before 11:00, so the sleeves are exposed to exactly the
wrong half of this. On the eight FOMC days a year their prime window runs at
**half** normal volatility — the 1% dip trigger rarely fires and the anchor
sits low and stable — and is then hit by a **3.5×** burst from 13:55 into the
close. That is the configuration most likely to arm a low anchor in the quiet
and then run it into the −4% stop.

**This is an observation, not a proposed rule change.** §12 is locked and
V16–V18 rejected every re-tuning they tried. But it is 8 predictable days a
year, and it is worth knowing before reading a paper-run week that contains
one.

---

## 3. FX — no

`drivers.py` §3, 1,250 sessions from 2021-08. UUP is a dollar-index ETF, FXY a
yen ETF.

| pair | raw corr | **partial, SPY removed** |
|---|---:|---:|
| UVXY vs SPY | −0.7619 | — |
| UVXY vs UUP (dollar) | +0.1262 | **−0.1027** |
| UVXY vs FXY (yen) | +0.1397 | **+0.1906** |

Lead/lag, corr(UVXY_t, FX_{t−k}):

| k | UUP | FXY | SPY |
|---:|---:|---:|---:|
| 0 | +0.126 | +0.140 | −0.762 |
| **+1** | **+0.008** | **−0.013** | +0.032 |
| +2 | −0.021 | +0.061 | +0.037 |

**Zero lead.** Forward quintile tests on both are null (TOP−BOT t = +1.09 and
−0.29). The small same-day correlation is the equity channel, and it does not
survive removing it. UVXY does not track FX in any usable sense.

The intuition that says otherwise comes from 2024-08-05 — a genuine yen-carry
unwind where UVXY ran +62%. That was one day. One day does not make a
relationship, and the sample contains 1,250 of them.

---

## 4. What actually moves it: same-day equities, asymmetrically

| | |
|---|---:|
| beta of UVXY to SPY | **−4.62** |
| R² | **0.580** |
| beta on SPY-**up** days | −3.82 |
| beta on SPY-**down** days | −5.50 |
| ratio | **1.44×** |

58% of UVXY's daily variance is same-day SPY, and the down-day beta is 1.44×
the up-day beta — that convexity is the entire reason a vol product is not
just a levered short index.

But this is a **decomposition, not a forecast**: contemporaneous corr with the
term-structure ratio is **+0.9602**. The curve does not predict UVXY, it *is*
UVXY, measured a different way.

The tail days show why headlines resist systematic treatment — the largest
UVXY days are not the largest SPY days:

| date | UVXY | SPY | ratio | |
|---|---:|---:|---:|---|
| 2024-08-05 | +62.0% | −2.91% | **21×** | yen carry unwind |
| 2021-11-26 | +39.0% | −2.23% | 17× | Omicron |
| 2025-04-03 | +37.0% | −4.93% | 7.5× | tariff shock |
| 2025-04-04 | +29.7% | −5.85% | **5.1×** | tariff shock, day 2 |

2024-08-05 produced twice the UVXY move of 2025-04-04 on **half** the SPY
move. What differs is positioning and the level of implied vol going in — the
vol-of-vol channel — and neither is in a price file.

---

## 5. So what is worth acting on

1. **Nothing here is a tradeable UVXY signal**, which is consistent with
   `UVXY_EVALUATION.md`: the instrument was already rejected on edge and cost.
2. **The FOMC calendar is the one real finding**, and it is about SOXL/SOXS.
   Eight days a year, known years in advance, where the sleeves' tradeable
   window is half-dead until 13:55 and then triples.
3. **Do not trust a backtest t-statistic built on overlapping windows.** The
   same numbers read −7.65 or −1.77 depending only on whether the overlap is
   handled, and this project has a history of taking the harsh reading.

### Not done

- No intraday FX. The lead/lag test is daily; a 1-minute USDJPY series could
  in principle show a lead that daily data averages away. I doubt it, but it
  is untested.
- **No causal claim about FOMC direction.** The volatility result is strong;
  the signed drift (−108 bp into the announcement) is a mean over 52 events
  and is not separated from the general vol-crush pattern around any scheduled
  event. Earnings and CPI days were not tested.
- The VIX **spot** index is unavailable — IBKR returns "Details currently
  unavailable" for conid 13455763 — so every volatility series here is a
  futures product. That is the correct basis for UVXY, but it means "does VIX
  itself mean-revert" is not answered, only "do VIX futures products".

---

## Reproducing

```bash
python3 vix_lab/fetch_refs.py        # freeze the IBKR daily references
python3 vix_lab/drivers.py           # §1 SMA, §2 curve, §3 FX, §4 equities
python3 vix_lab/fomc_and_drag.py     # §2 FOMC, §1.1-1.2 the drag control
```
