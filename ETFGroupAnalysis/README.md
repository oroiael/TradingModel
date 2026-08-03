# ETFGroupAnalysis

Independent and collective analysis of **SPXL** (3× S&P 500), **FAS** (3× Financials) and
**VXX** (long front VIX futures ETN) on 5-minute bars, 2020-07-23 → 2026-07-22, to decide
whether they can be traded together as an actively managed basket.

**Start here:**
- [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) — the plan, written before any test was run:
  purpose, expected outcome and priority for each test, plus seven falsifiable predictions
  recorded in advance.
- [`docs/FINDINGS.md`](docs/FINDINGS.md) — results, including the prediction scorecard and
  the five methodological errors found and corrected along the way.
- [`docs/OVERNIGHT_SPXL_FAS.md`](docs/OVERNIGHT_SPXL_FAS.md) — follow-up drilling into the
  one effect that survived: optimal entry/exit timing for SPXL and FAS overnight trades,
  and whether any indicator improves them (it does not).
- [`docs/CROSS_LEAD_INDICATORS.md`](docs/CROSS_LEAD_INDICATORS.md) — an 816-specification
  scan for cross-instrument leading indicators across aggregations from 5 minutes to 5
  days. Finds a real, family-wise-significant, out-of-sample-validated volatility signal
  (VXX last-hour RV leads SPXL/FAS next-day RV) that is nonetheless worth nothing in the
  two economic applications tested.

## Headline

This is **not a basket** — PC1 explains 80.5% of daily variance, so all three are one bet.
Nothing intraday is tradeable (SPXL and FAS are random walks at 5 min to 1 h; the best of
32 intraday variants breaks even at 0.34 bp). The one robust effect is that **68% of
SPXL's and 83% of FAS's six-year return accrued overnight**. VXX cannot be held (half-life
0.93 years) and did not reduce maximum drawdown when used as a hedge. A volatility-gated
overnight strategy showed Sharpe 1.14 and was **retracted** after a clean train/test
protocol showed gate selection carries no information (rank correlation −0.04).

## Layout

```
docs/     TEST_PLAN.md, FINDINGS.md
scripts/  analysis, run in order p0 -> p7
out/      raw text output + CSVs + summary.png  (every number in FINDINGS traces here)
data/     empty; see below
```

## Reproducing

The three source CSVs live at the repository root as Git LFS objects and are **not**
duplicated here.

```bash
cd /path/to/TradingModel
git lfs pull --include="SPXL_5min_6Years.csv,FAS_5min_6Years.csv,VXX_5min_6Years.csv"

pip install numpy pandas scipy statsmodels scikit-learn matplotlib arch

cd ETFGroupAnalysis/scripts
python3 validate_vr.py        # estimator validation -- run this first
python3 p0_integrity.py       # BLOCKING: data integrity and basis
python3 p1_independent.py     # per-instrument characterization
python3 p2_collective.py      # correlation, cointegration, PCA, lead-lag
python3 p2b_baskets.py        # corrected basket construction + VXX hedge sweep
python3 p3_strategies.py      # strategy hypotheses with costs and DSR
python3 p4_attribution.py     # attribution + corrected significance
python3 p5_final_costs.py     # corrected cost accounting + capacity
python3 p7_clean_oos.py       # clean out-of-sample selection protocol
python3 p6_charts.py          # summary figure

python3 p8_overnight_timing.py     # entry/exit grid + bar-level profile
python3 p9_overnight_indicators.py # 13 indicators, univariate + multivariate + rules
python3 p10_timing_robustness.py   # entry gradient in train/test, net-of-cost table

python3 p11_crosslead_panel.py     # aggregated multi-window feature panel
python3 p12_crosslead_scan.py      # 816-spec scan + family-wise bootstrap (~4 min)
python3 p13_crosslead_validate.py  # leverage-effect control + OOS forecast evaluation
python3 p14_crosslead_economic.py  # vol targeting + big-move classification
python3 p15_crosslead_chart.py     # cross-lead summary figure
```

Set `ETF_DATA_DIR` to read the CSVs from somewhere other than the repo root. Nothing here
writes to or modifies the source data.

`validate_vr.py` is not optional decoration — the first variance-ratio implementation was
wrong, and this harness is what catches that class of error. It checks the estimators
against white noise, AR(±0.15), a heteroskedastic-but-uncorrelated series, and a random
walk, with known expected answers for each.

## Caveats that change conclusions

- **The request named `FAX_5min_6Years.csv`, which does not exist.** This uses **FAS**.
- **There is no quote data in this repository.** Spreads could not be measured; both
  estimators tried (Roll, Corwin-Schultz) produced unusable output. Results are therefore
  reported as *break-even cost* rather than net return. The overnight sleeve breaks even
  at 8.24 bp per round trip — real fill data is needed to know whether that clears.
- **Nothing tested clears a Deflated Sharpe of 0.95.** Six years is not enough to
  establish a 0.67 Sharpe; the overnight effect itself sits at t ≈ 1.6.
- **Indicators do not improve the overnight trade.** Thirteen tested on SPXL and FAS:
  none significant at 5%, out-of-sample R² negative for both, and for SPXL only 14% of
  indicator rules beat simply holding every night. The one robust timing result is to
  enter at the last bar (15:55) — monotone in both symbols, both sub-periods, and 6 of
  7 years each.
- **A real cross-asset signal exists but does not pay.** VXX's last-hour realized
  volatility leads next-day realized volatility in SPXL and FAS (family-wise p = 0.0000,
  OOS R² +1.4/+1.9 pp, Diebold-Mariano p = 0.002/0.004), and information flows SPXL → FAS
  but not FAS → SPXL. It produced no gain in vol-targeted sizing or tail-day
  classification. Direction remains unpredictable at every aggregation tested.
