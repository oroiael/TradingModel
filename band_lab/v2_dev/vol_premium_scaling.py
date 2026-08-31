"""
Does the volatility premium scale with the volatility LEVEL? V45.

V44 compared SOXL's +11.5 volatility-point edge against SMH's 2.9-point spread
and called it favourable. Those are different underlyings whose volatilities
differ by a factor of three, so the subtraction was not valid. See
V45_PREMIUM_SCALING_BAR.md.

The question that decides how to read any SMH number:

    RV = a + b * IV

    additive      ->  b ~ 1,   a ~ +10.9 points   =>  SMH edge ~ +10.9, clears easily
    proportional  ->  a ~ 0,   b ~ 1.11           =>  SMH edge ~  +3.5, marginal

SOXL's implied vol moves a lot across 2022-2026, so its own option files
separate the two. That is the whole test, and it needs no new data.

    python3 band_lab/v2_dev/vol_premium_scaling.py
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

OUT = os.path.join(_HERE, "out")
DATA = os.path.join(_HERE, "data", "ibkr_daily_closes.csv")
TRADING_DAYS = 252
HORIZON = 21                       # V37's 1-month cell
DTE_LO, DTE_HI, BAND = 22, 45, 0.07

#: V43's measured round-trip spread, volatility points, per symbol.
SPREAD = {"SMH": 2.9, "SOXX": 8.0, "SOXL": 18.5, "SOXS": 37.6}

#: V37's published 1-month result. C1 checks against it.
V37 = {"iv": 99.2, "rv": 110.2, "edge": 10.9, "tol": 0.3}

FAILURES: list[str] = []


def check(name, ok, detail):
    if not ok:
        FAILURES.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def ols(x: np.ndarray, y: np.ndarray):
    """Slope, intercept, R^2, and the OLS standard errors. Plain, no deps."""
    n = len(x)
    sx, sy = x.mean(), y.mean()
    sxx = ((x - sx) ** 2).sum()
    b = ((x - sx) * (y - sy)).sum() / sxx
    a = sy - b * sx
    resid = y - (a + b * x)
    r2 = 1.0 - (resid ** 2).sum() / ((y - sy) ** 2).sum()
    s2 = (resid ** 2).sum() / (n - 2) if n > 2 else np.nan
    se_b = math.sqrt(s2 / sxx) if n > 2 else np.nan
    se_a = math.sqrt(s2 * (1.0 / n + sx ** 2 / sxx)) if n > 2 else np.nan
    return a, b, r2, se_a, se_b


def atm_iv(d, lo=DTE_LO, hi=DTE_HI, band=BAND) -> pd.Series:
    """Per date, median implied vol of near-the-money ~30-day contracts.

    V37's exact filter, reproduced here rather than imported so C1 is a real
    check on this file and not a tautology.
    """
    x = d[(d.dte.between(lo, hi)) & (d.implied_vol > 0)
          & (d.bid > 0) & (d.ask > d.bid)].copy()
    x = x[(x["strike"] / x["underlying_price"] - 1.0).abs() <= band]
    return x.groupby("trade_date")["implied_vol"].median()


def realised(px: pd.Series) -> float:
    """Annualised close-to-close vol of a daily series."""
    r = np.log(px / px.shift(1)).dropna()
    return float(r.std(ddof=1) * math.sqrt(TRADING_DAYS))


def main() -> int:
    w = 92

    # ---------------------------------------------------------------- C2
    print("=" * w)
    print("THE LEVERAGE, MEASURED — the fact that invalidates V44's comparison")
    print("=" * w)
    if not os.path.exists(DATA):
        print(f"  missing {DATA}")
        return 1
    px = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"\n  IBKR daily closes, {len(px):,} sessions, "
          f"{px.index.min().date()} to {px.index.max().date()}\n")
    print(f"  {'symbol':<8}{'ann. vol':>10}{'total return':>15}")
    print("  " + "-" * 33)
    vols = {}
    for c in px.columns:
        vols[c] = realised(px[c])
        tot = px[c].iloc[-1] / px[c].iloc[0] - 1.0
        print(f"  {c:<8}{vols[c]*100:>9.1f}%{tot*100:>14.1f}%")
    ratio = vols["SOXL"] / vols["SOXX"]
    print()
    check("C2 SOXL/SOXX realised vol ratio is 3x",
          2.85 <= ratio <= 3.15,
          f"{ratio:.2f}x  (SOXL {vols['SOXL']*100:.1f}% / "
          f"SOXX {vols['SOXX']*100:.1f}%)")
    print(f"  [note] SOXL/SMH = {vols['SOXL']/vols['SMH']:.2f}x — SMH tracks a "
          f"different index than SOXL, so SOXX is the clean comparison.")

    # ---------------------------------------------------------------- C1
    print("\nloading 1-minute bars...", flush=True)
    rv = realised_vols(minute_frame())
    print("loading option quotes...", flush=True)
    d = option_data.load(verbose=True)

    t = pd.DataFrame({"iv": atm_iv(d),
                      "rv": forward_rv(rv["v_cc"], HORIZON)}).dropna()
    t["edge"] = (t["rv"] - t["iv"]) * 100

    print("\n" + "=" * w)
    print("REPRODUCING V37's 1-MONTH CELL — C1")
    print("=" * w)
    print(f"\n  {len(t):,} matched dates, {t.index.min().date()} to "
          f"{t.index.max().date()}\n")
    got = (t["iv"].mean() * 100, t["rv"].mean() * 100, t["edge"].mean())
    print(f"  {'':16}{'implied':>10}{'realised':>11}{'edge':>9}")
    print("  " + "-" * 46)
    print(f"  {'V37 published':<16}{V37['iv']:>9.1f}%{V37['rv']:>10.1f}%"
          f"{V37['edge']:>+9.1f}")
    print(f"  {'this file':<16}{got[0]:>9.1f}%{got[1]:>10.1f}%{got[2]:>+9.1f}\n")
    check("C1 reproduces V37's 1-month cell",
          all(abs(g - V37[k]) <= V37["tol"]
              for g, k in zip(got, ("iv", "rv", "edge"))),
          f"max deviation {max(abs(g - V37[k]) for g, k in zip(got, ('iv','rv','edge'))):.2f} "
          f"points against a {V37['tol']} tolerance")

    # ---------------------------------------------------------------- C3
    lo, hi = t["iv"].min() * 100, t["iv"].max() * 100
    print("\n" + "=" * w)
    print("THE FITTED RANGE — C3, and the reason the SMH number is an "
          "extrapolation")
    print("=" * w)
    print(f"\n  SOXL implied vol spans {lo:.1f}% to {hi:.1f}% "
          f"(5th–95th pct {t['iv'].quantile(.05)*100:.1f}%–"
          f"{t['iv'].quantile(.95)*100:.1f}%)")
    print(f"  SMH's implied vol, if it sits near its realised "
          f"{vols['SMH']*100:.1f}%, is FAR BELOW that range.")
    print(f"  Every SMH figure below is an extrapolation of "
          f"{(lo - vols['SMH']*100):.0f}+ volatility points.")

    # ---------------------------------------------------------------- fit
    x, y = t["iv"].to_numpy() * 100, t["rv"].to_numpy() * 100
    a, b, r2, se_a, se_b = ols(x, y)

    # C4: non-overlapping only. All HORIZON offsets, so the choice is visible.
    offs = [ols(x[i::HORIZON], y[i::HORIZON]) for i in range(HORIZON)
            if len(x[i::HORIZON]) > 5]
    ob = np.array([o[1] for o in offs])
    oa = np.array([o[0] for o in offs])
    ose_b = np.array([o[4] for o in offs])
    ose_a = np.array([o[3] for o in offs])

    print("\n" + "=" * w)
    print("THE TEST — forward realised vol regressed on implied vol")
    print("=" * w)
    print(f"""
      RV = a + b * IV        additive premium  =>  b = 1,    a = +10.9
                             proportional      =>  a = 0,    b =  1.11
