#!/usr/bin/env python3
"""
signals.py  --  trailing regime indicators for SOXL, computed with NO look-ahead.

Every indicator at date t uses only underlying/IV data up to and including t (the
EOD we enter on), so merging a signal onto a trade's entry_date and comparing to
that trade's future P&L is leak-free.

Indicators (deliberately standard, round parameters -- not tuned to the P&L, to
avoid fitting the answer):
  trend     : px_vs_sma50, px_vs_sma20, sma20_vs_sma50 (golden/death cross)
  momentum  : mom10, mom20, mom60 (trailing returns); rsi14
  volatility: rvol20 (annualized realized vol); iv_atm (from the chain);
              vrp = iv_atm - rvol20 (implied minus realized)
  stress    : dd60 (drawdown from 60-day high); iv_chg20 (IV shock)

These are the candidate "is the trade going against us" flags tested in
run_signals.py for entry gating, inversion, and mid-trade stops.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from data_loader import underlying_daily_from_options


def _rsi(close: pd.Series, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def daily_atm_iv(opt: pd.DataFrame) -> pd.Series:
    """Per-trade_date ATM implied vol: median IV of near-money (|mny|<5%),
    ~monthly (20-45 DTE) calls. A clean daily IV level from the chain itself."""
    c = opt[(opt["right"] == "CALL") & (opt["implied_vol"] > 0)].copy()
    c["mny"] = (c["strike"] / c["underlying_price"] - 1).abs()
    atm = c[(c["mny"] < 0.05) & (c["dte"].between(20, 45))]
    s = atm.groupby("trade_date")["implied_vol"].median()
    s.index = pd.to_datetime(s.index)
    return s.rename("iv_atm")


def build_signals(opt: pd.DataFrame) -> pd.DataFrame:
    u = underlying_daily_from_options(opt).set_index("trade_date")["close"]
    u.index = pd.to_datetime(u.index)
    df = pd.DataFrame(index=u.index)
    df["close"] = u
    df["sma20"] = u.rolling(20).mean()
    df["sma50"] = u.rolling(50).mean()
    df["px_vs_sma20"] = u / df["sma20"] - 1
    df["px_vs_sma50"] = u / df["sma50"] - 1
    df["sma20_vs_sma50"] = df["sma20"] / df["sma50"] - 1      # >0 = golden cross
    df["mom10"] = u / u.shift(10) - 1
    df["mom20"] = u / u.shift(20) - 1
    df["mom60"] = u / u.shift(60) - 1
    df["rsi14"] = _rsi(u, 14)
    logret = np.log(u / u.shift(1))
    df["rvol20"] = logret.rolling(20).std() * np.sqrt(252)
    df["dd60"] = u / u.rolling(60).max() - 1
    iv = daily_atm_iv(opt)
    df = df.join(iv)
    df["iv_atm"] = df["iv_atm"].ffill()
    df["vrp"] = df["iv_atm"] - df["rvol20"]                   # implied - realized
    df["iv_chg20"] = df["iv_atm"] - df["iv_atm"].shift(20)
    df["uptrend"] = df["px_vs_sma50"] > 0                     # headline regime flag
    df.index = df.index.date
    return df


def attach(ledger: pd.DataFrame, sig: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Left-join signal columns onto a trade ledger by entry_date (no look-ahead)."""
    cols = cols or ["close", "px_vs_sma20", "px_vs_sma50", "sma20_vs_sma50",
                    "mom10", "mom20", "mom60", "rsi14", "rvol20", "dd60",
                    "iv_atm", "vrp", "iv_chg20", "uptrend"]
    s = sig[cols].copy()
    out = ledger.copy()
    ed = pd.to_datetime(out["entry_date"]).dt.date
    return out.join(s.reindex(ed).reset_index(drop=True))


if __name__ == "__main__":
    from data_loader import load_options
    opt = load_options(whole_strikes_only=True)
    sig = build_signals(opt)
    print(sig[["close", "px_vs_sma50", "mom20", "rsi14", "rvol20", "iv_atm",
               "vrp", "uptrend"]].describe().round(3).to_string())
    print(f"\nuptrend (spot>SMA50) share of days: {sig['uptrend'].mean():.1%}")
    print(f"IV_atm coverage: {sig['iv_atm'].notna().mean():.1%} of days")
