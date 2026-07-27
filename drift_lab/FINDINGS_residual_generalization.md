# Trying to "make B work": cross-sector validation of the residual stat-arb — honest verdict

Goal: harden trade **B** (semi-residual mean-reversion) with an **independent sample** by
running the identical walk-forward on a different 3× sector (FAS = financials) and pooling.
Real data only (SOXL/FAS/SPXL 5-min → daily). Reproduce: `residual_generalization.py`.

## Result

| residual-MR (WF-OOS, 5 bp/leg) | OOS Sharpe | grid-avg | **ex-2024 Sharpe** | 2024 share of P&L |
|---|--:|--:|--:|--:|
| SOXL (semis, hedge SPXL+FAS) | +1.22 | +0.78 | **+0.55** | 69% |
| FAS (financials, hedge SPXL+SOXL) | +0.55 | +0.12 | **−0.03** | **103%** |
| pooled (equal-risk) | +1.26 | — | +0.36 | 79% |

## What it means — it does NOT make B robust

- **It generalizes — which is the bad news, not the good news.** FAS is positive OOS (+0.55),
  so the effect isn't SOXL-only noise. But **FAS's entire edge is 2024** (ex-2024 Sharpe
  −0.03, 103% of P&L in 2024), and SOXL is 69%-in-2024. The effect showing up in *both*
  sectors *in the same year* proves it's a **common 2024 regime**, not a sector-idiosyncratic
  edge.
- **Pooling amplifies, not diversifies.** The two sector streams are daily-uncorrelated
  (corr −0.01) yet their *good periods coincide* (2024), so the pooled book is **79% 2024**
  (worse than SOXL alone) with ex-2024 Sharpe only +0.36. Adding sectors cannot diversify a
  concentration that is common to all of them.
- **FAS's grid-average is +0.12** (vs SOXL's +0.78) — the edge is fragile off SOXL: it lives
  in the selected parameters, not broadly.

## Verdict (no dressing it up)

**B is real but regime-dependent — a 2024 sector-rotation/dispersion effect — and the
cross-sector test does not make it a robust or diversifiable standalone edge.** Ex-2024 it is
weak-to-flat (SOXL +0.55, FAS −0.03, pooled +0.36). Its earlier appeal as an "uncorrelated
diversifier" for the combined book was largely a 2024 artifact; the combined A+B book's
forward case is weaker than the capstone stated, because the sleeve that carried it (B) only
worked in one regime.

**The honest stopping point:** the signature looks like *sector-rotation / high-dispersion
mean-reversion* that only pays when dispersion is high (2024 had a major semis/tech rotation).
Trading it would require gating on a dispersion/rotation regime signal — but this 2020–2026
sample contains **only one** such regime, so that gate **cannot be validated here.** It needs
a longer history spanning multiple dispersion regimes (pre-2020, or more years forward).
Until then, **B is not validated as tradeable** — I won't claim otherwise.

## Net effect on the playbook
Downgrade B from "validated, modest diversifier" to **"real but regime-dependent, not
validated as tradeable."** That leaves **A (the vol-decay harvest) as the one durable
market-neutral edge** — and A is itself borrow- and regime-sensitive (net Sharpe ~0.6
full-period, ~0.1 in the recent melt-up era). The honest bottom line of the whole study:
one genuine structural edge (A), best in choppy/bear tapes and gated by borrow costs; and a
regime-dependent maybe (B) that needs more history to trust.
