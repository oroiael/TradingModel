"""
Momentum or mean reversion? Both, measured the same way, from raw prices.

`dip_census.py` asked one question: after price falls, does it bounce? Answer,
no — 48.3% against a 48.5% baseline. This asks the general version, so the
opposite hypothesis gets the same test rather than being assumed away.

For every minute it computes the return over the previous N minutes, buckets by
that, and then measures what happens NEXT:

  - does +0.5% arrive before -0.5%?
  - the tradeable version: does +1% arrive before -4% before 15:55, and what is
    the expected return per bet?

If momentum is real, the up-rate rises with the trailing return. If mean
reversion is real, it falls. If neither, every bucket sits at ~48.5% and there
is nothing in this data to trade on a one-minute-to-one-day horizon.

Nothing from the strategy engine is imported. Prices and thresholds only.

    python3 band_lab/v2_dev/momentum_census.py
    python3 band_lab/v2_dev/momentum_census.py --lookback 30
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SYMBOLS = ("SOXL", "SOXS")
OPEN_MIN, CLOSE_MIN = 9 * 60 + 30, 15 * 60 + 59
TARGET, STOP = 0.01, 0.04
START_MIN, LAST_HOLD_MIN, FLATTEN_MIN = 90, 380, 385

LOOKBACKS = (5, 15, 30, 60)
EDGES = [-9.0, -0.01, -0.005, -0.0025, 0.0025, 0.005, 0.01, 9.0]
LABELS = ["< -1.00%", "-1.00 to -0.50%", "-0.50 to -0.25%", "-0.25 to +0.25%",
          "+0.25 to +0.50%", "+0.50 to +1.00%", "> +1.00%"]


def load(symbol, since):
    df = pd.read_csv(os.path.join(ROOT, f"{symbol}_1min.csv"))
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    m = dt.dt.hour * 60 + dt.dt.minute
    keep = (m >= OPEN_MIN) & (m <= CLOSE_MIN)
    df = df.assign(date=dt.dt.normalize(), minute=m - OPEN_MIN)[keep.values]
    if since:
        df = df[df["date"] >= pd.Timestamp(since)]
    return df.sort_values(["date", "minute"])


def forward(df):
    """Per minute: which of +-0.5% comes first, and the +1%/-4%/flatten bet."""
    rows = []
    for _date, g in df.groupby("date", sort=True):
        hi = g["High"].to_numpy(float)
        lo = g["Low"].to_numpy(float)
        cl = g["Close"].to_numpy(float)
        mn = g["minute"].to_numpy(int)
        n = len(cl)
        if n < 120:
            continue
        end = int(np.searchsorted(mn, FLATTEN_MIN, side="right"))
        for i in range(n - 1):
            ref = cl[i]
            up = hi[i + 1:] >= ref * 1.005
            dn = lo[i + 1:] <= ref * 0.995
            iu = int(np.argmax(up)) if up.any() else 10 ** 9
            idn = int(np.argmax(dn)) if dn.any() else 10 ** 9
            side = 1 if iu < idn else (0 if idn < iu else -1)

            bet = np.nan
            if START_MIN <= mn[i] <= LAST_HOLD_MIN and i + 1 < end:
                fu = hi[i + 1:end] >= ref * (1.0 + TARGET)
                fd = lo[i + 1:end] <= ref * (1.0 - STOP)
                ju = int(np.argmax(fu)) if fu.any() else 10 ** 9
                jd = int(np.argmax(fd)) if fd.any() else 10 ** 9
                if ju < jd and ju < 10 ** 9:
                    bet = TARGET
                elif jd < 10 ** 9:
                    bet = -STOP
                else:
                    bet = cl[end - 1] / ref - 1.0

            trail = {}
            for L in LOOKBACKS:
                trail[L] = (cl[i] / cl[i - L] - 1.0) if i >= L else np.nan
            rows.append((side, bet, *[trail[L] for L in LOOKBACKS]))
    return pd.DataFrame(rows, columns=["side", "bet"] +
                        [f"t{L}" for L in LOOKBACKS])


def show(symbol, d, lookback):
    col = f"t{lookback}"
    sub = d[np.isfinite(d[col])].copy()
    sub["b"] = pd.cut(sub[col], bins=EDGES, labels=LABELS)
    print(f"\n{symbol}  — bucketed by the return over the PREVIOUS "
          f"{lookback} minutes")
    print(f"  {'trailing move':<20}{'minutes':>10}{'up first':>10}"
          f"{'down first':>12}{'bets':>9}{'exp/bet':>10}{'t':>8}")
    for lbl in LABELS:
        g = sub[sub.b == lbl]
        if not len(g):
            continue
        res = g[g.side >= 0]
        up = float((res.side == 1).mean()) * 100 if len(res) else float("nan")
        b = g["bet"].dropna()
        if len(b) > 1:
            m, sem = b.mean(), b.std(ddof=1) / math.sqrt(len(b))
            t = m / sem
        else:
            m, t = float("nan"), float("nan")
        print(f"  {lbl:<20}{len(g):>10,}{up:>9.1f}%{100-up:>11.1f}%"
              f"{len(b):>9,}{m*100:>+9.3f}%{t:>8.1f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="momentum vs mean reversion")
    ap.add_argument("--since", default="2022-01-01")
    ap.add_argument("--lookback", type=int, default=None)
    a = ap.parse_args()

    print("=" * 88)
    print("MOMENTUM OR MEAN REVERSION — raw 1-minute data, no strategy engine")
    print("=" * 88)
    print("  'up first'  = share reaching +0.5% before -0.5% later that session")
    print("  'exp/bet'   = expected return of buying here with a +1% target,")
    print("                -4% stop and a forced exit at 15:55, from real prices")
    print("  MOMENTUM would show up-first RISING down the table.")
    print("  MEAN REVERSION would show it FALLING. Flat means neither.")

    for s in SYMBOLS:
        d = forward(load(s, a.since))
        for L in ([a.lookback] if a.lookback else LOOKBACKS):
            show(s, d, L)
    print("\n  Minutes overlap, so the t values are optimistic. They bound the")
    print("  direction of the answer, not its precision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
