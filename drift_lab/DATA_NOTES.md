# Drift study — data provenance, quality, and semantics

Everything below was measured from the files, not assumed. Where a field is
unreliable or missing, it is stated. Reproduce with `drift_lab/verify_data.py`.

## Files used

| role | file(s) | what it is |
|---|---|---|
| underlying | `SOXL_5min_6Years.csv` | 5-min OHLCV, 2020-07-16 → 2026-07-21 |
| options | `raw_data/SOXL_intraday_5m_exp_<EXP>_<YYYY>_<SEG>.csv` (664 files) | 5-min option TRADE aggregates by expiration |

Both are Git LFS objects (`git lfs pull` required). The many other CSVs in the
repo are prior backtests, not raw data.

## Underlying — `SOXL_5min_6Years.csv`

* 117,348 bars, 1,510 sessions. Columns `Date,Open,High,Low,Close,Volume` (ET).
* **78 bars/session, 09:30 → 15:55** (the 16:00 stamp is not present). 12 early-close
  half-days carry 42 bars (→12:55). **Zero intraday gaps** — the grid is complete.
* 27 zero-volume bars; no NaNs; no non-positive prices.
* **One split: 15:1 on 2021-03-02** (overnight 636.49 → 42.99, ratio 0.068). The
  series is **raw / not back-adjusted**, but the split is the *only* basis break and
  it is **before the option data starts**, so across the entire 2022–2026 option
  window the underlying sits on one consistent basis. No split inside 2022–2026.
* 2026 is real, current-year data through 07-21. SOXL (3× semis) ran ~$46 → ~$300
  → ~$158 in H1-2026; the path is smooth (no bar-to-bar or overnight jumps), i.e.
  internally consistent. Flagging the magnitude only so it can be cross-checked
  against your source — it is not a data error we can see.

## Options — `raw_data/SOXL_intraday_5m_exp_*.csv`

* **664 files, 246 distinct expirations, 2022–2026** (~140 expirations/yr; 2026
  partial at 99 files / 38 expirations). 1–9 capture-segment files per expiration.
* Columns `symbol,expiration,strike,right,timestamp,open,high,low,close,volume,count,vwap`.
  Polygon-style 5-min **TRADE aggregates — NOT bid/ask quotes.**
* **79 bars/session, 09:30 → 16:00** (one more than the underlying — see join note).
* Strikes are whole + half dollars, ~48–75 per expiration, and **bracket the
  underlying**: the at-the-money strike sits within pennies of spot at every
  timestamp (median |K−S| of the traded ATM strike = 0.00), confirming options and
  underlying share the same price basis.

### Field semantics — verified, and where they bite

* **`count` > 0 ⇔ `volume` > 0**, exactly. This is the reliable **trade flag**
  (a print occurred in that 5-min bar). `count` = number of trades.
* **`close`** (and O/H/L) is present on **95.8% of trade bars**; when present, OHLC
  is **100% internally consistent** (low ≤ open,close ≤ high). This is the reliable
  **price** field.
* **`vwap` is NOT trustworthy as a per-bar price.** It is **carried forward verbatim
  on no-trade bars (100.0% of the time)** and, on thin (count 1–2) trade bars, it
  frequently sits **outside the bar's own [low, high]** — in-range only **20.5%** of
  trade bars. It is a held "last value," not a clean bar VWAP.
  → **This study uses `close` for price and ignores `vwap`.** (A first pass that used
  `vwap` produced spurious "no-move" episodes; switching to `close` raised
  direction-coherence from 84% to 93%.)
* No-trade bar = `count=volume=0`, OHLC empty, `vwap` = carried last value.

### Underlying ⇄ option join

* Option timestamps match the underlying grid exactly **except the 16:00 bar** (35 of
  2,765 distinct stamps per expiration), which has no underlying bar because the
  underlying stops at 15:55. We map option 16:00 → the same-day 15:55 underlying
  close. Everything else is an exact 5-min join.

## Coverage envelope (what the option data can and cannot see)

* Intraday option history reaches back only a limited window before each expiration
  (mostly the final ~1–3 capture-months), so a given expiration's early, far-DTE life
  is sparsely traded, while its final week is dense. **"By expiration" therefore
  largely reflects which slice of each contract's life was captured; the clean axis
  is DTE, which we use throughout.**
* These are **trades, not quotes**, at **5-minute** resolution. Consequences for the
  analysis are stated in `FINDINGS_drift.md` (§ Limitations) — most importantly, a
  "stale" mark means the last *trade* is old, which is not the same as the market's
  *quote* failing to move.
