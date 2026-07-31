"""
Fetch 1-minute RTH bars from IBKR for the fill-resolution study.

Why: PHASE2_PARITY.md S10 — most of the strategy's measured edge comes from
re-entries priced inside the 5-minute bar that exited the previous position.
Five-minute OHLCV cannot say whether those fills are real. One-minute bars
shrink the unresolved window five-fold.

Output matches the repository's 5-minute CSVs exactly, so `intrabar.py` can
read it with the same conventions:

    Date,Open,High,Low,Close,Volume
    20260602 09:30:00 America/New_York,158.12,158.40,157.88,158.02,412300

Run on the machine with TWS (this cannot run in CI — it needs a broker):

    python3 band_lab/live/fetch_1min.py --symbol SOXL --start 2022-01-01
    python3 band_lab/live/fetch_1min.py --symbol SOXS --start 2022-01-01

Then validate and study:

    python3 band_lab/live/intrabar.py --symbol SOXL --check
    python3 band_lab/live/intrabar.py --symbol SOXL

Notes and unverified assumptions (IBKR documentation is not reachable from
the environment this was written in — PHASE2_PLAN.md §6):

* **Chunk size.** The default is one session per request, which is safe for
  1-minute bars. Larger durations may work and are 5-7x faster; try
  `--duration "1 W"` and check the output before trusting it.
* **Pacing.** IBKR limits historical requests (commonly cited as 60 per 10
  minutes). The default 11-second gap stays under that. A 2-year fetch is
  therefore ~90 minutes per symbol; run it overnight.
* **Depth.** IBKR's retention for 1-minute bars may not reach 2022. The
  script stops cleanly when the server stops returning data and reports the
  earliest session it actually got. If it cannot reach the target, see
  `--help` for the note on alternative vendors.
* **Adjustment.** Bars are fetched as TRADES with `useRTH=1`. SOXL's 2021
  split is applied at *read* time by `intrabar.py`, exactly as for the
  5-minute files — do not pre-adjust here.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]


# ------------------------------------------------------------------ helpers
def format_bar_date(value) -> str:
    """Render a bar timestamp in the repository's CSV convention."""
    if isinstance(value, str):
        txt = value.replace(" America/New_York", "").strip()
        for fmt in ("%Y%m%d %H:%M:%S", "%Y%m%d  %H:%M:%S", "%Y%m%d-%H:%M:%S"):
            try:
                dt = datetime.strptime(txt, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"unparseable bar date {value!r}")
    else:
        dt = value
        if getattr(dt, "tzinfo", None) is not None:
            dt = dt.astimezone(NY)
    return f"{dt:%Y%m%d %H:%M:%S} America/New_York"


def bars_to_frame(bars) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Date": format_bar_date(b.date), "Open": b.open, "High": b.high,
          "Low": b.low, "Close": b.close, "Volume": b.volume} for b in bars],
        columns=COLUMNS)


def merge_and_write(path: str, new: pd.DataFrame) -> pd.DataFrame:
    """Append, de-duplicate on the timestamp, sort, write. Safe to interrupt."""
    frames = [new]
    if os.path.exists(path):
        frames.insert(0, pd.read_csv(path))
    out = (pd.concat(frames, ignore_index=True)
           .drop_duplicates(subset="Date", keep="last"))
    key = out["Date"].str.slice(0, 17)
    out = out.assign(_k=key).sort_values("_k").drop(columns="_k")
    out.to_csv(path, index=False)
    return out


def earliest_session(path: str):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    return datetime.strptime(str(df["Date"].min())[:8], "%Y%m%d")


