"""
What it costs to trade the options. The input every gamma strategy needs first.

V27 measured the volatility edge: implied 98.6%, realised close-to-close 110.4%,
realised intraday-hedgeable 81.0%. Those are gross. No option strategy can be
estimated without knowing what the option itself costs to get into and out of,
and that has never been measured in this repository.

The number that matters is NOT the dollar spread or the percentage spread. It is
the spread expressed in **volatility points**, because that is the same unit as
the edge:

    vol points of round-trip spread  =  (ask - bid) / vega

A strategy whose edge is 11.8 vol points and whose round trip costs 8 vol points
has 3.8 left. One that costs 15 has nothing. Everything else about the strategy
is decoration until that comparison is done.

CAVEAT, stated up front because it changes the reading: these files carry a
handful of snapshots per session and `option_data.load` keeps the LAST one. The
timestamp distribution is printed below so the reader can see when the quotes
are from. Late-day and after-hours quotes are WIDER than midday quotes, so every
spread here should be read as an upper bound on what a midday trader pays.

    python3 band_lab/v2_dev/option_microstructure.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import option_data                                                 # noqa: E402

DTE_BUCKETS = [(0, 1), (2, 7), (8, 21), (22, 45), (46, 90), (91, 365)]


def label(lo, hi):
    return "0-1 (0DTE)" if (lo, hi) == (0, 1) else f"{lo}-{hi}"


def main() -> int:
    print("loading option quotes (~544 MB)...", flush=True)
    d = option_data.load(verbose=True, extra=("vega", "gamma", "theta"))
    d = d[(d.bid > 0) & (d.ask > d.bid) & (d.implied_vol > 0)].copy()
    d["mny"] = (d["strike"] / d["underlying_price"] - 1.0)
    d["spread_pct"] = d["spread"] / d["mid"]

    # UNITS. These files quote vega per 1.00 of volatility (i.e. per 100
    # volatility points), NOT per 1 point. The check below caught this: it
    # returned 98.66 against a textbook per-point vega, not ~1.0. An earlier
    # version of this file divided by the raw vega and reported spreads of
    # "0.1 vol points", which would have made every option strategy look free.
    # Dividing by vega/100 gives the cost in volatility points.
    d["vol_pts"] = np.where(d["vega"] > 0, d["spread"] / (d["vega"] / 100.0),
                            np.nan)

    w = 96
    print("\n" + "=" * w)
    print("WHEN ARE THESE QUOTES FROM?")
    print("=" * w)
    t = d["ts"].dt.tz_convert("America/New_York")
    hr = (t.dt.hour + t.dt.minute / 60.0)
    print(f"  {len(d):,} usable quotes")
    for q in (0.05, 0.25, 0.50, 0.75, 0.95):
        v = hr.quantile(q)
        print(f"    q{q:<5.2f}  {int(v):02d}:{int((v%1)*60):02d}")
    print(f"  share at or after 16:00 New York: {(hr >= 16).mean()*100:.0f}%")
    print(f"  Anything at or after 16:00 is an after-hours quote. Spreads then "
          f"are wider than midday,\n  so treat every number below as an UPPER "
          f"bound on the cost a midday trader pays.")

    # ---- units check. ATM vega per 1.00 of vol is ~ S*sqrt(T)*phi(0).
    atm = d[(d.mny.abs() < 0.02) & (d.dte.between(25, 35))]
    if len(atm):
        per_unit = (atm["underlying_price"] * np.sqrt(atm["dte"] / 365.0)
                    * 0.3989)
        ratio = float((atm["vega"] / per_unit).median())
        ok = 0.7 < ratio < 1.4
        print(f"\n  [{'PASS' if ok else 'FAIL'}] vega unit check: median(file "
              f"vega / textbook ATM vega per 1.00 of vol) = {ratio:.2f}")
        print(f"  Near 1.0 confirms vega is per 1.00 of volatility, so a "
              f"spread is converted to volatility\n  points by dividing by "
              f"vega/100. This check already failed once, at 98.66 against a "
              f"per-POINT\n  reference, which is how the 100x error in an "
              f"earlier version of this file was found.")
        if not ok:
            print("  Units are not what the code assumes. Stop and fix before "
                  "reading anything below.")

    print("\n" + "=" * w)
    print("COST TO TRADE — near the money (|strike/spot - 1| < 5%)")
    print("=" * w)
    print(f"\n  {'DTE':<14}{'quotes':>9}{'mid $':>9}{'spread $':>10}"
          f"{'spread %':>10}{'VOL POINTS':>13}{'round trip':>13}")
    print("  " + "-" * 78)
    near = d[d.mny.abs() < 0.05]
    for lo, hi in DTE_BUCKETS:
        g = near[near.dte.between(lo, hi)]
        if len(g) < 50:
            continue
        vp = g["vol_pts"].median()
        print(f"  {label(lo,hi):<14}{len(g):>9,}{g['mid'].median():>9.2f}"
              f"{g['spread'].median():>10.2f}{g['spread_pct'].median()*100:>9.1f}%"
              f"{vp:>13.1f}{vp:>13.1f}")
    print(f"\n  'VOL POINTS' = (ask - bid) / vega — what crossing the spread "
          f"ONCE costs in volatility terms.")
    print(f"  Buying and later selling the same option crosses it twice, but "
          f"you pay the half-spread each\n  way, so one full spread is the "
          f"round trip. That is the 'round trip' column.")

    print("\n" + "=" * w)
    print("TERM STRUCTURE — is the front or the back richer?")
    print("=" * w)
    print(f"\n  {'DTE':<14}{'dates':>8}{'ATM IV':>10}{'vs 30d':>10}")
    print("  " + "-" * 42)
    ref = None
    for lo, hi in DTE_BUCKETS:
        g = near[near.dte.between(lo, hi)]
        if len(g) < 50:
            continue
        iv = g.groupby("trade_date")["implied_vol"].median()
        if (lo, hi) == (22, 45):
            ref = iv.mean()
        print(f"  {label(lo,hi):<14}{len(iv):>8,}{iv.mean()*100:>9.1f}%"
              f"{'' if ref is None else f'{(iv.mean()-ref)*100:>+9.1f}'}")

    print("\n" + "=" * w)
    print("SKEW — are puts richer than calls? (25-delta wings, 22-45 DTE)")
    print("=" * w)
    m = d[d.dte.between(22, 45)]
    p25 = m[(m.right == "PUT") & (m.delta.between(-0.35, -0.15))]
    c25 = m[(m.right == "CALL") & (m.delta.between(0.15, 0.35))]
    atmv = m[m.mny.abs() < 0.02]
    for name, g in (("25-delta put", p25), ("at the money", atmv),
                    ("25-delta call", c25)):
        if len(g):
            print(f"  {name:<18}{g['implied_vol'].median()*100:>7.1f}%   "
                  f"({len(g):,} quotes)")
    if len(p25) and len(c25):
        print(f"\n  put minus call: "
              f"{(p25['implied_vol'].median()-c25['implied_vol'].median())*100:+.1f} "
              f"vol points")

    print("\n" + "=" * w)
    print("WHAT IS EVEN TRADEABLE — contracts per day with a two-sided quote")
    print("=" * w)
    per_day = near.groupby("trade_date").size()
    print(f"  near-the-money contracts quoted per day: "
          f"median {int(per_day.median())}, min {int(per_day.min())}")
    zero = d[d.dte <= 1]
    print(f"  0-1 DTE quotes in the files: {len(zero):,} over "
          f"{zero.trade_date.nunique():,} dates")
    print(f"  bid size at the money: median {int(near['bid_size'].median())} "
          f"contracts; ask size median {int(near['ask_size'].median())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
