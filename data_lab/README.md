# data_lab — Neutral, Strategy-Agnostic Data Analysis for SOXL

Purpose: **look at the data first, with no strategy in mind**, and let its measured
structure tell us what class of trade fits. SOXL is a mechanically-driven instrument
(a daily-rebalanced 3× ETF — leverage decay, path dependence, event-driven vol), so
the goal is to fingerprint the forces that actually move it, then hand off to
strategy evaluation. Nothing here optimizes or backtests a trade.

## Run

```bash
git lfs pull            # underlying 5-min + daily/intraday options
pip install pandas numpy scipy matplotlib
cd data_lab
python3 run_all.py      # 3 modules + a synthesis; or run each module alone
```

| module | what it measures | data |
|---|---|---|
| `underlying_signature.py` | return distribution & fat tails, **volatility drag**, mean-reversion vs momentum (autocorrelation, Lo-MacKinlay variance ratios, Hurst), vol clustering, tail mean-reversion | daily 2022–2026 |
| `intraday_microstructure.py` | **overnight vs intraday** return/risk, time-of-day vol profile, end-of-day rebalancing momentum, 5-min autocorrelation | 5-min 2023-07→2026-07 |
| `options_surface.py` | **volatility risk premium** (implied vs subsequent realized), term structure, **skew** (put vs call), vol-of-vol, IV/spot correlation | daily options 2022–2026 |
| `run_all.py` | orchestrates + prints a synthesis (measured facts → suggested structures) | — |
| `eval_overnight.py` | **evaluates finding B′** (overnight-drift capture) vs buy&hold & intraday, with cost sensitivity, by-year, regime robustness, and a documented proxy/assumption + additional-data section | 5-min 2023-07→2026-07 |

Charts land in `outputs/` (`underlying_signature.png`, `intraday_microstructure.png`,
`options_surface.png`).

## What the data says (measured)

| # | fact | number |
|---|---|---|
| A | **Volatility drag** — the leverage tax | arithmetic +87%/yr → geometric **+23%/yr**; **~64%/yr bled to choppiness** |
| B | Direction is a **random walk** daily→monthly | variance ratios ~0.9 (z≈0), Hurst **0.49**, no significant return autocorrelation |
| B′ | …but the return lives **overnight** | close→open **Sharpe 1.60** (+346%) vs intraday session **0.23** (+60%) |
| B″ | …and **extremes mean-revert** | day after a <−10% day: **+1.4% mean, 60% up** |
| C | **Volatility clusters** & tails are fat/left | |r| autocorrelation persistent to 20d; skew **−0.37**, excess kurtosis **+2.8**; corr(ΔIV, return) **−0.57** |
| D | **Options are cheap** (negative VRP) | 30d implied < next-30d realized by ~6–12%/yr **every year except 2023 (+2%)** |
| E | **Skew: puts rich, calls cheap** | 25Δ put IV 103%, ATM 94%, **25Δ call 90%** (right tail underpriced) |
| F | Term structure mildly **inverted** | short-tenor IV > long on **65%** of days |
| G | Intraday: **U-shaped vol**, 5-min random, no EOD momentum | open ≈ **2.9×** midday |

## What it suggests (hand-off to strategy evaluation — not yet proven)

The facts point one direction: **you are paid to be LONG convexity (especially the
cheap calls) and to capture the overnight drift; you are punished for being SHORT
vol or for holding through the choppy grind.** Direction itself is not the edge —
volatility, convexity, and the overnight session are.

Candidate structures to evaluate next, ranked by fit:
1. **Long right-tail convexity** — buy the cheap calls (E) into the overnight up-drift (B′), fat tails (C), cheap options (D): long calls / call debit spreads / call ratio backspreads.
2. **Overnight-drift capture** — long delta close→open, flat/hedged intraday (Sharpe 1.60 vs 0.23). *Untested and the single most striking fact.*
3. **Long-vol, vol-timed** — own convexity because vol clusters (C) and is cheap (D); stand down when VRP turns positive (2023) or realized vol is low.
4. **Tactical mean-reversion** on extremes (buy after big down days, B″).
5. **Avoid selling premium**, especially puts (negative VRP + fat left tail).
6. **Harvest with a trailing exit**, not a fixed target (keep the fat-tail winners).

Items 1, 3, 5, 6 match what the strategy backtests already found empirically — the
neutral data analysis *explains why*. Item 2 (overnight capture) is new and is the
most promising untested lead.

### Finding B′ evaluated (`eval_overnight.py`)

Holding SOXL **close→open only, flat intraday** (2023-07→2026-07, the 5-min window):

| strategy | CAGR | ann vol | Sharpe | maxDD |
|---|--:|--:|--:|--:|
| Buy & hold | +104% | 115% | 1.20 | −88% |
| **Overnight-only** | **+145%** | **72%** | **1.60** | **−61%** |
| Intraday-only | −17% | 88% | 0.23 | −90% |

Overnight-only beats buy&hold on **return, Sharpe, and drawdown** at once — the
mechanism is **volatility drag**: it bleeds ~26%/yr vs buy&hold's ~66%, saving
~40%/yr by dodging the high-vol intraday session. The edge survives realistic
costs (SOXL spread ~1–3 bps/side): overnight CAGR is +121% at 2 bps, +110% at 3
bps, still Sharpe 1.39. Most striking: in the **choppy 2024**, overnight made
**+198%** while buy&hold lost −13% and intraday lost −71%.

**Honest limits:** in-sample 3-year window (misses the 2022 bear); overnight is
**long beta** (corr +0.64 to buy&hold; it loses in down months, −2.8%/mo avg) and
**gives up return in a straight melt-up** (2026: +158% vs buy&hold +358%); 'close'
is the 15:55 bar, not the 16:00 auction. **Highest-value additional data: daily
open (or 5-min) for 2022–2023H1** to test the drift across a full bear — decisive
for whether this is a persistent premium or a bull-period artifact.