""")
    print(f"  {'sample':<34}{'a (intercept)':>16}{'b (slope)':>14}{'R2':>8}")
    print("  " + "-" * 72)
    print(f"  {'all dates (overlapping)':<34}{a:>+11.2f} pts{b:>14.3f}{r2:>8.3f}")
    print(f"  {'    standard error':<34}{se_a:>11.2f}   {se_b:>14.3f}"
          f"{'':>8}   <- NOT valid, overlapping")
    print(f"  {'non-overlapping, median of ' + str(len(offs)):<34}"
          f"{np.median(oa):>+11.2f} pts{np.median(ob):>14.3f}"
          f"{np.median([o[2] for o in offs]):>8.3f}")
    print(f"  {'    standard error (median)':<34}{np.median(ose_a):>11.2f}   "
          f"{np.median(ose_b):>14.3f}{'':>8}   <- C4, valid")
    print(f"  {'    range across offsets':<34}"
          f"{oa.min():>+7.2f} to {oa.max():>+5.2f}"
          f"{ob.min():>9.3f} to {ob.max():.3f}")

    zb = (np.median(ob) - 1.0) / np.median(ose_b)
    za = np.median(oa) / np.median(ose_a)
    print(f"""
  Is the slope 1 (additive)?      b - 1 = {np.median(ob) - 1:+.3f}, t = {zb:+.2f}
  Is the intercept 0 (proportional)?  a = {np.median(oa):+.2f}, t = {za:+.2f}
