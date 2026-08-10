# Research Agent — product requirements and specification

**Line:** v2.0-dev (DEVELOPMENT). **Status: PROPOSED — not built.**

An agent that runs a v2_dev test programme end to end under the discipline in
`v2_dev/README.md`, and **cannot** produce an adoption that the discipline
would not have allowed.

Related: `band_lab/AI_ROADMAP.md` §2, §8. This is the cheapest item on that
roadmap and the only one that accelerates every later stage.

---

## 1. The problem

The research line works. V16, V17 and V18 collectively swept ~1,040 parameter
cells against prespecified adoption bars and correctly adopted nothing. The
methodology is sound and the results are trustworthy.

**The binding constraint is that each programme costs days of human time.**
Every one requires: framing the question, writing the adoption bar before
seeing anything, building a harness that drives `live/sleeve.py` through
configuration rather than forking it, running the sweep, computing the
diagnostics, and writing a document that states honestly whether the bar was
cleared.

That cost has a consequence beyond throughput. **It makes the project
conservative about which questions get asked** — a programme has to look
promising enough to justify the days, which is itself a selection effect on
the research. `AI_ROADMAP.md` §5 lists at least four programmes that should
run (Stage 3's day-selection model, Stage 4's regime work, a cost-module
programme, and a re-run of V17 T2 on live fills) and none is likely to happen
at the current rate.

The agent's job is to take the mechanical eight-tenths of that work and leave
the human with the two-tenths that are actually judgement: **is this the right
question, is this the right bar, and do I sign off on this result.**

## 2. What this is not

| not | because |
|---|---|
| Not a strategy generator | It does not propose what to test. A human, or `AI_ROADMAP.md`, chooses the variable |
| Not an adjudicator | It computes whether the bar was cleared. It does not decide whether to adopt. §6 |
| Not connected to the broker | Read-only over CSVs, the 1-minute files, and (Stage 0 onward) `live.db`. No `ib_async` import, ever |
| Not a replacement for sign-off | Every artefact it produces lands in a branch, as a diff, for a human to merge |
| Not permitted in `phase1/` or `live/` | It writes only under `v2_dev/`. §7.3 |

## 3. Users and the workflow it replaces

One user: the person running the research line. The workflow today, and after.

| step | today | with the agent |
|---|---|---|
| frame the question | human | human |
| write the adoption bar | human | human writes; agent formats and **hash-commits** it |
| build the harness | human, ~1 day | **agent**, from the programme spec |
| run the sweep | human, hours of wall clock | **agent**, in the background |
| compute diagnostics | human | **agent**, from the declared test list |
| evaluate against the bar | human | **agent**, deterministically — §6 |
| write the document | human, ~half a day | **agent** drafts, human edits |
| decide adoption | human | **human** |

## 4. Scope — the programme lifecycle

A programme is six phases. The agent owns P2 through P5.

```
P1  FRAME      human      the variable, the question, the prior
P2  SPECIFY    agent      programme spec: tests, metrics, grid, adoption bar
                          -> human reviews and signs off
P3  COMMIT     agent      hash the signed spec; write it to the ledger
P4  EXECUTE    agent      build harness, run sweep, compute diagnostics
P5  REPORT     agent      evaluate bar deterministically; draft V<n>_*.md
P6  DECIDE     human      merge, or reject, or send back to P1
```

**P3 is the load-bearing phase and the reason this document is long.** See §6.

## 5. Functional requirements

### FR-1 — Programme specification (P2)

From a framing in prose, the agent produces a `V<n>_<NAME>_TEST.md` in the
established house form: why this variable and why now; the metric trap section
if one applies; the test list (T1…Tn) with each test's purpose stated before
its result exists; the grid; and the adoption bar as numbered criteria
(B1…Bn / D1…Dn).

It must reproduce the structural conventions of `V17_TRADE_CAP_TEST.md` and
`V18_VOL_GATE_TEST.md`, including the `Status: PROPOSED — awaiting sign-off.
Not yet run.` header and the sentence fixing the bar at sign-off.

### FR-2 — Harness construction (P4)

The harness **drives `live/sleeve.py` through configuration**. It may not
fork, reimplement, or subclass the state machine. `v2_dev/README.md` item 4 is
a hard requirement, not a preference:

> One engine, not two. A forked research engine is that problem by
> construction.

If a programme needs a parameter that `SleeveConfig` does not expose, the
agent stops and asks. Adding a field to `SleeveConfig` is a production code
change, it must default to the §12 value, and it requires the same
bit-identity evidence the V16 change produced: `phase1` green, `parity.py`
exit 0, `live` suite green, `replay.py` exit 0.

### FR-3 — Metric guards (P2 and P5)

The agent refuses to accept a programme spec, and refuses to report a result,
that violates either established metric rule:

| guard | rule | source |
|---|---|---|
| G1 | Any programme whose grid changes which days are traded **must** declare net bp per calendar day as primary | V18 §2 |
| G2 | `bp/ON-day` may be reported, never adopted on | V18 D1 |
| G3 | Selection walk-forward is not sufficient evidence on its own; a mechanism test is required | V16 R4.2 |
| G4 | A result where the sleeves move in opposite directions fails, regardless of aggregate | V16, on V1 and V3 |

