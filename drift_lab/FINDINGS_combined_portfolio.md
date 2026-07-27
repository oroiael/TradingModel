# Capstone: the combined A+B market-neutral book — honest results

Blend of the two validated market-neutral edges on their common walk-forward-OOS window
(**2022-11 → 2026-04**, the only window where both are fully realistic), each **net of real
costs** (A: −5.5%/yr borrow; B: −5 bp/leg) and each vol-targeted to 10%/yr before blending.
Reproduce: `combined_portfolio.py`. **This corrects the optimistic ~1.3–1.4 Sharpe I
speculated in the playbook — the honest number is lower, and here's exactly why.**

## Results (common OOS window, net of costs, each 10% vol)

| sleeve / blend | CAGR | Sharpe | maxDD | +months |
|---|--:|--:|--:|--:|
| A — vol-decay harvest | −0.3% | **0.03** | −17.0% | 54% |
| B — semi-residual MR | +14.3% | 1.29 | −8.2% | 68% |
| **blend 50/50** | **+7.1%** | **0.89** | **−6.7%** | 59% |
| blend 70/30 (A-heavy) | +4.1% | 0.50 | −7.6% | 61% |

- **The diversification is real:** correlation A,B = **+0.05**, and the 50/50 blend's maxDD
  (−6.7%) is **lower than either sleeve alone** (A −17%, B −8.2%). That's the whole point of
  combining two uncorrelated market-neutral edges — the drawdown shrinks.
- **But the blend is carried by B, not A.** On this window B did the work (Sharpe 1.29) while
  A was ~flat.

## Why A (the "core edge") was flat here — the borrow + regime truth

A's headline **Sharpe ~1.1 was gross and full-period.** Decomposed:

| period | gross CAGR / Sharpe | net of 5.5% borrow |
|---|--:|--:|
| full 2020–2026 | +12.0% / 1.12 | +6.0% / **0.60** |
| option era 2022–2026 | +8.5% / 0.80 | +2.7% / 0.30 |
| common OOS 2022-11→2026-04 | +6.2% / 0.68 | +0.5% / **0.10** |

Two forces compounded: **(1) the melt-up regime** (2023–2026 trends) cut the harvest's gross
from ~12% to ~6%, and **(2) borrow** (~5.5%/yr on ~11%-vol returns) ate most of what was left.
Net, in the recent regime, the harvest is **marginal (Sharpe ~0.1)**. It shines in choppy/bear
tapes (2020–2022) and struggles in sustained melt-ups — a chop/bear hedge, not an all-weather
engine, once you pay to borrow.

## Leverage (portfolio margin) on the 50/50 blend

The blend is delta-neutral, so PM levers it cheaply. Scan (target portfolio vol):

| target vol | leverage | CAGR | maxDD | worst day | on $150K |
|--:|--:|--:|--:|--:|--:|
| 10% | 1.2× | +9% | −8% | −2.6% | ~$13K/yr |
| 15% | 1.9× | +13% | −12% | −4.0% | ~$19K/yr |
| 20% | 2.5× | +17% | −16% | −5.3% | ~$26K/yr |
| 25% | 3.1× | +21% | −20% | −6.6% | ~$31K/yr |

## Honest verdict

- **The combined book is a real, diversified, market-neutral structure** — the +0.05
  correlation delivers a genuinely lower drawdown than either piece, and leveraged to ~25%
  vol it's ~**+21%/yr at −20% DD (~$31K/yr on $150K)**.
- **But the honest Sharpe is ~0.9 on this window, not 1.1+, and it rests on two shaky legs:**
  1. **A is borrow- and regime-crippled recently** (net Sharpe ~0.1 in the melt-up era). If
     you can borrow SOXS cheaply *and* the tape gets choppy again, A recovers toward its
     ~0.6 net full-period Sharpe; if not, it's a flat hedge.
  2. **B carried the window but is 2024-concentrated** (ex-2024 Sharpe ~0.55, lumpy). If B
     reverts to its steady-state, the blend Sharpe is closer to **~0.5**, not 0.9.
- **So budget the combined book at ~Sharpe 0.5–0.9 net, leverageable to strong double digits
  — a solid diversified cash engine, not a money machine.** The two things that would move it
  decisively are the two open gates: **real SOXS borrow** (rescues or sinks A) and an
  **independent-sample validation of B** (confirms or kills its recent strength).

> **Update (residual_generalization):** B was later shown to be a common-2024-regime effect (FAS ex-2024 Sharpe −0.03; pooling amplifies not diversifies). The combined book above was carried by B, so its forward case is weaker than shown — see `FINDINGS_residual_generalization.md`.
