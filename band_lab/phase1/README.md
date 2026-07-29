# band_lab/phase1 — clean-room backtest parity harness

Phase 1 of `band_lab/IMPLEMENTATION_SPEC.md` §9: re-implement the trading
rules of §2 **from that document alone**, run them over the repository's
5-minute history, and show that the result matches the research engine.

**Status: PASS.** Findings, the eight spec ambiguities it surfaced, and the
open decisions are in **[PHASE1_PARITY.md](PHASE1_PARITY.md)**.

## Layout

| file | role |
|---|---|
| `spec_constants.py` | §12 constants verbatim + the §6.8 startup config validator |
| `spec_engine.py` | the clean-room engine (§2 only — imports nothing from the research lab) |
| `parity.py` | parity vs the research engine, `v14_*.csv` rebuild, as-built gap attribution, §8 baseline guard |
| `cost_model.py` | per-trade cost model — reviews and replaces the flat v14 charge ([COST_MODEL.md](COST_MODEL.md)) |
| `test_spec_engine.py` | 48 acceptance tests for §10 items 1–8, 13, 14 |
| `out/` | generated artifacts — summary tables are committed, the per-day/per-trade logs are gitignored and regenerable |

## Setup

The 5-minute history is stored with git-lfs and is a pointer file on a fresh
clone:

```bash
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
pip install pandas numpy pytest
```

## Run

```bash
python3 band_lab/phase1/parity.py        # full report; exit code 0 == all green
python3 -m pytest band_lab/phase1 -v     # 48 tests, ~7s
python3 -m pytest band_lab/phase1 -m "not slow"   # skip the real-data parity tests
```

`parity.py` returns non-zero if the daily P&L series diverges from the
research engine, if any `band_lab/out/v14_*.csv` stops rebuilding
identically, or if the monitoring baselines published in
`IMPLEMENTATION_SPEC.md` §8 drift out of step with the engine — so it can be
used directly as a regression gate.

## The two engine profiles

`spec_engine.EngineConfig` exposes every clause of §2 that a clean-room
implementer cannot resolve from §2's words as a named switch:

- **`RESEARCH_COMPAT`** — the reading the research engine implements. This is
  what parity is measured under, and it reproduces the daily series to 4e-16.
- **`SPEC_LITERAL`** — the specification as it now stands, after the Phase 1
  amendments.

They differ only where the spec is right and the research engine never
implemented the rule: half-days OFF (§2.2), the 15:55 flatten (§2.8), clock
bar addressing (§2.1) and the incomplete-session refusal (§4). Together
those are worth **+0.3 bp/ON-day on SOXL and +3.5 on SOXS** against the
validated series — the gap the live system starts with, and the number to
carry into the Phase 3 comparison.

The switches that were measured and *not* adopted stay runnable, so the cost
of each decision remains a number. See PHASE1_PARITY.md §3 and §5.

## Not covered here

§10 items 9–12 and 15–16 (flatten verification, crash/restart reconciliation,
API disconnect, watchdog, session replay, weekly report) exercise the live
IBKR engine. They are not simulable in a bar-replay harness and are
deliberately absent rather than stubbed. They belong to Phase 2.
