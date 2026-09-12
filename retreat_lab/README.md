# retreat_lab — how long SOXL holds an upswing before giving it back

```bash
git lfs pull                                # SOXL_1min.csv, SOXL_5min_6Years.csv
python3 retreat_lab/retreat_timing.py       # all five configs -> retreat_lab/out/
python3 retreat_lab/retreat_timing.py 150 40   # or any (up_bps, dn_bps) pair
python3 retreat_lab/verify.py               # re-checks every episode against raw bars

SYMBOL=FAS python3 retreat_lab/overnight.py 1   # any symbol with a <SYM>_1min.csv
```

`SYMBOL` (default `SOXL`) selects the instrument for every script in this directory.
SOXL's output filenames are unchanged; any other symbol is namespaced with a suffix,
so the two never collide. See "FAS — the port, and it does not carry" below.

Stdlib only. Measured from `SOXL_1min.csv` — 1-min OHLCV, **2019-12-31 → 2026-07-30,
642,510 bars, 1,653 sessions**, complete minute grid (zero missing minutes), no OHLC
inconsistencies, split-adjusted (largest overnight moves are real events — COVID
March-2020, 2024-08-05 — not basis breaks). Cross-checked on `SOXL_5min_6Years.csv`.

## The SOXL + TQQQ + SPXL basket — it does not help

`basket.py`. Walk-forward p60 per leg, backtest from 2023 (the estimator is
allowed the 2021-22 history that precedes it — a warm start, not look-ahead),
1 bp/side. The 2022-inclusive window is printed alongside so the cost of
excluding it is visible rather than assumed.

### The three legs are nearly the same trade

Correlation of the filtered overnight streams, eligible nights only:

| | SOXL | TQQQ | SPXL |
|---|---|---|---|
| **SOXL** | 1.00 | 0.87 | 0.79 |
| **TQQQ** | 0.87 | 1.00 | **0.95** |
| **SPXL** | 0.79 | 0.95 | 1.00 |

TQQQ and SPXL at **0.95** are not two assets. There is very little to diversify.

### From 2023 (889 sessions, 3.5y)

| policy | total | CAGR | max DD | Sharpe | t |
|---|---|---|---|---|---|
| **SOXL alone (filtered)** | **531%** | **68.1%** | −29.5% | **1.38** | 2.60 |
| TQQQ alone | 186% | 34.5% | −27.0% | 1.17 | 2.21 |
| SPXL alone | 65% | 15.2% | −26.2% | 0.78 | 1.46 |
| 1. fixed 1/3, **no** filter | 304% | 48.3% | −51.4% | 1.12 | 2.11 |
| 2. fixed 1/3, gated | 225% | 39.4% | **−23.2%** | 1.30 | 2.45 |
| **3. renormalised across eligible** | 286% | 46.4% | −26.7% | **1.32** | 2.49 |
| 4. inverse-vol across eligible | 223% | 39.2% | −24.7% | 1.25 | 2.36 |
| 5. breadth ≥ 2 legs | 249% | 42.3% | −26.7% | 1.31 | 2.47 |
| 6. concentrate in lowest RV20 | 127% | 26.0% | −26.2% | 1.06 | 1.99 |

**No allocation policy beats SOXL alone on Sharpe, and none comes close on
return.** The pattern is mechanical: every "sophisticated" rule shifts weight
*away* from SOXL, which is the only leg carrying an edge. Inverse-vol
systematically underweights the highest-vol leg; concentrating in the lowest
RV20 name picks SPXL or TQQQ most nights and is the worst policy of the six.

The textbook condition says it all — adding an asset helps only if its Sharpe
exceeds correlation × the existing Sharpe:

| leg | needs Sharpe > | has | verdict |
|---|---|---|---|
| TQQQ | 0.87 × 1.38 = **1.20** | 1.17 | a wash |
| SPXL | 0.79 × 1.38 = **1.09** | 0.78 | dilutes |

### The SOXL tilt — a flat ridge

| SOXL weight | CAGR (from 2023) | max DD | Sharpe | CAGR (incl. 2022) | Sharpe |
|---|---|---|---|---|---|
| 33% | 46.3% | −26.7% | 1.32 | 37.2% | 1.13 |
| 50% | 52.5% | −28.5% | 1.35 | 40.8% | 1.14 |
| 70% | 59.5% | −30.6% | 1.36 | 45.0% | 1.15 |
| 80% | 63.0% | −31.6% | 1.36 | 47.0% | 1.15 |
| **100%** | **68.1%** | −29.5% | **1.38** | **51.1%** | **1.20** |

Sharpe is flat from 33% to 100% and the return rises monotonically with the SOXL
weight. On these numbers there is no interior optimum.

### But the Sharpe differences are not measurable

| window | SOXL alone | best basket | gap | SE of one Sharpe |
|---|---|---|---|---|
| from 2023 (n=889) | 1.38 | 1.32 | 0.06 | **~0.75** |
| incl. 2022 (n=1,197) | 1.20 | 1.13 | 0.07 | **~0.60** |

The gap is a tenth of the standard error. **The backtest cannot tell these
apart**, so "SOXL alone wins" is a statement about point estimates, not a
measured superiority.

### What excluding 2022 is worth

| | incl. 2022 | from 2023 | difference |
|---|---|---|---|
| SOXL alone, filtered | 51.1% CAGR, Sharpe 1.20 | 68.1%, 1.38 | **+17 pp CAGR** |
| fixed 1/3, no filter | 16.2% CAGR, −68.0% DD | 48.3%, −51.4% | **+32 pp CAGR** |

The filtered strategy loses far less to 2022 than the unfiltered basket does —
which is itself evidence the filter works — but 17 points of CAGR is the
premium being assumed away.

### The 60/30/10 tilt, year by year

`python3 retreat_lab/basket.py 1 2023`. Weights are SOXL 60 / TQQQ 30 / SPXL 10,
renormalised over whichever legs are eligible that night.

| policy | total | CAGR | max DD | Sharpe | t | avg deployed |
|---|---|---|---|---|---|---|
| SOXL alone (filtered) | 531% | 68.1% | −29.5% | **1.38** | 2.60 | 65% |
| **60/30/10** | **408%** | **58.2%** | −30.4% | **1.37** | 2.57 | 88% |
| equal 1/3 renormalised | 286% | 46.4% | −26.7% | 1.32 | 2.49 | 88% |
| fixed 1/3, no filter | 304% | 48.3% | −51.4% | 1.12 | 2.11 | 100% |

**60/30/10 recovers essentially all of SOXL-alone's Sharpe (1.37 vs 1.38) while
holding only 60% of it**, and deploys 88% of capital against SOXL-alone's 65%.

| year | sessions | 60/30/10 | SOXL only | equal 1/3 | 1/3 no filter |
|---|---|---|---|---|---|
| 2023 | 250 | **−0.4%** | **+7.1%** | −0.1% | +1.2% |
| 2024 | 252 | **+135.5%** | +121.4% | +103.1% | +117.4% |
| 2025 | 250 | **+119.9%** | +104.2% | +102.7% | +31.3% |
| 2026 (to 07-21) | 137 | **−1.5%** | **+30.2%** | −6.1% | +39.9% |
| **all** | 889 | **+408.5%** | +530.6% | +286.3% | +304.3% |

Worst drawdown reached within each year:

| policy | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| 60/30/10 | −27.2% | −16.4% | −21.6% | −30.4% |
| SOXL only | −29.5% | −17.8% | −23.7% | −25.0% |
| equal 1/3 | −24.3% | −13.5% | −20.6% | −26.7% |
| 1/3 no filter | −25.6% | −23.5% | −51.4% | −27.6% |

**The whole result is 2024 and 2025.** 2023 was flat and 2026 to date is
slightly negative, against a −30.4% intra-year drawdown. Two good years out of
three and a half is the shape of this strategy, and any live allocation has to
survive a year like 2023 — flat, while semiconductors themselves rose sharply —
without being abandoned.

**60/30/10 beat SOXL-alone in 2024 and 2025 and lost badly in 2026** (−1.5%
against +30.2%). The diversification is real but it cuts both ways, and over
3.5 years it costs 10 pp of CAGR for a Sharpe that is identical to within noise.

Return concentration, 60/30/10:

| | removing the best | removing the worst |
|---|---|---|
| 5 nights | +408% → **+199%** | → +725% |
| 10 nights | → +115% | → +1,058% |
| 20 nights | → **+22%** | → +1,855% |

Twenty nights out of 889 are the entire return. Worst night −13.1%
(2025-01-24, the DeepSeek weekend); best +19.9% (2025-05-09).

Contribution by leg over the window: SOXL +149.5%, TQQQ +47.3%, SPXL +8.6% of
summed weighted return — SPXL earns close to nothing for its 10%.

### The answer on allocation

**Neither a fixed split nor an indicator-driven one adds anything.** The
eligibility filter is already the dynamic allocation, and it is the only part
that pays. Given eligibility, split evenly across whichever legs qualify —
renormalised beat every alternative in *both* windows (1.32 and 1.13). Do not
inverse-vol weight, do not add a breadth condition, do not concentrate.

## TQQQ and SPXL — the replication, and two corrections it forces

`replicate.py`. FAS was the only external test and it failed; that is n=1. TQQQ
(3× Nasdaq-100, IBKR daily bars 2021-09 →) and SPXL (3× S&P 500, 5-min 2020-07 →)
make it four instruments. **The headline result replicates. Two things I
concluded from SOXL and FAS alone do not.**

**Control first.** TQQQ is daily-sourced, so SOXL was run from daily bars against
SOXL from 1-minute bars over 1,204 shared sessions: overnight-return correlation
**0.99921**, mean overnight difference **−1.82 bp/night** (daily slightly
understates the overnight leg). Daily-sourced figures are readable on the same
footing, and if anything are conservative.

### Correction 1 — "the intraday leg is variance drag" is not general

| symbol | buy & hold | overnight | intraday |
|---|---|---|---|
| SOXL | +532% | +2,092% | **−71%** |
| FAS | +76% | +230% | **−47%** |
| SPXL | +397% | +223% | **+54%** |
| TQQQ | +130% | +85% | **+24%** |

On SPXL and TQQQ the intraday leg is **positive**. Variance drag is ½σ², so it
only *dominates* where vol is high enough — semis and financials — not as a law.
"Go flat intraday, it is free" is right for SOXL and is **not** a general claim.

### Correction 2 — the conditioner is NOT merely a trend proxy

`mechanism.py` concluded RV20 was a trend signal in disguise, from SOXL (where
the two agree) and FAS (where trend worked and vol did not). The two new
instruments separate them, and they go the other way:

| symbol | hold every night | **RV20 < p60** | trailing-20d-return |
|---|---|---|---|
| SOXL | 0.96 | **1.39** (t 3.53) | 1.19 (t 3.02) |
| FAS | 0.52 | 0.60 (t 1.55) | **0.77** (t 1.98) |
| SPXL | 0.64 | **0.97** (t 2.37) | 0.33 (t 0.81) |
| TQQQ | 0.39 | **1.24** (t 2.74) | 0.37 (t 0.81) |

(Sharpe, 60% of nights kept either way.) The two rules select 68–75% of the same
nights, and correlate −0.25 to −0.39 — overlapping but not the same signal, and
the quarter that differs favours **volatility** on three of four names. The
trend-proxy reading was over-generalised from two instruments. **The SOXS mirror
finding is untouched** — the *return* is still directional sector beta, not an
overnight structural premium. What is refuted is that the *conditioner* is only
trend.

### On the same sessions, 2021-10-12 → 2026-07-21 (1,197 nights)

| symbol | overnight | intraday | RV20<p60 CAGR | Sharpe | t | trend CAGR | Sharpe | t |
|---|---|---|---|---|---|---|---|---|
| SOXL | +423% | −17% | 50.3% | 1.14 | **2.50** | 33.2% | 0.81 | 1.77 |
| TQQQ | +71% | +34% | 28.9% | 1.21 | **2.65** | 6.5% | 0.38 | 0.82 |
| SPXL | +45% | +70% | 17.9% | 1.04 | **2.26** | 4.3% | 0.32 | 0.70 |
| FAS | +13% | +18% | 2.0% | 0.20 | 0.43 | −2.2% | 0.00 | 0.00 |

### Walk-forward — the sober version

Expanding-window threshold, 252-session burn-in, no forward information:

| symbol | hold every night | walk-fwd p60 | walk-fwd p80 |
|---|---|---|---|
| SOXL | 0.80 (t 1.88) | **1.08 (t 2.53)** | 0.83 (t 1.94) |
| TQQQ | 0.94 (t 1.86) | **1.09 (t 2.15)** | 1.08 (t 2.13) |
| SPXL | 0.28 (t 0.62) | 0.62 (t 1.37) | 0.85 (t 1.89) |
| FAS | 0.39 (t 0.93) | 0.40 (t 0.94) | 0.31 (t 0.73) |

**Two of four clear t = 2 walk-forward.** SPXL is directionally right but not
significant; FAS is nothing. And the TQQQ walk-forward window begins ~2022-10,
so **the 2022 bear market falls in its burn-in** — the same blind spot SOXL's
has. The in-sample TQQQ run (t 2.74) *does* include 2022; the walk-forward does
not. Read them together, not as one number.

**No instrument is monotone in RV20 quintiles**, SOXL included. The cut works by
excluding the top two quintiles, not by a clean gradient.

### What this changes

The filter is **not SOXL-specific**. It has independent support on TQQQ and
partial support on SPXL, which is the evidence that was missing. It remains a
fitted cut on a non-monotone relationship, failing outright on one of four
instruments, and the return underneath it is still levered sector beta.

## Pricing the 3x SOXX carry against a real IBKR margin rate

`carry.py`. The earlier 3.55 bp/night advantage of 3× SOXX over SOXL was
measured **over all nights and gross of everything**. Priced properly against
IBKR's actual rates, on the nights the strategy actually holds, **it disappears
and then goes negative.**

Three corrections, each of which shrinks it:

**1. Match on realised beta, not a nominal 3.0.** Overnight beta of SOXL to SOXX
on the filtered set is **2.9701**. A flat 3.000× shows +4.48 bp/night, but 10%
of that is simply holding more exposure than SOXL gives. Beta-matched: **+4.03
bp/night**.

**2. The SOXX route trades ~3× the notional for the same exposure**, so it pays
~3× the dollar friction. This term is bigger than the advantage it chases:

| term (bp/night, per unit of equity) | equal bp cost | SOXX at half the bp cost |
|---|---|---|
| gross SOXX advantage | +4.03 | +4.03 |
| SOXL trading cost (1× notional) | −2.00 | −2.00 |
| SOXX trading cost (2.97× notional) | **−5.94** | −2.97 |
| **= net before financing** | **+0.09** | **+3.06** |

**3. Interest is charged per calendar DAY, not per night.** 903 nights held over
5.8 years carry **1,315 interest-days** — 1.46 days/night, because 188 of them
are weekend or holiday gaps. That is **227 interest-days a year** on a 1.97×
debit.

### The breakeven, and the answer

| assumption | breakeven margin rate |
|---|---|
| SOXX costs the same bp/side as SOXL | **0.11% / yr** |
| SOXX costs half the bp/side (generous) | **3.89% / yr** |

IBKR Pro Tier 1 is **5.12%** as of 2026-09 (benchmark ≈ Fed Funds 3.62% + 1.5%);
higher tiers narrow the spread toward ~4.4%.

| your margin rate | interest / yr | net vs SOXL | net CAGR | vs SOXL |
|---|---|---|---|---|
| 4.37% | 5.36% | −3.35 bp/night | 60.0% | **−8.5 pp** |
| 4.62% | 5.67% | −3.54 bp/night | 59.5% | **−9.0 pp** |
| 5.12% | 6.28% | −3.94 bp/night | 58.6% | **−9.9 pp** |

**SOXL wins on carry at every rate IBKR charges**, by 8.5–9.9 pp of CAGR. Even
on the generous assumption that SOXX trades at half SOXL's bp cost, breakeven is
3.89% — still below Tier 1, and roughly a wash at the best tier.

### And the margin footprint kills it independently

| route | notional / equity | leverage used |
|---|---|---|
| 1× SOXL at 3× semis | 1.0× | 1.0 : 1 |
| ~3× SOXX at 3× semis | 3.0× | 3.0 : 1 |
| 1× SOXL at f = 2.0 (6× semis) | 2.0× | 2.0 : 1 |
| ~3× SOXX at f = 2.0 (6× semis) | **6.0×** | **6.0 : 1** |

Identical economics, 3× the gross notional. Against the 3:1 portfolio-margin cap,
SOXL at f = 2.0 fits and the SOXX route does not exist.

**Verdict: stay in SOXL.** The embedded financing you are paying is cheaper than
the financing you can buy, and the leverage is cheaper in margin capacity too.

## The SOXX hedge, tested — the argument was wrong

