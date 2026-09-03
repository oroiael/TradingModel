#!/usr/bin/env python3
"""
Build {SYMBOL}_Options_{YEAR}.csv files for any underlying, from ThetaData.

This is the generalised form of soxl_options_greeks_2022.py and its siblings,
which each hardcode one symbol and one year. It exists because every option
backtest in band_lab/v2_dev needs these files and only SOXL has them.

RUN IT WHERE THE THETA TERMINAL IS. The `thetadata` client talks to a local
Java Terminal on port 25503, so this must run on the machine where that
Terminal is logged in -- not in a container.

    export THETA_EMAIL=you@example.com
    export THETA_PASSWORD=...                  # or put them in .env
    python3 fetch_option_chains.py --symbol FAS --years 2022 2023 2024 2025 2026
    python3 fetch_option_chains.py --symbol FAS --years 2024 --check

CREDENTIALS COME FROM THE ENVIRONMENT. The existing per-year scripts have the
email and password written into the source and committed to this repository.
Those should be rotated. Nothing here reads them.

WHAT IT VERIFIES. A silently wrong chain file is expensive -- it is three hours
into a backtest before anything looks odd, and V52 is the record of how long a
misread column can survive. So every file written is re-read and checked for
the nine columns band_lab/v2_dev/short_vol_backtest.py:load_chain() requires,
for dates that parse into the year requested, and for a plausible share of
two-sided quotes. A file that fails is reported, not silently kept.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date

import pandas as pd

# the columns load_chain() reads; a file without them cannot be backtested
REQUIRED = ["expiration", "strike", "right", "bid", "ask", "delta",
            "implied_vol", "underlying_price", "trade_date"]


def connect():
    try:
        from thetadata import ThetaClient
    except ImportError:
        sys.exit("thetadata is not installed in THIS interpreter.\n"
                 "  python -m pip install thetadata\n"
                 "and run with the same `python` -- a venv `pip` with a system\n"
                 "`python3` is the usual way this fails.")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    email = os.environ.get("THETA_EMAIL")
    pw = os.environ.get("THETA_PASSWORD")
    if not email or not pw:
        sys.exit("set THETA_EMAIL and THETA_PASSWORD in the environment or a "
                 ".env file. They are deliberately not stored in this file.")
    return ThetaClient(email=email, password=pw, dataframe_type="pandas")


def fetch_year(client, symbol, year, pause):
    dates = client.stock_list_dates(request_type="quote", symbol=[symbol])
    dates["date"] = pd.to_datetime(dates["date"]).dt.date
    valid = dates[(dates.date >= date(year, 1, 1))
                  & (dates.date <= date(year, 12, 31))].date.tolist()
    if not valid:
        print(f"  {year}: no trading dates returned for {symbol} — is the "
              f"symbol right, and does the subscription cover this year?")
        return None

    parts, failed = [], []
    for i, d in enumerate(valid, 1):
        sys.stdout.write(f"\r  {year}: [{i}/{len(valid)}] {d}   ")
        sys.stdout.flush()
        try:
            df = client.option_history_greeks_eod(
                symbol=symbol, start_date=d, end_date=d, expiration="*")
        except Exception as e:                      # one bad day must not kill the year
            failed.append((d, str(e)[:80]))
            continue
        if df is not None and not df.empty:
            df["trade_date"] = d
            parts.append(df)
        time.sleep(pause)
    print()
    if failed:
        print(f"  {year}: {len(failed)} of {len(valid)} dates failed, "
              f"first: {failed[0][0]} {failed[0][1]}")
    return pd.concat(parts, ignore_index=True) if parts else None


def verify(path, symbol, year):
    """Re-read what was written and check it can actually drive a backtest."""
    try:
        d = pd.read_csv(path, low_memory=False)
    except Exception as e:
        return [f"unreadable: {e}"]
    bad = []
    missing = [c for c in REQUIRED if c not in d.columns]
    if missing:
        bad.append(f"missing columns {missing}")
    if not missing:
        try:
            td = pd.to_datetime(d.trade_date.astype(str), format="mixed")
            off = (td.dt.year != year).mean()
            if off > 0.01:
                bad.append(f"{off:.1%} of trade_dates are not in {year}")
        except Exception as e:
            bad.append(f"trade_date will not parse: {e}")
        two_sided = ((d.bid > 0) & (d.ask > d.bid)).mean()
        if two_sided < 0.20:
            bad.append(f"only {two_sided:.1%} of rows are two-sided quotes")
        if d.get("right") is not None and d.right.astype(str).str[0].str.upper() \
                .isin(["C", "P"]).mean() < 0.99:
            bad.append("`right` is not call/put shaped")
    return bad


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", required=True, help="e.g. FAS, TQQQ, SPXL")
    p.add_argument("--years", nargs="+", type=int, required=True)
    p.add_argument("--outdir", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--force", action="store_true", help="refetch a year already on disk")
    p.add_argument("--pause", type=float, default=0.02, help="seconds between days")
    p.add_argument("--check", action="store_true",
                   help="verify files already on disk and exit, no fetching")
    a = p.parse_args()

    if a.check:
        for y in a.years:
            f = os.path.join(a.outdir, f"{a.symbol}_Options_{y}.csv")
            if not os.path.exists(f):
                print(f"  {y}: absent"); continue
            bad = verify(f, a.symbol, y)
            print(f"  {y}: {'OK' if not bad else 'PROBLEMS — ' + '; '.join(bad)}")
        return

    client = connect()
    print(f"connected. fetching {a.symbol} for {a.years}\n")
    for y in a.years:
        f = os.path.join(a.outdir, f"{a.symbol}_Options_{y}.csv")
        if os.path.exists(f) and not a.force:
            print(f"  {y}: already on disk, skipping (--force to refetch)")
            continue
        df = fetch_year(client, a.symbol, y, a.pause)
        if df is None:
            print(f"  {y}: nothing fetched")
            continue
        df.to_csv(f, index=False)
        bad = verify(f, a.symbol, y)
        print(f"  {y}: wrote {len(df):,} rows -> {f}"
              f"   {'OK' if not bad else 'PROBLEMS — ' + '; '.join(bad)}")

    print(f"\nthen, in the repo:\n"
          f"  python3 band_lab/v2_dev/short_vol_backtest.py    --symbol {a.symbol}\n"
          f"  python3 band_lab/v2_dev/credit_spread_backtest.py --symbol {a.symbol}\n"
          f"  python3 band_lab/v2_dev/option_fill_ladder.py     --symbol {a.symbol}\n"
          f"  python3 band_lab/v2_dev/pmcc_backtest.py          --symbol {a.symbol}\n")


if __name__ == "__main__":
    main()
