# Overnight trades — SPXL and FAS evaluated independently

Follow-up to `FINDINGS.md`, which established that ~68% (SPXL) and ~83% (FAS) of six
years of return accrued between the close and the next open. That used an assumed
15:55 → 09:30 convention. This document tests whether that convention is optimal, and
whether any indicator improves on holding every night.

Scripts: `p8_overnight_timing.py`, `p9_overnight_indicators.py`, `p10_timing_robustness.py`.
Output: `../out/p8_*`, `p9_*`, `p10_*`.

---

## Bottom line

| Question | Answer |
|---|---|
| Optimal **entry**? | **15:55 — the last bar.** Robust: monotone in both symbols, in train and test separately, and in 6 of 7 years each. |
| Optimal **exit**? | **Unresolved.** SPXL is flat across 09:30–10:30. For FAS, train and test disagree completely. |
| Do **indicators** help? | **No.** Zero of 13 indicators significant at 5% in either symbol. Out-of-sample R² is **negative** for both. |
| Is the overnight edge itself significant? | **Not at 5%.** t = 1.64 (SPXL), 1.60 (FAS). Suggestive, not established. |

The one thing worth acting on is *when* to enter, not *whether* to filter.

---

## 1. Where the money actually is

Mean log return per 5-minute bar, in bp, with bootstrap 95% CIs (`p8` section A):

| segment | SPXL | FAS |
|---|---|---|
| 15:30 bar | −0.07 | **−1.47 \*** |
| 15:35 bar | **−1.99 \*** | −1.03 |
| 15:45 bar | −1.00 | **−2.72 \*** |
| 15:55 bar | −0.13 | **−2.06 \*** |
| **OVERNIGHT jump** | **+8.17** (t=1.64) | **+8.82** (t=1.60) |
| 09:30 bar | +0.79 | +4.25 (t=1.83) |
| 09:55 bar | **+1.72 \*** | **+2.91 \*** |

\* = bootstrap CI excludes zero.

Two things stand out.

**The overnight jump is 4–8× larger than any single intraday bar** — and it is *still not
statistically significant*, because its volatility is 192 bp (SPXL) / 213 bp (FAS) per
jump. A Sharpe of 0.65 over six years gives t ≈ 1.6. That is the honest status of the
whole overnight effect: economically large, statistically marginal.

**The last half-hour is where money is lost, and FAS loses much more of it.** Three of
FAS's last four measured bars are significantly negative. Whatever late-day flow drives
this — index rebalancing, MOC imbalance, leveraged-ETF rebalancing pressure — it is
stronger in the thinner fund.

Caveat: 48 bar-level tests were run and 6 came back "significant" at 5%; ~2.4 are expected
by chance. The individual bar flags should not be trusted in isolation. The *pattern* —
late-day negative, overnight positive — is what carries, and it is confirmed independently
below.

## 2. Entry timing — the robust finding

Exit fixed at the 09:30 opening print. Sharpe by entry time:

| entry | SPXL full | SPXL train | SPXL test | FAS full | FAS train | FAS test |
|---|---|---|---|---|---|---|
| 15:00 | 0.333 | −0.092 | 0.962 | 0.158 | 0.256 | −0.004 |
| 15:15 | 0.338 | −0.046 | 0.906 | 0.145 | 0.272 | −0.071 |
| 15:30 | 0.442 | 0.008 | 1.051 | 0.254 | 0.369 | 0.067 |
| 15:40 | 0.590 | 0.064 | 1.316 | 0.375 | 0.410 | 0.320 |
| 15:50 | 0.654 | 0.417 | 0.980 | 0.497 | 0.748 | 0.088 |
| **15:55** | **0.673** | **0.402** | **1.049** | **0.657** | **0.836** | **0.368** |

Monotonicity (Spearman of Sharpe against entry lateness):

| | train | test |
|---|---|---|
| SPXL | **+0.943** | +0.486 |
| FAS | **+1.000** | **+0.886** |

Positive in all four cells. FAS is perfectly monotone in training and near-perfect in test.

Year by year, latest entry versus earliest entry (exit at the open):

| year | SPXL 15:00 | SPXL 15:55 | diff | FAS 15:00 | FAS 15:55 | diff |
|---|---|---|---|---|---|---|
| 2020 | +97.4% | +115.3% | +17.8 | +111.4% | +133.2% | +21.8 |
| 2021 | +9.5% | +42.8% | +33.2 | +40.8% | +81.0% | +40.2 |
| 2022 | −55.2% | −51.9% | +3.3 | −19.7% | −17.2% | +2.5 |
| 2023 | −8.7% | +0.4% | +9.1 | −35.7% | −18.6% | +17.1 |
| 2024 | +65.2% | +56.3% | **−8.8** | +64.0% | +56.2% | **−7.8** |
| 2025 | +9.3% | +17.4% | +8.1 | −34.1% | −14.0% | +20.1 |
| 2026 | +7.0% | +12.8% | +5.8 | −55.5% | −25.9% | +29.6 |

