# Stage 1 — Live State Machine Equivalence

**Result: PASS.** The state machine that will run against IBKR reproduces
`band_lab/phase1/spec_engine.py` (`SPEC_LITERAL`) exactly on the historical
5-minute bars — 779 SOXL and 793 SOXS ON-days, **zero** difference in daily
P&L, identical gate and filter reasons on every session, and identical entry
price, exit price, quantity and outcome on all 5,118 trades.

```bash
python3 band_lab/live/replay.py          # equivalence report, exit 0 == green
python3 -m pytest band_lab/live -v       # 58 tests
```

| sleeve | ON days | max abs daily P&L diff | trades | outcome diffs | max abs price diff | gross bp/ON-day |
|---|---:|---:|---:|---:|---:|---:|
| SOXL | 779 = 779 | 0.0 | 2,460 = 2,460 | 0 | 0.0 | 65.93 both |
| SOXS | 793 = 793 | 0.0 | 2,658 = 2,658 | 0 | 0.0 | 61.18 both |

That matches `phase1/PHASE1_PARITY.md` §4's as-built row (SOXL 65.9 bp / 779
days, SOXS 61.2 bp / 793 days), which is what the live engine inherits.

The point of this exercise is attribution: when the paper run comes in below
the backtest, the shortfall is now attributable to fills rather than to a
coding error in the ratchet, the counters or the anchor. Both are still
possible causes of a live-vs-backtest gap; only one of them has now been
eliminated.

Doing it surfaced two clauses that Phase 1's eight did not cover.

---

## S9 — §2.4 sizes off the limit price; the research engine sizes off the fill

`IMPLEMENTATION_SPEC.md` §2.4 says `order_qty = floor(f × sleeve_capital /
limit_price)`. `spec_engine.simulate_session` sizes off `entry_px`, the fill
price. The two differ whenever a bar opens below the resting limit, because
the fill is then at the open rather than at the limit.

The live engine has no choice: the order quantity is fixed when the order is
placed, so a better fill buys the same shares at a better price rather than
more shares. §2.4 is right and the research engine is the outlier.

```bash
python3 band_lab/live/replay.py --sizing
```

| sleeve | fill-priced (research) | limit-priced (§2.4, live) | delta | entries affected |
|---|---:|---:|---:|---:|
| SOXL | 65.93 bp | 65.08 bp | **−0.84 bp** | 1,664 / 2,460 (67.6%) |
| SOXS | 61.18 bp | 60.12 bp | **−1.06 bp** | 1,826 / 2,658 (68.7%) |

**Decision: the spec stands; the live engine sizes off the limit price**
(`SleeveConfig.sizing_basis="limit"`, the default). The fill-priced reading
stays runnable so the equivalence proof can reproduce the validated series.

This revises the as-built gap the live system carries into Phase 3. Against
the validated research series, and before any fill effects:

| | PHASE1_PARITY §4 | with S9 |
|---|---:|---:|
| SOXL | +0.3 bp | **−0.5 bp** |
| SOXS | +3.5 bp | **+2.4 bp** |

---

## S10 — two-thirds of the measured edge rests on same-bar sequencing

This is the material finding, and it is not a coding difference: the
equivalence run above reproduces it exactly, because it is a property of the
validated engine.

### What the engine does

Within one bar, `spec_engine` resolves an open position first and then, if the
resting limit is touched, opens a new one **in the same bar at that bar's
open** — a price that traded *before* the exit did. The `min(limit, open)`
fill rule then prices the re-entry at the bar's opening print regardless of
what the path did after the exit.

A real example, SOXL 2021-01-15, bar 21 (11:15–11:20), a bar with
`O=37.66  H=38.20  L=37.60  C=38.20`:

