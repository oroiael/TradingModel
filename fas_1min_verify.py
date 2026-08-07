"""Validate a 1-minute capture before anything is built on it.

Runs the same integrity checks this repository's analysis depends on, plus the
strongest validation available: aggregate the 1-minute bars up to 5 minutes and
compare them against the existing <SYMBOL>_5min_6Years.csv over the overlapping
window.  Two independent captures of the same instrument agreeing bar-for-bar
is far better evidence than any internal consistency check.

    python3 fas_1min_verify.py                  # FAS_1min.csv vs FAS_5min_6Years.csv
    python3 fas_1min_verify.py --symbol SOXL    # self-test on the known-good pair

Checks
  1. format         columns, timestamp convention, dtypes, zone suffix
  2. session grid   bars per session, first/last bar, missing sessions
  3. data hygiene   duplicates, NaN, non-positive prices, OHLC violations
  4. basis          split-adjusted or raw, and any unexplained overnight jump
  5. cross-check    1-min aggregated to 5-min vs the existing 5-min file
  6. reference      structural comparison against SOXL_1min.csv

Exit code is non-zero if any BLOCKING check fails.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("ETF_DATA_DIR", ROOT)
ZONE = " America/New_York"
FULL_1MIN, HALF_1MIN = 390, 210          # measured from SOXL_1min.csv
FULL_5MIN = 78

FAILURES: list[str] = []
WARNINGS: list[str] = []


def fail(msg):
    FAILURES.append(msg); print(f"  [FAIL] {msg}")


def warn(msg):
    WARNINGS.append(msg); print(f"  [warn] {msg}")


def ok(msg):
    print(f"  [ok]   {msg}")


def banner(t):
    print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")


def load_bars(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise SystemExit(f"missing file: {path}")
    if os.path.getsize(path) < 10_000:
        raise SystemExit(f"{path} is {os.path.getsize(path)} bytes -- Git LFS "
                         f"pointer? run: git lfs pull --include='{os.path.basename(path)}'")
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["Date"].astype(str).str.slice(0, 17),
                              format="%Y%m%d %H:%M:%S")
    df["session"] = df["ts"].dt.normalize()
    df["tod"] = df["ts"].dt.strftime("%H:%M")
    return df.sort_values("ts", ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a 1-minute bar capture")
    ap.add_argument("--symbol", default="FAS")
    ap.add_argument("--one", default=None, help="path to the 1-minute CSV")
    ap.add_argument("--five", default=None, help="path to the 5-minute CSV")
    ap.add_argument("--ret-tol-bp", type=float, default=1.0,
                    help="median |5-min return difference| tolerated, in bp")
    args = ap.parse_args()

    p1 = args.one or os.path.join(DATA, f"{args.symbol}_1min.csv")
    p5 = args.five or os.path.join(DATA, f"{args.symbol}_5min_6Years.csv")

    banner(f"1.  FORMAT  --  {os.path.basename(p1)}")
    d = load_bars(p1)
    expect = ["Date", "Open", "High", "Low", "Close", "Volume"]
    if list(d.columns[:6]) == expect:
        ok(f"columns {expect}")
    else:
        fail(f"columns are {list(d.columns[:6])}, expected {expect}")
    raw = pd.read_csv(p1, usecols=["Date"])["Date"].astype(str)
    if raw.str.endswith(ZONE).all():
        ok(f'every timestamp carries "{ZONE.strip()}"')
    else:
        fail(f"{int((~raw.str.endswith(ZONE)).sum())} rows lack the zone suffix")
    if raw.str.slice(0, 17).str.match(r"^\d{8} \d{2}:\d{2}:\d{2}$").all():
        ok("timestamps parse as YYYYMMDD HH:MM:SS")
    else:
        fail("some timestamps do not match YYYYMMDD HH:MM:SS")
    print(f"  rows {len(d):,}   sessions {d['session'].nunique():,}   "
          f"{d['ts'].min()} -> {d['ts'].max()}")
    span_y = (d["ts"].max() - d["ts"].min()).days / 365.25
    print(f"  span {span_y:.2f} years")
    if span_y < 5.5:
        warn(f"span is {span_y:.2f} years, short of the 6-year target")

    banner("2.  SESSION GRID")
    bc = d.groupby("session").size()
    counts = Counter(bc)
    print(f"  bars/session: {dict(sorted(counts.most_common(6)))}")
    n_full, n_half = counts.get(FULL_1MIN, 0), counts.get(HALF_1MIN, 0)
    odd = {k: v for k, v in counts.items() if k not in (FULL_1MIN, HALF_1MIN)}
    if n_full:
        ok(f"{n_full} full sessions at {FULL_1MIN} bars (09:30-15:59)")
    else:
        fail(f"no session has {FULL_1MIN} bars -- grid does not match SOXL_1min.csv")
    print(f"  half-days at {HALF_1MIN} bars: {n_half}")
    if odd:
        warn(f"{sum(odd.values())} sessions with other bar counts: "
             f"{dict(list(sorted(odd.items()))[:8])}")
    firsts = d.groupby("session")["tod"].first().value_counts()
    lasts = d.groupby("session")["tod"].last().value_counts()
    print(f"  first bar: {dict(firsts.head(3))}")
    print(f"  last  bar: {dict(lasts.head(4))}")
    if firsts.index[0] != "09:30":
        fail(f"most sessions start at {firsts.index[0]}, expected 09:30")
    else:
        ok("sessions start at 09:30")
    if lasts.index[0] != "15:59":
        fail(f"most sessions end at {lasts.index[0]}, expected 15:59 "
             f"(SOXL_1min.csv convention; 16:00 must NOT be present)")
    else:
        ok("sessions end at 15:59")

    banner("3.  DATA HYGIENE")
    dup = int(d["ts"].duplicated().sum())
    (ok if dup == 0 else fail)(f"duplicate timestamps: {dup}")
    nan = int(d[["Open", "High", "Low", "Close", "Volume"]].isna().sum().sum())
    (ok if nan == 0 else fail)(f"NaN values: {nan}")
    nonpos = int((d[["Open", "High", "Low", "Close"]] <= 0).any(axis=1).sum())
    (ok if nonpos == 0 else fail)(f"non-positive prices: {nonpos}")
    viol = int(((d["High"] < d[["Open", "Close"]].max(axis=1)) |
                (d["Low"] > d[["Open", "Close"]].min(axis=1))).sum())
    (ok if viol == 0 else fail)(f"OHLC violations: {viol}")
    zv = int((d["Volume"] == 0).sum())
    print(f"  zero-volume bars: {zv:,} ({zv/len(d):.2%})  "
          f"[SOXL_1min.csv has 8,080 = 1.26%]")

    banner("4.  PRICE BASIS AND CORPORATE ACTIONS")
    k = d.groupby("session")["Close"].last()
    o = d.groupby("session")["Open"].first()
    ratio = (o / k.shift(1)).dropna()
    jumps = ratio[(ratio < 0.6) | (ratio > 1.7)]
    print(f"  overnight open/prev-close range: {ratio.min():.4f} .. {ratio.max():.4f}")
    if len(jumps) == 0:
        ok("no unexplained overnight jump -- series is on a continuous basis")
    else:
        warn(f"{len(jumps)} overnight jumps outside [0.60, 1.70]:")
        for dt_, r in jumps.items():
            print(f"      {dt_.date()}  ratio {r:.4f}  (1-for-{1/r:.2f} "
                  f"or {r:.2f}-for-1 split?)")
        print("      A real split means the series is RAW. Adjust it, or record it "
              "in band_lab/live/replay.py SPLIT_ADJUSTMENTS.")

    banner(f"5.  CROSS-CHECK  --  1-min aggregated vs {os.path.basename(p5)}")
    if not os.path.exists(p5):
        warn(f"{p5} not present; skipping the strongest available check")
    else:
        f5 = load_bars(p5)
        d5 = d.set_index("ts")
        agg = d5.resample("5min").agg(Open=("Open", "first"), High=("High", "max"),
                                      Low=("Low", "min"), Close=("Close", "last"),
                                      Volume=("Volume", "sum")).dropna(subset=["Close"])
        agg = agg[agg.index.strftime("%H:%M").astype(str) <= "15:55"]
        j = agg.join(f5.set_index("ts")[["Open", "High", "Low", "Close", "Volume"]],
                     how="inner", lsuffix="_1m", rsuffix="_5m")
        print(f"  overlapping 5-minute bars: {len(j):,}")
        if len(j) < 100:
            fail("almost no overlap between the two files -- check the date ranges")
        else:
            lvl = (j["Close_1m"] / j["Close_5m"])
            print(f"  close ratio (1-min agg / 5-min file): median {lvl.median():.6f}, "
                  f"min {lvl.min():.6f}, max {lvl.max():.6f}")
            # A constant ratio means one shared basis. A ratio that CHANGES means
            # the two files disagree about a corporate action -- which is what
            # SOXL does (1.0 after 2021-03-02, 1/15 before it). Checking only the
            # median hides exactly that, so test the spread.
            if lvl.max() / max(lvl.min(), 1e-12) < 1.01:
                if abs(lvl.median() - 1) < 1e-3:
                    ok("identical price basis throughout")
                else:
                    warn(f"constant basis offset of {lvl.median():.4f}x -- the two "
                         f"files use different adjustment conventions, but "
                         f"consistently, so returns remain comparable")
            else:
                era = lvl.round(4)
                changes = era.ne(era.shift(1)) & era.shift(1).notna()
                pts = era.index[changes]
                warn(f"price basis CHANGES within the overlap "
                     f"(ratio spans {lvl.min():.4f} to {lvl.max():.4f}) -- the two "
                     f"files disagree about a corporate action")
                if len(pts):
                    big = [p for p in pts
                           if abs(era.loc[p] / era.shift(1).loc[p] - 1) > 0.02]
                    for p in big[:5]:
                        f_ = era.loc[p] / era.shift(1).loc[p]
                        print(f"      {p}: ratio steps by {f_:.4f} "
                              f"(1-for-{1/f_:.2f}?)")
                print("      This is EXPECTED here if the 1-min file is "
                      "split-adjusted and the 5-min file is raw (SOXL behaves "
                      "exactly this way). Returns below are basis-independent and "
                      "are the check that matters.")
            # Returns are the basis-free comparison.
            sess1 = j.index.normalize()
            r1 = np.log(j["Close_1m"]).diff()
            r5 = np.log(j["Close_5m"]).diff()
            same = sess1 == pd.Series(sess1, index=j.index).shift(1)
            m = same & r1.notna() & r5.notna()
            diff_bp = ((r1 - r5)[m]).abs() * 1e4
            print(f"  |5-min return difference|: median {diff_bp.median():.4f} bp, "
                  f"p95 {diff_bp.quantile(0.95):.4f} bp, max {diff_bp.max():.2f} bp")
            if diff_bp.median() <= args.ret_tol_bp:
                ok(f"returns agree (median {diff_bp.median():.4f} bp <= "
                   f"{args.ret_tol_bp} bp tolerance)")
            else:
                fail(f"returns disagree: median {diff_bp.median():.4f} bp exceeds "
                     f"{args.ret_tol_bp} bp -- the two captures are not the same series")
            bad = (diff_bp > 25).sum()
            print(f"  bars differing by more than 25 bp: {bad:,} "
                  f"({bad/max(1,len(diff_bp)):.3%})")
            vr = (j["Volume_1m"] / j["Volume_5m"].replace(0, np.nan)).dropna()
            print(f"  volume ratio: median {vr.median():.4f} "
                  f"(1.0 = identical share counts)")
            if abs(vr.median() - 1) > 0.02:
                warn("volume differs materially -- one source may be adjusting "
                     "volume for splits, or reporting consolidated vs primary tape")
            # session coverage
            s1 = set(d["session"].unique()); s5 = set(f5["session"].unique())
            lo, hi = max(min(s1), min(s5)), min(max(s1), max(s5))
            miss = sorted(x for x in s5 if lo <= x <= hi and x not in s1)
            print(f"  sessions in the 5-min file but missing from the 1-min file, "
                  f"within the overlap: {len(miss)}")
            if miss:
                warn(f"first few: {[str(x.date()) for x in miss[:8]]}")

    banner("6.  STRUCTURAL COMPARISON WITH SOXL_1min.csv")
    ref = os.path.join(DATA, "SOXL_1min.csv")
    if not os.path.exists(ref) or os.path.getsize(ref) < 10_000:
        warn("SOXL_1min.csv not available locally; skipping")
    elif os.path.abspath(ref) == os.path.abspath(p1):
        print("  (target IS SOXL_1min.csv -- self-test mode)")
    else:
        rd = pd.read_csv(ref, usecols=["Date"])
        rk = rd["Date"].astype(str).str.slice(0, 8)
        rs = rk.nunique()
        rbc = Counter(rk.value_counts().values)
        print(f"  reference: {len(rd):,} rows, {rs:,} sessions, "
              f"bars/session {dict(sorted(rbc.most_common(4)))}")
        print(f"  target   : {len(d):,} rows, {d['session'].nunique():,} sessions, "
              f"bars/session {dict(sorted(counts.most_common(4)))}")
        if set(counts) <= {FULL_1MIN, HALF_1MIN} and set(rbc) <= {FULL_1MIN, HALF_1MIN}:
            ok("same session-grid structure as the reference file")

    banner("VERDICT")
    if FAILURES:
        print(f"  {len(FAILURES)} BLOCKING failure(s):")
        for f in FAILURES:
            print(f"    - {f}")
    if WARNINGS:
        print(f"  {len(WARNINGS)} warning(s):")
        for w in WARNINGS:
            print(f"    - {w}")
    if not FAILURES and not WARNINGS:
        print("  clean -- the capture matches the repository's conventions.")
    elif not FAILURES:
        print("  usable, with the warnings above understood.")
    else:
        print("  NOT usable until the blocking failures are resolved.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
