# Market-neutral structural trades on the SOXL/SOXS/semis complex — a playbook

Everything in this repo pointed to one conclusion: **SOXL has no directional/timing edge**
(nothing leads it; rotation, fast-SMA, deep-ITM all fail), so the only durable edges are
**market-neutral and structural** — they pay you for a mechanical property of the
instruments, not for predicting direction. This lists every such trade, whether it's real,
how to test it, and how to turn it into cash and (with leverage) outsized returns.

"Structural" = the edge comes from how the products are *built* (daily-reset decay, expense/
financing, index composition), not from a forecast. "Market-neutral" = ~zero beta to the
semiconductor index (verified, not assumed).

| # | trade | source of edge | status | net Sharpe | notes |
|---|---|---|---|--:|---|
| A | **Vol-decay harvest** | 3× daily-reset −3σ² decay + carry | **validated** | **~1.1** | the core edge |
| B | **Semi-residual mean-reversion** | idiosyncratic (semi-vs-market) MR | **validated, lumpy** | ~0.5 | uncorrelated diversifier |
| C | **Pure carry (expense+financing)** | both funds bleed fees/financing | **validated** | ~0.9 | low-vol floor (sub-case of A) |
| D | Variance-risk-premium (sell vol) | implied > realized | **ruled out** | <0 | SOXL implied<realized (0.93) |
| E | Dispersion / index-vs-component vol | correlation risk premium | untestable here | ? | needs single-name options |
| F | Creation/redemption NAV arb | primary-market spread | not accessible | ? | authorized participants only |
| G | Extended cross-3× stat-arb | relative value across 3× ETFs | candidate | ? | generalize B to more triplets |

---

## A. Volatility-decay harvest — the core edge  *(validated)*

**What it is.** A 3× daily-reset fund loses −3σ² per period to compounding (proven: measured
slope −3.10 vs −3.00 theory), on top of its expense + swap financing. Shorting **both** SOXL
and SOXS is delta-neutral (β ≈ 0.02) and short that structural bleed.

**The one subtlety that makes it work.** Daily rebalancing captures ~none of the decay (it
resets with the funds → only the carry, +3.3%/yr). You must let the pair *drift* to harvest
the decay, but drifting blows up in a trend. The fix is a **drift-band rebalance** (reset to
equal-dollar only when a leg exceeds ~55% of gross): harvest in chop, force-cover the
ballooning leg in a trend.

**Numbers (real data, band 55%, gross 2×, no borrow):** +12%/yr, Sharpe 1.12, maxDD −9.4%,
positive **every** year incl. the 2026 melt-up, 65% of months positive. Robust out-of-sample
(halves Sharpe 1.34 / 0.94), survives 3–10 bp/rebalance costs.

**How to test it.** Daily close-to-close backtest of short-$1-SOXL + short-$1-SOXS with band
rebalancing; sweep the band (52–65%) and leverage; split-sample OOS; transaction-cost and
borrow sweeps; per-year and monthly cash distribution; verify β-to-index ≈ 0. (`vol_harvest.py`)

**Cash.** Median month +1.1% of equity, 65% positive → sweep monthly. On $150K at gross 2×,
~$2,400 median month, ~$18K/yr gross (~$10K net of ~5.5% borrow).

**Outsized returns.** It's delta-neutral, so **portfolio margin charges a few % of gross
(vs Reg-T 50%)** → $150K can carry gross 5–10× instead of 2×. Return scales linearly at
constant Sharpe: gross 4× ≈ +$20K/yr net, 6× ≈ +$30K, 10× ≈ +$48K — **but drawdown scales
too** (−18% / −26% / −40%) and it's leveraged short-vol (XIV/LTCM shape); a gap beyond the
sample can wipe a max-levered account. Sweet spot ~gross 3–4×, hard leverage cap.

---

## B. Semi-residual mean-reversion — the diversifier  *(validated, modest & lumpy)*

**What it is.** Hedge SOXL of its market fit (rolling 60-day β to SPXL + FAS) and the leftover
**semi-specific residual** (61%/yr idiosyncratic vol) weakly mean-reverts. Fade the z-score of
the cumulative residual: long the SOXL-vs-market spread when it's stretched down, short when up.

**Numbers (walk-forward OOS, 5 bp/leg):** Sharpe +1.22 headline, but **69% of P&L is 2024**;
ex-2024 Sharpe +0.55, 2022 negative. Grid-average of all params is +0.84 OOS (broad, not a
curve-fit). Vol-targeted 15% → +22% CAGR, −12% DD. Budget ~0.5 steady-state.

