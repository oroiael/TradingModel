"""Fetch 5 years of intraday FX bars from IBKR, in this repository's CSV format.

WHY THIS EXISTS
---------------
`band_lab` harvests intraday churn on SOXL: buy a 1% dip off the session rolling
high, sell +1%, stop -4%, gated on ATR5 >= 6%.  The question this lab opens is
whether the same mechanism survives on currencies.  It cannot be answered from
daily data, and it cannot be answered from MIDPOINT alone -- see §2 -- so this
script exists to get the right data before any strategy code is written.

`etf_scaling_test.py` already established the transfer protocol: scale the
parameters by k = (instrument median daily range) / 6.67%.  Measured on IBKR
daily MidPoint bars, 2026-05-17 -> 2026-08-12 (64 sessions):

    pair      median day range    k        k-scaled dip/target
    USDZAR          0.92%       0.137          0.137%
    USDMXN          0.55%       0.083          0.083%
    GBPJPY          0.46%       0.068          0.068%
    EURUSD          0.45%       0.067          0.067%
    USDJPY          0.34%       0.051          0.051%
    SOXL            6.67%       1.000          1.000%   <- band_lab reference

So FX spot is 7-20x quieter than SOXL and the transferred target lands at
**5-14 basis points**.  Everything unusual about this fetcher follows from that
one number.

1. FULL 24-HOUR DATA, NOT RTH
   `useRTH` defaults to FALSE here, the opposite of `band_lab/live/fetch_1min.py`.
   Spot FX has no regular trading session, so band_lab's V2 (session rolling
   high), V5 (11:00 start) and V9 (opening-30-minute filter) have no defined
   anchor until someone picks one.  Which anchor to pick is a research variable,
   and 24-hour data is a superset -- any session can be sliced out of it later,
   whereas an RTH-only capture cannot be un-done.  `fx_profile.py --session`
   scores the candidates (ny / fx / london / overlap).

2. BID AND ASK, NOT JUST MIDPOINT
   band_lab's most expensive lesson (STRATEGY_SPEC §0.2, PHASE2_PARITY S10/S11)
   was that roughly half its measured edge came from fills its bar size could
   not actually resolve.  A 5-14 bp target is far more fragile than a 100 bp one:
   on majors the IDEALPRO spread is a couple of percent of the target, but on
   USDZAR it can be a third of it.  Fetching MIDPOINT only makes that cost
   unmeasurable, so the default captures MIDPOINT, BID and ASK and
   `fx_profile.py` reports the real spread per session bucket.
   The price is pacing: three series instead of one.  Use `--what MIDPOINT`
   for a first look, then add BID,ASK before believing any P&L.

WHAT IBKR WILL AND WILL NOT GIVE YOU
------------------------------------
Verified from `TWS API/TWS Documentation - Copy Paste from Online.pdf` p.62
("Unavailable Historical Data" / "Pacing Violations") and from the installed
`ib_async` source.  IBKR's web documentation is not reachable from the
environment this was written in, so anything not from those two sources is
marked ASSUMPTION.

  * Spot FX (secType CASH, IDEALPRO) -- the only FX instrument here with real
    5-year intraday depth.  `--probe` measures it instead of assuming it.
  * FX futures (6E, 6J, 6B ...) -- "Expired futures data older than two years
    counting from the future's expiration date" is unavailable, so a 5-year
    stitched front-month series is impossible from IBKR.  `--futures` requests
    CONTFUT instead; ASSUMPTION that CONTFUT reaches 5 years at 1-minute, which
    is exactly what `--probe` is for.
  * FX futures *options* -- "Expired options, FOPs, warrants and structured
    products" have no historical data at IBKR, at any age.  There is no way to
    backtest currency futures options from this broker; that needs a vendor
    (the repo's ThetaData credentials, or CME DataMine).  This is why the
    script has no FOP mode.
  * Bars of 30 seconds or less are unavailable beyond six months.  Relevant
    because a 1-minute EURUSD bar's own range is a meaningful fraction of a
    6.7 bp target -- see README §"Fill resolution".
  * FX bars carry no meaningful volume; IBKR has no consolidated trade tape for
    spot.  The Volume column is written through as returned (typically -1) and
    `fx_profile.py` reports it rather than pretending otherwise.

whatToShow: IBKR's own sample (`TWS API/samples/Python/Testbed/Program.py`
lines 1065-1071) uses MIDPOINT for every FX historical request and TRADES only
for stocks.  MIDPOINT/BID/ASK are used here for that reason.  BID_ASK is
accepted but discouraged: it is counted twice against the pacing limit (p.62)
and returns a different bar shape (time-weighted average bid / max ask ...),
which `bars_to_frame` would silently mislabel as OHLC.

Timestamps use `formatDate=2`.  Verified in `ib_async/util.py:parseIBDatetime`:
with formatDate=2 IBKR returns an epoch integer, which becomes a tz-aware UTC
datetime, and this script converts it to America/New_York explicitly.  The
older scripts in this repo use formatDate=1, which returns *naive local time in
the TWS login timezone* -- correct only as long as TWS is set to New York.

USAGE
-----
    # 0. how deep does IBKR actually go, and how long will this take?
    python3 fx_lab/fetch_fx_intraday.py --probe
    python3 fx_lab/fetch_fx_intraday.py --dry-run --years 5

    # 1. one pair, MIDPOINT only, to shake out the plumbing (~45 min)
    python3 fx_lab/fetch_fx_intraday.py --symbols EURUSD --what MIDPOINT

    # 2. the recommended universe, all three series -- run this overnight
    python3 fx_lab/fetch_fx_intraday.py --preset core --years 5

    # 3. check what landed, and get the band_lab-comparable profile
    python3 fx_lab/fx_profile.py --check
    python3 fx_lab/fx_profile.py

Resumable: interrupt with Ctrl-C and rerun.  The file on disk is always sorted,
de-duplicated and complete up to the last written chunk.
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
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
ZONE = " America/New_York"

# Pacing, verified from the docs PDF p.62: no more than 60 historical requests
# in any ten-minute window; no identical request inside 15 seconds; no 6+
# requests for the same contract/exchange/tick type inside 2 seconds.  A single
# sequential loop at >=10s satisfies all three.  BID_ASK counts twice.
PACING_SECONDS = 10.5
PACING_SECONDS_BID_ASK = 21.0

# Measured medians (see module docstring) -> the k factor etf_scaling_test.py
# wants.  Used only to print guidance; nothing here trades on it.
MEDIAN_RANGE_PCT = {"USDZAR": 0.92, "USDMXN": 0.55, "GBPJPY": 0.46,
                    "EURUSD": 0.45, "USDJPY": 0.34}
SOXL_MEDIAN_RANGE = 6.67

UNIVERSE = {
    # The recommended first pull: the two highest-range liquid pairs (best k),
    # the highest-range major cross, and the two deepest majors as the
    # liquidity/cost control.  Rationale in README §"Which instruments".
    "core":    ["USDZAR", "USDMXN", "GBPJPY", "EURUSD", "USDJPY"],
    "majors":  ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD",
                "NZDUSD"],
    "crosses": ["GBPJPY", "EURJPY", "AUDJPY", "CADJPY", "EURGBP", "GBPNZD",
                "EURAUD"],
    "em":      ["USDMXN", "USDZAR", "USDNOK", "USDSEK", "USDPLN", "USDHUF"],
}

# CME FX futures roots, for --futures.  CONTFUT only; see the docstring on why
# a stitched front-month series cannot reach 5 years from IBKR.
FUTURES_EXCHANGE = "CME"
FUTURES_ROOTS = {"6E": "EUR", "6J": "JPY", "6B": "GBP", "6A": "AUD",
                 "6C": "CAD", "6S": "CHF", "6N": "NZD", "6M": "MXN"}


# --------------------------------------------------------------- formatting
def format_bar_date(value) -> str:
    """Render a bar timestamp in the repository's CSV convention (NY wall time).

    Accepts the tz-aware UTC datetime that formatDate=2 produces, a naive
    datetime (assumed already NY), or the string form the older scripts emit.
    """
    if isinstance(value, str):
        txt = value.replace(ZONE, "").strip()
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
    return f"{dt:%Y%m%d %H:%M:%S}{ZONE}"


def bars_to_frame(bars) -> pd.DataFrame:
    """Normalize an ib_async BarDataList to the repository's exact CSV shape."""
    return pd.DataFrame(
        [{"Date": format_bar_date(b.date), "Open": float(b.open),
          "High": float(b.high), "Low": float(b.low), "Close": float(b.close),
          "Volume": float(b.volume)} for b in bars],
        columns=COLUMNS)