G1 and G2 are checked mechanically from the spec. G3 and G4 are checked at
report time and, if violated, the agent must record a fail — it may not
narrate around them.

### FR-4 — Execution (P4)

Runs the sweep, writes raw per-cell results to `v2_dev/out/` as CSV under the
existing naming convention (`v<n>_<artefact>_<SYMBOL>.csv`), and records the
git SHA, the data file hashes, and the wall-clock duration in a run manifest.

Every reported number must be reproducible by re-running one command. The
command goes in the document, as the repo already requires: the command is the
evidence.

### FR-5 — Deterministic adjudication (P5)

The agent evaluates each criterion in the committed bar and emits, per
criterion, one of `PASS` / `FAIL` / `NOT-EVALUABLE`, with the computed number
and the threshold beside it. The programme outcome is a pure function of those
verdicts. **No natural-language reasoning may change an outcome.** §6.

### FR-6 — Reporting (P5)

Drafts the results sections of the programme document in house style, appends
the results table, and states the outcome as **ADOPTED** or **NOT ADOPTED**
with the failing criteria named. Where a programme fails, it must also record
findings worth carrying forward — the V16/V17/V18 documents' most valuable
content came from programmes that adopted nothing.

### FR-7 — Corpus retrieval

Retrieval over the spec corpus (`IMPLEMENTATION_SPEC.md`, `STRATEGY_SPEC.md`,
`MASTER_STRATEGY_DOCUMENT.md`, the V-programme documents, the parity
documents), so the agent can cite the § that establishes a prior rather than
restating it from memory. Citations must resolve to a real section; an
unresolvable citation is a bug, not a stylistic issue.

### FR-8 — Ledger

`v2_dev/PROGRAMMES.md`, append-only: programme, variable, spec hash, sign-off
timestamp, run SHA, outcome, and the criteria that failed. This is the audit
trail that makes §6 checkable after the fact.

## 6. The integrity model — the agent's primary threat is itself

**An agent that both writes the adoption bar and evaluates results against it
will rationalise.** Not through malice: a model asked "did this clear the
bar?" while holding the bar in the same context as an attractive result is
under exactly the pressure that produced the original problem in §11. The
V16 winner was attractive. It passed 5 of 5 held-out years. A sufficiently
motivated write-up could have adopted it.

The whole point of prespecification is that it removes the writer's
discretion. **An agent must be built so it cannot recover that discretion.**
Four mechanisms:

### 6.1 The bar is hash-committed before execution

At P3, the signed spec is hashed (SHA-256 over the normalised adoption-bar
section) and the hash is written to the ledger with a timestamp. At P5 the
agent recomputes the hash and **refuses to report if it does not match.**

A changed bar is not an error to be worked around. It voids the programme, and
the programme must be re-signed as a new one.

### 6.2 Role separation

Three roles, run as separate invocations with separate context:

| role | sees | produces |
|---|---|---|
| **Specifier** (P2) | the framing, the corpus, prior programmes | the spec and the bar. **Never sees results** |
| **Executor** (P4) | the committed spec, the data | raw CSVs. **Never sees the bar** |
| **Adjudicator** (P5) | the committed bar, the raw CSVs | per-criterion verdicts |

The Executor not seeing the bar is what prevents the sweep being shaped toward
it. The Specifier not seeing results is what makes prespecification real.

### 6.3 Adjudication is code, not judgement

Each criterion in the bar compiles to an executable predicate at P3 —
`metric`, `comparator`, `threshold`, `scope` — and the Adjudicator's output is
the result of running those predicates over the CSVs. The LLM's role at P5 is
to *explain* the verdicts and draft prose around them. It cannot produce them.

A criterion that cannot be compiled to a predicate is not admissible in a bar.
This is a real constraint on how bars are written, and it is a good one: it
was already implicit in how V17 §6 and V18 §7 were phrased.

### 6.4 The default outcome is NOT ADOPTED

Any of the following forces NOT ADOPTED, with no override path:

- spec hash mismatch (§6.1);
- any criterion evaluating to `NOT-EVALUABLE`;
- a metric guard violation (FR-3);
- a harness that does not drive `live/sleeve.py` (FR-2);
- failure to reproduce a reported number on re-run.

**The agent has no mechanism to adopt anything.** It can only produce a
NOT-ADOPTED, or a "bar cleared — awaiting human sign-off". Adoption is a human
merging a change to §12, and that stays true regardless of how good the
agent gets.

## 7. Architecture

### 7.1 Shape

A Claude Code subagent per role, orchestrated by a thin Python driver that
owns hashing, the ledger, predicate compilation and predicate evaluation. The
deterministic parts are Python because they must be auditable and must not
vary between runs; the drafting and framing parts are the model because that
is what it is good at.

