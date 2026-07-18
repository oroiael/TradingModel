#!/usr/bin/env python3
"""
Loader for the raw ThetaData option exports.

Merges SOXL_Options_2024.csv, SOXL_Options_2025.csv and SOXL_Options_2026.csv
into one normalized frame covering 2024-01-02 -> 2026-07-02:

    * dates parsed per file (the 2025 export uses M/D/YY, the 2024/2026
      exports use ISO YYYY-MM-DD)
    * `dte` derived as (expiration - trade_date) in calendar days
    * exact duplicate contracts across files dropped (keep first)
    * output columns: expiration, strike, right, bid, ask, implied_vol,
      trade_date, dte, underlying_price  (trade_date/expiration as
      datetime.date)

Nothing is repaired or imputed: zero bids, zero IVs and quote-only rows are
passed through untouched for the consumer to handle explicitly.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_FILES = ("SOXL_Options_2024.csv", "SOXL_Options_2025.csv",
             "SOXL_Options_2026.csv")
USECOLS = ["expiration", "strike", "right", "bid", "ask", "implied_vol",
           "trade_date", "underlying_price"]


def load_raw_options(root=ROOT, verbose=False):
    frames = []
    for name in RAW_FILES:
        p = Path(root) / name
        if not p.exists() or p.stat().st_size < 1000:
            raise FileNotFoundError(
                f"{name} missing or still a Git LFS pointer -- run "
                "'git lfs pull'")
        df = pd.read_csv(p, low_memory=False, usecols=USECOLS)
        for c in ("trade_date", "expiration"):
            fmt = "%m/%d/%y" if "/" in str(df[c].iloc[0]) else "%Y-%m-%d"
            df[c] = pd.to_datetime(df[c], format=fmt)
        if verbose:
            print(f"  {name}: {len(df):,} rows, "
                  f"{df['trade_date'].min().date()} -> "
                  f"{df['trade_date'].max().date()}")
        frames.append(df)
    f = pd.concat(frames, ignore_index=True)
    before = len(f)
    f = f.drop_duplicates(["trade_date", "expiration", "strike", "right"],
                          keep="first")
    if verbose and len(f) != before:
        print(f"  dropped {before - len(f):,} duplicate contract rows")
    f["dte"] = (f["expiration"] - f["trade_date"]).dt.days
    f["trade_date"] = f["trade_date"].dt.date
    f["expiration"] = f["expiration"].dt.date
    return f.sort_values(["trade_date", "expiration", "strike"],
                         ignore_index=True)


if __name__ == "__main__":
    f = load_raw_options(verbose=True)
    print(f"merged: {len(f):,} rows, {f['trade_date'].nunique()} trade "
          f"dates, {min(f['trade_date'])} -> {max(f['trade_date'])}, "
          f"DTE {f['dte'].min()}-{f['dte'].max()}")
