"""
Queue #2: does the unlevered index carry a volatility premium worth trading?

The repo holds no SMH or SOXX option data -- V47 needed a live TWS session for
that, and its Part B failed its own control on a unit error. But the premium is
still measurable here, because V47's Part A established the one thing needed to
derive it.

The derivation, and the assumption it rests on
-----------------------------------------------
V47 measured the implied-vol ratio between the 3x fund and its index at 2.97
observed against 2.97 predicted by the leverage identity -- an exact hit, and a
refutation of the additive alternative. If implied vol scales proportionally
with leverage, then the index's implied vol is the fund's divided by that
ratio, and a year of SOXL option quotes yields a year of SOXX implied vol
without holding a single SOXX contract.

That is an assumption carried across a year from a ratio verified at one moment
and one tenor. It is stated here rather than buried, and the control below is
what makes it usable.

THE CONTROL
-----------
The same pipeline is run on SOXL itself first, where the answer is already
known from two independent prior studies: V27 measured +11.8 volatility points
and V37 measured +10.9. If this code does not land in that neighbourhood on
SOXL, its SOXX number means nothing and should not be read.

WHAT V45 PREDICTED, BEFORE ANY OF THIS WAS RUN
-----------------------------------------------
V45 corrected V44's error -- comparing SOXL's edge in volatility points against
SMH's spread in volatility points, when a volatility point is not the same
amount of money on underlyings whose vols differ by 3x. Scaling the premium
proportionally, V45 predicted:

    index edge ~ +3.7 vol pts against a 2.9 spread -- net ~ +0.8

So the bar this test is scored against was written down before it ran, and
+0.8 volatility points is the honest size of the prize, not the +8.6 that the
uncorrected comparison suggested.

    python3 band_lab/v2_dev/index_premium.py
    python3 band_lab/v2_dev/index_premium.py --ratio 2.97 --horizon 30
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPREADS = (("SOXL", 18.5), ("SOXX", 8.0), ("SMH", 2.9))   # V43, replicated V47


def daily_close(path):
    df = pd.read_csv(os.path.join(ROOT, path))
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    return df.assign(day=dt.dt.normalize()).groupby("day").agg(c=("Close", "last")).c


def atm_iv(path, lo, hi, band=0.03):
    """Median ATM implied vol per trade date, at a target tenor."""
    cols = ["expiration", "strike", "right", "bid", "ask", "implied_vol",
            "underlying_price", "trade_date"]
    o = pd.read_csv(os.path.join(ROOT, path), usecols=cols, low_memory=False)
    o = o[(o.bid > 0.05) & (o.ask > o.bid) & o.implied_vol.notna()
          & (o.implied_vol > 0.05)]
    o["dte"] = (pd.to_datetime(o.expiration) - pd.to_datetime(o.trade_date)).dt.days
    o = o[(o.dte >= lo) & (o.dte <= hi)]
    o = o[(o.strike / o.underlying_price - 1).abs() < band]
    s = o.groupby("trade_date").implied_vol.median()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def forward_rv(px, n):
    """Realised vol over the n sessions AFTER each date. No look-back leakage."""
    r = np.log(px / px.shift(1))
    return (r.shift(-n).rolling(n).std() * np.sqrt(252)).dropna()


def score(iv, rv, label, horizon):
    j = pd.concat([iv.rename("iv"), rv.rename("rv")], axis=1, sort=True).dropna()
    if j.empty:
        return None
    edge = (j.rv - j.iv) * 100
    # Windows overlap by `horizon` sessions, so the independent count is far
    # below the row count. Deflating by that factor is the minimum honest
    # correction; it still flatters the t.
    eff = max(len(j) / horizon, 1)
    se = edge.std() / np.sqrt(eff)
    return dict(label=label, n=len(j), eff=eff, iv=j.iv.mean() * 100,
                rv=j.rv.mean() * 100, edge=edge.mean(), se=se,
                t=edge.mean() / se if se else np.nan,
                hit=(edge > 0).mean() * 100)


def show(r):
    print(f"  {r['label']}")
    print(f"    dates {r['n']:>4}   independent windows ~{r['eff']:.0f}")
    print(f"    implied {r['iv']:>6.1f}%   forward realised {r['rv']:>6.1f}%")
    print(f"    EDGE {r['edge']:+.2f} vol pts   SE {r['se']:.2f}   "
          f"t {r['t']:+.2f}   positive on {r['hit']:.0f}% of dates")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--options", default="SOXL_1Yr_Options_Greeks_EOD.csv")
    p.add_argument("--fund", default="SOXL_1min.csv")
    p.add_argument("--index", default="SOXX_5min_6Years.csv")
    p.add_argument("--ratio", type=float, default=2.97, help="IV ratio, V47 measured")
    p.add_argument("--horizon", type=int, default=30, help="forward sessions")
    p.add_argument("--dte", type=int, nargs=2, default=[25, 35])
    a = p.parse_args()

    iv = atm_iv(a.options, *a.dte)
    print(f"\n{'=' * 76}")
    print(f"  ATM {a.dte[0]}-{a.dte[1]}d implied vol: {len(iv)} dates, "
          f"{iv.index.min().date()} -> {iv.index.max().date()}")
    print(f"{'=' * 76}\n")

    ctl = score(iv, forward_rv(daily_close(a.fund), a.horizon),
                "CONTROL -- the levered fund, where the answer is known", a.horizon)
    show(ctl)
    ok = 8.0 < ctl["edge"] < 15.0
    print(f"    prior studies: V27 +11.8, V37 +10.9  ->  "
          f"{'METHOD AGREES' if ok else 'METHOD DISAGREES -- stop here'}\n")
    if not ok:
        raise SystemExit("control failed; the index number below would be unreadable")

    idx = score(iv / a.ratio, forward_rv(daily_close(a.index), a.horizon),
                f"INDEX -- implied derived as fund IV / {a.ratio}", a.horizon)
    show(idx)
    print(f"    V45 predicted ~+3.7 before this was run  ->  "
          f"{'PREDICTION HELD' if 2.5 < idx['edge'] < 5.0 else 'prediction missed'}")

    print(f"\n  AGAINST THE ROUND TRIP EACH INSTRUMENT CHARGES")
    print(f"    {'instrument':<12}{'spread':>9}{'edge':>9}{'net':>9}{'net/SE':>9}")
    for name, spread in SPREADS:
        e = ctl["edge"] if name == "SOXL" else idx["edge"]
        se = ctl["se"] if name == "SOXL" else idx["se"]
        net = e - spread
        print(f"    {name:<12}{spread:>9.1f}{e:>9.2f}{net:>+9.2f}{net / se:>+9.2f}")
    print(f"\n    net/SE is the number that matters. A positive net worth a"
          f" fraction of one\n    standard error is not an edge, it is a "
          f"coin landing the right way up.\n")


if __name__ == "__main__":
    main()
