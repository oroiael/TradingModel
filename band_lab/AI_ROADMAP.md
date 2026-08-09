# AI and learning — what to build, in what order, and what each stage buys

**Status: PROPOSED — planning document.** Nothing here changes v1.0. No §12
constant is touched by anything in this file, and no stage below is authorised
to touch one.

This document spans `live/` and `v2_dev/`, which is why it sits at the top of
`band_lab/` rather than inside either.

---

## 0. First, the legality question — this document and §11

`IMPLEMENTATION_SPEC.md` §11 says, in full:

> No parameter optimisation, auto-tuning, or machine learning of any kind. The
> parameters are fixed by validation and must be changed only by a deliberate,
> documented, re-validated decision.

**This roadmap does not overturn §11 and does not ask to.** It takes the same
route `v2_dev/README.md` took: §11 names "a deliberate, documented,
re-validated decision" as the *only* way a parameter moves, and every stage
below either (a) does not touch a parameter at all, or (b) is exactly that
route, with the adoption bar written before the run.

The distinction §11 is actually drawing is between **auto-tuning** — a process
that changes what the engine does without a human decision — and **evidence**.
Stages 0 through 2 produce only evidence. Stage 3 is the one that could move a
dial, and it is gated accordingly.

If a future reader thinks this document has drifted from §11, §11 wins. That
is the rule for every disagreement in this repository.

---

## 1. The three constraints that determine every answer below

Anyone proposing ML for this strategy needs to have absorbed three results the
project already produced. They are not caveats; they are the shape of the
problem.

### 1.1 The validation methodology does not detect the dominant error

V16 finding 1, in `v2_dev/README.md`:

> The rejected V16 winner beat the incumbent out-of-sample in 5 of 5 held-out
> years in both sleeves — a bias present in every year is identical in every
> fold.

**Walk-forward is not protective on this dataset.** Any model trained here
will pass walk-forward, and passing will mean nothing. Every stage below that
touches a strategy decision therefore requires a *mechanism* test — an account
of why the model believes what it believes, which survives inspection at
1-minute resolution — in addition to, not instead of, held-out performance.

### 1.2 The obvious objective function is invalid

V18 §2: `bp/ON-day` is corrupted for any day-selection question, because the
gate moves the denominator. A 10% ATR5 cutoff shows **93.9 bp/ON-day against
39.3** while *halving* what the account earns per calendar day.

That is the reward an RL agent, a classifier threshold sweep, or any naive
objective would maximise by default. **The primary metric for anything that
selects days is net bp per _calendar_ day**, and this may not be swapped after
results are seen.

### 1.3 The sample is small, and smaller than it looks

| | SOXL | SOXS |
|---|---:|---:|
| ON-days in the full sample | 779 | 793 |
| trades, both sleeves (`replay.py`) | 5,118 | |
| days where the trade cap binds (V17) | 136 (20.0%) | 178 (25.8%) |
| ON days carrying the entire edge (V17 R5) | ~30% | ~30% |

Signal-level learning has **N ≈ 780 per sleeve**, and the subpopulation that
actually carries the P&L is ~230 days. That supports one to three effective
parameters. It does not support a model with a feature set.

Execution-level learning has N in the **thousands of fills**. That asymmetry
is the single most important input to the sequencing in §4.

---

## 2. Verdict on the three candidates

| candidate | verdict | where it belongs |
|---|---|---|
| **Agent** | **Yes — supervisory and offline, never in the order path** | Stage 1 (ops), and the research agent (`v2_dev/RESEARCH_AGENT_PRD.md`) |
| **RAG** | **No, not in the trading system** | Retrieval over the spec corpus, inside the Stage 1 ops agent and the research agent. Zero alpha, near-zero risk, cheap |
| **Small model** | **Yes, eventually — on execution first, not on signal** | Stage 2. Stage 3 only after Stage 0–2 exist |

### 2.1 Why RAG is the wrong tool for the decision path