# -------------------------------------------------------------------- fetch
def fetch(symbol: str, start: datetime, path: str, host: str, port: int,
          client_id: int, duration: str, pause: float, exchange: str,
          primary: str) -> int:
    from ib_async import IB, Stock          # imported late: not needed to test

    ib = IB()
    print(f"connecting to {host}:{port} (clientId={client_id}) ...")
    ib.connect(host, port, clientId=client_id, timeout=20)
    try:
        contract = Stock(symbol, exchange, "USD", primaryExchange=primary or "")
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            print(f"[!] could not qualify {symbol} on {exchange}")
            return 1
        contract = qualified[0]
        print(f"qualified conId={contract.conId} ({contract.primaryExchange})")

        cursor = earliest_session(path)
        if cursor:
            print(f"resuming: existing data starts {cursor:%Y-%m-%d}")
        else:
            cursor = datetime.now()
        empty_streak, requests, rows = 0, 0, 0

        while cursor > start:
            end_str = cursor.strftime("%Y%m%d %H:%M:%S US/Eastern")
            try:
                bars = ib.reqHistoricalData(
                    contract, endDateTime=end_str, durationStr=duration,
                    barSizeSetting="1 min", whatToShow="TRADES", useRTH=True,
                    formatDate=1, keepUpToDate=False)
            except Exception as exc:                    # noqa: BLE001
                print(f"[!] request failed at {end_str}: {exc}")
                time.sleep(pause * 2)
                continue
            requests += 1

            if not bars:
                empty_streak += 1
                print(f"  {end_str[:8]}: no data (streak {empty_streak})")
                # A holiday returns nothing; the end of available history
                # returns nothing repeatedly. Five in a row means stop.
                if empty_streak >= 5:
                    print("[*] server stopped returning data — end of history")
                    break
                cursor -= timedelta(days=1)
                time.sleep(pause)
                continue

            empty_streak = 0
            frame = bars_to_frame(bars)
            merged = merge_and_write(path, frame)
            rows = len(merged)
            oldest = str(frame["Date"].min())[:8]
            print(f"  {oldest}: +{len(frame)} bars  (file {rows:,} rows)")

            new_cursor = datetime.strptime(oldest, "%Y%m%d")
            if new_cursor >= cursor:            # no progress: step back manually
                new_cursor = cursor - timedelta(days=1)
            cursor = new_cursor
            time.sleep(pause)

        got = earliest_session(path)
        print(f"\ndone: {requests} requests, {rows:,} rows in {path}")
        if got:
            print(f"earliest session obtained: {got:%Y-%m-%d} "
                  f"(target was {start:%Y-%m-%d})")
            if got.date() > start.date() + timedelta(days=7):
                print("[!] IBKR did not reach the requested start date. Its "
                      "1-minute retention may not go back that far; consider a "
                      "data vendor (Polygon, Databento, Alpaca) for the older "
                      "years, in the same CSV format.")
        return 0
    finally:
        ib.disconnect()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch 1-minute RTH bars from IBKR",
        epilog="If IBKR's history does not reach the requested start, any "
               "vendor will do — intrabar.py only needs the CSV columns "
               "Date,Open,High,Low,Close,Volume with RTH-only 1-minute bars.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--start", required=True, help="earliest session, YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="default <ROOT>/<SYMBOL>_1min.csv")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497, help="7497 TWS paper")
    ap.add_argument("--client-id", type=int, default=97)
    ap.add_argument("--duration", default="1 D",
                    help='per-request duration; "1 W" is faster if it works')
    ap.add_argument("--pause", type=float, default=11.0,
                    help="seconds between requests (IBKR pacing)")
    ap.add_argument("--exchange", default="SMART")
    ap.add_argument("--primary", default="ARCA",
                    help="primary listing exchange; pass '' to omit")
    args = ap.parse_args()

    out = args.out or os.path.join(ROOT, f"{args.symbol}_1min.csv")
    start = datetime.strptime(args.start, "%Y-%m-%d")
    print(f"{args.symbol}: 1-minute RTH bars back to {start:%Y-%m-%d} -> {out}")
    return fetch(args.symbol, start, out, args.host, args.port, args.client_id,
                 args.duration, args.pause, args.exchange, args.primary)


if __name__ == "__main__":
    raise SystemExit(main())
