#!/usr/bin/env python3
"""
data_loader.py  --  canonical data ingestion for the SOXL call-credit-spread lab.

Two datasets are loaded, nothing is imputed or invented:

1.  Daily EOD option chains  SOXL_Options_<YEAR>.csv  (2022..2026)
    One snapshot per (trade_date, expiration, strike, right).  Real bid/ask,
    implied_vol, first-order greeks, and the underlying_price stamped on the
    same snapshot.  Date columns come in two formats across the yearly files
    (ISO YYYY-MM-DD for 2022/2023/2024/2026, M/D/YY for 2025); each file's
    format is detected from its own first row, never hard-coded globally.

2.  5-minute intraday underlying  SOXL_5min_3Years.csv
    Date,Open,High,Low,Close,Volume with a "YYYYMMDD HH:MM:SS America/New_York"
    timestamp.  Used for intraday path / settlement checks ONLY -- there are no
    intraday OPTION quotes anywhere in the data, so option legs can only ever be
    priced at the daily EOD snapshot.

Project data conventions (from the repo strategy specs) implemented here:
  * whole-number strike enforcement is provided as an OPTIONAL filter
    (`whole_strikes_only`) -- the raw loader keeps everything so the profiler can
    measure how many decimal strikes exist before anything is dropped.
  * the 20% spread execution rule and nearest-neighbour strike search live in the
    backtester, not here -- this module only delivers clean, typed, de-duplicated
    quotes.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OPTION_FILES = {
    2022: "SOXL_Options_2022.csv",
    2023: "SOXL_Options_2023.csv",
    2024: "SOXL_Options_2024.csv",
    2025: "SOXL_Options_2025.csv",
    2026: "SOXL_Options_2026.csv",
}
FIVE_MIN_FILE = "SOXL_5min_3Years.csv"

# Only the columns the lab actually consumes are read -- keeps ~1.5M-row load light.
OPT_USECOLS = [
    "expiration", "strike", "right", "bid", "ask", "close",
    "implied_vol", "delta", "trade_date", "underlying_price", "volume",
]


def _parse_date_col(series: pd.Series) -> pd.Series:
    """Detect M/D/YY vs ISO from the first value; parse the whole column that way."""
    fmt = "%m/%d/%y" if "/" in str(series.iloc[0]) else "%Y-%m-%d"
    return pd.to_datetime(series, format=fmt)


def load_options(root=ROOT, years=range(2022, 2027), whole_strikes_only=False,
                 verbose=False) -> pd.DataFrame:
    """Load & merge the yearly option chains into one normalized frame.

    Returns columns: trade_date, expiration (datetime.date), dte (int calendar
    days), strike, right ('CALL'/'PUT'), bid, ask, close, implied_vol, delta,
    underlying_price, volume.  Exact duplicate contracts across files are
    dropped (keep first).  No prices are repaired.
    """
    frames = []
    for y in years:
        name = OPTION_FILES.get(y)
        if name is None:
            continue
        p = Path(root) / name
        if not p.exists() or p.stat().st_size < 1000:
            raise FileNotFoundError(
                f"{name} missing or still a Git LFS pointer -- run 'git lfs pull'")
        df = pd.read_csv(p, low_memory=False, usecols=OPT_USECOLS)
        df["trade_date"] = _parse_date_col(df["trade_date"])
        df["expiration"] = _parse_date_col(df["expiration"])
        df["right"] = df["right"].str.upper().str.strip()
        if verbose:
            print(f"  {name}: {len(df):>8,} rows  "
                  f"{df['trade_date'].min().date()} -> {df['trade_date'].max().date()}")
        frames.append(df)

    f = pd.concat(frames, ignore_index=True)
    before = len(f)
    f = f.drop_duplicates(["trade_date", "expiration", "strike", "right"], keep="first")
    if verbose and len(f) != before:
        print(f"  dropped {before - len(f):,} duplicate contract rows")

    f["dte"] = (f["expiration"] - f["trade_date"]).dt.days
    f["trade_date"] = f["trade_date"].dt.date
    f["expiration"] = f["expiration"].dt.date
    for c in ("strike", "bid", "ask", "close", "implied_vol", "delta",
              "underlying_price", "volume"):
        f[c] = pd.to_numeric(f[c], errors="coerce")

    if whole_strikes_only:
        f = f[f["strike"] % 1 == 0]

    return f.sort_values(["trade_date", "expiration", "strike", "right"],
                         ignore_index=True)


def underlying_daily_from_options(opt: pd.DataFrame) -> pd.DataFrame:
    """One underlying_price per trade_date, taken from the option snapshots.

    Every contract on a given trade_date carries the same underlying_price stamp,
    so we take the first.  This is the EOD underlying the options were marked
    against -- the correct series to use for option settlement.
    """
    u = (opt.groupby("trade_date", as_index=False)["underlying_price"].first()
            .rename(columns={"underlying_price": "close"}))
    u["trade_date"] = pd.to_datetime(u["trade_date"])
    return u.sort_values("trade_date", ignore_index=True)


def load_5min(root=ROOT) -> pd.DataFrame:
    """Load the 5-minute intraday underlying bars with a tz-aware NY timestamp."""
    p = Path(root) / FIVE_MIN_FILE
    if not p.exists() or p.stat().st_size < 1000:
        raise FileNotFoundError(f"{FIVE_MIN_FILE} missing or still an LFS pointer")
    df = pd.read_csv(p)
    # "20230707 09:30:00 America/New_York" -> strip tz label, parse naive NY time.
    ts = df["Date"].str.replace(" America/New_York", "", regex=False)
    df["ts"] = pd.to_datetime(ts, format="%Y%m%d %H:%M:%S")
    df["date"] = df["ts"].dt.date
    return df.sort_values("ts", ignore_index=True)


if __name__ == "__main__":
    opt = load_options(verbose=True)
    print(f"\nMERGED options: {len(opt):,} rows | "
          f"{opt['trade_date'].nunique()} trade dates | "
          f"{min(opt['trade_date'])} -> {max(opt['trade_date'])} | "
          f"DTE {opt['dte'].min()}..{opt['dte'].max()}")
    u = underlying_daily_from_options(opt)
    print(f"underlying daily: {len(u)} days, "
          f"close {u['close'].min():.2f}..{u['close'].max():.2f}")
    fm = load_5min()
    print(f"5-min bars: {len(fm):,} rows | {fm['date'].min()} -> {fm['date'].max()}")
