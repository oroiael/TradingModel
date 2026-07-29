#!/usr/bin/env python3
"""
ibkr_1min_fetcher.py -- 1-minute intraday bars from IBKR, multi-year, resumable.

Walks backward in chunks from today to <YEARS> years ago, checkpointing every
chunk so an interrupted run resumes where it stopped.

Pacing (from IB's documented rules -- all three are enforced here):
  * no more than 60 historical requests in any rolling 10 minutes
  * no identical historical request within 15 seconds
  * no 6+ requests for the same contract/exchange/tick-type within 2 seconds
Plus the per-request size cap: a request may not return more than 2000 bars.
1-minute RTH bars over "1 W" = 5 x 390 = 1950, which fits. Extended hours
(useRTH=0) would be ~1080/day, so that case drops to a "1 D" chunk.

Output matches the repo convention used by band_lab/cycle_lab loaders:
    Date,Open,High,Low,Close,Volume
    20240102 09:30:00 America/New_York,...

Runtime is dominated by pacing, not bandwidth: roughly 313 requests per
symbol-year-set, ~11 s apart -> 60-90 minutes for 6 years of one symbol.

Usage:
    python3 ibkr_1min_fetcher.py --symbols SOXS
    python3 ibkr_1min_fetcher.py --symbols SOXL SOXS --years 6 --port 7497
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta

import pandas as pd
from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

try:
    from zoneinfo import ZoneInfo
except ImportError:  # py<3.9
    ZoneInfo = None

# --- IB pacing limits -------------------------------------------------------
MAX_REQUESTS_PER_WINDOW = 55        # IB's ceiling is 60/10min; leave headroom
PACING_WINDOW_SECONDS = 600
MIN_SECONDS_BETWEEN_REQUESTS = 10.5  # 55 req / 600 s
IDENTICAL_REQUEST_COOLDOWN = 16.0   # IB's rule is 15 s; +1 s of slack
MAX_BARS_PER_REQUEST = 2000         # IB truncates above this

# --- behaviour --------------------------------------------------------------
REQUEST_TIMEOUT_SECONDS = 60        # a 1950-bar chunk can take a while
MAX_RETRIES_PER_CHUNK = 3
MAX_CONSECUTIVE_EMPTY = 10          # ~10 weeks of nothing => past inception
PACING_COOLDOWN_SECONDS = 60

# IB echoes back the timezone you send, so this string ends up in the CSV and
# must match what the existing repo loaders strip. See band_lab/transfer_test.py.
IB_TZ = "America/New_York"

# Informational codes that are not problems.
BENIGN_CODES = {2104, 2106, 2107, 2108, 2119, 2158, 2100, 2150, 2168, 2169, 2174}
# Codes that mean this request/contract will never succeed -- do not retry.
FATAL_CODES = {200, 354, 502, 504, 10197}


class Outcome:
    OK = "ok"
    NO_DATA = "no_data"
    PACING = "pacing"
    RETRY = "retry"
    FATAL = "fatal"


class HistoricalFetcher(EWrapper, EClient):
    def __init__(self) -> None:
        EClient.__init__(self, self)
        self._lock = threading.Lock()
        self.active_req_id: int | None = None
        self.bars: list[dict] = []
        self.done = threading.Event()
        self.outcome: tuple[str, str] = (Outcome.OK, "")
        self.connected_event = threading.Event()
        self.link_ok = threading.Event()
        self.link_ok.set()

    # -- lifecycle ----------------------------------------------------------
    def nextValidId(self, orderId: int) -> None:
        super().nextValidId(orderId)
        self.connected_event.set()

    def begin(self, req_id: int) -> None:
        """Arm the wrapper for a new request. Late replies to older reqIds are
        dropped, so an abandoned request cannot contaminate the next chunk."""
        with self._lock:
            self.active_req_id = req_id
            self.bars = []
            self.outcome = (Outcome.OK, "")
        self.done.clear()

    # -- data callbacks -----------------------------------------------------
    def historicalData(self, reqId, bar) -> None:
        with self._lock:
            if reqId != self.active_req_id:
                return
            # ibapi 10.x hands back Decimal volume; -1 means "unset".
            try:
                volume = float(bar.volume)
            except (TypeError, ValueError):
                volume = float("nan")
            if volume < 0:
                volume = float("nan")
            self.bars.append({
                "Date": re.sub(r"\s+", " ", str(bar.date)).strip(),
                "Open": float(bar.open),
                "High": float(bar.high),
                "Low": float(bar.low),
                "Close": float(bar.close),
                "Volume": volume,
            })

    def historicalDataEnd(self, reqId, start, end) -> None:
        with self._lock:
            if reqId != self.active_req_id:
                return
        self.done.set()

    # -- errors -------------------------------------------------------------
    def error(self, *args) -> None:
        """Parse across ibapi signature versions.

        <=10.29: (reqId, code, msg, advancedOrderRejectJson)
        >=10.30: (reqId, errorTime, code, msg, advancedOrderRejectJson)

        In both, the error code is the LAST int and the message the FIRST str,
        so this is stable without version sniffing.
        """
        ints = [a for a in args if isinstance(a, int)]
        strs = [a for a in args if isinstance(a, str)]
        req_id = ints[0] if ints else -1
        code = ints[-1] if len(ints) >= 2 else (ints[0] if ints else -1)
        msg = strs[0] if strs else ""

        if code in (1100,):
            print(f"[!] Connectivity to TWS lost ({msg}). Waiting for restore...")
            self.link_ok.clear()
            return
        if code in (1101, 1102):
            print("[*] Connectivity to TWS restored.")
            self.link_ok.set()
            return
        if code in BENIGN_CODES:
            return

        with self._lock:
            is_active = req_id == self.active_req_id
        if not is_active:
            if code not in BENIGN_CODES:
                print(f"[-] IBKR message (reqId {req_id}, code {code}): {msg}")
            return

        self._resolve(code, msg)

    def _resolve(self, code: int, msg: str) -> None:
        low = msg.lower()
        if code in FATAL_CODES:
            outcome = (Outcome.FATAL, f"{code}: {msg}")
        elif code == 162:
            # 162 is overloaded: pacing violation, empty result, AND permissions.
            # Treating them alike is what makes a naive loop spin forever.
            if "pacing violation" in low:
                outcome = (Outcome.PACING, msg)
            elif "no data" in low or "query returned no data" in low:
                outcome = (Outcome.NO_DATA, msg)
            elif "permission" in low or "not subscribed" in low:
                outcome = (Outcome.FATAL, f"{code}: {msg}")
            else:
                outcome = (Outcome.RETRY, f"{code}: {msg}")
        elif code == 165:
            return  # HMDS informational notice, request still in flight
        elif code == 366:
            outcome = (Outcome.RETRY, f"{code}: {msg}")
        else:
            outcome = (Outcome.RETRY, f"{code}: {msg}")

        with self._lock:
            self.outcome = outcome
        self.done.set()


class Pacer:
    """Enforces all three of IB's historical-data pacing rules."""

    def __init__(self) -> None:
        self.starts: deque[float] = deque()
        self.last_start = 0.0
        self.last_key: str | None = None
        self.last_key_time = 0.0

    def wait(self, key: str) -> None:
        while True:
            now = time.monotonic()
            while self.starts and now - self.starts[0] > PACING_WINDOW_SECONDS:
                self.starts.popleft()

            waits = []
            if len(self.starts) >= MAX_REQUESTS_PER_WINDOW:
                waits.append(PACING_WINDOW_SECONDS - (now - self.starts[0]) + 0.5)
            gap = MIN_SECONDS_BETWEEN_REQUESTS - (now - self.last_start)
            if gap > 0:
                waits.append(gap)
            # identical-request rule
            if key == self.last_key:
                same = IDENTICAL_REQUEST_COOLDOWN - (now - self.last_key_time)
                if same > 0:
                    waits.append(same)

            delay = max(waits) if waits else 0.0
            if delay <= 0:
                break
            print(f"    (pacing: holding {delay:.1f}s)")
            time.sleep(delay)

        now = time.monotonic()
        self.starts.append(now)
        self.last_start = now
        self.last_key = key
        self.last_key_time = now