def merge_and_write(path: str, new: pd.DataFrame) -> int:
    """Append, de-duplicate on timestamp, sort, write atomically.

    Interrupt-safe: `os.replace` means the file on disk is never half-written,
    so a killed run loses at most the chunk in flight.
    """
    frames = [new]
    if os.path.exists(path) and os.path.getsize(path) > 100:
        frames.insert(0, pd.read_csv(path))
    out = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset="Date", keep="last")
    out = (out.assign(_k=out["Date"].str.slice(0, 17))
              .sort_values("_k").drop(columns="_k"))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    out.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return len(out)


def existing_span(path: str):
    """(earliest, latest) session dates already in the file, or (None, None)."""
    if not os.path.exists(path) or os.path.getsize(path) < 100:
        return None, None
    df = pd.read_csv(path, usecols=["Date"])
    if df.empty:
        return None, None
    k = df["Date"].str.slice(0, 8)
    return (datetime.strptime(k.min(), "%Y%m%d").date(),
            datetime.strptime(k.max(), "%Y%m%d").date())


def bar_slug(bar_size: str) -> str:
    """'1 min' -> '1min', '5 mins' -> '5min', '30 secs' -> '30sec'."""
    n, unit = bar_size.split()
    return f"{n}{unit.rstrip('s')}"


