# Stage 1 — Live State Machine Equivalence

**Result: PASS.** The state machine that will run against IBKR reproduces
`band_lab/phase1/spec_engine.py` (`SPEC_LITERAL`) exactly on the historical
5-minute bars — 779 SOXL and 793 SOXS ON-days, **zero** difference in daily
P&L, identical gate and filter reasons on every session, and identical entry
price, exit price, quantity and outcome on all 5,118 trades.

```bash
python3 band_lab/live/replay.py          # equivalence report, exit 0 == green
python3 -m pytest band_lab/live -v       # 58 tests when this was written; more now
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

## S11 — the 1-minute study, both sleeves: the edge survives at ~54–64%

**Both 1-minute files are in**, in git-lfs, and neither needed a fetch:

| file | bars | coverage |
|---|---:|---|
| `SOXL_1min.csv` | 642,510 | 2019-12-31 → 2026-07-30 |
| `SOXS_1min.csv` | 642,563 | 2019-12-31 → 2026-07-31 |

Both reach far past the 2022 target `fetch_1min.py` warned IBKR's retention
might not deliver. Run on the 2022+ window, which is what
`IMPLEMENTATION_SPEC.md` asks for and which excludes the pre-2022 data-quality
problem in S12:

```bash
python3 band_lab/live/intrabar.py --symbol SOXL --start 2022-01-01
python3 band_lab/live/intrabar.py --symbol SOXS --start 2022-01-01
```

| fill bars | target delay | fill model | SOXL bp | SOXL Sharpe | SOXS bp | SOXS Sharpe |
|---|---|---|---:|---:|---:|---:|
| 5-minute | decision_bar | **spec** | **66.8** | 3.11 | **63.0** | 2.91 |
| 5-minute | decision_bar | no_better | 10.5 | 0.51 | 4.4 | 0.21 |
| 5-minute | decision_bar | next_bar | 21.8 | 1.18 | 2.5 | 0.13 |
| **1-minute** | decision_bar | **spec** | **42.5** | **2.14** | **34.2** | **1.70** |
| 1-minute | decision_bar | no_better | 10.3 | 0.52 | −0.9 | −0.05 |
| 1-minute | decision_bar | next_bar | 18.3 | 0.97 | 3.5 | 0.18 |
| **1-minute** | fill_bar | **spec** | **43.0** | **2.20** | **39.8** | **2.01** |
| 1-minute | fill_bar | no_better | 12.6 | 0.64 | −1.5 | −0.08 |
| 1-minute | fill_bar | next_bar | 17.3 | 0.92 | 3.5 | 0.19 |

679 SOXL ON days, 691 SOXS, on every row of their column.

### What it settles

1. **S10's range narrows sharply.** SOXL goes from "13–66" to **42–43**; SOXS
   from "2–61" to **34–40**. At five times the resolution the spec model gives
   up 24.3 bp on SOXL and 28.8 on SOXS — but both land far above the harsh
   floors. `no_better` and `next_bar` were too pessimistic: real 1-minute paths
   do return below the price just sold, and most of the same-bar re-entry edge
   is genuinely fillable.
2. **The direction the plan called "genuinely unknown" is down**, for both.
   Same-bar re-entries fall from 50.3% → 46.3% of entries on SOXL and
   51.4% → 46.0% on SOXS. The loss from finer re-entry pricing dominates the
   gain from earlier target fills in both sleeves.
3. **`target_delay` matters on SOXS but not on SOXL** — 0.5 bp on SOXL
   (42.5 → 43.0), **5.6 bp on SOXS** (34.2 → 39.8). The doc expected it to
   "matter as much as `fill_model`"; that holds only for SOXS, and even there
   `fill_model` is 5x larger. The validated `decision_bar` reading is the
   conservative one in both sleeves, so keeping it costs at most 5.6 bp and
   creates no live ambiguity.
4. **SOXS is the more fragile sleeve, and the finer data widens the gap.**
   Its `no_better` floor is *negative* at 1-minute resolution (−0.9 / −1.5 bp)
   where SOXL's stays at +10 to +13. Retention under the validated reading is
   **54% for SOXS against 64% for SOXL**. SOXS's edge is more concentrated in
   same-bar re-entry, exactly as S10's 5-minute counts implied (75.9 of 61.2
   bp/ON-day, vs SOXL's 62.5 of 65.9).
5. **Neither result is a one-period artifact, but SOXS has a bad year.**

| year | SOXL ON | SOXL 5-min | SOXL 1-min | ret | SOXS ON | SOXS 5-min | SOXS 1-min | ret |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 184 | 79.4 | 52.5 | 66% | 180 | 87.4 | 58.3 | 67% |
| 2023 | 140 | 84.2 | 52.3 | 62% | 149 | 27.1 | **−6.5** | −24% |
| 2024 | 151 | 59.2 | 38.0 | 64% | 159 | 38.1 | 18.4 | 48% |
| 2025 | 127 | 44.8 | 18.8 | 42% | 115 | 100.5 | 58.8 | 58% |
| 2026 | 77 | 56.2 | 49.1 | 87% | 88 | 70.3 | 50.6 | 72% |
| **all** | **679** | **66.8** | **42.5** | **64%** | **691** | **63.0** | **34.2** | **54%** |

SOXL never flips negative in any year. **SOXS 2023 does** — +27.1 bp at
5-minute resolution becomes −6.5 at 1-minute. That is the single most
important row in this table: it is a full year in which the sleeve's entire
apparent edge is a fill-resolution artifact. Worst day is −8.00% on all four
series (the stop binds identically). Positive days: SOXL 64.1% → 61.4%,
SOXS 57.6% → 53.4%.

### The pair

The two sleeves at w=0.50 each, which is what §2.4 actually deploys:

| fill model | days | bp/day | Sharpe | worst day |
|---|---:|---:|---:|---:|
| 5-minute spec | 818 | 54.4 | 5.74 | −4.00% |
| **1-minute spec** | 818 | **32.1** | **3.83** | −4.57% |
| 1-minute spec, fill_bar | 818 | 34.7 | 4.17 | −4.57% |

Pairing survives the resolution change well: 59% retention against 54–64% for
the individual sleeves, and the Sharpe stays high because the worst day nearly
halves (−8.00% → −4.57%) on 552 both-on days. The diversification V14 measured
is not a fill-model artifact — it is the most robust finding here.

### What it does not settle

Sub-minute sequencing is still unresolved, and the same argument applies one
level down: a 1-minute bar that re-enters below its own exit price is making
the same assumption S10 objected to, over a 60-second window instead of 300.
Expect real fills below these figures, not at them. The direction of the
remaining error is known — it only runs one way.

**Recommendation, unchanged from S10: change no parameter.** Read
`IMPLEMENTATION_SPEC.md` §8's 61.9 / 48.1 net bp/ON-day as upper bounds, and
plan on roughly **40 bp/ON-day for SOXL and 30 for SOXS**. A paper run at
20–40 bp is consistent with this and is not evidence the engine is broken.
Treat SOXS's contribution as the less certain half of the pair.

---

## S12 — the 1-minute file is split-adjusted; the 5-minute file is not

The `--check` gate earned its place immediately. `fetch_1min.py` documents
"SOXL's 2021 split is applied at *read* time by `intrabar.py`, exactly as for
the 5-minute files — do not pre-adjust here", and `load_1min_sessions`
divided every pre-2021-03-02 price by 15 on that basis. The delivered file is
already on the adjusted grid, so it was divided a second time:

| | 2021-02-16 09:30 |
|---|---|
| 5-minute file (raw) | 710.05 → ÷15 → 47.34 ✓ |
| 1-minute file (already adjusted) | 47.34 → ÷15 → **3.16** ✗ |

Volume settles it: the 1-minute file's volume is exactly **15.00×** the
5-minute file's before the split and **1.00×** after — a fully adjusted
series, prices and volumes both. The gate reported a worst OHLC difference of
**44.66**.

`load_1min_sessions` now **detects** the convention (`needs_split_adjustment`)
instead of assuming it, because the study explicitly accepts any vendor's CSV
and the vendor decides this, not the repository. That took the worst
difference from 44.66 to 0.357.

### A cent is not a threshold on a back-adjusted series

SOXS forced a second correction. The gate's rule was "worst difference under a
cent", which is well defined only on a real $0.01 tick grid.
`SOXS_5min_6Years.csv` is the back-adjusted S7 series and opens at
**$1,075,204/share**: there, a cent is 2 parts per billion, and no correct
file could ever pass. The units of a back-adjusted series are an artifact of
its reverse-split history and carry no information.

The tolerance is now **relative** (`PARITY_TOL_BP = 1.0`), which is what the
strategy itself is — §2 is written in percentages throughout. This is not a
relaxation: 1 bp is *tighter* than a cent everywhere SOXL actually trades
(1 bp of $47 is half a cent), and SOXL fails on exactly the same two sessions
under both rules. It makes the SOXS gate expressible at all. Both absolute
and relative figures are printed.

### Why 2022+ is the right window, for both sleeves

Worst relative difference per session, by year — the pattern is the same in
both sleeves and it is not about the split:

| year | SOXL median | SOXL max | SOXL >1bp | SOXS median | SOXS max | SOXS >1bp |
|---|---:|---:|---:|---:|---:|---:|
| 2020 | 25.7 bp | 63.4 | 118 / 118 | 15.4 bp | 48.5 | 80 / 113 |
| 2021 | 0.0 | 90.8 | 40 / 252 | 0.0 | 60.8 | 66 / 252 |
| 2022 | 0.0 | 0.00 | **0** / 251 | 0.0 | 28.2 | **1** / 251 |
| 2023 | 0.0 | 32.9 | **1** / 250 | 0.0 | 57.7 | **1** / 250 |
| 2024 | 0.0 | 0.00 | **0** / 252 | 0.0 | 0.00 | **0** / 252 |
| 2025 | 0.0 | 0.00 | **0** / 250 | 0.0 | 0.00 | **0** / 250 |
| 2026 | 0.0 | 2.58 | **1** / 137 | 0.0 | 0.00 | **0** / 140 |

2020–21 is dirty in **both** symbols; 2022 onward is essentially exact in
both. SOXL's dirty sessions coincide with its pre-split window, but SOXS has
no split adjustment applied at all and is dirty over the same span — so the
cause is a source/vintage boundary in the 5-minute files at the end of 2021,
not the split arithmetic. No 5-minute bar anywhere lacks 1-minute coverage.

Final gate state on the spec's window:

| window | sessions | worst | bars over 1 bp | verdict |
|---|---:|---:|---|---|
| SOXL 2022+ | 1,140 | 32.8 bp | 2 / 88,596 (0.0023%) | FAIL |
| SOXS 2022+ | 1,143 | 57.0 bp | 2 / 88,830 (0.0023%) | FAIL |

Both still return non-zero, each on **two disputed prints in ~88,700 bars**.
The strict rule has deliberately **not** been loosened to get a green light —
that is the failure mode this project's discipline exists to prevent. Instead
the gate reports per-bar and per-session counts alongside the worst case, so
the two failure modes are distinguishable: a wrong-basis series fails on
nearly every session (as the 44.66 did), while this fails on two.

**2023-06-05 is one of the two in both sleeves**, which is positive evidence:
a shared bad print in the 5-minute source, not a fetch error in either file.
S11 is run on the 2022+ window on that basis, stated here rather than decided
silently in code.

---

## The 1-minute study — how it works

S10's range cannot be narrowed with 5-minute data, so the next step is finer
bars. Both sleeves are now measured (S11); this section is the method.

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

`target_delay` was expected to matter as much as `fill_model` and to push the
other way: at 5-minute resolution the rule forces a profitable position to
wait up to five minutes before its target can fill, which is over-conservative
for a resting limit order. The 1-minute run should *raise* target fills while
*shrinking* same-bar re-entry, and the net direction was genuinely unknown.

**Measured (S11): the net direction is down, and the expectation about
`target_delay` held only for SOXS** — 5.6 bp there, 0.5 bp on SOXL, against
`fill_model`'s 24–29 bp in both.

### Running it

```bash
# both files are in git-lfs; neither needs a fetch
git lfs pull --include="SOXL_1min.csv,SOXS_1min.csv,SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"

