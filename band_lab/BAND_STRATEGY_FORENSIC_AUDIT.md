# Band Strategy — Forensic Audit

**Prepared:** 2026-08-28
**Scope:** the SOXL/SOXS band ("churn harvester") strategy, from its research
programs through nine live paper sessions to its rejection.
**Audience:** whoever decides what happens next.
**Author's position:** I built or ran most of what is audited below. Where a
finding implicates my own work it is marked **[AUTHOR]**. That is a conflict and
the reader should weigh it.

---

# 1. Executive summary

The strategy was deployed to a paper account on 2026-08-03 and stopped on
2026-08-26 after losing **4.16%** over the clean measurement window. It was then
found to have **negative expected value on raw price data** — before commissions,
before spreads, before any simulator.

**The disqualifying evidence existed in this repository three days before
launch, correctly measured, correctly titled, and with correct
recommendations.** It was set aside by one unevidenced sentence.

`live/PHASE2_PARITY.md` finding S10, committed 2026-07-31, is titled *"two-thirds
of the measured edge rests on same-bar sequencing."* It contains this table:

```
  sleeve  fill model    bp/ON-day   Sharpe
  SOXL    spec              65.9     3.14     <- the published number
  SOXL    no_better         12.6     0.62
  SOXL    next_bar          21.4     1.18
  SOXS    spec              61.2     2.83     <- the published number
  SOXS    no_better          5.9     0.28
  SOXS    next_bar           2.2     0.12
```

S10's own recommendation #3 reads: *"Treat §8's baselines as an upper bound, not
as the null hypothesis... A live run at 20 bp/ON-day would be consistent with
this finding and is not, on its own, evidence that the engine is broken."*

That recommendation was not followed. The daily monitoring report was built to
compare live results against **65.6 / 61.9 / 57.7 / 48.1** — the upper bound —
and did so for every session of the live run.

**Losses were not caused by the trading engine.** The engine was audited during
the live run and found correct: nine consecutive flat closes, execution within
5.7 bp round trip of the quote, and a daily self-check that passed every
session. Four defects were found and fixed; none of them was material to P&L.

---

# 2. The failure chain

Six links. Removing any one of them prevents the loss.

**Link 1 — the simulator books an impossible fill.** Within a single bar the
engine resolves an exit and then re-enters at that bar's *opening* price, which
traded before the exit did. Documented in `replay.py`'s own source comments from
Stage 2 onward.

**Link 2 — the exposure is measured correctly (S10, 2026-07-31).** Range for
SOXL stated honestly as **13–66 bp/ON-day**, "not 62 ± noise." Recommendations
were: change no parameter, launch paper as the fastest test, treat §8 as an
upper bound.

**Link 3 — S11 narrows the range to its optimistic end, without evidence.** The
1-minute study, committed the same day, produced this:

```
  1-minute fill_bar   spec        SOXL 43.0    SOXS 39.8
  1-minute fill_bar   no_better   SOXL 12.6    SOXS -1.5
  1-minute fill_bar   next_bar    SOXL 17.3    SOXS  3.5
```

S11 then wrote: *"S10's range narrows sharply. SOXL goes from '13–66' to
**42–43**; SOXS from '2–61' to **34–40**. `no_better` and `next_bar` were too
pessimistic: real 1-minute paths do return below the price just sold, and most
of the same-bar re-entry edge is genuinely fillable."*

**This is the decision that caused the loss.** The claim that the harsh models
are "too pessimistic" is an assertion. It was not tested against a single real
fill. It discards the two rows that disagree and keeps the one that agrees with
the published number. **S11's own table shows SOXS at −1.5 bp under `no_better`
— negative, in the repository, three days before capital was committed.**

**Link 4 — the baseline file is never updated.** `monitoring_expectations.csv`
retained the 5-minute spec figures (65.6/61.9, 57.7/48.1) even though S11 had
just reduced the same quantity to 43.0/39.8. Every daily report compared live
against numbers the project's own most recent analysis had superseded.

**Link 5 — live trading begins 2026-08-03**, three days after S10 and S11.