def out_path(symbol: str, bar_size: str, what: str, out_dir: str) -> str:
    """MIDPOINT gets the bare repo-convention name; other series get a suffix."""
    tail = "" if what.upper() == "MIDPOINT" else f"_{what.upper()}"
    return os.path.join(out_dir, f"{symbol}_{bar_slug(bar_size)}{tail}.csv")


# -------------------------------------------------------------------- plan
def parse_duration(duration: str) -> timedelta:
    """'1 D' -> 1 day. Accepts S/D/W/M/Y as IBKR spells them."""
    n, unit = duration.split()
    n = int(n)
    per = {"S": timedelta(seconds=1), "D": timedelta(days=1),
           "W": timedelta(weeks=1), "M": timedelta(days=30),
           "Y": timedelta(days=365)}
    if unit.upper() not in per:
        raise ValueError(f"bad duration unit in {duration!r}")
    return n * per[unit.upper()]


def pacing_floor(what: str) -> float:
    return PACING_SECONDS_BID_ASK if what.upper() == "BID_ASK" else PACING_SECONDS


# Spot FX closes Friday 17:00 ET and reopens Sunday 17:00 ET. ASSUMPTION on the
# exact minute (IDEALPRO's published hours are not reachable from here), but the
# 17:00 boundary is corroborated by the daily bars IBKR serves for CASH: they
# are stamped 21:15 UTC = 17:15 ET. Only used to skip requests, never to drop
# data — see window_is_closed.
FX_CLOSE_WEEKDAY = 4          # Friday
FX_CLOSE_HOUR = 17
FX_CLOSED_HOURS = 48


def ny_midnight(d) -> datetime:
    """Midnight New York on `d`, timezone-aware.

    Every cursor in this script is an aware NY datetime so that request
    boundaries survive both DST and a TWS set to another timezone.
    """
    return datetime(d.year, d.month, d.day, tzinfo=NY)


def _closure_containing(t: datetime):
    """(close, reopen) of the weekend closure containing `t`, or None."""
    friday = t - timedelta(days=(t.weekday() - FX_CLOSE_WEEKDAY) % 7)
    close = friday.replace(hour=FX_CLOSE_HOUR, minute=0, second=0, microsecond=0)
    if t < close:                       # `t` is before this week's close
        close -= timedelta(days=7)
    reopen = close + timedelta(hours=FX_CLOSED_HOURS)
    return (close, reopen) if close <= t < reopen else None


def window_is_closed(win_start: datetime, win_end: datetime) -> bool:
    """True only when the ENTIRE window lies inside one weekend closure.

    Conservative by construction: any overlap with an open period returns
    False, so this can never skip a request that would have returned data. At
    a 10.5s pacing floor and daily chunks it saves ~1 request in 7 — about 45
    minutes per series over five years.
    """
    closure = _closure_containing(win_start)
    return closure is not None and win_end <= closure[1]


