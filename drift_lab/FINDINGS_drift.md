# SOXL 5-min options — measuring "drift": when the option print lags the underlying

**Scope.** Every 5-min bar of SOXL options against 5-min SOXL, 2022–2026: **246
expirations, 664 files, 3,300,568 measured drift episodes.** No estimates, no
Black-Scholes, no synthetic proxies — the numbers below are counted from trades.
Data provenance and quality are in `DATA_NOTES.md` (reproduce with `verify_data.py`).

---

## 1. The one-paragraph answer

Your "drift" is real and it is large, but it is almost entirely **stale trade
prints, not the option market failing to reprice.** In this data an option's
"price" is its **last trade**, and near-money-but-not-near-expiry strikes simply
**don't trade every 5 minutes** — so the last print sits still while SOXL moves,
then jumps to catch up when the option finally trades. That gap is what you're
seeing. It is governed almost entirely by **two axes — days-to-expiry (DTE) and
moneyness — and is remarkably stable across the 2022 crash, the 2023 calm, and the
2026 melt-up.** When the option *does* trade in consecutive bars it tracks the
underlying tightly (correct direction 94% of the time, ~4.5× elasticity), with only
a **small (~5–7%) genuine under-reaction that clears within one more 5-min bar.**
The big, hours-long "drifts" are a liquidity/marking artifact, not a tradable
mispricing — and proving whether any *tradable* repricing lag exists would need
**bid/ask quote data, which this dataset does not contain** (see §6).

---

## 2. Terminology — your word "drift", named properly

| your phrasing | standard term | what it is here |
|---|---|---|
| "the option doesn't keep up with the move" | **option–underlying lead-lag** (the underlying *leads*) | the general phenomenon |
| "the disparity" (last price vs where the underlying is) | **stale-mark / stale-price drift** | our primary, model-free measure |
| — caused by no trades | **non-trading staleness** | dominant driver (illiquidity) |
| — caused by the last print predating the bar | **non-synchronous trading** | most of the residual bar-to-bar lag |
| — caused by slow repricing | **under-reaction** | small, clears in ≤1 bar |
| "how much the option should move per underlying move" | **delta** ($), **elasticity / lambda Ω** (%) | measured ≈ **4.5×** near-ATM |
| actual price vs a fair value | **fair-value dislocation** | *not computed* — needs a model + IV (see §6) |

We deliberately measure the **model-free** quantity (stale-mark drift) and treat the
model-based one (dislocation vs Black-Scholes fair value) as an optional extension,
because it requires an implied-vol input this intraday file doesn't carry.

---

## 3. Method (pure data — reproducible)

For every `(expiration, strike, right)`, on its 5-min grid:

