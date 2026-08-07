# ETF Group Analysis — Test Plan

**Instruments:** `VXX_5min_6Years.csv`, `FAS_5min_6Years.csv`, `SPXL_5min_6Years.csv`
**Objective:** determine whether these three can be traded as an active basket, at what
frequency, and with what holding period — or whether they cannot.
**Written before any test was run.** Results live in `../out/` and `FINDINGS.md`.

---

## 0. Naming correction

The request named `FAX_5min_6Years.csv`. **No such file exists in this repository.**
FAX is a real ticker (abrdn Asia-Pacific Income Fund, a leveraged closed-end bond fund) but
there is no FAX data here. The file present is `FAS_5min_6Years.csv` — Direxion Daily
Financial Bull 3X. This plan uses **FAS**. If FAX was actually intended, the data must be
sourced and this entire plan re-run; a bond CEF would change nearly every hypothesis below.

## 1. What these three instruments actually are

| | SPXL | FAS | VXX |
|---|---|---|---|
| Type | ETF | ETF | **ETN** (unsecured Barclays debt) |
| Exposure | 3× S&P 500 (daily) | 3× Russell 1000 Financials (daily) | Long front VIX futures, ~30d constant maturity |
| Reset | Daily | Daily | Daily roll |
| Structural drift | Negative (variance drag) | Negative (variance drag) | **Strongly negative** (contango roll yield) |
| Credit risk | None (holds assets) | None | **Yes** — Barclays counterparty |

This composition matters more than any statistic below. Two of the three are 3× levered
long-beta funds on **overlapping** underlyings — financials are ~13% of the S&P 500 and are
high-beta to it. The third is a structurally decaying short-risk proxy. My prior, before
testing, is that **this is close to one bet plus a hedge**, not three independent assets.
Phase 2 is designed to falsify or confirm that.

### Structural events that must be checked, not assumed

- **VXX reverse splits.** VXX has split 1:4 repeatedly. The file opens at $1,849.60 on
  2020-07-23 and ends at $22.22 — VXX actually traded near $28 in July 2020. That ~66×
  implies the series is back-adjusted, but it must be verified, not believed.
- **Barclays suspended VXX creations in March 2022**, and VXX traded at a large premium to
  NAV for weeks. Any 2022-window result is suspect until the data is inspected for it.
- **SPXL/FAS forward splits.** Both have split historically. Same verification required.

If any series is on a broken basis, every return, correlation and Sharpe below is garbage.
This repo already learned that the expensive way — `band_lab/live/PHASE2_PARITY.md` documents
the "S7 failure" where a wrong SOXS basis silently zeroed 248 sessions without erroring.

---

## 2. Priority scheme

| Priority | Meaning |
|---|---|
| **P0** | Blocking. Downstream results are invalid if this fails. Must pass before Phase 1. |
| **P1** | Core. Directly answers the frequency / holding-period question. |
| **P2** | Strategy hypotheses. Only meaningful if P0/P1 support them. |
| **P3** | Exploratory / non-standard. Run last, treated as hypothesis-generating only. |

---

## Phase 0 — Data integrity and basis (P0, blocking)

### T0.1 Session grid completeness
**Purpose.** Establish the tradeable calendar: bars per session, missing bars, half-days,
and whether the 09:30–15:55 grid is complete. Backtests silently mis-align when bars are
missing, and a missing 15:55 bar breaks any end-of-day exit rule.
**Method.** Bar counts per session, first/last stamp per session, gap scan over trading days.
**Expected.** ~1,500 sessions, 78 bars/day, ~12 half-days at 42 bars — matching the SOXL
files' documented structure. Anything else means these files were fetched differently.
**Standard?** Yes — baseline data QA.

### T0.2 Corporate-action and adjustment-basis scan
**Purpose.** Detect splits and determine whether each series is raw or back-adjusted.
**Method.** Overnight ratio `open[t] / close[t-1]` for every session boundary; flag outside
[0.6, 1.7]; test flagged ratios against integer split factors (1:4, 4:1, 3:1, 1:10 …).
Cross-check flagged dates against the magnitude of intraday moves on the same day.
**Expected.** VXX: several 1:4 reverse splits, *or* none if pre-adjusted. SPXL/FAS: possible
forward splits. A clean back-adjusted series shows **zero** unexplained boundary jumps.
**Decision rule.** Any unexplained jump > 1.7× or < 0.6× that is not a split → that date
range is quarantined and excluded, and the exclusion is stated in the findings.
**Standard?** Yes — mandatory and routinely skipped by retail backtests.

