# The options gap — what I tested, what I didn't, and what the data says

**I overstated the earlier conclusion.** "Nothing tradeable" was the summary of
five tests that were all the *same* test: does the price go up. That is the
delta-one question, and it is not what an option answers.

This document says exactly what was and was not tested, then measures the one
thing every option strategy depends on. The short version: **volatility is
substantially forecastable at 1–5 days (OOS R² 0.46 / 0.35), which is the
opposite of what I implied.** Whether that is *tradeable* is a different
question, and it is one this repository cannot currently answer.

---

## 1. What was actually tested

| test | what it asked | result |
|---|---|---|
| band_lab sleeve on UVXY | buy dips, does price rise | −1.8 bp/ON-day net |
| SMA z-score → forward return | does price rise | null |
| term-structure z → forward return | does price rise | null |
| FX → forward return | does price rise | null |
| 2σ event → forward return | does price rise | null |

All five are **long-only, delta-one, directional**. Every one asks about the
*mean* of the return distribution.

## 2. What was not tested

Options are not priced off the mean. They are priced off the rest of the
distribution, and I measured none of it against a strategy:

| dimension | what monetises it | tested? |
|---|---|---|
| **magnitude** (variance) | straddles, strangles, delta-hedged gamma | **no** |
| **carry** (contango/roll) | calendars, diagonals, covered calls | **no** |
| **skew** (tail asymmetry) | risk reversals, ratio spreads, put spreads | **no** |
| **convexity** (vol-of-vol) | back/front spreads, butterflies | **no** |
| **term structure of vol** | calendar spreads across expiries | **no** |

And I had already *measured* the raw material for all five without connecting
it: vol mean-reverts (`DRIVERS.md` §1.1), 2σ events cluster 3.9×
(`two_sigma.py` §C), the roll costs −44%/yr (`WHAT_UVXY_IS.md` §[2→3]), the
tail is 15:1 up at 4σ, and front-month vol-of-vol is 3.25× the fifth month.
Every one of those is a statement about something other than direction.

**You were right to push on this.**

---

## 3. Volatility is forecastable — and I said the opposite

`vix_lab/vol_forecast.py`. Realised variance computed from the **1-minute**
file (sum of squared intraday returns), which is a far better estimator than
close-to-close. Benchmark is HAR-RV: tomorrow's log RV on today's, the
trailing week's, and the trailing month's. Out-of-sample refits each January
on prior data only.

| horizon | n | in-sample R² | **OOS R²** | random-walk R² | corr(pred, actual) |
|---|---:|---:|---:|---:|---:|
| 1 day | 1,147 | 0.478 | **0.456** | 0.313 | **0.677** |
| 5 days | 1,143 | 0.388 | **0.345** | −0.074 | 0.598 |
| 22 days | 1,126 | 0.161 | **0.024** | −1.296 | 0.321 |

At 1 and 5 days this is a real, out-of-sample, model-beats-benchmark result.
At 22 days it collapses.

### Correcting the earlier claim

`DRIVERS.md` §1.1 reported corr **0.152** between trailing and forward 20-day
close-to-close vol, and I read it as "vol is barely forecastable." That
reading was too harsh on two counts: it used the noisiest possible estimator
(close-to-close) at the single hardest horizon (~22 days), and it compared
trailing vol to forward vol rather than a model to a benchmark.

Measured properly, **volatility is the most forecastable thing about UVXY** —
far more so than its direction, which was not forecastable at all. The
mean-reversion result in `DRIVERS.md` §1.1 stands (trailing vol is a
contrarian indicator at 20 days); the *interpretation* was wrong.

---

## 4. But forecastable ≠ tradeable, and this is the honest blocker

A short-vol structure earns **implied minus subsequently realised**. My
forecast of RV is only worth something if it beats the forecast already
embedded in the option price. R² = 0.46 against a random walk is necessary;
it is not sufficient.

The live snapshot is not encouraging on this name today:

| IBKR, UVXY, 2026-08-04, spot 23.11 | |
|---|---:|
| implied vol (annual) | **84.5%** |
| 30-day historical vol | **84.8%** |
| **implied − historical** | **−0.3%** |
| IV percentile, 52-week | 23.6% |
| percentile of 84.5% in the realised distribution | 55.4% |

**The premium is roughly zero right now** — implied is *below* trailing
realised. The classic "sell expensive vol" thesis is not visibly available on
UVXY at this moment.

One snapshot is not a study. But it is enough to say that assuming a fat
variance risk premium on this ticker would be an assumption, not a finding.

