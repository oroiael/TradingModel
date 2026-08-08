"""Offline self-test for fas_1min_fetch.py.

The network paths (Theta Terminal, IBKR/TWS) cannot run without a broker or a
local terminal, so they are not exercised here.  Everything that does NOT need
a network is tested against the real SOXL_1min.csv conventions, because those
are the parts most likely to silently corrupt a six-hour capture:

  * the Theta response parser -- maps columns by NAME from the payload header
  * the CSV formatter -- byte-identical convention to SOXL_1min.csv
  * merge/resume -- dedupe, sort, and atomic replace across interrupted runs

Run:  python3 fas_1min_selftest.py
"""

from __future__ import annotations

import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fas_1min_fetch import (bar_datetime, detect_splits, merge_and_write,  # noqa: E402
                            theta_frame, to_rows)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


print("=" * 72)
print("SELF-TEST  fas_1min_fetch.py")
print("=" * 72)

# ------------------------------------------------------------------ parser
print("\n1. Theta response parser")
# Field ORDER deliberately shuffled vs the natural one: the parser must key on
# the header names, not on position.
payload = [{
    "header": {"format": ["volume", "ms_of_day", "close", "high", "date",
                          "low", "open", "count"]},
    # 09:30:00 = 34_200_000 ms; 09:31:00 = 34_260_000 ms
    "response": [
        [170640, 34_200_000, 17.92, 17.96, 20191231, 17.90, 17.94, 812],
        [33000, 34_260_000, 17.92, 17.94, 20191231, 17.91, 17.92, 210],
        [0, 34_320_000, 0.0, 0.0, 20191231, 0.0, 0.0, 0],        # dead padding row
        [5000, 28_800_000, 17.80, 17.85, 20191231, 17.75, 17.80, 12],  # 08:00 pre-market
        [9100, 57_540_000, 18.10, 18.12, 20191231, 18.05, 18.06, 44],  # 15:59
    ]}]
f = theta_frame(payload)
check("parses shuffled header order", len(f) == 3, f"got {len(f)} rows")
check("drops pre-market 08:00 bar", "08:00" not in f["ts"].dt.strftime("%H:%M").values)
check("drops all-zero padding bar", (f[["Open", "High", "Low", "Close"]].sum(axis=1) > 0).all())
check("keeps the 15:59 bar", "15:59" in f["ts"].dt.strftime("%H:%M").values)
check("first bar is 09:30", f["ts"].iloc[0].strftime("%H:%M") == "09:30")
check("ms_of_day -> clock time correct",
      f["ts"].iloc[0] == pd.Timestamp("2019-12-31 09:30:00"))
check("OHLCV mapped by name, not position",
      bool(abs(f["Open"].iloc[0] - 17.94) < 1e-9 and abs(f["Close"].iloc[0] - 17.92) < 1e-9
           and abs(f["Volume"].iloc[0] - 170640) < 1e-9),
      f"open={f['Open'].iloc[0]} close={f['Close'].iloc[0]} vol={f['Volume'].iloc[0]}")

try:
    theta_frame([{"response": [[1, 2]]}])
    check("missing header raises", False)
except RuntimeError:
    check("missing header raises rather than guessing", True)

# ------------------------------------------------------------------ format
print("\n2. CSV format matches SOXL_1min.csv byte convention")
rows = to_rows(f)
check("column order", list(rows.columns) ==
      ["Date", "Open", "High", "Low", "Close", "Volume"], str(list(rows.columns)))
line = ",".join(str(x) for x in rows.iloc[0].tolist())
expect = "20191231 09:30:00 America/New_York,17.94,17.96,17.9,17.92,170640.0"
check("first line matches the reference exactly", line == expect,
      f"\n         got      {line}\n         expected {expect}")
check("zone suffix on every row",
      rows["Date"].str.endswith(" America/New_York").all())
check("volume is float dtype (matches reference)",
      str(rows["Volume"].dtype) == "float64")

