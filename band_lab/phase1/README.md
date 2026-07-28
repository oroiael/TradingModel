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
| `parity.py` | parity vs the research engine, `v14_*.csv` rebuild, ambiguity attribution, §8 baselines |
| `test_spec_engine.py` | 47 acceptance tests for §10 items 1–8, 13, 14 |
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
python3 band_lab/phase1/parity.py        # full report; exit code 0 == parity holds
python3 -m pytest band_lab/phase1 -v     # 47 tests, ~7s
python3 -m pytest band_lab/phase1 -m "not slow"   # skip the two real-data parity tests
```

`parity.py` returns non-zero if the daily P&L series diverges from the
research engine or if any `band_lab/out/v14_*.csv` stops rebuilding
identically, so it can be used directly as a regression gate.

## The two engine profiles

`spec_engine.EngineConfig` exposes every clause of §2 that a clean-room
implementer cannot resolve from §2's words as a named switch:

- **`RESEARCH_COMPAT`** — the reading the research engine implements. This is
  what parity is measured under, and it reproduces the daily series to 4e-16.
- **`SPEC_LITERAL`** — the reading closest to the words of §2. Worth
  +5.8 bp/ON-day on SOXL and +3.5 on SOXS, but it is *not* the system that
  was walk-forward validated.

The gap between the two, switch by switch, is the real output of Phase 1.
See PHASE1_PARITY.md §3.

## Not covered here

§10 items 9–12 and 15–16 (flatten verification, crash/restart reconciliation,
API disconnect, watchdog, session replay, weekly report) exercise the live
IBKR engine. They are not simulable in a bar-replay harness and are
deliberately absent rather than stubbed. They belong to Phase 2.