def now_exchange() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(IB_TZ)).replace(tzinfo=None)
    return datetime.now()


def parse_ib_datetime(value: str) -> datetime:
    """Handle every formatDate=1 shape IB emits, with or without a tz suffix."""
    text = re.sub(r"\s+", " ", str(value)).strip()
    tokens = text.replace("-", " ", 1).split(" ") if "-" in text[:12] else text.split(" ")
    if len(tokens) == 1:
        return datetime.strptime(tokens[0], "%Y%m%d")
    return datetime.strptime(f"{tokens[0]} {tokens[1]}", "%Y%m%d %H:%M:%S")


def build_contract(symbol: str, sec_type: str, exchange: str, currency: str) -> Contract:
    c = Contract()
    c.symbol = symbol
    c.secType = sec_type
    c.exchange = exchange
    c.currency = currency
    if sec_type == "STK":
        # SMART routing alone is ambiguous for dual-listed names; pin the primary.
        c.primaryExchange = "ARCA"
    return c


def chunk_duration(bar_size: str, use_rth: bool) -> tuple[str, timedelta]:
    """Largest chunk that stays under the 2000-bar cap, with its calendar span."""
    if bar_size != "1 min":
        return ("1 W", timedelta(days=7))
    if use_rth:
        return ("1 W", timedelta(days=7))   # 5 x 390 = 1950 bars
    return ("1 D", timedelta(days=1))       # ~1080 bars extended hours