### T0.3 Cross-file alignment
**Purpose.** The basket can only trade on bars where all three exist. Define that intersection.
**Method.** Set operations on session dates and on full 5-min timestamps.
**Expected.** High overlap. `SPXL_5min_6Years.csv` is known to end mid-session (last bar
13:55 on 2026-07-22) — a truncated final session that must be dropped, not silently used.
**Standard?** Yes.

### T0.4 Liquidity and capacity profile
**Purpose.** Decide whether an intraday strategy is *executable*, not just profitable on paper.
An edge of 8bp/trade is irrelevant if the bar cannot absorb the order.
**Method.** Dollar volume per bar by time-of-day; median and 5th-percentile bar notional;
implied max order size at 1% / 5% / 10% of bar volume; Amihud illiquidity ratio per instrument.
**Expected.** SPXL and VXX liquid; FAS materially thinner. If FAS's median midday bar is
small, FAS caps the whole basket's size.
**Standard?** Volume profiling is standard. Framing it as an explicit **capacity ceiling in
dollars** is buy-side execution research and is rare in retail analysis.

### T0.5 Microstructure noise / signature plot
**Purpose.** Determine the fastest sampling frequency at which returns carry signal rather
than bid-ask bounce. This sets the floor on trading frequency.
**Method.** Realized variance as a function of sampling interval (5min → 1 day). Under pure
efficiency RV is flat in the sampling interval; noise makes it explode at high frequency.
Also: Roll's implied spread and the Corwin-Schultz high-low spread estimator.
**Expected.** RV inflated at 5-min for FAS (thinnest), less so SPXL/VXX. Corwin-Schultz gives
a spread estimate we otherwise **cannot** obtain — see §6 limitations.
**Standard?** Signature plots are standard in academic high-frequency econometrics and
essentially **unheard of in retail ETF analysis**. Corwin-Schultz likewise.

---

## Phase 1 — Independent characterization (P1)

### T1.1 Return distributions and stylized facts
**Purpose.** Baseline risk. Establishes whether standard (Gaussian) risk math is even valid.
**Method.** Log returns at 5min/30min/daily. Moments, Jarque-Bera, ACF of returns and of
|returns|, Ljung-Box, tail index (Hill estimator).
**Expected.** Near-zero return autocorrelation; strong |return| autocorrelation (vol
clustering); heavy tails everywhere. SPXL/FAS negatively skewed, **VXX positively skewed** —
the sign of the skew is what makes VXX a hedge rather than an asset.
**Standard?** Yes, textbook.

### T1.2 Intraday seasonality
**Purpose.** Directly answers *when* to trade. The user wants "quick opportunities" — this
locates them in the clock.
**Method.** Mean return, realized vol, volume and range by each of the 78 5-min buckets,
with bootstrap confidence bands. Day-of-week overlay.
**Expected.** U-shaped vol and volume, midday lull. Any *mean return* pattern is far more
likely noise than edge — bootstrap bands are there to keep me honest about that.
**Standard?** Yes.

### T1.3 Variance ratio and Hurst exponent — **the central test**
**Purpose.** This single test answers "what is the natural holding period." VR(q) < 1 means
mean-reverting (fade moves, hold minutes); VR(q) > 1 means trending (ride moves, hold longer).
**Method.** Lo-MacKinlay variance ratio with heteroskedasticity-robust test statistics at
q = 2, 3, 6, 12, 78 (one day), 390 (one week). Hurst via DFA. Run per instrument.
**Expected.** Mean reversion at the fastest scales (partly microstructure, not tradeable),
drifting toward random walk at daily. If anything shows VR > 1 at the multi-hour scale that
is the most interesting finding available in this dataset.
**Standard?** Yes — Lo-MacKinlay is the canonical test. DFA is imported from physics and is
non-standard for ETFs.

### T1.4 Overnight vs intraday return decomposition
**Purpose.** Decides whether an *intraday* strategy is even the right product. If 100% of
these instruments' return accrues overnight, day-trading them is fighting for scraps and the
correct answer to the user's question is "hold, don't trade."
**Method.** Split cumulative log return into close→open (overnight) and open→close (RTH).
Per instrument, per year. Include Sharpe of each leg separately.
**Expected.** For levered equity longs, published work finds the equity premium concentrates
overnight. If that holds here, it is a direct argument *against* the stated strategy — and it
must be reported as such, not buried.
**Standard?** Yes, well documented ("the night effect").

