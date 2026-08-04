"""
Freeze the IBKR daily reference series into CSVs so the analysis reproduces
without re-hitting the broker.

Sources are IBKR `get_price_history` dumps (ONE_DAY, RTH, 5 years). They land
in the session's tool-results directory, which is ephemeral; this copies what
is needed into `vix_lab/data/`.

Why these seven:
  VIXY  1.0x VIX short-term futures ETF  -- the clean 1x reference (an ETF, so
        unlike VXX it was never halted; see UVXY_EVALUATION.md 1.2)
  VIXM  VIX MID-term futures ETF         -- with VIXY, a tradeable proxy for the
        term-structure slope, which is UVXY's dominant return driver
  SVXY  -0.5x, SVIX -1.0x                -- the short-vol side
  SPY   equity reference                 -- to separate "vol moved" from
                                            "the market moved"
  UUP   dollar index ETF (DXY proxy)
  FXY   yen ETF                          -- the 2024-08-05 carry unwind channel

IBKR has no entitlement here for the VIX index itself (`get_price_history` on
conid 13455763 returns "Details currently unavailable"), so the spot index is
not available and every volatility series below is a *futures* product. That
is the right basis anyway -- UVXY tracks futures, not spot.

Run:
    python3 vix_lab/fetch_refs.py
"""

from __future__ import annotations

import json
import os

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_HERE, "data")

TOOL = ("/root/.claude/projects/-home-user-TradingModel/"
        "36405402-2c9f-56a7-a70f-f169d7eb5d65/tool-results")

DUMPS = {
    "VIXY": "mcp-Interactive_Brokers_IBKR-get_price_history-1785753003320.txt",
    "SVXY": "mcp-Interactive_Brokers_IBKR-get_price_history-1785753583699.txt",
    "SVIX": "mcp-Interactive_Brokers_IBKR-get_price_history-1785753587632.txt",
    "VIXM": "mcp-Interactive_Brokers_IBKR-get_price_history-1785872770252.txt",
    "SPY":  "mcp-Interactive_Brokers_IBKR-get_price_history-1785872823724.txt",
    "UUP":  "mcp-Interactive_Brokers_IBKR-get_price_history-1785872825091.txt",
    "FXY":  "mcp-Interactive_Brokers_IBKR-get_price_history-1785872825938.txt",
}


def to_frame(path: str) -> pd.DataFrame:
    d = json.load(open(path))
    idx = (pd.to_datetime(d["time"]).tz_convert("America/New_York")
           .tz_localize(None).normalize())
    df = pd.DataFrame({"Open": d["open"], "High": d["high"], "Low": d["low"],
                       "Close": d["close"], "Volume": d["volume"]}, index=idx)
    df.index.name = "date"
    return df[~df.index.duplicated()].sort_index()


def load(sym: str) -> pd.DataFrame:
    """Cached daily bars for one reference symbol."""
    p = os.path.join(DATA, f"{sym}_daily.csv")
    if not os.path.exists(p):
        raise FileNotFoundError(f"{p} missing — run vix_lab/fetch_refs.py")
    return pd.read_csv(p, index_col=0, parse_dates=True)


def main() -> int:
    os.makedirs(DATA, exist_ok=True)
    for sym, fn in DUMPS.items():
        src = os.path.join(TOOL, fn)
        if not os.path.exists(src):
            print(f"{sym:<6} SKIP — dump not present ({fn})")
            continue
        df = to_frame(src)
        out = os.path.join(DATA, f"{sym}_daily.csv")
        df.to_csv(out)
        print(f"{sym:<6} {len(df):>5} sessions  {df.index.min().date()} -> "
              f"{df.index.max().date()}  -> {os.path.relpath(out, _HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
