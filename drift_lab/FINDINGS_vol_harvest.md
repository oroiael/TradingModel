# Constructing a SOXL/SOXS volatility-harvest that generates cash

**Goal:** balance a position between SOXL and SOXS that harvests the volatility (the daily-
reset decay) as frequent cash. Built and backtested on real 5-min → daily data
(`vol_harvest.py`). Borrow costs excluded by request (they are the real drag — see risks).
**Not investment advice; this is a short-volatility strategy.**

## The idea, from the mechanics

A 3× fund's **−3σ² decay is a multi-day compounding effect**, not a daily return. Shorting
**both** SOXL and SOXS is market-neutral (β to the index ≈ 0) and short that decay. The
catch we already proved: **daily rebalancing captures ~none of the decay** (it resets right
along with the funds — only the fund carry, +3.3%/yr), while **letting the pair drift**
captures the decay but blows up in a trend (fixed weekly rebalance = +15%/yr but **−40%**
drawdown; monthly = **−92%**, near-wipeout in the 2026 melt-up).

## The fix: rebalance on a drift band, not the calendar

Reset to equal-dollar **only when one leg exceeds ~55% of gross exposure.** In chop the
pair drifts and the decay accrues; in a trend the band **force-covers the ballooning leg**
(caps the melt-up tail) while re-shorting the shrunk one. That single change converts the
short-gamma bleed into a controlled harvest:

| construction (short both, gross 2×) | CAGR | Sharpe | maxDD | +months |
|---|--:|--:|--:|--:|
| calendar daily (pure carry, no decay) | +3.3% | 0.88 | −2.5% | 64% |
| calendar weekly | +15.0% | 0.67 | **−39.5%** | 61% |
| calendar monthly | +7.2% | 0.44 | **−91.8%** | 67% |
| **drift-band 55%** | **+12.0%** | **1.12** | **−9.4%** | **65%** |

**Positive every calendar year** — 2020 +10, 2021 +24, 2022 +7, 2023 +8, 2024 −1, 2025 +17,
2026 +7% — including the 2026 melt-up that wiped out the calendar versions. Median month
**+1.1%**, 65% of months positive: that's the "cash on a frequent basis."

## It's robust, not curve-fit

- **Out-of-sample halves:** band 55% gives Sharpe **1.34** in 2020–2023 and **0.94** in
  2024–2026, DD −9.4% in both. The *tight-band* region (53–56%) works in both a
  bear/chop regime and a melt-up regime; loosening to 60% degrades in both. Use a tight
  band ~53–56%, not a magic 55.0%.
- **Transaction costs:** ~51 rebalances/yr; at 3 bp/rebalance CAGR is still **+11.5%**
  (10 bp → +10.4%). SOXL/SOXS ETF spreads are ~1–3 bp, so this survives real execution.
- **Leverage is a clean dial** (Sharpe ~1.12 throughout): gross 1× → +6%/−4.8% DD, gross
  2× → +12%/−9.4%, gross 3× → +18%/−13.8%. Size to your drawdown tolerance.

## Recommended construction

1. **Short equal dollars of SOXL and SOXS** (gross ≈ 2× your capital for the +12%/−9%
   profile; scale down for less risk).
2. **Rebalance to equal-dollar on a ~55% drift band** (equivalently, when net delta drifts
   past a set threshold), checked at each close.
3. **Sweep realized gains** monthly — the equity accrues the decay as harvestable cash.
4. **Cap the tail** (below).

## The risks — read these, it is short volatility

- **You are short gamma / short vol.** The +12% / Sharpe 1.1 is *compensation for bearing
  crash-up risk.* The band caps but does not remove the tail: a **fast melt-up or a large
  overnight semiconductor gap cannot be rebalanced through** (you only act at the close).
  Worst month in-sample was −8%; a single 20%+ overnight index gap (SOXL ±60%) would exceed
  the −9.4% drawdown. It *will* have a bad event eventually.
- **Borrow costs are excluded here by request and are the real drag.** SOXS is a small,
  decayed, popular short — borrow can run 5–20%+/yr. On ~1× SOXS notional that's roughly
  −5%/yr at a 5% fee, taking +12% toward **~+7% net**; a hard-to-borrow spike hurts more.
  This is the number to pin down before sizing up — get actual SOXL/SOXS borrow history.
- **Overnight gap** is the specific failure mode; consider rebalancing intraday on big
  moves rather than once at the close.
- **Capacity:** SOXS is small; fine for a small investor, not for size.

## The natural enhancement (your options toolkit)

The tail is always the **SOXL-short leg in a melt-up.** A cheap **OTM SOXL call overlay**
converts this into a *defined-risk* short-vol trade — you keep the decay harvest and cap
the crash-up. Alternatively, express the whole view as **short option premium** (e.g.
short SOXL strangles) for literal weekly cash instead of shorting the ETFs, sidestepping
SOXS borrow entirely. Both are directly testable on the intraday option data already in
this repo — say the word and I'll backtest the call-capped and the short-premium versions.

## Reproduce
```bash
python3 drift_lab/vol_harvest.py
```
