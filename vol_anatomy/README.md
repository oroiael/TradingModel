# vol_anatomy — where SOXL's volatility comes from, and how to reproduce it

`python3 vol_anatomy/anatomy.py` — measured from `SOXL_5min_6Years.csv`,
`SOXS_5min_6Years.csv`, `FAS_5min_6Years.csv` (2022-01 → 2026-07, 1,140 sessions).
Fund facts from `SOXL-SOXS-Fact-Sheet.pdf` and `SAI_Combined3XShares.pdf`.

## What SOXL actually is

Direxion Daily Semiconductor Bull 3X (inception 2010-03-11). **Daily target 300%**
of the NYSE Semiconductor Index (`ICESEMIT`) — the 30 largest US-listed semis.
Net expense 0.75%. Sector weights: semiconductors 76.0%, semi materials &
equipment 24.0%. Top ten = **61.7% of the index** (Micron 8.6, AMD 8.1, Nvidia 6.8,
Intel 6.3, Broadcom 6.1, Applied Materials 5.8, KLA 5.7, Marvell 5.2, Lam 4.9,
TSMC 4.3). Exposure is obtained through **total return swaps and futures**, not
only shares — the SAI describes swaps where a counterparty pays the fund the
reference asset's return on a notional. The fund is **non-diversified** by
classification.

## Four stacked multipliers (measured)

| layer | contribution |
|---|---|
| 1. one sector, 30 names, 62% in ten | index vol **39.0%** close-to-close (30.6% intraday-only) vs ~16% for a broad index |
| 2. ×3 daily leverage | SOXL vol **116.9%** cc / 91.8% intraday — **exactly 3.00×** on both bases |
| 3. overnight gaps | **37% of total variance** sits in the gap you cannot trade through |
| 4. vol-of-vol | annual vol ranged **85.3% (2023) → 149.9% (2026)** |

The ±3× mechanism is verifiable without any fund disclosure: regressing SOXS
intraday returns on SOXL's gives slope **−1.0037, R² 0.9865**, and the index
return implied by SOXL/3 agrees with the one implied by −SOXS/3 to a median
absolute difference of **0.00066**. They are mechanically the same bet.

| year | cc vol | intraday | overnight | worst day | best day | \|move\|>5% | >10% |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 131.8% | 110.4% | 69.5% | −18.7% | +31.5% | 145 | 56 |
| 2023 | 85.3% | 69.4% | 48.4% | −12.2% | +19.8% | 87 | 14 |
| 2024 | 103.7% | 79.2% | 62.9% | −22.8% | +20.9% | 99 | 29 |
| 2025 | 119.6% | 96.9% | 72.7% | −29.8% | +55.9% | 94 | 26 |
| 2026 | 149.9% | 102.0% | 108.2% | −30.7% | +24.4% | 77 | 39 |

## The claim that does NOT survive measurement

A 3× fund must buy into strength and sell into weakness at the close to restore
its exposure, and the required trade is proportional to the day's move. This is
routinely cited as a self-amplifying volatility source. **It is not detectable
here**: corr(day move to 15:25, final 30 min) = **−0.0527**, and the most-down
quintile actually rises +0.209% in the last 30 minutes while the most-up quintile
falls −0.091%. If anything the close mean-reverts. The flow is real but small
against the underlying megacaps' liquidity, and it is anticipated. **Do not
attribute SOXL's volatility to its own rebalancing.**

## Volatility drag — why 3× daily ≠ 3× cumulative

For a daily-rebalanced *k*× fund on an index of vol σ, log-growth is
`k·μ − (k·σ)²/2`, so the drag versus *k* × the index is **`(k²−k)/2 · σ²`**:

| k | fund vol | annual drag |
|---|---:|---:|
| 1 | 30.6% | 0.0% |
| 2 | 61.2% | 9.4% |
| 3 | **91.8%** | **28.1%** |
| 5 | 153.1% | 93.7% |

Drag is **quadratic in leverage while return is linear** — that is the whole
trade-off. Measured geometric-minus-arithmetic gap on this data: **−42.0%/yr for
SOXL, −45.1%/yr for SOXS.**

But drag is not destiny — it is a *variance* cost that a strong *trend* can
overwhelm. Fact sheet, 2026-06-30: index +170.76% over 1Y while **SOXL NAV
+967.32%** — far more than 3 × 170.76 = 512%, because daily rebalancing compounds
a persistent trend in your favour. The identical mechanism run the other way gave
**SOXS −97.86% over 1Y, and −100.00% over both 10Y and since inception.**

## Reproducing the volatility without semis

Volatility is **linear in leverage**, so any asset reaches SOXL's 116.9% at
`leverage = 1.17 / (its own vol)`:

| instrument | ann vol | implied 1× | leverage to match SOXL |
|---|---:|---:|---:|
| SOXL 3× semis | 116.9% | 39.0% | 1.00× |
| SOXS −3× semis | 117.7% | 39.2% | 0.99× |
| FAS 3× financials | 55.6% | 18.5% | 2.10× |
| 1× semis index | 39.0% | — | 3.00× |
| 1× financials | 18.5% | — | 6.31× |

**Nothing about semiconductors is required.** Semis only reduce the leverage
needed. Ways to get there, cheapest-to-borrow first: another 3× sector ETF
(TQQQ/FAS/TNA/LABU), futures (deep, ~5–10% margin, no fund fee, no swap spread),
portfolio-margin equity leverage, or options — where delta gives leverage and
gamma makes it path-dependent, but you also pay the volatility risk premium and
carry theta.

**The caveat that matters:** a synthetic 2.10× daily-rebalanced FAS matches SOXL's
vol to the decimal (116.9%) but its daily returns correlate only **0.510** with
SOXL. Same volatility, different bet. If you want the *number* — for testing an
options structure, sizing a risk model, generating strategy stress paths — any
levered proxy works. If you want SOXL's actual *exposure* (an AI-capex cycle,
TSMC/Taiwan concentration, memory pricing), no amount of leverage on financials
supplies it. Matching a moment is not matching a risk.
