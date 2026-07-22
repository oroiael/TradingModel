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
| `overnight_6y.py` | **re-tests finding B′ on 6 real years** (2020–2026, split-adjusted): out-of-sample verdict, by-year session attribution, 6y volatility drag, free-overlay protection re-validated on real 2022 | **5-min 2020-07→2026-07 (real)** |
| `overnight_startstop_6y.py` | is a **6-month vol SMA** a useful start/stop for the overnight trade? (vs fast vol-target & trend filter) | 5-min underlying 2020–2026 |
| `overnight_option_tenor.py` | do **short-dated options reprice more** on the overnight move? elasticity/theta/net by DTE | real intraday options 2022–2026 |
| `bracket_weekly.py` | **hold vs write a weekly option bracket** + trade the underlying (delta-hedged): long vs short gamma, by year, tail protection | daily weekly options 2022–2026 |
| `overnight_bracket_combo.py` | put the **overnight ETF strategy inside a paid option bracket** (strike × tenor sweep) vs the free gate | overnight 6y + weekly options |
| `two_sleeve.py` | **overnight + weekly-bracket as two sleeves**: correlation, tail hedge, blend frontier | both, per weekly cycle 2022–2026 |

Charts land in `outputs/` (`underlying_signature.png`, `intraday_microstructure.png`,
`options_surface.png`, `overnight_6y.png`).

> **Data note (2026-07):** `SOXL_5min_6Years.csv` (real 5-min, 2020-07→2026-07)
> replaces the earlier reconstruction as ground truth for 2020–2023H1. Loaded via
> `data_loader.load_5min_6y()` / `daily_oc_6y()` with the 15:1 split back-adjusted.
> It validated the reconstruction and turned the overnight test into a real
> out-of-sample check — see `overnight_6y.py` and "Finding B′ RE-TESTED" below.

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
| B′ | …but the return lives **overnight** (structurally) | full-6y-real close→open **Sharpe 1.16 / drag 22%/yr** vs intraday **0.28 / hold 0.93**; the 3-year **Sharpe 1.60 was window-specific** (OOS 0.58) — see `overnight_6y.py` |
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
2. **Overnight-drift capture** — long delta close→open, flat/hedged intraday. *Now tested on 6 real years (`overnight_6y.py`): the mechanical drag edge holds (drawdown/compounding beat buy&hold), but the drift is long-beta/regime-dependent and the Sharpe 1.60 was window-specific (OOS 0.58) — gate it with vol/trend.*
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

### Finding B′ RE-TESTED on 6 years of REAL 5-min (`overnight_6y.py`) — the OOS verdict

The `SOXL_5min_6Years.csv` file (2020-07→2026-07) supplies exactly the missing data
above. It is clean and trustworthy: 1,497 days, 78 bars/session, zero nulls, **one
corporate action** (the 15:1 split 2021-03-02, back-adjusted ÷15 — the only overnight
gap outside [0.5, 2.0] in six years), overlap with the 3-year file **identical to
0.0000%**, and it **validates the 2022 put-call-parity reconstruction** (close error
0.17%, corr 1.0000). So the 2020–2023H1 half is a genuine **out-of-sample** test of an
edge discovered on 2023–2026.

| window | strategy | CAGR | vol | Sharpe | maxDD | MAR |
|---|---|--:|--:|--:|--:|--:|
| **full 6y** | buy&hold | +51% | 111% | 0.93 | −91% | 0.57 |
| **full 6y** | **overnight** | **+73%** | 66% | **1.16** | **−77%** | **0.94** |
| **full 6y** | intraday | −12% | 87% | 0.28 | −91% | −0.14 |
| **OOS 2020-07..2023-06** | buy&hold | +23% | 106% | **0.72** | −91% | 0.25 |
| **OOS 2020-07..2023-06** | overnight | +19% | 57% | 0.58 | −77% | 0.24 |
| **OOS 2020-07..2023-06** | intraday | +3% | 87% | 0.47 | −78% | 0.04 |
| discovery 2023-07..2026 | overnight | +149% | 74% | **1.60** | −61% | 2.43 |

**The honest verdict — two parts, only one of them robust:**

1. **Robust (mechanical):** overnight has **~⅓ the volatility drag** of buy&hold on the
   full 6 years (**22%/yr vs 62%/yr**) because it sits out the high-variance intraday
   session. So it has **lower drawdown and lower vol than buy&hold in every sub-period**
   and a **higher geometric return over the full sample** (+73% vs +51%). This is a
   structural leverage-tax fact, and it holds.
2. **NOT robust (the headline Sharpe):** the eye-popping **Sharpe 1.60 was specific to
   the 2023–2026 window.** Out-of-sample it is **0.58 — below buy&hold's 0.72.** The
   directional drift is **long beta and regime-dependent, not stationary:**

   | year | overnight | intraday | who carried it |
   |---|--:|--:|---|
   | 2020 | +83% | +12% | overnight |
   | 2021 | +98% | +17% | overnight |
   | **2022** | **−97%** | −15% | overnight **caused the whole crash** |
   | **2023** | +23% | **+125%** | **intraday** (overnight went quiet) |
   | 2024 | +142% | −98% | overnight |
   | 2025 | +73% | +38% | overnight |
   | 2026 | +117% | +69% | overnight |

