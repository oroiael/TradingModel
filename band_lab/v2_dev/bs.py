"""
Black-Scholes, and a check that the option file's own greeks agree with it.

Nothing in the straddle study should trust the vendor's `delta` and
`implied_vol` columns without evidence, because the whole strategy is a hedge
ratio applied to a volatility difference. If the vendor's delta is computed
against a spot price from a different moment than its bid/ask, the hedge is
wrong every single day and the study measures nothing.

    python3 band_lab/v2_dev/bs.py      # the agreement check
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

SQRT2 = math.sqrt(2.0)


def _ncdf(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x, float) / SQRT2))


def _npdf(x):
    return np.exp(-0.5 * np.asarray(x, float) ** 2) / math.sqrt(2 * math.pi)


def d1d2(S, K, T, r, q, sig):
    S, K, T, sig = (np.asarray(v, float) for v in (S, K, T, sig))
    with np.errstate(divide="ignore", invalid="ignore"):
        v = sig * np.sqrt(T)
        a = (np.log(S / K) + (r - q + 0.5 * sig ** 2) * T) / v
    return a, a - v


def price(S, K, T, r, q, sig, right):
    """European price. American early exercise is ignored — see MODEL_NOTES."""
    a, b = d1d2(S, K, T, r, q, sig)
    df, dq = np.exp(-r * np.asarray(T, float)), np.exp(-q * np.asarray(T, float))
    if right == "CALL":
        return S * dq * _ncdf(a) - K * df * _ncdf(b)
    return K * df * _ncdf(-b) - S * dq * _ncdf(-a)


def delta(S, K, T, r, q, sig, right):
    a, _ = d1d2(S, K, T, r, q, sig)
    dq = np.exp(-q * np.asarray(T, float))
    return dq * _ncdf(a) if right == "CALL" else dq * (_ncdf(a) - 1.0)


def vega(S, K, T, r, q, sig):
    """Per 1.00 of volatility, matching the option files' convention."""
    a, _ = d1d2(S, K, T, r, q, sig)
    return (np.asarray(S, float) * np.exp(-q * np.asarray(T, float))
            * _npdf(a) * np.sqrt(np.asarray(T, float)))


def gamma(S, K, T, r, q, sig):
    a, _ = d1d2(S, K, T, r, q, sig)
    S, T, sig = (np.asarray(v, float) for v in (S, T, sig))
    return np.exp(-q * T) * _npdf(a) / (S * sig * np.sqrt(T))


def implied_vol(px, S, K, T, r, q, right, lo=0.01, hi=6.0, tol=1e-6, it=100):
    """Bisection. Slower than Newton and it cannot diverge, which matters more.

    Returns NaN where the price is outside the no-arbitrage band rather than
    returning a boundary value that would look like a real measurement.
    """
    px, S, K, T = (np.asarray(v, float) for v in (px, S, K, T))
    lo_v = np.full(px.shape, lo)
    hi_v = np.full(px.shape, hi)
    p_lo = price(S, K, T, r, q, lo_v, right)
    p_hi = price(S, K, T, r, q, hi_v, right)
    bad = (px < p_lo - 1e-9) | (px > p_hi + 1e-9) | (T <= 0)
    for _ in range(it):
        mid = 0.5 * (lo_v + hi_v)
        p = price(S, K, T, r, q, mid, right)
        up = p < px
        lo_v = np.where(up, mid, lo_v)
        hi_v = np.where(up, hi_v, mid)
        if np.nanmax(hi_v - lo_v) < tol:
            break
    out = 0.5 * (lo_v + hi_v)
    return np.where(bad, np.nan, out)


# --------------------------------------------------------------------- check
def main() -> int:
    import pandas as pd
    import option_data

    print("loading 2026 option quotes...", flush=True)
    d = option_data.load(years=("2026",), verbose=False,
                         extra=("vega", "gamma", "theta"))
    d = d[(d.bid > 0) & (d.ask > d.bid) & (d.implied_vol > 0)
          & (d.dte.between(7, 120))].copy()
    d = d.sample(min(40000, len(d)), random_state=0)
    T = d["dte"].to_numpy(float) / 365.0
    S = d["underlying_price"].to_numpy(float)
    K = d["strike"].to_numpy(float)
    px = d["mid"].to_numpy(float)

    print("=" * 84)
    print("DOES THE FILE'S IMPLIED VOL AGREE WITH BLACK-SCHOLES ON ITS OWN "
          "QUOTED PRICES?")
    print("=" * 84)
    print(f"  {len(d):,} quotes, 7-120 DTE, two-sided, 2026\n")
    print(f"  {'r':>6}{'q':>6}   {'median |my IV - file IV|':>26}"
          f"{'  within 1 vol pt':>18}{'  within 3':>12}")
    print("  " + "-" * 74)
    best = None
    for r in (0.0, 0.02, 0.04, 0.05):
        for q in (0.0, 0.01, 0.02):
            iv = np.full(len(d), np.nan)
            for right in ("CALL", "PUT"):
                m = (d["right"] == right).to_numpy()
                iv[m] = implied_vol(px[m], S[m], K[m], T[m], r, q, right)
            err = np.abs(iv - d["implied_vol"].to_numpy(float))
            med = np.nanmedian(err)
            w1 = np.nanmean(err < 0.01)
            w3 = np.nanmean(err < 0.03)
            if best is None or med < best[0]:
                best = (med, r, q, iv, err)
            print(f"  {r:>6.2f}{q:>6.2f}   {med*100:>25.2f}"
                  f"{w1*100:>17.0f}%{w3*100:>11.0f}%")

    med, r, q, iv, err = best
    print(f"\n  best fit: r = {r:.2f}, q = {q:.2f}, median disagreement "
          f"{med*100:.2f} vol points")

    ok = med < 0.02
    print(f"\n  [{'PASS' if ok else 'FAIL'}] the file's implied vol is "
          f"reproducible from its own bid/ask and its own")
    print(f"         underlying_price. That is the evidence that the quote and "
          f"the spot are from the")
    print(f"         same moment. If they were hours apart this would not "
          f"close.")

    # delta agreement matters more than IV agreement: it IS the hedge ratio
    dl = np.full(len(d), np.nan)
    for right in ("CALL", "PUT"):
        m = (d["right"] == right).to_numpy()
        dl[m] = delta(S[m], K[m], T[m], r, q,
                      d["implied_vol"].to_numpy(float)[m], right)
    derr = np.abs(dl - d["delta"].to_numpy(float))
    print(f"\n  DELTA — the number the hedge actually uses")
    print(f"    median |my delta - file delta|  {np.nanmedian(derr):.4f}")
    print(f"    within 0.01                     {np.nanmean(derr < 0.01)*100:.0f}%")
    print(f"    within 0.02                     {np.nanmean(derr < 0.02)*100:.0f}%")
    dok = np.nanmedian(derr) < 0.01
    print(f"    [{'PASS' if dok else 'FAIL'}]")

    vg = vega(S, K, T, r, q, d["implied_vol"].to_numpy(float))
    verr = np.abs(vg - d["vega"].to_numpy(float)) / np.maximum(d["vega"], 1e-9)
    print(f"\n  VEGA — confirms the per-1.00-of-vol convention independently")
    print(f"    median relative error {np.nanmedian(verr)*100:.1f}%")
    return 0 if (ok and dok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
