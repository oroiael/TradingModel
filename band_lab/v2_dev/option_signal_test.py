"""
Do option prices predict tomorrow's move in the underlying?

The claim being tested: options encode a forward view, that view moves during
the day, so the move should say something about the next session.

Seven signals, fixed before running, from the derived series in `pricing_lab/`
(real quotes, 2024-01 to 2026-07):

    iv7, iv30                       the level of implied volatility
    slope_7_30, slope_7_180         the term structure
    d_iv7, d_slope_7_30             how they CHANGED from yesterday
    carry_ann                       the implied forward's financing rate

Each is tested against the NEXT session's SOXL return. Seven tests at 5% means
0.35 false positives expected; that number is printed beside the results.

**A control runs first.** Implied volatility is known to predict realized
volatility — that is one of the most reliable relationships in finance. So the
same signals are tested against next-day realized volatility too. If IV does
not predict RV here, the join or the data is broken and no directional result
from this script means anything.

    python3 band_lab/v2_dev/option_signal_test.py
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAB = os.path.join(ROOT, "pricing_lab")

SIGNALS = ["iv7", "iv30", "slope_7_30", "slope_7_180",
           "d_iv7", "d_slope_7_30", "carry_ann"]


def soxl_daily():
    df = pd.read_csv(os.path.join(ROOT, "SOXL_5min_6Years.csv"))
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    d = df.assign(date=dt.dt.normalize())
    close = d.groupby("date")["Close"].last()
    hi = d.groupby("date")["High"].max()
    lo = d.groupby("date")["Low"].min()
    out = pd.DataFrame({"close": close})
    out["ret"] = close.pct_change()
    # Realized volatility proxy for the control: the day's own range.
    out["rv"] = (hi - lo) / close
    return out


def build():
    ts = pd.read_csv(os.path.join(LAB, "s3_term_structure.csv"),
                     parse_dates=["trade_date"]).set_index("trade_date")
    fwd = pd.read_csv(os.path.join(LAB, "s4_implied_forward.csv"),
                      parse_dates=["trade_date"])
    # nearest expiry per date — the most responsive part of the surface
    near = (fwd.sort_values(["trade_date", "dte"])
               .groupby("trade_date").first()[["carry_ann"]])

    x = ts.join(near, how="inner").sort_index()
    x["d_iv7"] = x["iv7"].diff()
    x["d_slope_7_30"] = x["slope_7_30"].diff()

    s = soxl_daily()
    # NEXT session's return and range, aligned to today's signal.
    nxt = s.shift(-1)[["ret", "rv"]].rename(columns={"ret": "next_ret",
                                                     "rv": "next_rv"})
    j = x.join(nxt, how="inner").dropna()
    return j


def ols(y, x):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    n = len(x)
    if n < 30:
        return None
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    if sxx <= 0:
        return None
    b = ((x - xm) * (y - ym)).sum() / sxx
    a = ym - b * xm
    resid = y - (a + b * x)
    s2 = (resid ** 2).sum() / (n - 2)
    se = math.sqrt(s2 / sxx)
    t = b / se if se else float("nan")
    r2 = 1 - (resid ** 2).sum() / ((y - ym) ** 2).sum()
    return dict(n=n, beta=b, t=t, r2=r2)


def quintiles(j, sig, target):
    q = pd.qcut(j[sig], 5, labels=False, duplicates="drop")
    g = j.groupby(q)[target].agg(["mean", "count"])
    return g


def table(j, target, label, unit):
    print(f"\n  {label}")
    print(f"    {'signal':<16}{'n':>6}{'slope':>12}{'t':>8}{'R2':>9}"
          f"{'Q1':>10}{'Q5':>10}{'Q5-Q1':>10}")
    hits = 0
    for sig in SIGNALS:
        r = ols(j[target], j[sig])
        if r is None:
            continue
        g = quintiles(j, sig, target)
        q1, q5 = g["mean"].iloc[0], g["mean"].iloc[-1]
        if abs(r["t"]) > 1.96:
            hits += 1
        star = " *" if abs(r["t"]) > 1.96 else ""
        print(f"    {sig:<16}{r['n']:>6}{r['beta']:>12.4f}{r['t']:>8.2f}"
              f"{r['r2']:>9.4f}{q1*unit:>9.3f}{q5*unit:>9.3f}"
              f"{(q5-q1)*unit:>9.3f}{star}")
    return hits


def main() -> int:
    argparse.ArgumentParser(description="do options predict the underlying?").parse_args()
    j = build()

    print("=" * 92)
    print("DO OPTION PRICES PREDICT THE NEXT SESSION?")
    print("=" * 92)
    print(f"  {len(j)} trade dates, {j.index.min().date()} to {j.index.max().date()}")
    print("  signals from real EOD option quotes; target from the SOXL 5-minute file")
    print("  Q1/Q5 = mean outcome in the lowest / highest quintile of the signal")

    print("\n" + "-" * 92)
    print("  CONTROL — IV must predict next-day realized range, or the test is broken")
    print("-" * 92)
    c = table(j, "next_rv", "target: next session's high-low range, in %", 100.0)

    print("\n" + "-" * 92)
    print("  THE ACTUAL QUESTION — does any of it predict DIRECTION?")
    print("-" * 92)
    h = table(j, "next_ret", "target: next session's return, in %", 100.0)

    print(f"\n  direction: {h} of {len(SIGNALS)} signals clear |t| > 1.96; "
          f"{0.05*len(SIGNALS):.2f} expected by chance")
    print(f"  control:   {c} of {len(SIGNALS)} — if this is 0 the join is "
          f"suspect and nothing above counts")
    print("\n  R2 is the share of next-day variance explained. For a tradeable")
    print("  directional signal you would want it well above 0.01; noise gives ~0.003.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
