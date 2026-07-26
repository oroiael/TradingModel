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

The tail is always the **SOXL-short leg in a melt-up.** I backtested the two option
variants on the real intraday option data (2022–2026, entry at real trade prices, expiry
settled at intrinsic, 5% sell-slippage). **Neither beats the bare pair — options don't
improve the harvest.**

| construction (2022–2026, same capital axis) | CAGR | Sharpe | maxDD | win-rate |
|---|--:|--:|--:|--:|
| **1) bare drift-band pair (gross 2×)** | **+8.1%** | **0.79** | **−8.5%** | 61% mo |
| 2) call-capped pair (25% OTM call overlay) | +18.6% | 0.59 | −23.1% | 39% mo |
| 3) naked weekly short strangle (5% OTM) | **−49.8%** | **−0.89** | **−94.7%** | 61% wk |

- **Selling premium fails outright.** A naked weekly SOXL strangle loses **~−50%/yr with a
  −95% drawdown at every strike** (3/5/8% OTM all ≈ −47…−55%), *despite winning 56–65% of
  weeks* at ~+2%/wk — the classic short-vol trap. SOXL's ~14% weekly vol means the tail
  weeks (worst ≈ −32%) bury the premium. You cannot sell premium on a 3× ETF naked.
- **Buying protection is too dear to help.** SOXL's ~100% IV makes an OTM call overlay cost
  **~30–40%/yr**; it doesn't cap risk, it converts the trade into a lumpy long-vol bet that
  looked high-return only because 2024/2026 were melt-ups — with **worse Sharpe (0.59) and
  worse drawdown (−23%)** than the bare pair. And the **band already caps the pair's
  realized tail** (−8.5%), so the calls are expensive redundancy.

**Conclusion: the delta-neutral, band-rebalanced ETF pair is the construction.** Its
*dynamic* delta-neutral risk control is exactly what the static option structures lack.
The only real open lever remains **SOXS borrow cost** (excluded by request), not options.

## Sizing on $150K + portfolio margin

Dollar figures from the daily backtest (band 55%, 2020–2026), net = after ~5.5%/yr
combined SOXL+SOXS borrow. "Net cash" is what you could sweep; risk is in % of equity so
it scales honestly with leverage (Sharpe stays ~1.1 throughout):

| gross | CAGR | net/yr | net cash $/yr | med month $ | maxDD | worst day | verdict |
|--:|--:|--:|--:|--:|--:|--:|---|
| **2× (Reg-T)** | +12% | +7% | **~$9.8K** | ~$2,400 | −9% | −3.1% | safe base |
| 4× (PM) | +24% | +13% | ~$19.7K | ~$5,700 | −18% | −6.2% | survivable |
| 6× (PM) | +36% | +20% | ~$29.5K | ~$9,800 | −26% | −9.2% | aggressive |
| 10× (PM) | +59% | +32% | ~$47.6K | ~$27K | −40% | −15% | **ruin risk** |

~65% of months are positive at every leverage. **Portfolio margin is what unlocks the
upper rows:** the pair is delta-hedged, so a ±15% index stress nets ≈0 and PM charges
margin on the tiny residual (a few % of gross) instead of Reg-T's 50% of gross short — so
$150K can carry gross 5–10× instead of ~2×. **That linearly scales both the cash AND the
drawdown/gap risk.** This is short volatility with leverage — the XIV/LTCM shape — so the
in-sample −9…−40% drawdowns are *not* the worst possible: a single overnight
semiconductor gap larger than 2020–2026 contained can't be rebalanced through and, at 10×,
a ~−45% gap wipes the account (PM liquidates fast). **Recommended for a $150K account:
gross 3–4× under PM (~$20–25K/yr net cash, −18% worst drawdown), a hard leverage cap, and
dry powder — not max PM.** Borrow, broker PM numbers, gap-stress, and taxes are the
pre-trade items, not more backtesting.

## Reproduce
```bash
python3 drift_lab/vol_harvest.py       # the ETF-pair construction (leverage sweep incl.)
python3 drift_lab/option_harvest.py    # the 3-way option comparison (loads option data, ~5 min)
```
