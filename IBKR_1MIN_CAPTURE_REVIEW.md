# 1-minute IBKR capture for TQQQ, FAS, SPXL, MUU, BULZ, TMF

**Question asked:** does this repository already contain working, accepted code to
pull 1-minute bars for those six symbols from IBKR?

**Answer:** yes for the mechanism, no for the symbol set. Two merged, tested
fetchers exist and both walk IBKR history correctly. Neither could fetch **TQQQ**
or **MUU** as written, because both pinned the primary listing exchange to `ARCA`
and those two are NASDAQ-listed. That is fixed here, along with a timestamp
defect in the path this repo now defaults to. Nothing about the fetch loop itself
needed rewriting.

---

## What already exists

| path | what it does | status |
|---|---|---|
| `fas_1min_fetch.py` | 1-min RTH bars → `<SYM>_1min.csv`; IBKR default, ThetaData alternate; resumable; `--normalize-splits` | **merged to main**, 33/33 offline self-tests pass |
| `fas_1min_verify.py` | six-check validator, incl. 1-min→5-min cross-check against `<SYM>_5min_6Years.csv` | merged to main; self-validated on the known-good SOXL pair |
| `fas_1min_selftest.py` | offline tests for the parts that decide what lands on disk | merged to main |
| `band_lab/live/fetch_1min.py` | the same backward walk, built for the S10 fill-resolution study | merged to main, 11/11 pytest pass |
| `band_lab/live/broker.py:_dated_bars` | `reqHistoricalData` inside the live engine | **the only IBKR bar code here that has demonstrably run against a real account** |
| `ibkr_intraday_fetcher.py` / `_2.py` | the raw-`ibapi` 5-minute fetchers that produced `*_5min_6Years.csv` | works, but hard-codes `SYMBOL` at module scope; superseded for 1-minute work |
| `TQQQ_ibkr_historical_3yr.py`, `soxl_ibkr_historical*.py` | daily EOD pulls | unrelated to 1-minute |

`FAS_1MIN_CAPTURE.md` is the provenance record for the first three and is still
accurate; read it before trusting any basis decision.

### The two 1-minute fetchers, side by side

They are the same algorithm — qualify the contract, request `1 min` / `TRADES` /
`useRTH=1` backwards from a cursor, merge-dedupe-sort onto disk, stop after five
consecutive empty responses — with different strengths:

| | `fas_1min_fetch.py` | `band_lab/live/fetch_1min.py` |
|---|---|---|
| exchange/primary configurable | **now yes** (was ARCA-only) | yes (`--exchange`, `--primary`) |
| bar timestamp conversion | **now** the four documented `parseIBDatetime` shapes | naive / aware / string forms |
| atomic write | yes (`.tmp` + `os.replace`) | no (direct `to_csv`) |
| split re-anchoring | yes (`--normalize-splits`) | no — split applied at read time by `intrabar.py` |
| second source | ThetaData | none |
| validator | `fas_1min_verify.py` | `intrabar.py --check` |

`fas_1min_fetch.py` is the one to use for this job: it produces the repository's
1-minute CSV convention, it re-anchors the split basis deliberately rather than
inheriting whatever the chunking produced, and it has a validator that
cross-checks against an independently sourced file.

---

## Per-symbol readiness

Contract identity resolved from IBKR's own contract search on 2026-09-07:

| symbol | what it is | primary exchange | conId | already in repo | 5-min cross-check |
|---|---|---|---|---|---|
| **TQQQ** | ProShares UltraPro QQQ (3×) | **NASDAQ** | 72539702 | daily EOD + option chains only | ✗ none |
| **FAS** | Direxion Financial Bull 3× | ARCA | 97276826 | `FAS_5min_6Years.csv` | ✓ |
| **SPXL** | Direxion S&P 500 Bull 3× | ARCA | 55679428 | `SPXL_5min_6Years.csv` | ✓ |
| **MUU** | Direxion Daily MU Bull **2×** | **NASDAQ** | 734424283 | nothing | ✗ none |
| **BULZ** | MicroSectors FANG & Innovation 3× | ARCA | 593821806 | nothing | ✗ none |
| **TMF** | Direxion 20+ Year Treasury Bull 3× | ARCA | 665380902 | nothing | ✗ none |

Four things in that table change what you should expect:

**MUU has no six-year history to fetch.** Its monthly bars begin **2024-10-10**,
so roughly two years exist at any resolution. A `--start 2019-12-31` run will
walk back, hit five empty responses, and stop — correctly, but the verifier will
then warn that the span is short of six years. That is the instrument, not the
capture. MUU is also the odd one out on substance: a 2× single-stock ETF, not a
3× index fund, so it does not belong in a cross-sectional comparison with the
other five without saying so.

