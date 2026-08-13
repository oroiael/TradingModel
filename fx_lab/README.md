# fx_lab — porting the band_lab churn harvester to currencies

Status: **data acquisition only.** Nothing here is a strategy, a backtest, or a
result. It exists to get the right currency data, in this repository's format,
and to answer one prior question honestly: *is the band_lab mechanism even
applicable to FX, and at what cost?*

Adoption of anything would require the full protocol band_lab uses — a
prespecified plan, walk-forward with prior-years-only selection, plateau
support, mechanism attribution. See `band_lab/v2_dev/RESEARCH_AGENT_PRD.md`.

| file | does |
|---|---|
| [`fetch_fx_intraday.py`](fetch_fx_intraday.py) | 5 years of intraday FX bars from IBKR, resumable |
| [`fx_profile.py`](fx_profile.py) | integrity check, then the band_lab-comparable transfer profile |
| [`tests/`](tests/) | 68 offline tests — no broker needed |

```bash
python3 fx_lab/fetch_fx_intraday.py --probe          # how deep does IBKR go?
python3 fx_lab/fetch_fx_intraday.py --dry-run        # how long will this take?
python3 fx_lab/fetch_fx_intraday.py --preset core --duration "1 W"
python3 fx_lab/fx_profile.py --check
python3 fx_lab/fx_profile.py
python3 -m pytest fx_lab/tests -q
```

---

## 1. What band_lab's edge actually is

Worth being precise, because it determines what can port. From
`STRATEGY_SPEC.md` §V2, the audit's central finding:

> **instant re-entry below the standing session high is worth +47.9 bp/day of
> the core's 65.6.** The strategy is properly described as "on gated days, stay
> long below the session high in +1% increments, with the 2-stop breaker as the
> escape hatch" — the 1% dip is the cadence, not the edge.

So the machine has four load-bearing parts:

1. **A session-anchored ratchet.** The rolling *session* high is the anchor, and
   V2 tested the alternatives to destruction: windowed highs, VWAP references,
   prior-close and reset-after-exit anchors were all rejected, monotonically —
   the more an anchor forgets the session high, the worse it does.
2. **Dense mean-reverting churn.** 15 completed ≥1% swings per day, never a
   zero-swing day in six years. The +1% target is calibrated to that count.
3. **A volatility gate that selects *for* churn.** ATR5 ≥ 6%: quartile-1 days
   lose 9 bp, quartile-4 days make 51 bp. "Churn income and vol bursts are the
   same phenomenon."
4. **Gap neutrality, deliberately paid for.** Flat at the close costs 17–26
   bp/day of measured overnight edge (V6) and buys a −8.0% worst day instead of
   −13.6%.

And one hard-won caveat that governs everything below — `STRATEGY_SPEC.md` §0.2:
roughly **half** the original 5-minute edge was an artifact of fills the bar
size could not resolve. 65.6 bp/day became 42.5 on 1-minute data.

### How each part fares on FX

| part | verdict on currencies |
|---|---|
| session-anchored ratchet | **undefined.** Spot FX trades Sunday 17:00 → Friday 17:00 ET continuously. There is no open, so no session high, no OR30, no "11:00". V2/V5/V9 have no anchor until one is chosen — this is the first thing to settle, not a detail |
| dense churn | **must be measured, not assumed.** `fx_profile.py` counts completed swings at the scaled depth with band_lab's own `zigzag_legs` |
| vol gate | **ports cleanly.** ATR5 is scale-free once expressed in percentiles; the script reports the cutoff that reproduces band_lab's 52% ON-rate |
| gap neutrality | **free.** This is FX's one structural gift: a 24-hour market has no overnight gap to be neutral to, so the 17–26 bp/day V6 pays for flatness is not owed. Intraday spot also incurs no financing |

## 2. The measured problem: FX is 7–20× quieter

`etf_scaling_test.py` already defines the transfer protocol — scale parameters
by `k = median daily range / 6.67%`. Measured on IBKR daily MidPoint bars,
2026-05-17 → 2026-08-12 (64 sessions, a window that includes a sharp JPY move):

| pair | median day range | k | dip/target becomes | stop becomes |
|---|---:|---:|---:|---:|
| USDZAR | 0.92% | 0.137 | **13.7 bp** | 0.55% |
| USDMXN | 0.55% | 0.083 | 8.3 bp | 0.33% |
| GBPJPY | 0.46% | 0.068 | 6.8 bp | 0.27% |
| EURUSD | 0.45% | 0.067 | 6.7 bp | 0.27% |
| USDJPY | 0.34% | 0.051 | 5.1 bp | 0.20% |
| **SOXL** | **6.67%** | **1.000** | **100 bp** | **4.00%** |

