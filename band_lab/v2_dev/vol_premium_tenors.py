"""
Is there a volatility edge at LONG tenors? V29 Tier 2 #4's missing input.

V27 compared ~30-day at-the-money implied vol against the following 30 sessions
of realised vol and found +11.8 points. That is the only tenor ever tested here,
and V29 flagged the gap explicitly: a 180-day option must be compared against the
following 180 days, not against the next month.

The comparison has to be MATCHED on both sides or it means nothing:

    tenor      implied vol taken from        realised vol measured over
    30 days    options with 22-45 DTE        the next 21 sessions
    90 days    options with 75-105 DTE       the next 63 sessions
    180 days   options with 150-210 DTE      the next 124 sessions

It also has to account for something V27 did not have to: **overlap**. Rolling
180-day windows over 4.5 years give ~1,000 dates but only about 9 independent
observations, so the standard error is computed on the independent count, not the
row count. Reporting a t-statistic on 1,000 overlapping windows would be
arithmetic dressed as evidence.

    python3 band_lab/v2_dev/vol_premium_tenors.py
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import option_data                                                 # noqa: E402
from vol_premium import forward_rv, minute_frame, realised_vols    # noqa: E402

TRADING_DAYS = 252

#: (label, calendar days, DTE lo, DTE hi, forward sessions)
TENORS = [
    ("1 week",   7,    4,   10,   5),
    ("1 month",  30,   22,  45,   21),
    ("3 months", 90,   75,  105,  63),
    ("6 months", 180,  150, 210,  124),
    ("1 year",   365,  300, 400,  252),
]


def atm_iv(d, lo, hi, band=0.07):
    x = d[(d.dte.between(lo, hi)) & (d.implied_vol > 0)
          & (d.bid > 0) & (d.ask > d.bid)].copy()
    x = x[(x["strike"] / x["underlying_price"] - 1.0).abs() <= band]
    if x.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    g = x.groupby("trade_date")
    return g["implied_vol"].median(), (g["ask"].median() - g["bid"].median())


def main() -> int:
    print("loading 1-minute bars...", flush=True)
    rv = realised_vols(minute_frame())
    print("loading option quotes...", flush=True)
    d = option_data.load(verbose=True, extra=("vega",))

    w = 96
    print("\n" + "=" * w)
    print("MATCHED-TENOR VOLATILITY PREMIUM — SOXL")
    print("   implied vol at each tenor against realised vol over the SAME "
          "forward horizon")
    print("=" * w)
    print(f"\n  {'tenor':<11}{'dates':>7}{'indep':>7}{'implied':>10}"
          f"{'realised':>10}{'edge':>9}{'se':>8}{'t':>7}{'% RV>IV':>9}")
    print("  " + "-" * 76)

    out = []
    for label, cal, lo, hi, fwd in TENORS:
        iv, _ = atm_iv(d, lo, hi)
        if iv.empty:
            print(f"  {label:<11}  no quotes in {lo}-{hi} DTE")
            continue
        rvf = forward_rv(rv["v_cc"], fwd)
        t = pd.DataFrame({"iv": iv, "rv": rvf}).dropna()
        if len(t) < 30:
            print(f"  {label:<11}{len(t):>7}  too few matched dates")
            continue
        edge = (t["rv"] - t["iv"]) * 100
        # Overlap: consecutive windows share all but one session, so the
        # independent count is the span divided by the horizon.
        indep = max(len(t) / fwd, 1.0)
        se = edge.std(ddof=1) / math.sqrt(indep)
        out.append(dict(label=label, n=len(t), indep=indep,
                        iv=t["iv"].mean(), rv=t["rv"].mean(),
                        edge=edge.mean(), se=se, t=edge.mean() / se,
                        pos=(edge > 0).mean()))
        print(f"  {label:<11}{len(t):>7,}{indep:>7.1f}{t['iv'].mean()*100:>9.1f}%"
              f"{t['rv'].mean()*100:>9.1f}%{edge.mean():>+9.1f}{se:>8.1f}"
              f"{edge.mean()/se:>7.2f}{(edge>0).mean()*100:>8.0f}%")

    print(f"""
  'indep' is the number of NON-overlapping windows the sample supports, and the
  standard error uses it. On 4.5 years a 6-month tenor gives about 9 independent
  observations and a 1-year tenor about 4 -- a t-statistic on the raw row count
  would be roughly {math.sqrt(124):.0f}x too large at 6 months.

  The edge column is realised minus implied in volatility points. Positive means
  options were cheap: the underlying went on to move more than they were priced
  for.""")

    if out:
        o = pd.DataFrame(out)
        print("\n" + "=" * w)
        print("WHAT THIS MEANS FOR A LONG-DATED STRADDLE (V29 Tier 2 #4)")
        print("=" * w)
        f = {"1 week": 9.3, "1 month": 8.1, "3 months": 6.5,
             "6 months": 4.9, "1 year": 4.9}
        print(f"\n  {'tenor':<11}{'edge':>8}{'V28 spread':>13}"
              f"{'net':>8}{'cycles/yr':>11}{'net/yr':>10}")
        print("  " + "-" * 62)
        for _, r in o.iterrows():
            sp = f.get(r.label, np.nan)
            cal = dict((x[0], x[1]) for x in TENORS)[r.label]
            per_yr = 365.0 / cal
            print(f"  {r.label:<11}{r.edge:>+8.1f}{-sp:>12.1f}"
                  f"{r.edge - sp:>+8.1f}{per_yr:>11.1f}"
                  f"{(r.edge - sp) * per_yr:>+10.1f}")
        print(f"""
  'V28 spread' is the measured end-of-day round trip at that tenor. It is an
  UNDERSTATEMENT at every tenor: V32 measured the real intraday ATM straddle
  round trip at 17.8 vol points against the 10.6 those snapshots imply, a
  shortfall of 7.2. The same shortfall has NOT been measured at 6 or 12 months
  and is not applied here, so every 'net' below is optimistic by an unknown
  amount that is probably several points.

  'net/yr' is what matters for comparing tenors: a cheap spread paid twice a
  year beats an expensive one paid twelve times, which is the entire case for
  #4 and the reason it is worth testing at all.""")
        o.to_csv(os.path.join(_HERE, "out", "V37_tenor_premium.csv"),
                 index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
