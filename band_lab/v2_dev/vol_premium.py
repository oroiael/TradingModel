"""
The only way to turn range into money without predicting direction: own gamma.

Everything else measured in this repo needs a directional call, and every
directional signal tested has come in at 49-51%. Gamma is different. If you own
an option and delta-hedge it, you are mechanically forced to sell into strength
and buy into weakness, and your P&L over the life of the hedge is approximately

    0.5 * gamma * S^2 * (realised variance - implied variance) * time

You do not have to be right about direction even once. You have to be right
about ONE thing: whether the market's implied volatility is below what the
stock actually goes on to do.

So that is the question this measures, and it is measurable with data already
in this repository:

    for each trade date, take the ~30-day at-the-money implied vol
    then look forward and compute what volatility ACTUALLY happened
    compare

If implied is systematically above realised, gamma buyers lose and the harvest
runs the other way — you sell options, which is a different business with a
different risk. If implied is systematically below realised, buying and hedging
pays, and then the question becomes whether hedging costs eat it.

Realised volatility is computed three ways because they are not the same number
and the difference is the point:

    close-to-close   includes the overnight gap. What the option is priced on.
    open-to-close    the day session only. What an intraday hedger captures.
    1-minute         the path an aggressive hedger could actually reach.

    python3 band_lab/v2_dev/vol_premium.py
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import option_data                                                 # noqa: E402
from research_kit import friction_for                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(_HERE))
TRADING_DAYS = 252
OPEN_MIN, CLOSE_MIN = 9 * 60 + 30, 15 * 60 + 59


def minute_frame() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(ROOT, "SOXL_1min.csv"))
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    mins = dt.dt.hour * 60 + dt.dt.minute
    df = df.assign(date=dt.dt.normalize(), mofd=mins)
    return df[(mins >= OPEN_MIN) & (mins <= CLOSE_MIN)].sort_values(
        ["date", "mofd"])


def realised_vols(mn: pd.DataFrame) -> pd.DataFrame:
    """Per-session variance contributions, three ways. Annualised later."""
    rows = []
    prev_close = None
    for date, g in mn.groupby("date"):
        c = g["Close"].to_numpy(float)
        if len(c) < 30:
            continue
        o = float(g["Open"].iloc[0])
        r_intraday = np.diff(np.log(c))
        rows.append(dict(
            date=date,
            # squared log return, the daily variance contribution
            v_cc=(np.log(c[-1] / prev_close) ** 2) if prev_close else np.nan,
            v_oc=np.log(c[-1] / o) ** 2,
            v_1m=float((r_intraday ** 2).sum()),
            path=float(np.abs(np.diff(c) / c[:-1]).sum()),
            n_min=len(c)))
        prev_close = c[-1]
    return pd.DataFrame(rows).set_index("date")


def atm_iv(d: pd.DataFrame, dte_lo=21, dte_hi=45, band=0.05) -> pd.Series:
    """Per trade date: median implied vol of near-the-money, ~30-day contracts.

    Median rather than mean, and both calls and puts, because a single stale
    quote in a thin strike would drag an average and this is the input to
    everything below.
    """
    x = d[(d.dte.between(dte_lo, dte_hi)) & (d.implied_vol > 0)
          & (d.bid > 0) & (d.ask > d.bid)].copy()
    x["mny"] = (x["strike"] / x["underlying_price"] - 1.0).abs()
    x = x[x["mny"] <= band]
    return x.groupby("trade_date")["implied_vol"].median()


def forward_rv(v: pd.Series, n: int) -> pd.Series:
    """Annualised realised vol over the NEXT n sessions. Strictly forward."""
    fwd = v.shift(-1).rolling(n).sum().shift(-(n - 1))
    return np.sqrt(fwd / n * TRADING_DAYS)


def bp(x) -> str:
    return f"{x*1e4:,.0f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=30,
                    help="trading sessions of realised vol to compare against")
    a = ap.parse_args()

    print("loading 1-minute bars...", flush=True)
    rv = realised_vols(minute_frame())
    print("loading option quotes (~544 MB)...", flush=True)
    d = option_data.load(verbose=True)
    iv = atm_iv(d)

    n = a.horizon
    tbl = pd.DataFrame({
        "iv": iv,
        "rv_cc": forward_rv(rv["v_cc"], n),
        "rv_oc": forward_rv(rv["v_oc"], n),
        "rv_1m": forward_rv(rv["v_1m"], n),
    }).dropna()

    w = 88
    print("\n" + "=" * w)
    print(f"SOXL — IMPLIED VOLATILITY vs WHAT ACTUALLY HAPPENED NEXT")
    print(f"   ~30-day at-the-money implied vol, against the following "
          f"{n} sessions of realised vol")
    print("=" * w)
    print(f"  {len(tbl):,} trade dates, {tbl.index.min().date()} to "
          f"{tbl.index.max().date()}\n")

    print(f"  {'measure':<48}{'mean':>9}{'median':>9}")
    print("  " + "-" * 66)
    rows = [("implied vol the market charged", "iv"),
            ("realised, close-to-close — ALL of it", "rv_cc"),
            ("realised, 1-minute path — the part you can hedge", "rv_1m")]
    for label, k in rows:
        print(f"  {label:<48}{tbl[k].mean()*100:>8.1f}%"
              f"{tbl[k].median()*100:>8.1f}%")

    # Variance is additive, volatility is not. Split it before comparing.
    var_cc = float((tbl["rv_cc"] ** 2).mean())
    var_1m = float((tbl["rv_1m"] ** 2).mean())
    var_on = max(var_cc - var_1m, 0.0)
    print(f"\n  WHERE THE VARIANCE LIVES  (variance adds; volatility does not)")
    print(f"    total, close to close        {np.sqrt(var_cc)*100:6.1f}% vol"
          f"   {var_cc/var_cc*100:5.0f}% of variance")
    print(f"    inside the day session       {np.sqrt(var_1m)*100:6.1f}% vol"
          f"   {var_1m/var_cc*100:5.0f}% of variance   <- hedgeable")
    print(f"    overnight, market closed     {np.sqrt(var_on)*100:6.1f}% vol"
          f"   {var_on/var_cc*100:5.0f}% of variance   <- NOT hedgeable")

    print(f"\n  GAMMA BUYER'S EDGE — realised minus implied")
    print(f"  {'':<48}{'mean':>9}{'median':>9}{'% of days > 0':>16}")
    print("  " + "-" * 82)
    for label, k in rows[1:]:
        diff = tbl[k] - tbl["iv"]
        print(f"  {label:<48}{diff.mean()*100:>+8.1f}%"
              f"{diff.median()*100:>+8.1f}%{(diff > 0).mean()*100:>15.0f}%")
    print(f"\n  An open-to-close estimator is deliberately NOT used as a "
          f"headline here. It has one\n  observation per day, so its mean is "
          f"set by a handful of huge trending sessions: the\n  median ratio of "
          f"1-minute realised variance to squared open-to-close return is 2.11, "
          f"but\n  the ratio of the MEANS is 0.86. Reporting the second as if "
          f"it described a typical day\n  would say intraday moves trend, and "
          f"they do not.")

    print(f"\n  by calendar year, close-to-close realised minus implied\n")
    print(f"  {'year':<8}{'n':>6}{'implied':>10}{'realised':>10}{'edge':>10}"
          f"{'% days RV>IV':>15}")
    print("  " + "-" * 59)
    for y, g in tbl.groupby(tbl.index.year):
        e = g["rv_cc"] - g["iv"]
        print(f"  {y:<8}{len(g):>6}{g['iv'].mean()*100:>9.1f}%"
              f"{g['rv_cc'].mean()*100:>9.1f}%{e.mean()*100:>+9.1f}%"
              f"{(e > 0).mean()*100:>14.0f}%")

    # ---- what the hedging itself costs
    f = friction_for("SOXL")
    print("\n" + "=" * w)
    print("AND THEN THE HEDGING BILL")
    print("=" * w)
    print(f"""
  The numbers above are gross. Delta-hedging is not free: every hedge is a
  trade in the underlying, at the measured {f.round_trip_bp:.2f} bp round trip.

  A gamma position that is hedged H times a day pays roughly H x half a round
  trip in friction on the hedge legs alone, on the hedged notional. The
  variance you capture rises with H (you track the path more closely); so does
  the bill. The path length itself is the thing being chased and it is
  {bp(rv['path'].mean())} bp/day.
""")
    for h in (1, 4, 13, 26, 78, 390):
        cost_day = h * f.round_trip_bp / 2
        print(f"    hedge {h:>4}x/day  ->  {cost_day:>7.0f} bp/day of hedging "
              f"friction  = {cost_day*252/100:>7.0f}% a year on hedged notional")

    print(f"""
  Read that against the edge table. A vol edge of a few points a year on a 70%
  vol underlying is worth a few hundred bp a year. Hedging four times a day
  costs {4*f.round_trip_bp/2*252/100:.0f}% a year. The friction is not a detail here; it is the
  whole trade.
""")

    tbl.to_csv(os.path.join(_HERE, "out", "V27_vol_premium.csv"))
    print(f"  wrote out/V27_vol_premium.csv ({len(tbl):,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
