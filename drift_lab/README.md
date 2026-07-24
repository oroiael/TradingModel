# drift_lab — option-vs-underlying "drift" (stale-mark / lead-lag) study

Measures, model-free, every instance where SOXL's 5-min move outpaces its option
**trade prints**, 2022–2026 (246 expirations, 3.3 M episodes).

| file | what |
|---|---|
| `FINDINGS_drift.md` | **the analysis** — method, results, limits, data requests |
| `DATA_NOTES.md` | data provenance, quality, field semantics (the gaps, stated) |
| `drift_engine.py` | loader + stale-mark drift-run detector (the definitions) |
| `run_full.py` | run all expirations → `out/` |
| `report.py` | the answer tables (how often / how long / how big + lead-lag) |
| `make_heatmaps.py` | `out/drift_heatmaps.png` |
| `verify_data.py` | reproduces every claim in `DATA_NOTES.md` |
| `out/ANSWER_*.csv`, `out/*.csv` | the tables (plain text) |
| `out/*.parquet` | full episode + lead-lag data (regenerable; git-ignored) |

Headline: the "drift" is real but is overwhelmingly **stale trade prints
(illiquidity), governed by DTE × moneyness and stable across regimes** — not the
option market failing to reprice. Genuine under-reaction is ~5–7% of a move and
clears within one 5-min bar. Proving any *tradable* lag needs **bid/ask quote data**,
which this dataset lacks. See `FINDINGS_drift.md` §6.

```bash
git lfs pull --include="SOXL_5min_6Years.csv,raw_data/SOXL_intraday_5m_exp_*.csv"
python3 drift_lab/verify_data.py && python3 drift_lab/run_full.py && \
python3 drift_lab/report.py && python3 drift_lab/make_heatmaps.py
```
