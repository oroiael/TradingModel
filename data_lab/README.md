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

## Drawdown protection for the overnight strategy (`eval_overnight_protection.py`)

First, **2022 is now usable**: `reconstruct_underlying.py` rebuilds the intraday
underlying from the option chain via **put-call parity** (S ≈ Call − Put + K),
validated to **0.15% median error, corr 1.0000** vs the daily underlying and
0.15–0.29% vs the real 5-min feed. Adding 2022 shows the overnight drift
**reverses in a bear** (2022 overnight −65%), so the *true* full-period drawdown is
**−76%**, not −61%. The question: can options/pricing mitigate it?

Overlays on the overnight strategy, full 2022–2026 (MAR = CAGR / |maxDD|):

| overlay | CAGR | vol | Sharpe | **maxDD** | MAR |
|---|--:|--:|--:|--:|--:|
| base (no protection) | +42% | 71% | 0.85 | **−76%** | 0.55 |
| **vol_target 60%** (free) | **+45%** | 57% | **0.93** | −65% | **0.69** |
| **trend: flat below SMA50** (free) | +37% | 49% | 0.89 | **−57%** | 0.65 |
| combo vol_target × trend (free) | +28% | 40% | 0.82 | −54% | 0.52 |
| dd_stop −25% (free) | −6% | 9% | −0.69 | −26% | −0.24 |
| **rolled 7% OTM put** (paid, real bid/ask) | +14% | 62% | 0.53 | −72% | 0.20 |

**The pricing tells the story you asked about:** the **rolled protective put costs
~27%/yr net** (SOXL puts are *rich* — skew +9%) and **barely dents the drawdown**
(−76% → −72%), gutting return (+42% → +14%). Paying for options protection here is
a bad trade *because of the pricing*. The best mitigation is **free and comes from
the volatility clustering the data analysis found**: **vol-targeting cuts maxDD to
−65% while *raising* return and Sharpe**; the **trend filter cuts maxDD to −57%**
for a modest return give-up. A hard **stop-loss whipsaws** (kills return). Residual
drawdowns stay large (−54% to −65%) — this is an aggressive 3× ETF strategy — but
they can be cut meaningfully for free, and *not* worth insuring with rich puts.

### Cheaper option structures + the best free overlay (`eval_protection_combined.py`)

You asked to test *cheaper* hedges than the rich outright put and to combine the
best **free** overlay. Every leg priced from real bid/ask, 2022–2026.

**Cheaper protective puts, on the overnight book** (net cost = annualized option P&L):

| structure | CAGR | maxDD | Sharpe | MAR | net cost/yr |
|---|--:|--:|--:|--:|--:|
| outright 7% put | +6% | −72% | 0.41 | 0.09 | −35% |
| put spread 7/20% | +8% | −72% | 0.45 | 0.11 | −31% |
| **tail put 15%** | **+14%** | **−71%** | **0.52** | **0.20** | **−27%** |
| *(base, no hedge)* | *+42%* | *−76%* | *0.85* | *0.55* |

Cheaper structures **do** cut the bleed (tail-put 15% ≈ −27%/yr vs outright −35%),
but **all still gut return and barely move the −76% drawdown** — puts are too rich
(skew +9%) to buy. Least-bad is the far **tail put**, still only MAR 0.20 vs base 0.55.

**Collar** (sell a call to fund the put): can't go on this book — a continuous short
call needs a continuous long, but the overnight strategy is long *only overnight*, so
bolting one on just hands away the intraday upside it never took (a −99% **basis
artifact**, not a real result). Tested fairly on **buy&hold**, the collar is *also* a
losing trade (7%/7% collar: **−34% CAGR, −84% maxDD** vs buy&hold +16%/−90%): SOXL's
**calls are cheap** (skew), so *selling* them is negative-EV just as *buying* puts is.
**Both sides of the SOXL option market are priced against the hedger.**

**Best free overlay, and free + a cheap option tail on top:**

| config | CAGR | vol | Sharpe | maxDD | MAR |
|---|--:|--:|--:|--:|--:|
| base | +42% | 71% | 0.85 | −76% | 0.55 |
| **vol_target (free)** | **+45%** | 57% | **0.93** | −65% | **0.69** |
| **combo free (vol_target × trend)** | +28% | 40% | 0.82 | **−54%** | 0.52 |
| combo free + put spread 7/20% | −5% | 40% | 0.06 | −57% | −0.10 |
| combo free + tail put 15% | −7% | 50% | 0.11 | −68% | −0.10 |

**Adding *any* paid option tail on top of the free overlay makes it worse** — the
free overlay already removed most of the crash exposure, so the option just bleeds:
combo free +28%/−54% collapses to −5%/−57% (put spread) or −7%/−68% (tail put), and
the full-period drawdown actually **rises**. By-year, the tail doesn't even reliably
cut the annual drawdown (2025/2026 are worse with it).

**Recommendation:** the drawdown is best cut **for free, with no bought protection.**
Use **combo vol_target × trend** for the smallest swing (−76% → −54%), or **vol_target
alone** for the best return-per-drawdown (MAR 0.69 — and it *raises* return). The
pricing verdict is unchanged and now symmetric: **don't insure with rich puts, and
don't fund it by selling cheap calls.**

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

### Overnight drift via cheap CALLS (`eval_overnight_calls.py`) — fails on cost

The natural refinement (use the cheap calls so down months are capped) was tested
on **real intraday option prints, 2022–2026**: buy a call at 15:55, sell at the
09:30 open. **Gross of spread the signal is real** (+5% 30D call: +3.2%/night,
ann. Sharpe ~1.9, right-tail-driven). **But it does not survive the option bid/ask:**

| half-spread h | mean/night | ann Sharpe | outcome |
|---|--:|--:|---|
| 0% | +3.2% | +1.9 | 21.6× |
| **2.5%** | **−1.8%** | **−1.1** | **→ $0** |
| 5% | −6.6% | −4.2 | → $0 |
| 10% | −15.6% | −11.0 | → $0 |

A nightly option round-trip pays ~2h of premium; near-money option spreads are
~10% (h≈5%), widest at the 09:30 open. Even an optimistic 2.5% half-spread turns
+3.2%/night into −1.8% and ruin. The downside also isn't well-capped in bears
(2022 gross −2.8%/night). **Conclusion: capture the overnight drift with the ETF
(1–3 bps to trade), NOT with options — the microstructure kills the nightly
round-trip.** (Holding calls *continuously* is a different, viable thing — that is
just "long calls," already validated in the strategy work — but it does not
isolate the overnight session.) *Highest-value data here: intraday option bid/ask;
though the sensitivity is so steep the conclusion is robust to it.*
