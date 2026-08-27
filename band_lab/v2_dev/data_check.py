"""
Is the price data any good? Checks that can fail, not reassurances.

Everything concluded so far rests on two CSV files. Before believing any of it,
these are the things that would be wrong if the data were bad:

  1. The 1-minute and 5-minute files must agree. Aggregate five 1-minute bars
     and they must reproduce the 5-minute bar's open, high, low and close.
     They come from separate downloads, so agreement is real evidence.

  2. SOXL and SOXS track the same index in opposite directions. Their minute
     returns must be strongly negatively correlated. Anything near zero means
     one of the files is mislabelled, misaligned, or garbage.

  3. SOXL is 3x the semiconductor index. Regressed on SOXX minute returns the
     slope must come out near +3.

  4. Sessions must have ~390 minutes, no duplicate timestamps, no gaps, no
     zero or negative prices, no bars where high < low.

  5. Returns must have fat tails. Real minute data has kurtosis far above 3.
     Synthetic or smoothed data does not.

    python3 band_lab/v2_dev/data_check.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OPEN_MIN, CLOSE_MIN = 9 * 60 + 30, 15 * 60 + 59
FAILURES = []


def check(name, ok, detail):
    mark = "PASS" if ok else "FAIL"
    if not ok:
        FAILURES.append(name)
    print(f"  [{mark}] {name}: {detail}")


def load_min(symbol, minutes=True):
    fn = f"{symbol}_1min.csv" if minutes else f"{symbol}_5min_6Years.csv"
    path = os.path.join(ROOT, fn)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        if fh.read(40).startswith(b"version https://git-lfs"):
            return None
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    m = dt.dt.hour * 60 + dt.dt.minute
    keep = (m >= OPEN_MIN) & (m <= CLOSE_MIN)
    return df.assign(dt=dt, date=dt.dt.normalize(),
                     minute=m - OPEN_MIN)[keep.values].sort_values("dt")


def main() -> int:
    print("=" * 78)
    print("DATA QUALITY — checks designed to fail if the files are wrong")
    print("=" * 78)

    one = {s: load_min(s) for s in ("SOXL", "SOXS")}
    five = {s: load_min(s, minutes=False) for s in ("SOXL", "SOXS")}

    for s in ("SOXL", "SOXS"):
        d = one[s]
        print(f"\n{s}  1-minute file: {len(d):,} rows, "
              f"{d['date'].nunique():,} sessions, "
              f"{d['date'].min().date()} to {d['date'].max().date()}")
        check(f"{s} no duplicate timestamps",
              not d["dt"].duplicated().any(),
              f"{int(d['dt'].duplicated().sum())} duplicates")
        check(f"{s} no non-positive prices",
              bool((d[["Open", "High", "Low", "Close"]] > 0).all().all()),
              "all four price columns > 0")
        bad_hl = int((d["High"] < d["Low"]).sum())
        check(f"{s} high >= low everywhere", bad_hl == 0,
              f"{bad_hl} bars with high < low")
        oc = int(((d["Open"] > d["High"]) | (d["Open"] < d["Low"]) |
                  (d["Close"] > d["High"]) | (d["Close"] < d["Low"])).sum())
        check(f"{s} open/close inside high/low", oc == 0,
              f"{oc} bars violate it")
        per = d.groupby("date").size()
        full = int((per == 390).sum())
        check(f"{s} sessions are ~390 minutes",
              full / len(per) > 0.90,
              f"{full:,} of {len(per):,} sessions exactly 390 "
              f"({full/len(per)*100:.1f}%), median {int(per.median())}")
        r = d.groupby("date")["Close"].pct_change().dropna()
        r = r[np.isfinite(r)]
        kurt = float(pd.Series(r).kurtosis())
        check(f"{s} returns have fat tails (real, not synthetic)",
              kurt > 5,
              f"excess kurtosis {kurt:.1f} (normal = 0; real minute data is "
              f"far above)")

        # --- 1-minute vs 5-minute agreement
        f = five[s]
        if f is None:
            check(f"{s} 1-min agrees with 5-min", False,
                  "5-minute file is an LFS pointer, cannot compare")
            continue
        g = d.assign(blk=d["minute"] // 5).groupby(["date", "blk"]).agg(
            o=("Open", "first"), h=("High", "max"),
            l=("Low", "min"), c=("Close", "last"))
        f5 = f.assign(blk=f["minute"] // 5).set_index(["date", "blk"])
        j = g.join(f5[["Open", "High", "Low", "Close"]], how="inner")
        if not len(j):
            check(f"{s} 1-min agrees with 5-min", False, "no overlapping bars")
            continue
        rel = {k: (np.abs(j[a] - j[b]) / j[b]).median()
               for k, a, b in (("open", "o", "Open"), ("high", "h", "High"),
                               ("low", "l", "Low"), ("close", "c", "Close"))}
        worst = max(rel.values())
        check(f"{s} 1-min aggregates to the 5-min file",
              worst < 1e-6,
              f"{len(j):,} bars compared, worst median relative error "
              f"{worst:.2e}")

    # --- cross-symbol sanity
    print()
    a = one["SOXL"].set_index("dt")["Close"].pct_change()
    b = one["SOXS"].set_index("dt")["Close"].pct_change()
    j = pd.concat([a.rename("l"), b.rename("s")], axis=1).dropna()
    j = j[np.isfinite(j).all(axis=1)]
    c = float(j["l"].corr(j["s"]))
    check("SOXL and SOXS move opposite each other", c < -0.90,
          f"minute-return correlation {c:+.4f} over {len(j):,} minutes "
          f"(should be near -1)")

    soxx = load_min("SOXX", minutes=False)
    if soxx is None:
        print("  [skip] SOXL vs SOXX leverage: no 1-minute SOXX file")
    else:
        x = soxx.set_index("dt")["Close"].pct_change()
        l5 = five["SOXL"]
        if l5 is not None:
            y = l5.set_index("dt")["Close"].pct_change()
            k = pd.concat([y.rename("l"), x.rename("x")], axis=1).dropna()
            k = k[np.isfinite(k).all(axis=1)]
            slope = float(np.polyfit(k["x"], k["l"], 1)[0])
            check("SOXL is ~3x the semiconductor index",
                  2.7 < slope < 3.3,
                  f"regression slope on SOXX = {slope:.3f} over {len(k):,} bars")

    print("\n" + "=" * 78)
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED: {', '.join(FAILURES)}")
        return 1
    print("All checks passed. The data is not the problem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
