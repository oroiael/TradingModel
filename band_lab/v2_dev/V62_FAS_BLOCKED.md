# V62 — The four tests cannot be run on FAS. What is missing, and what is ready.

The request was to apply V53/V54 (short vol), V55/V56 (credit spreads),
V57/V58 (long vol and the fill ladder) and V60/V61 (PMCC) to FAS.

**All four are option tests. There are no FAS option chains, so none of them can
run.** This records the blocker precisely and removes every other obstacle.

## What exists for FAS, and what does not

| | status |
|---|---|
| `FAS_5min_6Years.csv` — price bars | **present** after `git lfs pull`: 117,036 bars, 2020-07-23 → 2026-07-22, 1,506 sessions |
| `FAS_Options_YYYY.csv` — option chains | **absent.** No FAS option data exists anywhere in the repo |
| `fas_lab/` — prior FAS work | present, and it is an *equity* band strategy, not options |

Only SOXL has option chains here. They were built by
`soxl_options_greeks_YYYY.py`, which calls ThetaData's
`option_history_greeks_eod` through a **local Java Theta Terminal on port
25503**. In this container `thetadata` is not installed and 25503 refuses the
connection, so the chains cannot be built here — they have to be fetched on the
machine where the Terminal runs.

Worth knowing: most CSVs in this repo are unfetched git-lfs pointers of about
130 bytes. `FAS_5min_6Years.csv` was one until `git lfs pull` was run against
it. That is why a file can appear to exist and hold nothing.

## What is now ready, so the four tests run the moment the data lands

**1. All four backtests take `--symbol`.** `load_chain()` and the renamed
`underlying_daily()` discover `{SYMBOL}_Options_*.csv` by glob rather than a
hardcoded SOXL list, and find the price file whether it is `_1min.csv` or
`_5min_*.csv` — bar size does not matter, the daily close is the last bar of the
session either way.

    python3 band_lab/v2_dev/short_vol_backtest.py     --symbol FAS
    python3 band_lab/v2_dev/credit_spread_backtest.py --symbol FAS
    python3 band_lab/v2_dev/option_fill_ladder.py     --symbol FAS
    python3 band_lab/v2_dev/pmcc_backtest.py          --symbol FAS

Asking for FAS today fails immediately and says why, rather than part-way
through with something confusing:

    FileNotFoundError: no option chain files for FAS: expected
    /home/user/TradingModel/FAS_Options_YYYY.csv. Only SOXL has them in this
    repo. Build them with `python3 fetch_option_chains.py --symbol FAS` on a
    machine running the Theta Terminal, then re-run.

**Regression: SOXL is byte-identical after the refactor.** `git diff --quiet`
is clean on the V54 and V56 grid and ledger CSVs, so nothing in the published
sequence moved.

Outputs for a non-SOXL symbol are filename-tagged, so a FAS run cannot overwrite
a SOXL baseline.

**2. `fetch_option_chains.py`** generalises the eight per-year SOXL scripts to
any symbol and year, and adds the thing they lack: it re-reads each file it
writes and checks it can actually drive a backtest — the nine columns
`load_chain()` needs, trade dates that parse into the year requested, a
plausible share of two-sided quotes, and a call/put-shaped `right`. A bad fetch
is caught at fetch time rather than three hours into a grid. V52 is the record
of how long a misread column can survive here.

    export THETA_EMAIL=... THETA_PASSWORD=...
    python3 fetch_option_chains.py --symbol FAS --years 2022 2023 2024 2025 2026
    python3 fetch_option_chains.py --symbol FAS --years 2022 2023 --check

## Credentials in the repository

The eight `soxl_options_greeks_*.py` scripts and two others — ten files — carry
an email address and password **in plaintext in committed source**. The new
fetch script reads `THETA_EMAIL` / `THETA_PASSWORD` from the environment and
stores nothing. The committed password should be rotated regardless, since it is
in the git history and rotating is the only thing that actually retires it.

## What to expect if the chains arrive

FAS is a 3× financials ETF against SOXL's 3× semiconductors. Two things about
the sample differ in ways that matter, and both should be settled before reading
any result rather than after:

- **FAS options are thinner than SOXL's.** `fas_lab` already charges FAS 3 bp
  against SOXL's 2 bp on the equity side for exactly this reason. Every one of
  the four tests is spread-dominated — V58 established the fill convention is
  worth 4.6 points of joint P&L on SOXL — so a wider FAS quote moves all four
  verdicts in the same direction, and the V58 ladder should be run **first** on
  FAS rather than last.
- **The price history starts 2020-07-23**, not 2022-01. If ThetaData serves FAS
  chains back that far the sample gains the 2020–21 period; if it does not, the
  window is whatever the chains cover, and that should be reported rather than
  assumed to match SOXL's.

No prediction is recorded here about the results, because V60's prediction was
wrong on the gate it named and there is no evidence about FAS options to reason
from.
