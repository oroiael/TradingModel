"""Shared loaders for the covered-call + long-dated-put backtest."""
import functools
import os
import numpy as np
import pandas as pd

ROOT = "/home/user/TradingModel"
OUT = os.path.join(ROOT, "cc_lp_lab/out")
SPLIT_DATE = pd.Timestamp("2021-03-02")   # 15:1 forward split, before option data


@functools.lru_cache(maxsize=1)
def underlying_5min():
    """5-min OHLCV, tz-naive ET index. Raw basis (split is pre-2022, outside window)."""
    df = pd.read_csv(os.path.join(ROOT, "SOXL_5min_6Years.csv"))
    ts = df["Date"].str.replace(" America/New_York", "", regex=False)
    df["ts"] = pd.to_datetime(ts, format="%Y%m%d %H:%M:%S")
    df["date"] = df["ts"].dt.normalize()
    df["minute"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    return df[["ts", "date", "minute", "Open", "High", "Low", "Close", "Volume"]]


@functools.lru_cache(maxsize=1)
def spot_at(minute=600):
    """Series date -> underlying price at the given minute-of-day (default 10:00).

    Uses the OPEN of that 5-min bar: an order worked at 10:00 fills at the price
    prevailing when the bar starts. Falls back to the nearest later bar that day
    (early closes / missing stamps), then to the session close.
    """
    u = underlying_5min()
    out = {}
    for d, g in u.groupby("date"):
        g = g.sort_values("minute")
        hit = g[g["minute"] >= minute]
        row = hit.iloc[0] if len(hit) else g.iloc[-1]
        out[d] = (row["Open"], row["minute"])
    s = pd.DataFrame(out, index=["px", "minute"]).T
    return s


@functools.lru_cache(maxsize=1)
def daily_close():
    u = underlying_5min()
    return u.groupby("date")["Close"].last()


@functools.lru_cache(maxsize=1)
def eod_chain():
    """EOD listed chain: date, exp, strike, right, bid, ask, close, vol, delta, iv, spot."""
    e = pd.read_parquet(os.path.join(OUT, "opt_eod_chain.parquet"))
    e["date"] = pd.to_datetime(e["date"])
    e["exp"] = pd.to_datetime(e["exp"])
    e["right"] = e["right"].astype(str)
    e["dte"] = (e["exp"] - e["date"]).dt.days
    return e


@functools.lru_cache(maxsize=1)
def intraday_trades():
    """5-min option TRADE bars (close px). Only bars where a print occurred."""
    d = pd.read_parquet(os.path.join(OUT, "opt_intraday_trades.parquet"))
    d["date"] = pd.to_datetime(d["date"])
    d["exp"] = pd.to_datetime(d["exp"])
    d["right"] = d["right"].astype(str)
    return d


def trading_days():
    return pd.DatetimeIndex(sorted(underlying_5min()["date"].unique()))
