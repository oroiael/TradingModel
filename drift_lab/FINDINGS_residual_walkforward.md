# Walk-forward: semi-residual mean-reversion — it passes, but read the caveats

Proper walk-forward of the one active idea that wasn't a flat failure: mean-reverting the
**semi-specific residual** (SOXL daily return minus its causal rolling-60-day market fit to
SPXL+FAS). Fully out-of-sample: causal hedge betas, parameters re-selected each quarter from
**past-only** data (train 504d → test 63d, 14 blocks), 5 bp/leg costs. Reproduce:
`residual_walkforward.py`.

## Result — the edge is real and broad (not a curve-fit)

| (same OOS window, 5 bp/leg) | Sharpe | CAGR | maxDD |
|---|--:|--:|--:|
| **walk-forward (OOS, params re-selected)** | **+1.22** | +72% | −44% |
| fixed (L=20, θ=0), no selection | +1.01 | +54% | −51% |
| **grid-average (ALL params)** | **+0.84** | +33% | −44% |
| in-sample-best (biased reference) | +0.96 | +50% | −44% |

The decisive anti-overfit check is the **grid-average: every parameter combo averages a
positive +0.84 Sharpe out-of-sample.** The edge doesn't live at one lucky point — the whole
grid works. Selection alternated between just two neighbors, `(L=20,θ=0)` and `(L=40,θ=0)`
(7 each), i.e. "always fade the 20–40-day z-score of the cumulative residual" — a simple,
stable rule with effectively one knob. It survives 5 bp/leg costs (moderate turnover) and is
positive in **9 of 14 quarters.**

## The caveats — and they matter

- **It's lumpy and 2024-concentrated.** OOS Sharpe by year: 2022 **−0.64**, 2023 +0.63, 2024
  **+2.85**, 2025 +0.76, 2026 +0.41. **69% of the total P&L was earned in 2024**, and
  **ex-2024 the Sharpe is +0.55.** So the honest steady-state expectation is **~0.5, not the
  headline 1.2** — with occasional standout years and a losing year (2022) in the mix.
- **It's high-vol and must be sized down.** Raw maxDD is −44%. **Vol-targeted to 15%/yr**
  (trailing-vol scaling) it becomes **Sharpe 1.29, +22% CAGR, −12% maxDD** — a usable sleeve,
  but again that Sharpe is 2024-flattered; budget for ~0.5 and −12%-ish drawdowns.
- **Small sample / regime risk.** 14 OOS blocks over one semiconductor cycle; the 2024
  strength may be a dispersion regime that doesn't repeat. Some daily close-to-close bounce
  could also flatter a mean-reversion signal (though survival at 5 bp argues it's mostly real).

## Where it fits

The most useful property: **correlation to the vol-decay harvest is +0.03 — essentially
zero.** So this is a genuinely *diversifying* market-neutral sleeve, not a competitor. A
book that runs the **band-rebalanced decay harvest** (Sharpe ~1.1, robust) *plus* a small,
vol-targeted **residual-MR** sleeve (Sharpe ~0.5 steady-state, uncorrelated) would have a
higher combined Sharpe than either alone — the classic benefit of two uncorrelated edges.

## Verdict
**Passes the walk-forward** — a real, broad, cost-surviving, market-neutral edge — but
**modest and lumpy**, not the Sharpe-1.2 machine the headline suggests. Trade it **small,
vol-targeted, as a diversifier to the harvest**, with realistic expectations (~0.5 Sharpe,
occasional great years, the odd losing year). Next hardening step before real capital: a
longer/independent sample (pre-2020 or another 3× sector complex) and confirming it isn't
close-bounce — but as stat-arb candidates go, this one earned its place.

## Reproduce
```bash
python3 drift_lab/residual_walkforward.py
```
