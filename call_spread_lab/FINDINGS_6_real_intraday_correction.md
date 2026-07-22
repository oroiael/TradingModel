# SOXL Part 6 — Full Real Intraday Data OVERTURNS the Part-4 Intraday Claim

The user uploaded the **complete** 5-min option set (2022–2026, 664 files, 246
expirations, 660,471 contract-day highs). With real intraday prices across all
regimes — and, critically, **realistic execution** — the Part-4 "intraday
harvesting helps" result **does not survive.** This is a correction, stated plainly.

## What changed: execution modeled honestly

Part 4 (and my first pass on the real data) harvested a leg at the intraday
**peak** — BS at the underlying's high, or the option's own intraday high, ×(1−slip).
**That assumes you sell at the top of the spike, which needs foresight.** The
user's actual rule — "sell when the leg is up +X%" — is a **limit order that fills
at the +X% threshold** when the intraday high reaches it, *not* at the high. Fixing
this is the whole story.

| execution model | 30 DTE | 60 DTE | what it represents |
|---|--:|--:|---|
| **limit-fill (realistic)** | **−51%** | **−30%** | you sell at +50% when touched |
| sell-at-high (Part-4 style) | +90% | +47% | unachievable ceiling (perfect timing) |

## The result: intraday threshold-harvesting LOSES to EOD at every tenor

REAL intraday (limit-fill) vs EOD close-harvest, 7.5% dist, take +50%, leg_frac
15%, 2022–2026 (`real_tenor_sweep.csv`):

| DTE | EOD CAGR | **REAL (limit) CAGR** | uplift |
|--:|--:|--:|--:|
| 21 | +19% | −57% | −76% |
| 30 | −15% | −51% | −36% |
| 45 | +23% | −21% | −44% |
| 60 | +15% | −30% | −44% |
| 90 | +2% | −19% | −20% |
| **120** | **+44%** | +11% | −32% |
| 150 | +17% | −3% | −20% |

**Intraday harvesting underperforms EOD at every single tenor.** The 60-DTE chart
(`real_harvest_60dte.png`) says it in one picture: limit-fill intraday (red) bleeds
to ~$20k, EOD (blue) grows to ~$184k, and the sell-at-high ceiling (green, ~$570k)
is the mirage that made intraday look good.

## Why — and it's a real property of the instrument

Force-selling every leg at +50% **the instant it is touched intraday caps the
fat-tail winners that ARE the edge.** A leg that spikes through +50% intraday very
often closes far higher (SOXL trends hard); the limit sells it at +50% and buys a
fresh decaying leg (churn). Letting winners run to the close (EOD) captures the
right tail. On a fat-tailed 3× ETF, *harvesting sooner and at a fixed threshold is
the wrong direction.*

## Reconciliation — what still stands

* **Part 3 stands (realistic):** the **120-DTE strangle, EOD (close) harvest at
  +50%** is still the best realistic configuration — **+44% CAGR, −36% DD** — and
  EOD harvest still beats hold-to-expiry (+44% vs +27%). Both sides of that use
  realistic EOD marks; nothing there depended on intraday peak-selling.
* **Part 4 is corrected:** its intraday improvement (+77%→+87–101%) came from
  peak-selling (BS at the underlying extreme). Under limit-fill it disappears. The
  Part-5 *bar-level* BS validation (corr 0.98–0.995) is still true — BS prices the
  option well — but pricing the option well is not the same as being able to *sell
  at that peak*, and that distinction is the entire error.
* **The data is not at fault — it's excellent** (Part 5): full 2022–2026 coverage,
  near-ATM vwap ~99%, intraday close = daily close (corr 1.0000). The real prices
  are exactly what let us catch the mistake.

## What this means for the strategy

* **Recommendation: 120-DTE strangle, harvest at the CLOSE (EOD) when a leg is up
  ~+50%, sized fractionally, with the vol-regime rotation for low-vol years.** Do
  **not** chase intraday spikes with a fixed threshold — the real data says it
  destroys value.
* Intraday data's payoff here was **diagnostic, not additive**: it converted an
  optimistic modeling assumption into a measured, refuted one.
* **Open door (different strategy, not yet validated):** a *smarter* intraday rule
  — trailing stop that lets winners run then locks a pullback, an adaptive/high
  threshold, or partial-harvest-and-hold — could in principle beat EOD by keeping
  the tail while trimming fade. That is a new hypothesis; the fixed-threshold
  limit-harvest tested here is not it. Happy to build and test a trailing-stop
  variant on the real data if you want to pursue it.

## Reproduce

```bash
git lfs pull --include="raw_data/SOXL_intraday_5m_exp_*.csv"   # ~3.5 GB, 664 files
cd call_spread_lab
python3 run_real_harvest.py   # builds cached real_hi; EOD vs BS vs REAL at 60 & 120 DTE
python3 run_real_tenor.py     # tenor sweep + limit-vs-high execution realism + plot
```
