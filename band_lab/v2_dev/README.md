# band_lab/v2_dev — strategy **v2.0-dev** (DEVELOPMENT)

> ## ⚠️ NOTHING IN HERE IS APPROVED FOR TRADING
>
> | | |
> |---|---|
> | **v1.0 — PRODUCTION** | the locked strategy. `band_lab/IMPLEMENTATION_SPEC.md` §12, `band_lab/phase1/`, `band_lab/live/`. Every §12 constant unchanged since lock. This is what goes to the paper account. |
> | **v2.0-dev — DEVELOPMENT** | this directory. Re-tests specific locked parameters against the 1-minute fill data. **No result here changes v1.0 unless it clears a prespecified adoption bar and is signed off.** |

## Why this line exists

`band_lab/live/PHASE2_PARITY.md` S10–S12 established that the 5-minute
backtest priced roughly half of its own edge at prices that were not
available in time order. The 1-minute data corrects that.

That creates a specific, bounded problem. Quoting the reasoning rather than
restating it: **when a backtest contains a bias that inflates one mechanism,
every parameter that was chosen by sweeping — and that controls how often
that mechanism fires — was tuned on inflated feedback.** The biased mechanism
here is re-entry immediately after an exit. So the parameters that set the
churn rate are the ones whose original verdicts are least trustworthy.

That is the entire scope of v2.0-dev. It is not a licence to re-sweep the
strategy.

## The discipline this line operates under

`IMPLEMENTATION_SPEC.md` §11 forbids parameter optimisation. v2.0-dev does not
overturn that; it is the "deliberate, documented, re-validated decision" §11
names as the only route. Concretely:

1. **The adoption bar is written down before the test is run**, in the test
   document, and is not edited afterwards. (`V14_PAIR_PROTOCOL.md` set this
   precedent — it prespecified its bar before any capital moved.)
2. **A fixed, small number of variables per program.** We have one cleaner
   dataset and twelve parameters; sweeping all of them on the same window
   would manufacture a better backtest and a worse strategy — the exact
   failure that produced the current problem.
3. **Walk-forward, not full-sample.** A full-sample winner is a hypothesis,
   not a result.
4. **One engine, not two.** The research harness drives
   `band_lab/live/sleeve.py` — the same state machine the live engine uses —
   through configuration, rather than forking it. `PHASE2_PARITY.md` warns
   against comparing two harnesses; a forked research engine is that problem
   by construction.

## What changed in the production code to enable this

`SleeveConfig` gained three fields — `dip_pct` (V1), `target_pct` (V3),
`stop_pct` (V4) — which **default to the locked §12 values**. Production
behaviour is bit-identical and is asserted as such: 82 live tests, 59 phase1
tests, `phase1/parity.py` reproducing all 16 published §8 numbers, and
`live/replay.py` Stage 1 equivalence all pass unchanged.
`spec_constants.validate_config` still rejects a live engine that moves them,
so the production path cannot silently drift.

## Programs

| program | variables | status |
|---|---|---|
| [V16_CHURN_JOINT_TEST.md](V16_CHURN_JOINT_TEST.md) | V1 dip depth × V3 profit target × V7 trade cap | **complete — NOT ADOPTED** |
| [V17_TRADE_CAP_TEST.md](V17_TRADE_CAP_TEST.md) | V7 trade cap, tested at the margin | **complete — NOT ADOPTED** |
| [V18_VOL_GATE_TEST.md](V18_VOL_GATE_TEST.md) | V10 vol gate: cutoff × lookback | **complete — NOT ADOPTED** |

## Tooling

[**RESEARCH_AGENT_PRD.md**](RESEARCH_AGENT_PRD.md) — **proposed, not built.** An
agent that runs a programme through phases P2–P5 of this discipline. Its
integrity model exists for one reason: an agent that both writes the adoption
bar and grades results against it will rationalise, so the bar is hash-committed
before execution and the role that sees the results never sees the bar. It has
no mechanism to adopt anything. Acceptance is reproducing V18's published
NOT ADOPTED from its framing alone.

Wider context — where this sits relative to models, agents and retrieval:
[`../AI_ROADMAP.md`](../AI_ROADMAP.md).

## Run

```bash
python3 band_lab/v2_dev/churn_joint_test.py            # full program
python3 band_lab/v2_dev/churn_joint_test.py --quick    # coarse grid, for iteration
python3 band_lab/v2_dev/trade_cap_test.py             # V17
python3 band_lab/v2_dev/vol_gate_test.py              # V18
```