Every awkward decision in this lab follows from that right-hand column. Three
consequences:

**Leverage is mandatory, and it is roughly neutral.** Unlevered, band_lab's
42.5 bp/ON-day scales to ~2.8 bp on EURUSD. Recovering the original figure needs
~15× leverage — which IDEALPRO margin permits on majors — and at 15× the scaled
0.27% stop becomes ~4% of equity, i.e. band_lab's −4% stop. **FX spot at ~15×
is approximately a synthetic 3× ETF**, in return *and* in risk. Nothing is
gained or hidden by the leverage; it just restores the scale.

**Costs do not scale away.** Commission and spread are both proportional to
notional, so cost-as-a-fraction-of-target is leverage-invariant. On measured
IDEALPRO majors it lands near **8% of gross target** (0.2 bp spread + ~0.4 bp
round-trip commission against a 6.7 bp target) versus 1–2% for SOXL. Survivable,
but it is a five-fold worse ratio and it must be measured per pair, not assumed
— which is why the fetcher captures BID and ASK by default. EM pairs look
better in this table only because their targets are wider; their spreads are
also far wider, and only a real capture will say which way that nets out.

**Fill resolution gets worse, not better.** A 1-minute EURUSD bar's own range is
a substantial fraction of a 6.7 bp target, so a single bar can straddle entry
and target — precisely the defect that halved band_lab's estimate. At 5-minute
resolution the FX numbers would be meaningless. `fx_profile.py` reports
`bar_range_vs_target_%` for exactly this; above ~30%, 1-minute bars are not
enough and the study needs 30-second bars (capped at 6 months of history) or
tick data.

## 3. Which instruments, and what IBKR will actually serve

Verified from `TWS API/TWS Documentation - Copy Paste from Online.pdf` p.62,
"Unavailable Historical Data". IBKR's web docs are unreachable from here, so
anything else is marked ASSUMPTION at its use site.

