# Pre-registration — FOMC announcement-night overnight return

**Locked: 2026-09-17.** The git commit carrying this file is the timestamp, and
that is the only thing that makes what follows worth doing. Nothing below may be
changed after the first observation lands. Results go in `fomc_oos.csv`, never
in here.

---

## Why this exists

`fomc_test.py` found something in 30 FOMC announcements from 2023. It was found
by looking, after the hypothesis it was meant to test (the published pre-FOMC
drift, on the night *before* the announcement) came back weak. That makes it
exploratory, and exploratory findings on n=29 with fat tails are the single most
reliable way to fool yourself in this kind of work.

Two upcoming events are known in advance and appear in no backtest. This file
states exactly what is predicted, exactly how it will be scored, and exactly
what would count as failure — before any of it is observable.

## The claim

Buying at the close of an FOMC **announcement day** — after the 14:00 decision
and the press conference are already public — and selling at the next open
returns more than an ordinary night.

This is **not** the published Lucca–Moench pre-FOMC drift, which concerns the
night *before* the announcement. That one was tested and came back at
permutation p = 0.077, failing a multiple-comparison haircut. The claim here is
a different, weaker-provenance one.

**There is no established mechanism.** The obvious candidate is ruled out:
FOMC-day intraday returns are +0.130% against +0.127% on other days, so this is
not a reversal of a weak afternoon. The effect is in the overnight and nowhere
else, and nothing explains why. A finding with no mechanism deserves a higher
evidentiary bar, not a lower one.

## In-sample values being predicted forward

2023-01-03 → 2026-09-10, 29 scoreable announcement nights.

| instrument | announcement night | other nights | excess | overnight sd |
|---|---|---|---|---|
| QLD  | +1.166% | +0.085% | **+1.081%** | 1.59% |
| TQQQ | +1.742% | +0.119% | +1.623% | 2.38% |
| SOXL | +2.360% | +0.326% | +2.034% | 4.58% |
| TECL | +1.526% | +0.138% | +1.388% | 2.93% |
| TNA  | +1.232% | +0.081% | +1.151% | 2.53% |
| XLU  | +0.148% | +0.040% | +0.108% | 0.47% |

## Primary endpoint: QLD, and why not SOXL

**QLD**, the 2× Nasdaq-100 ETF. Chosen on POWER, computed before any data
exists: detecting its +1.081% excess at t=2 needs ~9 events, reachable inside
2027. SOXL needs ~20, which is 2029.

SOXL is what is actually traded and is recorded as a secondary endpoint. It does
not decide anything, because it cannot — its volatility is too high for the
effect size to clear the noise in any reasonable number of events. Choosing the
tradeable instrument as the primary endpoint would guarantee an inconclusive
test, which is a way of never being wrong.

## The test

**Statistic.** Overnight return = `open(next session) / close(announcement day) − 1`,
from IBKR daily bars, `whatToShow="TRADES"`, matching every other measurement in
this repository.

**Null hypothesis.** The mean over out-of-sample announcement nights equals the
contemporaneous non-announcement mean.

**Stopping rule.** Score at **n = 9** out-of-sample events: 2026-10-28,
2026-12-09, and the first seven of 2027. No interim decisions, no stopping early
because it looks good, no continuing because it looks bad.

**Decision at n = 9**, one-sample t against the contemporaneous baseline:

| result | conclusion |
|---|---|
| t ≥ 2.0 **and** mean excess > 0 | survives; then and only then consider acting |
| 0 < t < 2.0 | unresolved; extend to n = 18 under the same rule, once |
| mean excess ≤ 0 | **abandoned.** Do not re-test, do not re-slice |

**Pre-declared secondary observations**, recorded but not decisive: SOXL, TQQQ,
TECL, TNA, XLU on the same nights.

## What is NOT being tested, and may not be added later

* the **eve** night. It failed in-sample and is not resurrected here.
* whether the volatility filter should be **overridden** on these nights. The
  in-sample cell — 11 declined nights averaging +4.01% — is n=11 selected from
  29 selected from 926, and is exactly the kind of cell that this whole file
  exists to avoid trusting.
* any instrument not listed above.
* any subset of these events (SEP meetings, cut-vs-hold, first-of-year).
  Slicing 9 events is not analysis.

## Things that would invalidate the test

* an unscheduled or emergency FOMC action in the window
* a date changing (each is tentative until the preceding meeting confirms it)
* a market closure or half-session on an announcement day
* our data source changing basis away from `TRADES`

Any of these: record it in `fomc_oos.csv` and exclude that event, stating why
at the time and not afterwards.

## Live configuration

**Unchanged.** Nothing in this pre-registration alters what trades tonight. If
the test survives at n = 9, that is when the conversation about acting starts —
not before, and not because an interim number looked good.