**TQQQ, MUU, BULZ and TMF have no 5-minute companion file.** Step 5
of `fas_1min_verify.py` — aggregating the new 1-minute file to 5 minutes and
comparing it bar-for-bar against an independently sourced capture — is the check
that actually establishes a file is sound. For four of the six symbols it will
warn and skip. Their captures rest on internal consistency alone, which is
weaker; treat FAS and SPXL as the calibration pair and the other four as
unverified against a second source.

BULZ is also the only one of the six IBKR lists with no options section at all,
consistent with the MicroSectors line being exchange-traded notes rather than
funds. That changes what you can hedge with, not what the capture does.

**Four of the six split inside the capture window.** From IBKR's corporate-action
history, read on 2026-09-07 — this is what `--normalize-splits` and step 4 of the
verifier should find, so a run that reports something else is wrong about
something:

| symbol | splits, 2021-09-07 → 2026-09-05 |
|---|---|
| TQQQ | **2022-01-13** 2-for-1, **2025-11-20** 2-for-1 |
| FAS | none |
| SPXL | none |
| MUU | **2026-07-15** 20-for-1 |
| BULZ | **2022-10-31** 1-for-10 reverse, **2026-02-24** 10-for-1 |
| TMF | **2023-12-04** 1-for-10 reverse |

Every one of those factors (2, 10, 20 and their reciprocals) is already in
`SPLIT_FACTORS`, and the normalizer compounds correctly across two splits: bars
before the earlier cut are multiplied by both factors. What it cannot see is
**2019-12-31 → 2021-09-06** — five years is the longest window IBKR's contract
history exposes — so `FAS_1MIN_CAPTURE.md`'s open question about a FAS action
during the COVID crash stays open, and the same gap applies to the other five.
Record whatever step 4 names in `SPLIT_ADJUSTMENTS` in
`band_lab/live/replay.py`, which currently holds only SOXL.

All six also pay quarterly distributions, some large: FAS paid $12.09 on
2025-12-10 against a ~$165 price. The split detector fires on overnight ratios
outside [0.60, 1.70], so an ordinary distribution will not trip it — but a
distribution large enough would be, and would be snapped to a "split" that
never happened.
Check any factor the normalizer prints against the table above before accepting
the file.

---

## What was changed, and why

### 1. The primary exchange was hard-coded to ARCA

`fas_1min_fetch.py` qualified every symbol as
`Stock(symbol, "SMART", "USD", primaryExchange="ARCA")` with no override. Two of
the six requested symbols are NASDAQ-listed, and `UVXY` — which already has a
1-minute file in this repository — is BATS-listed.

This is not cosmetic. IBKR's own documentation, in
`TWS API/TWS Documentation - Copy Paste from Online.pdf` under *Unavailable
Historical Data*, says:

> Historical data for securities which move to a new exchange will often not be
> available prior to the time of the move. For example, SOXX stock moved to
> NASDAQ exchange on 15 Oct 2010, so no SOXX data before 15 Oct 2010 can be
> retrieved despite SOXX was listed in 2001. **This limitation also applied to
> contract which specifies `SMART` as the exchange.**

The listing venue is part of the request, not decoration. There is now a
`PRIMARY_EXCHANGE` table carrying the six symbols plus the ones this repo already
uses, a `--primary` / `--exchange` override, and a retry that lets IBKR resolve
the venue and prints what it chose if the table is wrong — so a bad entry costs
one line of output instead of an operator round trip.

### 2. The IBKR path read bar timestamps in a way that could silently shift them four hours

The old line was:

```python
"ts": pd.to_datetime(str(b.date).replace(" America/New_York", "").strip())
```

That is correct only when `ib_async` hands back a naive datetime. This repo
already documents, in `band_lab/live/broker.py:bar_time_et` and from that
package's source, that `parseIBDatetime` returns **any of four things** depending
on the TWS version and its configured timezone: a zone-aware datetime with an
IANA zone, a zone-aware **UTC** datetime decoded from an epoch, a naive datetime,
or a bare `date`.

Given the UTC form, the old expression would have written `13:30:00` under an
` America/New_York` suffix — a four-hour error stamped with the wrong zone — and
a run whose chunks mixed aware and naive datetimes would have put an
object-dtype column into `to_rows`, where `.dt.strftime` raises mid-capture.
`fas_1min_verify.py` step 2 would have caught the first case after the fact by
seeing sessions that start at 13:30 rather than 09:30; it is better not to spend
five hours per symbol finding out.

