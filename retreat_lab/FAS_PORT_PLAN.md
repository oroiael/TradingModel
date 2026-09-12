# Porting the SOXL analysis to FAS — data confirmation and priority order

## The data, confirmed

`FAS_1min.csv` came from `origin/data/fas-1min` (commit `7f7a9f0`, "Add FAS
1-minute RTH base, 2019-12-31 onward"), Git LFS oid
`5a0ec5d275adee0bb3f34907ea4bc4afaf4eee9b694e4171cacc23dff49669b3`. It is added
here at that identical oid, so no second copy of the object exists.

`fas_1min_verify.py` passes clean:

| check | result |
|---|---|
| rows / sessions | 653,040 / 1,680 — **27 sessions more than `SOXL_1min.csv`** |
| span | 2019-12-31 → **2026-09-08** (SOXL stops 2026-07-30) |
| session grid | 1,668 full @ 390 bars, 12 half-days @ 210; 09:30 → 15:59 |
| hygiene | 0 duplicates, 0 NaN, 0 non-positive, 0 OHLC violations |
| cross-check vs `FAS_5min_6Years.csv` | 117,036 bars, median return diff 0.0000 bp, 0 bars off >25 bp |
| decimals | **≤2 throughout** — the integer-cent engine ports unchanged |

Two defects, both load-bearing:

- **11.57% zero-volume bars** against SOXL's 1.26%
- **median $97,610 dollar volume per minute bar** against SOXL's $2,247,162 —
  **23× thinner**

## The two facts that set the order

**The central SOXL result replicates at about a third the size.**

| | FAS | SOXL |
|---|---|---|
| buy & hold | +87.2% (9.8%/yr) | +541% (32.6%/yr) |
| overnight only | +214.5% (18.7%/yr) | +2,245% (61.5%/yr) |
| intraday only | −40.5% (−7.5%/yr) | −72.7% (−17.9%/yr) |
| daily σ | 69.4% ann | 116.4% ann |

**And costs eat it.** Unfiltered overnight, gross to net:

| bp/side | FAS CAGR | SOXL CAGR |
|---|---|---|
| 0 | 18.7% | 61.5% |
| 1 | 12.9% | 53.6% |
| 2 | **7.3%** | 46.1% |
| 5 | **−7.7%** | 25.7% |

FAS buy-and-hold is 9.8%/yr. **At 2 bp/side the unfiltered overnight strategy
already loses to buy-and-hold; at 5 bp it is negative.** SOXL had 28.9pp/yr of
headroom over B&H — FAS has 8.9pp gross and roughly none by 2 bp. On SOXL the
vol filter was an improvement; on FAS it is the only thing that could make the
trade exist, because it cut trade count 40%, which is the lever FAS needs.

Forced liquidation under a 3:1 portfolio-margin cap, breach at `r < (f−3)/2f`:

| | FAS nights breached | SOXL |
|---|---|---|
| f=1.5 (gap < −50%) | 0 | 0 |
| f=2.0 (gap < −25%) | **1** — 2020-03-16, −32.2% | 1 — 2020-03-16, −31.2% |
| f=2.5 (gap < −10%) | **9** | 31 |

FAS is safer at f=2.5, identical at f=2.0. The filtered backtests begin
2021-01-29 after burn-in, so March 2020 never appears in them — a blind spot,
not a clean bill of health.

## Priority order

**P0 — prerequisite.** 28 scripts hardcode `SOXL_1min.csv`. ~45 min, mechanical;
`verify.py` must still pass 5/5 on SOXL afterward. Fold into whichever item runs
first.

### Tier 1 — decides whether FAS is worth anything

| | test | script | decides | cost |
|---|---|---|---|---|
| **P1** | overnight-only with cost sensitivity | `overnight.py` | whether a trade exists after costs | ~2 min |
| **P2** | RV20 filter, in-sample **and** walk-forward together | `overnight_vol_filter.py` + `walkforward.py` | everything | ~10 min |
| **P3** | scoreboard on identical terms | `scoreboard.py` | go / no-go | ~5 min |

P1 reads only the 09:30 and 15:59 bars — the day's two most liquid minutes — so
FAS's thin tape barely touches it. Expect marginal-to-negative; run it to make
that formal.

P2 is also **a genuine out-of-sample test of the SOXL conclusion, possibly worth
more than the FAS answer.** SOXL's walk-forward found the effect tracks
*absolute* volatility, not relative — expanding-window absolute memory worked,
rolling-relative was worse than no filter. If that holds, FAS at 69.4% ann vol
sits almost entirely below SOXL's 107.6% cut, so a ported absolute threshold
keeps nearly every night and does nothing. If p60 on FAS's *own* distribution
works instead, the "it's absolute" conclusion is wrong and needs amending. Test
both parameterizations. Run in-sample and walk-forward together — the in-sample
version alone is not decision-grade.

### Tier 2 — only if P3 clears

- **P4** skip after a −3% / −4% day — `skip_rule.py`, `skip_symmetric.py`. Cheap
  and additive on SOXL, but another parameter fitted on a thinner edge.
- **P5** leverage and forced liquidation — re-derive, do not copy. Numbers above.
- **P6** cash sweep and high-water mark — `sweep.py`, `hwm.py`. Instrument-
  independent, ports as-is. Last: an overlay on an edge is pointless before the
  edge is established.

### Tier 3 — argued against

- **P7** the retreat-timing study itself — `retreat_timing.py`,
  `independence_check.py`, `tradeability.py`, `edge_test.py`. On SOXL it produced
  **no tradeable signal** (trigger t −1.1 to +1.0, mechanical trade −99%, worse
  than random entry). On FAS it is also contaminated: with 11.57% zero-volume
  bars a large share of episodes would trigger and retreat on synthetic prints.
  Needs a volume gate built first — new work, not a port.
- **P8** every intraday test — `bracket.py`, `take_profit.py`, `floor_sweep.py`,
  `intraday_short.py`, `intraday_vol_filter.py`. On SOXL all failed for a
  *structural* reason, variance drag, which applies to FAS unchanged (intraday
  geometric −7.5%/yr against a positive arithmetic mean); 1,024 bracket configs
  gave 5 significant results against 26 expected by chance. And these are exactly
  the tests that read intrabar highs and lows at the minute, where ~1 FAS bar in
  9 has no volume. If any, run **one** — the bracket grid with a liquidity gate —
  as a check on the drag argument, not as a strategy search.
- **P9 — BLOCKED, not deprioritized.** The five option structures
  (`protection_cost.py`, `premium_selling.py`, `put_spread.py`, `collar.py`).
  **No FAS option data exists in this repo** — 742 SOXL files, 5 TQQQ, 0 FAS.
  Data acquisition, not analysis. And on SOXL all five were priced through
  (mid-market overnight put ~6.6 bp against 16–33 bp to cross naked); FAS options
  are less liquid, so that result should be worse, not better.

## Recommendation

P1 + P2 as one job with P0 folded in — about an hour, and it answers the only
question that matters: whether FAS's overnight premium survives its own
transaction costs once the filter thins the trade count. The prior from the cost
table is that it is close, and the honest answer may be that FAS is a worse SOXL.
