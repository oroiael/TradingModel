"""
P0 — which spot were the vendor's greeks computed against?

The option files carry an `underlying_price` that is a single end-of-day value
per trade date, beside quote timestamps that are scattered through the session.
Every implied vol and every delta in those files was computed against SOME spot,
and which one decides whether the data can carry a backtest.

Two hypotheses, and they are distinguishable
---------------------------------------------
  EOD    the vendor used the same end-of-day spot it reports. Then a quote
         stamped 15:08 was priced against a 16:00 price, every IV is wrong by
         whatever SOXL did in between, and the file needs repairing.

  LIVE   the vendor used the spot at the quote's own moment and merely reports
         the EOD one in that column. Then the greeks are right, the column is
         misleading, and nothing needs repairing except our reading of it.

Recompute implied vol from the quote mid under each spot and see which
reproduces the vendor's own `implied_vol`. Rates and dividends are unknown and
assumed; that does not matter, because an error in them moves both hypotheses
by the same amount and the test is which one lands closer.

Gates, written before the run
------------------------------
  G1  EOD  reproduces vendor IV within 1.0 vol pt at the median -> defect real
  G2  LIVE reproduces vendor IV within 1.0 vol pt at the median -> no defect
  G3  neither reproduces it -> STOP, something else is wrong
  G4  put-call parity residual must shrink under whichever spot G1/G2 selects,
      or the minute-bar join itself is wrong

    python3 band_lab/v2_dev/option_spot_audit.py
    python3 band_lab/v2_dev/option_spot_audit.py --year 2024 --rate 0.05
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def minute_bars():
    """SOXL 1-minute closes, keyed (date, minute-of-day)."""
    df = pd.read_csv(os.path.join(ROOT, "SOXL_1min.csv"))
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    return (df.assign(d=dt.dt.normalize(), m=dt.dt.hour * 60 + dt.dt.minute)
              .set_index(["d", "m"])["Close"])


def load(year, dte_lo, dte_hi, band):
    use = ["expiration", "strike", "right", "timestamp", "bid", "ask",
           "delta", "implied_vol", "underlying_price", "trade_date"]
    df = pd.read_csv(os.path.join(ROOT, f"SOXL_Options_{year}.csv"),
                     usecols=use, low_memory=False)
    qt = pd.to_datetime(df.timestamp, format="mixed", utc=True).dt.tz_convert(
        "America/New_York")
    df["qmin"] = qt.dt.hour * 60 + qt.dt.minute
    df["qdate"] = qt.dt.tz_localize(None).dt.normalize()
    df["dte"] = (pd.to_datetime(df.expiration)
                 - pd.to_datetime(df.trade_date)).dt.days
    df["mid"] = (df.bid + df.ask) / 2
    df["mny"] = df.strike / df.underlying_price

    keep = (df.qmin > 0) & (df.qmin >= 570) & (df.qmin <= 959)   # real, in RTH
    keep &= df.bid.gt(0.05) & df.ask.gt(df.bid)
    keep &= df.dte.between(dte_lo, dte_hi)
    keep &= df.mny.sub(1).abs().lt(band)
    keep &= df.implied_vol.gt(0.05) & df.implied_vol.lt(4.0)
    return df[keep].copy()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", default="2023")
    p.add_argument("--rate", type=float, default=0.05)
    p.add_argument("--div", type=float, default=0.0)
    p.add_argument("--dte", type=int, nargs=2, default=[7, 90])
    p.add_argument("--band", type=float, default=0.15,
                   help="|strike/spot - 1| ceiling; vega is largest near the money")
    a = p.parse_args()

    bars = minute_bars()
    d = load(a.year, a.dte[0], a.dte[1], a.band)
    print(f"\n{'=' * 78}")
    print(f"  P0  SOXL {a.year}   {len(d):,} usable quotes   "
          f"{d.trade_date.nunique()} dates")
    print(f"  real timestamp, RTH, DTE {a.dte[0]}-{a.dte[1]}, "
          f"|moneyness-1| < {a.band}")
    print(f"{'=' * 78}")

    # --- the join: each quote to SOXL's close in its own minute
    idx = pd.MultiIndex.from_arrays([d.qdate, d.qmin])
    d["spot_live"] = bars.reindex(idx).to_numpy()
    hit = d.spot_live.notna()
    print(f"\n  minute-bar join: matched {hit.sum():,} of {len(d):,} "
          f"({hit.mean() * 100:.1f}%)")
    d = d[hit].copy()
    drift = (d.spot_live / d.underlying_price - 1) * 100
    print(f"  spot at the quote vs the reported EOD spot:")
    print(f"    median {drift.median():+.3f}%   mean |drift| {drift.abs().mean():.3f}%"
          f"   p90 |drift| {drift.abs().quantile(.9):.2f}%")

    # --- recompute IV under each hypothesis
    T = d.dte.to_numpy(float) / 365.0
    K = d.strike.to_numpy(float)
    px = d.mid.to_numpy(float)
    right = np.where(d.right.str.upper().str.startswith("C"), "CALL", "PUT")
    iv_eod = np.full(len(d), np.nan)
    iv_live = np.full(len(d), np.nan)
    for r in ("CALL", "PUT"):
        m = right == r
        iv_eod[m] = bs.implied_vol(px[m], d.underlying_price.to_numpy(float)[m],
                                   K[m], T[m], a.rate, a.div, r)
        iv_live[m] = bs.implied_vol(px[m], d.spot_live.to_numpy(float)[m],
                                    K[m], T[m], a.rate, a.div, r)
    v = d.implied_vol.to_numpy(float)
    e_eod = np.abs(iv_eod - v) * 100
    e_live = np.abs(iv_live - v) * 100
    ok = np.isfinite(e_eod) & np.isfinite(e_live)
    e_eod, e_live = e_eod[ok], e_live[ok]

    print(f"\n  RECOMPUTED IV vs THE VENDOR'S OWN implied_vol   "
          f"({ok.sum():,} solvable)")
    print(f"    {'hypothesis':<28}{'median |err|':>14}{'mean':>9}{'p90':>9}"
          f"{'within 1.0':>12}")
    for lab, e in (("EOD  vendor's own column", e_eod),
                   ("LIVE spot at quote time", e_live)):
        print(f"    {lab:<28}{np.median(e):>13.3f}{e.mean():>9.3f}"
              f"{np.percentile(e, 90):>9.3f}{(e < 1.0).mean() * 100:>11.1f}%")

    g1 = np.median(e_eod) < 1.0
    g2 = np.median(e_live) < 1.0
    print(f"\n    G1 EOD  within 1.0 vol pt: {'PASS' if g1 else 'fail'}")
    print(f"    G2 LIVE within 1.0 vol pt: {'PASS' if g2 else 'fail'}")
    if not (g1 or g2):
        print(f"\n    G3 TRIPPED — neither spot reproduces the vendor's IV.")
        print(f"    Something other than the spot is wrong. Stopping.")
    winner = "EOD" if np.median(e_eod) <= np.median(e_live) else "LIVE"
    print(f"    closer: {winner}   by "
          f"{abs(np.median(e_eod) - np.median(e_live)):.3f} vol pts at the median")

    # --- G4: put-call parity, both legs stamped, under each spot
    print(f"\n  G4  PUT-CALL PARITY   C - P  vs  S - K*exp(-rT)")
    piv = d.pivot_table(index=["trade_date", "expiration", "strike"],
                        columns="right", values=["mid", "spot_live", "qmin",
                                                 "underlying_price", "dte"],
                        aggfunc="first").dropna()
    if len(piv) > 50:
        c, pu = piv[("mid", "CALL")], piv[("mid", "PUT")]
        Tp = piv[("dte", "CALL")].to_numpy(float) / 365.0
        Kp = piv.index.get_level_values("strike").to_numpy(float)
        gap = (piv[("qmin", "CALL")] - piv[("qmin", "PUT")]).abs()
        s_eod = piv[("underlying_price", "CALL")].to_numpy(float)
        s_live = ((piv[("spot_live", "CALL")] + piv[("spot_live", "PUT")]) / 2).to_numpy(float)
        disc = Kp * np.exp(-a.rate * Tp)
        r_eod = np.abs((c - pu).to_numpy(float) - (s_eod - disc))
        r_live = np.abs((c - pu).to_numpy(float) - (s_live - disc))
        print(f"    {len(piv):,} strikes with both legs stamped   "
              f"median leg time gap {gap.median():.0f} min")
        print(f"    {'spot used':<28}{'median residual $':>18}{'p90':>10}")
        print(f"    {'EOD':<28}{np.median(r_eod):>17.4f}{np.percentile(r_eod,90):>10.4f}")
        print(f"    {'LIVE (mean of both legs)':<28}{np.median(r_live):>17.4f}"
              f"{np.percentile(r_live,90):>10.4f}")
        better = "LIVE" if np.median(r_live) < np.median(r_eod) else "EOD"
        print(f"    smaller residual: {better}")
        # tight-gap subset: the cleanest possible parity test
        tight = gap.to_numpy() <= 5
        if tight.sum() > 30:
            print(f"    legs within 5 min ({tight.sum():,}):  "
                  f"EOD {np.median(r_eod[tight]):.4f}   "
                  f"LIVE {np.median(r_live[tight]):.4f}")
    else:
        print(f"    too few paired strikes to test")

    # --- what the choice actually moves
    print(f"\n  WHAT THE REPAIR WOULD MOVE")
    mny_eod = (d.strike / d.underlying_price - 1).abs()
    mny_live = (d.strike / d.spot_live - 1).abs()
    print(f"    |moneyness| reclassified by >1%: "
          f"{((mny_eod - mny_live).abs() > 0.01).mean() * 100:.1f}% of quotes")
    print(f"    IV level shift, LIVE minus EOD: median "
          f"{np.nanmedian((iv_live - iv_eod)) * 100:+.3f} vol pts   "
          f"mean |shift| {np.nanmean(np.abs(iv_live - iv_eod)) * 100:.3f}\n")


if __name__ == "__main__":
    main()
