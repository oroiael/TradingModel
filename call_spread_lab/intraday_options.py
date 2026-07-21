#!/usr/bin/env python3
"""
intraday_options.py  --  loader for the 5-minute OPTION files in raw_data/.

Files: raw_data/SOXL_intraday_5m_exp_<EXPYYYYMMDD>_<YEAR>_<SEG>.csv
One file = one expiration's full chain (both rights, all strikes), 5-min OHLC +
volume + count + vwap, 09:30-16:00 ET, split by capture-month segment. These are
TRADE prices (not bid/ask); no-trade bars have empty OHLC and vwap 0. Coverage is
2024-2025, ~2-3 capture-months (~75 days) before each expiration (104 expirations).

Loads whatever files are present locally (git lfs pull the subset you need). Keeps
only rows with a usable price (vwap>0) unless raw=True.
"""
from __future__ import annotations
from pathlib import Path
import glob
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw_data"
USECOLS = ["expiration", "strike", "right", "timestamp", "high", "low",
           "close", "volume", "vwap"]


def available_expirations():
    """Expirations that have at least one intraday segment file present (>1KB)."""
    exps = {}
    for p in glob.glob(str(RAW / "SOXL_intraday_5m_exp_*.csv")):
        if Path(p).stat().st_size < 10_000:      # skip LFS pointers
            continue
        stem = Path(p).name
        exp = stem.split("_")[4]                 # YYYYMMDD
        exps.setdefault(exp, []).append(p)
    return exps


def load_intraday(files, raw=False) -> pd.DataFrame:
    frames = []
    for p in files:
        df = pd.read_csv(p, usecols=USECOLS)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    f = pd.concat(frames, ignore_index=True)
    f["right"] = f["right"].str.upper().str.strip()
    f["ts"] = pd.to_datetime(f["timestamp"], utc=True).dt.tz_convert("America/New_York")
    f["ts_naive"] = f["ts"].dt.tz_localize(None)
    f["date"] = f["ts"].dt.date
    f["expiration"] = pd.to_datetime(f["expiration"]).dt.date
    for c in ("strike", "high", "low", "close", "vwap", "volume"):
        f[c] = pd.to_numeric(f[c], errors="coerce")
    if not raw:
        f = f[f["vwap"] > 0]
    return f.sort_values(["expiration", "strike", "right", "ts"], ignore_index=True)


def load_all_present(raw=False) -> pd.DataFrame:
    exps = available_expirations()
    files = [p for ps in exps.values() for p in ps]
    return load_intraday(files, raw=raw)


if __name__ == "__main__":
    exps = available_expirations()
    print(f"expirations with intraday files present: {len(exps)}")
    df = load_all_present()
    print(f"loaded {len(df):,} priced 5-min option bars | "
          f"{df['date'].min()} -> {df['date'].max()} | "
          f"{df['expiration'].nunique()} expirations, {df['strike'].nunique()} strikes")