def plan(symbols, whats, start, end, duration, pause) -> dict:
    """Request count and wall-clock estimate, so a 50-hour job is a decision.

    Walks the same windows and applies the same weekend skip as the fetch loop,
    so the estimate does not flatter the run.
    """
    step = parse_duration(duration)
    cursor = ny_midnight(end)
    start_dt = ny_midnight(start)
    per_series = 0
    while cursor > start_dt:
        if not window_is_closed(cursor - step, cursor):
            per_series += 1
        cursor -= step
    per_series = max(1, per_series)
    total = per_series * len(symbols) * len(whats)
    seconds = sum(per_series * max(pause, pacing_floor(w))
                  for w in whats) * len(symbols)
    return {"per_series": per_series, "total_requests": total,
            "hours": seconds / 3600.0}


def print_plan(symbols, whats, start, end, duration, pause, bar_size):
    p = plan(symbols, whats, start, end, duration, pause)
    print(f"plan: {len(symbols)} symbol(s) x {len(whats)} series x "
          f"~{p['per_series']} requests = {p['total_requests']:,} requests")
    print(f"      {bar_size} bars, {start} -> {end}, chunked by '{duration}'")
    print(f"      pacing floor {max(pause, min(pacing_floor(w) for w in whats)):.1f}s"
          f"/request  ->  ~{p['hours']:.1f} hours wall clock")
    if p["hours"] > 8:
        print("      [!] that is an overnight job. Try a larger --duration (the "
              "run verifies it against '1 D' first), or fewer --symbols, or "
              "--what MIDPOINT for the first pass.")
    return p


# ---------------------------------------------------------------- contracts
def make_contract(symbol: str, futures: bool):
    """Forex('EURUSD') -> CASH/IDEALPRO; ContFuture -> CONTFUT/CME.

    Verified in ib_async/contract.py: Forex splits a 6-character pair into
    symbol=base, currency=quote, secType CASH, exchange IDEALPRO -- which
    matches IBKR's own ContractSamples.py cash contract (EUR/GBP, IDEALPRO).
    """
    from ib_async import ContFuture, Forex

    if futures:
        root = symbol.upper()
        return ContFuture(symbol=root, exchange=FUTURES_EXCHANGE)
    if len(symbol) != 6:
        raise ValueError(f"{symbol!r} is not a 6-character pair like EURUSD")
    return Forex(symbol.upper())


def qualify(ib, symbol: str, futures: bool):
    contract = make_contract(symbol, futures)
    found = ib.qualifyContracts(contract)
    if not found:
        print(f"[!] could not qualify {symbol} "
              f"({'CONTFUT/' + FUTURES_EXCHANGE if futures else 'CASH/IDEALPRO'})")
        return None
    c = found[0]
    print(f"  qualified {symbol}: conId={c.conId} {c.secType}/{c.exchange}")
    return c


# ------------------------------------------------------------------- probe
def probe(symbols, whats, host, port, client_id, futures, use_rth) -> int:
    """Ask IBKR how far back it actually goes, before committing hours to it.

    reqHeadTimeStamp is the documented way to do this (docs PDF p.62-63:
    "you can use EClient.reqHeadTimestamp to find the first available point of
    data for a given whatToShow value").  Note the docs also warn it counts as
    an ongoing historical request and follows the 30-second-bar limitations
    regardless of the bar size asked for.
    """
    from ib_async import IB

    ib = IB()
    print(f"connecting to {host}:{port} (clientId={client_id}) ...")
    ib.connect(host, port, clientId=client_id, timeout=20)
    rows = []
    try:
        for symbol in symbols:
            contract = qualify(ib, symbol, futures)
            if contract is None:
                rows.append({"symbol": symbol, "what": "-",
                             "earliest": "NOT QUALIFIED", "years": None})
                continue
            for what in whats:
                try:
                    head = ib.reqHeadTimeStamp(contract, what, use_rth,
                                               formatDate=2)
                except Exception as exc:                        # noqa: BLE001
                    rows.append({"symbol": symbol, "what": what,
                                 "earliest": f"error: {exc}", "years": None})
                    time.sleep(pacing_floor(what))
                    continue
                years = None
                if isinstance(head, datetime):
                    years = round((datetime.now(head.tzinfo) - head).days / 365.25, 1)
                    head = head.astimezone(NY).strftime("%Y-%m-%d %H:%M")
                rows.append({"symbol": symbol, "what": what,
                             "earliest": str(head), "years": years})
                print(f"    {symbol:8s} {what:9s} earliest {head}"
                      + (f"  ({years} years)" if years else ""))
                time.sleep(pacing_floor(what))
    finally:
        ib.disconnect()

    df = pd.DataFrame(rows)
    print("\n" + "=" * 72)
    print("HEAD TIMESTAMPS — how deep IBKR's history actually is")
    print("=" * 72)
    print(df.to_string(index=False))
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    dest = os.path.join(HERE, "out", "head_timestamps.csv")
    df.to_csv(dest, index=False)
    print(f"\n-> {dest}")
    short = df[df["years"].notna() & (df["years"] < 5)]
    if len(short):
        print("\n[!] these series do not reach 5 years; fetch what exists and "
              "source the rest from a vendor in the same CSV format:")
        print(short.to_string(index=False))
    return 0