**Late entry beat early entry in 6 of 7 years, in both symbols**, with 2024 the sole
exception in each.

### Why this claim is stronger than the effects that failed earlier

The overnight *level* is not significant (t ≈ 1.6), yet the entry *gradient* is. That is
not a contradiction — it is the difference between an absolute and a paired comparison.
Entering at 15:00 versus 15:55 shares the identical overnight jump; the difference between
them is only the 15:00→15:55 intraday leg, whose variance is an order of magnitude smaller.
That leg is worth **−9.37%/yr for SPXL (SR −0.59, t ≈ −1.45)** and **−16.31%/yr for FAS
(SR −1.03, t ≈ −2.51)**.

The FAS late-day decline is significant on its own. And unlike the volatility gate in
`FINDINGS.md`, this is not a variant selected from a grid — it is a monotone ordering
across six pre-ordered times, replicated in two instruments and two sub-periods.

**Practical note:** 15:55 is the last bar in this dataset, not the actual close. A true
MOC order fills at 16:00. The gradient says later is better, so an MOC fill should be at
least as good as the 15:55 print — but this data cannot measure the 15:55→16:00 segment,
and that is exactly the window where MOC imbalance pressure lands.

## 3. Exit timing — unresolved, and the two symbols differ

Entry fixed at 15:55:

| exit | SPXL full | SPXL train | SPXL test | FAS full | FAS train | FAS test |
|---|---|---|---|---|---|---|
| 09:30 open (auction) | 0.673 | 0.402 | 1.049 | 0.657 | **0.836** | **0.368** |
| 09:30 bar close | 0.736 | 0.539 | 1.009 | **0.870** | 0.733 | **1.110** |
| 09:35 | **0.766** | 0.534 | 1.092 | 0.757 | 0.620 | 0.994 |
| 09:45 | 0.671 | 0.499 | 0.923 | 0.667 | 0.570 | 0.835 |
| 10:00 | 0.747 | **0.570** | 1.020 | 0.769 | 0.729 | 0.848 |
| 10:30 | 0.725 | 0.472 | **1.120** | 0.791 | 0.670 | 1.007 |
| 11:00 | 0.646 | 0.448 | 0.964 | 0.776 | 0.720 | 0.882 |

**SPXL: flat.** Every exit from 09:30 to 10:30 sits in a 0.67–0.77 band full-sample and
0.92–1.12 in test. Train-selecting 10:00 delivered 1.020 in test while doing nothing at
all (exiting at the open) delivered 1.049. There is no exit edge here — take the most
liquid fill.

**FAS: train and test disagree outright.** Training says exit at the auction (0.836 vs
0.733); testing says the opposite, and emphatically (0.368 vs 1.110). Train-selection
picked the *worst* test outcome of the seven. That is the signature of noise, not signal.

The FAS open→09:30-close leg is worth +10.71%/yr at SR 0.748 full-sample, which is large
enough to demand an explanation. Two candidates, and this data cannot separate them:

1. **Real morning drift** in financials.
2. **A microstructure artifact.** FAS's opening auction is thin — median 09:30 bar
   notional $4.06M against SPXL's $19.2M. If FAS's opening print is systematically struck
   away from fair value, an MOO seller eats that, and waiting five minutes recovers it.

Both readings point the same way — *don't exit FAS at the auction* — but the magnitude is
not trustworthy, and interpretation 2 implies the gain is really an avoided cost, which
would not show up as profit against a properly measured benchmark.

## 4. Indicators — a clean null

13 indicators, each pre-specified with an economic rationale before testing: same-day
intraday return, close-in-range, 21d realized vol, 5d/21d vol ratio, RSI(14), distance
from SMA20, prior overnight return, day of week, volume ratio, VXX daily change, VXX
63d z-score, last-30-minute return, 5-day return.

**Univariate regressions (HAC errors), target = overnight return:**

| | best t-stat | significant at 5% | max R² |
|---|---|---|---|
| SPXL | −1.54 (rsi14) | **none of 13** | 0.28% |
| FAS | −1.69 (vxx_chg) | **none of 13** | 0.47% |

Not one indicator clears 5% in either symbol. Of the 26 tests, zero significant — fewer
than the ~1.3 false positives expected by chance.

**Multivariate — the decisive test.** All 13 fitted on train, predicting test:

| | in-sample R² | F-test p | **out-of-sample R²** | sign hit rate | long-when-positive test SR | ungated test SR |
|---|---|---|---|---|---|---|
| SPXL | 1.84% | 0.113 | **−1.53%** | 0.532 | 0.644 | **1.049** |
| FAS | 1.81% | 0.302 | **−3.27%** | 0.469 | 0.037 | **0.368** |