### T1.5 Volatility regimes
**Purpose.** Edges are rarely constant; they concentrate in regimes. Identify them so
Phase 3 can condition on them.
**Method.** GJR-GARCH(1,1) with skew-t errors on daily returns; 2- and 3-state Gaussian HMM
on realized vol; PELT change-point detection on the vol series.
**Expected.** 2–3 clear regimes; COVID tail, 2022 bear, 2024–26 whatever the data shows.
**Standard?** GARCH yes. HMM regime-switching is standard in quant research, uncommon retail.
Change-point detection on vol is non-standard.

### T1.6 Leverage-drag decomposition (SPXL, FAS)
**Purpose.** Quantify the cost of holding a 3× fund longer than one day. For a daily-reset
L× fund, log drift ≈ `L·μ − ½·L(L−1)·σ²`. That second term is a *mechanical* headwind that
grows with volatility and is the reason these products are labelled for daily holding.
**Method.** De-lever the series (`r_1x ≈ r_3x / 3`), rebuild a synthetic 1× index, compound
it forward at 3× daily, compare to the actual fund path. The divergence *is* the path-
dependency cost. Also compute the theoretical drag term from realized σ and compare.
**Expected.** Meaningful annual drag; larger for FAS if financials are more volatile.
**Standard?** Standard in levered-ETF academic literature; **rare** in practitioner backtests,
which routinely treat SPXL as if it were 3× SPY over any horizon. It is not.
**Honest limitation.** There is no SPY or XLF file in this repo, so the 1× series must be
*reconstructed* from the fund itself. This validates internal consistency and quantifies the
drag identity, but it cannot verify tracking against the true benchmark.

### T1.7 VXX decay and payoff asymmetry
**Purpose.** Establish what VXX *is* for a trader: an asset, a hedge, or a lottery ticket.
**Method.** Distribution of n-day holding-period returns for n = 1…20: median, mean, hit
rate, skew, best/worst. Annualized decay rate. Time-to-halving. Conditional payoff on days
when SPXL falls > 1%, > 2%, > 3%.
**Expected.** Median return negative at every horizon, mean dragged positive only by a thin
right tail, hit rate well below 50%. That profile means VXX must be **sized as insurance with
a known premium**, never held as a position expecting a return.
**Standard?** Roll-yield analysis is standard for volatility products and **completely absent**
from ordinary ETF screening. Anyone treating VXX like a normal ETF is mispricing it.
**Honest limitation.** No VIX futures term structure in the repo, so contango cannot be
separated from spot VIX moves. Only the *net* realized decay is measurable.

---

## Phase 2 — Collective / pairwise analysis (P1)

### T2.1 Correlation across horizons and through time
**Purpose.** Is this three bets or one? Does diversification hold when it is needed?
**Method.** Pearson and Spearman at 5min / 30min / daily; 60-day rolling correlation;
correlation computed separately per volatility regime from T1.5.
**Expected.** SPXL–FAS very high (0.8–0.95 daily). VXX–SPXL strongly negative. Correlations
intensifying in stress — which *helps* the VXX hedge and *hurts* the SPXL/FAS diversification.
**Standard?** Yes.

### T2.2 Tail / exceedance correlation
**Purpose.** Average correlation is the wrong statistic for a strategy that dies in tails.
Measure correlation conditional on being in the worst/best decile of moves.
**Method.** Exceedance correlation curves; lower/upper tail dependence coefficients.
**Expected.** SPXL–FAS correlation rising toward 1 in selloffs (diversification evaporates
exactly when needed); VXX–SPXL becoming more negative and convex.
**Standard?** Standard in risk management, non-standard in ETF/basket selection.

### T2.3 Cointegration and pairs testing (SPXL vs FAS)
**Purpose.** Test for a tradeable stat-arb spread.
**Method.** Engle-Granger and Johansen on log prices; ADF on the residual; Ornstein-Uhlenbeck
fit for mean-reversion half-life; rolling hedge ratio via Kalman filter.
**Expected — and this is a prediction I expect to be *rejected*.** Two daily-reset 3× funds
on different underlyings are **not** theoretically cointegrated: path dependence guarantees
the ratio drifts without an error-correction mechanism. I expect no cointegration on the
levered prices. I will then re-test on the *de-levered reconstructed* series from T1.6, where
cointegration is theoretically plausible. If the de-levered pair cointegrates but the levered
pair does not, the honest conclusion is that the spread is real but **not tradeable with these
instruments** — a genuinely useful negative result.
**Standard?** Cointegration is standard. Applying it to levered ETFs is a well-known trap;
identifying the trap is the value here.