# ------------------------------------------------------------------- fetch
def request_bars(ib, contract, end_dt, duration, bar_size, what, use_rth):
    """One historical request.

    `end_dt` must be a timezone-AWARE datetime (or None for "now").  Verified in
    `ib_async/util.py:formatIBDatetime`: an aware datetime is converted to UTC
    and sent as "YYYYMMDD HH:MM:SS UTC", whereas a plain string is passed
    through untouched and IBKR then reads it in the *TWS login timezone*.  The
    older fetchers in this repo send strings, so their request boundaries are
    silently wrong on any TWS not set to New York.  Passing the object keeps
    both ends of the request unambiguous.
    """
    assert end_dt is None or end_dt.tzinfo is not None, \
        "endDateTime must be timezone-aware — see docstring"
    return ib.reqHistoricalData(
        contract, endDateTime=end_dt or "", durationStr=duration,
        barSizeSetting=bar_size, whatToShow=what, useRTH=use_rth,
        formatDate=2, keepUpToDate=False)


def check_duration(ib, contract, bar_size, what, use_rth, duration,
                   pause) -> bool:
    """Is a big --duration lossless? Compare its overlap against a '1 D' pull.

    band_lab/live/fetch_1min.py says of larger durations: "Larger durations may
    work and are 5-7x faster; try --duration '1 W' and check the output before
    trusting it."  This automates that check rather than leaving it to trust.
    Returns True if the last common session matches bar-for-bar.
    """
    if duration == "1 D":
        return True
    print(f"  verifying --duration '{duration}' against '1 D' ...")
    big = request_bars(ib, contract, None, duration, bar_size, what, use_rth)
    time.sleep(max(pause, pacing_floor(what)))
    small = request_bars(ib, contract, None, "1 D", bar_size, what, use_rth)
    time.sleep(max(pause, pacing_floor(what)))
    if not big or not small:
        print("  [!] verification inconclusive (a request came back empty); "
              "falling back to '1 D'")
        return False
    a, b = bars_to_frame(big), bars_to_frame(small)
    day = b["Date"].str.slice(0, 8).max()
    a = a[a["Date"].str.slice(0, 8) == day].reset_index(drop=True)
    b = b[b["Date"].str.slice(0, 8) == day].reset_index(drop=True)
    same = len(a) == len(b) and a.equals(b)
    if same:
        print(f"  ok: '{duration}' and '1 D' agree on {day} "
              f"({len(b)} bars) — using '{duration}'")
    else:
        print(f"  [!] '{duration}' disagrees with '1 D' on {day} "
              f"({len(a)} vs {len(b)} bars) — falling back to '1 D'. "
              f"Re-run with --no-duration-check to override.")
    return same


