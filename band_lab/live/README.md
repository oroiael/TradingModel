# band_lab/live — Phase 2 live engine

Phase 2 of `band_lab/IMPLEMENTATION_SPEC.md` §9: the always-on service that
trades the SOXL and SOXS sleeves on IBKR, against a paper account first.

**Status: Stages 1-4 complete and runnable; not yet connected to a broker.**
`run.py` drives a whole trading day end to end — pre-open, bar feed, orders,
flatten, reconcile — and is proven against a `FakeIB` double. **No code here
has ever talked to IBKR.** The next step is Stage 4's acceptance: one real
session with `--dry-run` (transmit off). See [DEPLOYMENT.md](DEPLOYMENT.md) §12.

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
| `tests/` | 137 tests: core arithmetic, state machine (§10.4–8, 14), equivalence, intrabar, fetcher | 1 ✅ |
| `broker.py` | ib_async adapter + `FakeIB` test double; live-data assertion, session hours, reconcile primitives | 2 ✅ |
| `store.py` | SQLite (WAL): bars, decisions, orders, fills, quotes, counters, daily | 2 ✅ |
| `orders.py` | OrderManager: deterministic refs, ratchet, OCA, partial fills, flatten, reconcile | 3 ✅ |
| `engine.py` | the §5 daily timetable (logic) | 4 ✅ |
| `run.py` | **the service entrypoint** — the timetable driven by a wall clock | 4 ✅ |
| `config.py` | deployment config; delegates strategy numbers to §12 and refuses changes | 4 ✅ |
| `features.py` | ATR5/thr80 bootstrap: CSV backbone + broker top-up, percentages only | 4 ✅ |
| `feed.py` | 5-minute bar feed (polled historical), holds back the forming bar | 4 ✅ |
| `report.py` | 16:10 reconcile, shadow parity, weekly §8 report | 6 |
| `risk.py`, `watchdog.py` | day-loss breaker, kill switch, independent flatten | 7 |

## Run

```bash
python3 band_lab/live/replay.py           # equivalence vs phase1 — exit 0 == green
python3 -m pytest band_lab/live -q        # 137 tests
python3 band_lab/live/run.py --dry-run     # Stage 4: a session with transmit OFF
python3 band_lab/live/replay.py --sizing        # S9
python3 band_lab/live/replay.py --fill-models   # S10

# the 1-minute study — both files are in git-lfs, no fetch needed
git lfs pull --include="SOXL_1min.csv,SOXS_1min.csv,SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
for S in SOXL SOXS; do
  python3 band_lab/live/intrabar.py --symbol $S --check --start 2022-01-01
  python3 band_lab/live/intrabar.py --symbol $S --start 2022-01-01
done
```

Needs the git-lfs 5-minute CSVs — see [DEPLOYMENT.md](DEPLOYMENT.md) §2.

## The one thing to read first

[PHASE2_PARITY.md](PHASE2_PARITY.md) §S10–S11. Roughly two-thirds of the
strategy's measured edge comes from re-entries priced inside the bar that
exited the previous position, at a price that traded before that exit (S10).
**Both sleeves' 1-minute data is now in**, and it narrows that exposure: the
edge survives, but at 54–64% of the 5-minute figure (S11).

| | 5-minute | 1-minute | retained |
|---|---:|---:|---:|
| SOXL | 66.8 bp/ON-day | **42.5** | 64% |
| SOXS | 63.0 bp/ON-day | **34.2** | 54% |
| pair (w=0.50) | 54.4 bp/day | **32.1** | 59% |

`IMPLEMENTATION_SPEC.md` §8's baselines remain an upper bound. Plan on
**~40 bp/ON-day for SOXL and ~30 for SOXS** until real fills say otherwise.

Two things to carry forward: **SOXS is the more fragile sleeve** — its
`no_better` floor is negative and its 2023 turns negative at 1-minute
resolution — and the **pair's diversification is the most robust finding**,
halving the worst day to −4.57%.