**Negative out-of-sample R² means the fitted model predicts worse than simply using the
training mean.** Trading the forecast produced test Sharpe +0.05 (SPXL) and −0.30 (FAS).
Filtering to only-when-forecast-positive underperformed holding every night in both.

**Rule backtests, clean train-select/test-evaluate over 78 rules per symbol:**

| | Spearman ρ(train SR, test SR) | rules beating ungated baseline in test |
|---|---|---|
| SPXL | +0.123 | **11 of 78 (14%)** |
| FAS | +0.224 | 34 of 78 (44%) |

For SPXL, only 14% of indicator rules beat simply holding every night — far *below* the
~50% expected if indicators were merely useless. Conditioning actively destroys value:
almost any filter removes good nights along with bad ones and gives up more return than
risk. The train-selected SPXL winner (`rv21:bot50`) posted test Sharpe 1.64 and ranked 2nd
of 78 — but it is the same volatility-gate hypothesis that failed the clean protocol in
`FINDINGS.md`, the rank correlation supporting it is only +0.12, and 86% of its sibling
rules lost to doing nothing. I do not treat it as established.

**Day of week** shows no stable pattern. SPXL Monday: +22.2 bp in train, −6.0 bp in test.
FAS Monday: +38.3 bp train, −0.8 bp test. Signs flip between halves for both.

## 5. The recommended trade, net of cost

Entry at the 15:55 close, 252 round trips per year:

| | ann. return | ann. vol | Sharpe | max DD | hit rate | worst night | **break-even** |
|---|---|---|---|---|---|---|---|
| SPXL → 09:30 auction | +20.58% | 30.56% | 0.673 | −54.0% | 55.7% | −12.88% | **8.17 bp** |
| SPXL → 09:30 bar close | +22.36% | 30.39% | 0.736 | −53.6% | 55.7% | −12.43% | **8.87 bp** |
| FAS → 09:30 auction | +22.24% | 33.87% | 0.657 | −51.6% | 55.1% | −12.65% | **8.82 bp** |
| FAS → 09:30 bar close | +33.07% | 38.03% | 0.870 | −57.4% | 54.3% | −11.69% | **13.12 bp** |

Sharpe net of round-trip cost:

| | 1 bp | 2 bp | 3 bp | 5 bp | 8 bp |
|---|---|---|---|---|---|
| SPXL → auction | 0.591 | 0.509 | 0.426 | 0.261 | 0.014 |
| SPXL → 09:30 close | 0.653 | 0.570 | 0.487 | 0.321 | 0.072 |
| FAS → auction | 0.582 | 0.508 | 0.433 | 0.285 | 0.061 |
| FAS → 09:30 close | 0.803 | 0.737 | 0.671 | 0.538 | 0.340 |

**SPXL** is the more defensible of the two: tighter spreads, 7× the liquidity, a flat exit
surface (so execution can be optimized for fill quality rather than timing), and a
break-even near 8–9 bp.

**FAS** shows better gross numbers but they rest on the exit choice that train and test
disagree about, and its capacity ceiling is roughly $47K per position against SPXL's
$510K (`FINDINGS.md`, Phase 0). The higher FAS break-even is real but is partly
compensation for a worse fill environment, not free money.

## 6. What would change these conclusions

1. **Real fill data.** Break-even is 8–13 bp and this repo has no quote data. That single
   input decides whether any of this is tradeable. Nothing else on this list matters as much.
2. **The 15:55→16:00 window.** The dataset stops at 15:55. The entry gradient says later is
   better, but the final five minutes — where MOC imbalances print — is invisible here.
   One month of 1-minute or tick data through 16:00 would settle it.
3. **FAS opening auction quality.** Auction prints versus the consolidated NBBO at 09:30
   would separate "morning drift" from "bad auction fill" and resolve the FAS exit.
4. **Sample length.** t ≈ 1.6 on the overnight effect. Six years is not enough. This
   improves only with time, not with more analysis.

## 7. Honest summary of the evidence

- The **entry rule is well-supported**: monotone in two symbols, two sub-periods, and 6 of
  7 years each. Act on it.
- The **exit rule is not identified** for FAS and does not matter for SPXL.
- **Indicators do not help.** Thirteen tested, none significant, negative out-of-sample
  R², and for SPXL, gating is actively harmful 86% of the time.
- The **overnight effect itself is marginal at t ≈ 1.6** and, per `FINDINGS.md`, does not
  clear a Deflated Sharpe of 0.95.

The strongest honest statement available: *if* you are going to hold SPXL or FAS overnight,
enter as late as you can and do not filter. Whether you should hold them overnight at all
depends on a transaction cost this dataset cannot measure.