`bar_timestamp()` now handles all four shapes and is covered by eight new
self-tests, including the UTC case specifically.

### 3. The module docstring argued for a source the script no longer uses

It still claimed the 1-minute files "did not come from the IBKR path in this
repo" and that the script "therefore defaults to that same proven local-REST
pattern" — both retracted by `FAS_1MIN_CAPTURE.md` and contradicted by the code,
which has defaulted to `--source ibkr` since commit `b3c7d66`. Rewritten to match.

**Not changed:** `band_lab/live/config.py` carries a single `primary: str = "ARCA"`
for every symbol in a sleeve, and `test_live_runner.py` already exercises
`symbols=("SOXL", "SOXS", "TQQQ")`. A live TQQQ sleeve would hit the same
mis-qualification. That is the live engine's business, not this capture's, so it
is flagged here rather than fixed.

---

## Running it

TWS or IB Gateway must be up with the API enabled; paper is port 7497.

```bash
python3 check_tws.py                       # connectivity smoke test

for s in TQQQ FAS SPXL MUU BULZ TMF; do
    python3 fas_1min_fetch.py --symbol $s --normalize-splits
    python3 fas_1min_verify.py --symbol $s
done
```

Each run is resumable — Ctrl-C and rerun; the file on disk is always sorted and
de-duplicated. Note that both fetchers only walk **backwards** from the earliest
row they already have, so a rerun extends history but does **not** top up recent
sessions. Re-fetching the tail means starting a fresh file or passing `--out`.

### If it will not start

The first real run failed like this, and the traceback names the wrong problem:

```
(env) PS C:\Users\churc\documents\TradingModel> python3 fas_1min_fetch.py
ModuleNotFoundError: No module named 'ib_async'
```

That reads as "install ib_async", which is usually already done. The actual
fault is which interpreter ran: **`pip` resolves to the active venv while
`python3` on Windows resolves to the Microsoft Store shim or a system Python**,
so `pip install ib_async` answers "already satisfied" and the import still
fails. `RUNBOOK_WINDOWS.md` covers it in one line — *Python is invoked as
`python` (not `python3`)* — and `band_lab/v2_dev/option_spread_probe.py` has
carried a comment recording that this already cost someone their time once.

**Where the environment actually is**, from the evidence in that session:

| | |
|---|---|
| virtualenv | `C:\Users\churc\documents\TradingModel\env` — `pip` reports `ib_async 2.1.0` in `.\env\Lib\site-packages` |
| its interpreter | `.\env\Scripts\python.exe` |
| what `python3` runs | `C:\Users\churc\AppData\Local\Python\pythoncore-3.14-64\python.exe` — Python 3.14, **outside the venv** |

A Windows venv puts `python.exe` and `pythonw.exe` in `Scripts\`; activation
prepends that folder to `PATH`, which is why `python` and `pip` reach the venv.
There is no `python3.exe` there, so `python3` falls through `PATH` to the 3.14
install, which has pandas but not `ib_async`. That is the whole bug.

Three things now follow from that:

- **Use `python`, not `python3`, on Windows.** `python fas_1min_fetch.py`. To
  name the interpreter outright, PowerShell needs the leading `.\` and a call
  operator — `& ".\env\Scripts\python.exe" fas_1min_fetch.py`. Written as
  `.env\Scripts\python.exe`, PowerShell reads `.env` as a *module* and answers
  "The module '.env' could not be loaded", which is a third, imaginary problem.
- **Or give `python3` a home in the venv**, since the muscle memory is not going
  away: `Copy-Item .\env\Scripts\python.exe .\env\Scripts\python3.exe`, then
  confirm with `python3 fas_1min_fetch.py --check-env` — it should report the
  venv as `sys.prefix`.
- **Ask the tooling where it is.** `python fas_1min_fetch.py --check-env` prints
  the running interpreter, the active virtualenv and its real interpreter path,
  whether `python3.exe` exists in it at all, which of pandas / numpy / ib_async /
  requests that Python can actually see, and a verdict. It exits 0 when the fetch
  would run and 1 when it would not, so it works as a gate before a six-symbol
  loop. `band_lab/live/fetch_1min.py --check-env` does the same.

Every IBKR entry point also fails this way now rather than with a traceback, and
the check happens **before** the run announces itself — the old code printed
`FAS: 1-minute RTH bars 2019-12-31 -> 2026-09-08` and only then discovered it
could not import a client. It exits non-zero, so a `for` loop over six symbols
stops rather than repeating the same failure six times.

```
ib_async is not importable from THIS interpreter (the IBKR client the current scripts use).

  script      : fas_1min_fetch.py
  interpreter : C:\Program Files\WindowsApps\...\python3.exe
  sys.prefix  : C:\Program Files\WindowsApps\...
  VIRTUAL_ENV : C:\Users\churc\documents\TradingModel\env

  -> A virtualenv is active but this is NOT its interpreter, so you
     are running the wrong Python. ...
