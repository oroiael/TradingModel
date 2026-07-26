# Active SOXL strategies — a survey (fast-SMA, cross-asset fit, SOXL/SOXS independent)

Testing the three ideas on real data (daily + 5-min, 2020–2026). Reproduce:
`active_strategies.py`. Bottom line: **directional/timing edges on SOXL fail; the only
survivors are market-neutral structure trades.**

## 1) Fast-SMA active trading — no
- **Intraday 5-min mean-reversion** (fade deviation from a short SMA): gross edge is trivial
  (+8%/yr, Sharpe 0.12) and it's **a cost trap** — ~16,000 trades/yr, so at 2 bp/trade it
  nets **−45%/yr.** You're trying to capture bid-ask bounce you can't actually transact.
- **Daily SMA momentum** (long above / short below): **−75% to −87%/yr**, Sharpe negative —
  whipsaw × 3× leverage × decay, the same failure as the breakout rotation.

## 2) Fit to another underlying (the "R²" idea) — two very different answers

**As a *leading* indicator: no.** SOXL is **~63% explained by the broad market** (SPXL,
β 1.78) and ~21% by financials (FAS), but **nothing leads it** — the lagged coefficient of
SPXL and FAS on next-day SOXL is ~0 (slightly negative). They move *with* SOXL, not ahead.
Note: **treasuries and currencies are not in the repo.** They'd be the interesting macro
test (semis are rate-sensitive), but the prior is low — even the broad market, far more
correlated to semis than rates/FX, shows no daily lead. Upload TLT / a rates series / DXY
and I'll test it directly.

**As a *stat-arb*: the one qualified maybe.** Hedge SOXL of its market fit (rolling β to
SPXL+FAS) and you isolate a **semi-specific residual with 61%/yr idiosyncratic vol** that
**weakly mean-reverts** (lag-1 autocorr −0.06). A market-neutral residual-MR (fade the 20-day
z-score) runs:

| | Sharpe |
|---|--:|
| gross | +0.76 |
| net of 5 bp/leg (3 legs) | **+0.59** |
| OOS 2020–2023 | +0.32 |
| OOS 2024–2026 | +1.22 |

So it **survives realistic costs** (moderate turnover ~72 flips/yr) but is **unstable across
the two halves** — most of the edge is in 2024–2026. That's a yellow flag (regime-dependent
or over-fit to the recent tape), so treat it as a **candidate needing proper walk-forward
validation, not a proven edge.** It is market-neutral and roughly uncorrelated with the
vol-decay harvest, so if it validates it would *complement* the harvest rather than replace
it — but it does not beat it (Sharpe ~0.6 vs ~1.1, and less stable).

## 3) SOXL and SOXS as independent inverse positions — no
Their daily returns correlate **−0.992** — they are **not independent.** Trading both is one
directional bet mirrored; the *only* exploitable difference between them is the decay/
tracking, which is exactly what the market-neutral pair harvest already captures. There is no
separate "independent inverse" edge.

## The through-line
Across everything now tested — internal lead-lag (drift study), breakout rotation, fast-SMA,
cross-asset lead, residual stat-arb — **SOXL has no reliable directional/timing edge**,
because it is efficiently priced (nothing leads it) and it decays (so holding it long loses).
The edges that survive are both **market-neutral and structural**: the **vol-decay harvest**
(short pair, band-rebalanced — robust, Sharpe ~1.1) and, as a maybe, **semi-residual
mean-reversion** (Sharpe ~0.6, needs validation). Everything directional is a donation.