**Conclusion:** the overnight session is genuinely the better place to hold SOXL —
lower drag, lower drawdown, better compounding — but the *magnitude* of the edge was
overstated by the bull-heavy 3-year window, and **the drift reverses hard in a bear
(2022: essentially the entire −114% happened overnight)**. This is not a free Sharpe
1.6; it is a long-beta exposure that must be **vol-/trend-gated**. Re-running the free
overlays on the real 6 years confirms it: base overnight −77% maxDD → **combo
vol_target × trend −55%** (CAGR +41%, Sharpe 1.07), matching the reconstruction-based
protection result. *The earlier −61%/−76% drawdown figures are now superseded by the
real −77% full-6y ground truth.*

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

### Does a SHORT-DATED option reprice more overnight? (`overnight_option_tenor.py`)

Direct test of the intuition that *short-dated options reprice immediately on an
overnight swing while longer-dated ones don't.* 41,073 real overnight call
round-trips (2022–2026), underlying move measured 15:55→09:30 from the 6-year feed so
it matches the option prints. **Elasticity** = option %-move per 1% underlying
overnight move (regression through origin); **theta** = mean option move on ~flat
nights (|underlying|<0.5%):

| DTE bucket (ATM) | nights | elasticity | R² | theta/night (flat) | net @ h=5% |
|---|--:|--:|--:|--:|--:|
| **weekly 1–7D** | 2,229 | **+11.1** | 0.73 | **−8.2%** | −4.6% |
| 2–3wk 8–20D | 2,346 | +6.3 | 0.81 | −2.5% | −7.6% |
| monthly 21–45D | 1,245 | +4.4 | 0.83 | −1.7% | −7.6% |
| quarterly 46–90D | 314 | +3.2 | 0.85 | +0.2% | −8.9% |
| long 91–250D | 185 | +2.3 | 0.87 | ~0 | −9.0% |

**Your intuition is correct on the mechanics.** Elasticity rises sharply as DTE
falls: a **weekly ATM call moves ~11%** per 1% overnight underlying move (and tracks
it — the up-night/down-night split is +50%/−41%), while a **90–250D call moves only
~2.3%** (muted, dominated by time value/vega). Short-dated options *do* reprice most
fully on the overnight gap — it is a delta/gamma-per-premium effect, and it's even
stronger for OTM weeklies (elasticity +14.5).

**But the same shortness that lifts elasticity raises both costs**, so it is *not* the
fix: the weekly ATM call bleeds **−8%/night in theta on flat nights** (a night is a big
slice of its remaining life) and cheap near-expiry options carry the **widest %-spreads**,
worst at the 09:30 open. Net of a realistic ~5% haircut the overnight call round-trip
**loses at every tenor** (weekly −4.6%/night, long −9.0%). The higher elasticity of the
short-dated option is exactly cancelled by its higher theta + spread.

**Bottom line for close→open option trading:** the option repricing you're picturing is
real and largest for short-dated — but capturing the overnight drift with a *nightly
option round-trip* pays too much premium to carry, at any tenor. Use the **ETF** for the
overnight drift (1–3 bps); if you want option **convexity**, hold calls **continuously**
rather than churning them every night. *Decisive missing data (unchanged): intraday
option bid/ask — but the theta wall alone sinks the short-dated version even gross of spread.*

### HOLD the weekly bracket + trade the underlying (`bracket_weekly.py`) — this works

The right way to use short-tenor options here is **not to churn them** but to **hold a
weekly bracket (call+put) as a standing position while you trade the *underlying***.
Delta-hedging the held bracket with the underlying is the neutral, assumption-free
version of "trade actively, let the options protect you," and it isolates the
structural edge. Tested on 235 real weekly cycles (2022–2026), entered at real EOD
bid/ask, hedged daily on the chain's EOD deltas, held to expiry:

| structure (delta-hedged, %/wk of notional) | ann | win% | Sharpe | worst wk |
|---|--:|--:|--:|--:|
| **LONG straddle (ATM) = hold bracket** | **+41%** | 50% | **+0.95** | −14% |
| SHORT straddle (ATM) = write bracket | −97% | 40% | −2.20 | −39% |
| LONG strangle (~5% wings) | +31% | 45% | +0.74 | −11% |
| SHORT strangle (~5% wings) | −76% | 46% | −1.82 | −39% |