RAG conditions text generation on retrieved documents. Every decision this
system makes is arithmetic over six numbers: `atr5`, `or30`, `thr80`, `pos10`,
the rolling anchor, and the current position. There is no natural-language
input anywhere in `strategy_core.py`, and adding one would be a strategy
change of the largest possible kind.

Retrieval *is* legitimately useful outside the loop. `PROJECT_STATUS.md` §6
exists because it became hard to tell which of thirteen documents to read;
that is a real cost, paid by every person who touches this project, and a
retrieval layer over the spec corpus fixes it. Call that documentation
tooling, not a trading system, and do not count it as progress toward
learning.

### 2.2 Why the first model must be an execution model

A gradient-boosted classifier on ~10 features over 780 rows will find
something, and per §1.1 it will pass walk-forward. It will be
indistinguishable from the V16 winner that was correctly rejected.

An execution model has 100× the sample, an unambiguous label, and — decisively
— **cannot change what the strategy does.** It changes what you believe the
strategy earns. That is the safe class of learning and it happens to sit on
top of the largest open question in the project.

### 2.3 Why no LLM goes in the order path

Beyond latency and non-determinism: it destroys the property that makes
`replay.py` meaningful. Today the live state machine and the backtest are the
same code, and the equivalence report shows **779 = 779 ON-days on SOXL,
793 = 793 on SOXS, max daily P&L difference 0.0, 5,118 trades with 0 outcome
differences.** That is the most valuable single asset in this codebase and it
is worth more than any plausible signal improvement.

---

## 3. The reframe — the loop that does not exist yet

**Eight defects have been found in five live sessions, and every one was
invisible to a suite that is now 232 green** (`PROJECT_STATUS.md` §4), because
all eight lived in `IBBroker`, the feature bootstrap, or the order path
against a real broker — which a `FakeIB` suite cannot reach by construction.
The worst left **241 of 541 shares with no protective stop**. Another consumed
an entire session, ingested every bar, decided nothing and raised no error,
because TWS was configured for `America/Los_Angeles` and `Bar.idx` came out at
**−36**.

Meanwhile: no target or stop has ever filled against IBKR, `report.py` does
not exist, `risk.py` does not exist, and there is no alerting of any kind.

So the honest headline:

> **The highest-value "learning system" for this strategy over the next
> quarter is not machine learning. It is closing the feedback loop that does
> not currently exist.** The engine trades and nobody diffs the fills against
> the backtest. You cannot learn from a loop that does not measure.

`PROJECT_STATUS.md` §5E already says this — `report.py` is "the highest-priority
remaining work — without it the run generates fills nobody compares to the
backtest." This document agrees and adds only that it is also the precondition
for every AI stage below.

---

## 4. The staged path

| stage | what it is | ML? | precondition | honest expected outcome |
|---|---|---|---|---|
| **0** | `report.py` — the measurement instrument | no | none | the training set for everything below |
| **1** | invariants as code, then an ops agent | agent | Stage 0 | defect latency: one session → same session |
| **2** | execution model (fill probability, sequencing) | **yes** | 4–8 weeks of fills | a calibrated number for "what does this earn" |
| **3** | day-selection → **sizing multiplier**, not a gate | yes | Stages 0–2 | **most likely NOT ADOPTED** |
| **4** | regime / excursion clustering | yes | Stage 3 complete | unknown; strongest untouched prior in the repo |

Stages run in order. Each one's output is the next one's input, and skipping
ahead reproduces the failure §1 describes.

---

## 5. Stage detail

### Stage 0 — `report.py`. The prerequisite for everything.

Already specified as Stage 6 of `live/PHASE2_PLAN.md` and already top of the
Week 1 checklist. What matters for this roadmap is the *output shape*: a
per-session, per-trade record of **what the backtest said** against **what the
broker did**, joined on session and trade ordinal.

Deliverables:

- daily shadow parity: for each sleeve, the decision the engine made against
  the decision `phase1/spec_engine.py` would have made on the same bars;