```
v2_dev/agent/
  driver.py         P3/P5 mechanics: hash, ledger, compile, evaluate
  predicates.py     the criterion vocabulary — metric x comparator x scope
  harness.py        SleeveConfig sweep runner over live/sleeve.py
  corpus.py         FR-7 retrieval over the spec documents
  roles/
    specifier.md    P2 prompt + house-style rules
    executor.md     P4 prompt — never receives the bar
    adjudicator.md  P5 prompt — receives verdicts, drafts prose
```

### 7.2 Data access

Read-only. Historical CSVs (including the git-lfs 1-minute files), `v2_dev/out/`,
and from `AI_ROADMAP.md` Stage 0 onward, a read-only handle on `live/out/live.db`
for programmes that use realised fills. **No `ib_async` import in this tree, at
any point, for any reason.**

### 7.3 Write boundary

The agent writes only under `v2_dev/`, and only on a branch. It may not modify
`phase1/` (the reference implementation, which `PROJECT_STATUS.md` §6 says must
not be modified), `live/`, or any `§12` constant. FR-2's `SleeveConfig` case is
the sole exception and it goes to a human as a normal reviewed change, with the
bit-identity evidence attached.

## 8. Interfaces

```bash
# P2 — draft a programme spec from a framing
python3 v2_dev/agent/driver.py specify --var V19 --framing framing.md

# P3 — hash and commit a signed spec (refuses if Status is still PROPOSED)
python3 v2_dev/agent/driver.py commit --spec v2_dev/V19_*.md

# P4 — build the harness and run the sweep
python3 v2_dev/agent/driver.py execute --programme V19 [--quick]

# P5 — adjudicate and draft the results
python3 v2_dev/agent/driver.py report --programme V19

# any time — verify a completed programme still reproduces
python3 v2_dev/agent/driver.py verify --programme V19
```

`--quick` mirrors the existing coarse-grid convention in `churn_joint_test.py`
and is marked in the manifest so a quick run can never be reported as a full
one.

## 9. Acceptance tests

The agent is not usable until all nine pass. Tests 1–3 are the integrity model
and are the ones that matter.

| # | test | passes when |
|---|---|---|
| 1 | Edit the bar after `commit`, then `report` | refuses, hash mismatch, records void in the ledger |
| 2 | Give the Executor a spec and inspect its full context | the adoption bar is absent |
| 3 | Hand the Adjudicator a result that beats the incumbent but fails one criterion | outcome is NOT ADOPTED, criterion named, no hedging prose |
| 4 | **Replay V18 end to end from its framing** | reproduces NOT ADOPTED, and its per-criterion verdicts match the published document |
| 5 | Replay V16 | reproduces NOT ADOPTED; independently reaches the sleeves-disagree finding (G4) |
| 6 | Propose a programme with `bp/ON-day` primary on a day-selection variable | refused at P2 by G1 |
| 7 | Propose a programme needing an unexposed `SleeveConfig` field | stops and asks; does not fork the engine |
| 8 | `verify` on a completed programme after a data file changes | fails, names the file whose hash moved |
| 9 | Run the full live + phase1 suites after any agent run | unchanged and green — the agent touched nothing outside `v2_dev/` |

**Test 4 is the acceptance test.** V18 is the most recent completed programme,
its adoption bar is written down, and its verdicts are published. An agent that
cannot reproduce a known NOT-ADOPTED from its framing is not trustworthy on a
question whose answer nobody knows.

## 10. Milestones

| M | scope | gate |
|---|---|---|
| M1 | `driver.py`, `predicates.py`, ledger, hashing | tests 1, 3, 6, 8 |
| M2 | `harness.py` over `live/sleeve.py` | test 7, 9; reproduces a published V16 cell exactly |
| M3 | The three roles; corpus retrieval | test 2, 5 |
| M4 | **V18 replay** | **test 4** |
| M5 | First live use: the `AI_ROADMAP.md` Stage 3 programme | a human signs off a bar the agent drafted |

M1–M4 are the build. M5 is the first thing it is for.

## 11. Risks

| risk | mitigation | residual |
|---|---|---|
| The agent makes bad programmes cheap, and volume becomes its own multiple-comparisons problem | The ledger is append-only and every programme is counted, including abandoned ones. A future bar should be adjusted for the number of programmes run | **Real and unmitigated.** The honest cost of removing the time constraint is that time was doing some of the work of restraint. Watch the ledger length |
| Prose that argues around a FAIL | §6.3 — verdicts are computed; test 3 | low |
| Harness drift from the live engine | FR-2; test 9; `replay.py` in CI | low |
| Retrieval fabricates a § citation | Citations resolve or the report fails to build | low |
| The agent is trusted more than the humans were | Nothing it produces is adoptable without a human merging a §12 change | low, if §6.4 holds |

The first row is the one to take seriously. **The research line's discipline
has partly been enforced by how expensive it was to run a programme.** Removing
that cost removes some of the enforcement, and the ledger is the only thing
put in its place. If programme count starts rising faster than findings, that
is the signal to slow down, and it should be checked explicitly at each
sign-off.
