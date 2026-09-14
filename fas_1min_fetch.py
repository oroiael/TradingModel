"""Fetch 1-minute RTH bars over ~6 years, in the repository's CSV format.

Written for FAS; symbol-agnostic in use -- `--symbol` takes any US equity or
ETF, and the listing venue is looked up per symbol (see PRIMARY_EXCHANGE).

Produces <SYMBOL>_1min.csv matching SOXL_1min.csv / SOXS_1min.csv exactly:

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
IBKR, by default -- the same vendor as the 5-minute ETF files.  FAS_1MIN_CAPTURE.md
records the evidence (the two SOXL files are demonstrably the same data, 15x
apart before the 2021-03-02 split and identical after it) and retracts an earlier
argument in this docstring that the 1-minute files must have come from ThetaData.
The differing price basis is a property of how a fetch is chunked, not of who
supplied it: IBKR adjusts each request relative to its own endDateTime.

ThetaData remains available as `--source theta`.  Its stock endpoint could not be
verified from the environment this was written in, so the response parser maps
columns BY NAME from the payload's own header rather than by position, and
--probe fetches a single day and prints the raw response.  Run --probe first if
you use that path.

USAGE
-----
    # 0. TWS or IB Gateway running, API enabled (paper = port 7497)
    python3 check_tws.py                                  # connectivity smoke test

    # 1. full fetch, resumable -- safe to Ctrl-C and rerun
    python3 fas_1min_fetch.py --symbol FAS --normalize-splits

    # 2. validate the result (integrity + cross-check vs FAS_5min_6Years.csv)
    python3 fas_1min_verify.py --symbol FAS

    # the six-ETF set; the listing venue is resolved per symbol
    for s in TQQQ FAS SPXL MUU BULZ TMF; do
        python3 fas_1min_fetch.py --symbol $s --normalize-splits
    done

    # ThetaData instead, if an IBKR depth limit bites.  Start the terminal
    # first (Java 21+, creds.txt beside the jar), then probe before committing
    # to a full pull -- it reports which route the terminal answers on.
    python3 fas_1min_fetch.py --source theta --probe
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

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

from ibkr_env import require_ib_async

ROOT = os.path.dirname(os.path.abspath(__file__))
COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
ZONE = " America/New_York"
NY = ZoneInfo("America/New_York")

# Primary listing exchange per symbol, resolved from IBKR's own contract search
# on 2026-09-07 (conId in the comment). This matters: IBKR's documentation warns
# that "historical data for securities which move to a new exchange will often
# not be available prior to the time of the move ... this limitation also
# applied to contract which specifies SMART as the exchange"
# (TWS API/TWS Documentation - Copy Paste from Online.pdf, "Unavailable
# Historical Data"), so the listing venue is part of the request, not decoration.
#
# ARCA was hard-coded here until 2026-09-07, which silently excluded every
# NASDAQ- and BATS-listed name in this repository's own universe.
PRIMARY_EXCHANGE = {
    "TQQQ": "NASDAQ",   # 72539702  ProShares UltraPro QQQ
    "MUU":  "NASDAQ",   # 734424283 Direxion Daily MU Bull 2X
    "FAS":  "ARCA",     # 97276826  Direxion Daily Financial Bull 3X
    "SPXL": "ARCA",     # 55679428  Direxion Daily S&P 500 Bull 3X
    "BULZ": "ARCA",     # 593821806 MicroSectors FANG & Innovation 3X (ETN)
    "TMF":  "ARCA",     # 665380902 Direxion Daily 20+ Year Treasury Bull 3X
    "SOXL": "ARCA",     # matches check_tws.py, which connects successfully
    "SOXS": "ARCA",     # 892340391
    "UVXY": "BATS",     # 829567196 -- not ARCA, despite UVXY_1min.csv existing
}
DEFAULT_PRIMARY = "ARCA"


def primary_exchange(symbol: str) -> str:
    """The listing venue to qualify on. Unknown symbols keep the old default."""
    return PRIMARY_EXCHANGE.get(symbol.upper(), DEFAULT_PRIMARY)


# SOXL_1min.csv starts here; matching it keeps the two files directly
# comparable, which is the point of having both.
DEFAULT_START = "2019-12-31"

# Theta Terminal v3 serves on 25503 (25504 is the staging environment). This
# file carried 25520 until 2026-09-09, so every health check reported "no local
# Theta Terminal" against a terminal that was in fact running. Override with
# --theta-port, or the THETA_PORT environment variable.
THETA_PORT = int(os.environ.get("THETA_PORT", "25503"))
THETA_BASE = f"http://127.0.0.1:{THETA_PORT}"


def set_theta_port(port: int) -> None:
    """Point this module at a different terminal. Called from main()."""
    global THETA_PORT, THETA_BASE
    THETA_PORT = port
    THETA_BASE = f"http://127.0.0.1:{port}"


# Route and parameter shape per terminal generation. theta_frame() resolves
# response columns BY NAME from the payload's own header, so only the REQUEST
# differs between these: v3 renamed `root` to `symbol` and replaced the
# millisecond `ivl` with `interval`.
#
# Neither shape can be exercised from the environment this was written in --
# ThetaData's documentation is egress-blocked here -- so theta_route() tries
# each in turn against a single day and uses whichever answers, and --probe
# prints the raw payload rather than assuming. v3 caps a multi-day request at
# one month, which is what --chunk-days 30 already respects.
def _v3_params(symbol: str, start: str, end: str) -> dict:
    return {"symbol": symbol, "start_date": start, "end_date": end,
            "interval": "1m", "rth": "true"}


def _v2_params(symbol: str, start: str, end: str) -> dict:
    return {"root": symbol, "start_date": start, "end_date": end,
            "ivl": 60_000, "rth": "true"}


THETA_ROUTES = [("/v3/stock/history/ohlc", _v3_params),
                ("/v2/hist/stock/ohlc", _v2_params)]


# ------------------------------------------------------------- IBKR bar time
def bar_timestamp(raw) -> pd.Timestamp:
    """An IBKR bar timestamp as naive exchange wall-clock, whatever form it takes.

    `ib_async.util.parseIBDatetime` can hand back any of four things depending on
    the TWS version and its configured timezone -- band_lab/live/broker.py's
    `bar_time_et` documents them from that package's source:

      * a tz-aware datetime carrying an IANA zone,
      * a tz-aware UTC datetime decoded from an epoch,
      * a naive datetime (already exchange time, the convention the CSVs use),
      * a bare `date`, for daily bars.

    This used to be `pd.to_datetime(str(b.date).replace(" America/New_York", ""))`,
    which is right only for the naive case. Given a UTC-decoded bar it would have
    written 13:30 under an " America/New_York" suffix -- a four-hour error stamped
    with the wrong zone -- and a run that mixed aware and naive chunks would put
    an object-dtype column into `to_rows`, where `.dt.strftime` raises.
    """
    if isinstance(raw, date) and not isinstance(raw, datetime):
        # A daily bar has no clock time; the session open is the only defensible
        # reading. 1-minute requests should never produce one -- if they do, the
        # verifier's session-grid check is what catches it.
        return pd.Timestamp(datetime.combine(raw, dtime(9, 30)))
    if not isinstance(raw, datetime):
        txt = str(raw).replace(ZONE, "").strip()
        for fmt in ("%Y%m%d %H:%M:%S", "%Y%m%d  %H:%M:%S", "%Y%m%d-%H:%M:%S"):
            try:
                return pd.Timestamp(datetime.strptime(txt, fmt))
            except ValueError:
                continue
        raise ValueError(f"unparseable IBKR bar date {raw!r}")
    if raw.tzinfo is not None:
        return pd.Timestamp(raw.astimezone(NY).replace(tzinfo=None))
    return pd.Timestamp(raw)


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


def theta_route(symbol: str, probe_day: str = "20260701"):
    """Which (path, params-builder) pair this terminal actually answers on.

    Tries each shape in THETA_ROUTES once against a single day and returns the
    first that comes back 200 with a usable header. Returns None having printed
    what each one said -- an options-only subscription 401s or 403s here.
    """
    for path, build in THETA_ROUTES:
        try:
            r = requests.get(f"{THETA_BASE}{path}",
                             params=build(symbol, probe_day, probe_day),
                             timeout=30)
        except Exception as exc:                                  # noqa: BLE001
            print(f"  {path}: {exc}")
            continue
        if r.status_code == 200:
            try:
                if (r.json().get("header") or {}).get("format"):
                    return path, build
            except ValueError:
                pass
        print(f"  {path}: HTTP {r.status_code}  {r.text[:160]}")
    return None


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

    print("resolving the terminal's stock OHLC route:")
    route = theta_route(symbol)
    if route is None:
        print("[!] this terminal answered none of the known stock OHLC routes.\n"
              f"    Tried: {', '.join(r for r, _ in THETA_ROUTES)}\n"
              "    Check the subscription covers STOCK data (options-only plans\n"
              "    401/403 here), and that --theta-port matches the port the\n"
              "    terminal printed on startup.")
        return 1
    route_path, build_params = route
    print(f"  using {route_path}\n")

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
        params = build_params(symbol, cursor.strftime("%Y%m%d"),
                              chunk_end.strftime("%Y%m%d"))
        try:
            pages = theta_get(route_path, params)
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
               client_id: int, duration: str, pause: float,
               exchange: str = "SMART", primary: str | None = None) -> int:
    """Walk backwards from today. Mirrors band_lab/live/fetch_1min.py.

    Depth is not something to assume. IBKR's documented "Unavailable Historical
    Data" list caps bars of *30 seconds or less* at six months and says nothing
    about 1-minute retention, so the loop discovers the end of history by
    stopping after five consecutive empty responses and reports the earliest
    session it actually reached.

    IBKR also returns a price basis relative to each request's endDateTime, so a
    chunked backward walk can differ from the existing 1-minute files -- verify
    with fas_1min_verify.py before mixing sources in one file.
    """
    # Imported late: not needed to probe, and the guard turns a bare
    # ModuleNotFoundError into the interpreter diagnosis that actually names
    # the fault -- see ibkr_env.py.
    require_ib_async()
    from ib_async import IB, Stock

    if primary is None:
        primary = primary_exchange(symbol)

    ib = IB()
    print(f"source: IBKR, connecting to {host}:{port} (clientId={client_id})")
    ib.connect(host, port, clientId=client_id, timeout=20)
    try:
        print(f"qualifying {symbol} on {exchange}"
              f"{f' (primary {primary})' if primary else ''}")
        qualified = ib.qualifyContracts(Stock(symbol, exchange, "USD",
                                              primaryExchange=primary or ""))
        if not qualified and primary:
            # A wrong listing venue is the likeliest cause, and it is worth one
            # retry rather than an operator-hours round trip: let IBKR resolve
            # the venue and print what it chose, so PRIMARY_EXCHANGE can be
            # corrected instead of guessed at.
            print(f"[!] {symbol} did not qualify as {primary}; "
                  f"retrying without a primary exchange")
            qualified = ib.qualifyContracts(Stock(symbol, exchange, "USD"))
        if not qualified:
            print(f"[!] could not qualify {symbol} on {exchange}")
            return 1
        contract = qualified[0]
        print(f"qualified conId={contract.conId} ({contract.primaryExchange})")
        if primary and contract.primaryExchange and \
                contract.primaryExchange != primary:
            print(f"[!] IBKR resolved {symbol} to {contract.primaryExchange}, "
                  f"not {primary} -- update PRIMARY_EXCHANGE in this file")

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
            f = pd.DataFrame([{"ts": bar_timestamp(b.date),
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
        print(f"[!] no local Theta Terminal at {THETA_BASE}.\n"
              "    Start it:  java -jar ThetaTerminalv3.jar\n"
              "    (needs Java 21+, and creds.txt beside the jar: email on line\n"
              "     one, password on line two)\n"
              "    v3 serves on 25503; if yours printed a different port on\n"
              "    startup, pass --theta-port.")
        return 1
    for path, build in THETA_ROUTES:
        params = build(symbol, day, day)
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
    print("[!] no known route returned a usable payload. Check the Theta "
          "subscription covers STOCK data (options-only plans will 401/403 "
          "here), and that --theta-port matches the terminal's port.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch FAS 1-minute RTH bars in the repo's CSV format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Then fas_1min_verify.py to validate the output. On --source "
               "theta, run --probe first.")
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
    ap.add_argument("--theta-port", type=int, default=None,
                    help=f"ThetaData terminal port (default {THETA_PORT}; v3 "
                         f"serves 25503, 25504 is staging)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497, help="IBKR: 7497 paper")
    ap.add_argument("--client-id", type=int, default=96)
    ap.add_argument("--duration", default="1 D",
                    help='IBKR per-request duration. IBKR\'s own client '
                         'documents durations "up to one week"; "1 W" is ~5x '
                         'faster, so try it on one symbol and verify the output')
    ap.add_argument("--exchange", default="SMART",
                    help="IBKR routing exchange (default SMART)")
    ap.add_argument("--primary", default=None,
                    help="IBKR primary listing exchange; default is looked up "
                         "per symbol (TQQQ/MUU NASDAQ, UVXY BATS, else ARCA). "
                         "Pass '' to let IBKR resolve it")
    args = ap.parse_args()

    if args.theta_port:
        set_theta_port(args.theta_port)
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
                        args.client_id, args.duration, pause,
                        args.exchange, args.primary)
    if rc == 0 and args.normalize_splits and os.path.exists(out):
        print("\nnormalizing split basis:")
        normalize_splits(out)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