def fetch_series(ib, contract, symbol, what, path, start, end, bar_size,
                 duration, pause, use_rth) -> int:
    """Walk backwards from `end` to `start`, writing as we go. Resumable."""
    have_lo, have_hi = existing_span(path)
    if have_lo:
        print(f"  resuming {os.path.basename(path)}: have {have_lo} -> {have_hi}")
        # Backfill only, deliberately: the cursor walks backwards from the
        # oldest bar held. Newer bars are NOT topped up, because doing both in
        # one pass makes an interrupted run's coverage ambiguous. To extend
        # forward, fetch the recent window into a separate --out-dir and merge,
        # or delete the file and re-pull.
        if (end - have_hi).days > 3:
            print(f"  [note] file ends {have_hi}, {(end - have_hi).days} days "
                  f"short of {end}. This pass backfills older data only.")
        cursor = ny_midnight(have_lo)
    else:
        cursor = ny_midnight(end) + timedelta(days=1)
    floor = max(pause, pacing_floor(what))
    step = parse_duration(duration)
    start_dt = ny_midnight(start)
    empty, requests, rows = 0, 0, 0

    while cursor > start_dt:
        if window_is_closed(cursor - step, cursor):
            cursor -= step
            continue        # no request: the whole window is a market closure
        try:
            bars = request_bars(ib, contract, cursor, duration, bar_size,
                                what, use_rth)
        except Exception as exc:                                # noqa: BLE001
            print(f"  [!] request failed at {cursor:%Y-%m-%d %H:%M}: {exc}")
            time.sleep(floor * 2)
            requests += 1
            # Do not retry the same endDateTime forever: an identical request
            # inside 15s is itself a pacing violation (docs p.62). Step back.
            cursor -= step
            continue
        requests += 1

        if not bars:
            empty += 1
            print(f"  {cursor:%Y-%m-%d}: no data (streak {empty})")
            # Weekends and holidays return nothing; so does the end of
            # available history, but repeatedly. Six in a row = stop.
            if empty >= 6:
                print("  [*] server stopped returning data — end of history")
                break
            cursor -= step
            time.sleep(floor)
            continue

        empty = 0
        frame = bars_to_frame(bars)
        rows = merge_and_write(path, frame)
        oldest_key = frame["Date"].str.slice(0, 17).min()
        oldest = datetime.strptime(oldest_key, "%Y%m%d %H:%M:%S").replace(tzinfo=NY)
        print(f"  {oldest:%Y-%m-%d %H:%M}: +{len(frame):,} bars  "
              f"(file {rows:,} rows)")
        # Step to just before the oldest bar received; if the server gave us
        # nothing older than where we already were, force progress.
        nxt = oldest - timedelta(seconds=1)
        cursor = nxt if nxt < cursor else cursor - step
        time.sleep(floor)

    lo, hi = existing_span(path)
    if os.path.exists(path):            # a run that fetched nothing new still
        rows = sum(1 for _ in open(path)) - 1        # has whatever was there
    print(f"  done {symbol}/{what}: {requests} requests, {rows:,} rows")
    if lo:
        print(f"  coverage {lo} -> {hi}  (target start {start})")
        if lo > start + timedelta(days=14):
            print(f"  [!] did not reach {start}. Run --probe to see the real "
                  f"head timestamp; older years need a vendor.")
    return 0


def fetch(symbols, whats, start, end, bar_size, duration, pause, host, port,
          client_id, futures, use_rth, out_dir, duration_check) -> int:
    from ib_async import IB

    ib = IB()
    print(f"connecting to {host}:{port} (clientId={client_id}) ...")
    ib.connect(host, port, clientId=client_id, timeout=20)
    try:
        for symbol in symbols:
            print(f"\n{'=' * 72}\n{symbol}\n{'=' * 72}")
            contract = qualify(ib, symbol, futures)
            if contract is None:
                continue
            eff_duration = duration
            if duration_check:
                if not check_duration(ib, contract, bar_size, whats[0],
                                      use_rth, duration, pause):
                    eff_duration = "1 D"
            for what in whats:
                path = out_path(symbol, bar_size, what, out_dir)
                fetch_series(ib, contract, symbol, what, path, start, end,
                             bar_size, eff_duration, pause, use_rth)
        return 0
    finally:
        ib.disconnect()


