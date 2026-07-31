# band_lab/live — Phase 2 live engine

Phase 2 of `band_lab/IMPLEMENTATION_SPEC.md` §9: the always-on service that
trades the SOXL and SOXS sleeves on IBKR, against a paper account first.

**Status: Stage 1 complete.** The strategy core and sleeve state machine are
built and proven equivalent to the Phase 1 backtest engine. Nothing here has
connected to IBKR yet.

| document | what it is |
|---|---|
| [PHASE2_PLAN.md](PHASE2_PLAN.md) | the build plan, configuration decisions, and resolved spec gaps |
| [PHASE2_PARITY.md](PHASE2_PARITY.md) | Stage 1's result, plus the S9 and **S10** findings |
| [DEPLOYMENT.md](DEPLOYMENT.md) | macOS setup, TWS configuration, ntfy, runbook |

## Layout

| file | role | stage |
|---|---|---|
| `strategy_core.py` | pure strategy: §2.1–§2.4 arithmetic, gate, filter, levels, sizing | 1 ✅ |
| `sleeve.py` | per-sleeve state machine (§2.5–§2.8); emits `Intent`s, performs no I/O | 1 ✅ |
| `replay.py` | offline driver + equivalence report + the S9/S10 diagnostics | 1 ✅ |
| `intrabar.py` | 5-minute decisions, 1-minute fills — the S10 resolution study | 1 ✅ |
| `fetch_1min.py` | IBKR 1-minute bar fetcher (resumable, paced) | 1 ✅ |
| `tests/` | 78 tests: core arithmetic, state machine (§10.4–8, 14), equivalence, intrabar, fetcher | 1 ✅ |
| `broker.py`, `store.py` | ib_async adapter, bar feed, SQLite | 2 |
| `orders.py` | OrderManager: ratchet, OCA, flatten, reconciliation | 3 |
| `engine.py` | the §5 daily timetable | 4 |
| `report.py` | 16:10 reconcile, shadow parity, weekly §8 report | 6 |
| `risk.py`, `watchdog.py` | day-loss breaker, kill switch, independent flatten | 7 |

## Run

```bash
python3 band_lab/live/replay.py           # equivalence vs phase1 — exit 0 == green
python3 -m pytest band_lab/live -q        # 78 tests
python3 band_lab/live/replay.py --sizing        # S9
python3 band_lab/live/replay.py --fill-models   # S10

# the 1-minute study — SOXL data is in git-lfs, SOXS is not yet fetched
python3 band_lab/live/intrabar.py --symbol SOXL --check --start 2022-01-01
python3 band_lab/live/intrabar.py --symbol SOXL --start 2022-01-01
```

Needs the git-lfs 5-minute CSVs — see [DEPLOYMENT.md](DEPLOYMENT.md) §2.

## The one thing to read first

[PHASE2_PARITY.md](PHASE2_PARITY.md) §S10–S11. Roughly two-thirds of the
strategy's measured edge comes from re-entries priced inside the bar that
exited the previous position, at a price that traded before that exit (S10).
The SOXL 1-minute data is now in and narrows that exposure: the edge
survives, but at **~64% of the 5-minute figure — 42.5 vs 66.8 bp/ON-day**,
consistently across every year (S11). `IMPLEMENTATION_SPEC.md` §8's baselines
remain an upper bound; **~40 bp/ON-day is the working planning figure** for
SOXL until real fills say otherwise.

SOXS is still outstanding, and its 1-minute file has an adjustment trap worth
reading before the fetch, not after — PHASE2_PARITY.md, "SOXS: the adjustment
trap".