# ------------------------------------------------------------------ merge
print("\n3. Merge / resume / dedupe")
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "T_1min.csv")

    n1 = merge_and_write(p, rows)
    check("writes a new file", n1 == 3 and os.path.exists(p), f"{n1} rows")

    # same chunk again -- a resumed run re-requesting an overlapping window
    n2 = merge_and_write(p, rows)
    check("re-writing the same chunk does not duplicate", n2 == 3, f"{n2} rows")

    # an earlier chunk arriving after a later one: must sort, not append blindly
    older = to_rows(pd.DataFrame({
        "ts": [pd.Timestamp("2019-12-30 09:30:00")],
        "Open": [17.0], "High": [17.1], "Low": [16.9], "Close": [17.05],
        "Volume": [1234.0]}))
    n3 = merge_and_write(p, older)
    got = pd.read_csv(p)
    check("out-of-order chunk merges", n3 == 4, f"{n3} rows")
    check("file stays chronologically sorted",
          got["Date"].str.slice(0, 17).is_monotonic_increasing)
    check("earliest row is the late-arriving older bar",
          got["Date"].iloc[0].startswith("20191230"))

    # a corrected bar for a timestamp already present must win (keep="last")
    fixed = to_rows(pd.DataFrame({
        "ts": [pd.Timestamp("2019-12-31 09:30:00")],
        "Open": [99.0], "High": [99.0], "Low": [99.0], "Close": [99.0],
        "Volume": [1.0]}))
    merge_and_write(p, fixed)
    got = pd.read_csv(p)
    row = got[got["Date"].str.startswith("20191231 09:30:00")]
    check("re-fetched bar overwrites the stale one",
          len(row) == 1 and float(row["Close"].iloc[0]) == 99.0)

    check("no .tmp left behind (atomic replace)",
          not os.path.exists(p + ".tmp"))

# ------------------------------------------------------------------ ib dates
print("\n4. IBKR bar-timestamp normalization")
from datetime import datetime as _dt, date as _d, timezone as _tz, timedelta as _td
from zoneinfo import ZoneInfo as _Z
NY = _Z("America/New_York")

# The exact shape that crashed the first live run: ib_async returns a tz-AWARE
# datetime for intraday bars, which then could not be compared to a naive cursor.
aware = _dt(2026, 8, 7, 9, 30, tzinfo=NY)
got = bar_datetime(aware)
check("tz-aware datetime -> naive", got.tzinfo is None, str(got))
check("tz-aware wall clock preserved", got == _dt(2026, 8, 7, 9, 30), str(got))

# A UTC-stamped bar must be converted to NY, not merely stripped.
utc = _dt(2026, 8, 7, 13, 30, tzinfo=_tz.utc)          # 09:30 EDT
got = bar_datetime(utc)
check("UTC converted to New York (not just stripped)",
      got == _dt(2026, 8, 7, 9, 30), str(got))

check("naive datetime passes through",
      bar_datetime(_dt(2026, 8, 7, 9, 30)) == _dt(2026, 8, 7, 9, 30))
check("date -> midnight", bar_datetime(_d(2026, 8, 7)) == _dt(2026, 8, 7, 0, 0))
check("string with zone suffix",
      bar_datetime("20260807 09:30:00 America/New_York") == _dt(2026, 8, 7, 9, 30))
check("string with double space",
      bar_datetime("20260807  09:30:00") == _dt(2026, 8, 7, 9, 30))
check("string date only", bar_datetime("20260807") == _dt(2026, 8, 7, 0, 0))
check("ISO string", bar_datetime("2026-08-07 09:30:00") == _dt(2026, 8, 7, 9, 30))
try:
    bar_datetime(12345)
    check("unknown type raises", False)
except TypeError:
    check("unknown type raises TypeError rather than corrupting the cursor", True)

# the arithmetic that actually blew up
cursor = _dt.now()
oldest = pd.Series([bar_datetime(aware)]).min()
nxt = oldest.to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)
try:
    _ = nxt if nxt < cursor else cursor - _td(days=1)
    check("cursor comparison no longer raises", True)
except TypeError as e:
    check("cursor comparison no longer raises", False, str(e))

# ------------------------------------------------------------------ splits
print("\n5. Split detection and snapping")
idx = pd.to_datetime(["2021-02-26", "2021-03-01", "2021-03-02", "2021-03-03"])
o = pd.Series([580.0, 600.0, 42.99, 35.0], index=idx)
c = pd.Series([579.77, 636.49, 38.55, 34.98], index=idx)
sp = detect_splits(o, c)
check("detects the one split", len(sp) == 1, f"{len(sp)} found")
if sp:
    when, factor, observed = sp[0]
    check("snaps to a clean 1-for-15", abs(factor - 1/15) < 1e-9,
          f"factor={factor:.6f} from observed {observed:.4f}")
    check("dates the split correctly", str(when.date()) == "2021-03-02", str(when))
check("ordinary moves are not flagged",
      len(detect_splits(pd.Series([100.0, 101.0], index=idx[:2]),
                        pd.Series([100.0, 99.0], index=idx[:2]))) == 0)

print("\n" + "=" * 72)
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f_ in FAIL:
        print(f"  FAILED: {f_}")
print("\nNot covered here (needs a live source): the Theta HTTP endpoint path and\n"
      "pagination, and the IBKR/TWS connection. Use --probe for the first and a\n"
      "short --start window for the second before committing to a full run.")
raise SystemExit(1 if FAIL else 0)