**Link 6 — three weeks of live analysis measure against the wrong benchmark.**
**[AUTHOR]** I spent 2026-08-12 to 2026-08-26 explaining live underperformance
against a baseline S10 had explicitly said not to use, and did not read S10 until
2026-08-28.

---

# 3. Timeline

| date | event |
|---|---|
| 2026-07-28 | V1–V14 research programs run; parameters selected |
| 2026-07-31 | **S10 written** — the bias measured, range 13–66, §8 declared an upper bound |
| 2026-07-31 | **S11 written** — range re-narrowed to 42–43 on an untested assertion |
| 2026-08-03 | live paper trading begins; legacy 500-share SOXL position liquidated pre-market |
| 2026-08-06 | flatten fires three times against one position; account short 1,082 shares overnight |
| 2026-08-10 | 524 shares never flattened; carried overnight, dumped 04:00 next day |
| 2026-08-12 | **PR #40 merges 05:29 ET** — trading logic frozen, 85 min before the open |
| 2026-08-12 → 08-26 | nine sessions, all closing flat; four non-material defects found and fixed |
| 2026-08-26 | **V20** re-derives S10's result at 1-minute resolution |
| 2026-08-27 | dip/momentum censuses: negative expected value on raw prices |
| 2026-08-28 | **S10 read for the first time**; this audit |

---

# 4. Catalogue of every test

## 4.1 Original research programs (V1–V14), run 2026-07-28

**Audit status: NOT INDEPENDENTLY AUDITED.** I re-scored their *parameters* in
V21 but never reviewed their original methodology, code, or fill assumptions.
All of them ran on the `spec` fill model, i.e. on the bug.

| program | variable | values swept | outcome | audit note |
|---|---|---|---|---|
| V1 | entry dip % | adaptive vs fixed 1% | fixed retained | re-swept by V16, 672 cells, nothing adopted |
| V2 | entry anchor | session high vs windowed vs VWAP vs reset | session high retained | headline "+47.9 bp of the core's 65.6 from instant re-entry" — **this was the bug, measured and misread as the mechanism** |
| V3 | target % | adaptive vs fixed 1% | fixed retained | joint with V1 in V16 |
| V4 | stop % | — | 4% retained | |
| V5 | start time | 10:30 vs alternatives | moved to 11:00 | document concedes 10:30 was "derived, never tested" |
| V6 | EOD exit | force-flat variants | force-flat retained | rejected on role, not return |
| V7 | trade cap | — | 5 retained | re-tested by V17 |
| V8 | direction / concurrency | long-only, one position | **never tested** | document says "unexplored, not rejected" |
| V9 | morning filter | OR30 vs thr80, pos10 | **ADOPTED** direction-aware filter | never re-tested on 1-minute data |
| V10 | volatility gate | ATR5 cutoff and lookback | **ADOPTED** ATR5 ≥ 6.0% | re-tested by V18, confirmed |
| V11 | sizing / breakers | per-trade size, stop count | **ADOPTED** 2-stop breaker; size never varied | |
| V14 | the SOXL+SOXS pair | pairing protocol | **ADOPTED** | diversification survived 1-minute re-test |

**Material finding:** V2's headline — that instant re-entry was worth 47.9 of
the core's 65.6 bp — was the bug, measured from the other direction and
interpreted as the strategy's mechanism. The document now carries an amendment
saying so.

## 4.2 Parity / bias findings (S1–S12)

| id | finding | status |
|---|---|---|
| S1 | thr80 refresh cadence | spec amended |
| S4 | target live on entry bar | gap closed |
| S5 | tick grid not modelled | held as conservatism |
| S7 | whole-share sizing | live-engine rule only |
| S8 | incomplete session data | handled |
| S9 | sizing off limit vs fill | documented divergence |
| **S10** | **two-thirds of the edge is same-bar sequencing** | **correct, and overridden** |
| **S11** | 1-minute study, "edge survives at 54–64%" | **the error** |
| S12 | 1-minute file split-adjusted, 5-minute is not | handled |

## 4.3 v2_dev programs with prespecified bars (V16–V19)

