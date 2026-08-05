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


---

# Is high volatility *harvestable*? — `harvestability.py`

Short answer: **volatility is a scale parameter, not an edge.** Selling options
does not pay for taking volatility; it pays only for the *spread* between implied
and subsequently realised volatility. That spread turns out to be small and
roughly instrument-independent, while the vol level is not.

## The premium does not scale with the level

ATM implied vol at *t* minus the vol actually realised over the tenor. Identical
method, both instruments, `SOXL_Options_2024/25.csv` and
`raw_data/TQQQ_Options_2024/25.csv`:

| | tenor | mean IV | mean RV | **mean VRP** | median VRP | % positive |
|---|---|---:|---:|---:|---:|---:|
| **SOXL** | 7d | 97.1% | 94.5% | **+2.6%** | +11.2% | 60% |
| | 30d | 92.9% | 103.2% | **−10.3%** | −0.7% | 49% |
| | 90d | 91.3% | 107.3% | **−15.9%** | −9.9% | 33% |
| **TQQQ** | 7d | 58.4% | 57.2% | **+1.2%** | +10.1% | 65% |
| | 30d | 56.1% | 66.1% | **−9.9%** | +2.5% | 57% |
| | 90d | 56.9% | 72.6% | **−15.7%** | −2.7% | 46% |

**The implied-vol levels differ by 39 points. The premiums differ by 1.4 points.**
Doubling volatility did not double the harvest — it barely moved it. And beyond
one week the premium is *negative on both*: sellers were systematically underpaid
for what actually happened.

This is precisely why the covered call in `cc_lp_lab` lost money on the call leg
(−$35,264 net of $253,641 collected). It was not bad luck. There was no premium
there to collect.

Note the mean/median split: 60–65% of weeks show a positive premium while the
mean is ~0. That is the short-vol payoff — win small, often; lose large, rarely.
The mean is what compounds.

A longer SOXL series (`pricing_lab/s2_vrp_daily.csv`, 2024–2026) agrees and is
worse, because it includes 2026: 7d +0.7%, 30d −14.0%, 90d −21.8%, 180d −28.5%
(positive in only **12%** of observations).

## Leverage multiplies amplitude — and nothing else

The one thing an active path-trade needs is structure. Leverage is a *linear*
transform, so it scales every move and leaves every structural statistic exactly
unchanged. Measured on 5-min returns, 2022–2026:

| | ac(1) | ac(2) | ac(6) | VR(6) | VR(12) | VR(78) |
|---|---:|---:|---:|---:|---:|---:|
| SOXL | −0.0048 | −0.0042 | −0.0061 | 0.994 | 0.995 | 1.007 |
| FAS | −0.0056 | −0.0175 | +0.0014 | 0.970 | 0.969 | 0.982 |
| SOXS | −0.0140 | −0.0021 | −0.0008 | 0.987 | 1.002 | 1.066 |

Both are random walks intraday (VR ≈ 1, autocorrelation ≈ 0), and **FAS is
slightly *more* mean-reverting than SOXL, not less.** So the difference in
tradability is not that SOXL's path is more predictable.

What leverage *does* fix is amplitude against fixed costs:

| | median day range | ≥0.5% swings/day | ≥1% | ≥2% | days with no 1% swing |
|---|---:|---:|---:|---:|---:|
| SOXL | 7.06% | 14.9 | 7.7 | 3.2 | 0% |
| FAS | 3.59% | 8.2 | 3.5 | 1.2 | 4% |
| **FAS levered 2.10×** | — | **16.3** | **8.6** | **3.7** | **0%** |

Levered FAS *exceeds* SOXL's swing density. The raw material is reproducible.
But **Sharpe is leverage-invariant** — levering scales return and risk equally, so
it cannot convert a weak edge into a strong one.

## Why FAS specifically has produced nothing here

1. **Its vol is not SOXL's.** 55.6% vs 116.9% — it needs 2.10× leverage to match.
2. **It was already tested.** `band_lab/out/etf_scaling_FAS.csv`: with SOXL's
   locked settings FAS gives **−2.8 bp/ON-day, Sharpe −0.14**; fully rescaled to
   its own volatility it reaches **+7.1 bp/day, Sharpe 0.49** — against SOXL's
   **65.6 bp/day, Sharpe 3.09**. `MASTER_STRATEGY_DOCUMENT.md` §9: "SPXL, FAS and
   TQQQ were evaluated; none is adopted."
3. **It is not a diversifier.** `etf_overlap_FAS.csv`: +14.9 bp/day when SOXL is
   also trading, **−10.9 bp/day when SOXL is idle**, correlation 0.578. It works
   only when SOXL works.
4. **There is no FAS option data in this repo at all** — only the 5-min price
   file. No options trade on FAS can be backtested here, and FAS's real options
   market is far thinner than SOXL's, whose weeklies carry $0.50 strikes and a
   measured $0.02 half-spread.

## The one genuinely long-vol finding

At 30–90 days, realised **exceeded** implied on both instruments by 10–16 vol
points. The profitable side of SOXL vol over 2024–25 was **buying** it, not
selling it. That does *not* validate `cc_lp_lab`'s long put, which lost $42,120 —
a long put is short delta, and SOXL rose 2.6× over the window, so it lost on
direction. Capturing a positive long-vol premium requires **delta-hedging**
(gamma scalping), paying the spread on every rehedge, which is a different trade
with its own cost problem.

## Bottom line

100% volatility buys you more *transactions*, larger premiums and wider bands —
and proportionally larger losses. What it does not buy is edge. Edge is either a
**spread** (IV − RV, measured ≈ 0 at a week and negative beyond) or a
**structure** (autocorrelation, measured ≈ 0). Neither improves with volatility.
The real benefit of a high-vol instrument is **capital efficiency** — expressing a
given dollar of risk with less capital — and that is genuine, but it is not free
money and it cuts symmetrically.
