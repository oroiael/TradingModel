"""Offline self-test for fas_1min_fetch.py.

The network paths (Theta Terminal, IBKR/TWS) cannot run without a broker or a
local terminal, so they are not exercised here.  Everything that does NOT need
a network is tested against the real SOXL_1min.csv conventions, because those
are the parts most likely to silently corrupt a six-hour capture:

  * the Theta response parser -- maps columns by NAME from the payload header
  * the CSV formatter -- byte-identical convention to SOXL_1min.csv
  * merge/resume -- dedupe, sort, and atomic replace across interrupted runs
  * the IBKR contract lookup and bar-timestamp conversion -- the two things
    that decide whether a capture is the right instrument on the right clock

Run:  python3 fas_1min_selftest.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ibkr_env  # noqa: E402
from fas_1min_fetch import (  # noqa: E402
    bar_timestamp, merge_and_write, primary_exchange, theta_frame, to_rows)

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

# --------------------------------------------------------------- IBKR bars
# The connection cannot be tested without TWS, but the two things that decide
# whether a six-hour capture is usable can be: which contract gets qualified,
# and how a bar's timestamp is read.
print("\n4. IBKR contract and bar timestamps")
check("TQQQ qualifies on NASDAQ, not ARCA", primary_exchange("TQQQ") == "NASDAQ")
check("MUU qualifies on NASDAQ", primary_exchange("MUU") == "NASDAQ")
check("UVXY qualifies on BATS", primary_exchange("UVXY") == "BATS")
check("the ARCA names are unchanged",
      all(primary_exchange(s) == "ARCA" for s in ("FAS", "SPXL", "BULZ", "TMF")))
check("lookup is case-insensitive", primary_exchange("tqqq") == "NASDAQ")
check("an unlisted symbol falls back to ARCA", primary_exchange("ZZZZ") == "ARCA")

# ib_async's parseIBDatetime returns any of these; band_lab/live/broker.py's
# bar_time_et documents them from that package's source.
naive = datetime(2026, 6, 2, 9, 30)
check("naive datetime is exchange time already",
      bar_timestamp(naive) == pd.Timestamp("2026-06-02 09:30:00"))
check("zone-aware ET bar keeps its wall clock",
      bar_timestamp(naive.replace(tzinfo=ZoneInfo("America/New_York")))
      == pd.Timestamp("2026-06-02 09:30:00"))
check("epoch-decoded UTC bar is converted, not relabelled",
      bar_timestamp(datetime(2026, 6, 2, 13, 30, tzinfo=ZoneInfo("UTC")))
      == pd.Timestamp("2026-06-02 09:30:00"),
      "this is the four-hour error the old str() path would have written")
check("string form with the zone suffix parses",
      bar_timestamp("20260602 09:30:00 America/New_York")
      == pd.Timestamp("2026-06-02 09:30:00"))
check("string form with IBKR's double space parses",
      bar_timestamp("20260602  09:30:00") == pd.Timestamp("2026-06-02 09:30:00"))
check("a daily bar's bare date lands on the open",
      bar_timestamp(date(2026, 6, 2)) == pd.Timestamp("2026-06-02 09:30:00"))
try:
    bar_timestamp("2 June 2026")
    check("an unparseable date raises", False)
except ValueError:
    check("an unparseable date raises rather than guessing", True)

# Mixed aware/naive chunks in one run must still format: a tz-aware column and
# a naive one concatenate to object dtype, where .dt.strftime raises.
mixed = to_rows(pd.DataFrame({
    "ts": [bar_timestamp(datetime(2026, 6, 2, 13, 30, tzinfo=ZoneInfo("UTC"))),
           bar_timestamp("20260602  09:31:00")],
    "Open": [1.0, 1.0], "High": [1.0, 1.0], "Low": [1.0, 1.0],
    "Close": [1.0, 1.0], "Volume": [1.0, 1.0]}))
check("mixed aware/naive chunks format to one convention",
      mixed["Date"].tolist() == ["20260602 09:30:00 America/New_York",
                                 "20260602 09:31:00 America/New_York"],
      str(mixed["Date"].tolist()))

# ------------------------------------------------------- missing IBKR client
# The failure a user actually hits first: `python3 fas_1min_fetch.py` on a box
# where the venv has ib_async but `python3` is not the venv's interpreter.
print("\n5. Missing-client diagnosis")
check("fas_1min_fetch guards the ib_async import",
      "require_ib_async" in open(
          os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fas_1min_fetch.py"), encoding="utf-8").read())
_argv, _venv = sys.argv, os.environ.get("VIRTUAL_ENV")
try:
    sys.argv = ["fas_1min_fetch.py"]
    os.environ["VIRTUAL_ENV"] = os.path.join(os.sep, "somewhere", "else")
    msg = ibkr_env.diagnosis("ib_async")
    check("names the interpreter, not just the module", sys.executable in msg)
    check("says the running Python is the wrong one", "NOT its interpreter" in msg)
    check("names the script that failed", "fas_1min_fetch.py" in msg)
    os.environ.pop("VIRTUAL_ENV")
    msg = ibkr_env.diagnosis("ib_async")
    check("without a venv, says it is genuinely not installed",
          "not installed" in msg and "NOT its interpreter" not in msg)
finally:
    sys.argv = _argv
    os.environ.pop("VIRTUAL_ENV", None)
    if _venv is not None:
        os.environ["VIRTUAL_ENV"] = _venv
try:
    ibkr_env.require("some_module_nobody_has")
    check("require() exits rather than raising ImportError", False)
except SystemExit:
    check("require() exits rather than raising ImportError", True)

print("\n" + "=" * 72)
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f_ in FAIL:
        print(f"  FAILED: {f_}")
print("\nNot covered here (needs a live source): the Theta HTTP endpoint path and\n"
      "pagination, and the IBKR/TWS connection. Use --probe for the first and a\n"
      "short --start window for the second before committing to a full run.")
raise SystemExit(1 if FAIL else 0)