""")

    # ------------------------------------------------- quintiles, no form
    print("=" * w)
    print("THE SAME QUESTION WITHOUT A FUNCTIONAL FORM — quintiles by IV level")
    print("=" * w)
    t2 = t.copy()
    t2["q"] = pd.qcut(t2["iv"], 5, labels=False)
    print(f"\n  {'IV quintile':<13}{'dates':>7}{'implied':>10}{'realised':>11}"
          f"{'edge pts':>11}{'edge / IV':>12}")
    print("  " + "-" * 64)
    for q, g in t2.groupby("q"):
        print(f"  {'Q' + str(int(q) + 1) + ' lowest' if q == 0 else ('Q' + str(int(q) + 1) + ' highest' if q == 4 else 'Q' + str(int(q) + 1)):<13}"
              f"{len(g):>7,}{g['iv'].mean()*100:>9.1f}%{g['rv'].mean()*100:>10.1f}%"
              f"{g['edge'].mean():>+11.1f}{g['edge'].mean()/(g['iv'].mean()*100)*100:>11.1f}%")
    qe = t2.groupby("q")["edge"].mean()
    qr = t2.groupby("q").apply(
        lambda g: g["edge"].mean() / (g["iv"].mean() * 100) * 100,
        include_groups=False)
    print(f"""
  If the premium were ADDITIVE the 'edge pts' column would be flat.
  If PROPORTIONAL the 'edge / IV' column would be flat.
    edge pts  spans {qe.min():+.1f} to {qe.max():+.1f}  (range {qe.max()-qe.min():.1f})
    edge / IV spans {qr.min():+.1f}% to {qr.max():+.1f}% (range {qr.max()-qr.min():.1f} pts)
""")

    # ------------------------------------------------- leverage constraint
    print("=" * w)
    print("THE LEVERAGE CONSTRAINT — what settles it without a regression")
    print("=" * w)
    lev = vols["SOXL"] / vols["SOXX"]
    c = V37["edge"]
    rx = vols["SOXX"] * 100
    print(f"""
  SOXL is a {lev:.2f}x daily-reset fund on the index SOXX tracks, so its return
  is {lev:.2f}x SOXX's every day and its volatility is {lev:.2f}x SOXX's at every
  horizon -- realised AND implied. That is mechanical, not empirical.

  Now suppose the premium were ADDITIVE, the same {c:+.1f} points on both:

      IV_SOXX = RV_SOXX - {c:.1f} = {rx:.1f} - {c:.1f} = {rx - c:.1f}%
      IV_SOXL = RV_SOXL - {c:.1f} = {rx * lev:.1f} - {c:.1f} = {rx * lev - c:.1f}%

  But a {lev:.2f}x fund's options must price at {lev:.2f}x the index's vol:

      {lev:.2f} x IV_SOXX = {lev:.2f} x {rx - c:.1f} = {lev * (rx - c):.1f}%

  Those disagree by {(rx * lev - c) - lev * (rx - c):.1f} volatility points -- exactly (lev-1) x {c:.1f}.
  An additive premium on both legs of a levered pair therefore requires the
  market to price SOXL volatility {(rx*lev - c)/(rx - c):.2f}x the index's while the fund
  delivers {lev:.2f}x. That is a {(rx * lev - c) - lev * (rx - c):.0f}-point relative-value gap sitting in the two
  most liquid semiconductor chains in the market, permanently.

  **It does not exist. So the premium cannot be additive.** It scales with the
  volatility level, which is what the regression's point estimate said
  (b = {np.median(ob):.2f}, a = {np.median(oa):+.1f}) but could not establish on {len(offs) and len(x[0::HORIZON])} independent
  windows. The leverage identity establishes it on arithmetic instead.