**Holding the bracket (long gamma) made +41%/yr, Sharpe 0.95, positive every year but
2023; writing it (short gamma) lost −97%/yr, every year.** This is the same lesson as
all prior work — *be long convexity on SOXL, never sell premium* — now shown for the
exact structure you described. The delta-hedged long-gamma P&L is positive **by
construction the harvested (realized − implied) variance**, corroborating the negative
30-day VRP: SOXL's weekly moves are underpriced by weekly implied. Mechanism = **long
the fat weekly tails**: it wins only ~half of weeks but the wins are bigger (P95 +8.7%
vs P5 −6.5%), so it's a bet on kurtosis/convexity, not average vol — which is why it
fails *only* in the calm, low-realized **2023** (the one +VRP year).

Two things this nails from your framing:
- **"If something gets away from you the options have protection"** — confirmed: the
  long bracket's worst week is **−14% (bounded ≈ premium)** with a fat right tail that
  *pays* on runaways, vs the short bracket's **−39% unbounded left tail**. Holding the
  bracket *is* the insurance; writing it sells the insurance.
- **"Trade actively on the underlying"** — I tested the neutral rules version (daily
  delta hedging, **no assumed directional skill**). Any real directional edge you have
  in the underlying is **additive on top**; if you have none, the long bracket still
  pays and caps the loss. The one control it needs is a **realized-vs-implied (or plain
  realized-vol) gate** — stand down when moves collapse below what implied charges
  (2023), the same regime dial the overnight trade needs.

*Caveats: EOD daily hedging (not continuous) — but that deliberately captures the
overnight gaps where SOXL moves; deltas are the chain's stamped EOD greeks; it is an
aggressive book (~12.6% of notional in premium at risk each week).*

### Can finding B′ (overnight) live INSIDE the bracket? (`overnight_bracket_combo.py`, `two_sleeve.py`)

Two ways to combine the **overnight-drift ETF** strategy with the **weekly bracket** —
one fails, one is the real answer.

**(a) Stuff the option into the overnight instrument — DOMINATED.** Holding a rolled
put (or full bracket) *on top of* the overnight ETF and sweeping strike × tenor
(2022–2026, real bid/ask): the put *does* cut the 2022 tail (−76% → −63%), and the far-
OTM **−12% monthly** put is the least-bad (MAR 0.30, −20%/yr cost). But **every paid
config is dominated on the CAGR-vs-drawdown frontier by the FREE vol/trend gate**:

| config | CAGR | maxDD | MAR |
|---|--:|--:|--:|
| base overnight | +42% | −77% | 0.54 |
| **free combo (vol_target × trend)** | +26% | **−55%** | 0.48 |
| −12% monthly put (best paid) | +23% | −77% | 0.30 |
| −5% **weekly** put | +11% | −80% | 0.13 |
| free combo + −8% weekly put | −7% | −72% | −0.09 |

Weekly puts are the **worst value** (max theta — the exact tenor that felt right is the
wrong one to *buy and hold*). Worse, a continuously-held put often makes the *overall*
drawdown **deeper**, because the strategy is exposed only overnight while the put bleeds
24/7 — you pay for intraday insurance the strategy doesn't use. **Reducing exposure
(free gate) beats insuring it (paid) here, because the puts are rich.**

**(b) Run them as TWO SEPARATE SLEEVES — the free lunch.** The delta-hedged long-gamma
bracket **profits in crashes** (2022: **+76%**) exactly when the overnight ETF **bleeds**
(2022: **−51%**). Measured per weekly cycle, the two sleeves' correlation is **−0.01**,
and **in the overnight sleeve's worst-decile weeks the bracket sleeve returns +2.9%** —
it pays when the overnight bleeds. So the bracket is **self-funding crash insurance**
(unlike a bought put, it earns a positive Sharpe on its own *and* hedges the tail):

| blend (w overnight / bracket) | CAGR | Sharpe | maxDD | MAR |
|---|--:|--:|--:|--:|
| 100% overnight / 0% | +22% | 0.68 | −67% | 0.33 |
| 0% / 100% bracket | +38% | 0.95 | −44% | 0.86 |
| **~40% / 60% (best Sharpe)** | **+37%** | **1.17** | **−36%** | 1.02 |
| 30% / 70% (best MAR) | +38% | 1.14 | −35% | 1.10 |

By year the blend is positive every year **but the calm 2023** (−7%), and it turns the
overnight strategy's 2022 disaster (−51%) into **+12%**. The blend beats *both* sleeves
on Sharpe **and** drawdown — a genuine diversification benefit grounded in the economics
(long gamma pays in the crashes long beta suffers), not curve-fitting.

**Answer to "what's optimal for this to work":** you can't fuse them into one instrument
— the bracket's edge *needs* the delta hedge that an overnight tilt would replace, and
buying the option outright is dominated by the free gate. **Run the gated overnight and
the delta-hedged weekly bracket side by side (~⅓–½ in overnight), governed by the same
realized-vol/trend dial.** That gives the overnight strategy's return with roughly half
its drawdown, and the one shared weak spot (a calm, low-vol year like 2023) is exactly
what the vol gate is there to dial down. *Caveat: the blend weight is in-sample, but the
~zero/negative-tail correlation and "any ⅓–½ mix beats both" hold across the frontier.*