### T2.4 Lead-lag structure
**Purpose.** Any exploitable ordering — does VXX move before SPXL? Do financials lead the index?
**Method.** Cross-correlation of 5-min returns at lags ±12 bars; Granger causality with
HAC standard errors; repeat on 1-min-equivalent aggregation where possible.
**Expected.** Overwhelmingly contemporaneous. Any measured lead-lag at 5-min resolution must
be compared against the estimated spread from T0.5 — a 2bp lead is unexploitable if the
round-trip cost is 6bp. **A statistically significant lead-lag is not a strategy.**
**Standard?** Yes.

### T2.5 PCA / eigenportfolio decomposition
**Purpose.** Count the independent bets. Directly answers the "basket" question.
**Method.** PCA on standardized daily and 30-min returns; variance explained per component;
loadings; rolling PCA to see if the structure is stable.
**Expected.** PC1 (market beta) explains 80%+. If so, **the honest headline is that this is
one bet with a hedge, and calling it a diversified basket would be false.** PC2 is likely
SPXL-vs-FAS (sector spread) and is the only genuinely idiosyncratic component available.
**Standard?** Yes.

### T2.6 Basket construction and comparison
**Purpose.** If a basket is warranted, on what weights?
**Method.** Build and compare: equal-weight, inverse-volatility, risk-parity (equal risk
contribution), minimum-variance, and PC1-neutral. Evaluate on Sharpe, max drawdown, Calmar,
turnover, and tail loss (CVaR 95). Walk-forward the weights — no in-sample optimization.
**Expected.** Inverse-vol will assign VXX a small weight. Min-variance may go long VXX purely
as a variance sink, which would be an artifact of ignoring VXX's negative drift — a trap the
evaluation must catch by reporting return, not just variance.
**Standard?** Yes.

### T2.7 Nonlinear dependence (P3)
**Purpose.** Correlation only measures linear co-movement. Check for structure it misses.
**Method.** Mutual information and transfer entropy between the three return series;
distance correlation; wavelet coherence across timescales.
**Expected.** Likely weak and unstable. Transfer entropy is data-hungry and prone to false
positives on financial data. **If results are inconclusive I will report them as inconclusive**
rather than fitting a story to them.
**Standard?** Transfer entropy and wavelet coherence are imported from information theory and
geophysics respectively. Both are non-standard for ETFs and neither is widely trusted here.

---

## Phase 3 — Strategy hypotheses (P2)

These are only formulated *after* Phases 0–2. Listing them now as candidates, explicitly
conditional on what the earlier tests show. **No strategy below will be reported as viable
unless it survives Phase 4.**

| ID | Hypothesis | Runs only if |
|---|---|---|
| T3.1 | Intraday mean reversion (open-range fade, VWAP reversion) on SPXL/FAS | T1.3 shows VR < 1 at a horizon slower than the noise floor from T0.5 |
| T3.2 | Vol-gated directional exposure — VXX level/change gates SPXL/FAS longs | T1.5 finds distinct regimes and T2.1 shows a usable conditional relationship |
| T3.3 | Overnight-hold sleeve, flat intraday | T1.4 shows overnight dominance |
| T3.4 | SPXL/FAS relative-value spread | T2.3 finds cointegration (I expect it will not) |
| T3.5 | VXX convex hedge overlay sized against a long sleeve | T1.7 quantifies the premium and T2.2 confirms tail behaviour |

## Phase 4 — Validation (P0 in importance, executed last)

### T4.1 Transaction-cost sensitivity
Every candidate edge is re-evaluated at 0 / 1 / 2 / 5 / 10 bp round-trip. **The break-even
cost is reported for every strategy.** A strategy whose break-even is below the estimated
spread is dead, and will be labelled dead.

### T4.2 Walk-forward out-of-sample
Train 2020-07 → 2023-12, test 2024-01 → 2026-07. No parameter chosen on test data.

### T4.3 Multiple-testing correction
Deflated Sharpe Ratio (Bailey & López de Prado) accounting for the number of configurations
tried, plus White's Reality Check. **Testing 40 variants and reporting the best one is the
single most common way backtests lie.** Every reported Sharpe gets a trials-adjusted p-value.

### T4.4 Regime and year-by-year stability
Per-year performance. An edge present only in 2022 is a story about 2022, not an edge.

---

## 3. Standard vs non-standard techniques — summary

**Standard for equities/ETFs:** OHLCV QA, split adjustment, log returns, moments, JB/ADF/KPSS,
ACF/Ljung-Box, intraday seasonality, realized-vol estimators (Parkinson, Garman-Klass,
Yang-Zhang), correlation/rolling correlation, OLS beta, PCA, GARCH, cointegration and pairs
trading, variance ratio, Sharpe/Sortino/Calmar/max-DD, walk-forward, cost modelling,
Amihud illiquidity, overnight/intraday decomposition.

