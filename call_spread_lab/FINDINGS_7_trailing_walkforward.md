# SOXL Part 7 — Trailing Stop, Walk-Forward Validated (is the edge real or fitted?)

Part 6 showed fixed profit-target harvesting (sell when up +X%) fails — it caps the
fat-tail winners. The **trailing stop** (let winners run, exit on a pullback at an
achievable stop level) looked like the one rule that beats close-harvesting, but the
+71% number picked the best arm/trail over the whole sample — in-sample cheating.
This tests it honestly, out-of-sample.

## Method (no peeking)

`run_walkforward.py`, 60-DTE strangle, 7.5% strikes, 15%/leg, 5% slippage:
* **Candidates:** EOD close-harvest + a 3×3 grid of trailing (arm ∈ {25,50,100%} ×
  trail ∈ {15,25,40%}).
* **Walk-forward:** split 2023-2026 into 6-month test windows. Before each window,
  pick the candidate with the best score on **all prior data only** (expanding
  train), then trade that pick through the window. Chain the windows into one
  out-of-sample equity curve. The portfolio is flat between windows, so the OOS
  result is if anything *penalized* by extra turnover (conservative).
* Two selection rules shown (best past **return**; best past **return/drawdown**),
  vs a **fixed** EOD baseline and a **fixed** trailing config, all under the same
  windowing.

## Result — the edge is REAL, not fitted

| approach (60 DTE, 2023–2026 OOS) | CAGR | max DD | end $ |
|---|--:|--:|--:|
| in-sample best (cheating: chosen with hindsight) | +99% | — | — |
| **walk-forward, return-selected (honest OOS)** | **+82%** | **−60%** | **$810k** |
| walk-forward, return/DD-selected (honest OOS) | +82% | −60% | $810k |
| fixed trailing a25%/t25% (no optimization) | +74% | −62% | $687k |
| **fixed EOD close-harvest (baseline)** | **+5%** | −54% | $118k |

**Three independent signs it is real, not curve-fit:**
1. **Small honesty tax.** Out-of-sample +82% vs in-sample +99% — the choice losing
   sight of the future costs ~17 points, not the whole edge.
2. **Stable selection.** The optimizer picked the *same* config, `arm 25% / trail
   15%`, in **7 of 8 windows** (one window picked arm 50%/trail 15%) — chosen from
   past data alone. A fitted mirage jumps around; this didn't.
3. **It works even with NO optimization.** A single fixed trailing config held the
   whole time returns **+74%** — the edge is trailing *itself*, not the parameter
   search. And it beats the EOD baseline (+5%) by ~70 points under identical
   windowing, across every OOS year (2023's low-vol grind included; the chart shows
   the trailing lines above the baseline throughout, not only in the 2026 melt-up).

**Why:** the trailing stop keeps SOXL's fat-tail runners (a leg that goes +300%
rides until it pulls back), which fixed harvesting throws away at +50%. On a 3×
ETF whose whole edge is the tail, keeping the tail is the thing.

## The honest caveats (this is aggressive, not a free lunch)

* **Drawdown is brutal: −60%.** This is a high-variance strategy — you must be able
  to sit through halving your account. The EOD baseline's drawdown (−54%) is nearly
  as deep for far less return, but −60% is a real "can you stomach it" number.
* **One instrument, ~3.5 OOS years, fat-tail-amplified.** The final surge rides
  2026's (confirmed-real) melt-up; strip that and the CAGR is lower. The edge is
  present in 2023–2025 too, but the level leans on SOXL's fat regimes. No
  cross-ticker validation yet — TQQQ (already in the repo) is the obvious next check.
* **Daily-resolution stop.** The peak ratchets on the daily high and the exit
  triggers on the daily low, filling at the stop level (achievable). A true 5-min
  trailing stop could differ modestly; the fill model is realistic, the timing is
  daily.
* Fractional sizing (15%/leg) is still mandatory; "invest 100%" remains ruin.

## Bottom line

**The trailing stop is the first robustly out-of-sample edge in the project.** A
60-DTE long strangle, trailing each leg once it's up ~25% and exiting on a ~15–25%
pullback, delivered **+82% CAGR out-of-sample** (vs +5% for close-harvesting) —
validated by walk-forward, stable in its parameter choice, and present even without
any optimization. The price of admission is a **~60% drawdown** and a return level
that leans on SOXL's fat-tail regimes. Real edge, aggressive risk.

## Why 60 DTE, and what about 90–180? (`run_tenor_coverage.py`)

60 DTE was not eliminated-by-fiat for the others — but the tenor choice is
entangled with a data limit, so here is the honest picture.

**Data limit:** the intraday 5-min option files start only **~50 days before
expiry** (median lookback 50d; 25th–75th 43–50d). So the trailing signal can see:
~100% of a 30-DTE hold, ~83% of 60 DTE, ~56% of 90, **~42% of 120, ~28% of 180.**
Long-tenor holds are *unmanaged early* (the stop can't operate before the data
starts) — though the leg still gets trailed in its final ~50 days, so trailing
exits still fire on ~70–77% of legs at every tenor.

**Tenor result (EOD close-harvest vs trailing arm25%/trail15%, 2022–2026):**

| DTE | EOD CAGR | trailing CAGR |
|--:|--:|--:|
| 30 | −15% | **+163%** |
| 45 | +23% | +89% |
| 60 | +15% | +99% |
| 90 | +2% | +15% |
| 120 | +44% | +44% (tie) |
| 150 | +17% | +1% |
| 180 | −0% | +15% |

**Read:** the trailing edge is a **short-tenor phenomenon** — huge at 30–60 DTE,
gone by ~120 DTE (ties EOD), slightly negative at 150. Two reasons, both real: (a)
long holds are **data-handicapped** (only ~30–40% covered), and (b) **structurally**
the 120-DTE *EOD* harvest is already the sweet spot (+44%), leaving little for a
stop to add — trailing's spike-capture pays most on shorter, higher-gamma legs.
So the two approaches want *different* tenors: **EOD → 120–150 DTE; trailing →
30–60 DTE.** Caveat: only **60 DTE is walk-forward-validated**; the 30-DTE +163% is
a single in-sample config on spiky short-dated options and is almost certainly more
fragile — do not take that magnitude at face value.

## Reproduce

```bash
git lfs pull --include="raw_data/SOXL_intraday_5m_exp_*.csv"
cd call_spread_lab
python3 run_harvest_points.py   # builds the real hi/lo/close cache (first run)
python3 run_walkforward.py      # out-of-sample walk-forward + plot
python3 run_tenor_coverage.py   # intraday coverage + EOD-vs-trailing by tenor
```