- **Trade flag** = `count > 0` (verified identical to `volume > 0`). **Price** =
  `close` (the bar's last trade). We **do not use `vwap`** — it is carried forward on
  no-trade bars and is unreliable on thin bars (in-range only ~20% of the time; see
  `DATA_NOTES.md`).
- The **mark** is the last trade price, carried forward until the next trade.
- A **stale-mark drift run** is the interval between two consecutive *priced* bars
  `i → j` **within one session** with a no-trade gap between them. We record:
  - **duration** = 5·(gap length) minutes — *how long the last print stayed stale*;
  - **underlying peak excursion** = max |Uₜ/Uᵢ − 1| over the run — *how far SOXL moved
    while the option was frozen*;
  - **catch-up jump** = C_j/C_i − 1 — *how far the option leapt when it finally traded*.
- A **drift episode** (the tradable kind) = a run where **SOXL actually moved ≥ 1%**
  while frozen. Everything in §4 is conditioned on that.

Segmented by **|moneyness| × DTE × right × year × expiration**. A second, independent
test (§5) regresses the option's return on the underlying's contemporaneous and
lagged return to separate genuine under-reaction from non-synchronous trading.

**What "reprice" means here:** time until the **next trade prints**. That is exactly
what your "option data" shows. It is *not* the time for a market-maker **quote** to
move (quotes aren't in this data) — a distinction that turns out to be the whole
interpretation (§6).

---

## 4. Results

### 4a. How OFTEN — trade frequency and stale-drift frequency (% of 5-min bars, pooled 2022–2026)

**Fraction of bars that actually trade** (fresh price) — the mirror image of staleness:

| \|moneyness\| \ DTE | 0-1 | 2-3 | 4-7 | 8-14 | 15-30 | 31-60 | 60+ |
|---|--:|--:|--:|--:|--:|--:|--:|
| **ATM <2%** | 80.8 | 78.5 | 68.6 | 43.5 | 21.0 | 14.3 | 14.4 |
| 2–5% | 67.7 | 64.1 | 56.2 | 33.7 | 15.8 | 11.1 | 11.2 |
| 5–10% | 53.6 | 53.6 | 48.2 | 28.8 | 13.9 | 10.0 | 9.4 |
| 10–20% | 33.2 | 36.7 | 35.0 | 22.6 | 12.7 | 9.6 | 8.5 |
| >20% | 12.3 | 14.2 | 13.8 | 10.5 | 8.2 | 7.8 | 6.2 |

**Fraction of bars in stale-drift** (last print stale **and** SOXL has since moved ≥1%):

| \|moneyness\| \ DTE | 0-1 | 2-3 | 4-7 | 8-14 | 15-30 | 31-60 | 60+ |
|---|--:|--:|--:|--:|--:|--:|--:|
| **ATM <2%** | **3.8** | 3.8 | 8.0 | 15.0 | 29.1 | 34.9 | 39.8 |
| 2–5% | 7.8 | 8.2 | 12.5 | 21.8 | 36.7 | 43.2 | 47.6 |
| 5–10% | 13.6 | 13.4 | 17.4 | 26.2 | 39.9 | 44.8 | 50.9 |
| 10–20% | 25.7 | 23.0 | 26.2 | 32.9 | 42.8 | 45.3 | 52.1 |
| >20% | 51.2 | 45.1 | 47.9 | 49.5 | 52.5 | 51.1 | 57.9 |

**Read it:** the near-money, near-expiry corner (top-left) barely drifts — an ATM
weekly in its last two days trades ~80% of bars and is stale-while-moving only ~4% of
the time. Drift **grows monotonically as you move out in time and out of the money**:
a 30–60-DTE ATM option is in stale-drift ~35% of all bars; deep-OTM strikes, half the
time. This is the single most important structural fact — **drift is a DTE × moneyness
(i.e. liquidity) surface, not a market-wide "slowness."**

### 4b. How LONG until it reprices — near-money (|mny|<5%), SOXL moved ≥1%

| segment | median | p75 | p90 | p99 | ≤5 min | ≤15 min | ≤30 min |
|---|--:|--:|--:|--:|--:|--:|--:|
| **all near-money** | **20** | 50 | 105 | 270 | 20% | 43% | 62% |
| 0–1 DTE | 10 | 25 | 50 | 145 | 38% | 67% | 83% |
| 2–7 DTE | 10 | 25 | 55 | ~190 | 35% | 64% | 81% |
| 8–14 DTE | 15 | 35 | 75 | 215 | 25% | 52% | 72% |
| 15–30 DTE | 25 | 60 | 115 | 265 | 15% | 37% | 57% |
| 31–60+ DTE | 35 | 75 | 140 | 300 | 13% | 31% | 50% |

(minutes). **Near expiry the option catches up fast (median 10 min, 83% within half an
hour); far from expiry it can stay stale for over an hour.** The tail is long (p99
≈ 4.5 h) but bounded by the session.

### 4c. How BIG — near-money, SOXL moved ≥1%

- **Underlying move while frozen:** median **1.6%**, p90 **3.6%**, p99 **7.9%**.
- **Option catch-up jump on the reprint:** median **6.2%**, p90 **18.3%**, p99 **45.2%**.
- **Elasticity Ω = |ΔC%| / |ΔS%|:** median **4.5×** (calls 4.6, puts 4.4) — the option
  moves ~4–5× the underlying's percentage, as expected for near-money 3× -ETF options.
- Catch-up size falls with DTE (median 15.5% at 0–1 DTE → 2.9% at 60+), tracking the
  gamma/elasticity of the leg, not any change in "how wrong" the mark was.
- **Material episodes** (near-money, SOXL ≥2% **and** frozen ≥15 min): **62,737**, i.e.
  **27.9%** of near-money drift episodes are both sizeable and durable.

See `out/drift_heatmaps.png` for 4a/4b/4c as one picture.

### 4d. By YEAR / regime — near-money, SOXL moved ≥1%

| year | episodes | median dur (min) | median SOXL move | median catch-up |
|---|--:|--:|--:|--:|
| 2022 (bear) | 47,488 | 20 | 1.7% | 6.7% |
| 2023 (calm) | 33,176 | 25 | 1.5% | 7.0% |
| 2024 | 53,803 | 25 | 1.5% | 6.9% |
| 2025 | 38,737 | 20 | 1.5% | 6.1% |
| 2026 (melt-up) | 51,635 | 25 | 1.9% | 4.4% |

**The drift signature barely moves across radically different tapes.** That stability
is itself the finding: this is microstructure/liquidity, not a regime effect. (2026's
smaller catch-up % is just the higher share price → lower percentage option leverage.)

---

## 5. Is any of it *genuine* under-reaction? (the lead-lag test)

When the option trades in **consecutive** 5-min bars we can ask whether its price lags
the underlying beyond mere non-trading. Pooled near-money OLS
`optionRet = α + β·underlyingRetₜ + c·underlyingRetₜ₋₁`:

| | n | contemporaneous β | **lag β** | lag / contemp |
|---|--:|--:|--:|--:|
| CALL (all) | 661,173 | 8.82 (t=467) | +1.224 (t=84) | **+13.9%** |
| PUT (all) | 455,661 | −9.25 (t=−382) | −1.690 (t=−89) | **+18.3%** |

So ~14–18% of the underlying's move shows up in the option only on the **next** bar —
highly significant. **But that is mostly an artifact, not slow repricing.** Two clean
tests:

- **Density split:** on **densely-traded** bars (≥5 trades in both bars, so the last
  print sits near the bar's close) the lag **collapses** — calls +26% → **+5.2%**,
  puts +30% → **+7.1%**. The lag lives in *thin* bars, i.e. it is **non-synchronous
  trading** (the last print predates the bar's close), not the market being slow.
- **Second lag ≈ 0:** the `t−2` coefficient is −1.4% to +1.2% (t≈0). Nothing persists
  beyond one bar.

**Conclusion:** genuine under-reaction is small (~5–7% of a move) and **fully resolved
within one additional 5-min bar**. There is no multi-bar momentum in option repricing
to harvest at this resolution. This is stable across all five years (calls +9%→+19%,
puts +12%→+24% before the density correction).

---

## 6. What this data **cannot** tell you — and what to get

Stated plainly, because it bounds every number above:

1. **These are trades, not quotes.** "Stale" means the **last trade** is old. It does
   **not** mean the market's **bid/ask** was stale — a market maker re-quotes
   continuously off the underlying via delta, with **no trade printing**. So the
   hours-long "drifts" in §4 are overwhelmingly *"nobody traded,"* not *"the option was
   mispriced and pickable."* **To measure true quote-repricing latency — and whether a
   tradable lag exists — you need the NBBO bid/ask quote stream** (e.g. Polygon
   options *quotes*, or OPRA). That is the single highest-value addition.
2. **5-minute resolution is a floor.** Real electronic option repricing is
   sub-second; at 5-min bars, genuine quote repricing is essentially always within one
   bar (§5 confirms it). Sub-5-min lead-lag is invisible here. **Trade-and-quote (TAQ)
   or 1-second data** would be required to see it.
3. **No implied-vol / greeks intraday.** We could not compute **fair-value
   dislocation** (traded price vs Black-Scholes value at the live underlying) because
   the intraday files carry no IV. An EOD greeks file exists
   (`SOXL_1Yr_Options_Greeks_EOD.csv`, ~186 MB, LFS) but it is **daily**, so it can
   only bound overnight dislocation, not intraday. **An intraday IV or NBBO feed** would
   let us build the model-referenced measure and directly test "is the traded price
   *wrong*," not just "is it *old*."
4. **Coverage is trade-window-limited.** Each expiration's early, far-DTE life is
   sparsely captured; the clean, unconfounded axis is **DTE** (used throughout), not
   calendar expiration date.
5. **`vwap` is unusable as price** (documented); we used `close`. If your source can
   re-export a true per-bar VWAP it would sharpen the thin-bar prices, but `close`
   is correct and sufficient for everything here.

If the goal is *"find option prints that lag the underlying and trade against them,"*
the honest verdict from this data is: **the lag is real but is stale-print/liquidity,
which you cannot reliably transact at the stale price — get quote data before assuming
an edge.** If the goal is *"characterize the drift for marking, execution-timing, or
risk,"* §4 is a complete, regime-stable answer.

---

## 7. Reproduce

```bash
git lfs pull --include="SOXL_5min_6Years.csv,raw_data/SOXL_intraday_5m_exp_*.csv"
python3 drift_lab/verify_data.py     # data-quality claims (DATA_NOTES.md)
python3 drift_lab/run_full.py        # all 246 expirations -> out/ (~3.5 min)
python3 drift_lab/report.py          # the tables in §4-5
python3 drift_lab/make_heatmaps.py   # out/drift_heatmaps.png
```

Outputs in `drift_lab/out/`: `episodes.parquet` (3.3 M rows), `per_expiration.csv`,
`coverage_by_year_mny_dte.csv`, `ANSWER_*.csv`, `leadlag_input.parquet`,
`drift_heatmaps.png`.