# -------------------------------------------------------------------- main
def resolve_symbols(args) -> list[str]:
    if args.symbols:
        return [s.upper() for s in args.symbols]
    if args.futures:
        return list(FUTURES_ROOTS)
    return UNIVERSE[args.preset]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Fetch intraday FX bars from IBKR in the repo's CSV format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run --probe first: it measures how deep IBKR's history really "
               "is per symbol and series, which is the one thing that decides "
               "whether a 5-year request is achievable at all.")
    ap.add_argument("--symbols", nargs="*", default=None,
                    help="pairs like EURUSD USDJPY (or futures roots with "
                         "--futures); overrides --preset")
    ap.add_argument("--preset", default="core", choices=sorted(UNIVERSE),
                    help="named universe (default core)")
    ap.add_argument("--futures", action="store_true",
                    help="request CME CONTFUT instead of IDEALPRO spot")
    ap.add_argument("--what", default="MIDPOINT,BID,ASK",
                    help="comma list: MIDPOINT,BID,ASK (default all three — "
                         "BID/ASK are what make the cost measurable)")
    ap.add_argument("--years", type=float, default=5.0,
                    help="history depth in years (default 5)")
    ap.add_argument("--start", default=None,
                    help="explicit earliest session YYYY-MM-DD; overrides --years")
    ap.add_argument("--end", default=None, help="latest session YYYY-MM-DD")
    ap.add_argument("--bar-size", default="1 min",
                    help="'1 min' (default), '5 mins', '30 secs' (<=30 secs is "
                         "capped at ~6 months of history by IBKR)")
    ap.add_argument("--duration", default="1 D",
                    help="per-request span; '1 W' is ~7x faster and is verified "
                         "against '1 D' before use (default '1 D')")
    ap.add_argument("--rth", action="store_true",
                    help="restrict to regular trading hours. OFF by default — "
                         "24-hour data is a superset and the FX session anchor "
                         "is still an open research question")
    ap.add_argument("--out-dir", default=DATA)
    ap.add_argument("--pause", type=float, default=0.0,
                    help="seconds between requests; raised to the verified "
                         "pacing floor (10.5s, 21s for BID_ASK) regardless")
    ap.add_argument("--probe", action="store_true",
                    help="report head timestamps and exit — no bulk fetch")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the request plan and exit — no connection")
    ap.add_argument("--no-duration-check", dest="duration_check",
                    action="store_false",
                    help="skip verifying a large --duration against '1 D'")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497,
                    help="7497 TWS paper, 7496 TWS live, 4002 gateway paper")
    ap.add_argument("--client-id", type=int, default=95)
    args = ap.parse_args(argv)

    symbols = resolve_symbols(args)
    whats = [w.strip().upper() for w in args.what.split(",") if w.strip()]
    bad = [w for w in whats if w not in
           {"MIDPOINT", "BID", "ASK", "BID_ASK", "TRADES"}]
    if bad:
        print(f"[!] unsupported whatToShow: {bad}")
        return 2
    if "BID_ASK" in whats:
        print("[!] BID_ASK returns time-weighted-average-bid / max-ask in the "
              "OHLC slots, which this script would mislabel as prices, and it "
              "costs double against pacing. Prefer --what MIDPOINT,BID,ASK.")
    if not args.futures and "TRADES" in whats:
        print("[!] TRADES is not the FX convention — IBKR's own sample uses "
              "MIDPOINT for CASH contracts. Continuing, but expect empty bars.")

    end = (datetime.strptime(args.end, "%Y-%m-%d").date() if args.end
           else datetime.now().date())
    start = (datetime.strptime(args.start, "%Y-%m-%d").date() if args.start
             else (datetime.now() - timedelta(days=args.years * 365.25)).date())
    if start >= end:
        print(f"[!] start {start} is not before end {end}")
        return 2

    print(f"symbols: {' '.join(symbols)}")
    print(f"series : {' '.join(whats)}   useRTH={args.rth}")
    print(f"output : {args.out_dir}")
    for s in symbols:
        if s in MEDIAN_RANGE_PCT:
            k = MEDIAN_RANGE_PCT[s] / SOXL_MEDIAN_RANGE
            print(f"         {s}: median range {MEDIAN_RANGE_PCT[s]:.2f}% "
                  f"-> k={k:.3f} -> band_lab dip/target scales to {k:.3f}%")
    print()
    print_plan(symbols, whats, start, end, args.duration, args.pause,
               args.bar_size)
    if args.dry_run:
        print("\n--dry-run: nothing fetched")
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    if args.probe:
        return probe(symbols, whats, args.host, args.port, args.client_id,
                     args.futures, args.rth)
    return fetch(symbols, whats, start, end, args.bar_size, args.duration,
                 args.pause, args.host, args.port, args.client_id,
                 args.futures, args.rth, args.out_dir, args.duration_check)


if __name__ == "__main__":
    raise SystemExit(main())