```

**One more source of confusion, worth knowing about.** `RUNBOOK_WINDOWS.md`
documents the venv as `.venv-live` under `C:\TradingModel`; this machine uses
`env` under `C:\Users\churc\documents\TradingModel`. Both work — nothing in
the code cares what the venv is called, and `--check-env` reads `VIRTUAL_ENV`
rather than assuming a name — but the runbook's literal
`.\.venv-live\Scripts\Activate.ps1` will not activate anything here. `env/` is
gitignored, so it is invisible from the repository side.

The guard is wired into `fas_1min_fetch.py`, `band_lab/live/fetch_1min.py`,
`band_lab/live/broker.py`, `check_tws.py`, `test_connection.py`,
`get_option_chain.py`, `stream_market_data.py`, and the five older `ibapi`
fetchers, which fail identically with `No module named 'ibapi'`.

### How long this takes

Pacing, verified from the documentation PDF (*Pacing Violations for Small Bars*):

> * Making identical historical data requests within 15 seconds.
> * Making six or more historical data requests for the same Contract, Exchange
>   and Tick Type within two seconds.
> * Making more than 60 requests within any ten minute period.

The default 11-second gap gives 54.5 requests per ten minutes, inside the limit.
At one session per request that is ~1,650 requests and **~5 hours per symbol**,
so ~30 hours for all six. IBKR's own client documents `durationStr` as valid
"up to one week" (`TWS API/source/pythonclient/ibapi/client.py`), and
`band_lab/live/fetch_1min.py` has always suggested `1 W`; at that size the set
drops to roughly six hours. It is untested against a live TWS here — run one
symbol with `--duration "1 W"`, verify it, then commit to the rest.

### Two things that will bite before the data does

**Volume can come back in lots rather than shares.** From the same PDF, under
*Historical Volume Scaling*: Global Configuration → API → Settings → "Send market
data in lots for US Stocks for dual-mode API clients". Checked returns round
lots, unchecked returns shares. The existing CSVs are in shares; if that setting
is on, every volume in the new files is 100× small and step 5 of the verifier
will report a volume ratio near 0.01 for FAS and SPXL. Check it before the run,
not after.

**Historical data is filtered.** IBKR filters trades that occur away from the
NBBO (combo legs, block trades, derivative trades), so historical volume is
systematically lower than the real-time tape. That is expected and is why the
verifier compares *returns*, which are basis- and filter-independent, rather than
price levels.

---

## What could not be tested here

- **No TWS, and `ib_async` is not installed in this container.** The connection,
  qualification and request loop are unexercised. Everything asserted above about
  `parseIBDatetime`'s return shapes comes from this repository's own reading of
  that package's source in `broker.py`, not from a live call — the distinction
  the `ibkr-semantics` skill exists to enforce.
- **The verifier could not be run end-to-end.** Every `*.csv` here is a Git LFS
  pointer and `git lfs` is not installed in this container. `fas_1min_verify.py`
  detects that and says so rather than parsing a pointer file.
- **39 of 491 tests in `band_lab/live/tests` fail in this container**, for the
  same reason — they read data files that are pointers, so the frames have no
  `Date` column. Identical failures on a clean checkout without these changes.
  The suites that do not need data files pass: `test_live_fetch.py` 11/11,
  `fas_1min_selftest.py` 33/33.
- **The maximum `durationStr` for a 1-minute bar size is not verifiable from
  here.** The duration and bar-size tables are the one part of IBKR's historical
  data documentation the committed PDF does not carry, and their online docs are
  egress-blocked.

## Worth doing next, not done here

- `reqHeadTimeStamp` returns the earliest available data point for a contract and
  `whatToShow` (documentation PDF, *Finding the Earliest Available Data Point*).
  Both fetchers instead discover the end of history by requesting until five
  responses come back empty. For MUU that is ~55 seconds of wasted requests; for
  a symbol whose depth you do not know, it is the difference between planning a
  run and finding out afterwards.
- Neither fetcher can extend a file *forward*. Adding a `--forward` mode would
  make these six files maintainable rather than one-shot.