| instrument | 5-year intraday from IBKR? |
|---|---|
| **Spot FX** (CASH/IDEALPRO) | **yes** — the only FX instrument with real depth. `--probe` measures it rather than trusting it |
| FX futures (6E, 6J, 6B…) | **no, not as a stitched series.** "Expired futures data older than two years counting from the future's expiration date" is unavailable. `--futures` requests CONTFUT instead; whether CONTFUT reaches 5 years at 1-minute is exactly what `--probe` is for |
| **FX futures options** | **no, at any age.** "Expired options, FOPs, warrants and structured products" have no historical data. Currency futures options cannot be backtested from this broker at all — that needs a vendor (the repo's existing ThetaData credentials, or CME DataMine). This is why the script has no FOP mode |
| bars ≤ 30 seconds | 6 months only |

So the answer to "pairs and/or their futures options" is: **spot pairs, because
the futures-options history does not exist here.** If the options overlay is the
real interest, the blocker is data procurement, not strategy code, and it should
be priced before anything else is built.

### The recommended first pull — `--preset core`

`USDZAR USDMXN GBPJPY EURUSD USDJPY`

Chosen to make the transfer question falsifiable rather than to look good:

- **USDZAR and USDMXN** have the highest k of the liquid pairs — the largest
  scaled target, so the best cost ratio *if* their spreads cooperate. They are
  the most likely to work and the most likely to be killed by spread. Both
  also carry event risk a churn strategy may not survive (interventions,
  sovereign headlines), which the −4k% stop has to absorb.
- **GBPJPY** is the highest-range major cross, and yen crosses are where the
  2024–2026 vol has actually been.
- **EURUSD and USDJPY** are the liquidity/cost control: the tightest spreads
  and lowest k. If the edge survives on USDZAR but not EURUSD, the difference
  is vol, not mechanism. If it survives on neither, that is the answer.

Other presets: `majors`, `crosses`, `em`.

## 4. Design decisions in the fetcher that differ from the existing scripts

`band_lab/live/fetch_1min.py` and `fas_1min_fetch.py` are the ancestors of this
script and it reuses their proven merge/resume core. Four deliberate departures:

1. **`useRTH=False` by default.** The FX session anchor is an open research
   question (§1), and 24-hour data is a superset — any session can be sliced out
   later, an RTH-only capture cannot be un-done. `fx_profile.py` scores four
   candidate anchors: `ny` (09:30–16:00 ET, band_lab-identical, 390 bars),
   `fx` (17:00–17:00 ET, IBKR's own FX day), `london`, `overlap`.
2. **`formatDate=2`.** Verified in `ib_async/util.py:parseIBDatetime`: this
   returns a tz-aware **UTC** datetime, which the script converts to New York
   explicitly. The older scripts use `formatDate=1`, which returns *naive local
   time in the TWS login timezone* — correct only while TWS is set to New York,
   and silently wrong otherwise.
3. **`--probe` before the bulk fetch.** `reqHeadTimeStamp` reports the earliest
   data IBKR will serve per symbol *and per whatToShow*. band_lab's fetcher
   could only discover a depth shortfall after hours of requests.
4. **BID and ASK captured alongside MIDPOINT.** At a 5–14 bp target, an
   unmeasured spread is the difference between an edge and a rounding error.
   IBKR's own sample uses MIDPOINT for every FX historical request
   (`TWS API/samples/Python/Testbed/Program.py` lines 1065–1071), and MIDPOINT
   alone makes cost unknowable. `BID_ASK` is accepted but discouraged: it costs
   double against pacing and returns a different bar shape that `bars_to_frame`
   would mislabel as OHLC.

### Pacing and runtime

Verified limits (docs p.62): no more than 60 historical requests per ten
minutes; no identical request within 15 seconds; no 6+ requests for the same
contract/exchange/tick-type within 2 seconds; **BID_ASK counts twice**. A
sequential loop at 10.5 s/request satisfies all of them.

That makes runtime the binding constraint, so `--dry-run` prints it:

| job | requests | wall clock |
|---|---:|---:|
| core preset, 3 series, `1 D` chunks | 27,405 | ~68 h |
| core preset, MIDPOINT only, `1 W` chunks | 1,305 | ~3.8 h |
| one pair, MIDPOINT, `1 W` chunks | 261 | ~46 min |

Two things cut it down. Windows lying entirely inside the weekend closure are
skipped without a request (~1 in 7 at daily chunking, conservative by
construction — any overlap with an open market is still requested, and a
five-year exhaustive test asserts no open window is ever skipped). And
`--duration "1 W"` is ~6× fewer requests; because larger durations are not
documented as safe, the run **verifies** the chosen duration against a `1 D`
pull bar-for-bar before using it, and falls back automatically if they disagree.

## 5. Output

`fx_lab/data/<PAIR>_1min.csv` (MIDPOINT), plus `_BID.csv` / `_ASK.csv`. Format is
byte-identical to `SOXL_1min.csv`, so band_lab's own loaders read it unchanged:

```
Date,Open,High,Low,Close,Volume
20260615 09:30:00 America/New_York,1.15234,1.15241,1.15228,1.15236,-1.0
```

`Volume` is `-1` for spot FX and that is correct — IBKR has no consolidated
trade tape for CASH. `fx_profile.py --check` reports it rather than pretending
otherwise. Anything in band_lab that filters or weights by volume cannot be
ported to spot; the futures path is the only one with real volume.

`fx_lab/data/` is gitignored (a 5-year 1-minute 24-hour capture is ~100 MB per
file). Summary tables in `fx_lab/out/` are committed, matching how the other
labs handle bulky-but-regenerable data.

## 6. Open questions, in the order they should be answered

1. **What is a session?** Run the profile across all four anchors and compare
   churn-per-unit-spread. Until this is settled, V2, V5 and V9 cannot be
   evaluated at all. This is a V-numbered program in its own right.
2. **Is 1-minute resolution sufficient?** Read `bar_range_vs_target_%`. If it
   is above ~30%, no backtest on these bars is trustworthy and the honest next
   step is 30-second bars (6 months) or tick data, not a grid search.
3. **Does the churn exist at the scaled depth?** `swings_mean` against SOXL's
   15. If FX shows 3, the +1%-equivalent target is mis-calibrated and V3 needs
   re-deriving from the FX swing distribution rather than inherited.
4. **What does the spread actually cost, per pair and per session bucket?**
   From the BID/ASK captures. EM pairs are the ones at risk here.
5. **Only then**: does the mechanism transfer? Run `transfer_test.py`-style
   locked rules and `etf_scaling_test.py`-style scaled cells, with the same
   adoption bar written before the run.

A note on that last point, from `v2_dev`'s V16 finding: **walk-forward is not
protective against a bias present in every year.** The rejected V16 winner beat
the incumbent out-of-sample in 5 of 5 held-out years. If FX fills are
systematically optimistic at 1-minute resolution, every fold will agree and
every fold will be wrong. Question 2 is not optional groundwork — it gates
whether questions 3–5 can be answered at all.