| | |
|---|---|
| held from bar 18 | entry 37.767, target 38.144 |
| exit on bar 21 | **sold at 38.144** (the target) |
| re-entry on bar 21 | **bought at 37.661** (the bar's open) |
| booked | +1.377% on the next leg — more than the 1% target |

The bar closed at its high. For that round trip to exist, price had to return
to 37.66 *after* printing 38.14; the bar's own close says it did not.

### How much of the edge is exposed

```bash
python3 band_lab/live/replay.py --fill-models
```

Every row runs the identical §2 rules. Only the price a 5-minute simulator is
willing to assume for a re-entry inside the exit bar changes:

| sleeve | fill model | bp/ON-day | Sharpe |
|---|---|---:|---:|
| SOXL | **spec** (validated engine) | **65.9** | **3.14** |
| SOXL | `no_better` — may not re-buy below the price just sold, same bar | 12.6 | 0.62 |
| SOXL | `next_bar` — no same-bar re-entry at all | 21.4 | 1.18 |
| SOXS | **spec** | **61.2** | **2.83** |
| SOXS | `no_better` | 5.9 | 0.28 |
| SOXS | `next_bar` | 2.2 | 0.12 |

Supporting counts:

| | SOXL | SOXS |
|---|---:|---:|
| same-bar re-entries | 1,203 / 2,460 entries (48.9%) | 1,347 / 2,658 (50.7%) |
| …that re-bought **below** the price just sold | 907 (75% of them) | 1,022 (76%) |
| median discount captured | **46 bp** | **53 bp** |
| …where the bar then **closed above** the re-entry price | 84% | 81% |
| P&L in those trades | **62.5 of 65.9 bp/ON-day** | **75.9 of 61.2** |

### What this does and does not mean

- It does **not** mean the strategy loses money. `no_better` and `next_bar`
  are assumptions too, and both are deliberately harsh: intrabar price does
  oscillate, and some of these re-entries are genuinely fillable. The true
  value is somewhere between the rows.
- It **does** mean the published 65.6 / 57.7 bp sits at the optimistic
  extreme of what 5-minute bars can support, and that the honest planning
  range for SOXL is roughly **13–66 bp/ON-day**, not 62 ± noise. No amount of
  further analysis of 5-minute OHLCV can narrow it — the information needed
  is intrabar sequencing, which the data does not contain.
- It is the same phenomenon `STRATEGY_SPEC.md` V2 reports from the other
  direction: *"instant re-entry below the standing session high is worth
  +47.9 bp/day of the core's 65.6."* V2 read that as the strategy's
  mechanism. It is at least partly a fill-model artifact, and V2's number is
  the size of the exposure, independently derived.
- It is **not** covered by the v5 correction, which fixed same-bar
  trigger-and-target lookahead (`v5_corrected_rerun.py`). Re-entry pricing
  inside the exit bar survived that fix.
- Assumption **A2** names the general class ("true sub-bar sequencing is
  unknown... cuts both ways; net effect unknown"). Its magnitude had not been
  measured. It does not cut both ways here: it runs one direction, and it is
  most of the edge.

### Why this makes paper trading *more* valuable, not less

`PHASE2_PLAN.md` §1 argued that paper cannot validate A1 because IBKR's paper
fills are simulated and do not model queue position. **S10 is different and
paper does test it**, because it is a question of time ordering rather than
of queue: a re-entry order sent after an exit can only fill against prints
that occur after it is sent. If the backtest's re-entry prices are not
achievable, paper fills will show it — in the fill prices themselves, within
days, on the very first ON-days.

The daily shadow-parity report (Stage 6) is the instrument: it replays each
session's own bars through this harness and diffs the simulated fills against
the real ones. S10 predicts a systematic gap on same-bar re-entries
specifically, which is a sharper and faster test than watching aggregate bp.

### Recommendations

1. **Change no parameter.** This is a measurement problem, not a strategy
   problem, and §11's prohibition on re-optimisation applies with full force.
2. **Launch the paper run** — it is the fastest available evidence, and S10
   is diagnosable in its first week.
3. **Treat `IMPLEMENTATION_SPEC.md` §8's baselines as an upper bound**, not
   as the null hypothesis, until paper fills say otherwise. A live run at 20
   bp/ON-day would be consistent with this finding and is *not*, on its own,
   evidence that the engine is broken.
4. **Get 1-minute bars for 2022 and 2026** and re-run these three fill
   models. `STRATEGY_SPEC.md` §3 already lists this as build priority 3 for
   exactly this reason (A1/A2). It is now the highest-value offline work in
   the project, and it is a data-fetch away.

---

## S10 measured at 1-minute resolution (2026-07-31)

1-minute RTH bars fetched from IBKR, 1,653 sessions, 2020-07-16 → 2026-07-21.
Decisions stay on the 5-minute clock; only the assumed fill price changes.

| fill bars | target delay | fill model | bp/ON-day | Sharpe | trades |
|---|---|---|---:|---:|---:|
| 5-minute | decision_bar | **spec** | **65.9** | **3.14** | 2,460 |
| 5-minute | decision_bar | no_better | 12.6 | 0.62 | 2,338 |
| 5-minute | decision_bar | next_bar | 21.4 | 1.18 | 2,322 |
| **1-minute** | decision_bar | **spec** | **42.5** | **2.17** | 2,393 |
| 1-minute | decision_bar | no_better | 12.5 | 0.64 | 2,337 |
| 1-minute | decision_bar | next_bar | 20.7 | 1.12 | 2,347 |
| 1-minute | fill_bar | spec | 42.8 | 2.22 | 2,413 |
| 1-minute | fill_bar | no_better | 14.4 | 0.75 | 2,349 |
| 1-minute | fill_bar | next_bar | 19.8 | 1.08 | 2,360 |

**Refining the fill resolution five-fold removes 23.4 bp — 35% of the measured
edge.** Three findings behind that number:

1. **`target_delay` is not load-bearing.** The prediction that faster target
   fills would offset the loss was wrong: `fill_bar` adds +0.3 bp. §2.6's
   anti-lookahead patch, calibrated on 5-minute bars, costs almost nothing at
   finer resolution.
2. **The conservative models are resolution-invariant** — `no_better` 12.6 →
   12.5, `next_bar` 21.4 → 20.7 — while `spec` fell 23.4. They are measuring
   something that does not depend on bar width, and `spec` converges toward
   them as resolution improves. That makes them a floor rather than an
   artifact of coarse data.
3. **The dependency survives the refinement.** 45% of entries are still
   same-bar re-entries at 1-minute, and `spec` − `no_better` is still 30 bp.
   Most of the *remaining* edge rests on within-minute sequencing.

**Planning range: ~13–43 bp/ON-day gross**, against the published 65.6. Net of
the $75K-sleeve cost of 3.2 bp: ~39 bp at the optimistic bound, ~9–11 bp at
the conservative one. Positive under every model tested.

### This invalidates §8's monitoring baselines

`IMPLEMENTATION_SPEC.md` §8 publishes **61.9 net bp/ON-day** for SOXL and
instructs the live system to investigate >20% deviations as structural
breaks. If the true value is nearer 39, a correctly functioning paper run
reads as a 35% miss on day one — the same failure mode Phase 1 corrected §8
for once already, one resolution deeper. **The baselines must be revised or
annotated before Phase 2 starts**, and the revision belongs to whoever owns
the strategy document, not to this harness.

### Data caveat, quantified and immaterial

The 1-minute file does not aggregate exactly to the 5-minute file: 8.8% of
bars differ by more than 1 bp, worst 90 bp on 2021-02-24, confined to 160
pre-split sessions. Those sessions hold **26 of 779 ON-days (3.3%) and −0.7%
of total P&L** — `thr80` needs 120 prior sessions, so the first ON-day is
2021-01-06 and most of the affected range never traded. It cannot change the
result above.

It is still unexplained, and it matters for Stage 2 for a different reason:
if IBKR's history does not reproduce the research record, `thr80` continuity
across the seam needs checking before the live engine relies on it.

---

## The 1-minute study (harness built, data outstanding)

S10's range cannot be narrowed with 5-minute data, so the next step is finer
bars. The harness is built and tested; it needs the data.

**The strategy's clock does not change.** The anchor ratchet, the 11:00
activation and the counters are defined on 5-minute bars (§2.5) and every
validated result depends on that cadence. `intrabar.py` separates the two
clocks: decisions stay on the 5-minute series, and only the price a fill is
assumed to occur at moves to 1-minute resolution.

Two switches, both simulator-side:

| switch | values | meaning |
|---|---|---|
| `fill_model` | `spec` / `no_better` / `next_bar` | as S10, but "same bar" now means the same *minute* |
| `target_delay` | `decision_bar` / `fill_bar` | §2.6's "the target may fill from the next bar onward" — the next 5-minute bar (the validated reading) or the next fill bar |

`target_delay` matters as much as `fill_model` and pushes the other way: at
5-minute resolution the rule forces a profitable position to wait up to five
minutes before its target can fill, which is over-conservative for a resting
limit order. Expect the 1-minute run to *raise* target fills while *shrinking*
same-bar re-entry. The net direction is genuinely unknown — which is the point
of measuring it.

### Running it

```bash
# on the Mac, with TWS running (~90 min per symbol at the default pacing)
python3 band_lab/live/fetch_1min.py --symbol SOXL --start 2022-01-01
python3 band_lab/live/fetch_1min.py --symbol SOXS --start 2022-01-01

python3 band_lab/live/intrabar.py --symbol SOXL --check   # data-quality gate
python3 band_lab/live/intrabar.py --symbol SOXL           # the 9-row table
```

`--check` aggregates the 1-minute bars back to 5 minutes and diffs them
against the file every validated number came from. If that does not pass,
nothing downstream is worth reading.

### What the existing documents already say about this

Reviewed 2026-07-31, because it changes how this study should be read.

**No 1-minute work had ever been done in this project.** Every reference to
1-minute data across `band_lab` is one of three things: the `Better with:`
field of a V-programme's prespecified test template (whose companion
`Data now:` field always reads "sufficient — 5-min bars regenerate every
trade"); an assumption-register entry marking A1/A2 **Untested**; or a
recommendation for future work. The repository held no 1-minute file until
2026-07-31.

That makes this study the discharge of two standing items:

- `MASTER_STRATEGY_DOCUMENT.md` §7 limitations, item 1 — *"Sub-5-minute fill
  sequencing (A1/A2)... **This is the highest-priority item for the
  validator.**"*
- §7's third-party validation checklist item **(c)** — *"obtain 1-minute data
  for 2022 and 2026 and re-test fills."* (Item (b), the clean-room
  re-implementation, was Phase 1.)

**Two consequences that are easy to miss.**

First, §2.6's anti-lookahead rule is a *5-minute-specific* patch. V5 found the
same class of defect — "an unknowable intrabar sequence booked as certain
profit" — and fixed it with "target fills from the next bar onward", which on
5-minute bars forces a five-minute wait before a winner may be taken. That is
the `decision_bar` reading. `target_delay=fill_bar` asks what the rule means
once bars are not five minutes wide, and is arguably closer to its intent,
since live the OCA genuinely rests from the moment of fill. The 1-minute run
therefore re-tests the v5 fix's calibration, not only S10.

Second, **V5 named this data as the condition for re-opening its own
verdict** — on rejecting the 09:35 start: *"its trades live in the bars where
touch-fill assumptions are least believable (revisit only if 1-min data +
cost model ever land)."* V5 also records that the bug's effect "scales with
bar range: rampant 09:30–10:00, mild at midday", the same scaling that drives
S10. The condition is now met. Several other decisions were taken on data
their own programme flagged as coarser than ideal (V11 T2/T4, V8 T4, V1/V3
T2, V2 T3).

None of that is licence to re-open anything. §11 requires a deliberate,
documented, re-validated decision, and a fill-resolution study is not one —
it must not become a start-time re-optimisation by the back door. Recorded
here so the option is visible and explicit rather than stumbled into.

### Split adjustment — the trap the first real fetch hit

The repository's 5-minute CSVs hold SOXL's **unadjusted** pre-2021-03-02
prices and are divided by 15 at read time. Data fetched fresh from IBKR comes
back **already adjusted**. Adjusting it again puts the fill stream at 1/15 the
scale of the decision stream, and the failure is not obvious: entries fill at
the low scale while the 15:55 flatten books at the high one, so the table
reads as an enormous edge rather than as an error (the first run reported
3,784 bp/ON-day).

Three things now prevent it:

- `load_1min_sessions(split_adjust=False)` is the **default**, which is
  correct for IBKR data. Pass `--split-adjust` only for genuinely unadjusted
  vendor files.
- `--check` reports the 1-min/5-min price ratio either side of each split
  date and names the fix: a ratio of ~0.0667 means adjusted twice, ~15 means
  not adjusted at all.
- A mismatch of more than 5% now raises `PriceScaleError` at replay time
  rather than producing a table.

`intrabar.py` also refuses to run the study at all when `--check` fails
(`--force` overrides).

### Two traps this harness already avoids

- **Truncated feature history.** ATR5 needs 5 prior sessions and thr80 needs
  120. Rebuilding the history from only the 1-minute window stands down every
  early session and silently deletes it from the sample. Features are always
  computed from the full 5-minute record, as they are live.
- **Comparing different harnesses.** Fed 5-minute bars as both streams,
  `intrabar.py` reproduces `replay.py` exactly (asserted for both sleeves in
  `test_live_intrabar.py`), so a 1-minute difference is a resolution effect
  rather than an artifact of a second implementation.

### Known risk on the data

IBKR's retention for 1-minute bars may not reach 2022. The fetcher stops
cleanly when the server stops returning history and reports the earliest
session it obtained. If it falls short, any vendor's RTH 1-minute bars in the
same CSV schema will do — the study only needs
`Date,Open,High,Low,Close,Volume`.

---

## What Stage 1 does not cover

The broker adapter, order management, persistence, safety systems and
reporting (Stages 2–7 of `PHASE2_PLAN.md`). The state machine here emits
`Intent`s and is driven by a simulator; nothing in this stage has ever
connected to IBKR.