- the two S10/S11 questions answered from `fills` and `quotes`: did any fill
  occur without the quote reaching the limit, and on same-bar re-entries is
  the achieved price at or worse than the price just sold;
- realised slippage per fill, against both the limit and the mid at decision
  time;
- the §8 monitoring table computed on live data, so the >20% structural-break
  rule has something to fire on.

**Outcome:** the first labelled dataset this project has ever had of its own
execution. Everything downstream trains on it.

### Stage 1 — invariants first, agent second

The ordering inside this stage is not cosmetic. **A model must never be the
thing standing between the account and a missing stop.** Write the
deterministic checks first:

| invariant | the defect it would have caught |
|---|---|
| protective qty == `broker.position()`, continuously | defect 8 — 241 shares unstopped |
| feature freshness ≤ 5 days | defect 5 — ATR5 from data ending 2026-07-21 |
| bar 0 is the 09:30 bar | the `America/Los_Angeles` −36 index |
| exposure past 15:58 | three consecutive failures to flatten (`watchdog.py`, built) |

Then, and only then, the agent: read-only access to the SQLite
`events` / `orders` / `fills` / `quotes` / `daily` tables plus the spec corpus,
producing (a) a plain-language session narrative, (b) anomaly triage with a
§-citation for the rule each anomaly violates, (c) an escalation when an
invariant trips.

It explains and escalates. **It does not decide, and it has no write path to
the broker.** This is where retrieval over the specs earns its place: the
agent should be able to say "the bracket quantity is 300 against a position of
541, which violates §2.6" and cite the line.

**Outcome:** defect-discovery latency drops from *one live session per defect*
to same-session. This is the gate on unattended operation, which
`PROJECT_STATUS.md` §3 currently blocks on "no alerting" and "no service
supervision".

### Stage 2 — the execution model. The first real ML, and it is small.

Two targets, both supervised, both on data that will exist after 4–8 weeks of
paper fills plus the 1-minute history already in git-lfs:

1. **Fill probability and expected slippage** for a resting limit at
   `anchor × 0.99`, conditioned on the quote and the recent bar. Label:
   whether it filled, and at what price relative to the limit.
2. **The S10/S11 sub-minute sequencing residual.** `PHASE2_PARITY.md`
   establishes that 5-minute bars over-credit same-bar re-entry, and that at
   1-minute resolution the edge retains 64% on SOXL and 54% on SOXS. The
   remaining uncertainty is sub-minute ordering, and it runs one direction
   only — real fills should land *below* the 1-minute figures.

**Why this is worth more than any signal tweak:** it converts "plan on ~40
bp/ON-day for SOXL and ~30 for SOXS, and real fills should land below that"
into a calibrated estimate with an error bar. That number decides whether to
fund the strategy with real money at all, and at what size. Nothing in Stage 3
or 4 can matter more than that.

**Constraint:** the output of Stage 2 does not enter the decision path. It is
an estimate *about* the strategy, not an input *to* it.

### Stage 3 — day selection, expressed as sizing. The ambitious one.

V17 R5 is the one genuine signal-level target in the repository:

> The entire edge comes from the ~30% of ON days that reach the trade cap; the
> other ~70% lose money (**−31.0 bp/day SOXL, −91.2 SOXS**).

If membership in that cohort is forecastable from information available at
06:00 or 10:00, it is worth a great deal. V18 already asked the narrow version
of this question of ATR5 alone and closed it. The broader version — a model
over the full feature set — is the natural successor, under five conditions,
all of which come from this project's own results:

1. **Judged per calendar day** (§1.2). Non-negotiable, fixed before the run.
2. **Mechanism test required** (§1.1). Held-out performance is necessary and
   not sufficient. The model must produce an account of *why* a day is
   different, and that account must survive at 1-minute resolution.