`soxx_hedge.py`, quotes in `out/option_quotes_20260911.csv`, pulled from IBKR on
2026-09-11 (7 DTE, expiry 2026-09-18, matching the historical test's tenor band).

The claim to test: the SOXL put overlay fails on **spread**, not premium, so
expressing the trade in SOXX — a $500, mega-liquid, ~38%-IV ETF — should make
the hedge affordable. **It does not. SOXX is worse on both legs.**

Two things had to be got right, and the first is easy to get wrong:

1. **Moneyness matches in underlying-move terms, not strike terms.** SOXL moves
   3× SOXX, so a k% OTM SOXL put corresponds to a **(k/3)%** OTM SOXX put.
   Comparing "5% OTM" on both compares a 5% SOXL move against a 15% one.
2. **Notional matches at 3× for SOXX.** This does *not* by itself penalise SOXX:
   its premium per unit notional is ~1/3 of SOXL's because its vol is ~1/3, so
   3× notional costs about the same premium. Only the spread *percentage*
   differs, and that is what the comparison isolates.

| SOXL-equiv strike | SOXL premium | SOXX premium | SOXL spread | SOXX spread | ratio |
|---|---|---|---|---|---|
| ~ −3% | 539 bp | 565 bp | 13.7% | 21.5% | 1.6× |
| ~ −4.5% | 464 bp | 510 bp | 3.7% | 18.2% | 4.9× |
| ~ −7% | 379 bp | 406 bp | 14.9% | 25.7% | 1.7× |
| ATM | 643 bp | 655 bp | 8.8% | 28.3% | 3.2× |

Premiums are within 2–10% of each other, as the vol ratio predicts. **Spread as
a fraction of premium is 2.3× worse on SOXX** (median 25.7% against 11.2%).

**Why the argument failed.** It confused *underlying* liquidity with *option*
liquidity. SOXX the ETF is far bigger and calmer than SOXL; SOXX **options** are
thin. Open interest at the same 7-DTE expiry, away from round strikes: SOXL 141
and 91, SOXX 31 and 23. SOXL is one of the most heavily optioned ETFs in the
market — the speculative flow that makes it violent is also what makes its
weeklies tight.

### The breakeven, and why the margin makes the caveats irrelevant

Sweeping the spread through the historical overlay (real 15:55 → 09:30 prints,
397 covered nights):

| round-trip spread | CAGR | max DD | Sharpe |
|---|---|---|---|
| unhedged | 12.1% | −53.5% | 0.527 |
| 0% | 10.8% | **−41.6%** | **0.592** |
| **1%** | 8.9% | −44.2% | **0.510 — falls below unhedged** |
| 5% | 1.7% | −53.5% | 0.184 |
| 10% | −6.6% | −65.3% | −0.225 |

**The overlay stops helping at about a 1% round-trip spread.** Measured: SOXL
11.2% (**11× breakeven**), SOXX 25.7% (**26× breakeven**).

The quotes are FROZEN — pulled after Friday's close, so wider than intraday for
both names. It does not matter: halve both and they are still **6×** and **13×**
breakeven. No plausible quote-timing error closes a gap of that size.

### Verdict

The put overlay is dead in both expressions, and SOXX is the worse of the two.
The separate 3.55 bp/night carry gap is priced in "Pricing the 3x SOXX carry"
above and does **not** survive: beta-matching, 3x the trading friction and real
margin interest turn it into a 8.5-9.9 pp/yr disadvantage. Options as a drawdown tool on this strategy
are now closed.

## Mitigating the drawdown — seven candidates, and what survives

`drawdown.py`. The −29.5% drawdown on the p60 strategy is a **tail, not a
grind**: the deepest episode (2023-07-31 → 2023-10-25) runs 61 nights, and its
**worst 5 nights are 88% of it**. Across all 979 nights only 13 are worse than
−8%.

| removing the … | total becomes |
|---|---|
| — | +2,248% |
| 1 worst night | +2,679% |
| 5 worst nights | +4,459% |
| 10 worst nights | +7,316% |

### The sizing frontier — what every candidate has to beat

| size | CAGR | max DD | Sharpe |
|---|---|---|---|
| 0.25× | 14.8% | −8.0% | **1.39** |
| 0.50× | 30.3% | −15.6% | **1.39** |
| 1.00× | 62.7% | −29.5% | **1.39** |
| 2.00× | 122.7% | −56.8% | **1.39** |

Sharpe is flat to four positions. Any hedge worth adding has to raise it.

### None of them does

| candidate | CAGR | max DD | Sharpe | verdict |
|---|---|---|---|---|
| baseline (p60, 1.0×) | 62.7% | −29.5% | **1.39** | — |
| vol-target 60% inside the filter | 45.3% | −24.2% | 1.40 | de-levering with extra steps |
| **SOXS 25% overlay** | 46.4% | −22.9% | 1.39 | ≡ holding 75% SOXL (46.5% / −22.8% / 1.39) |
| UVXY 10% overlay | 57.6% | −28.2% | 1.39 | −5.1pp CAGR buys −1.3pp of drawdown |
| weekend size 0% | 50.0% | **−29.7%** | 1.32 | drawdown *unchanged* |
| 70/30 SOXL+FAS | 47.1% | −28.6% | 1.38 | corr +0.35, tails coincide |
| put overlay (real prints) | see below | | | dead above 0% spread |

**The SOXS result is the clean one.** SOXL 100% + SOXS 25% and "just hold 75%
SOXL" produce 46.4% / −22.9% / 1.39 and 46.5% / −22.8% / 1.39. The mirror hedge
is an exactly redundant, slightly more expensive way to hold less.

**UVXY does work on the tail and still loses.** On SOXL's 10 worst nights UVXY
averaged **+10.95%** against SOXL's −10.82% — a near 1:1 offset. But it decays
−0.280%/night, so you pay for 979 nights to be right on 10.

### The put overlay, priced from real prints rather than modelled

This is where a payoff model misleads. `(entry − exit)/S` from actual
15:55 → 09:30 prints is the **complete** hedge P&L — it already nets the tail
payoffs against the premium. Modelling a payoff on top of a measured net cost
double-counts the benefit, and that error makes the overlay look excellent.
Measured properly, on the same nights:

| 3–7% OTM, 3–7 DTE | CAGR | max DD | Sharpe | effective cost |
|---|---|---|---|---|
| unhedged | 12.1% | −53.5% | 0.53 | — |
| **hedged, 0% spread** | 10.8% | **−41.6%** | **0.59** | 4.5 bp/night |
| hedged, 5% spread | 1.7% | −53.5% | 0.18 | 15.4 bp/night |
| hedged, 10% spread | −6.6% | −65.3% | −0.23 | 26.3 bp/night |

**It works only at a spread of zero.** SOXL weeklies cross at 5–15% of premium.
The hedge is not mispriced — it is correctly priced and you cannot reach it.

### The one thing that is not ruled out

`SOXX` (1× semis) tracks SOXL almost perfectly overnight — **beta 2.964,
correlation 0.9982** over 1,506 shared nights — so 3× SOXX is the same trade.

| | mean/night | compounded |
|---|---|---|
| SOXL | +0.282% | +1,805% |
| 3× SOXX | **+0.318%** | **+3,065%** |

A **3.55 bp/night** gap in SOXX's favour, which is SOXL's embedded expense and
financing. Against it you must set your own margin cost on the 2× borrowed
portion, for the hours actually held — that comparison is not made here and
decides whether the switch pays on its own.

What it does change regardless is **hedgeability**. The put overlay fails on
spread, not on premium, and spread-as-a-fraction-of-premium on SOXX — a
$500, mega-liquid, ~30%-vol ETF — is a fraction of SOXL's weeklies. A hedge
that is 3 points underwater at SOXL's spreads could clear at SOXX's. **Tested and refuted** — see "The SOXX hedge, tested" above: SOXX option spreads are
2.3x SOXL's, because SOXX *options* are thin even though the ETF is not.

### The honest summary

Everything testable here moves along a single risk-return line. The only tool
that reliably reduces drawdown is **size**, and the clever versions of it —
mirror overlays, vol targeting, cross-sector diversification — are size in
disguise, several of them with extra cost attached. The one intervention in
this repo that ever raised Sharpe was the filter itself (0.96 → 1.38), which is
sitting on the sidelines.

## What the filter is actually selecting — SOXS settles it

`mechanism.py`. The FAS failure raised a question it could not answer on its
own: is the SOXL result a volatility mechanism, a leveraged-ETF structural
effect, or directional exposure to semiconductors? **SOXS answers it.** SOXS is
−3× the *same* underlying as SOXL. A structural close-to-open effect must show
the **same** sign on both. Directional exposure must show the **mirror**.

| symbol | overnight | intraday | overnight mean/night | t |
|---|---|---|---|---|
| SOXL (+3× semis) | +2,092% | −71% | **+0.291%** | +2.63 |
| SOXS (−3× semis) | −100% | −100% | **−0.266%** | −2.39 |
| FAS (+3× financials) | +230% | −47% | +0.113% | +1.63 |

Overnight mean per night, by each instrument's own RV20 quintile:

| symbol | Q1 (lowest vol) | Q2 | Q3 | Q4 | Q5 (highest) |
|---|---|---|---|---|---|
| SOXL | **+0.334%** | +0.470% | +0.393% | +0.177% | +0.080% |
| SOXS | **−0.302%** | −0.333% | −0.390% | −0.163% | −0.145% |
| FAS | −0.011% | +0.087% | +0.222% | +0.118% | +0.151% |

**SOXL and SOXS mirror each other in every bucket.** Their overnight means sum
to +0.024%/night — they cancel. A structural effect would have added.

**So the "overnight edge" is not an overnight effect and not a leveraged-ETF
effect. It is long exposure to semiconductors, collected overnight.** And the
vol filter is not selecting calm nights, it is selecting nights when semis went
up: on SOXS the *same* filter concentrates the position into its **worst**
nights (kept −0.362%/night against excluded −0.174%).

### And RV20 is a trend conditioner in disguise

| symbol | corr(RV20, trailing 20d return) | corr(RV20, drawdown from 60d high) |
|---|---|---|
| SOXL | −0.249 | **−0.648** |
| FAS | −0.350 | **−0.741** |

Low RV20 means *near the recent high*. Substituting trend for volatility as the
conditioner, keeping 60% of nights either way:

| conditioner | SOXL total | CAGR | Sharpe | arith/night | FAS total | CAGR | Sharpe |
|---|---|---|---|---|---|---|---|
| no filter | +1,482% | 53.2% | 0.96 | 0.2707% | +137% | 14.0% | 0.52 |
| **LOW RV20** (published) | **+2,248%** | 62.8% | 1.39 | **0.3791%** | **+93%** | 10.5% | 0.60 |
| HIGH trailing 20d return | +1,808% | 57.7% | 1.19 | **0.3777%** | **+201%** | **18.2%** | **0.77** |
| SMALL drawdown from 60d high | +631% | 36.0% | 0.91 | 0.2705% | +88% | 10.1% | 0.55 |

On SOXL the momentum conditioner produces an **almost identical arithmetic mean**
— 0.3777% against 0.3791% — because it is picking essentially the same nights.
RV20's extra total return over momentum is variance reduction, not selection.

And on FAS, where the vol version fails, **the momentum version works** (+201%
against +137%, Sharpe 0.77). The conditioner that ports across both instruments
is trend, not volatility. (In-sample on both, and now the third conditioner
tested on the same data — the multiple-comparison budget is being spent.)

### Restating the SOXL result honestly

Before: *a volatility-conditioned overnight anomaly, Sharpe 1.38, t 3.53.*

After: **a leveraged long position in semiconductors, held only overnight, and
only while the sector is in an uptrend, measured over a period in which the
sector rose 5.4×.**

What survives as general, confirmed on both instruments and on both signs of the
semis trade:

* **The overnight/intraday decomposition is real** on SOXL, SOXS and FAS —
  negative intraday on all three, which is what a ½σ² effect must do.
  **But see "TQQQ and SPXL" above: it does NOT generalise.** Intraday is
  *positive* on SPXL (+54%) and TQQQ (+24%). The drag dominates only where vol
  is high enough.

What does not survive as general:

* ~~**"Low volatility predicts better overnight returns."** It is a trend proxy.~~
  **Superseded** — see "TQQQ and SPXL" above. Trend fails on SPXL and TQQQ
  exactly where the vol cut works, so the two are not the same signal. The
  conditioner survives; it still fails on FAS, and the SOXS mirror still shows
  the *return* is directional beta.
* **Any reading of the p60 threshold as a mechanism.** It is a fitted cut on a
  conditioner that a cruder rule captures nearly as well.

### What this changes in practice

Size it as a **levered sector bet with a trend overlay**, not as a market-neutral
anomaly with Sharpe 1.38. Its risk is the sector's risk; the −29.5% drawdown is
conditional on the sample containing only one trending bear year (2022). The
f = 2.0 work compounds this — 2× on top of 3× is **6× semiconductor exposure**
gated by a trend filter. And the honest benchmark is not buy-and-hold SOXL but
*SOXL with any trend filter*, which the table above shows is a much lower bar to
clear than the README's earlier framing implied.

## FAS — the port, and it does not carry

Run as P0/P1/P2 of `FAS_PORT_PLAN.md`. `SYMBOL=FAS` switches the whole lab;
SOXL remains the default and its outputs are unchanged.

### P1 — the overnight leg exists, and it is a third of SOXL's

`SYMBOL=FAS python3 retreat_lab/overnight.py 1` — 1,680 sessions, 2019-12-31 →
2026-09-08.

| bp/side | FAS total | FAS CAGR | Sharpe | SOXL CAGR |
|---|---|---|---|---|
| 0 | +214% | 18.7% | 0.61 | 61.5% |
| **1** | **+125%** | **12.9%** | **0.50** | 53.6% |
| 2 | +61% | 7.3% | 0.39 | 46.1% |
| 3 | +15% | 2.1% | 0.28 | 39.0% |
| 5 | −41% | −7.7% | 0.05 | 25.7% |

FAS buy-and-hold is 9.9%/yr, so **the unfiltered overnight trade stops beating
buy-and-hold somewhere between 1 and 2 bp per side** and is negative by 5. Max
drawdown −75.3%.

The by-year table is the real finding:

| year | overnight | buy & hold | intraday |
|---|---|---|---|
| 2020 | **+44.3%** | −38.9% | −57.5% |
| 2021 | **+120.7%** | +118.7% | −6.6% |
| 2022 | −21.2% | −44.3% | −32.3% |
| 2023 | **−23.1%** | +11.3% | **+34.2%** |
| 2024 | +64.8% | +84.0% | +8.5% |
| 2025 | **−18.8%** | +10.9% | **+29.3%** |
| 2026 | **−13.8%** | +3.4% | **+18.8%** |

**The FAS overnight premium is 2020–2021 and nothing else. It has been negative
in four of the last five years, and in 2023, 2025 and 2026 the relationship
inverts outright** — overnight negative while intraday is positive. On SOXL the
overnight leg beat the intraday leg in every one of seven years.

### P2 — the RV20 filter fails, and fails in the diagnostic direction

`SYMBOL=FAS python3 retreat_lab/overnight_vol_filter.py 1`:

| filter | nights | total | CAGR | maxDD | Sharpe |
|---|---|---|---|---|---|
| all nights | 1,659 | +137% | 13.8% | −75.3% | 0.52 |
| **below p60** | 995 | **+93%** | **10.4%** | −41.3% | 0.60 |
| below p80 | 1,327 | +139% | 13.9% | −50.4% | 0.61 |
| below p20 | 331 | **−4%** | **−0.6%** | −23.5% | −0.03 |

On SOXL, p60 took +1,586% to +2,248% and cut drawdown from −78% to −29.5%. **On
FAS p60 takes +137% down to +93%.** And the quintile detail inverts the
mechanism: FAS's *lowest*-volatility quintile is its **worst** (−0.6%/yr), the
middle quintile its best (+9.8%/yr). That is the same shape as SOXL's VXX proxy,
which was already on record here as the SOXL result's biggest unexplained
caveat. On FAS the instrument's own RV20 behaves the way SOXL's proxy did.

### The walk-forward: nothing on FAS is significant

`SYMBOL=FAS python3 retreat_lab/walkforward.py 1` — live window 2021-01-29 →
2026-09-04, 1,407 nights.

| strategy | n | total | CAGR | Sharpe | t |
|---|---|---|---|---|---|
| hold every night | 1,407 | +52% | 7.8% | 0.39 | 0.93 |
| walk-fwd expanding p60 | 1,117 | +46% | 7.0% | 0.40 | 0.94 |
| walk-fwd expanding p80 | 1,350 | +30% | 4.9% | 0.31 | 0.73 |
| walk-fwd rolling 504, p60 | 907 | +94% | 12.6% | 0.66 | **1.56** |
| walk-fwd rolling 252, p80 | 1,125 | +80% | 11.0% | 0.53 | 1.25 |

**Every t-stat is below 1.6.** SOXL's walk-forward expanding p60 was t = 2.53.
And the *ordering* inverts: on SOXL expanding worked and rolling failed — the
result the "it is absolute, not relative" conclusion rests on. On FAS rolling-504
is the best cell and expanding-p80 among the worst. A mechanism does not reverse
its own sign across instruments; noise does.

The mechanical reason is in the split: **FAS's threshold does not transfer.**
First-half p60 = 64%, second-half p60 = 42%. SOXL's were 109% and 107%.

### Absolute or relative? The port answers it, and the answer is "neither, on FAS"

`abs_threshold.py` runs both parameterizations on both instruments.

| symbol | p20 | p40 | p50 | p60 | p80 | max | SOXL's p60 ranks at |
|---|---|---|---|---|---|---|---|
| SOXL | 73.1 | 89.7 | 99.5 | **107.5** | 131.3 | 333.3 | 60.0% |
| FAS | 36.6 | 43.8 | 48.6 | 55.5 | 71.3 | 316.5 | **94.2%** |

| FAS rule | n | kept | total | CAGR | maxDD | Sharpe | t |
|---|---|---|---|---|---|---|---|
| hold every night | 1,659 | 100% | +137% | 14.0% | −75.3% | 0.52 | 1.34 |
| ABSOLUTE: RV20 < 107.5% (SOXL's cut) | 1,562 | **94.2%** | +207% | 18.5% | −55.1% | 0.67 | 1.72 |
| RELATIVE: RV20 < own p60 (55.5%) | 995 | 60.0% | +93% | 10.5% | −41.3% | 0.60 | 1.55 |

(On SOXL the two rows are identical by construction — its p60 *is* the absolute
cut.)

**SOXL's absolute threshold sits at FAS's 94th percentile.** Ported unchanged it
keeps 94.2% of FAS nights, so it is not a filter on FAS at all — it is "skip the
6% most violent nights." That version does help: 18.5%/yr against 14.0%, and
drawdown −55.1% against −75.3%. But t = 1.72 is not significant, it is one cut
chosen after seeing the data, and the honest reading is that the absolute
formulation makes **no discriminating prediction** for an instrument whose whole
distribution lies beneath it.

### Verdict on FAS

**No.** The overnight anomaly is present and directionally the same, but it is a
third the size, gone by 2 bp of cost, negative in four of the last five years,
and the one filter that rescued SOXL actively hurts here while its own
walk-forward produces nothing significant. Tiers 2 and 3 of the port plan are not
worth running against this. The port's real value was as an out-of-sample test of
the SOXL conclusion — and it does not confirm it.

## Scoreboard — what actually works on this instrument

`scoreboard.py` re-runs every candidate on identical terms. Same window, same cost,
same metrics. 2019-12-31 → 2026-07-30 (6.6y), 1 bp per side:

| strategy | total | CAGR | max DD | Sharpe | trades | t |
|---|---|---|---|---|---|---|
| overnight, RV20 < p80 | **+2,826%** | 67.1% | −59.2% | 1.25 | 1,306 | 3.21 |
| **overnight, RV20 < p60** | **+2,248%** | **61.6%** | **−29.5%** | **1.38** | 979 | **3.53** |
| overnight only | +1,586% | 53.6% | −78.2% | 0.97 | 1,652 | 2.48 |
| **buy and hold** | **+528%** | 32.2% | −90.5% | 0.83 | 1 | — |
| best intraday bracket (of 1,024) | +34% | 4.6% | −16.2% | 0.80 | 1,653 | 2.05 |
| intraday long | −80% | −21.9% | −92.6% | 0.16 | 1,653 | 0.42 |
| intraday short | −99% | −47.6% | −99.4% | −0.28 | 1,653 | −0.71 |
| 2%/0.5% retreat momentum | −99% | −53.3% | −99.4% | −1.49 | 7,014 | −3.82 |

Cost sensitivity of the only two that beat buy-and-hold:

| bps/side | overnight | overnight RV20<p60 |
|---|---|---|
| 0 | +2,245% | +2,754% |
| 1 | +1,586% | +2,248% |
| 2 | +1,112% | +1,831% |
| **5** | **+350%** | **+975%** |

The filter also makes it *more* cost-robust, because it trades 40% fewer nights.

### One thing works

**Hold SOXL overnight; skip the nights when trailing realised volatility is in its
top quintiles.** It beat buy-and-hold on return, on drawdown and on Sharpe, survived
every robustness test applied (positive in 6 of 7 years, both split halves
significant, still +271% after deleting its 20 best nights), and holds up to 5 bps of
cost.

Its caveats, all recorded above and none of them small: the threshold was fitted on
this data; "low vol" means below **107.6% annualised**, not calm; the **VIX-like
proxy does not confirm it** (lowest VXX bucket is the *worst*); the drawdown is still
−29.5%; and the overnight/intraday split is a **documented market anomaly**, not a
discovery here — which means it is not a fluke of this sample, and also that plenty
of people already know about it.

### Everything else fails for one of two structural reasons

**Intraday: variance drag.** The intraday leg has a *positive* arithmetic mean
(+21.4%/yr) and a negative geometric one (−17.9%/yr). The 39%/yr gap is ½σ² on a
5.58%-a-day series. Exit rules redistribute a distribution; they cannot raise its
mean. That is why 1,024 bracket configurations produced 5 significant results against
26 expected by chance, why tighter stops are only ever *less bad*, and why shorting
is worse still — the short flips the mean negative and keeps the drag.

**Options: the spread exceeds the edge.** Mid-market, the overnight put costs ~6.6 bp
and the short collects ~5.8 bp. Crossing costs 16–33 bp naked and roughly double for
a vertical. Every structure tested — long put, short put, long vertical, short
vertical, collar — is priced through. The naked long put is the only one that does
its job, and only as insurance: its expectancy is negative by construction, but it is
the one thing measured here whose protection *improves* as the night gets worse
(58–86% coverage on a >6% gap, against 12% for the debit spread).

### What the original question was worth

The retreat timing study that started this — how long SOXL holds a 2% upswing before
giving back 0.5% — produced **no tradeable signal**. The trigger is indistinguishable
from noise (t −1.1 to +1.0), the mechanical trade compounds to −99%, and it is worse
than a random entry. What it did surface, incidentally, is the one durable fact in
this repo's version of SOXL: **the return is overnight, the risk is overnight, and
the intraday session is a variance-drag machine.** Everything that works here is a
consequence of that sentence; everything that fails, of ignoring it.

## Read this first: which strategy is which

This README covers two separate questions that are easy to conflate.

1. **The intraday design** — enter by time, exit at +X% or on a floor breach or a
   time stop, whichever is sooner, flat by the bell. **Nothing works.** 1,024
   configurations, 5 with t>2 against ~26 expected by chance, and the best dies at
   2 bps per side. See *What stop width actually works with a +1% target*.
2. **The overnight strategy** — buy at the close, sell at the next open, flat all
   day. This is a *different trade*, and it is the only thing in this lab that beat
   buy-and-hold. **Every mention of "RV20 filter", "p60" or "walk-forward" below
   refers to this one, not to the intraday design.**

They are not variants of each other. The intraday result does not rescue the
overnight one and vice versa.

### And what the RV20 filter actually does

Walk-forward expanding p60, year by year, on the overnight strategy:

| year | all nights | filtered | nights kept | filter helped? |
|---|---|---|---|---|
| 2021 | +94.0% | +29.8% | 178/234 | no |
| 2022 | −69.7% | **−13.6%** | 30/251 | **yes** |
| 2023 | −0.2% | +7.1% | 223/250 | yes |
| 2024 | +207.1% | +121.4% | 185/252 | no |
| 2025 | +54.5% | **+104.2%** | 139/250 | **yes** |
| 2026 | +100.9% | +30.2% | 32/143 | no |

**It helps in three years of six and hurts in three.** It is not picking better
nights. What it does is cut the bad stretch:

| | all nights | filtered | sd/night |
|---|---|---|---|
| first half (2021–23) | **−55%** | **−8%** | 3.57% → 3.04% |
| second half (2024–26) | **+1,149%** | +671% | 4.87% → 3.69% |
| **compounded** | **+460%** | **+607%** | |

The filter loses 478 points in the good half and saves 47 in the bad half — and still
wins overall, because **−8% then +671% compounds to more than −55% then +1,149%.**
Losing less in the drawdown leaves more capital to compound afterwards.

That is a real effect and it is what risk management is for. It is **not** an edge in
night selection, and the distinction matters: in a good regime this filter will
underperform, sometimes badly (2024: +207% → +121%; 2026: +101% → +30%). It earns its
keep by making the bad regimes survivable, not by finding better nights.

## p80 vs p60, and why the early years differ from the late ones

`regime.py`, walk-forward expanding cuts on the overnight strategy:

| year | all | p40 | p60 | p80 | kept p60 | kept p80 |
|---|---|---|---|---|---|---|
| 2021 | +94.0% | −9.0% | +29.8% | +46.6% | 178/234 | 211/234 |
| **2022** | **−69.7%** | −2.4% | **−13.6%** | **−54.0%** | **30/251** | 156/251 |
| 2023 | −0.2% | +8.3% | +7.1% | −0.2% | 223/250 | 250/250 |
| 2024 | +207.1% | +41.6% | +121.4% | +176.8% | 185/252 | 211/252 |
| 2025 | +54.5% | +22.3% | +104.2% | +100.5% | 139/250 | 223/250 |
| 2026 | +100.9% | +5.8% | +30.2% | +39.0% | 32/143 | 78/143 |
| **full** | **+460%** | +76% | **+607%** | +419% | | |
| 2021–23 | −41% | −4% | **+20%** | −33% | | |
| 2024–26 | +853% | +83% | +489% | +672% | | |

**p80 is not the answer.** Over the full window it returns +419% against p60's +607%
and no-filter's +460% — it is slightly *worse than not filtering at all*. The reason
is visible in 2022: p80 kept 156 of 251 nights and returned −54.0%, barely better than
the −69.7% it was meant to avoid, where p60 kept only 30 nights and lost 13.6%. **The
filter's entire value is being tight enough to actually stand aside in the bad year**,
and p80 is not.

### Why the years differ

| year | mean/night | sd/night | win% | worst | median RV20 | drag |
|---|---|---|---|---|---|---|
| 2021 | +0.324% | 2.87% | 58.1% | −9.0% | 76% | 0.041 |
| **2022** | **−0.379%** | 4.39% | 43.8% | −12.2% | **131%** | 0.095 |
| 2023 | +0.045% | 3.05% | 50.8% | −6.8% | 83% | 0.046 |
| 2024 | +0.525% | 3.95% | 57.1% | −19.8% | 90% | 0.078 |
| 2025 | +0.280% | 4.60% | 55.2% | −15.5% | 103% | 0.106 |
| **2026** | **+0.729%** | **6.93%** | 55.9% | −21.6% | 119% | **0.240** |

Two things changed, and neither is subtle.

1. **The overnight drift is not a constant.** It averaged roughly zero across 2021–23
   — including a solidly negative 2022 at −0.379%/night — and strongly positive across
   2024–26 (+0.525%, +0.280%, +0.729%). The "overnight premium" was **absent in 2022**,
   which was a semiconductor bear market. Six years is six annual observations; that is
   a very thin basis for calling it persistent.
2. **Volatility more than doubled.** Nightly sd went 2.87% → 6.93% and the variance
   drag with it, 0.041 → 0.240 per night. The late years are a different instrument,
   statistically, from the early ones.

### The finding that explains the filter

Mean overnight return by RV20 tercile **within each year**, so it is not a level
effect:

| year | low vol | mid | high vol | winner |
|---|---|---|---|---|
| 2021 | 0.080% | 0.106% | **0.788%** | high |
| 2022 | −0.685% | −0.034% | **−0.416%** | high |
| 2023 | **0.072%** | 0.022% | 0.041% | low |
| 2024 | 0.467% | 0.333% | **0.774%** | high |
| 2025 | 0.135% | **0.778%** | −0.069% | low |
| 2026 | **0.800%** | 0.652% | 0.734% | low |

**High vol wins in three years, low vol wins in three.** Within a year, volatility does
not predict the overnight return at all — it is a coin flip.

So the filter is **not selecting better nights**, and never was. What it does is stand
aside when the distribution is wide, which mechanically cuts the ½σ² drag (0.041 in
2021 vs 0.240 in 2026) and the drawdown. **It is a position-sizing rule wearing a
signal's clothing.** That is a legitimate and useful thing to be — but it means the
right way to judge it is on drawdown and survivability, not on return, and it explains
why p60 beats p80: the tighter cut sizes down harder exactly when sizing down matters.

## Position sizing, and a real put overlay

`sizing_and_hedge.py`, on the walk-forward p60 overnight strategy, $100,000 start.

### Sizing is a risk dial, not an optimisation

Fraction *f* of the balance committed each night, remainder in cash:

| f | final equity | CAGR | max DD | ann vol | Sharpe | worst night |
|---|---|---|---|---|---|---|
| 0.25 | $177,466 | 11.0% | **−8.0%** | 10.2% | 1.08 | −$3,878 |
| 0.50 | $297,588 | 22.0% | −15.6% | 20.3% | 1.08 | −$7,755 |
| **1.00** (full) | $706,655 | 42.7% | −32.2% | 40.6% | 1.08 | −$15,510 |
| 2.00 | $2,026,224 | 72.9% | −63.6% | 81.3% | 1.08 | −$31,021 |
| **2.50** | **$2,434,324** | 78.8% | −75.6% | 101.6% | 1.08 | −$38,776 |
| 4.00 | $977,280 | 51.4% | −94.8% | 162.5% | 1.08 | −$62,042 |

**Sharpe is constant at 1.08 across every f** — scaling a return series scales mean and
standard deviation together. So sizing buys nothing in risk-adjusted terms; it only
chooses where on the curve you sit. Terminal wealth peaks near **f = 2.50**, past which
variance drag (which grows with f²) finally overtakes return (which grows with f) —
and the peak is illusory anyway, because f > 1 requires margin whose cost is not
charged here and which would move the peak left.

The practical reading is the opposite of "maximise terminal wealth": **f = 0.50 gives
22.0% CAGR with a −15.6% drawdown**, which is a far more holdable profile than 42.7%
with −32.2% for the same Sharpe. A **fixed $100,000 stake, never compounded, returns
$340,832** — the compounding is doing a large share of the headline.

### The put overlay works mechanically and fails economically

One put per night on the nights the strategy is long, priced from **real paired
15:55 → next-09:30 prints**. Hedged and unhedged compared over exactly the same nights:

| 3–7 DTE (398 nights, 51% coverage) | final | CAGR | max DD | worst night | ann vol |
|---|---|---|---|---|---|
| unhedged | $219,883 | 15.4% | −42.6% | −15.5% | 29.2% |
| **+ long put** | $185,965 | 12.0% | **−33.9%** | **−5.0%** | **19.0%** |

| 15–45 DTE (580 nights, 74% coverage) | final | CAGR | max DD | worst night | ann vol |
|---|---|---|---|---|---|
| unhedged | $242,545 | 17.5% | −51.3% | −15.5% | 36.9% |
| **+ long put** | $222,804 | 15.7% | −41.1% | **−6.3%** | 22.5% |

It does exactly what insurance should: **the worst night goes from −15.5% to −5.0%,
volatility falls by a third, drawdown improves 9 points.** The longer-dated put is the
cheaper hedge per night (−5.5 bp vs −7.6 bp), as expected.

And then the spread kills it:

| round-trip spread | 3–7 DTE final | CAGR | 15–45 DTE final | CAGR |
|---|---|---|---|---|
| 0% (prints) | $185,965 | 12.0% | $222,804 | 15.7% |
| **5%** | **$49,985** | −11.9% | **$3,387** | −46.0% |
| 10% | $13,377 | −30.7% | $50 | −74.9% |

At a realistic 5% round trip the hedged strategy loses money; at 10% it is destroyed.
The longer-dated put is *worse* here despite its lower per-night cost, because its
premium is twice as large so the same percentage spread is twice the dollars. **You
cannot buy this insurance nightly at retail spreads.** Sizing down to f = 0.50 buys the
same drawdown reduction for free, which is the honest substitute.

## p60 at half size, and is this a bull-market strategy?

`regime_switch.py`. SOXX — the **unlevered** semiconductor index ETF — is the regime
yardstick, because it carries no leverage decay so its moving averages mean what they
say.

### p60 at f = 0.50, $100,000 start

Final **$297,588**, +198%, **CAGR 22.0%, max drawdown −14.7%**, 288 weeks, 787 nights
traded. Median week $0 (it stands aside 36% of weeks), mean +$686, best +$20,300,
worst −$29,339.

| year | cash | equity end | running CAGR | worst week |
|---|---|---|---|---|
| 2021 | +15,631 | 115,631 | 17.1% | −4,718 |
| **2022** | **−7,263** | 108,368 | 4.3% | −7,030 |
| 2023 | +6,591 | 114,959 | 4.9% | −6,006 |
| 2024 | +68,000 | 182,959 | 16.6% | −7,784 |
| 2025 | +83,450 | 266,409 | 22.0% | −17,239 |
| 2026 | +31,179 | 297,588 | 21.9% | −29,339 |

Even the bad year costs only −$7,263 at half size, and equity never drops below
$100,000 after the first quarter.

### Yes, it is a bull strategy — at the raw level

The **unfiltered** overnight premium, split by SOXX against its 200-day average:

| regime | nights | mean/night |
|---|---|---|
| SOXX **above** 200d | 934 | **+0.280%** |
| SOXX **below** 200d | 373 | **−0.051%** |

The premium is a bull-regime phenomenon. Below the 200-day average it is *gone* —
slightly negative. That confirms the concern stated earlier in this README.

### But the volatility filter is already the regime switch

Within the p60-filtered nights the split reverses — below-200d nights average +0.796%
against +0.228% above — but **that is not significant (Welch t = 1.27)** and it rests
on 103 nights, of which 2022's 28 were themselves negative (−0.107%); the positive
figure comes from 37 nights in 2023 and 2025. Treat it as noise.

What is not noise is the mechanism: **the p60 filter keeps only 103 of 373 bear
nights — 28%.** Bear markets are high-volatility markets, so a volatility gate
excludes them automatically. The filter is not a separate idea from regime timing; it
*is* regime timing, expressed in the one variable that updates daily rather than
monthly.

### Which is why adding a trend gate makes it worse

| gate | nights | final | CAGR | max DD |
|---|---|---|---|---|
| **none (p60 only)** | 787 | **$297,588** | **22.0%** | −15.6% |
| + SOXX > 200d avg | 659 | $194,546 | 12.9% | −17.3% |
| + SOXX > 50d avg | 589 | $201,941 | 13.6% | −21.9% |
| + within 20% of 1y high | 653 | $266,048 | 19.5% | −15.6% |

Every trend gate *reduces* return and none reduces drawdown. Volatility has already
removed the dangerous bear nights; the trend gate then additionally removes the calm
ones, which were profitable. **Do not stack a bull-market filter on top of the vol
filter — you would be paying twice for the same protection and cutting good nights to
do it.**

### The leveraged-ETF mechanic

A 3× ETF must trade *with* the day's move at the close to hold leverage constant —
buying after up days, selling after down days — so required flow scales with the
day's move. If the overnight premium were that flow, it should depend on the day's own
move:

| that day's intraday move | nights | mean overnight |
|---|---|---|
| **< −3%** | 159 | **+0.038%** |
| −3 to −1% | 132 | +0.394% |
| −1 to +1% | 159 | +0.429% |
| +1 to +3% | 155 | +0.301% |
| > +3% | 182 | +0.373% |

One bucket stands out: **after a >3% down day the overnight premium essentially
disappears** (+0.038% against ~+0.37% everywhere else). That is consistent with
forced deleveraging into the close — the fund sells low, and the bounce does not come
that night. It is a usable rule of thumb (skip the night after a −3% session) but not
a regime indicator; the other four buckets are flat, so there is no monotone
rebalance signature to trade.

## Adding the skip-after-a-3%-down-day rule

`skip_rule.py`. The rule is implementable with no look-ahead — entry is at 15:59 and
the day's open-to-close move is known by then. **But the −3% threshold was found by
inspecting this same data**, so it is treated here as a hypothesis to attack rather
than a result.

### It is not a knife-edge

p60 overnight, f = 0.50, skipping the night after an intraday move below X:

| rule | nights | skipped | final | CAGR | max DD | Sharpe | t |
|---|---|---|---|---|---|---|---|
| p60 only | 787 | 0 | $297,588 | 22.0% | −15.6% | 1.08 | 2.53 |
| skip < −1% | 496 | 291 | $232,802 | 16.6% | −19.5% | 1.05 | 2.46 |
| skip < −2% | 570 | 217 | $268,470 | 19.7% | −19.3% | 1.17 | 2.74 |
| **skip < −3%** | 628 | 159 | $297,324 | 21.9% | **−13.6%** | **1.22** | 2.87 |
| skip < −4% | 675 | 112 | $319,261 | 23.5% | −14.6% | **1.25** | 2.92 |
| skip < −5% | 711 | 76 | $321,620 | 23.7% | −16.5% | 1.22 | 2.86 |
| skip < −7% | 751 | 36 | $309,966 | 22.9% | −15.5% | 1.14 | 2.68 |

Everything from −3% to −7% improves Sharpe (1.14–1.25 against 1.08) with equal or
better return. Only the aggressive cuts (−1%, −2%) hurt, by removing too many ordinary
nights. A rule that works across a broad plateau of thresholds is much less likely to
be an artifact than one that works at exactly one.

### It survives a split

Applying the −3% rule unchanged to each half:

| half | variant | nights | mean/night | total | t |
|---|---|---|---|---|---|
| first | p60 only | 394 | 0.050% | +6% | 0.33 |
| first | **p60 + skip** | 308 | **0.139%** | +20% | 0.81 |
| second | p60 only | 393 | 0.563% | +182% | 3.01 |
| second | **p60 + skip** | 320 | **0.600%** | +149% | 3.07 |

The mean improves in **both** halves — though the first half remains insignificant on
its own (t 0.81), and the gap between halves (0.050% vs 0.563% a night) is the regime
problem restated: there was almost no overnight premium in 2021–23.

The rule removes **159 of 787 nights (20.2%)**, and those nights averaged **+0.038%**
against **+0.374%** for the nights kept.

### The run at f = 0.50

**Final $297,324 · +197% · CAGR 21.9% · max drawdown −11.5%** (weekly marks) over 628
nights.

| year | cash | equity end | running CAGR | worst week |
|---|---|---|---|---|
| 2021 | +14,838 | 114,838 | 16.2% | −3,071 |
| **2022** | **−352** | 114,486 | 7.3% | −6,969 |
| 2023 | +7,109 | 121,595 | 6.9% | −6,160 |
| 2024 | +58,016 | 179,611 | 16.1% | −8,260 |
| 2025 | +88,681 | 268,292 | 22.2% | −12,316 |
| 2026 | +29,032 | 297,324 | 21.9% | −30,166 |

**2022 goes from −$7,263 to −$352** — the bad year becomes a flat year. That is the
rule's real contribution.

Two things to be honest about. **Return is unchanged**: 21.9% against 22.0%. The whole
gain is in drawdown and Sharpe, so this is another risk overlay, not a return
enhancer. And the **−11.5% drawdown is measured on weekly marks**, which smooth over
intra-week troughs; the night-by-night figure in the sensitivity table above is
**−13.6%**, and that is the honest one to plan against.

## The skip rule on p80

`skip_rule.py 1 100000 0.5 80`. Same rule, looser volatility gate.

### It helps p80 — and does not rescue it

| variant | nights | final | CAGR | max DD | Sharpe | t | 2022 cash |
|---|---|---|---|---|---|---|---|
| p60 | 787 | $297,588 | 22.0% | −15.6% | 1.08 | 2.53 | −$7,263 |
| **p60 + skip −3%** | 628 | $297,324 | 21.9% | **−13.6%** | **1.22** | 2.87 | **−$352** |
| p60 + skip −4% | 675 | **$319,261** | **23.5%** | −14.6% | **1.25** | **2.92** | −$4,061 |
| p80 | 1,129 | $275,738 | 20.3% | −43.1% | 0.83 | 1.94 | −$36,384 |
| p80 + skip −3% | 868 | $263,145 | 19.3% | −38.8% | 0.90 | 2.11 | −$31,793 |
| p80 + skip −4% | 937 | $290,643 | 21.4% | −37.0% | 0.94 | 2.21 | −$30,711 |

The skip lifts p80's Sharpe from 0.83 to 0.90 and trims 4 points of drawdown, so it
is a genuine improvement there too. But **p80 + skip is still worse on every measure
than p60 alone**, and in 2022 it loses **−$31,793 against p60 + skip's −$352**. The
looser gate cannot be repaired by the skip rule; a −43% drawdown becomes a −39% one.

Split-sample on p80 shows the same shape as p60 — the skip helps the weak half and
costs nothing much in the strong one:

| half | variant | mean/night | total | t |
|---|---|---|---|---|
| first | p80 only | **−0.051%** | −20% | −0.35 |
| first | p80 + skip | **+0.020%** | −2% | 0.12 |
| second | p80 only | 0.479% | +246% | 2.89 |
| second | p80 + skip | 0.474% | +167% | 2.66 |

### Why the skip adds less to p80 than you would expect

Nights following a −3% day are **343 of 1,380 (24.9%)** in the full live set. How many
each volatility gate has *already* removed before the skip rule is applied:

| gate | nights kept | of which follow a −3% day | skip nights the vol gate already removed |
|---|---|---|---|
| **p60** | 787 | 159 (20.2%) | **184 of 343 — 54%** |
| p80 | 1,129 | 261 (23.1%) | 82 of 343 — 24% |

**p60 has already eliminated more than half the nights the skip rule targets**, because
a −3% session is usually a high-volatility session and the two signals point at the
same days. p80, being looser, lets three-quarters of them through — so the skip rule
has more left to do there, and still cannot close the gap, because the nights p80 lets
through that p60 blocks are bad for reasons the skip rule does not see.

### The practical read

**p60 + skip at −3% or −4% is the best configuration measured in this lab.** −4%
returns more (23.5% CAGR, $319,261) and −3% protects 2022 better (−$352 vs −$4,061);
both beat everything else on Sharpe. The two rules are complementary but heavily
overlapping — the volatility gate does most of the work, and the skip rule is a
second, cheaper pass over what it missed.

Standing caveat, unchanged: both thresholds were chosen by looking at this data, and
2022 is the only adverse regime in the sample.

## Skipping after a big intraday GAIN — and a caveat on the down-skip

`skip_symmetric.py`. The down-day rule came from a coarse five-bucket table. Finer
buckets change the picture, and not in the rule's favour.

### No bucket is significantly different from the rest

| that day's intraday move | nights | mean overnight | sd | t vs all other nights |
|---|---|---|---|---|
| **below −5%** | 76 | **−0.164%** | 4.00% | **−1.09** |
| −5% to −3% | 83 | +0.224% | 3.74% | −0.21 |
| −3% to −1% | 132 | +0.394% | 3.03% | 0.36 |
| −1% to +1% | 159 | +0.429% | 3.74% | 0.47 |
| +1% to +3% | 155 | +0.301% | 2.75% | −0.02 |
| **+3% to +5%** | 96 | **+0.436%** | 3.10% | 0.43 |
| above +5% | 86 | +0.303% | 3.76% | −0.01 |

**The largest |t| in the table is 1.09.** Nothing here is statistically distinguishable
from anything else.

It also relocates the effect. The coarse table's "below −3% is bad (+0.038%)" is really
**"below −5% is bad (−0.164%)"** diluted with a perfectly ordinary −5%-to−3% band at
+0.224%. The −3% threshold was never where the signal lived.

### Skipping after gains does not work

| rule | nights | final | CAGR | max DD | Sharpe | ΔSharpe |
|---|---|---|---|---|---|---|
| p60 only | 787 | $297,588 | 22.0% | −15.6% | 1.08 | |
| skip after > +2% | 534 | $219,244 | 15.4% | −12.8% | 0.93 | **−0.15** |
| skip after > +3% | 605 | $217,634 | 15.2% | −18.7% | 0.88 | **−0.19** |
| skip after > +4% | 657 | $218,926 | 15.3% | −26.3% | 0.86 | **−0.22** |
| skip after > +5% | 701 | $265,160 | 19.4% | −24.5% | 1.03 | −0.05 |
| skip after > +7% | 751 | $335,880 | 24.7% | −19.1% | 1.22 | +0.15 |

Every threshold from +2% to +5% **hurts**, which is what the bucket table predicts —
the +3% to +5% band has the *highest* mean of any bucket (+0.436%), so skipping it
throws away good nights. Only +7% appears to help, and it removes **36 nights of 787
(4.6%)**; a Sharpe improvement resting on 36 observations is not a finding. Its split
is 0.050%→0.071% (t 0.46) and 0.563%→0.627% (t 3.33) — marginal in both halves.

Skipping both tails adds nothing over the down side alone: |move| > 4%/5% gives Sharpe
1.22, the same as skip < −3% by itself.

### What this does to the down-skip rule

Both of these remain true and they sit in tension:

* The rule **did** improve out-of-sample metrics — Sharpe 1.08 → 1.22, drawdown −15.6%
  → −13.6%, better mean in both split halves, across a −3% to −7% plateau.
* The **mechanism it was attributed to is not established.** No single bucket is
  significant, the effect is at −5% rather than −3%, and a plateau of thresholds over
  one sample can be produced by the same noise that produced the buckets.

The previous section presented the plateau as evidence against artifact. That was too
strong: a plateau rules out a *knife-edge* fit, not a shared-noise fit, because
adjacent thresholds are testing overlapping night sets and are not independent
evidence.

### The multiple-comparison bill

Thresholds tested in this script: **11**. Across this lab on the same 5.5 years: **well
over 100** — 6 retreat pairs, 4 percentiles, 3 windows, 6 down-skips, 5 up-skips, 5
both-tail combinations, 1,024 bracket configurations, 200 take-profit configurations.

At that width roughly one test in twenty clears t = 2 by chance. **A new rule now needs
to clear it in both halves and by a wide margin to carry any weight**, and the up-side
skip does not come close.

## Full backtest at f = 1.00: p60 + skip −3% and −4%

`skip_rule.py 1 100000 1.0 60 -0.03` and `... -0.04`. Walk-forward p60 threshold,
1 bp per side, $100,000, full reinvestment, 2021-01-29 → 2026-07-29.

| variant | nights | final | CAGR | max DD | Sharpe | t |
|---|---|---|---|---|---|---|
| buy and hold | — | $344,521 | 25.2% | | | |
| p60 only | 787 | $706,655 | 42.7% | −32.2% | 1.08 | 2.53 |
| **p60 + skip −3%** | 628 | $748,636 | 44.2% | **−27.6%** | 1.22 | 2.87 |
| **p60 + skip −4%** | 675 | **$849,145** | **47.6%** | −28.6% | **1.25** | 2.92 |
| p60 + skip −5% | 711 | $851,527 | 47.7% | −32.6% | 1.22 | 2.86 |

Drawdowns are night-by-night. At full size both skip variants beat p60 alone on return
*and* drawdown, which they did not do at f = 0.50 (there the return was flat and only
the risk improved).

### p60 + skip −3%, f = 1.00

Final **$748,636**, +649%, **CAGR 44.2%**, 628 nights. Drawdown **−22.2% on weekly
marks, −27.6% night by night**. Weekly cash: median $0, mean +$2,252, best +$65,556,
worst **−$151,609**, 35.1% of weeks positive.

| year | cash | equity end | running CAGR | worst week |
|---|---|---|---|---|
| 2021 | +29,502 | 129,502 | 32.5% | −6,397 |
| **2022** | **−2,546** | 126,956 | 13.3% | −15,381 |
| 2023 | +10,561 | 137,517 | 11.6% | −13,634 |
| 2024 | +150,714 | 288,230 | 30.9% | −27,229 |
| 2025 | +332,208 | 620,438 | 44.9% | −59,158 |
| 2026 | +128,198 | 748,636 | 44.2% | **−151,609** |

### p60 + skip −4%, f = 1.00

Final **$849,145**, +749%, **CAGR 47.6%**, 675 nights. Drawdown **−23.1% weekly,
−28.6% night by night**. Weekly cash: median $0, mean +$2,601, best +$106,503, worst
**−$162,504**, 36.1% positive.

| year | cash | equity end | running CAGR | worst week |
|---|---|---|---|---|
| 2021 | +40,511 | 140,511 | 44.7% | −9,539 |
| **2022** | **−11,415** | 129,096 | 14.2% | −16,688 |
| 2023 | +12,184 | 141,280 | 12.6% | −13,864 |
| 2024 | +155,079 | 296,359 | 31.9% | −28,711 |
| 2025 | +368,666 | 665,025 | 46.9% | −63,409 |
| 2026 | +184,120 | 849,145 | 47.5% | **−162,504** |

**−3% protects 2022 better** (−$2,546 vs −$11,415); **−4% makes more everywhere else**
($849,145 vs $748,636). Neither year-1 equity ever falls below the starting capital.

The cost of full size versus half: **worst week goes from −$30,166 to −$151,609**, and
the −$151,609 week is 2026, when the account was large. As a share of equity the worst
weeks are −19.5% at f = 0.5 and roughly −20% at f = 1.0 — the dollar figure grows with
the account, the percentage does not.

## Leverage: f = 1.5 and f = 2.0 with the −4% skip

p60 + skip −4%, 675 nights, $100,000, 1 bp per side. **f is a multiple of equity
committed to a 3× ETF**, so f = 1.5 is ~4.5× exposure to the semis index and f = 2.0
is ~6×.

| f | final | CAGR | max DD | worst night | effective exposure |
|---|---|---|---|---|---|
| 0.5 | $319,261 | 23.5% | −14.6% | −6.0% | 1.5× |
| 1.0 | $849,145 | 47.6% | −28.6% | −12.1% | 3.0× |
| **1.5** | **$1,885,879** | **70.7%** | −42.5% | −18.1% | 4.5× |
| **2.0** | **$3,500,406** | **91.0%** | −55.2% | −24.1% | 6.0× |
| 2.5 | $5,427,016 | 106.9% | −66.3% | −30.1% | 7.5× |

### Charging margin — a change from the earlier runs

f > 1 borrows, and none of the earlier tables charged for it. At **6%/yr on the
borrowed portion, accrued per night held**:

| f | final | CAGR | max DD | drag vs no charge |
|---|---|---|---|---|
| 1.0 | $849,145 | 47.6% | −28.6% | — |
| **1.5** | **$1,784,409** | **68.9%** | −43.0% | **−5.4%** |
| **2.0** | **$3,133,839** | **87.2%** | −56.0% | **−10.5%** |
| 2.5 | $4,596,796 | 100.7% | −67.1% | −15.3% |

Material but not decisive — the position is only held overnight, so borrow accrues on
roughly 675 nights rather than continuously.

### Year by year, with the margin charge

| year | f = 1.0 | f = 1.5 | f = 2.0 |
|---|---|---|---|
| 2021 | 140,511 | 159,405 | 177,065 |
| 2022 | 129,096 | 136,877 | 139,952 |
| 2023 | 141,280 | 144,858 | 137,415 |
| 2024 | 272,487 | 358,897 | 418,772 |
| 2025 | 624,586 | 1,161,598 | 1,841,884 |
| 2026 | **849,145** | **1,784,409** | **3,133,839** |

2022 is still profitable at every leverage — the filters carry it.

### What it costs: the worst weeks

| f | worst week | second | third |
|---|---|---|---|
| 1.5 | 2026-03-02 **−28.5%** (−$503,029) | 2022-08-01 −17.5% | 2024-10-28 −16.1% |
| 2.0 | 2026-03-02 **−37.0%** (−$1,169,322) | 2022-08-01 −22.9% | 2024-10-28 −21.3% |

### The tail risk that does not show in these numbers

The filters caught the four worst nights in the live window. That is an outcome, not a
property — **a volatility filter cannot forecast a gap.**

| night | raw | passed p60? | passed skip −4%? | at f = 1.5 | at f = 2.0 |
|---|---|---|---|---|---|
| 2026-06-22 | −21.6% | **no** | — | −32.4% | **−43.2%** |
| 2024-08-02 | −19.8% | **no** | — | −29.7% | −39.6% |
| 2025-01-24 | −15.5% | yes | **no** | −23.3% | −31.0% |
| 2026-07-06 | −15.1% | **no** | — | −22.6% | −30.2% |

Worst night that *did* pass both filters: **−12.1%** → −18.1% at f = 1.5, −24.1% at
f = 2.0. Worst night in the window: −21.6%, which at f = 2.0 would have taken **43% of
the account in one night.** Nothing in the method guarantees the next such gap lands on
a night the filter excludes.

### One practical constraint worth checking before acting

Reg T permits 2:1 initial margin on marginable equities, but **house requirements on
3× leveraged ETFs are commonly 75–100%**, which would make f = 2.0 unavailable and
f = 1.5 marginal at many brokers. These figures assume the leverage is obtainable at
6%; confirm both before treating the f > 1 rows as reachable.

## Forced liquidation at f = 2.5 under a 3:1 portfolio-margin cap

**Scope of what follows.** The thresholds are exact arithmetic from the stated 3:1
maximum — verifiable, no IBKR knowledge involved. Anything about how IBKR actually
computes portfolio margin on a 3× ETF, or when in the session it liquidates, is
**inferred and unverified here**: IBKR's own documentation is egress-blocked from this
environment, and this repo's IBKR notes cover order semantics, not margin.

### The threshold is exact

After an overnight move *r*, leverage becomes `L' = f(1+r) / (1 + f·r)`. A breach of
`L' > 3` happens when `r < (f − 3) / 2f`:

| f | gross exposure | liquidates at | nights breaching (675 in set) | worst kept night |
|---|---|---|---|---|
| 1.0 | 3.0× | −100% | 0 | −12.1% |
| 1.5 | 4.5× | −50.0% | 0 | −12.1% |
| **2.0** | **6.0×** | **−25.0%** | **0** | −12.1% |
| **2.5** | **7.5×** | **−10.0%** | **3** | −12.1% |

**f = 2.0 has a −25% buffer and never breaches** — not in the 675 filtered nights, and
not in all 1,380 unfiltered live nights either (worst was −21.6%).

**f = 2.5 liquidates on a −10% night, and three occurred:** 2026-03-02 (−12.1%),
2024-07-16 (−10.3%), 2025-03-05 (−10.3%). Unfiltered, 24 of 1,380 nights would have
breached.

### Why liquidation costs this strategy less than it would most

**The position is flat during the day.** It is entered at 15:59 and exited at the 09:30
open, so a forced liquidation at the open coincides with the exit the strategy was
making anyway. That is a genuinely unusual property — the exposure window is one
overnight per trade, and the liquidation trigger and the planned exit are the same
moment.

Modelling the liquidation as a fill worse than the 09:30 print:

| liquidation slippage | final | CAGR | max DD | liquidations |
|---|---|---|---|---|
| none (fills at the open) | $4,596,796 | 100.7% | −67.1% | 3 |
| 1% worse | $4,138,783 | 96.9% | −67.1% | 3 |
| 3% worse | $3,316,041 | 89.1% | −67.1% | 3 |
| 5% worse | $2,610,214 | 81.1% | −67.1% | 3 |
| 10% worse | $1,298,381 | 59.5% | −67.1% | 3 |

f = 2.0 for comparison: **$3,133,839, CAGR 87.2%, −56.0% drawdown, zero liquidations.**

**At roughly 4% liquidation slippage, f = 2.5 stops beating f = 2.0** — and f = 2.0
carries a −25% buffer instead of −10%, so it is not paying for the extra return with
the same risk.

### The three things this analysis cannot settle

1. **Pre-market fills.** `SOXL_1min.csv` is regular-hours only. SOXL trades from 04:00
   ET, and a liquidation would most likely be filled there, below the 09:30 print this
   backtest uses for every exit. **The single most important number for the f = 2.5
   question — how far below the open a forced fill lands — is not measurable from this
   data.**
2. **Whether IBKR's PM requirement on a 3× ETF is really 3:1.** Portfolio margin is
   risk-based (a stress scenario), not a fixed ratio, and leveraged ETFs commonly carry
   a house add-on. If the effective cap is nearer 2.5:1, the f = 2.5 threshold moves
   from −10% to about −3.3% and breaches become frequent rather than rare.
3. **Over-liquidation and account consequences.** Whether IBKR closes only what the
   deficit requires, and what three liquidations in five years does to account
   standing, are not knowable from here.

### What the arithmetic does support

**f = 2.0 is the highest leverage this sample never puts in liquidation range**, with a
−25% buffer against a worst observed night of −21.6% unfiltered and −12.1% filtered.
f = 2.5 returns more on paper but its entire margin of safety is 2.1 percentage points
of gap, and it is one unmeasured pre-market print away from being materially worse.

## f = 2.0 with a weekly cash sweep — 75% reinvested, 25% to interest

`sweep.py`. Rules, each a stated choice: the sweep fires only on **profitable** weeks;
it is **one-way** (the reserve never funds losses back); position size is 2.0× the
**trading** account, so sweeping shrinks the position; margin 6%/yr on the borrowed
portion; the reserve earns an approximate short-T-bill schedule (0.05% in 2021 rising
to 5% in 2023–24, 4% by 2026) rather than one flat number.

### As specified: 25% of every profitable week

| | trading | reserve | total | CAGR | max DD |
|---|---|---|---|---|---|
| no sweep | $3,133,839 | $0 | $3,133,839 | 87.2% | −46.0% |
| **sweep 25% weekly** | **$278,490** | **$340,644** | **$619,134** | **39.3%** | **−31.2%** |
| sweep 10% weekly | $1,201,955 | $355,129 | $1,557,084 | 64.8% | −39.5% |
| sweep 50% weekly | $22,690 | $214,285 | $236,975 | 17.0% | −20.4% |

103 of 288 weeks swept, median $2,269, largest $20,516, **$314,457 banked in total**.
Rate sensitivity is small: at a flat 0% the total is $592,946, at 5% it is $625,049.

| year | trading P&L | swept | trading equity | reserve | total |
|---|---|---|---|---|---|
| 2021 | +63,874 | 39,436 | 124,438 | 39,442 | 163,881 |
| **2022** | **−25,166** | **11,183** | 88,089 | 51,488 | 139,576 |
| **2023** | **−2,784** | **30,913** | **54,391** | 85,787 | 140,178 |
| 2024 | +103,790 | 57,200 | 100,981 | 148,957 | 249,938 |
| 2025 | +245,948 | 119,233 | 227,696 | 276,796 | 504,492 |
| 2026 | +107,285 | 56,491 | 278,490 | 340,644 | 619,134 |

### The problem the by-year table exposes

**2023: gross P&L −$2,784, yet $30,913 swept out.** The trading account fell from
$88,089 to $54,391 in a flat year. 2022 does the same on a smaller scale.

A one-way sweep on every up week is a **ratchet**: profitable weeks are taxed, losing
weeks are not refunded, so in choppy periods the account is drained by its own
volatility. With 35% winning weeks the up-weeks alone were large enough to fund
$42,096 of sweeps across two years in which the strategy made nothing. That is why
total falls from $3.13M to $619k — far more than the $314k actually swept, because the
money leaves before it can compound at 2× leverage.

### The repair — sweep above a high-water mark

| rule | trading | reserve | total | CAGR | max DD |
|---|---|---|---|---|---|
| no sweep | $3,133,839 | $0 | $3,133,839 | 87.2% | −46.0% |
| 25% of every up week | $278,490 | $340,644 | $619,134 | 39.3% | −31.2% |
| **25% above the high-water mark** | **$1,377,385** | **$453,407** | **$1,830,792** | **69.7%** | −40.9% |
| 25% of the year's net profit | $1,851,269 | $399,370 | $2,250,639 | 76.2% | −40.7% |

Swept by year, weekly rule vs high-water mark:

| year | weekly swept | HWM swept |
|---|---|---|
| 2022 | $11,183 | **$0** |
| 2023 | $30,913 | **$0** |

The high-water-mark rule banks **more** in the reserve ($453,407 against $340,644)
while leaving five times as much in the trading account, because it only takes money
when the account is genuinely at a new peak. The annual rule banks slightly less and
keeps more still.

### What sweeping actually buys

Less than it looks. Drawdown falls from −46.0% to −40.9% under the high-water rule and
to −31.2% under the aggressive weekly one — but that is measured on the **total**, and
the reserve only cushions once it has grown, so early drawdowns are barely affected.
What the sweep genuinely provides is **withdrawn, non-recallable capital**: $453,407
sitting outside the leveraged account and immune to a gap. Judge it as taking money off
the table, not as risk control inside the strategy.

## Programming the high-water mark

`hwm.py`. The mark is the **highest trading-account equity ever recorded at a weekly
mark**. Each week: trade, then sweep `pct × max(0, equity − hwm)`, then set
`hwm = max(hwm, equity after the sweep)`. Three lines, no history, no lookback window
— one number carried forward.

Note the mark is set **after** the sweep, so it ratchets by the retained 75% only. If
it were set before, the swept dollars would be permanently exempt and the next new high
would sweep nothing.

### Which balance carries the mark

| rule | trading | reserve | total | CAGR | max DD | weeks swept |
|---|---|---|---|---|---|---|
| none (all reinvested) | $3,133,839 | $0 | $3,133,839 | 87.2% | −46.0% | 0/288 |
| every profitable week | $278,490 | $340,644 | $619,134 | 39.3% | −31.2% | 103/288 |
| **HWM on trading equity** | **$1,377,385** | **$453,407** | **$1,830,792** | **69.7%** | −40.9% | **41/288** |
| HWM on trading + reserve | $1,366,495 | $455,170 | $1,821,664 | 69.6% | −40.9% | 53/288 |

The two are nearly identical here, but they are not the same rule and the difference
grows with the reserve: marking the **total** means the reserve's own interest lifts
the bar, so eventually the strategy must out-earn its own T-bill balance to sweep at
all. Mark the **trading** account.

### The 2022 window, week by week

| week | after trading | HWM | above? | swept | HWM after |
|---|---|---|---|---|---|
| 2022-07-25 | 152,523 | 154,008 | −1,486 | **0** | 154,008 |
| 2022-08-01 | 117,607 | 154,008 | −36,401 | **0** | 154,008 |
| 2022-09-26 | 102,808 | 154,008 | −51,200 | **0** | 154,008 |
| 2022-10-03 | 121,173 | 154,008 | −32,835 | **0** | 154,008 |

2022-09-26 and 2022-10-03 are **profitable** weeks — +$1,038 and +$18,365. The weekly
rule banks 25% of each; the high-water rule banks nothing, because the account is still
$33k below a peak set in July. That is the entire difference between the two rules.

### The operational consequence nobody plans for

**41 of 288 weeks swept. The longest stretch with no sweep at all was 109 weeks —
2021-12-20 through 2024-01-15, just over two years.** A high-water rule is not an
income schedule. If the reserve is meant to pay for anything on a calendar, this rule
will not fund it.

### Minimum transfer size

| floor | weeks swept | banked | total equity |
|---|---|---|---|
| $0 | 41 | $429,890 | $1,830,792 |
| $250 | 39 | $430,062 | $1,831,693 |
| $1,000 | 35 | $434,897 | $1,859,881 |
| $5,000 | 20 | $483,447 | $2,193,965 |

Skipping dust transfers costs nothing and ends up banking *more*, because the skipped
dollars stay at 2× and are swept later at a higher level. Median sweep is $3,427,
largest $69,115.

### Reconciling banked against reserve

Total swept is **$429,890**; the reserve ends at **$453,407**. The $23,517 gap is
interest accrued on the reserve, not a discrepancy — the sweep column sums principal,
the reserve column includes its own carry.

## Walk-forward: does the RV20 filter survive an honest threshold?

The filter as reported used a percentile of the **whole sample** — at any night it
implicitly knew where that night's volatility would rank against volatility that had
not happened yet. RV20 was always trailing; the cut was not. `walkforward.py` rebuilds
it with no forward information: `threshold(i)` = the p-th percentile of RV20 over a
window strictly **before** i, with a 252-session burn-in.

Everything below is over the same post-burn-in window (2021-01-29 → 2026-07-29, 5.5y,
1,380 nights) — which **excludes 2020**, one of the strategy's two best years, so every
figure is lower than the headline numbers elsewhere in this README.

| strategy | n | total | CAGR | max DD | Sharpe | t |
|---|---|---|---|---|---|---|
| hold every night (no filter) | 1,380 | +460% | 36.8% | −78.2% | 0.80 | 1.88 |
| *in-sample cut at p60* | 811 | *+811%* | *49.5%* | *−29.5%* | *1.19* | *2.78* |
| **walk-forward expanding, p60** | 787 | **+607%** | **42.7%** | **−32.2%** | **1.08** | **2.53** |
| walk-forward expanding, p80 | 1,129 | +419% | 34.9% | −69.3% | 0.83 | 1.94 |
| walk-forward rolling 252, p60 | 775 | +121% | 15.6% | −61.2% | 0.55 | 1.30 |
| walk-forward rolling 504, p60 | 743 | +238% | 24.8% | −49.6% | 0.77 | 1.81 |

**It survives, and it costs something.** Expanding-window p60 keeps a real edge over
no filter (Sharpe 1.08 vs 0.80, drawdown −32% vs −78%) but gives back about a quarter
of the in-sample return, +811% → +607%.

**The window choice is itself a fitted decision, and it matters more than the
percentile.** Expanding works; rolling 252 and 504 do not, and rolling-252 p60 is
*worse* than no filter at all. A rolling threshold adapts to the recent regime, so in
a high-vol period it raises the bar and lets high-vol nights through. That the
absolute-memory version works and the relative one does not is consistent with the
earlier VXX result, where a relative-to-recent conditioner also failed. **The effect
appears to be about absolute volatility levels, not relative ones.**

### The clean single split

Fit the threshold on the first half of the live window, apply it to the second, no
other contact:

| second half | n | total | CAGR | max DD | Sharpe | t |
|---|---|---|---|---|---|---|
| hold every night | 690 | **+1,149%** | 149.9% | −61.6% | 1.58 | 2.62 |
| cut fitted on 1st half, p60 | 434 | +733% | 115.7% | **−30.3%** | **1.87** | 3.11 |
| cut fitted on 1st half, p80 | 579 | **+1,133%** | 148.7% | −45.1% | 1.85 | 3.08 |

Thresholds transfer well — first-half p60 = 109% annualised, second-half p60 = 107% —
so the volatility distribution is stable enough for a fitted cut to carry forward.

### The correction this forces

The scoreboard section says the filter "beat buy-and-hold on return, on drawdown and
on Sharpe." **Out of sample that is only two-thirds true.** What survives honest
construction is the **risk** improvement: Sharpe 1.58 → 1.87 and drawdown −61.6% →
−30.3% at p60; at p80, essentially identical return (+1,133% vs +1,149%) with Sharpe
1.85 and a −45.1% drawdown instead of −61.6%.

What does not reliably survive is the **return** improvement. In-sample the filter
appeared to add return and cut risk; walk-forward it mostly cuts risk, and at p60 it
cuts return too. The right description is **a volatility-based risk overlay on the
overnight position, not a return enhancer** — worth having if the −78% drawdown of the
unfiltered version is what stops you holding it, which is a real reason, but not the
free lunch the in-sample numbers implied.

## The event

1. **Anchor** — the running trough while no episode is open.
2. **Trigger** — first bar ≥ `anchor × (1 + up)`. This is the *upswing*.
3. **Peak** — running maximum from the trigger bar onward.
4. **Retreat** — first bar ≤ `peak × (1 − down)`. This is the *retreat*.
   *Leg A* = trigger → peak, *Leg B* = peak → retreat. If the trigger bar is itself
   the peak, Leg A = 0 and the whole wait is Leg B.
5. **Reset** — anchor restarts at the retreat bar; hunt for the next upswing.

Time is reported two ways because the file is regular-hours only: **market minutes**
(tradeable bars elapsed) and **wall-clock minutes** (calendar time, including closed
hours). For an intraday episode they are identical; they diverge only across a close.

### Scope: any minute, not the day's open — and one episode at a time

**The series is one continuous stream, never reset at the open.** The anchor is the
running trough carried forward across days; the calendar is used only to *label*
whether an episode spanned a close. So a trigger can fire on any of the 390 minutes of
a session, measured against a low that may sit hours or days earlier:

| | 2%/0.5% | 5%/2% |
|---|---|---|
| anchor on a *different day* from the trigger | 10.3% | 36.4% |
| anchor age: same day / 1–3 days / 4–7 days | 6,290 / 704 / 20 | 965 / 524 / 29 |
| oldest anchor | 4 calendar days | 6 calendar days |
| anchor is a 09:30 bar (uniform would be 0.3%) | 2.0% | 3.6% |

Anchors and triggers spread across every hour of the session; the mild clustering at
09:30 is just the open often being the day's extreme, not a rule.

**Episodes are sequential and non-overlapping.** The engine holds one anchor and is
either *seeking* (hunting the next upswing) or *armed* (inside an episode, watching for
the retreat). While armed it does not start a new episode, and after a retreat the
anchor restarts at the retreat bar. So the episode count is **"how many fit end to
end", not "how many upswings occurred"** — and the wider the pair, the more of the tape
is locked inside an open episode:

| | 1%/0.25% | 2%/0.5% | 3%/1% | 4%/1.5% | 5%/2% |
|---|---|---|---|---|---|
| bars inside an open episode | 15.7% | 12.2% | 16.9% | 19.8% | **22.5%** |

`independence_check.py` tests whether those two rules drive the answer, by re-measuring
with an anchor that has no episode memory (trailing minimum over a fixed lookback) and,
separately, with overlaps allowed:

| pair | primary (event anchor, no overlap) | V2 (rolling anchor, no overlap) | V1 (rolling anchor, **overlap allowed**) |
|---|---|---|---|
| 5%/2% | n 1,518 · med **41** | n 1,789 · med **48** | n 5,054 · med **76** |
| 4%/1.5% | 2,197 · **26** | 2,517 · **29** | 5,924 · **44** |
| 3%/1% | 3,575 · **13** | 3,635 · **16** | 6,902 · **22** |
| 2%/0.5% | 7,014 · **6** | 5,554 · **7** | 7,795 · **8** |
| 1%/0.25% | 18,166 · **4** | 7,128 · **4** | 8,167 · **4** |

**The anchor rule is not what produces the answer** (primary vs V2 moves the median by
one to seven minutes, and V2 lands within a couple of minutes of primary at every
lookback tried — 78, 390 and 1,950 bars).

**The overlap rule looks like it matters, but the difference is double-counting.**
When overlaps are allowed, one rally spawns many triggers that all terminate at the
*same* retreat bar. At 5%/2%, **60% of V1's episodes are re-counts of a terminal event
already counted** — a single retreat at 2022-12-27 09:30 ends 23 of them, with start
points spread over the previous session and durations from 6 to 305 minutes for what is
one event. The inflation's size also swings with the arbitrary lookback (median 16 / 22
/ 17 at L = 78 / 390 / 1,950), which is what an artifact looks like.

So the non-overlapping count is the right one for *"if I traded this rule, re-arming
after each exit, how long would each round trip last?"* — the question these numbers
answer. It is **not** the answer to *"SOXL is 5% off its low right now, how long have
I got?"*, which conditions on a moment rather than on a completed prior episode; V1's
column is the loose upper bound for that reading, inflated by the re-counting above.

### Start time matters a great deal

The engine treats every minute identically, but the *outcome* depends strongly on when
the episode starts — median market minutes to the retreat, by trigger clock time:

| trigger window | 1%/0.25% | 2%/0.5% | 3%/1% | 4%/1.5% | 5%/2% |
|---|---|---|---|---|---|
| 09:30–10:00 | 3 | 4 | 8 | 16 | **29** |
| 11:00–12:00 | 4 | 8 | 19 | 43 | **76** |
| 13:00–14:00 | 5 | 10 | 29 | 55 | **76** |
| 15:00–15:30 | 4 | 8 | 17 | 37 | **41** |
| 15:30–16:00 | 3 | 5 | 9 | 12 | **16** |

At 5%/2% a midday trigger runs a median 76 minutes and a 9:30 trigger 29 — the opening
half hour is the fastest tape, so upswings there are given back quickest. The late
buckets are **truncated, not fast**: a 15:45 trigger has 15 minutes of session left, so
it either resolves inside them or spans a close, which is exactly the 15:30–16:00 row
of the spanning table above. Read those two rows together, never separately.

## Answer — all five thresholds

| | **5% / 2%** | **4% / 1.5%** | **3% / 1%** | **2% / 0.5%** | **1% / 0.25%** |
|---|---|---|---|---|---|
| up : down ratio | 2.5 : 1 | 2.67 : 1 | 3 : 1 | 4 : 1 | 4 : 1 |
| episodes | 1,518 (0.9/session) | 2,197 (1.3) | 3,575 (2.2) | 7,014 (4.2) | 18,166 (11.0) |
| Leg A · trigger → peak | median **17 min** | **11** | **6** | **3** | **1** |
| Leg B · peak → retreat | median **15 min** | **9** | **5** | **3** | **2** |
| **Total · trigger → retreat** | median **41 min** | **26** | **13** | **6** | **4** |
| mean / p90 / p99 | 95.3 / 276 / 608 | 57.9 / 158 / 386 | 30.4 / 75 / 253 | 11.1 / 26 / 73 | 5.6 / 12 / 32 |
| resolved ≤ 15 min | 25.6% | 36.4% | 54.2% | 79.4% | 94.0% |
| resolved ≤ 30 min | 42.2% | 54.3% | 71.9% | 92.7% | 98.9% |
| resolved ≤ 60 min | 59.7% | 72.5% | 86.7% | 98.2% | 99.9% |
| **survived a full session** | **74 (4.9%)** | 20 (0.9%) | 4 (0.1%) | 0 | 0 |
| **survived two sessions** | **7** | 2 | 0 | 0 | 0 |
| longest | **1,101 min (2.8 sessions)** | 908 (2.3) | 675 (1.7) | 191 (0.5) | 122 (0.3) |
| peak *is* the trigger bar | 13.1% | 14.8% | 19.3% | 26.6% | 34.6% |
| run-up past the line | med 1.54%, p90 6.49% | 1.22%, 4.91% | 0.73%, 3.43% | 0.40%, 1.90% | 0.22%, 1.32% |
| full upswing anchor → peak | med 7.33%, p90 13.23% | 5.76%, 10.53% | 4.22%, 7.75% | 2.70%, 4.79% | 1.45%, 2.81% |
| **spans a close** | **345 (22.7%)** | **309 (14.1%)** | **291 (8.1%)** | **236 (3.4%)** | **332 (1.8%)** |
| — overnight / weekend / holiday | 269 / 72 / 4 | 246 / 60 / 3 | 234 / 54 / 3 | 189 / 45 / 2 | 267 / 60 / 5 |
| — crossed ≥2 closes | **24** (one crossed 3) | 4 | 1 | 0 | 0 |
| — of spanning, triggered 15:30–16:00 | **22%** | 34% | 57% | 83% | 96% |
| retreat itself crossed the gap | 163 (10.7%) | 134 (6.1%) | 139 (3.9%) | 129 (1.8%) | 169 (0.9%) |
| — of those, **survived the open** | **33%** | 19% | 12% | 5% | 3% |
| give-back when the gap did complete it | med **3.96%** | 3.59% | 3.05% | 2.74% | 2.47% |
| weekend episodes per year | 10.9 | 9.1 | 8.2 | 6.8 | 9.1 |

All durations in market minutes; max give-back is 31.5% at every threshold (the same
event, 2020-03-13 → 03-16). The ratios differ across configs — 4:1, 4:1, 3:1, 2.67:1,
2.5:1 — so this is not a clean scaling of one shape: as the upswing grows the retreat
is proportionally deeper too.

## Every column is monotone, and the crossover sits between 2% and 3%

**At 1% and 2% this is an intraday noise event.** Median 4–6 minutes, 93–99% resolved
inside half an hour, nothing ever survived a session, nothing ever crossed more than
one close. The handful that spanned a close did so almost entirely because the bell
arrived first — 83–96% of them were triggered in the final 30 minutes.

**At 3% and above it is a multi-session position, and by 5%/2% that is the norm.**
Only 25.6% of 5%/2% episodes resolve within 15 minutes and **40.3% are still open
after a full hour**; 74 survived a whole session, 7 survived two, 24 crossed two or
more closes (one crossed three), and the longest ran 1,101 market minutes — 2.8
sessions, triggered 2020-12-04 10:39, peaked 2020-12-08 14:24 after a 7.2% run-up,
broke 2% at the 12-09 open. In wall-clock terms the p90 episode lasts 1,402 minutes
(about a day) and the longest 7,460 (5.2 days).

The clearest single indicator is where the spanning episodes come from:

| trigger window | 5%/2% spans | 4%/1.5% | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|---|
| 09:30–10:00 | **11.0%** | 3.2% | 0.4% | 0.0% | 0.0% |
| 11:00–12:00 | **16.3%** | 8.5% | 3.3% | 0.0% | 0.0% |
| 13:00–14:00 | **27.9%** | 21.3% | 6.8% | 0.0% | 0.0% |
| 14:00–15:00 | **39.7%** | 20.7% | 11.6% | 1.4% | 0.1% |
| 15:00–15:30 | **56.2%** | 43.3% | 19.7% | 6.0% | 0.6% |
| 15:30–16:00 | 82.4% | 77.4% | 66.1% | 42.5% | 25.3% |
| *share of all spanning triggered 15:30–16:00* | **22%** | 34% | 57% | 83% | 96% |

At 5%/2% a **9:30 trigger spans a close 11% of the time** and a 1pm trigger 27.9%.
Overnight risk here is not an artifact of running out of session — it is what the
position is.

## A new behaviour at 2%: the gap stops being decisive

At the tight thresholds, a retreat that crossed a close was essentially always
completed by the gap itself — 97% at 1%/0.25%, 95% at 2%/0.5%. That fraction falls
steadily, and at 5%/2% **a third of gap-crossing retreats survive the open**: the
2% band is wide enough that the overnight gap does not clear it, and the position
lives on into the next session before breaking.

So the two overnight risks separate as the threshold widens. The *un-actionable* one
(gap prints straight through your level) grows in severity — median give-back 2.47 →
3.96% — but shrinks as a share of gap-crossings. The *duration* one (you are simply
still holding, days later) grows without bound.

## The thresholds do not scale linearly

Going 1% → 5% on the upswing:

* Episodes fall **18,166 → 7,014 → 3,575 → 2,197 → 1,518** — halving, halving, then
  −39%, then −31%.
* The median wait rises **4 → 6 → 13 → 26 → 41 min** — flat, then roughly doubling.
* Leg B (the retreat itself) rises **2 → 3 → 5 → 9 → 15 min**.

The retreat leg is compressed at the bottom because small retreats sit near SOXL's
noise floor. Measured on the same file, the **median absolute 1-minute return is
0.119%**, so 0.25% is 2.1× a typical minute (22.6% of individual minutes clear it
unaided), 0.5% is 4.2× (6.1%), 1% is 8.4× (0.9%), 1.5% is 12.6× (0.2%) and 2% is
16.8× (0.06%). A 0.25% "retreat" is really just the next wiggle; a 2% one is an event.

## The part that matters for trading

At **every** threshold the gap-completed retreats gave back far more than the
threshold — **median 2.47 / 2.74 / 3.05 / 3.59 / 3.96% below the peak on the first bar
back**, worst 31.5% in all five. Across a close, none of these is a level you get
filled at; the open prints straight past it. Neither widening nor tightening the
retreat protects you there.

What the threshold really chooses is **how much overnight exposure you take on**:
1.8% → 3.4% → 8.1% → 14.1% → **22.7%** of episodes span a close. At 5%/2% roughly
**one episode in four is carried through a close**, one in nine has its retreat
completed by a gap you cannot trade, 72 (10.9/yr) run over a weekend, and 74 are still
open a full session later.

## By year — median market minutes (and % spanning a close)

| year | 5%/2% | 4%/1.5% | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|---|
| 2020 | 28 (21%) | 19 (15%) | 11 (8%) | 5 (3%) | 3 (2%) |
| 2021 | 83 (35%) | 44 (22%) | 20 (10%) | 9 (5%) | 5 (3%) |
| 2022 | 35 (19%) | 20 (11%) | 11 (5%) | 5 (3%) | 3 (1%) |
| 2023 | 100 (38%) | 56 (20%) | 27 (12%) | 9 (4%) | 4 (2%) |
| 2024 | 44 (17%) | 30 (12%) | 18 (7%) | 8 (4%) | 4 (2%) |
| 2025 | 47 (25%) | 27 (12%) | 15 (11%) | 6 (3%) | 4 (2%) |
| 2026 | 27 (13%) | 16 (10%) | 8 (7%) | 5 (3%) | 3 (2%) |

The year ordering is identical at every threshold — 2021 and 2023 are the slow low-vol
grinds, 2022 and 2026 the fast ones — so the ranking is a property of the tape, not of
the threshold. **Read the 5%/2% row-to-row spread with care**: at 144–312 episodes per
year the per-year medians swing 27 → 100 minutes, which is real dispersion but on
samples an order of magnitude thinner than the 1%/0.25% column. Full per-year
n / mean / p90 / max are in each report file.

## Robustness

| variant | 5%/2% | 4%/1.5% | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|---|
| **1-min closes (primary)** | 1,518 · 41 min · 22.7% | 2,197 · 26 · 14.1% | 3,575 · 13 · 8.1% | 7,014 · 6 · 3.4% | 18,166 · 4 · 1.8% |
| 1-min intrabar (High/Low) | 1,869 · 25 min · 16.2% | 2,880 · 12 · 9.8% | 5,003 · 5 · 4.9% | 11,228 · 1 · 1.2% | 40,510 · 1 · 0.5% |
| 5-min closes (separate file) | 1,027 · 85 min · 32.5% | 1,450 · 55 · 21.4% | 2,205 · 30 · 14.1% | 3,945 · 15 · 6.8% | 8,467 · 10 · 4.8% |

The three disagree exactly as sampling says they must, and none reverses the finding
at any threshold. Intrabar High/Low is the *earliest-possible* reading and is
optimistic: a single 1-min bar whose High clears the trigger and whose Low is the
retreat below that High scores as a complete 0-minute episode, though the within-bar
sequence is unknowable at this resolution — it degenerates at 1%/0.25%, where the
median episode is one bar, and is most informative at the wide pairs, where it still
gives a 25-minute median. 5-min bars cannot resolve anything faster than 5 minutes and
skip the wiggles that end an episode, so they overstate duration everywhere. **Closes
on 1-min bars are the primary read: unambiguous, and every level in them is one you
could have transacted at.**

## Is it tradeable? — measured, and mostly no

`tradeability.py` turns each ledger into a trade log; `edge_test.py` asks whether the
events carry information at all. Both were run before any strategy was proposed, and
they rule most of them out.

**The mechanical trade is zero-mean.** Buy at the trigger, sell at the retreat, over
6.6 years, no costs:

| pair | n | win% | mean/trade | median/trade | time in market |
|---|---|---|---|---|---|
| 5%/2% | 1,518 | 37.0% | +0.039% | −0.819% | 22.5% |
| 3%/1% | 3,575 | 36.0% | +0.019% | −0.472% | 16.9% |
| 2%/0.5% | 7,014 | 34.4% | **−0.042%** | −0.303% | 12.2% |
| 1%/0.25% | 18,166 | 35.4% | **−0.002%** | −0.195% | 15.7% |

Mean per trade is within a rounding error of zero and **flips sign** with the threshold
and with a one-bar execution lag. Compounded outcomes swing wildly (−97% to +898%)
because a near-zero mean with 2–4% per-trade dispersion is all volatility drag, not
edge. Buy-and-hold over the same window returned **542%**. The mirror trade (short the
trigger, cover the retreat) is the same series negated and is not a strategy either.

**The trigger and the retreat carry no information.** Forward returns after each event
versus an unconditional random bar, Welch t:

| horizon | after trigger | after retreat | after peak |
|---|---|---|---|
| +15 min | t −0.9 … +0.8 | t +0.2 … +0.8 | **t −32** |
| +60 min | t −1.1 … +0.4 | t +0.2 … +0.9 | **t −26** |

Trigger and retreat are indistinguishable from noise at every threshold and horizon.
The peak looks enormously predictive and is **not tradeable**: it is defined
retrospectively as the running maximum, so price falls after it by construction. That
row is a look-ahead-bias check, not a signal.

**The one candidate edge does not survive a split sample.** Overnight return when an
episode was open at the close looked negative (2%/0.5%: −0.54% vs +0.44%, t −2.64).
Split at 2023-04-13 it is a first-half-only effect — 3%/1% goes −1.22% (t −2.87) then
+0.30% (t +0.64); 1%/0.25% goes −0.89% then −0.01%. It is COVID-era volatility, not
structure, and five thresholds were tested to find one t past 2.

### What the data does establish: the cost of a stop

Slippage against the level the stop was aiming at (`peak × (1 − down)`):

| pair | avg slip/episode | p99 | max | share of total drag from the ~1–11% of episodes crossing a close |
|---|---|---|---|---|
| 5%/2% | 0.486% | 5.86% | 30.1% | **52%** |
| 4%/1.5% | 0.398% | 4.37% | 30.4% | 40% |
| 3%/1% | 0.344% | 3.56% | 30.8% | 33% |
| 2%/0.5% | 0.296% | 2.31% | 31.1% | 21% |
| 1%/0.25% | 0.251% | 1.62% | 31.3% | 12% |

A 0.5% stop costs 0.80% to execute — a **59% overshoot** — and at 5%/2% **half the
total slippage comes from one episode in nine**, the ones that cross a close. That
concentration, not any directional signal, is the durable, actionable finding here.

## What overnight protection actually costs

`protection_cost.py` prices the hedge the slippage finding implies, from
`raw_data/SOXL_intraday_5m_exp_*.csv` (736 files, 5-min option **trade
aggregates**). Buy a put at the last print of the session, sell at the first
print of the next: **37,586 paired trades over 1,353 overnights, 2021-01 → 2026-07.**

Two data facts had to be established first. The **16:00 option bar never carries a
trade** — the last print of the session is 15:55, so that is the entry stamp. And
trade density collapses with tenor: 26% of bars at 0–4 DTE, 5% at 35–39, so only
short-dated contracts support this measurement at all.

### Cost of one night, in bp of the SOXL notional protected

| tenor / strike | median premium | median cost/night | **mean cost/night** | paid off |
|---|---|---|---|---|
| 3–7 DTE, ATM ±1% | 446 bp | 39.2 bp | **14.0 bp** | 40.2% |
| 3–7 DTE, 3–7% OTM | 238 bp | 23.6 bp | **3.6 bp** | 40.3% |
| 8–14 DTE, ATM ±1% | 613 bp | 27.8 bp | **10.5 bp** | 42.4% |
| 1–2 DTE, ATM ±1% | 278 bp | 52.2 bp | **−1.7 bp** | 37.9% |

**Mean far below median is the insurance signature** — you lose a little on most
nights and get paid on the bad ones. Splitting 3–7 DTE ATM by what the night did
shows the payoff working exactly as intended: gap down >2% returns **−241 bp**
(paid off 94.3% of the time), gap up >2% costs **+218 bp** (paid off 0.5%).

### But prints are not quotes

These are trade prints, so the measured cost is a **lower bound** — you buy nearer
the ask and sell nearer the bid. On the 3–7 DTE, 0 to −7% population (n=2,695,
median premium 327 bp):

| round-trip spread | cost/night |
|---|---|
| 0% (measured) | 6.6 bp |
| 5% | 23.0 bp |
| 10% | 39.3 bp |
| 20% | 72.0 bp |

SOXL weekly spreads are realistically 5–15% of premium, so **~25–50 bp/night** is
the honest planning number, not 6.6.

### Head to head with the slippage it prevents

| pair | nights exposed | gap slippage per exposed night | hedge cost/night (5–15% spread) |
|---|---|---|---|
| 5%/2% | 370 | **103 bp** | 23–50 bp |
| 3%/1% | 292 | **137 bp** | 23–50 bp |
| 2%/0.5% | 236 | **188 bp** | 23–50 bp |

The benefit exceeds the cost at every realistic spread. **Three caveats keep this
from being a free lunch**, and they are large:

1. **Delta.** An ATM put is ~0.5 delta, so one put per 100 shares hedges about half
   the initial move; full coverage roughly doubles the cost. Delta rises toward 1 as
   a gap goes ITM, so the tail is better hedged than the median — but the median
   night is over-counted above.
2. **The put and the stop do not target the same level.** "Gap slippage" is measured
   against `peak × (1 − down)`; a put pays below its strike. They overlap, they are
   not the same quantity, so this is an order-of-magnitude comparison, not a P&L.
3. **The benefit only exists if you run the stop strategy** — and the section above
   shows that strategy is zero-mean. Hedging a no-edge strategy does not create edge;
   the cheaper fix is not to trade it.

A conditional test — does the hedge cost less on nights an episode was open? — is
negative at four of five thresholds (t between −0.16 and +0.24). Only 2%/0.5% shows
an effect (−31.2 bp vs +12.8 bp, t −3.01) and it does survive a split sample, but
with no monotone pattern across thresholds and one hit in five tests it should be
read as multiple comparisons, not a finding.

## Selling that premium instead

`premium_selling.py` takes the other side: sell the put at 15:55, buy it back at
the next 09:30. Same 37,586 paired trades. The seller's P&L is the buyer's cost
with the sign flipped, but the two sides are **not** mirror images, because the
spread is paid by whoever crosses and the tail sits entirely on the seller.

### The seller wins most nights and still loses

| tenor / strike | premium | mean | median | win rate | p1 | worst | worst ÷ mean |
|---|---|---|---|---|---|---|---|
| 3–7 DTE, ATM ±1% | 446 bp | **+14.0 bp** | +39.2 | 58.7% | −801 | **−1,497 bp** | 107× |
| 3–7 DTE, 3–7% OTM | 238 bp | **+3.6 bp** | +23.6 | 57.9% | −656 | −1,249 bp | 346× |
| 1–2 DTE, ATM ±1% | 278 bp | **−1.7 bp** | +52.2 | 61.5% | −884 | −1,243 bp | mean ≤ 0 |
| 1–2 DTE, 1–3% OTM | 190 bp | **−16.1 bp** | +36.6 | 59.7% | −838 | −1,086 bp | mean ≤ 0 |

Win rates of 57–63% with a mean near zero or negative is the short-vol signature.
Note the **1–2 DTE rows are already negative before any costs** — the tenor where
theta looks richest is the one where an overnight gap most outruns the premium.

### The equity curve says it plainly

One sale per night, the 3–7 DTE contract nearest 3% OTM, 717 nights 2021-03 → 2026-07:

| round-trip spread | mean/night | total | max drawdown | Sharpe (ann) |
|---|---|---|---|---|
| 0% (prints) | +5.8 bp | +4,172 bp | −3,592 bp | 0.51 |
| **2%** | **−1.2 bp** | −830 bp | −7,049 bp | −0.10 |
| 5% | −11.6 bp | −8,331 bp | −12,236 bp | −1.03 |
| 10% | −29.1 bp | −20,834 bp | −21,283 bp | −2.56 |

**Break-even round-trip spread: 1.8% of premium.** SOXL weeklies realistically run
5–15%, so the seller loses at any spread you can actually trade. And even at a
fictional zero spread the max drawdown is 86% of the entire profit.

The five worst nights are all overnight gaps the study already flagged:

| night | spot | gap | premium | P&L |
|---|---|---|---|---|
| 2026-06-22 | 300.89 | **−21.6%** | 785 bp | **−1,212 bp** |
| 2025-01-24 | 32.73 | −15.5% | 278 bp | −1,057 bp |
| 2024-08-02 | 29.32 | −19.8% | 716 bp | −989 bp |

**One worst night = 208 nights of average income** — and that income is already
negative once you pay the spread. By year the mean is negative in 2021, 2022 and
2024 and positive in 2023, 2025, 2026; the two best years (+24, +30 bp) carry the
two worst tails (−1,057, −1,212 bp).

Conditioning on the retreat study does not rescue it: selling only on nights with no
open episode gives t between 0.00 and 0.46 at four of five thresholds. Only 2%/0.5%
separates (quiet +13.1 bp vs episode-open −36.2 bp, t 1.99) — the same lone threshold
that keeps surfacing across every test here, still short of significance, still one
hit in five.

### Both sides lose to the spread — which is the real finding

| | buyer | seller |
|---|---|---|
| at zero spread | −6.6 bp/night | +5.8 bp/night |
| at 5% spread | −23.0 bp/night | −11.6 bp/night |
| at 10% spread | −39.3 bp/night | −29.1 bp/night |

The mid-market edge either way is ~6 bp; crossing costs 16–33 bp. **The spread is
larger than the entire directional edge**, which is what a well-functioning options
market looks like — the market maker holds the edge, and neither side of this trade
is a strategy.

The asymmetry that remains is one of *purpose*, not expectancy. The buyer is
purchasing insurance: the mean is not the point, the truncation of a 31.5% tail is,
and paying a fair-to-slightly-rich price for that can still be rational. The seller
has no such defence — they take a fat tail for a mean that is negative after costs.

## Selling the spread instead of the naked put

`put_spread.py` replaces the naked short put with a vertical: sell a put ~3% OTM,
buy one below it, same expiration, both legs at the 15:55 print and out at the next
09:30. A naked round trip crosses the market twice; a vertical crosses **four**
times, and the cost knob charges each leg's own premium on every crossing.

### The tail cap works. The economics get worse.

Short leg 3% OTM, 3–7 DTE, width 5% of spot — 654 nights, 2021-03 → 2026-07,
median credit 146 bp of spot against a median max loss of 352 bp:

| per-leg spread | mean/night | total | max DD | win | Sharpe | worst night |
|---|---|---|---|---|---|---|
| 0% (prints) | +2.2 bp | +1,424 bp | −1,871 bp | 54.1% | 0.52 | −336 bp |
| **2%** | **−19.6 bp** | −12,821 bp | −12,907 bp | 44.2% | −4.65 | −401 bp |
| 5% | −52.3 bp | −34,190 bp | −34,190 bp | 23.2% | −11.71 | −499 bp |
| 10% | −106.7 bp | −69,803 bp | −69,803 bp | 6.9% | −20.03 | −661 bp |

**Break-even per-leg spread: 0.2% of premium**, against 1.8% for the naked put.

So the vertical does exactly what it is supposed to do on the tail — worst night
**−336 bp against −1,212 bp naked, a 3.6× reduction**, and the cap binds: on
2026-06-25 (−10.8% gap) the loss stopped at −336 bp against a −336 bp maximum. Two
of the five worst nights finished *inside* the cap because the long leg went ITM too.

But it pays for that with a **9× harder cost hurdle**. The credit is roughly half the
naked premium while the crossings double, so the same real-world spread that merely
erases the naked seller's edge buries the vertical. At a realistic 5% per-leg spread
the naked seller loses 11.6 bp/night and the vertical loses 52.3.

### Width is a dial between the two, not an escape

| width | credit / max loss | mean @ 0 spread | worst night |
|---|---|---|---|
| 2% of spot | 52% | +0.3 bp | −234 bp |
| 5% of spot | 43% | +2.2 bp | −336 bp |
| 10% of spot | 31% | +3.4 bp | −571 bp |

Mean rises and the tail widens monotonically as the long leg moves away — the
structure walks continuously from vertical toward naked, and the expectancy you gain
is exactly the tail you take back on. There is no width at which it becomes a trade.

### Where this leaves all four structures

| structure | mean @ 0 spread | break-even spread | worst night |
|---|---|---|---|
| long put (protection) | −6.6 bp | n/a — it is insurance | +payoff |
| naked short put | +5.8 bp | 1.8% | **−1,212 bp** |
| short 5%-wide vertical | +2.2 bp | **0.2%** | −336 bp |

Every structure here is priced through the spread. The mid-market edge is a few bp in
either direction; crossing costs 16–33 bp naked and roughly double that for a
vertical. Defining the risk does not create edge — it buys a smaller tail at a
strictly worse expectancy, and in this market that trade is not close.

## Buying the spread instead

The same `put_spread.py` also prices the debit side: long a put ~1% OTM, short one
below it — capped protection, bought cheaper than the naked put. It is cheaper. It
also stops working exactly where it is needed.

### Coverage runs backwards

Realised option P&L as a share of the underlying's loss that night, 562 nights with
both structures priced, 5%-wide spread:

| gap bucket | n | underlying loss | naked put | cover | **spread** | **cover** |
|---|---|---|---|---|---|---|
| 0 to −1% | 57 | 51 bp | 14 bp | 27% | 11 bp | 23% |
| −1 to −3% | 108 | 190 bp | 70 bp | 37% | 31 bp | **17%** |
| −3 to −6% | 73 | 419 bp | 187 bp | 45% | 71 bp | **17%** |
| **worse than −6%** | 24 | 986 bp | 571 bp | **58%** | 123 bp | **12%** |

**The naked put's coverage rises with the size of the gap — 27% → 58% — which is what
insurance is supposed to do. The spread's coverage falls, 23% → 12%.** The short leg
is a promise to stop protecting you, and it comes due precisely on the nights the
position exists for.

Night by night on the five worst gaps:

| night | gap | underlying loss | naked put | spread | spread's cap |
|---|---|---|---|---|---|
| 2026-06-22 | −21.6% | 2,157 bp | **1,497 bp** | 248 bp | 157 bp |
| 2024-08-02 | −19.8% | 1,978 bp | **1,177 bp** | 188 bp | 153 bp |
| 2025-01-24 | −15.5% | 1,549 bp | **1,210 bp** | 217 bp | 165 bp |
| 2026-03-02 | −12.0% | 1,203 bp | 614 bp | **−69 bp** | 220 bp |

On 2026-03-02 the "protection" **lost money on a 12% adverse gap**.

### And it costs more to run

| per-leg spread | long naked put | long 5%-wide vertical |
|---|---|---|
| 0% (prints) | −6.6 bp | **−3.1 bp** |
| 5% | −23.0 bp | **−70.6 bp** |
| 10% | −39.3 bp | **−138.0 bp** |

Cheaper at a fictional zero spread, three times dearer at a realistic one, because
two legs cross the market twice as often. So the debit spread buys you a lower
premium in exchange for **5× less tail coverage and 3× the friction**.

### All four structures, together

| structure | mean @ 0 spread | @ 5% spread | tail behaviour |
|---|---|---|---|
| **long put** | −6.6 bp | −23.0 bp | covers **58%** of a >6% gap |
| long vertical | −3.1 bp | −70.6 bp | covers 12%; can lose on a −12% night |
| short put | +5.8 bp | −11.6 bp | worst night −1,212 bp |
| short vertical | +2.2 bp | −52.3 bp | worst night −336 bp |

Both two-leg structures are dominated by their one-leg counterparts once real spreads
are paid. Selling the vertical caps a tail but moves break-even from a 1.8% spread to
0.2%; buying it lowers the premium but guts the coverage. The second leg always pays
for itself in something you wanted.

**The only structure here that does its job is the naked long put, and only as
insurance** — its expectancy is negative by construction, the point is that it is the
one thing measured in this lab whose protection gets *better* as the night gets worse.

## Buying the put and selling a call against it — the collar

`collar.py` puts the second leg on the *other* side: keep the put whole, sell a call
to pay for it, give up upside instead of downside. That is a different trade-off from
the debit spread, and it measures very differently. Uses `raw_data/SOXL_intraday_5m_exp_*.csv`
for both rights — 187,032 call prints alongside the 161,613 put prints.

### The risk transformation is real, and the coverage is right way up

3% OTM put / 3% OTM call, 3–7 DTE, 634 nights, holding 100 shares through the night:

| position | mean | sd | worst | best | Sharpe |
|---|---|---|---|---|---|
| stock alone | 27.5 bp | 419.7 bp | −2,157 bp | 1,987 bp | 1.04 |
| stock + collar @ 0% spread | 1.7 bp | **135.8 bp** | **−592 bp** | 477 bp | 0.20 |

Volatility falls **3.1×** and the worst night **3.6×**. Unlike the debit spread,
coverage *rises* with the size of the gap — 71% on −3 to 0%, 75% on −6 to −3%,
**86% worse than −6%** — because on a down gap the put gains **and** the short call
also gains. Both legs pull the same way. That is the structural difference from the
put spread, where the short leg fought you exactly when it mattered.

The median net debit is **0 bp**: at 3%/3% the call fully finances the put.

### But the call costs 2.5× more than the put it finances

Leg attribution over the same 634 nights, zero spread:

| | bp/night |
|---|---|
| stock overnight drift | **+27.5** |
| long put leg | −7.4 |
| **short call leg** | **−18.4** |
| collar net | +1.7 |

| leg | 335 up nights | 299 down nights |
|---|---|---|
| call | **−135.2 bp** | +112.5 bp |
| put | −117.2 bp | +115.6 bp |

On a >6% up gap the collar surrenders 747 bp of a 931 bp rally — you keep 20%.

### Vol-matched, the protective put alone beats both

A structure that cuts volatility must be compared at equal risk:

| position | mean | sd | Sharpe | **vol-matched mean** |
|---|---|---|---|---|
| stock alone | 27.5 bp | 419.7 bp | 1.04 | 27.5 bp |
| **stock + long put only** | 20.1 bp | 269.3 bp | **1.18** | **31.3 bp** |
| stock + collar | 1.7 bp | 135.8 bp | 0.20 | 5.3 bp |

**At zero spread the protective put alone is the only overlay in this lab that beats
holding the stock** — Sharpe 1.18 against 1.04, and 31.3 bp against 27.5 bp once
levered to equal volatility. Adding the call takes that to 5.3 bp. At a realistic 5%
per-leg spread everything is negative again: put-only −14.0 bp/night, collar −66.4.

### The caveat that matters most

SOXL's overnight drift over this sample is **+27.5 bp/night — about +69%/yr from gaps
alone.** A short call is structurally punished in that regime, so **the call-leg
result is the most sample-dependent number in this lab.** In a flat or falling market
the collar would look materially better, and nothing measured here rules that out.
The put-leg and coverage results do not depend on the drift the same way; the −18.4
bp/night call cost does.

### Every structure measured, together

| structure | mean @ 0 spread | @ 5% spread | tail behaviour |
|---|---|---|---|
| **long put** | −6.6 bp overlay / **+31.3 bp vol-matched** | −23.0 bp | covers 58–86% of a big gap |
| **collar** | +1.7 bp / +5.3 vol-matched | −66.4 bp | covers 86%, keeps 20% of a big rally |
| long vertical | −3.1 bp | −70.6 bp | covers 12%; can lose on a −12% night |
| short put | +5.8 bp | −11.6 bp | worst night −1,212 bp |
| short vertical | +2.2 bp | −52.3 bp | worst night −336 bp |

The collar is the first two-leg structure here that is not dominated on risk — it
genuinely converts a fat-tailed holding into a narrow one, with coverage that improves
as the night gets worse. What it cannot do is survive the spread, and in this sample
it pays for its protection with more upside than the protection is worth.

## The three underlying-only claims, tested

This lab asserted three risk-management claims and did not check them.
`exit_rules.py` does. Entry is always the same +2% trigger (7,014 of them, no
directional edge), so only the exit rule varies — these are exit-quality questions,
judged on dispersion, tail and execution slippage, not on profit.

### Claim 1 — "time stops beat price stops": **supported, but "beats" is too strong**

At matched holding periods:

| exit rule | median hold | mean | sd | p1 | slippage |
|---|---|---|---|---|---|
| trailing stop 0.50% | 6 min | −4.21 bp | 136.2 | −225 bp | **29.6 bp** |
| time stop 5 min | 5 min | **−1.51 bp** | **123.1** | **−336 bp** | **0** |
| trailing stop 1.00% | 15 min | −2.43 bp | 201.3 | −386 bp | 33.9 bp |
| time stop 15 min | 15 min | −2.01 bp | 209.1 | −549 bp | **0** |

The clock exit gives an equal-or-better mean and **eliminates the 26–34 bp of
slippage entirely** — a stop has to be filled, a clock does not. But it has a
*fatter left tail* (p1 −336 vs −225), because it never cuts a loser. So it is a
trade, not a free win: you swap guaranteed slippage for an uncapped tail.

### Claim 2 — "don't set a stop tighter than ~0.5%": **not supported**

| trailing stop | mean | sd | worst | slippage | spans a close |
|---|---|---|---|---|---|
| **0.25%** | **−1.74 bp** | **106.9** | −2,799 | **28.3 bp** | **1.9%** |
| 0.50% | −4.21 bp | 136.2 | −2,799 | 29.6 bp | 3.4% |
| 1.00% | −2.43 bp | 201.3 | −2,799 | 33.9 bp | 8.5% |
| 3.00% | +22.48 bp | 493.9 | −2,799 | 60.6 bp | 43.2% |

The claim was that below ~0.5% you stop on noise and it costs you. **It does not.**
The 0.25% stop has the *lowest* dispersion, the *lowest* slippage and the *least*
overnight exposure, with a mean no worse than 0.5%. The reasoning was wrong:
stopping on noise costs nothing when there is no edge to protect. The rising mean at
wider stops (+22 bp at 3%) is not stop quality — it is holding longer and collecting
more of SOXL's drift, bought with 4.6× the dispersion.

The real argument against a very tight stop is **turnover** — more round trips, more
commission and spread — and this test does not price that. It is a cost question, not
a noise question.

### Claim 3 — "don't open a stop-managed position in the last 30 minutes": **strongly supported**

Trailing stop 0.50%, split by entry time:

| entries | n | mean | sd | worst | spans a close | slippage |
|---|---|---|---|---|---|---|
| before 15:30 | 6,550 | −2.59 bp | 98.1 | −436 | 0.6% | 23.9 bp |
| **15:30–16:00** | 464 | **−27.07 bp** | 379.6 | **−2,799** | 42.5% | **110.7 bp** |
| late, forced flat at the bell | 464 | **+8.84 bp** | 95.9 | −226 | 0% | 27.4 bp |

Late entries are **10× worse in mean, 4× the dispersion, 6× the worst case and 4.6×
the slippage.** At a 1% stop it is starker still: −53.75 bp and 156.9 bp of slippage.

But the fix is better than the claim. **Do not avoid the entry — force the exit.**

### The finding none of the three claims made

Flattening at the bell rather than holding the stop overnight improves **every metric
at every stop width**, and costs nothing:

| rule | mean | sd | worst | spans |
|---|---|---|---|---|
| stop 0.50%, hold overnight | −4.21 bp | 136.2 | −2,799 | 3.4% |
| **stop 0.50%, flat at bell** | **−1.86 bp** | **95.4** | **−435** | 0% |
| stop 1.00%, hold overnight | −2.43 bp | 201.3 | −2,799 | 8.5% |
| **stop 1.00%, flat at bell** | **+0.55 bp** | **143.5** | **−435** | 0% |
| stop 2.00%, hold overnight | +1.64 bp | 331.8 | −2,799 | 25.7% |
| **stop 2.00%, flat at bell** | **+4.03 bp** | **222.1** | **−548** | 0% |

Mean improves, dispersion falls ~30%, and the worst case falls **6×** — from −2,799 bp
to −435. No premium, no second leg, no options account. The whole options investigation
above was chasing a way to survive the overnight gap; **the cheapest way to survive it
is not to be there.** That only costs the overnight drift, which the entry signal does
not earn anyway.

## Backtesting the underlying-only rules — and a correction

`exit_rules.py` compared exits per-trade. Per-trade means hide compounding and
turnover, so `backtest.py` runs each rule as a full strategy: compounded equity,
costs per side, drawdown, against buy-and-hold over the same 6.6 years. All-in /
all-out, never levered, no overlapping trades.

### Every variant loses, most of them catastrophically

At 1 bp per side (2 bp round trip):

| strategy | total | CAGR | max DD | Sharpe | trades | in market |
|---|---|---|---|---|---|---|
| **buy and hold** | **+542%** | **+32.7%** | | | 1 | 100% |
| trail 2%, flat at bell | −42% | −7.9% | −71.2% | 0.15 | 4,409 | 56.8% |
| flat at bell only (no stop) | −73% | −18.2% | −83.1% | 0.16 | 1,658 | 90.0% |
| trail 1%, flat at bell | −79% | −20.9% | −87.1% | −0.31 | 6,083 | 29.2% |
| time 30m, flat at bell | −82% | −22.9% | −93.8% | −0.18 | 5,528 | 24.7% |
| trail 0.5%, flat at bell | −95% | −36.9% | −96.4% | −1.32 | 7,014 | 12.1% |
| trail 0.5%, hold overnight | −99% | −53.3% | −99.4% | −1.49 | 7,014 | 12.2% |

Set costs to zero and only one variant turns positive — trail 2% flat at bell,
**+40% against buy-and-hold's +542%.** The per-trade improvements were real and they
do not survive contact with turnover: **1,066 round trips a year is 21.3%/yr of pure
friction at 1 bp per side, 42.6%/yr at 2 bp.**

### The entry is worse than random

| rule | trigger entry | random entry, same count |
|---|---|---|
| trail 1%, flat at bell | **−79%** | −22% |
| time 30m, flat at bell | −82% | −85% |

Entering on a +2% upswing is *actively worse* than entering at a random minute. This
does not contradict the earlier finding that the trigger has no directional edge
(t −1.1 to +1.0) — it explains it. The trigger is not predictive of direction, but it
is systematically bad for a **trailing stop**, because you enter at a local extreme
where the stop sits immediately under a fresh peak. Recall 26.6% of triggers *are*
the peak.

### The correction: what "flat at the bell" actually costs

Decomposing SOXL's 6.6 years into the two legs:

| leg | total | annualised |
|---|---|---|
| **overnight (close → next open), 1,652 nights** | **+2,320%** | **+62.3%/yr** |
| **intraday (open → close), 1,652 sessions** | **−75%** | **−19.1%/yr** |

**SOXL's entire return is overnight. The intraday session is a persistent −19.1%/yr
headwind.** Buy-and-hold's +542% is the product of the two.

This overturns the recommendation this lab made one section earlier. "Flat at the
bell" was offered as a free improvement because it improved every per-trade metric —
mean, dispersion, worst case. It improved them **by removing exposure to the only
part of the day that makes money.** The claim that it "costs only the overnight
drift, which this entry signal does not earn anyway" was right about the signal and
badly wrong about the magnitude: that drift is +62.3%/yr, the whole instrument.

So the per-trade table was not measuring a better rule. It was measuring the risk
reduction you get from being flat — which you can obtain more cheaply and completely
by not trading at all.

### What survives

Nothing, as a strategy. Any intraday long on SOXL fights a −19.1%/yr drift before
costs, and this entry adds 1,066 round trips a year of friction on top. The three
exit-rule claims tested in the previous section remain correct **as statements about
exits** — a clock exit really does eliminate slippage, late entries really are far
worse, tight stops really do have the lowest dispersion — but they are refinements to
a position that should not be opened. **The measured conclusion of this lab is that
the tradeable content of the retreat timing study is zero, and the one durable fact
it surfaced is about when SOXL earns its return, not about upswings and retreats.**

## Backtesting the overnight-only strategy

`overnight.py` turns the decomposition into a strategy and charges it: buy at the
session close, sell at the next open, flat all day. 251 round trips a year against
the trigger strategy's 1,066, so friction is ~4× lighter — 5.0%/yr at 1 bp per side.

### It beats buy-and-hold, and survives realistic costs

| strategy | total | CAGR | max DD | Sharpe | win |
|---|---|---|---|---|---|
| buy and hold | +542% | 32.7% | −90.5% | 0.78 | |
| **sell at the 09:30 open print** | **+1,586%** | **53.6%** | −78.2% | **0.97** | 54.8% |
| sell 5 min after the open | +1,214% | 47.9% | −85.6% | 0.91 | 53.0% |
| sell 30 min after the open | +886% | 41.6% | −85.8% | 0.84 | 52.1% |

Cost sensitivity, selling at the open print: **+2,245% at 0 bp, +1,586% at 1, +1,112%
at 2, +350% at 5, and −14% at 10 bp per side.** It needs sub-5-bp execution — plausible
in SOXL with MOC/MOO orders, fatal if you cross a spread.

The edge decays the longer you hold past the open (53.6% → 47.9% → 41.6% CAGR), which
is consistent with a genuine open-print effect rather than a data artifact.

### But the return is 20 nights out of 1,652

| | total |
|---|---|
| all 1,652 nights | +1,586% |
| drop the best 5 | +624% |
| drop the best 10 | +249% |
| **drop the best 20 (1.2% of nights)** | **−0%** |
| drop the best 50 | −95% |

**The entire six-year return comes from twenty nights.** That is not a drift you
harvest; it is a lottery-ticket portfolio that happened to hit. And the nights that
pay are the volatile ones — precisely where your fill is least likely to match a print
in a 5-minute aggregate.

### And it is not stable

| year | overnight | buy & hold | intraday |
|---|---|---|---|
| 2020 | **+134.8%** | +61.3% | −32.5% |
| 2021 | +140.0% | +127.5% | −13.6% |
| 2022 | −69.7% | −86.5% | −53.8% |
| **2023** | **−0.2%** | **+175.4%** | **+180.1%** |
| 2024 | **+207.1%** | −7.3% | −70.9% |
| 2025 | +54.5% | +68.0% | −1.2% |
| 2026 | +100.9% | +155.0% | +15.1% |

**2023 reverses the thesis completely** — the overnight leg made nothing while the
intraday leg made +180%. Leave-one-year-out spans +449% (excluding 2024) to +5,457%
(excluding 2022). Split-half: +53% then +998%, Sharpe 0.54 then 1.36.

The mean is **0.272%/night, sd 4.46%, t = 2.48** — marginal for a single test, and
this was not an independent test: the effect was found by looking, then measured on
the same data.

### The tail is the point

Worst nights: −31.2% (2020-03-13), −23.3%, −22.2%, −21.6% (2026-06-22), −20.5%.
**147 nights worse than −5%, 31 worse than −10%**, against a best night of +19.9%.
Max drawdown −78.2%.

So the honest description is not "SOXL drifts up overnight." It is: **SOXL's largest
gaps in both directions happen overnight, and over this particular sample the up-gaps
won, by a margin concentrated in twenty nights.** You are being paid to hold
event risk through the close — which is the same risk the protective-put section was
trying to hedge, and hedging it would cost more than the 0.272%/night it pays.

### Verdict

Better risk-adjusted than buy-and-hold on this sample (Sharpe 0.97 vs 0.78) and the
only structure in this lab that beats it at all. But it is a concentrated, unstable,
cost-fragile bet on a regime that fully reversed in 2023, with a −78% drawdown and a
−31% single night. It is a real finding about **where SOXL's return lives**, and a
weak basis for a strategy.

## The intraday short — and a correction to how the decomposition was described

`intraday_short.py` trades the other leg: short at the open, cover at the close, flat
overnight. An intraday-only short is flat at settlement so it typically avoids the
overnight borrow charge, but borrow is a parameter here rather than an assumption.

### It loses catastrophically — and so does the long

| strategy | total | CAGR | max DD | Sharpe | worst day |
|---|---|---|---|---|---|
| buy and hold | +528% | 32.2% | | | |
| intraday **long** (open→close) | −80% | −21.9% | −92.6% | 0.16 | −21.1% |
| **intraday SHORT (open→close)** | **−99%** | **−47.6%** | −99.4% | −0.28 | **−51.7%** |
| overnight long (close→open) | +1,586% | 53.6% | −78.2% | 0.97 | −31.2% |
| short the day + long the night | −74% | −18.6% | −98.5% | 0.40 | −51.7% |

Costs and borrow barely matter — at **zero** cost and zero borrow the short still
returns −98%. It loses in six of seven years, in both sample halves (−88% / −88%),
and **t = −0.71** on the daily mean. There is no intraday edge in either direction.

### Why: it is variance drag, not drift

| leg | arithmetic mean | geometric mean | daily sd | variance drag |
|---|---|---|---|---|
| **intraday** | **+0.0770%/day (+21.4%/yr)** | −0.0784%/day (**−17.9%/yr**) | 5.58% | **39%/yr** |
| overnight | +0.2919%/day (+108.5%/yr) | +0.1912%/day (+61.8%/yr) | 4.46% | 25%/yr |

**The intraday leg's arithmetic mean is positive.** Its −17.9%/yr compounded result is
entirely the ½σ² penalty of compounding a 5.58%-a-day series — 39%/yr of pure drag on
a 3× levered ETF.

This corrects how the previous section described it. Calling intraday "a persistent
−19.1%/yr headwind" implies a drift you can short. **You cannot short variance drag.**
Shorting flips the sign of the mean — turning +0.077%/day into −0.097%/day after
costs — while the drag stays exactly where it was, because drag is symmetric. The
short is charged twice and compounds to −99%.

The overnight leg is different in kind, not just in sign: its arithmetic mean
(+108.5%/yr) is large enough to survive its own 25%/yr drag. That, not a directional
tilt, is why one leg works and the other cannot.

### The tail closes the case

Worst days for the short: **−51.7%**, −25.3%, −24.0%, −19.0%, −18.6%. **262 days worse
than −5%, 47 worse than −10%.** A single 2025 session took more than half the account.
Dropping the best 5, 10, 20 or 50 days changes nothing — it is already −99%.

### Where the whole investigation lands

| | arithmetic | geometric | verdict |
|---|---|---|---|
| overnight long | +108.5%/yr | **+61.8%/yr** | works, but 20 nights carry it and 2023 reversed it |
| intraday long | +21.4%/yr | −17.9%/yr | positive edge, eaten by drag |
| intraday short | −21.4%/yr | −47.6%/yr | drag *and* negative mean |

The only leg with a mean big enough to beat its own compounding penalty is the
overnight one, and the previous section already showed that leg is 20 nights of luck
in a 1,652-night sample. Everything else in this lab is a way of paying friction to
hold a zero-mean exposure.

## Holding overnight only when volatility is low

`overnight_vol_filter.py` conditions the overnight leg on volatility. **Data note:**
the VIX index itself was not obtainable — it is absent from the repo, and IBKR
returns "Details currently unavailable" for contract 13455763 (index subscription).
Two substitutes are used and reported side by side, both computed strictly through
the close of day D so there is no look-ahead:

* **RV20** — SOXL's own trailing 20-session realised volatility, annualised.
* **VXXr** — VXX over its own 60-day average. VXX's *level* is useless across time
  (roll decay and reverse splits put 2026's maximum below 2020's minimum), but the
  ratio to its own recent average detrends that and tracks the vol regime.

### On SOXL's own realised vol, the filter improves everything

| filter | nights | total | CAGR | max DD | Sharpe | worst night |
|---|---|---|---|---|---|---|
| all nights | 1,632 | +1,482% | 52.1% | **−78.2%** | 0.95 | **−31.2%** |
| **RV20 below p60** | 979 | **+2,248%** | **61.6%** | **−29.5%** | **1.38** | −15.5% |
| RV20 below p80 | 1,305 | +2,729% | 66.2% | −59.2% | 1.24 | −15.5% |

By quintile, and it is close to monotone:

| RV20 quintile | nights | total | Sharpe | worst | mean/night |
|---|---|---|---|---|---|
| 1 (lowest vol) | 326 | +144% | 0.79 | −7.5% | 0.312% |
| 2 | 326 | +278% | 1.01 | −15.5% | **0.461%** |
| 3 | 327 | +155% | 0.65 | −13.7% | 0.364% |
| 4 | 326 | +20% | 0.25 | −15.0% | 0.157% |
| **5 (highest vol)** | 327 | **−44%** | 0.06 | **−31.2%** | 0.060% |

**The top vol quintile loses money outright.** Excluding the top two takes the whole
strategy from +1,482% to +2,248% while cutting the drawdown from −78.2% to −29.5%.

### It is not keeping the big winners — it is dropping the big losers

The 20 best nights sit at a **median RV20 percentile of 95**; the 20 worst at **93**.
Only 1 of the best 20 is in the lowest vol quintile, and 0 of the worst 20. High vol
produces both tails. The filter gives up most of the biggest up-nights and still ends
ahead, because in that bucket the losses outweigh the wins.

That also fixes the fragility. Unfiltered, dropping the best 20 nights took the
strategy to **−6%**. Filtered, it still returns **+271%**:

| | unfiltered | RV20 below p60 |
|---|---|---|
| full | +1,482% | +2,248% |
| drop best 20 | **−6%** | **+271%** |
| drop best 50 | −95% | −42% |

### Robustness

| test | result |
|---|---|
| by year | positive in **6 of 7** (2022 −19.0% against −69.7% unfiltered; 2023 **+23.0%** against −0.2%) |
| split halves | +232% (t 2.09) then +607% (t 2.86) — both positive, both significant |
| worst night per year | −6.8% to −15.5%, against −31.2% unfiltered |
| t on the mean | **3.53** (0.379%/night, sd 3.36%), against 2.48 unfiltered |

This is the only result in this lab that survived every robustness test applied to it.

### Three caveats that matter

1. **The VIX-like proxy does not confirm it.** On VXX/MA60 the quintiles are
   non-monotone and the *lowest* bucket is the worst: −56% total, Sharpe −0.38.
   Trading below its p20 loses money. So this is a **SOXL-realised-vol** effect, not a
   "VIX is low" effect — the two measure different things, and the question as asked
   ("when VIX is low") is answered **no** by the closest proxy available here.
2. **"Low vol" here is not calm.** The p60 threshold is **107.6% annualised**. This
   filter does not select quiet markets; it selects SOXL below its own median chaos.
3. **The threshold was chosen from the same data.** p20/p40/p60/p80 were all tested
   and p60 reported. p40 (+822%) and p80 (+2,729%) also beat unfiltered, so it is not
   a knife-edge, but the exact cut is fitted and should be expected to degrade
   out of sample.

## The same vol filter on the intraday leg — it does not rescue it

The overnight filter worked. `intraday_vol_filter.py` applies the same conditioner
to the intraday leg, where there is a precise hypothesis to test rather than a hunch:
drag is ~σ²/2, so restricting to low-vol days should shrink it with the *square* of
σ. If the positive arithmetic mean (+0.077%/day) survives while drag collapses, the
geometric mean flips and the intraday long becomes viable.

RV20 is measured through the close of **D−1** here and applied to day D, so a
session's own move cannot inform its own filter.

### The long is not rescued

| RV20 quintile | n | total | arith mean | geo mean | drag | sd/day | t |
|---|---|---|---|---|---|---|---|
| all sessions | 1,632 | −79% | +0.0608% | −0.0962% | 0.157 | 5.60% | 0.44 |
| 1 (lowest vol) | 326 | **−5%** | +0.0591% | −0.0173% | 0.076 | 3.88% | 0.28 |
| 2 | 326 | −57% | **−0.1608%** | −0.2600% | 0.099 | 4.41% | −0.66 |
| 3 | 327 | **+22%** | +0.1978% | +0.0615% | 0.136 | 5.19% | 0.69 |
| 4 | 326 | −20% | +0.1052% | −0.0677% | 0.173 | 5.86% | 0.32 |
| 5 (highest vol) | 327 | −48% | +0.1021% | −0.1973% | 0.299 | 7.84% | 0.24 |

**No monotone pattern**, the only positive bucket is the *middle* one, and every
t-statistic is between −0.66 and +0.69 — the arithmetic means are not
distinguishable from zero in any bucket. Compare the overnight leg, where the
quintiles were near-monotone and the top one lost money outright.

### The mechanism worked exactly as predicted — and it still was not enough

| quintile | sd/day | drag = σ²/2 | arith mean | **mean ÷ drag** |
|---|---|---|---|---|
| Q1 | 3.88% | 0.075 pp | 0.0591% | **0.78** |
| Q3 | 5.19% | 0.135 pp | 0.1978% | 1.47 |
| Q5 | 7.84% | 0.307 pp | 0.1021% | 0.33 |
| all | 5.60% | 0.157 pp | 0.0608% | 0.39 |

The σ² scaling is exact: Q1's drag is 0.48× the all-session drag, and
(3.88/5.60)² = 0.48. Filtering to the calmest fifth **halved the drag and doubled
the mean-to-drag ratio, 0.39 → 0.78.** It simply did not reach 1.

**SOXL's calmest quintile is still 3.88%/day — 61% annualised.** For the intraday
long to survive compounding you would need σ near 3.4%/day, below anything this
instrument offers. The drift is not too small so much as the floor volatility is too
high; a 3× levered single-sector ETF has no quiet regime in which its intraday
arithmetic mean can outrun its own variance penalty.

### The short is destroyed in every bucket

| RV20 quintile | total | t |
|---|---|---|
| 1 (lowest vol) | −43% | −0.46 |
| 3 | −70% | −0.83 |
| 5 | −79% | −0.33 |

Only Q2 is positive (+9%, t 0.49 — noise). On the VXX conditioner it is worse still:
below p40 returns −98% with t −3.19.

### Why the filter helped one leg and not the other

The overnight filter worked because it removed a genuinely **negative** subset — the
top vol quintile returned −44% on its own. There was something real to cut.

Intraday has no such subset: every quintile's arithmetic mean is statistical noise
around a small positive number, and what kills the strategy is not a bad regime but
the variance penalty, which scales with exactly the quantity you are filtering on.
**You cannot filter your way out of drag: the filter removes the drag and the drift
together.** That is the difference between conditioning away a loss and conditioning
away a fee.

## Enter, wait for +X%, exit on the cross — does the take-profit work?

`take_profit.py` tests it directly: enter at a chosen minute, rest a limit at
+X%, exit the moment it prints. The target is detected on the bar **high**, since a
resting limit fills when price trades there — the one place in this lab where
intrabar data is the correct field rather than an optimistic one.

### With a session-close fallback, every configuration loses

Target +1%, exit at the close if it never prints:

| entry | hit rate | median trade | mean | total | t |
|---|---|---|---|---|---|
| 09:30 | **80.0%** | **+0.980%** | −0.060% | −80% | −0.91 |
| 11:00 | 72.8% | +0.980% | −0.020% | −55% | −0.36 |
| 13:00 | 62.0% | +0.980% | −0.031% | −55% | −0.66 |
| 15:00 | 43.0% | +0.408% | −0.053% | −64% | −1.57 |
| 15:30 | 32.8% | +0.154% | −0.056% | −65% | −1.88 |

That is the take-profit signature in one table: **you hit the target 80% of the time,
the median trade is +0.98%, and the strategy still loses 80%.** The 20% of days that
never print the target give back more than the 80% collect. Same at +2% and +3%
targets; no entry time, no target, and no t-statistic above +0.10.

### The intuition about "later in the day" is right — but not for the reason given

Hold to the next open instead of exiting at the bell and the picture inverts:

| entry | hit rate | mean | total | CAGR | t |
|---|---|---|---|---|---|
| 09:30 | 80.0% | −0.142% | −96% | −39.6% | −1.75 |
| 13:00 | 62.0% | +0.021% | −36% | −6.6% | 0.28 |
| 15:00 | 43.0% | +0.213% | **+1,366%** | 50.4% | 2.77 |
| **15:30** | 32.9% | +0.226% | **+1,521%** | 52.7% | 2.75 |

Later is better — but the **hit rate falls** as you go later (80% → 33%), so it is not
that the rise is more probable late in the day. A 15:30 entry held to the open is
simply the overnight trade wearing a different hat, and the overnight leg is where
this instrument's return lives.

### And the target actively subtracts

| variant | mean/night | total | max DD |
|---|---|---|---|
| 15:30 → next open, **no cap** | **0.287%** | **+1,816%** | −74.9% |
| 15:30 → next open, +1% cap | 0.226% | +1,521% | **−49.2%** |
| 15:59 close → next open (plain overnight) | 0.280% | +1,639% | −74.0% |

The cap costs **0.061%/night and about 300 points of total return**. It is not a
return improvement; it is a *risk* trade — it cuts the drawdown from −74.9% to −49.2%
by truncating the nights that run past +1%. Worth having if the drawdown is what
binds; worth knowing it is paid for in return, not free.

## Which days not to trade

On the plain 15:30 → next-open trade (n=1,619, +1,824%, t 2.52):

| filter | n | mean/night | total | max DD | t |
|---|---|---|---|---|---|
| all sessions | 1,619 | 0.290% | +1,824% | −74.9% | 2.52 |
| drop the highest-vol quintile | 1,295 | 0.308% | +1,888% | −59.6% | 2.82 |
| drop Thursdays | 1,294 | 0.399% | +3,960% | −66.6% | 3.03 |
| drop prior-day 0 to +3% | 1,306 | 0.424% | **+5,759%** | −61.0% | 3.24 |
| **drop both vol-Q5 and prior-day 0–3%** | 1,022 | **0.454%** | +4,610% | **−46.3%** | **3.69** |

Split-half on the combined filter: +500% (t 2.49) then +685% (t 2.73) — both positive,
both significant.

**But weight these very unequally.** Eighteen cuts were tested (5 weekdays, 5 vol
quintiles, 4 gap buckets, 4 prior-day buckets). Finding two or three that look good is
what chance produces at that width.

* **The vol filter is credible** — it independently replicates the overnight
  volatility result found earlier on different code and different cuts. Two
  independent arrivals at "do not hold overnight in the top vol quintile" is evidence.
* **Thursday (t 0.03 on its own) and prior-day 0–3% are single-sample findings** from
  an 18-cut search, with no mechanism proposed and no out-of-sample test. They are the
  best-looking slices of a search, and the honest prior is that most of that
  advantage decays. Do not size on them.

The defensible version of the answer is the narrow one: **don't hold overnight when
SOXL's trailing volatility is in its top quintile.** Everything else in the table is a
hypothesis, not a finding.

## The three-way bracket: target, trailing stop, adaptive time stop

`bracket.py` implements the full proposal — enter by time, take profit at +X%, cut on
a 0.5% retreat from the running peak, and if neither fires exit at an **adaptive**
time limit set to the trailing-6-month median minutes-to-target. Same-minute
target+stop collisions resolve as **stop first** (pessimistic); stops fill at their
trigger (optimistic by the 24–30 bp of slippage measured earlier).

### The risk control is real. The edge is not.

Enter 09:30, target +1%, adding one rule at a time:

| configuration | target hit | stopped | mean | total | max DD | t |
|---|---|---|---|---|---|---|
| target only, bell backstop | **80.0%** | — | −0.060% | −80% | **−92.6%** | −0.91 |
| + trailing stop 0.5% | **21.2%** | 78.8% | −0.012% | −21% | **−38.4%** | −0.86 |
| + adaptive time stop | 10.8% | 40.8% | −0.023% | −33% | −42.8% | −1.76 |
| trailing stop 1% instead | 11.8% | 12.5% | −0.029% | −40% | −52.1% | −1.89 |
| trailing stop 2% instead | 12.0% | 1.2% | −0.030% | −42% | −57.4% | −1.88 |

**The stop more than halves the drawdown and more than halves the loss** — from −80%
to −21%, −92.6% to −38.4%. As risk control it works. It just never crosses zero, and
every entry time and target tested has a negative mean with t between −0.80 and −4.09.

### Why: 0.5% is inside the noise, so the stop cuts risers, not collapses

**6.13% of individual SOXL minutes move ≥0.5%** (1.0%: 0.86%; 2.0%: 0.06%). A 0.5%
trailing stop is therefore triggered by ordinary one-minute chop. Adding it drops the
target hit rate from **80.0% to 21.2%** — it kills three of every four trades that
would have reached +1%, before the rise can develop.

The economics, by exit reason:

| exit | n | share | mean | contribution |
|---|---|---|---|---|
| target | 178 | 10.8% | +0.980% | **+174.4 pp** |
| **stop** | 675 | 40.8% | **−0.520%** | **−351.0 pp** |
| time | 800 | 48.4% | +0.173% | +138.5 pp |

Losing 0.52% on 40.8% of trades costs more than winning 0.98% on 10.8% earns. To break
even the target would need roughly double its hit rate, or the stop half its frequency
— and those move together.

### The adaptive time stop has a bias built into its estimator

The trailing-6-month median chose **1 minute**, range 1–30. That is not a bug in the
code; it is what the definition produces. Minutes-to-target is measured *only on
trades that hit the target*, and conditioning on hitting selects fast moves — the
median winner takes 1 minute. Using the winners' median as a waiting time therefore
**systematically cuts off the slower winners**. Fixed 5/15/60-minute limits all give
the same result (−21%, −20%, −21%), because the 0.5% stop fires first regardless.

### The full grid: 200 configurations

5 entry times × 4 targets × 5 stops × (bell | overnight):

| best by total | n | hit | mean | total | t |
|---|---|---|---|---|---|
| 15:30, +2.0% / −5.0%, **overnight** | 1,641 | 10.1% | 0.237% | +1,239% | 2.43 |
| 11:00, +3.0% / −3.0%, **overnight** | 1,653 | 27.0% | 0.187% | +1,080% | 2.76 |
| 15:00, +0.5% / −5.0%, **overnight** | 1,641 | 68.6% | 0.156% | +779% | 2.96 |
| *worst:* 09:30, +2.0% / −5.0% | 1,653 | 57.4% | −0.107% | −91% | −1.59 |

71 of 200 are positive; 13 have t > 2, against ~10 expected by chance at that width.

**Every top configuration holds overnight, and every one uses a stop so wide it almost
never fires.** The winners are the settings that switch the bracket *off* and let the
overnight leg run. Conversely the 09:30 entries — where the bracket has the whole
session to work — are the worst in the grid.

### What this says about the idea

The reasoning behind it is sound and the instinct to cut before a collapse is the
right one; it runs into a specific empirical fact rather than a logical error. At 0.5%
on SOXL **you cannot distinguish a riser from noise**, so a stop at that distance
spends its time cutting the winners it was meant to protect. Widening it to where it
only catches real collapses (2–5%) means it essentially never fires, and what is left
is the overnight hold with a decorative bracket attached.

The bracket's genuine contribution is drawdown: −92.6% → −38.4% at 09:30, and the
overnight configs keep most of their return while capping the tail. That is worth
having as **risk management on a position held for another reason**. It is not an
entry edge, and no setting in 200 made it one.

## What stop width actually works with a +1% target — intraday only

The previous section drifted into overnight holds, which is not the rule as
specified. `floor_sweep.py` tests it as stated: enter, exit at +1%, **or** on a dip
below a floor, **or** after N minutes — whichever is sooner, **no overnight hold.**

The time stop is set from the duration this lab already measured for an upswing
before it retreats (4 minutes at 1%/0.25%, 6 at 2%/0.5%) rather than the
median-time-to-target estimator, which conditions on winners and degenerates to 1
minute.

### The answer: none of them, and tighter is less bad

Enter 09:30, +1% target, fixed floor, 4-minute time stop:

| floor | target hit | stopped | mean | total | max DD |
|---|---|---|---|---|---|
| **0.25%** | 18.3% | 77.0% | **−0.011%** | **−18%** | **−30.1%** |
| 0.50% | 26.0% | 60.0% | −0.022% | −33% | −48.4% |
| 1.00% | 32.5% | 34.8% | −0.033% | −45% | −58.0% |
| 3.00% | 34.7% | 2.5% | −0.042% | −54% | −67.9% |
| 5.00% | 34.7% | 0.2% | −0.041% | −54% | −68.1% |

The full 8×8 matrix of floor width × time stop is **negative in all 64 cells**, from
−0.8 bp to −6.7 bp per trade:

| floor | 2m | 4m | 6m | 15m | 60m | 390m |
|---|---|---|---|---|---|---|
| **0.25%** | −0.9 | −1.1 | −1.0 | −0.9 | −0.8 | −0.8 |
| 0.50% | −2.4 | −2.2 | −2.0 | −1.8 | −1.9 | −2.0 |
| 1.00% | −3.2 | −3.3 | −4.1 | −3.5 | −3.7 | −3.8 |
| 3.00% | −4.3 | −4.2 | −4.9 | −3.5 | −4.5 | −5.0 |

**Tighter is monotonically less bad**, and the reason is not that the stop works. A
tighter floor cuts the position sooner, so it spends less time exposed to a zero-mean,
high-variance process. Less exposure, less loss. That is the ½σ² penalty showing up
again — you are minimising a fee, not capturing an edge.

### Across every entry time: 1,024 configurations

8 entry times × 8 floor widths × 8 time stops × (fixed | trailing):

| best by total | n | hit% | stopped% | mean | total | max DD | t |
|---|---|---|---|---|---|---|---|
| 10:00, 0.25% trailing, 10m | 1,653 | 6.4% | **93.5%** | +0.018% | **+34%** | −16.2% | 2.05 |
| 10:00, 0.25% trailing, 6m | 1,653 | 6.0% | 92.8% | +0.018% | +32% | −16.3% | 1.97 |

* **38 of 1,024 positive (4%).**
* **5 with t > 2, against about 26 expected by chance at that width.** There are
  *fewer* significant results than random data would produce.

And the single best of the 1,024 does not survive one extra basis point:

| bps/side | mean/trade | total | t |
|---|---|---|---|
| 0.5 | 2.8 bp | +58% | 3.16 |
| **1.0** | **1.8 bp** | **+34%** | **2.05** |
| 1.5 | 0.8 bp | +14% | 0.94 |
| **2.0** | **−0.2 bp** | **−4%** | −0.18 |

251 trades a year, each crossing twice. The whole edge is 1.8 bp per trade; two bps
per side erases it. And its profile — 6.4% of trades reaching the target, 93.5%
stopped — is not "catching risers." It is being stopped out nine times in ten and
losing slightly less than the alternatives.

### The direct answer

**There is no stop width that makes a +1% intraday target profitable on SOXL.** The
best of 1,024 tested configurations returns +34% over 6.6 years against buy-and-hold's
+542%, sits inside the count expected from chance, and dies at 2 bps per side.

The reason is the same one measured throughout: intraday SOXL has a **positive
arithmetic mean (+21.4%/yr) and a negative geometric one (−17.9%/yr)**, the gap being
39%/yr of variance drag. Exit rules redistribute a zero-mean distribution; they cannot
add to its mean. Narrowing the floor reduces how much of the drag you pay, which is
why 0.25% wins — but paying less of a fee is not the same as earning a return.

## Limitations

* **Regular hours only.** The file is 09:30–15:59; there is no pre/post-market data.
  A retreat that truly occurred at 16:30 is recorded at the next open, so the
  "spans a close" counts are an upper bound on *market-hours* duration and the
  overnight/weekend split is a statement about the RTH session grid. **This caveat
  binds hardest at 5%/2%**, where 22.7% of episodes span a close and 24 cross two or
  more — nearly a quarter of the answer depends on hours this file cannot see, against
  1.8% at 1%/0.25%.
* **Trades, not quotes**, and closes are bar-end marks — no bid/ask, so nothing here
  is net of spread or slippage. That matters most at 0.25%: a threshold roughly two
  ticks wide on a $100 stock is inside the round-trip cost of acting on it.
* The anchor is a *running trough with no minimum dwell*, so an upswing off a
  one-minute spike low counts the same as one off a multi-day base. That is the
  question as posed; a swing-confirmation filter would cut the episode count and
  lengthen the median.
* Episode boundaries are sequential and non-overlapping: a new upswing is only hunted
  after the prior episode's retreat completes. At the wide pairs this materially
  reduces the count — at 5%/2% the tape spends a large share of its time inside an
  open episode, so 1,518 is "how many fit end-to-end", not "how many 5% upswings
  occurred".

## Correctness

`verify.py` re-derives every claim in every ledger straight from `SOXL_1min.csv`
without reusing the state machine — ordering, ledger prices against the file, the
trigger clearing the threshold *and being the first such bar*, the anchor being the
true running trough, the peak being the true running max, the retreat clearing its
threshold *and being the first breach*, both legs summing to the total, market/wall
minutes against the grid, the span labels against the actual dates, and non-overlap.
**1,518 / 1,518, 2,197 / 2,197, 3,575 / 3,575, 7,014 / 7,014 and 18,166 / 18,166
pass, 0 failures.**

That check earned its keep. The first engine tested thresholds in floating point and
silently dropped **9 genuine triggers** sitting exactly on +2.000%: `14.00 * 1.02`
evaluates to `14.280000000000001`, so a real move to `14.28` failed `>=`. Every price
in both files is exactly 2 decimals, so the engine carries prices as **integer cents**
and thresholds as **integer basis points**, testing `px*10000 >= trough*(10000+up_bps)`
and `px*10000 <= peak*(10000−dn_bps)`. No tolerance, no boundary class of bug, and any
threshold pair expressible in bps stays exact.

## Output

Files are tagged `up<bps>_dn<bps>` — `up500_dn200` is 5%/2%, `up400_dn150` is 4%/1.5%,
`up300_dn100` is 3%/1%, `up200_dn50` is 2%/0.5%, `up100_dn25` is 1%/0.25%.

| file | what |
|---|---|
| `out/retreat_report_<tag>.txt` | full report — primary plus both sensitivities |
| `out/retreat_episodes_1min_<tag>.csv` | every episode: anchor/trigger/peak/retreat stamps and prices, both leg durations on both clocks, run-up, span label, gap flag |
| `out/retreat_episodes_1min_intrabar_<tag>.csv` | same for the intrabar variant |

`independence_check.py`, `tradeability.py`, `edge_test.py`, `protection_cost.py` and
`premium_selling.py`, `put_spread.py`, `collar.py`, `exit_rules.py`, `backtest.py` and `overnight.py` print to stdout and write nothing;
`backtest.py`, `overnight.py` and `intraday_short.py` take an optional cost in bps
per side; `intraday_short.py` also takes an annual borrow rate. `overnight_vol_filter.py` and
`intraday_vol_filter.py` and `take_profit.py` and `bracket.py` and `floor_sweep.py` and `scoreboard.py` and `walkforward.py` and `regime.py` and `sizing_and_hedge.py` and `regime_switch.py` take an optional cost in bps per
side; `regime_switch.py` and `skip_rule.py` and `skip_symmetric.py` also take capital and a position fraction; `skip_rule.py`
additionally takes the volatility percentile and skip threshold, and `sweep.py`
and `hwm.py` take a sweep fraction; `abs_threshold.py` takes a cost in bps per side (`hwm.py` also writes `out/weekly_hwm25_f20.csv`). `collar.py` needs cached extracts of both put and call prints at the
15:55 / 09:30 stamps. `protection_cost.py` needs the option files
(`git lfs pull --include="raw_data/SOXL_intraday_5m_exp_*.csv"`, ~4 GB) and a cached
extract of put prints at the 15:55 / 09:30 stamps. `independence_check.py` takes an optional lookback in bars; `tradeability.py`
takes an optional per-side cost in bps (`python3 retreat_lab/tradeability.py 5`).