def bar_label(bar_size: str) -> str:
    return bar_size.replace(" ", "")


def output_path(symbol: str, args: argparse.Namespace) -> str:
    if args.output:
        return args.output
    years = int(args.years) if float(args.years).is_integer() else args.years
    return os.path.join(
        args.outdir, f"{symbol}_{bar_label(args.bar_size)}_{years}Years.csv")


def resume_point(path: str, default: datetime) -> datetime:
    if not os.path.exists(path):
        return default
    try:
        existing = pd.read_csv(path, usecols=["Date"])
    except (ValueError, pd.errors.EmptyDataError) as exc:
        print(f"[!] {path} exists but is not a bar file ({exc}). Refusing to append.")
        sys.exit(1)
    if existing.empty:
        return default
    # Format is fixed-width YYYYMMDD HH:MM:SS, so string min == chronological min.
    oldest = parse_ib_datetime(str(existing["Date"].min()))
    print(f"[*] Found {len(existing):,} existing rows. Resuming backward from "
          f"{oldest:%Y-%m-%d %H:%M:%S}")
    return oldest


def fetch_symbol(app: HistoricalFetcher, pacer: Pacer, req_seq: list[int],
                 symbol: str, args: argparse.Namespace) -> bool:
    contract = build_contract(symbol, args.sec_type, args.exchange, args.currency)
    duration, step = chunk_duration(args.bar_size, bool(args.use_rth))

    end_of_range = now_exchange()
    start_of_range = end_of_range - timedelta(days=int(args.years * 365.25))

    label = bar_label(args.bar_size)
    out_path = output_path(symbol, args)

    # Guard against the classic footgun: appending one bar size into another's
    # file. The repo already contains <SYM>_5min_6Years.csv files that downstream
    # backtests depend on.
    if os.path.exists(out_path) and label not in os.path.basename(out_path):
        print(f"[!] {out_path} does not carry the '{label}' tag. Aborting rather "
              f"than mixing bar sizes.")
        return False

    current_end = resume_point(out_path, end_of_range)

    total_chunks = max(1, int((current_end - start_of_range) / step))
    est_minutes = total_chunks * (MIN_SECONDS_BETWEEN_REQUESTS + 3) / 60
    print(f"\n=== {symbol}: {args.bar_size} bars back to {start_of_range:%Y-%m-%d} ===")
    print(f"    chunk={duration}  useRTH={args.use_rth}  file={out_path}")
    print(f"    ~{total_chunks} requests, est. {est_minutes:.0f} min\n")

    consecutive_empty = 0
    rows_written = 0

    while current_end > start_of_range:
        if not app.isConnected():
            print("[!] Disconnected from TWS. Stopping; rerun to resume.")
            return False
        app.link_ok.wait(timeout=300)

        end_str = f"{current_end:%Y%m%d %H:%M:%S} {IB_TZ}"
        chunk_ok = False

        for attempt in range(1, MAX_RETRIES_PER_CHUNK + 1):
            req_seq[0] += 1
            req_id = req_seq[0]
            pacer.wait(end_str)

            print(f"[>] {symbol} {duration} ending {end_str}"
                  f"{f' (attempt {attempt})' if attempt > 1 else ''}")
            app.begin(req_id)
            app.reqHistoricalData(
                reqId=req_id, contract=contract, endDateTime=end_str,
                durationStr=duration, barSizeSetting=args.bar_size,
                whatToShow=args.what_to_show, useRTH=args.use_rth,
                formatDate=1, keepUpToDate=False, chartOptions=[])

            if not app.done.wait(timeout=REQUEST_TIMEOUT_SECONDS):
                print(f"[!] No response in {REQUEST_TIMEOUT_SECONDS}s. Cancelling.")
                app.cancelHistoricalData(req_id)
                with app._lock:
                    app.active_req_id = None
                continue

            status, message = app.outcome
            with app._lock:
                bars = list(app.bars)

            if status == Outcome.FATAL:
                print(f"[X] Fatal for {symbol}: {message}")
                return False
            if status == Outcome.PACING:
                print(f"[!] Pacing violation. Cooling down {PACING_COOLDOWN_SECONDS}s.")
                time.sleep(PACING_COOLDOWN_SECONDS)
                continue
            if status == Outcome.RETRY:
                print(f"[-] Retryable: {message}")
                time.sleep(5)
                continue
            if status == Outcome.NO_DATA or not bars:
                consecutive_empty += 1
                print(f"[-] No data for this window "
                      f"({consecutive_empty}/{MAX_CONSECUTIVE_EMPTY} consecutive).")
                current_end -= step
                chunk_ok = True
                break

            consecutive_empty = 0
            if len(bars) >= MAX_BARS_PER_REQUEST:
                print(f"[!] {len(bars)} bars -- at the {MAX_BARS_PER_REQUEST} cap, "
                      f"data may be truncated. Reduce the chunk size.")

            pd.DataFrame(bars).to_csv(
                out_path, mode="a", header=not os.path.exists(out_path), index=False)
            rows_written += len(bars)
            earliest = parse_ib_datetime(bars[0]["Date"])
            print(f"[*] {len(bars):,} bars saved ({earliest:%Y-%m-%d %H:%M} -> "
                  f"{parse_ib_datetime(bars[-1]['Date']):%Y-%m-%d %H:%M}), "
                  f"{rows_written:,} this run")

            # Monotonicity guard: the cursor MUST move backward or the loop spins.
            if earliest >= current_end - timedelta(minutes=1):
                print("[-] Cursor did not advance; forcing a step back.")
                current_end -= step
            else:
                current_end = earliest
            chunk_ok = True
            break

        if not chunk_ok:
            print(f"[!] Chunk failed {MAX_RETRIES_PER_CHUNK}x; skipping backward.")
            current_end -= step
            consecutive_empty += 1

        if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
            print(f"[*] {MAX_CONSECUTIVE_EMPTY} empty windows in a row -- assuming "
                  f"start of available history for {symbol}.")
            break

    return True