3. **Output is a bounded multiplier on `f`, not an on/off gate.** V17 R5 also
   found that low-volatility days are profitable through *safety* — the −4%
   stop rarely fires — and high-volatility days through *churn*. The gate
   cannot be tightened without deleting a profitable regime. A gate is the
   wrong instrument; continuous sizing is the right one. Suggested bound:
   `f ∈ [0.5, 1.0]`, which stays inside the §12 valid range and cannot
   increase risk beyond the already-validated maximum.
4. **Adoption bar written and hash-committed before the run**, per the v2_dev
   discipline and `RESEARCH_AGENT_PRD.md` §6.
5. **Both sleeves, same direction.** V16 closed V1 and V3 because the sleeves
   disagreed in *direction*. Any model that helps SOXL and hurts SOXS is
   fitting, and should be rejected on that alone.

**Honest expected outcome: NOT ADOPTED**, in line with V16, V17 and V18. Call
it a ~30% chance of a real sizing improvement and a ~70% chance of a fourth
well-documented rejection. **That is a good trade, and the rejections have
been worth more than the adoptions so far** — findings 1 and 2 in §1 above
both came out of programmes that adopted nothing.

### Stage 4 — regime. The strongest untouched prior.

`README.md` §3 documents a measured, persistent clustering effect the live
engine uses not at all:

| | |
|---|---|
| P(excursion) on a random day | 10% |
| P(excursion) the day after one | **32%** |
| longest observed burst | **11 straight sessions** |
| high-vol day after a high-vol day | 38% against a 17% base rate |

And the known unhedged risk is a regime flip: the cycle sleeve lost **−80.3%
in 2022** on parameters selected by walk-forward from pre-2022 data. That is
what "learned parameters" have historically done in this repository, and it is
the argument for treating Stage 4 as the most dangerous stage, not the most
exciting one.

Left deliberately underspecified. It should not be designed until Stage 3 has
run and its result — adoption or rejection — is known.

---

## 6. Explicit non-goals for AI work

In the spirit of §11, and binding on every stage above.

- **No LLM in the order path or the decision path.** §2.3.
- **No reinforcement learning.** N ≈ 780 days, and §1.2 means the reward
  function would be wrong before the first episode.
- **No online or continuous learning.** Any parameter that adapts between
  sessions breaks `validate_config`, breaks `replay.py` equivalence, and
  re-creates the tuning-on-biased-feedback failure S10 exposed.
- **No model output may modify a §12 constant.** Stage 3's multiplier acts on
  `f`, which §2.9 already defines as configuration rather than logic, and only
  within its already-validated range.
- **No model in the safety path.** Invariants, the day-loss breaker and the
  watchdog stay deterministic, forever.
- **No alternative-data ingestion** before Stage 4, and not without its own
  programme document.

---

## 7. The design rule that makes all of this reversible

One architectural invariant governs every stage:

> **Anything that learns lives outside the locked core and emits a
> configuration the deterministic engine consumes. If a model output ever
> reaches a decision, it is logged as an input to that decision — in the
> `daily` row, alongside `atr5` and `or30` — so the session stays replayable
> and the model stays auditable.**

Consequences worth stating explicitly:

- `replay.py` equivalence must still pass with the model's recorded outputs
  replayed as fixed inputs. If it cannot, the design is wrong.
- Turning every model off must return the system to bit-identical v1.0
  behaviour, and there should be a test asserting exactly that — the same
  guarantee `v2_dev` obtained when `SleeveConfig` gained `dip_pct`,
  `target_pct` and `stop_pct` with §12 defaults.
- No model is ever consulted twice for the same decision, and no decision is
  ever made from a model call that failed. Failure means the locked default.

---

## 8. What to do next week

1. Build `report.py`. Nothing else on this list is reachable without it.
2. Write the four Stage 1 invariants as plain assertions in the engine.
3. Read `v2_dev/RESEARCH_AGENT_PRD.md` and decide whether to build it — it is
   the cheapest item here and it accelerates Stages 3 and 4 by removing the
   binding constraint on the research line, which is human time.

Everything else waits for fills.
