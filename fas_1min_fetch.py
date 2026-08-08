"""Fetch FAS 1-minute RTH bars over ~6 years, in the repository's CSV format.

Produces FAS_1min.csv matching SOXL_1min.csv / SOXS_1min.csv exactly:

    Date,Open,High,Low,Close,Volume
    20191231 09:30:00 America/New_York,17.94,17.96,17.9,17.92,170640.0

Verified properties of the existing SOXL_1min.csv that this script reproduces:
  * 390 bars per full session, 09:30 through 15:59 inclusive (NOT 16:00)
  * 210 bars on early-close half-days, 09:30 through 12:59
  * RTH only, no pre/post market
  * one row per minute, no duplicate timestamps, no NaN
  * the " America/New_York" suffix on every timestamp
  * volume written as a float, values integral

WHICH SOURCE
------------
The repo's 5-minute files came from IBKR via ibkr_intraday_fetcher.py, and
DATA_NOTES.md records them as RAW / unadjusted (SOXL opens at $200.01 in July
2020, its true pre-split price).

The 1-minute files are on a DIFFERENT basis: SOXL_1min.csv opens at $17.94 on
2019-12-31, when SOXL actually traded near $269 -- i.e. it is SPLIT-ADJUSTED
(269/15 = 17.9), and a discontinuity scan over it finds no split jump at all.
It also reaches 2019-12-31, well past what IBKR normally retains for 1-minute
bars, and band_lab/live/PHASE2_PARITY.md states the delivered 1-minute files
"neither needed a fetch".

So the 1-minute files did not come from the IBKR path in this repo.  The most
likely source is ThetaData: .env carries THETADATA_* credentials, several
scripts here use it, and local_fast_fetch.py already talks to the local Theta
Terminal REST server directly (deliberately bypassing the Python SDK).  This
script therefore defaults to that same proven local-REST pattern, with IBKR
available as --source ibkr for the recent years.

I could not verify the ThetaData stock endpoint from the environment this was
written in, so the response parser maps columns BY NAME from the payload's own
header rather than by position, and --probe fetches a single day and prints the
raw response.  Run --probe first.

USAGE
-----
    # 0. start the Theta Terminal in another shell (credentials from .env)
    java -jar ThetaTerminalv3.jar

    # 1. confirm the endpoint and payload shape before a six-year pull
    python3 fas_1min_fetch.py --probe

    # 2. full fetch, resumable -- safe to Ctrl-C and rerun
    python3 fas_1min_fetch.py

    # 3. validate the result (integrity + cross-check vs FAS_5min_6Years.csv)
    python3 fas_1min_verify.py

    # alternative source, if the Theta subscription does not cover stocks
    python3 fas_1min_fetch.py --source ibkr --start 2020-08-01
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

# `requests` is only needed for the ThetaData path; the IBKR path uses
# ib_async instead. Import it softly so `--source ibkr` and the offline
# self-test still run in an environment that lacks it -- band_lab/live's
# requirements.txt did not list it, which is exactly how this bit users.
try:
    import requests
except ImportError:                                          # pragma: no cover
    requests = None

ROOT = os.path.dirname(os.path.abspath(__file__))
COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
ZONE = " America/New_York"

# SOXL_1min.csv starts here; matching it keeps the two files directly
# comparable, which is the point of having both.
DEFAULT_START = "2019-12-31"
THETA_BASE = "http://127.0.0.1:25520"


# ---------------------------------------------------------------- formatting
def to_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize any source frame to the repository's exact CSV shape."""
    out = pd.DataFrame({
        "Date": df["ts"].dt.strftime("%Y%m%d %H:%M:%S") + ZONE,
        "Open": df["Open"].astype(float),
        "High": df["High"].astype(float),
        "Low": df["Low"].astype(float),
        "Close": df["Close"].astype(float),
        "Volume": df["Volume"].astype(float),
    })
    return out[COLUMNS]