**Non-standard for these products (but legitimate and used deliberately here):**
- Realized-variance signature plots and Corwin-Schultz spread estimation (academic HF
  microstructure) — T0.5
- Detrended fluctuation analysis for the Hurst exponent (statistical physics) — T1.3
- HMM regime detection and PELT change-point detection on volatility — T1.5
- Explicit levered-ETF variance-drag decomposition and path-dependency measurement — T1.6
- Ornstein-Uhlenbeck half-life fitting and Kalman-filtered hedge ratios — T2.3
- Exceedance correlation and tail-dependence coefficients — T2.2
- Transfer entropy, distance correlation, wavelet coherence — T2.7
- Deflated Sharpe Ratio / White's Reality Check — T4.3

**Considered and rejected as inappropriate for this dataset:**
- Hawkes / point-process models of trade arrivals — needs tick data, we have 5-min bars.
- Order-book imbalance, queue position, microprice — needs L2 data; none exists.
- Options-implied signals (skew, term structure, gamma exposure) — no options data for SPXL,
  FAS or VXX in this repo (only SOXL and TQQQ chains exist).
- Recurrence quantification analysis — I can compute it, but I know of no credible evidence it
  adds anything over DFA for return series, and running it would pad the analysis without
  informing the decision.

---

## 4. Success criteria

The analysis succeeds if it produces a defensible answer to:

1. What is the natural holding period of each instrument? (T1.3, T1.4)
2. How many independent bets does this basket contain? (T2.5)
3. Is there a tradeable intraday edge that survives realistic costs? (T3.x, T4.1)
4. Does the data support a longer hold, and in which instrument? (T1.4, T1.6, T1.7)
5. What is the maximum size this basket can trade? (T0.4)

**A defensible "no tradeable edge was found" is a successful outcome.** The failure mode to
avoid is manufacturing a strategy that only exists because forty were tried.

---

## 5. Falsifiable predictions, recorded in advance

Recorded so they can be scored honestly rather than rationalized afterwards:

1. SPXL–FAS daily return correlation will exceed 0.80.
2. PC1 will explain more than 75% of daily variance across the three.
3. SPXL and FAS log prices will **not** be cointegrated (Engle-Granger p > 0.05).
4. VXX median holding-period return will be negative at every horizon from 1 to 20 days.
5. Overnight will account for a disproportionate share of SPXL's and FAS's cumulative return.
6. Variance ratios at q=2 on 5-min returns will be below 1 for all three (microstructure).
7. No intraday strategy tested will retain a Deflated Sharpe > 1.0 after 5bp round-trip costs.

## 6. Known limitations — stated before results, not after

- **No quote data anywhere in the repo.** These are trade bars. Spreads must be *estimated*
  (Corwin-Schultz, Roll). Every transaction-cost conclusion inherits that estimation error.
  This is the single largest threat to any intraday finding.
- **No 1× benchmarks** (SPY, XLF, VIX, VIX futures). Leverage tracking and VXX roll yield
  can be characterized internally but not verified externally.
- **RTH only, no pre/post market.** Overnight is measured as a single close→open jump; the
  path through it is invisible, so overnight risk is understated.
- **Trade prices, not NAV.** The 2022 VXX creation halt means market price may have decoupled
  from indicative value. Detectable only as anomalous behaviour, not directly measurable.
- **Survivorship of the instruments themselves.** All three still exist. Levered ETFs that
  blew up are not in this sample. Conclusions apply to survivors.
- **Six years, one macro regime family.** 2020-07 → 2026-07 covers a COVID recovery, a 2022
  bear, and subsequent conditions — but no 2008-style credit event. FAS in particular is a
  financials fund whose worst historical scenario is absent from this window.

## 7. Open questions for the user

These change the analysis materially and are not inferable from the data:

1. **FAX or FAS?** No FAX file exists. Proceeding with FAS.
2. **Account size and PDT status?** Under $25k, US pattern-day-trader rules cap day trades at
   three per five days, which would rule out most of Phase 3 regardless of edge.
3. **Execution venue and realistic commission?** The repo is wired for IBKR. Assumed
   throughout: IBKR-like costs, marketable limit orders.
4. **Is holding overnight acceptable?** 3× funds gap hard. If overnight is prohibited, T3.3
   is off the table and the answer to "longer hold" is constrained before any test runs.
5. **Is shorting available?** VXX's structural decay makes *short* VXX the historically
   profitable side, with catastrophic tail risk. Long-only changes the conclusion entirely.
