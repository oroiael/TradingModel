"""
Does buying a dip actually improve the odds? Raw count, no strategy engine.

The whole premise of the strategy is that price falling 1% below the session
high makes a bounce more likely. `move_census.py` established the unconditional
baseline: from a random minute, +0.5% comes first about 48.5% of the time. This
asks whether the dip condition beats that number.

Two measurements, both straight from the 1-minute files:

  A. Bucketed by how far below the running session high the price sits, what
     share of minutes reach +0.5% before -0.5%?

  B. The strategy's actual bet, priced from raw data with no fill model at all:
     standing at or below (session high x 0.99) between 11:00 and 15:50, does
     +1% arrive before -4% before the 15:55 flatten — and what is the resulting
     expected return per trade?

The session high is taken from COMPLETED minutes only, which is how the engine
computes its anchor. Nothing here looks forward to set an entry.

    python3 band_lab/v2_dev/dip_census.py
    python3 band_lab/v2_dev/dip_census.py --since 2022-01-01
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

#: The strategy's own numbers, so measurement B prices the real bet.
DIP, TARGET, STOP = 0.01, 0.01, 0.04
START_MIN, LAST_HOLD_MIN, FLATTEN_MIN = 90, 380, 385   # 11:00, 15:50, 15:55

#: Depth buckets for measurement A, in fractions below the running high.
BUCKETS = [(0.0, 0.0025), (0.0025, 0.005), (0.005, 0.01),
           (0.01, 0.015), (0.015, 0.02), (0.02, 1.0)]


def load(symbol, since):
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


def run(df):
    a_up = np.zeros(len(BUCKETS), dtype=np.int64)
    a_dn = np.zeros(len(BUCKETS), dtype=np.int64)
    a_no = np.zeros(len(BUCKETS), dtype=np.int64)
    b_out, b_ret = {"target": 0, "stop": 0, "flatten": 0}, []
    b_first = []                       # per-minute outcome for the real bet

    for _date, g in df.groupby("date", sort=True):
        hi = g["High"].to_numpy(float)
        lo = g["Low"].to_numpy(float)
        cl = g["Close"].to_numpy(float)
        mn = g["minute"].to_numpy(int)
        n = len(cl)
        if n < 60:
            continue
        # Running high over COMPLETED minutes: high of bars 0..i-1.
        run_hi = np.maximum.accumulate(hi)
        anchor = np.empty(n)
        anchor[0] = np.nan
        anchor[1:] = run_hi[:-1]

        for i in range(1, n - 1):
            if not np.isfinite(anchor[i]) or anchor[i] <= 0:
                continue
            depth = 1.0 - cl[i] / anchor[i]
            if depth < 0:
                depth = 0.0

            # ---- A: symmetric +-0.5% from here, bucketed by depth
            b = next((k for k, (a_, z) in enumerate(BUCKETS)
                      if a_ <= depth < z), None)
            if b is not None:
                ref = cl[i]
                up = hi[i + 1:] >= ref * 1.005
                dn = lo[i + 1:] <= ref * 0.995
                iu = int(np.argmax(up)) if up.any() else -1
                idn = int(np.argmax(dn)) if dn.any() else -1
                if iu < 0 and idn < 0:
                    a_no[b] += 1
                elif idn < 0 or (iu >= 0 and iu < idn):
                    a_up[b] += 1
                elif iu < 0 or idn < iu:
                    a_dn[b] += 1

            # ---- B: the real bet. Standing at/below anchor*(1-DIP), 11:00-15:50
            if not (START_MIN <= mn[i] <= LAST_HOLD_MIN):
                continue
            if cl[i] > anchor[i] * (1.0 - DIP):
                continue
            ref = cl[i]
            end = np.searchsorted(mn, FLATTEN_MIN, side="right")
            fut_hi, fut_lo = hi[i + 1:end], lo[i + 1:end]
            if not len(fut_hi):
                continue
            up = fut_hi >= ref * (1.0 + TARGET)
            dn = fut_lo <= ref * (1.0 - STOP)
            iu = int(np.argmax(up)) if up.any() else 10 ** 9
            idn = int(np.argmax(dn)) if dn.any() else 10 ** 9
            if iu < idn and iu < 10 ** 9:
                b_out["target"] += 1
                b_ret.append(TARGET)
                b_first.append(1)
            elif idn < 10 ** 9:
                b_out["stop"] += 1
                b_ret.append(-STOP)
                b_first.append(0)
            else:
                b_out["flatten"] += 1
                b_ret.append(cl[end - 1] / ref - 1.0)
                b_first.append(-1)

    return a_up, a_dn, a_no, b_out, np.array(b_ret), np.array(b_first)


def main() -> int:
    ap = argparse.ArgumentParser(description="does a dip improve the odds?")
    ap.add_argument("--since", default="2022-01-01")
    a = ap.parse_args()

    print("=" * 84)
    print("DOES BUYING A DIP IMPROVE THE ODDS?  raw 1-minute data, no engine")
    print("=" * 84)
    print("  session high uses COMPLETED minutes only — nothing looks forward")

    for s in SYMBOLS:
        df = load(s, a.since)
        up, dn, no, out, ret, first = run(df)

        print(f"\n{s}   {df['date'].nunique()} sessions "
              f"({df['date'].min().date()} to {df['date'].max().date()})")
        print("\n  A. P(+0.5% before -0.5%), by how far below the session high")
        print(f"     {'depth below high':<22}{'minutes':>11}{'up first':>11}"
              f"{'down first':>12}")
        for k, (lo_, hi_) in enumerate(BUCKETS):
            t = up[k] + dn[k] + no[k]
            if not t:
                continue
            lbl = (f"{lo_:.2%} - {hi_:.2%}" if hi_ < 1 else f"{lo_:.2%}+")
            print(f"     {lbl:<22}{t:>11,}{up[k]/t*100:>10.1f}%"
                  f"{dn[k]/t*100:>11.1f}%")

        n = sum(out.values())
        if not n:
            continue
        mean = ret.mean()
        sd = ret.std(ddof=1)
        sem = sd / math.sqrt(n)
        print(f"\n  B. THE ACTUAL BET: at or below the high x 0.99, 11:00-15:50,")
        print(f"     does +1% arrive before -4% before the 15:55 flatten?")
        print(f"     {n:,} qualifying minutes")
        for k in ("target", "stop", "flatten"):
            print(f"       {k:<10}{out[k]:>10,}{out[k]/n*100:>8.1f}%")
        print(f"     expected return per bet  {mean*100:+.4f}%   "
              f"sd {sd*100:.2f}%   sem {sem*100:.4f}%")
        print(f"     t = {mean/sem:+.2f}   "
              f"95% CI [{(mean-1.96*sem)*100:+.4f}%, "
              f"{(mean+1.96*sem)*100:+.4f}%]")
        # Decomposed, because the headline hides where the loss comes from.
        resolved = out["target"] + out["stop"]
        need = STOP / (TARGET + STOP)          # p*TARGET = (1-p)*STOP -> p
        flat_avg = ret[first == -1].mean() if (first == -1).any() else 0.0
        print(f"     of the bets that RESOLVE (+1% or -4%, ignoring flattens):")
        print(f"       P(target) = {out['target']/resolved:.1%}, "
              f"break-even needs {need:.1%}  -> "
              f"{'PROFITABLE' if out['target']/resolved > need else 'LOSING'}")
        print(f"     where the money actually goes, per bet:")
        print(f"       targets   {out['target']/n*TARGET*100:+.3f}%")
        print(f"       stops     {out['stop']/n*-STOP*100:+.3f}%")
        print(f"       flattens  {out['flatten']/n*flat_avg*100:+.3f}%"
              f"   ({out['flatten']/n:.1%} of bets averaging {flat_avg*100:+.3f}%)")
        print(f"       TOTAL     {mean*100:+.3f}%")
    print("\n  NOTE: these minutes overlap heavily — consecutive minutes share "
          "most of\n  their forward path — so the standard errors above are "
          "optimistic. They\n  bound the direction of the answer, not its "
          "precision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