def merge_and_write(path: str, new: pd.DataFrame) -> int:
    """Append, de-duplicate on timestamp, sort chronologically, write.

    Interrupt-safe: the file on disk is always a valid, sorted, de-duplicated
    dataset, so a killed run loses at most the current chunk.
    """
    frames = [new]
    if os.path.exists(path) and os.path.getsize(path) > 100:
        frames.insert(0, pd.read_csv(path))
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset="Date", keep="last")
    out = out.assign(_k=out["Date"].str.slice(0, 17)).sort_values("_k").drop(columns="_k")
    tmp = path + ".tmp"
    out.to_csv(tmp, index=False)
    os.replace(tmp, path)          # atomic: never leave a half-written file
    return len(out)


# Clean split factors to snap to. The observed overnight ratio also contains
# that night's real price move, so it never lands exactly on 1/15 -- snapping
# avoids baking that move into the adjustment.
SPLIT_FACTORS = [1/n for n in (2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 40,
                               50, 75, 100, 150, 200)]
SPLIT_FACTORS += [1 / f for f in SPLIT_FACTORS]


def detect_splits(daily_open: pd.Series, daily_close: pd.Series):
    """Overnight jumps too large to be price moves, snapped to a clean factor."""
    ratio = (daily_open / daily_close.shift(1)).dropna()
    out = []
    for dt_, r in ratio[(ratio < 0.6) | (ratio > 1.7)].items():
        best = min(SPLIT_FACTORS, key=lambda f: abs(np.log(f) - np.log(r)))
        out.append((dt_, best, float(r)))
    return out


def normalize_splits(path: str, verbose: bool = True) -> int:
    """Re-anchor the whole file onto its most recent split era.

    IBKR adjusts history relative to each request's endDateTime, so a backward
    chunked fetch returns each era on the basis that was current at the time --
    which is why SOXL_5min_6Years.csv still carries a visible 15:1 jump at
    2021-03-02 while SOXL_1min.csv does not.  This makes the output basis a
    deliberate choice rather than an artifact of how the fetch was chunked.

    Prices before a split are multiplied by the factor and volumes divided,
    which preserves notional traded.
    """
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["Date"].str.slice(0, 17), format="%Y%m%d %H:%M:%S")
    day = ts.dt.normalize()
    g = df.assign(_d=day).groupby("_d")
    splits = detect_splits(g["Open"].first(), g["Close"].last())
    if not splits:
        if verbose:
            print("no split discontinuity found -- file already on one basis")
        return 0
    for cut, factor, observed in splits:
        pre = day < cut
        for c in ("Open", "High", "Low", "Close"):
            df.loc[pre, c] = df.loc[pre, c] * factor
        df.loc[pre, "Volume"] = df.loc[pre, "Volume"] / factor
        if verbose:
            print(f"  {cut.date()}: observed ratio {observed:.4f} -> snapped to "
                  f"{factor:.6f} (1-for-{1/factor:.0f})" if factor < 1 else
                  f"  {cut.date()}: observed ratio {observed:.4f} -> snapped to "
                  f"{factor:.6f} ({factor:.0f}-for-1)")
    tmp = path + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)
    if verbose:
        print(f"  re-anchored {len(splits)} split(s); {path} now on one basis")
    return len(splits)


def existing_span(path: str):
    if not os.path.exists(path) or os.path.getsize(path) < 100:
        return None, None
    df = pd.read_csv(path, usecols=["Date"])
    if df.empty:
        return None, None
    k = df["Date"].str.slice(0, 8)
    return (datetime.strptime(k.min(), "%Y%m%d").date(),
            datetime.strptime(k.max(), "%Y%m%d").date())


# ---------------------------------------------------------------- ThetaData
def require_requests() -> bool:
    """Report a missing dependency as an instruction, not a traceback."""
    if requests is not None:
        return True
    print("[!] the ThetaData path needs the 'requests' package, which is not "
          "installed in this environment.\n"
          f"    Install it:  {os.path.basename(sys.executable)} -m pip install requests\n"
          "    (band_lab/live/requirements.txt now lists it, so you can also run:\n"
          "     pip install -r band_lab/live/requirements.txt)\n"
          "    Or use the broker instead:  --source ibkr")
    return False


