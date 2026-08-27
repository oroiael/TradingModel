"""
How often does the price actually move 0.5%? Raw count, no strategy.

Reads SOXL_1min.csv and SOXS_1min.csv directly. No gate, no filter, no entry
rule, no cost model, no fill model. Nothing from the rest of this project is
imported. The only inputs are the price files and the 0.5% threshold.

Three questions, answered by counting:

  1. Starting from each minute of the session, does the price reach +0.5%
     before it reaches -0.5%, or the other way round, or neither before 16:00?

  2. How many completed UP-then-DOWN round trips are there per day — price goes
     +0.5% from some minute, and from that point goes -0.5%?

  3. How many non-overlapping 0.5% legs does a day contain at all?

    python3 band_lab/v2_dev/move_census.py
    python3 band_lab/v2_dev/move_census.py --minute 62
    python3 band_lab/v2_dev/move_census.py --pct 0.01 --since 2022-01-01
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SYMBOLS = ("SOXL", "SOXS")

#: Regular trading hours only. 09:30 is minute 0, 15:59 is minute 389.
OPEN_MIN, CLOSE_MIN = 9 * 60 + 30, 15 * 60 + 59


def load(symbol: str, since: str | None):
    """One row per minute, grouped by session. Prices as they are in the file.

    SOXS's file is back-adjusted and its prices run into the millions. That is
    irrelevant here: every number below is a ratio, and ratios do not care about
    the scale.
    """
    df = pd.read_csv(os.path.join(ROOT, f"{symbol}_1min.csv"))
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    mins = dt.dt.hour * 60 + dt.dt.minute
    keep = (mins >= OPEN_MIN) & (mins <= CLOSE_MIN)
    df = df.assign(date=dt.dt.normalize(), minute=mins - OPEN_MIN)[keep.values]
    if since:
        df = df[df["date"] >= pd.Timestamp(since)]
    return df.sort_values(["date", "minute"])


def census(df, pct):
    """For every starting minute in every session, what happens first."""
    up_first, down_first, neither, ambiguous = [], [], [], []
    round_trips, legs_per_day, n_days = [], [], 0

    for _date, g in df.groupby("date", sort=True):
        hi = g["High"].to_numpy(float)
        lo = g["Low"].to_numpy(float)
        cl = g["Close"].to_numpy(float)
        mn = g["minute"].to_numpy(int)
        n = len(cl)
        if n < 30:
            continue
        n_days += 1

        u = np.full(n, -1, dtype=int)      # first bar index reaching +pct
        d = np.full(n, -1, dtype=int)      # first bar index reaching -pct
        for i in range(n - 1):
            ref = cl[i]
            up_hits = hi[i + 1:] >= ref * (1.0 + pct)
            dn_hits = lo[i + 1:] <= ref * (1.0 - pct)
            if up_hits.any():
                u[i] = i + 1 + int(np.argmax(up_hits))
            if dn_hits.any():
                d[i] = i + 1 + int(np.argmax(dn_hits))

        for i in range(n - 1):
            if u[i] < 0 and d[i] < 0:
                neither.append(mn[i])
            elif u[i] >= 0 and (d[i] < 0 or u[i] < d[i]):
                up_first.append(mn[i])
            elif d[i] >= 0 and (u[i] < 0 or d[i] < u[i]):
                down_first.append(mn[i])
            else:
                # Both thresholds touched inside the same minute. OHLC cannot
                # say which came first, so it is counted separately rather than
                # guessed.
                ambiguous.append(mn[i])

        # 2. up-then-down round trips, non-overlapping, scanning forward
        rt, i = 0, 0
        while i < n - 1:
            if u[i] >= 0 and (d[i] < 0 or u[i] < d[i]):
                j = u[i]
                if j < n - 1 and d[j] >= 0:
                    rt += 1
                    i = d[j]
                    continue
                i = j
                continue
            i += 1
        round_trips.append(rt)

        # 3. how many 0.5% legs the day holds at all, either direction
        legs, ref, i = 0, cl[0], 1
        while i < n:
            if hi[i] >= ref * (1.0 + pct) or lo[i] <= ref * (1.0 - pct):
                legs += 1
                ref = cl[i]
            i += 1
        legs_per_day.append(legs)

    return dict(up=np.array(up_first), down=np.array(down_first),
                neither=np.array(neither), ambiguous=np.array(ambiguous),
                round_trips=np.array(round_trips),
                legs=np.array(legs_per_day), days=n_days)


def report(symbol, r, pct, minute):
    tot = len(r["up"]) + len(r["down"]) + len(r["neither"]) + len(r["ambiguous"])
    print(f"\n{symbol}   {r['days']} sessions, {tot:,} starting minutes")
    print(f"  from a given minute, which comes first — {pct:+.2%} or {-pct:.2%}?")
    for lbl, arr in (("UP first", r["up"]), ("DOWN first", r["down"]),
                     ("neither before 16:00", r["neither"]),
                     ("both in the same minute (can't tell)", r["ambiguous"])):
        print(f"    {lbl:<38}{len(arr):>9,}{len(arr)/tot*100:>8.1f}%")
    print(f"  completed UP-then-DOWN round trips per day: "
          f"mean {r['round_trips'].mean():.2f}   median "
          f"{np.median(r['round_trips']):.0f}   max {r['round_trips'].max()}")
    print(f"    days with 0: {(r['round_trips'] == 0).mean()*100:.0f}%   "
          f"1: {(r['round_trips'] == 1).mean()*100:.0f}%   "
          f"2: {(r['round_trips'] == 2).mean()*100:.0f}%   "
          f"3+: {(r['round_trips'] >= 3).mean()*100:.0f}%")
    print(f"  any-direction {pct:.1%} legs per day: "
          f"mean {r['legs'].mean():.2f}   median {np.median(r['legs']):.0f}")

    if minute is not None:
        m = minute
        u = int((r["up"] == m).sum())
        d = int((r["down"] == m).sum())
        nn = int((r["neither"] == m).sum())
        a = int((r["ambiguous"] == m).sum())
        t = u + d + nn + a
        hh, mm = divmod(OPEN_MIN + m, 60)
        print(f"\n  minute {m} of the session = {hh:02d}:{mm:02d}  "
              f"({t} sessions had it)")
        if t:
            print(f"    reached {pct:+.1%} first   {u:>6}  {u/t*100:>5.1f}%")
            print(f"    reached {-pct:.1%} first   {d:>6}  {d/t*100:>5.1f}%")
            print(f"    reached neither        {nn:>6}  {nn/t*100:>5.1f}%")
            print(f"    ambiguous              {a:>6}  {a/t*100:>5.1f}%")


def by_hour(symbol, r, pct):
    print(f"\n  {symbol} by time of day — share of starting minutes that reach "
          f"{pct:+.1%} first")
    edges = [(0, 59, "09:30-10:29"), (60, 119, "10:30-11:29"),
             (120, 179, "11:30-12:29"), (180, 239, "12:30-13:29"),
             (240, 299, "13:30-14:29"), (300, 359, "14:30-15:29"),
             (360, 389, "15:30-15:59")]
    for a, b, lbl in edges:
        u = int(((r["up"] >= a) & (r["up"] <= b)).sum())
        d = int(((r["down"] >= a) & (r["down"] <= b)).sum())
        nn = int(((r["neither"] >= a) & (r["neither"] <= b)).sum())
        am = int(((r["ambiguous"] >= a) & (r["ambiguous"] <= b)).sum())
        t = u + d + nn + am
        if not t:
            continue
        print(f"    {lbl}  up {u/t*100:>5.1f}%   down {d/t*100:>5.1f}%   "
              f"neither {nn/t*100:>5.1f}%   ambiguous {am/t*100:>5.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description="raw 0.5% move census")
    ap.add_argument("--pct", type=float, default=0.005)
    ap.add_argument("--minute", type=int, default=62)
    ap.add_argument("--since", default=None)
    a = ap.parse_args()

    print("=" * 78)
    print(f"RAW MOVE CENSUS — threshold {a.pct:.2%}, 1-minute bars, RTH only")
    print("=" * 78)
    print("  No strategy. No gate, filter, entry rule, cost or fill model.")
    print("  Reference price for each starting minute = that minute's CLOSE.")
    print("  A threshold counts as reached when a later minute's HIGH (up) or")
    print("  LOW (down) crosses it. Only within the same session.")

    for s in SYMBOLS:
        df = load(s, a.since)
        print(f"\n  {s}: {df['date'].min().date()} to {df['date'].max().date()}")
        r = census(df, a.pct)
        report(s, r, a.pct, a.minute)
        by_hour(s, r, a.pct)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