| program | question | cells | result |
|---|---|---|---|
| V16 | joint dip × target on 1-minute fills | 672 | nothing adopted; established walk-forward is not protective here |
| V17 | trade cap at the margin | 8 caps × 2 sleeves | not adopted, cap stays 5 |
| V18 | volatility gate | cutoff × lookback | confirmed, nothing adopted; found `bp/ON-day` invalid for day-selection tests |
| V19 | day profit stop | diagnostic | **no bar was written** — ineligible to change anything, correctly recorded as such |

## 4.4 This session's work (V20–V23 and censuses)

| test | what it varied | result |
|---|---|---|
| **V20** fill model | spec / no_better / next_bar at 1-min | SOXL 39.34 → 8.95; SOXS 30.29 → −10.61; account 29.12 → −0.77 bp/day |
| **V21** parameters | 6 parameters, 33 configs, 66 runs, 137,201 trades | no parameter was bug-selected; **most curves flat inside 1 standard error** — the parameters never carried information |
| **backtest_as_executed** | wait-one-minute + whole shares + tick + 15:55 exit | account +6.16 bp/day, t = 1.53, p = 0.127 |
| **soxl_only** | SOXL alone vs the pair | SOXL +15.3% / −24.1% DD; pair +11.7% / −15.6% DD; correlation −0.758 |
| **vs_buy_and_hold** | strategy vs owning the index | SOXX at 45% weight beats the strategy on return, Sharpe and drawdown |
| **move_census** | ±0.25/0.5/1/2% thresholds | up-first 49–50% at every threshold; friction is 32% of a 0.25% move |
| **dip_census** | P(bounce) by dip depth | 48.3% at the entry depth vs a 48.5% baseline — **the dip carries no information** |
| | the actual +1%/−4%/15:55 bet | **SOXL −0.020%, SOXS −0.054% per bet, on raw prices** |
| **momentum_census** | trailing 5/15/30/60-min return | flat at 47–51% everywhere; best cell +0.023%/bet vs 0.023% round-trip cost |
| **data_check** | data integrity | all pass; 1-min aggregates to 5-min with 0.00e+00 error |

---

# 5. Assumption register

Every assumption the band backtest rests on, its origin, whether it was
verified, and which way it biases the result.

| # | assumption | origin | verified? | bias |
|---|---|---|---|---|
| 1 | **a sell and a re-buy may occur in the same bar, the buy priced at the bar's open** | simulator | **falsified** — live re-entries came in at or worse than the exit 9 of 14 times | **flattering, and it was the entire edge** |
| 2 | buy fills at `min(limit, bar open)` | simulator | no | flattering |
| 3 | target sells at `max(bar open, target)` | simulator | no | flattering |
| 4 | stop sells at `min(bar open, stop)` | simulator | no | conservative |
| 5 | same-bar entry-then-stop fills exactly at the stop | simulator | no | flattering |
| 6 | end-of-day exit is free at the 15:50 close | simulator | measured live: −9.13 bp per flatten | flattering |
| 7 | fractional shares | simulator | corrected | small |
| 8 | no tick rounding | simulator | corrected | small |
| 9 | cost 1.167 bp/fill | derived from published gross–net | **verified** — IBKR statement $599.36 = 1.16 bp/side | none |
| 10 | test window starts 2022-01-01 | **[AUTHOR]** choice | never discussed | unknown |
| 11 | the 1% dip / 1% target / −4% stop / 11:00 / 5 fills / 6% gate | V1–V12, scored on the bug | re-scored in V21 | **curves flat — the values never mattered** |
| 12 | "no_better and next_bar are too pessimistic" | **S11** | **falsified** | **flattering; this is the load-bearing one** |
| 13 | market data quality | vendor | **verified** — 1-min reconciles to 5-min at 0.00e+00 | none |

---

# 6. Errors found in my own work during this session **[AUTHOR]**

Listed because an audit that finds no fault with its author is not an audit.

1. **I never read S10 until after re-deriving it.** V20 reproduced, at 1-minute
   resolution, a result that had been in the repository since 2026-07-31. Three
   weeks of live analysis proceeded without it.
