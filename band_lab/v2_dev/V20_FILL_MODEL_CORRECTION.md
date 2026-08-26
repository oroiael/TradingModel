# V20 — The same-bar re-entry fill model, falsified against live fills

**Line:** measurement. This corrects the *instrument*, not the strategy.

**Status: BAR PRESPECIFIED, WRITTEN BEFORE THE RUN. Results appended below.**

Run: `python3 band_lab/v2_dev/fill_model_correction.py`

---

## 1. This is not a §11 program, and the distinction has to hold

`IMPLEMENTATION_SPEC.md` §11 forbids parameter optimisation. V20 changes **no
strategy parameter**. Every §12 constant — `f`, `w`, the 6.0% ATR5 gate, the 1%
dip, the 1% target, the 4% stop, `MAX_FILLS`, `MAX_STOPS`, the 11:00 start, the
15:55 flatten — is untouched, and `spec_constants.validate_config` still pins
all seven.

What changes is which *simulator assumption* the published baselines are
computed under. That is the same category as the `report.py` parity fix (a
measurement that disagreed with the engine it audited) and the opposite category
from tuning a threshold until the backtest improves.

The distinction is only worth anything if it survives the result being
unwelcome. §6 B1 exists for that reason and is stated before the run.

## 2. What was falsified, and by what

`replay.py` documents the assumption honestly and always has:

> under "spec" an entry that follows an exit *in the same bar* is priced at that
> bar's open — a price that traded before the exit did. See PHASE2_PARITY.md S10.

S10 was identified in Phase 2 and answered with a 35% haircut: publishing
1-minute fills instead of 5-minute, which moved the headline from 61.9/48.1 to
roughly 40/30 bp per ON-day. **That haircut was a simulation of the bias, not a
measurement of it.** The live sessions are the measurement, and they are the
first evidence in the project's history that bears on it directly.

