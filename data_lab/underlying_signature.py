#!/usr/bin/env python3
"""
underlying_signature.py  --  NEUTRAL statistical fingerprint of the SOXL underlying.

No strategy assumed. We ask the data: what kind of process is this? A 3x
daily-rebalanced ETF has mechanical properties (volatility drag, path dependence,
end-of-day rebalancing flows) on top of the semis it tracks -- this quantifies the
signature those forces leave, which is what should dictate the strategy class.

Measures, daily (2022-2026) unless noted:
  1. return distribution & fat tails (moments, tail frequencies)
  2. volatility DRAG (arithmetic vs geometric) -- the leverage tax, in $ terms
  3. MEAN-REVERSION vs MOMENTUM by horizon: return autocorrelation + Lo-MacKinlay
     variance ratios (VR>1 trending, VR<1 reverting) with robust z-stats
  4. volatility CLUSTERING & persistence (ACF of |r|) and the leverage effect
     (returns vs next-period volatility)
  5. tail mean-reversion: what follows big up/down days
Outputs a printed report + outputs/underlying_signature.png.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import load_options, underlying_daily_from_options  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 200)
ANN = 252


def hr(t): print("\n" + "=" * 84 + f"\n{t}\n" + "=" * 84)


def variance_ratio(r, q):
    """Lo-MacKinlay VR(q) with heteroskedasticity-robust z-stat. r = log returns."""
    r = np.asarray(r); n = len(r)
    mu = r.mean()
    var1 = np.sum((r - mu) ** 2) / (n - 1)
    # overlapping q-sums
    qsum = np.convolve(r, np.ones(q), "valid")           # length n-q+1
    m = q * (n - q + 1) * (1 - q / n)
    varq = np.sum((qsum - q * mu) ** 2) / m
    vr = varq / var1     # varq already per-period via m; VR≈1 under a random walk
    # robust z (heteroskedasticity-consistent)
    phi = 0.0
    for k in range(1, q):
        dk = ((r[k:] - mu) ** 2) @ ((r[:-k] - mu) ** 2)
        delta = dk / (np.sum((r - mu) ** 2) ** 2 / n)
        phi += (2 * (q - k) / q) ** 2 * delta
    z = (vr - 1) / np.sqrt(phi) if phi > 0 else np.nan
    return vr, z


def hurst_via_vr(r):
    """Hurst from the VR scaling: VR(q) ~ q^(2H-1) -> slope of log VR vs log q."""
    qs = [2, 4, 8, 16, 32]
    vrs = [variance_ratio(r, q)[0] for q in qs]
    b = np.polyfit(np.log(qs), np.log(np.array(vrs) * np.array(qs)), 1)[0]  # log(varq) vs log q
    return b / 2.0                                                          # H


def acf(x, lags):
    x = np.asarray(x) - np.mean(x)
    denom = np.sum(x * x)
    return [float(np.sum(x[k:] * x[:-k]) / denom) for k in lags]


def main():
    hr("LOAD daily underlying 2022-2026")
    u = underlying_daily_from_options(load_options())
    u = u.sort_values("trade_date").reset_index(drop=True)
    p = u["close"].values
    r = np.diff(np.log(p))                                   # daily log returns
    n = len(r)
    dates = u["trade_date"].values[1:]
    print(f"{n} daily returns, {u['trade_date'].min().date()} -> {u['trade_date'].max().date()}")

    # ---------------------------------------------------------------- 1 distribution
    hr("1.  RETURN DISTRIBUTION & FAT TAILS (daily)")
    from scipy import stats as ss
    sd = r.std(ddof=1)
    print(f"  ann. return (geo) {(np.exp(r.sum())**(ANN/n)-1):+.1%}   ann. vol {sd*np.sqrt(ANN):.0%}")
    print(f"  daily mean {r.mean():+.4f}   std {sd:.4f}   "
          f"skew {ss.skew(r):+.2f}   excess kurtosis {ss.kurtosis(r):+.1f}  (normal=0)")
    for thr in (0.05, 0.10, 0.15, 0.20):
        exp_norm = 2 * ss.norm.sf(thr / sd)
        print(f"  |daily move| > {thr:.0%}: actual {np.mean(np.abs(r)>thr):5.1%}   "
              f"vs {exp_norm:6.2%} if normal   (x{np.mean(np.abs(r)>thr)/max(exp_norm,1e-9):.0f} fatter)")
    print(f"  worst day {r.min():.1%}   best day {r.max():+.1%}")

    # ---------------------------------------------------------------- 2 vol drag
    hr("2.  VOLATILITY DRAG  (the leverage tax: arithmetic vs geometric)")
    R = p[1:] / p[:-1] - 1.0                              # SIMPLE daily returns
    arith_ann = R.mean() * ANN
    geo_ann = (p[-1] / p[0]) ** (ANN / n) - 1
    drag = arith_ann - geo_ann
    print(f"  arithmetic mean of daily returns -> {arith_ann:+.1%}/yr  (what you'd get with NO compounding drag)")
    print(f"  geometric (actual compounded)    -> {geo_ann:+.1%}/yr  (what you ACTUALLY earned)")
    print(f"  DRAG = arithmetic - geometric    -> {drag:.1%}/yr  bled to volatility (theory ~0.5*sig^2 = {0.5*sd**2*ANN:.0%})")
    print(f"  meaning: SOXL must earn ~{arith_ann:+.0%}/yr in raw daily edge just to net {geo_ann:+.0%}. Choppiness is the enemy.")

    # ---------------------------------------------------------------- 3 revert/trend
    hr("3.  MEAN-REVERSION vs MOMENTUM by horizon")
    print("  return autocorrelation (｜z｜>2 ~ significant; +=momentum, -=reversal):")
    lags = list(range(1, 11))
    ac = acf(r, lags); band = 1.96 / np.sqrt(n)
    for k, a in zip(lags, ac):
        flag = "  <-- " + ("MOMENTUM" if a > 0 else "REVERSAL") if abs(a) > band else ""
        print(f"    lag {k:2d} day: {a:+.3f}{flag}")
    print(f"    (95% band +/-{band:.3f})")
    print("\n  Variance ratios VR(q)  (>1 trending, <1 mean-reverting; z robust):")
    for q in (2, 3, 5, 10, 20):
        vr, z = variance_ratio(r, q)
        tag = "trend" if vr > 1 else "revert"
        sig = "*" if abs(z) > 1.96 else " "
        print(f"    VR({q:2d}) = {vr:.2f}  z={z:+.1f}{sig}  -> {tag}")
    print(f"\n  Hurst exponent (0.5=random walk, >0.5 trend, <0.5 revert): {hurst_via_vr(r):.2f}")

    # ---------------------------------------------------------------- 4 vol clustering
    hr("4.  VOLATILITY CLUSTERING & LEVERAGE EFFECT")
    aac = acf(np.abs(r), list(range(1, 21)))
    print("  ACF of |returns| (vol clustering) at lags 1,2,3,5,10,20:")
    for k in (1, 2, 3, 5, 10, 20):
        print(f"    lag {k:2d}: {aac[k-1]:+.3f}")
    print(f"  -> |r| autocorrelation stays positive & decays slowly = strong vol persistence")
    # leverage effect: today's return vs tomorrow's abs return (vol)
    lev = np.corrcoef(r[:-1], np.abs(r[1:]))[0, 1]
    dn = r[:-1] < 0
    print(f"\n  leverage effect: corr(return_t, |return_t+1|) = {lev:+.2f} "
          f"(negative = vol rises more after DOWN moves)")
    print(f"    avg |next-day move| after DOWN day {np.abs(r[1:])[dn].mean():.2%}  "
          f"vs after UP day {np.abs(r[1:])[~dn].mean():.2%}")

    # ---------------------------------------------------------------- 5 tail reversion
    hr("5.  WHAT FOLLOWS BIG DAYS  (tail mean-reversion / continuation)")
    for thr, lbl in [(-0.10, "big DOWN (< -10%)"), (0.10, "big UP (> +10%)")]:
        if thr < 0:
            mask = r[:-1] < thr
        else:
            mask = r[:-1] > thr
        nxt = r[1:][mask]
        if len(nxt) > 3:
            print(f"  day after {lbl:18s} (n={len(nxt):3d}): next-day mean {nxt.mean():+.2%}  "
                  f"win {np.mean(nxt>0):.0%}  (unconditional mean {r.mean():+.2%})")

    _plot(r, dates, aac, band)
    print(f"\nsaved {OUT/'underlying_signature.png'}")


def _plot(r, dates, aac, band):
    from scipy import stats as ss
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    # return dist vs normal
    ax[0, 0].hist(r, bins=80, density=True, alpha=0.6, color="tab:blue")
    xs = np.linspace(r.min(), r.max(), 200)
    ax[0, 0].plot(xs, ss.norm.pdf(xs, r.mean(), r.std()), "r-", label="normal")
    ax[0, 0].set_yscale("log"); ax[0, 0].set_title("daily return distribution (log y) — fat tails")
    ax[0, 0].legend()
    # return acf
    lags = list(range(1, 16)); a = acf(r, lags)
    ax[0, 1].bar(lags, a, color=["tab:red" if abs(v) > band else "gray" for v in a])
    ax[0, 1].axhline(band, ls="--", c="k", lw=.6); ax[0, 1].axhline(-band, ls="--", c="k", lw=.6)
    ax[0, 1].set_title("return autocorrelation (momentum + / reversal -)")
    # vol clustering acf
    ax[1, 0].bar(range(1, 21), aac, color="tab:green")
    ax[1, 0].set_title("ACF of |returns| — volatility clustering (persistence)")
    # price path
    ax[1, 1].plot(pd.to_datetime(dates), np.exp(np.cumsum(r)))
    ax[1, 1].set_yscale("log"); ax[1, 1].set_title("SOXL path (log)")
    fig.tight_layout(); fig.savefig(OUT / "underlying_signature.png", dpi=110)


if __name__ == "__main__":
    main()
