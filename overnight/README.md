# overnight — the live strategy

The specification is [`STRATEGY.md`](STRATEGY.md). This is the code half.

```bash
python3 overnight/parity.py            # P0's gate: exits 0 only on exact agreement
python3 -m pytest overnight/tests -q   # 47 tests
```

## What is here (P0 complete)

| module | what it is |
|---|---|
| `constants.py` | the specification's numbers, once. Nothing re-types one |
| `features.py` | daily bars → RV20 and the walk-forward threshold. No decisions |
| `core.py` | the decision, sizing and cost arithmetic. Pure: no broker, no I/O, no clock, **no dates** |
| `parity.py` | the gate — replays `core` over the real history and diffs it against the research ledger |

## The two invariants worth knowing before you change anything

**The RV window ends at D−1.** An MOC order must reach NYSE markets by 15:50 ET
(`IBKR Order types.md:13`), so day D's close cannot be an input to the decision
that submits it. `features.window_end_index` is the only place that arithmetic
lives, and `test_realised_vol_does_NOT_see_the_decision_day_move` fails loudly if
it is ever dropped — including a self-check that the test is not blind.

**The threshold is walk-forward, never a constant.** `threshold_at` sees only
history strictly before the day it is asked about.
`test_build_never_lets_a_day_set_its_own_threshold` replays the whole series and
re-derives every cut from the days before it.

## The gate, and why the mutation tests exist

`parity.py` reproduces all **895** decisions in
`retreat_lab/out/proposed_ledger.csv` — the same leg on every day and the same
return to four decimal places. 580 SOXL, 204 XLU, 111 flat.

A harness that passes on its first run proves nothing until it has been shown to
fail. `test_parity.py` mutates the specification four ways — shifts the
percentile, changes the cost, drops the RV lag, reverses leg precedence — and
asserts the gate goes red on each. If one of those ever passes, the gate has
stopped testing.

## Not here yet

`schedule.py`, `run.py` and `replay.py` — P1 onward. The broker, order, store,
report, status and watchdog layers are reused from `band_lab/live/` rather than
rewritten; see `STRATEGY.md` §5.

## A note on running the band_lab suite here

`band_lab/live/tests/test_live_broker_guards.py` has 7 tests that import
`ib_async` to assert this codebase's transcribed constants match the installed
library. They fail in any environment without it — including this container —
and pass where TWS runs. That is the point of them; they are not a defect.