Thirteen sleeve-sessions, 2026-08-13 to 2026-08-26, on the frozen engine
(PR #40, merged 08-12 05:29 ET), 08-17 excluded because its gate was recorded
OFF and the shadow never ran:

```
  trade counts MATCH    n=7   mean live-shadow gap    -14.6 bp
  trade counts DIFFER   n=6   mean live-shadow gap   -135.0 bp
  -> 89% of the total gap sits in sessions where the backtest books a
     round trip the live session never had
```

All ten of those are same-bar re-entries the shadow prices below the exit it
just took:

```
  08-20 SOXS  bar 22: prev exit 46.78   shadow 46.44
  08-20 SOXS  bar 23: prev exit 46.90   shadow 46.73
  08-20 SOXS  bar 25: prev exit 47.20   shadow 47.07
  08-21 SOXL  bar 25: prev exit 120.25  shadow 119.73
  08-24 SOXS  bar 76: prev exit 51.26   live 51.26  shadow 50.66  (+117.91 bp)
```

And the live counter-observation, from the same reports:

```
  §5 Q2 — live re-entry at or worse than the price just sold:  9 of 14
```

Reality pays **more** two times in three when it sells into strength and
immediately re-buys. The `spec` model pays less by construction.

Execution is not the alternative explanation and was checked first: entry fills
average **+2.82 bp** against the quote while the order worked, flatten
spread-crossing **+2.89 bp** — about 5.7 bp round trip against a gap of 70 bp
per sleeve-session. And the live **stop rate is at baseline** (2/30 = 6.7% vs
9.6%, p = 0.44), so nothing is being stopped out that shouldn't be.

## 3. What is being computed

`FILL_MODELS` already carries all three. Nothing new is being invented:

| model | same-bar re-entry priced at | reading |
|---|---|---|
| `spec` | `min(limit, bar.open)` | the falsified incumbent |
| `no_better` | `min(limit, max(bar.open, exit))` | may not be better than the exit it followed |
| `next_bar` | not permitted at all | lower bound |

`no_better` is the correction. `next_bar` is reported beside it because
`no_better` still allows a re-entry *at* the exit price, and live says reality
is nearer `next_bar` than `spec`. The truth is bracketed, not pinpointed, and
publishing a single number would overstate what this establishes.

Both are run at 1-minute fill resolution, 2022+, net of the same per-fill cost
model, so the output is directly comparable to the incumbent baselines in
`phase1/out/monitoring_expectations.csv`.

## 4. What is NOT being tested

- No strategy parameter. See §1.
- Not whether the strategy should keep running. That is a separate decision and
  §6 B4 says what this result can and cannot support.
- Not the live sample's own P&L. Thirty trades cannot estimate an edge; they are
  used here **only** to establish that the `spec` model's same-bar re-entries are
  unavailable, which is a statement about the simulator.

## 5. Projection — written before the run

I expect `no_better` to cut both sleeves materially and `next_bar` to cut them
further, with SOXS hit harder than SOXL because SOXS carries more reloads per
ON-day (3.36 vs 3.17) and therefore more same-bar re-entry opportunities.

I expect the corrected `net_bp_per_ON_day` to land **positive but small** for at
least one sleeve. I hold this loosely: if S10 is most of the published edge
rather than a portion of it, both go to zero or below, and I have no basis to
rule that out. Recording the expectation so §6 B1 can be checked against it.

## 6. The bar — PRESPECIFIED, fixed before the run

**B1. The corrected baselines replace the published ones regardless of the
result.** There is no number at which `spec` is retained. It has been falsified
against real fills; a falsified instrument is not kept because its output is
more attractive. This is written first because it is the decision most likely to
be relitigated after the numbers are visible.

**B2.** If corrected `net_bp_per_ON_day` is **positive for both sleeves**: the
edge survives the honest fill model at a smaller size. Live validation continues
against the new baselines, and live's −4.16% since 08-13 is an ordinary
drawdown against a smaller expectation.

**B3.** If **positive for one sleeve, negative for the other**: the negative
sleeve's published edge was an artifact. Per the V1/V16 precedent, sleeves
disagreeing closes a program rather than licensing a per-sleeve change — but the
combined expectation must be re-stated, because that is what live is measured
against.

**B4.** If **negative or within one standard error of zero for both**: the
strategy has no demonstrated edge under an honest fill model. Paper trading
stops being validation and becomes data collection on a strategy with no prior.
Say so plainly, in those words. Do not deploy capital.

**B5. The detection horizon is recomputed and reported even if it is
inconveniently large.** The 78-active-day figure is `(z·sd/mean)²` at a mean of
29.12 bp/active day. The horizon grows as the inverse square of the mean, so a
halved edge is a quadrupled wait. This must not be quietly dropped.

**B6. Falsification of V20 itself.** If `no_better` changes the trade count by
**less than 5%** against `spec`, then same-bar re-entries are too rare in the
backtest to explain a 70 bp/sleeve-session live gap, my diagnosis in §2 is
wrong, and the live gap needs a different cause. Report that outcome as a
refutation of this document, not as a null result.

**B7.** Stage 1 equivalence must still pass under `spec` after any code change.
The correction is to which model is *published*, never to the engine.

---

# RESULTS

*(appended after the run)*

## VERDICT: **the published edge does not survive an honest same-bar re-entry.**

Under B1 the corrected baselines replace the published ones. They are written to
`v2_dev/out/v20_corrected_baselines.csv`, which `report.py` now reads in
preference to the `spec` file, and the daily report prints which set it used.

```
                        §8 pub(5m)   spec@1min   no_better    next_bar
SOXL  net_bp_per_ON_day      61.90       39.34       +8.95      +13.65
SOXS  net_bp_per_ON_day      48.10       30.29      -10.61       -5.64
account, per active day         --      +29.12       -0.77       +3.28
```

## R1. B6 fired. The criterion was wrong, and that is a disclosure, not a defence.

```
  SOXL: spec 2157 trades -> no_better 2101   (2.6%)   threshold 5%   BELOW
  SOXS: spec 2290 trades -> no_better 2209   (3.5%)   threshold 5%   BELOW
```

B6 said: if the trade count moves less than 5%, same-bar re-entries are too rare
to explain the live gap and §2's diagnosis is refuted. **By the letter of the
bar, V20 is refuted.**

The criterion was mis-specified. It used trade *count* as a proxy for
materiality, and the proxy is invalid here: removing 2.6% of SOXL's trades
removes **77%** of its net edge, and removing 3.5% of SOXS's removes **135%**.
Rarity does not imply immateriality when the trades being removed are not a
random sample — a re-entry priced below the exit it just took is
*systematically* favourable, so a handful of them can carry most of the edge.
The P&L effect is direct output, not inference; B6 could not have detected it
at any threshold on counts.

This follows V17's R1 (a criterion mis-specified, disclosed rather than quietly
corrected). Two things a reader is owed:

