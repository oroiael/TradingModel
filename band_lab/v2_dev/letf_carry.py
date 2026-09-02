"""
Is SOXL's decay harvestable, and what does the short leg have to beat?

Queue item #1. The premise was that SOXL's volatility decay -- V44 measured the
fund turning a +159% index into +119.9% -- is free money to a short, gated only
by the borrow rate. The premise is wrong in an instructive way.

What the arithmetic says before any data
-----------------------------------------
SOXL's contract is to deliver 3x the index's DAILY return. So a position that is
short $1 of SOXL and long $3 of the index, reset every day, has a daily P&L of

    -(3 * r_index) + 3 * r_index = 0

exactly zero, before fees. The decay does not appear. It cannot: the decay is a
compounding effect that accumulates across days, and rebalancing daily removes
precisely the multi-day compounding that creates it.

The decay is therefore only reachable by NOT rebalancing -- and an unrebalanced
short of a 3x fund is a short gamma position. It profits when the index chops
and loses when the index trends, in either direction. That is a volatility
trade with an unbounded tail, not an arbitrage.

So the daily-rebalanced pair earns exactly one thing: the amount by which SOXL
fails to deliver its 3x. That is the fund's fee and its cost of funds, and this
script measures it.

What it has to beat
--------------------
To be short $1 of SOXL and long $3 of the index you must finance $2 net (the
$3 long, less $1 of short proceeds). You have therefore replaced the fund's
borrowing with your own. The trade pays the difference between what the fund
charges for leverage and what leverage costs you, and nothing else:

    net = (fund fee + fund financing) - 2 * your_margin_rate - your_borrow_fee

The borrow fee is one of two costs and the smaller one. A sensitivity over both
is printed instead of a single answer, because neither rate is in this repo.

    python3 band_lab/v2_dev/letf_carry.py
    python3 band_lab/v2_dev/letf_carry.py --leverage 3 --index SOXX_5min_6Years.csv
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def daily_close(path):
    df = pd.read_csv(os.path.join(ROOT, path))
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    return df.assign(day=dt.dt.normalize()).groupby("day").agg(c=("Close", "last")).c


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fund", default="SOXL_1min.csv")
    p.add_argument("--index", default="SOXX_5min_6Years.csv")
    p.add_argument("--leverage", type=float, default=3.0)
    a = p.parse_args()
    L = a.leverage

    df = pd.concat([daily_close(a.fund).rename("f"),
                    daily_close(a.index).rename("x")], axis=1).dropna()
    df["rf"] = df.f.pct_change()
    df["rx"] = df.x.pct_change()
    df = df.dropna()
    df["pair"] = -df.rf + L * df.rx          # short 1 fund, long L index, daily reset
    yrs = (df.index[-1] - df.index[0]).days / 365.25
    ann = df.pair.mean() * 252
    vol = df.pair.std() * np.sqrt(252)
    t = df.pair.mean() / df.pair.std() * np.sqrt(len(df))

    print(f"\n{'=' * 78}")
    print(f"  {a.fund.split('_')[0]} carry vs {a.index.split('_')[0]}   "
          f"{df.index[0].date()} -> {df.index[-1].date()}   {len(df):,} sessions")
    print(f"{'=' * 78}")

    beta = np.polyfit(df.rx, df.rf, 1)[0]
    r2 = np.corrcoef(df.rx, df.rf)[0, 1] ** 2
    print(f"\n  DAILY TRACKING       realised beta {beta:.4f} against a stated {L:.1f}"
          f"   R^2 {r2:.4f}")
    print(f"    The shortfall from {L:.1f} IS the carry. Daily tracking is the "
          f"product's contract,")
    print(f"    so a daily-reset pair nets exactly that shortfall and nothing else.")

    print(f"\n  DELTA-NEUTRAL PAIR   short 1 fund / long {L:.0f} index, reset daily")
    print(f"    gross {ann * 100:+.2f}%/yr   vol {vol * 100:.2f}%   t = {t:+.2f}"
          f"   Sharpe {ann / vol:.2f}")

    sx = df.rx.std() * np.sqrt(252)
    theo = 0.5 * L * (L - 1) * sx * sx
    print(f"\n  VS THE DECAY IT WAS SUPPOSED TO CAPTURE")
    print(f"    index vol {sx * 100:.1f}%   theoretical drag 0.5*L*(L-1)*sigma^2 = "
          f"{theo * 100:.1f}%/yr")
    print(f"    delta-neutrally captured                        "
          f"{ann * 100:.2f}%/yr")
    print(f"    unreachable without being short gamma           "
          f"{(theo - ann) * 100:.1f}%/yr")

    print(f"\n  IS IT DECAY OR IS IT FINANCING?")
    print(f"    {'year':<7}{'sessions':>9}{'pair/yr':>10}{'index vol':>11}")
    for y, g in df.groupby(df.index.year):
        if len(g) < 60:
            continue
        print(f"    {y:<7}{len(g):>9}{g.pair.mean() * 252 * 100:>9.2f}%"
              f"{g.rx.std() * np.sqrt(252) * 100:>10.1f}%")
    print(f"    Decay would scale with the vol column. Rank-correlate them and see.")
    rho = df.groupby(df.index.year).apply(
        lambda g: pd.Series({"p": g.pair.mean() * 252,
                             "v": g.rx.std() * np.sqrt(252)}))
    rho = rho[df.groupby(df.index.year).size() >= 60]
    print(f"    corr(annual pair return, annual index vol) = "
          f"{rho.p.corr(rho.v):+.2f} across {len(rho)} years")

    print(f"\n  WHAT YOU NET, per $1 of fund shorted (requires ${L:.0f} of index long,")
    print(f"  so ${L - 1:.0f} financed after short proceeds)")
    print(f"    {'margin rate':>12}{'borrow fee':>12}{'carry cost':>12}"
          f"{'net/yr':>10}")
    for m in (0.02, 0.03, 0.04, 0.05, 0.06):
        for b in (0.005, 0.02):
            cost = (L - 1) * m + b
            net = ann - cost
            flag = "  <-- clears" if net > 0 else ""
            print(f"    {m * 100:>11.1f}%{b * 100:>11.1f}%{cost * 100:>11.2f}%"
                  f"{net * 100:>9.2f}%{flag}")
    print(f"\n    breakeven: {(L - 1):.0f} x margin rate + borrow fee must stay "
          f"under {ann * 100:.2f}%/yr")
    print(f"    on the last full year it was {df[df.index.year == df.index.year.max() - 1].pair.mean() * 252 * 100:.2f}%/yr\n")


if __name__ == "__main__":
    main()