---

## 5. What the realised distribution says about structure

Model-free, from the underlying alone — no option data needed. This is what a
short at-the-money straddle had to collect to break even:

| holding | mean \|move\| | median | p90 | p99 | max |
|---|---:|---:|---:|---:|---:|
| 1 session | 4.8% | 3.3% | 10.3% | 26.2% | 62.0% |
| 5 sessions | 10.4% | 7.5% | 21.1% | 61.3% | 151.0% |
| 22 sessions | **24.1%** | **17.5%** | 37.4% | **190.9%** | **935.4%** |

The gap between mean (24.1%) and median (17.5%) at one month *is* the skew.
A seller collecting the median wins most months and is destroyed by the tail.

Split by direction, which is where the structures diverge:

| holding | mean up move | mean down move | P(up) | up tail p99 | down tail p99 |
|---|---:|---:|---:|---:|---:|
| 5 sessions | +13.4% | −8.9% | 35.1% | +104.8% | −31.2% |
| 22 sessions | **+36.2%** | **−19.3%** | **28.7%** | **+580.0%** | **−46.2%** |

**The whole options problem in one line: the side that wins most often is the
side that loses most per event.** At one month UVXY rises only 28.7% of the
time, and when it does it goes 1.9× as far — with a 99th-percentile up tail
of +580% against a down tail bounded at −46% (a share price cannot go below
zero, and the roll only bleeds so fast).

### What this supports, and how confidently

| structure | the measured basis | confidence |
|---|---|---|
| **Short calls / call spreads, naked** | +580% p99 up tail, 15:1 up-tail ratio at 4σ | **avoid** — this is the XIV/Feb-2018 shape |
| **Defined-risk only, on any short-vol leg** | mean ≫ median at every horizon | **strong** — structural, not regime-dependent |
| **Put-side premium** | bounded −46% downside vs unbounded upside | **plausible** — the tails are genuinely asymmetric, but the −44%/yr roll is public and priced |
| **Calendars / diagonals** | vol forecastable at 1–5d but not 22d; vol-of-vol 3.25× front vs 5th | **plausible, untested** — the term structure of forecastability is real |
| **Long gamma into a cluster** | P(2σ \| 2σ yesterday) = 26.4% vs 6.8% base | **plausible, untested** — clustering is strong and measured |
| **Any naked short-vol carry trade** | VRP measured at −0.3% today | **not supported by anything measured** |

Everything in the "plausible, untested" rows is a hypothesis with a measured
motivation. **None of them has been backtested.** I am not going to present
them as findings.

---

## 6. What is missing, precisely

To test any of the above properly this repository needs, for UVXY:

1. **Historical option chains with IV** — the SOXL equivalent already exists
   (`SOXL_1Yr_Options_Greeks_EOD.csv`, full greeks, from
   `soxl_options_greeks_*.py`). The same fetchers point at IBKR and would work
   for UVXY with a symbol change. **This is the binding constraint** — without
   an IV history the variance risk premium cannot be measured, and every
   structure above is untestable.
2. **Bid/ask, not mid.** UVXY options are wide. `COST_MODEL.md` already shows
   what happens to a thin edge under real spreads on the *equity*; options are
   worse by a wide margin.
3. **Assignment and early-exercise handling** for American-style short legs.

The existing options infrastructure in this repo — `put_diagonal_backtest.py`,
`call_diagonal_backtest.py`, `r3_iron_condor_backtest.py`,
`volatility_pricing_lab.py` — is substantial and was built for SOXL. It is the
natural place to run this once the data exists.

---

## 7. Where I actually land

- The **directional null stands**. It rules out the simple things, and that is
  worth having: it is why the band_lab sleeve on UVXY loses money.
- **"Nothing tradeable" was wrong as stated.** It should have read: *no
  directional delta-one edge, and the non-directional cases were not
  examined.*
- **Volatility is forecastable at 1–5 days** (OOS R² 0.46 / 0.35, beating a
  random walk). That is a genuine result and it is the precondition for vol
  trading.
- **Whether it is tradeable turns on the variance risk premium, which I cannot
  measure without an IV history.** The single live snapshot shows a premium of
  −0.3%, which argues against assuming one exists on this name.
- The distribution's asymmetry is severe enough that **any short-vol structure
  on UVXY should be defined-risk**, and the call side is the one that kills.

The honest next step is not a strategy. It is fetching a UVXY option history
and measuring the premium — after which the structures above become testable
instead of arguable.