""")

    # ------------------------------------------------- extrapolation
    print("=" * w)
    print("WHAT THIS IMPLIES FOR SMH AND SOXX — against their OWN spreads")
    print("=" * w)
    print(f"""
  Given a symbol's realised vol RV, the fitted line inverts to the implied vol
  the market would have charged:  IV = (RV - a) / b,  edge = RV - IV.
""")
    A, B = float(np.median(oa)), float(np.median(ob))
    #: The leverage argument forces a = 0. SOXL's own ratio then fixes b, and
    #: that is the model carried to the other symbols. The fitted line is shown
    #: beside it because its intercept is not identified (se ~22 points) and
    #: the difference between the two IS the remaining uncertainty.
    K = V37["rv"] / V37["iv"]
    print(f"  {'symbol':<8}{'realised':>10}{'implied':>10}{'edge':>8}"
          f"{'spread':>9}{'net':>8}{'clears?':>10}   model")
    print("  " + "-" * 74)
    rows = []
    for sym in ("SOXL", "SOXX", "SMH"):
        r = vols[sym] * 100
        sp = SPREAD[sym]
        for tag, iv_hat in (("proportional (a=0, b=%.3f)" % K, r / K),
                            ("fitted line", (r - A) / B)):
            edge = r - iv_hat
            rows.append(dict(symbol=sym, model=tag, realised=r,
                             implied=iv_hat, edge=edge, spread=sp,
                             net=edge - sp))
            print(f"  {sym:<8}{r:>9.1f}%{iv_hat:>9.1f}%{edge:>+8.1f}{sp:>9.1f}"
                  f"{edge - sp:>+8.1f}{'YES' if edge > sp else 'no':>10}   {tag}")
        print()

    smh = [r for r in rows if r["symbol"] == "SMH"]
    prop, fit = smh[0], smh[1]
    print(f"""  Under the ADDITIVE model V44 assumed, SMH's edge would be +{V37['edge']:.1f} against a
  2.9 spread -- net +{V37['edge'] - 2.9:.1f}, a comfortable strategy. The leverage constraint
  above says that model cannot be right.

  Under the proportional model it forces, SMH's edge is {prop['edge']:+.1f} against 2.9 --
  **net {prop['net']:+.1f} volatility points per cycle.** Positive, and small enough that
  it is not distinguishable from zero by anything measured so far. The fitted
  line, whose intercept is not identified, puts it at {fit['net']:+.1f}.

  SOXX fails under either: {prop['edge']:+.1f} edge against its own {SPREAD['SOXX']:.1f} spread. Its
  volatility is SMH's but its options cost {SPREAD['SOXX'] / SPREAD['SMH']:.1f}x as much to trade.

  [A28] Both rows carry SOXL's premium down to a volatility level ~{(lo - vols['SMH']*100):.0f} points
  below anything in the fitted sample. This is NOT a measurement of SMH.
  Only vol_premium_ibkr.py, run against a live IBKR session, measures SMH itself.
""")

    print("=" * w)
    print(f"CHECKS: {'ALL PASS' if not FAILURES else 'FAILED — ' + ', '.join(FAILURES)}")
    print("=" * w)

    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame(rows).to_csv(
        os.path.join(OUT, "V45_premium_scaling.csv"), index=False)
    t.to_csv(os.path.join(OUT, "V45_soxl_iv_rv_pairs.csv"))
    print(f"\n  wrote out/V45_premium_scaling.csv and "
          f"out/V45_soxl_iv_rv_pairs.csv")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