**How to test it.** Walk-forward with **causal** hedge betas (past-only), parameters
re-selected each quarter from the trailing window, concatenate the test blocks; check the
**grid-average** (broad vs point edge), per-year concentration, cost sweep, and correlation to
A. Harden with an independent sample (pre-2020, or another 3× sector triplet). (`residual_walkforward.py`)

**Cash.** Lumpier — 9/14 OOS quarters positive; realize at the quarterly/z-score exits.

**Outsized returns.** Its value is **diversification, not size**: correlation to A is **+0.03**.
Two uncorrelated ~market-neutral edges combine to a higher portfolio Sharpe than either alone.
Run it small and vol-targeted *alongside* A, not levered on its own.

---

## C. Pure carry (expense + financing) — the low-vol floor  *(validated)*

**What it is.** The daily-rebalanced short pair (no band) — you forgo the σ² decay but collect
the two expense ratios (0.75% + 1.00%) plus the net financing differential (SOXL pays
financing, SOXS earns on cash), fully delta-neutral. +3.3%/yr, Sharpe 0.88, maxDD only −2.5%.

**Use.** The conservative version of A — steadiest cash, smallest drawdown. Good as the base
layer you always run, dialing up toward the band-harvest (A) for more return/risk. Same test
harness as A (it's the daily-rebalance corner of the band sweep).

---

## D. Variance risk premium (selling vol) — **ruled out with data**

**What it would be.** Sell SOXL options (delta-hedged) to harvest implied-over-realized vol —
the standard equity-index short-vol carry.

**Why it fails here.** Measured directly: SOXL weekly **implied move 10.1% vs realized 10.8%**,
**implied/realized = 0.93**; implied ann vol ~91% vs realized ~111%. **There is no premium** —
SOXL options are, if anything, *cheap* relative to how much the thing actually moves, so
selling vol loses even when delta-hedged. This is exactly why the naked weekly strangle was a
−50%/yr, −95%-DD disaster. (`vrp_diagnostic.py`) Do not sell vol on SOXL.

---

## E–G. Candidates that need data we don't have

- **E. Dispersion** (sell index vol / buy component vol, or vice versa) harvests the
  correlation risk premium — a real structural edge, but needs **single-name semiconductor
  options** (not in the repo). Test: compare SOXX-implied vol to the cap-weighted basket of
  component-implied vols; trade the spread delta-neutral.
- **F. Creation/redemption NAV arbitrage** is real but **authorized-participants only** — not
  accessible to a retail/small account.
- **G. Extended cross-3× stat-arb** generalizes B: run the same residual-MR across more 3×
  triplets (e.g., TQQQ, FAS, SPXL, biotech/energy 3×) to build a diversified market-neutral
  relative-value book. Test: the walk-forward harness in B, applied per pair, pooled — and it
  doubles as the independent-sample check B still needs.

---

## Putting it together — cash now, outsized later

**The book.** Run **C as the floor**, dial up to **A (band-harvest)** for the main return, and
add a small vol-targeted **B** sleeve for uncorrelated diversification. A and B are ~0
correlated, so a vol-weighted blend (say 70% A / 30% B) lifts the combined Sharpe toward
~1.3–1.4 with a smoother curve than A alone.

**Cash generation.** A throws off cash ~65% of months (sweep monthly); B adds lumpier
quarterly cash. The combined book is designed to *pay you regularly* from structure, not from
being right about direction.

**Outsized returns — honestly.** These are **Sharpe ~1 market-neutral** edges. "Outsized"
comes only from **leverage**, which portfolio margin makes cheap for delta-neutral books —
lever a Sharpe-1.3 blend to 20–25% target vol → ~+25–35%/yr, or push further for more. But
leverage scales the **tail** one-for-one, and A is short-vol with overnight-gap risk that
can't be rebalanced through. So the real ceiling is set by **how much gap/ruin risk you'll
wear**, not by the edge. Truly lottery-sized returns (2×–5×) only come from *directional* bets
(buy-hold SOXL was +53%/yr this cycle) — and those carry no edge, just risk premium and −90%
drawdowns. The honest promise of this playbook: **steady, structural, market-neutral cash at a
good Sharpe, leverageable to strong double-digit returns — not a lottery ticket.**

**Before real capital:** actual SOXL/SOXS borrow-rate history (the number that sets A's net),
your broker's portfolio-margin stress parameters (sets true leverage), an overnight-gap stress
test, an independent sample for B, and taxes. Those are the gates — not more backtesting.