for S in SOXL SOXS; do
  python3 band_lab/live/intrabar.py --symbol $S --check --start 2022-01-01
  python3 band_lab/live/intrabar.py --symbol $S --start 2022-01-01 --force  # 9-row table
done
```

> **`--start 2022-01-01` is not optional, and `--force` is needed for the table.**
> Run with no arguments and the window spans 2020–21, which this section
> documents as a dirty source/vintage boundary: expect a worst case near 90 bp
> and **~160 of 1,510 SOXL sessions** over 1 bp (118 from 2020 + 40 from 2021 +
> the 2 disputed prints). That is the known result reproducing itself, not a new
> fault. On the 2022+ window the gate still exits non-zero on those two prints —
> deliberately, per S12 — so the study refuses to run without `--force`.
>
> `--force` was referenced at the refusal site but never defined as an argument
> until 2026-08-03, so that path raised `AttributeError` rather than printing the
> refusal it describes. Fixed.

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

*Settled for both:* the delivered files reach 2019-12-31, well past the
target. Retention was never the binding constraint; the price basis was (S12).

### SOXS arrived on the correct basis — but check it on any refetch

`SOXS_5min_6Years.csv` is the back-adjusted S7 series and `SPLIT_ADJUSTMENTS`
has **no** SOXS entry, so `load_1min_sessions` applies nothing: the 1-minute
file has to already be on that same back-adjusted basis. The delivered
`SOXS_1min.csv` is — it opens at **$5,160,020.64/share** on 2019-12-31 and
decays to ~$51 by 2026-07-31, tracking the 5-minute file throughout (which
opens at $1,075,204.30 on 2020-07-23, the first session the two share).

That is a fortunate outcome, not a guaranteed one, and it is worth stating
what would have happened otherwise: SOXS traded near $25–30 in early 2022, so
a **raw** IBKR fetch would differ from the validated series by ~2,000x in the
2022 window alone, and — unlike SOXL's single 15:1 split — there is no one
ratio to divide by, because the reverse splits are repeated and ongoing. On a
wrong basis the §2.4 sizing arithmetic silently produces near-zero
quantities: the S7 failure, which zeroed 248 sessions without erroring.

So on any refetch or vendor change, run `intrabar.py --symbol SOXS --check`
**first**. It is designed for exactly this and now fails in relative terms, so
it works on a series quoted in millions.

---

## What Stage 1 does not cover

The broker adapter, order management, persistence, safety systems and
reporting (Stages 2–7 of `PHASE2_PLAN.md`). The state machine here emits
`Intent`s and is driven by a simulator; nothing in this stage has ever
connected to IBKR.