- **B1 does not depend on B6.** It says the corrected baselines replace the
  published ones regardless of the result, and it was written first for exactly
  this reason.
- **Discount the pre-registration accordingly.** A criterion wrong in this
  direction is a criterion that could have been wrong in the other. The defence
  of V20 is the measurement, not the bar.

## R2. `next_bar` beats `no_better` — which is the cleanest confirmation available

SOXL +13.65 vs +8.95; SOXS −5.64 vs −10.61. **Forbidding the same-bar re-entry
outright is better than permitting it at the exit price.** So the same-bar
re-entries priced honestly are, on net, *losers*: every bit of their value came
from the price improvement that does not exist. Nothing about the strategy
requires them; the backtest's edge did.

## R3. B4 is the branch that fires

```
  no_better   SOXL   +8.95 bp/ON-day   sem 11.91   95% CI [-14.40, +32.30]
              SOXS  -10.61 bp/ON-day   sem 11.70   95% CI [-33.55, +12.32]
  next_bar    SOXL  +13.65             sem 11.39   95% CI [ -8.67, +35.98]
              SOXS   -5.64             sem 11.22   95% CI [-27.63, +16.34]
```

Zero is inside every interval. Under `no_better` both sleeves are within one
standard error of zero, which is B4 verbatim: **the strategy has no demonstrated
edge under an honest fill model.** Paper trading stops being validation and
becomes data collection on a strategy with no prior. Do not deploy capital.

Stated as B4 requires: not "the strategy is broken" — 4.5 years and 4,300 trades
cannot distinguish a small positive edge from zero here. What is established is
that the *evidence for* an edge was the fill model.

## R4. B5 — the detection horizon, reported because it is inconvenient

```
  spec (falsified)   +29.12 bp ->     78 active days
  no_better           -0.77 bp -> no positive edge to detect
  next_bar            +3.28 bp ->  5,464 active days  = ~30 calendar years
```

Every "wait N days and we will know" figure in this project descends from the
falsified mean. The honest answer to *when will live tell us whether this
works* is **never, at any plausible horizon.**

## R5. Live, re-tested against the corrected baselines

```
  SOXL  live -47.02 bp/ON-day (n=6)  vs corrected +8.95   z=-0.44  p=0.33  INSIDE
  SOXS  live -52.91 bp/ON-day (n=7)  vs corrected -10.61  z=-0.36  p=0.36  INSIDE
  drawdown since 08-13  -4.16%  vs 3.60% expected sd over 8 active days  z=-1.15
```

Against the corrected baseline, **live is unremarkable.** Nothing in three weeks
of sessions is evidence of anything except that the baseline was wrong.

Outcome mix, retested: `stop_%` 6.7% vs a corrected 11.0% is now **normal**
(p=0.34). `target_%` 50.0% vs 67.3% (p=0.037) and `flatten_%` 43.3% vs 21.7%
(p=0.007) remain breached — live still under-trades even the corrected model
(2.31 fills/sleeve-session vs 3.09–3.20). At n=30 that is unresolved and is the
one live question V20 does not answer.

## R6. Projection scorecard (§5, written before the run)

| §5 said | outcome |
|---|---|
| `no_better` cuts both sleeves materially | **right** — −77% / −135% |
| `next_bar` cuts them further | **wrong** — it cuts them *less*; see R2 |
| SOXS hit harder than SOXL | **right** — SOXS goes negative, SOXL does not |
| at least one sleeve stays positive but small | **right, and it is the weakest claim here** — SOXL +8.95 with zero inside its CI |

## R7. What is NOT concluded

- No strategy parameter changes. All seven §12 constants unchanged;
  `test_config_rejects_strategy_parameter_changes` and the other 59 phase1 tests
  pass at HEAD (B7).
- `no_better` is not proven correct — it is *less wrong* than `spec`, on 14 live
  re-entries. `next_bar` brackets it. Publishing one number would overstate this.
- The live under-trading in R5 is unexplained and is the next question.