2. **I quoted a drawdown baseline I could not source.** Used 148,942 as "the
   peak" for two weeks. The actual starting equity was 155,803, and 148,942 was a
   mid-series value carried forward in conversation. Every percentage I gave
   before 2026-08-27 was measured from the wrong baseline.
3. **I conflated two corrections in one table.** Compared `no_better` at
   1-minute against the *5-minute* published headline, mixing the old S10/S11
   haircut with the new correction. Caught before reporting; the table was rebuilt.
4. **I mis-specified my own falsification criterion (V20 B6).** Used trade
   *count* as a proxy for materiality; removing 2.6% of trades removed 77% of the
   edge. The criterion fired against a conclusion the measurement supported.
5. **I printed a break-even threshold backwards** — "P(target) ≥ 20%" where the
   correct figure is 80%. No computed result was affected; the line invited the
   wrong reading.
6. **I told you to halve position size on a paper account.** Pointless — and
   worse, it would have contaminated the very execution comparison under test.
7. **I gave you a GitHub billing path from memory, three times, and it was
   wrong.** The correct control was "usage and budgets."
8. **My V23 regime tag is wrong.** Windows are tagged by start year rather than
   by the regime they lived through, so a 252-day window opened in 2022 mostly
   closes inside the 2023 recovery. Does not change that verdict; the tag is
   still wrong.

---

# 7. What is established, and what is not

## Established, with code you can run

- The band strategy has **negative expected value on raw prices**: SOXL
  −0.020%, SOXS −0.054% per bet, before any cost or simulator.
- **The dip carries no information.** 48.3% at the entry depth against a 48.5%
  unconditional baseline.
- **Momentum carries no information either.** 47–51% across every lookback.
- **The engine is correct.** Nine flat closes, 5.7 bp round-trip execution,
  stop rate at baseline, daily self-check passing.
- **The market data is sound.** Independent files reconcile exactly.
- **The strategy loses to owning the index at reduced size** on return, Sharpe
  and drawdown simultaneously.

## NOT established

- **That V1–V14's original methodology was sound.** I never audited it. All of
  it ran on the bug.
- **That the live sample means anything.** 30 trades. It cannot estimate an edge.
- **Whether any dip-buying variant works.** Not searched, deliberately — there
  is no held-out data left, so a search could not be trusted.
- **That −0.020%/bet is precise.** Overlapping windows; the sign is solid, the
  magnitude is not.

---

# 8. Findings and recommendations

**F1 — The controlling failure was one unevidenced sentence in S11**, not a
coding defect. The bug was found, measured and correctly bounded. It was
un-found by an assertion nobody tested. *Recommendation: no analysis may narrow
a range by declaring one end "too pessimistic" without a measurement that
distinguishes them.*

**F2 — The monitoring baseline was stale at launch and never corrected.**
`report.py` compared live against 65.6/61.9/57.7/48.1 when the project's own
newest analysis said 43.0/39.8. *Recommendation: the baseline file must be
regenerated by whichever analysis is current, and the report must print which
one it used.* (Implemented 2026-08-26.)

**F3 — No backtest in this project printed the underlying's return beside its
own.** This is the same defect that made a −65% option strategy the top
recommendation in a separate study. *Recommendation: make the benchmark column
mandatory in every backtest. It is one line and it would have caught all of
this.*

**F4 — Parameters were selected from flat curves.** V21 found best-to-worst
spreads of 3.8–10.7 bp against standard errors of 9.6–11.1. V1–V12 were reading
noise, and would have been reading noise even with a correct simulator.
*Recommendation: report the standard error beside every sweep; a sweep whose
range is inside one is not an optimisation.*

**F5 — The engine is worth keeping. The strategy is not.** The software was
audited under live fire and found sound. *Recommendation: retain the engine,
retire the strategy, and do not commit capital.*

---

*Every figure in this document is reproducible from the scripts in
`band_lab/v2_dev/`. Where a number is inherited rather than verified, that is
stated. Where it implicates the author, that is marked.*
