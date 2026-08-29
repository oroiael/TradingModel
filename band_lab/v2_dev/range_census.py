"""
How much intraday range is actually there, and what would it take to capture it.

The 250 bp/day figure from V26 is NOT an opportunity. It is the width of an
error bar — the difference between filling at the best price inside every minute
and the worst. Nobody can systematically buy the low of a minute, because the
low of a minute is only knowable after the minute is over. That number measures
what the data cannot see, not money lying on the ground.

But there IS a real quantity underneath the question: the price genuinely moves
a long way every day. This measures it, and then measures the wall in front of
it.

  PATH LENGTH   add up the size of every move, ignoring direction. This is the
                theoretical maximum for a trader with perfect foresight at that
                horizon: catch every up move long, every down move short.
  RANGE         high minus low over the session. The maximum for one perfect
                round trip per day.
  NET           where it actually ended up. What a buy-and-hold got.
  EFFICIENCY    |net| / path. How much of the motion went somewhere. Low means
                chop: lots of movement, no displacement.

Then the wall. Every capture costs a round trip. At horizon H there are about
390/H of them per day, and each one costs the measured friction. So perfect
foresight has a cost too, and the break-even directional accuracy is

    p = 0.5 + friction / (2 x average absolute move at that horizon)

which is pure arithmetic and does not care what strategy you use to get there.

    python3 band_lab/v2_dev/range_census.py
    python3 band_lab/v2_dev/range_census.py --since 2024-01-01
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from research_kit import friction_for                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(_HERE))
SYMBOLS = ("SOXL", "SOXS")
OPEN_MIN, CLOSE_MIN = 9 * 60 + 30, 15 * 60 + 59
HORIZONS = (1, 2, 5, 15, 30, 60, 390)

#: Measured elsewhere in this repo, on the same data, so the wall below can be
#: compared against something real rather than against a hope.
#:   move_census.py      P(reach +X before -X) from any minute: 49.2-50.0%
#:   momentum_census.py  P(next move continues) at every lookback: 47-51%
#:   dip_census.py       P(up | after a dip): 48.3% vs a 48.5% baseline
#:   hour_census.py      best of 35 weekday x hour cells: 57.8%, 0 survive BH
MEASURED_HIT_RATES = "49-51% at every horizon and every signal tested so far"


def load(symbol: str, since: str | None) -> pd.DataFrame:
    path = os.path.join(ROOT, f"{symbol}_1min.csv")
    with open(path, "rb") as fh:
        if fh.read(40).startswith(b"version https://git-lfs"):
            raise RuntimeError(f"{path} is an LFS pointer — run `git lfs pull`")
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    mins = dt.dt.hour * 60 + dt.dt.minute
    df = df.assign(date=dt.dt.normalize(), mofd=mins)
    df = df[(mins >= OPEN_MIN) & (mins <= CLOSE_MIN)]
    if since:
        df = df[df["date"] >= pd.Timestamp(since)]
    return df.sort_values(["date", "mofd"])


def per_day(df: pd.DataFrame) -> pd.DataFrame:
    """One row per session: range, net move, and path length at each horizon."""
    rows = []
    for date, g in df.groupby("date"):
        c = g["Close"].to_numpy(float)
        if len(c) < 30:
            continue
        o = float(g["Open"].iloc[0])
        row = dict(date=date, bars=len(c),
                   rng=(g["High"].max() - g["Low"].min()) / o,
                   net=c[-1] / o - 1.0)
        for h in HORIZONS:
            # Blocks of h minutes. The last partial block is kept; it is a real
            # trade a real trader would still have to close at 15:59.
            px = np.concatenate([[o], c[h - 1::h]])
            if px[-1] != c[-1]:
                px = np.append(px, c[-1])
            r = np.diff(px) / px[:-1]
            row[f"path{h}"] = float(np.abs(r).sum())
            row[f"n{h}"] = len(r)
            row[f"absmean{h}"] = float(np.abs(r).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def bp(x) -> str:
    return f"{x*1e4:,.0f}"


def report(sym: str, d: pd.DataFrame) -> None:
    f = friction_for(sym)
    rt = f.round_trip_bp / 1e4

    print("=" * 92)
    print(f"{sym} — how much movement is actually there, {len(d):,} sessions, "
          f"{d.date.min().date()} to {d.date.max().date()}")
    print("=" * 92)
    print(f"\n  average session high-to-low range        "
          f"{d.rng.mean()*100:6.2f}%   ({bp(d.rng.mean())} bp)")
    print(f"  average |open-to-close| move             "
          f"{d.net.abs().mean()*100:6.2f}%   ({bp(d.net.abs().mean())} bp)")
    print(f"  average path length, 1-minute steps      "
          f"{d.path1.mean()*100:6.2f}%   ({bp(d.path1.mean())} bp)")
    print(f"  efficiency: |net| / path                 "
          f"{(d.net.abs()/d.path1).mean()*100:6.2f}%")
    print(f"\n  So the price travels about {d.path1.mean()*100:.1f}% of distance "
          f"in a day and ends up {d.net.abs().mean()*100:.1f}% from where it")
    print(f"  started. {(1-(d.net.abs()/d.path1).mean())*100:.0f}% of the "
          f"motion cancels itself out. That cancelling motion is the thing")
    print(f"  people mean by 'harvesting volatility', and it is real. What "
          f"follows is what it costs to reach.")

    print(f"\n  PERFECT FORESIGHT AT EACH HORIZON — catch every single move, "
          f"long and short")
    print(f"  friction {f.round_trip_bp:.2f} bp per round trip (measured)\n")
    print(f"  {'horizon':<12}{'trades/day':>11}{'gross/day':>12}"
          f"{'cost/day':>11}{'net/day':>12}{'avg move':>11}"
          f"{'break-even':>12}")
    print("  " + "-" * 79)
    for h in HORIZONS:
        n = d[f"n{h}"].mean()
        gross = d[f"path{h}"].mean()
        cost = n * rt
        avg = d[f"absmean{h}"].mean()
        be = 0.5 + rt / (2 * avg) if avg else float("nan")
        label = "1 day" if h == 390 else f"{h} min"
        print(f"  {label:<12}{n:>11.1f}{bp(gross):>11} bp{bp(cost):>10} bp"
              f"{bp(gross-cost):>11} bp{bp(avg):>10} bp{be*100:>11.1f}%")
    print(f"\n  'break-even' = the directional accuracy you need at that "
          f"horizon just to cover friction.")
    print(f"  Measured accuracy of every signal tested in this repo: "
          f"{MEASURED_HIT_RATES}.")

    print(f"\n  WHAT EACH LEVEL OF ACCURACY IS WORTH, per day, net of friction\n")
    print(f"  {'horizon':<12}" + "".join(f"{p:>10.0%}" for p in
                                          (0.50, 0.51, 0.52, 0.55, 0.60, 0.70)))
    print("  " + "-" * 72)
    for h in HORIZONS:
        n = d[f"n{h}"].mean()
        avg = d[f"absmean{h}"].mean()
        cells = []
        for p in (0.50, 0.51, 0.52, 0.55, 0.60, 0.70):
            edge = n * ((2 * p - 1) * avg - rt)
            cells.append(f"{edge*1e4:>+10.0f}")
        label = "1 day" if h == 390 else f"{h} min"
        print(f"  {label:<12}" + "".join(cells) + "  bp/day")
    print(f"\n  Read the 50% column first: it is what a coin flip pays after "
          f"costs. It is the cost of trading, nothing else.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2022-01-01")
    ap.add_argument("--symbol", choices=SYMBOLS + ("BOTH",), default="BOTH")
    a = ap.parse_args()
    for sym in (SYMBOLS if a.symbol == "BOTH" else (a.symbol,)):
        report(sym, per_day(load(sym, a.since)))
        print()
    print("=" * 92)
    print("THE POINT")
    print("=" * 92)
    print("""
  The range is real and it is large. Nothing above disputes that.

  What the table shows is that the range is not the constraint. Direction is.
  At every horizon, a coin flip loses exactly the friction, and the accuracy
  needed to clear friction rises as you trade faster — while the number of
  chances rises too, so the two fight each other and friction wins early.

  No signal measured anywhere in this repository has reached the break-even
  column at any horizon. Not the dip. Not momentum. Not the hour of the day.
  Not the day of the week. All of them sit at 49-51%.

  There is exactly one way to convert range into money without predicting
  direction, and it is not a directional strategy at all: be paid the spread
  instead of paying it (market making), or own gamma and delta-hedge, which
  mechanically converts realised path length into P&L. Whether the second one
  pays depends on realised volatility versus implied volatility, which is a
  measurable thing and is measured in vol_premium.py.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