def finalize(path: str, symbol: str) -> None:
    if not os.path.exists(path):
        return
    print(f"\n[*] Sorting and de-duplicating {path} ...")
    df = pd.read_csv(path)
    before = len(df)
    df.drop_duplicates(subset=["Date"], keep="last", inplace=True)
    df.sort_values(by="Date", inplace=True)  # fixed-width format sorts correctly
    df.to_csv(path, index=False)

    ts = df["Date"].map(parse_ib_datetime)
    sessions = ts.dt.normalize().nunique()
    print(f"[OK] {symbol}: {len(df):,} rows ({before - len(df):,} dupes removed), "
          f"{sessions:,} sessions, {ts.min():%Y-%m-%d} -> {ts.max():%Y-%m-%d}")

    # Surface corporate actions -- repo loaders expect raw files with known
    # splits applied explicitly, so an unflagged jump would corrupt a backtest.
    daily = df.assign(d=ts.dt.normalize()).groupby("d")["Close"].last()
    jumps = daily.pct_change().abs()
    for day, move in jumps[jumps > 0.35].items():
        print(f"     [!] {day:%Y-%m-%d}: {move * 100:.1f}% close-to-close jump "
              f"-- verify split vs. real move")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", nargs="+", default=["SOXS"])
    p.add_argument("--years", type=float, default=6)
    p.add_argument("--bar-size", default="1 min")
    p.add_argument("--what-to-show", default="TRADES")
    p.add_argument("--use-rth", type=int, default=1, choices=[0, 1])
    p.add_argument("--sec-type", default="STK")
    p.add_argument("--exchange", default="SMART")
    p.add_argument("--currency", default="USD")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7497, help="7496 live, 7497 paper")
    p.add_argument("--client-id", type=int, default=17)
    p.add_argument("--outdir", default=".")
    p.add_argument("--output", default=None, help="explicit path (single symbol)")
    args = p.parse_args()

    if args.output and len(args.symbols) > 1:
        p.error("--output only makes sense with a single symbol")

    app = HistoricalFetcher()
    app.connect(args.host, args.port, clientId=args.client_id)
    threading.Thread(target=app.run, daemon=True).start()

    print(f"Connecting to TWS/Gateway at {args.host}:{args.port} ...")
    if not app.connected_event.wait(timeout=20):
        print("[!] Connection timed out. Check that TWS/Gateway is running, that "
              "'Enable ActiveX and Socket Clients' is on, and that the port matches "
              "(7496 live / 7497 paper).")
        app.disconnect()
        return 1
    print(f"Connected. Server version {app.serverVersion()}")

    pacer = Pacer()
    req_seq = [1000]
    exit_code = 0
    try:
        for symbol in args.symbols:
            out_path = output_path(symbol, args)
            try:
                if not fetch_symbol(app, pacer, req_seq, symbol, args):
                    exit_code = 1
            finally:
                finalize(out_path, symbol)
    except KeyboardInterrupt:
        print("\n[*] Interrupted. Progress is checkpointed; rerun to resume.")
        exit_code = 130
    finally:
        app.disconnect()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