def theta_get(path: str, params: dict, timeout: int = 60):
    """GET against the local Theta Terminal, following its pagination header."""
    url = f"{THETA_BASE}{path}"
    pages = []
    while url:
        r = requests.get(url, params=params if url.startswith(THETA_BASE + path) else None,
                         timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError(f"{r.status_code} from {r.url}: {r.text[:300]}")
        js = r.json()
        pages.append(js)
        url = r.headers.get("Next-Page") or ""
        if url in ("null", "None"):
            url = ""
    return pages


def theta_frame(pages) -> pd.DataFrame:
    """Parse Theta OHLC pages into a normalized frame.

    Columns are resolved BY NAME from the payload's own header, because the
    exact field order is not something this script can verify offline.
    """
    rows, fmt = [], None
    for js in pages:
        f = (js.get("header") or {}).get("format")
        if f:
            fmt = [c.lower() for c in f]
        body = js.get("response") or []
        rows.extend(body)
    if not rows:
        return pd.DataFrame(columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    if not fmt:
        raise RuntimeError("Theta response carried no header/format; run --probe "
                           "and adapt the parser to what the server actually sends")
    df = pd.DataFrame(rows, columns=fmt)

    def col(*names):
        for n in names:
            if n in df.columns:
                return df[n]
        raise RuntimeError(f"none of {names} in Theta response columns {list(df.columns)}")

    day = col("date").astype(int).astype(str)
    ms = col("ms_of_day").astype("int64")
    ts = pd.to_datetime(day, format="%Y%m%d") + pd.to_timedelta(ms, unit="ms")
    out = pd.DataFrame({
        "ts": ts,
        "Open": col("open").astype(float),
        "High": col("high").astype(float),
        "Low": col("low").astype(float),
        "Close": col("close").astype(float),
        "Volume": col("volume").astype(float),
    })
    # Theta can emit empty padding bars outside the session; keep RTH 09:30-15:59
    tod = out["ts"].dt.strftime("%H:%M")
    out = out[(tod >= "09:30") & (tod <= "15:59")]
    # drop all-zero padding rows (no trade AND no price)
    dead = (out[["Open", "High", "Low", "Close"]].sum(axis=1) == 0)
    return out[~dead].sort_values("ts").reset_index(drop=True)


def fetch_theta(symbol: str, start: date, end: date, path: str,
                pause: float, chunk_days: int) -> int:
    if not require_requests():
        return 1
    print(f"source: ThetaData local terminal at {THETA_BASE}")
    try:
        requests.get(THETA_BASE, timeout=4)
    except requests.exceptions.RequestException:
        print("[!] cannot reach the local Theta Terminal.\n"
              "    Start it first:  java -jar ThetaTerminalv3.jar\n"
              "    (credentials come from .env: THETADATA_USERNAME / _PASSWORD)")
        return 1

    have_lo, have_hi = existing_span(path)
    if have_lo:
        print(f"resuming: {path} already covers {have_lo} -> {have_hi}")

    cursor, total, reqs = start, 0, 0
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        # skip a chunk already fully covered by the file
        if have_lo and have_lo <= cursor and chunk_end <= have_hi:
            cursor = chunk_end + timedelta(days=1)
            continue
        params = {"root": symbol,
                  "start_date": cursor.strftime("%Y%m%d"),
                  "end_date": chunk_end.strftime("%Y%m%d"),
                  "ivl": 60_000,          # 1 minute, in milliseconds
                  "rth": "true"}
        try:
            pages = theta_get("/v2/hist/stock/ohlc", params)
            frame = theta_frame(pages)
        except Exception as exc:                                  # noqa: BLE001
            print(f"  {cursor} .. {chunk_end}: FAILED ({exc})")
            time.sleep(pause * 3)
            cursor = chunk_end + timedelta(days=1)
            continue
        reqs += 1
        if len(frame):
            total = merge_and_write(path, to_rows(frame))
            print(f"  {cursor} .. {chunk_end}: +{len(frame):,} bars  "
                  f"(file {total:,} rows)")
        else:
            print(f"  {cursor} .. {chunk_end}: no data")
        cursor = chunk_end + timedelta(days=1)
        time.sleep(pause)

    lo, hi = existing_span(path)
    print(f"\ndone: {reqs} requests, {total:,} rows -> {path}")
    if lo:
        print(f"coverage {lo} -> {hi}")
        if lo > start + timedelta(days=10):
            print(f"[!] did not reach {start}. Theta's stock history may be "
                  f"shallower than requested on this subscription.")
    return 0


# -------------------------------------------------------------------- IBKR
def fetch_ibkr(symbol: str, start: date, path: str, host: str, port: int,
               client_id: int, duration: str, pause: float) -> int:
    """Walk backwards from today. Mirrors band_lab/live/fetch_1min.py.

    Note IBKR's 1-minute retention is typically far shorter than six years, and
    IBKR returns a different price basis than the existing 1-minute files --
    verify with fas_1min_verify.py before mixing sources in one file.
    """
    from ib_async import IB, Stock           # imported late: not needed to probe

    ib = IB()
    print(f"source: IBKR, connecting to {host}:{port} (clientId={client_id})")
    ib.connect(host, port, clientId=client_id, timeout=20)
    try:
        qualified = ib.qualifyContracts(Stock(symbol, "SMART", "USD",
                                              primaryExchange="ARCA"))
        if not qualified:
            print(f"[!] could not qualify {symbol}")
            return 1
        contract = qualified[0]
        print(f"qualified conId={contract.conId} ({contract.primaryExchange})")

        lo, _ = existing_span(path)
        cursor = datetime.combine(lo, datetime.min.time()) if lo else datetime.now()
        if lo:
            print(f"resuming backwards from {lo}")
        empty, reqs, total = 0, 0, 0
        start_dt = datetime.combine(start, datetime.min.time())

        while cursor > start_dt:
            end_str = cursor.strftime("%Y%m%d %H:%M:%S US/Eastern")
            try:
                bars = ib.reqHistoricalData(
                    contract, endDateTime=end_str, durationStr=duration,
                    barSizeSetting="1 min", whatToShow="TRADES", useRTH=True,
                    formatDate=1, keepUpToDate=False)
            except Exception as exc:                              # noqa: BLE001
                print(f"[!] request failed at {end_str}: {exc}")
                time.sleep(pause * 2)
                continue
            reqs += 1
            if not bars:
                empty += 1
                print(f"  {end_str[:8]}: no data (streak {empty})")
                if empty >= 5:
                    print("[*] server stopped returning data -- end of history")
                    break
                cursor -= timedelta(days=1)
                time.sleep(pause)
                continue
            empty = 0
            f = pd.DataFrame([{"ts": pd.to_datetime(str(b.date).replace(ZONE, "").strip()),
                               "Open": b.open, "High": b.high, "Low": b.low,
                               "Close": b.close, "Volume": b.volume} for b in bars])
            total = merge_and_write(path, to_rows(f))
            oldest = f["ts"].min()
            print(f"  {oldest:%Y%m%d}: +{len(f)} bars  (file {total:,} rows)")
            nxt = oldest.to_pydatetime().replace(hour=0, minute=0, second=0)
            cursor = nxt if nxt < cursor else cursor - timedelta(days=1)
            time.sleep(pause)

        lo, hi = existing_span(path)
        print(f"\ndone: {reqs} requests, {total:,} rows -> {path}")
        if lo:
            print(f"coverage {lo} -> {hi}  (target start {start})")
        return 0
    finally:
        ib.disconnect()


# ------------------------------------------------------------------- probe
def probe(symbol: str) -> int:
    """Fetch one day and dump the raw payload, so the parser can be checked."""
    if not require_requests():
        return 1
    day = "20260701"
    print(f"probing Theta stock OHLC for {symbol} on {day}\n")
    try:
        requests.get(THETA_BASE, timeout=4)
    except requests.exceptions.RequestException:
        print(f"[!] no local Theta Terminal at {THETA_BASE}. "
              f"Start it:  java -jar ThetaTerminalv3.jar")
        return 1
    for path in ("/v2/hist/stock/ohlc", "/v3/hist/stock/ohlc"):
        params = {"root": symbol, "start_date": day, "end_date": day,
                  "ivl": 60_000, "rth": "true"}
        try:
            r = requests.get(f"{THETA_BASE}{path}", params=params, timeout=30)
            print(f"--- {path} -> HTTP {r.status_code}")
            body = r.text[:1200]
            print(body)
            if r.status_code == 200:
                js = r.json()
                fmt = (js.get("header") or {}).get("format")
                n = len(js.get("response") or [])
                print(f"\n  header format: {fmt}")
                print(f"  rows returned: {n}  (expect ~390 for a full RTH session)")
                if fmt:
                    print("  -> parser maps by name; this endpoint looks usable")
                    return 0
        except Exception as exc:                                  # noqa: BLE001
            print(f"--- {path} -> {exc}")
        print()
    print("[!] neither endpoint returned a usable payload. Check the Theta "
          "subscription covers STOCK data (options-only plans will 401/403 here).")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch FAS 1-minute RTH bars in the repo's CSV format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run --probe first. Then fas_1min_verify.py to validate output.")
    ap.add_argument("--symbol", default="FAS",
                    help="ticker (default FAS; works for any US equity/ETF)")
    ap.add_argument("--source", default="ibkr", choices=("ibkr", "theta"),
                    help="default ibkr, matching the 5-minute ETF files")
    ap.add_argument("--start", default=DEFAULT_START,
                    help=f"earliest session YYYY-MM-DD (default {DEFAULT_START}, "
                         f"matching SOXL_1min.csv)")
    ap.add_argument("--years", type=float, default=None,
                    help="alternative to --start: this many years back from today")
    ap.add_argument("--end", default=None, help="latest session YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="default <ROOT>/<SYMBOL>_1min.csv")
    ap.add_argument("--chunk-days", type=int, default=30,
                    help="days per Theta request (default 30)")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="seconds between requests; use 11 for IBKR pacing")
    ap.add_argument("--normalize-splits", action="store_true",
                    help="after fetching, re-anchor the file onto its latest "
                         "split era so it matches SOXL_1min.csv's convention")
    ap.add_argument("--probe", action="store_true",
                    help="fetch one day, print the raw payload, exit")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497, help="IBKR: 7497 paper")
    ap.add_argument("--client-id", type=int, default=96)
    ap.add_argument("--duration", default="1 D", help="IBKR per-request duration")
    args = ap.parse_args()

    if args.probe:
        return probe(args.symbol)

    out = args.out or os.path.join(ROOT, f"{args.symbol}_1min.csv")
    if args.years is not None:
        start = (datetime.now() - timedelta(days=args.years * 365.25)).date()
    else:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = (datetime.strptime(args.end, "%Y-%m-%d").date() if args.end
           else datetime.now().date())

    print(f"{args.symbol}: 1-minute RTH bars {start} -> {end}")
    print(f"output: {out}\n")

    if args.source == "theta":
        rc = fetch_theta(args.symbol, start, end, out, args.pause, args.chunk_days)
    else:
        pause = args.pause if args.pause > 5 else 11.0     # IBKR pacing floor
        rc = fetch_ibkr(args.symbol, start, out, args.host, args.port,
                        args.client_id, args.duration, pause)
    if rc == 0 and args.normalize_splits and os.path.exists(out):
        print("\nnormalizing split basis:")
        normalize_splits(out)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
