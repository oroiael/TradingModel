"""
How often does UVXY sit or move 2 standard deviations from its 30-day mean?

The question has two honest readings and they give different answers, so
both are measured:

  A. **Band excursion** (the Bollinger reading). Is the CLOSE outside
     SMA30 +/- 2*SD30? This is "2 sd around the 30-day mean" read literally
     — a statement about the price *level*.

  B. **Return shock.** Is the DAY'S MOVE bigger than 2x the trailing 30-day
     standard deviation of daily returns? This is "swing" read as motion.

Windows are 30 **trading** days throughout.

Two traps this module is built around:

  1. **The drift.** UVXY falls ~68%/yr, so a trailing mean of a declining
     series sits above the price far more often than below it. A naive band
     count is therefore asymmetric for a reason that has nothing to do with
     volatility. Both raw and detrended versions are reported.

  2. **Normality.** The textbook expectation for |z| > 2 is 4.55%. UVXY is
     violently non-normal and the two tails are nothing like each other, so
     a single number for "2 sigma" hides the entire point.

Run:
    python3 vix_lab/two_sigma.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
from dq_uvxy import load_raw  # noqa: E402
from fetch_refs import load as load_ref  # noqa: E402

OUT = os.path.join(_HERE, "out")
N = 30                      # trading days
NORMAL_TWO_TAIL = 0.0455    # P(|z| > 2) under a normal


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


def daily_close(sym: str) -> pd.Series:
    df = load_raw(os.path.join(ROOT, f"{sym}_1min.csv"))
    return df.groupby("date")["Close"].last()


def zscore(px: pd.Series, n: int = N, log: bool = False) -> pd.Series:
    """(x - rolling mean) / rolling sd, on price or log price."""
    x = np.log(px) if log else px
    return (x - x.rolling(n).mean()) / x.rolling(n).std()


def _detrend_last(w: np.ndarray) -> float:
    """Residual of the window's last point from a linear fit, in residual sd."""
    t = np.arange(len(w), dtype=float)
    slope, intercept = np.polyfit(t, w, 1)
    resid = w - (intercept + slope * t)
    sd = resid.std(ddof=1)
    return resid[-1] / sd if sd else np.nan


def zscore_detrended(px: pd.Series, n: int = N) -> pd.Series:
    """How far the close sits from its own 30-day *trend*, in residual sd.

    The plain band measures distance from a flat mean, which for a series
    falling 68%/yr is dominated by the fall itself rather than by any
    excursion. Fitting the trend inside the window and z-scoring the residual
    asks the question the band was meant to ask.
    """
    return np.log(px).rolling(n).apply(_detrend_last, raw=True)


# -------------------------------------------------------- A. band excursion
def band(px: pd.Series, label: str) -> pd.Series:
    z = zscore(px, log=True)
    v = z.dropna()
    hi, lo = (v > 2).mean(), (v < -2).mean()
    print(f"{label:<22}{len(v):>7}{hi + lo:>10.2%}{hi:>10.2%}{lo:>10.2%}"
          f"{(hi + lo) / NORMAL_TWO_TAIL:>10.2f}")
    return z


def section_band() -> dict:
    hdr("A. Band excursion — is the close outside SMA30 +/- 2 sd?")
    print("Computed on LOG price (a multiplicative series should be banded")
    print("multiplicatively). 30 trading days. 'x normal' compares the total")
    print("to the 4.55% a Gaussian would give.\n")
    print(f"{'series':<22}{'n':>7}{'|z|>2':>10}{'z>+2':>10}{'z<-2':>10}"
          f"{'x normal':>10}")
    zs = {}
    for sym in ("UVXY", "SOXL", "SOXS"):
        zs[sym] = band(daily_close(sym), sym)
    for sym in ("VIXY", "SPY"):
        zs[sym] = band(load_ref(sym)["Close"], sym)

    print("\nUVXY on RAW price rather than log, for comparison:")
    print(f"{'series':<22}{'n':>7}{'|z|>2':>10}{'z>+2':>10}{'z<-2':>10}"
          f"{'x normal':>10}")
    u = daily_close("UVXY")
    zr = zscore(u, log=False).dropna()
    print(f"{'UVXY (raw price)':<22}{len(zr):>7}"
          f"{((zr.abs() > 2).mean()):>10.2%}{(zr > 2).mean():>10.2%}"
          f"{(zr < -2).mean():>10.2%}"
          f"{(zr.abs() > 2).mean() / NORMAL_TWO_TAIL:>10.2f}")

    print("\nBoth of the above measure distance from a FLAT 30-day mean, which")
    print("for a series falling 68%/yr is dominated by the fall itself. Fitting")
    print("the trend inside the window and z-scoring the residual asks what the")
    print("band was meant to ask -- is today unusual *given* the downtrend:\n")
    zd = zscore_detrended(u).dropna()
    print(f"{'series':<22}{'n':>7}{'|z|>2':>10}{'z>+2':>10}{'z<-2':>10}"
          f"{'x normal':>10}")
    print(f"{'UVXY (detrended)':<22}{len(zd):>7}"
          f"{(zd.abs() > 2).mean():>10.2%}{(zd > 2).mean():>10.2%}"
          f"{(zd < -2).mean():>10.2%}"
          f"{(zd.abs() > 2).mean() / NORMAL_TWO_TAIL:>10.2f}")
    return zs


# ---------------------------------------------------------- B. return shock
def section_shock() -> dict:
    hdr("B. Return shock — is the day's MOVE bigger than 2x trailing 30d sd?")
    print("sigma is the standard deviation of the prior 30 daily log returns,")
    print("known before the day starts. No lookahead.\n")
    print(f"{'series':<22}{'n':>7}{'|r|>2s':>10}{'r>+2s':>10}{'r<-2s':>10}"
          f"{'x normal':>10}{'max |r|/s':>11}")
    out = {}
    series = {s: daily_close(s) for s in ("UVXY", "SOXL", "SOXS")}
    series.update({s: load_ref(s)["Close"] for s in ("VIXY", "SPY")})
    for sym, px in series.items():
        r = np.log(px).diff()
        s = r.rolling(N).std().shift(1)
        k = (r / s).dropna()
        out[sym] = k
        print(f"{sym:<22}{len(k):>7}{(k.abs() > 2).mean():>10.2%}"
              f"{(k > 2).mean():>10.2%}{(k < -2).mean():>10.2%}"
              f"{(k.abs() > 2).mean() / NORMAL_TWO_TAIL:>10.2f}"
              f"{k.abs().max():>11.1f}")

    k = out["UVXY"]
    print("\nUVXY, how far into the tail it actually goes:")
    print(f"{'threshold':<14}{'count':>8}{'frequency':>12}{'1 per N days':>14}"
          f"{'normal':>10}")
    from math import erfc, sqrt
    for t in (1, 2, 3, 4, 5, 6):
        f = (k.abs() > t).mean()
        norm = erfc(t / sqrt(2))
        print(f"{f'|r| > {t} sigma':<14}{int((k.abs() > t).sum()):>8}"
              f"{f:>12.2%}{(1 / f if f else np.inf):>14.0f}{norm:>10.2%}")

    print("\nSplit by direction — this is the whole character of the")
    print("instrument, and a single '2 sigma' number destroys it:")
    print(f"{'threshold':<14}{'up count':>10}{'down count':>12}{'ratio':>8}")
    for t in (2, 3, 4, 5):
        up, dn = int((k > t).sum()), int((k < -t).sum())
        print(f"{f'{t} sigma':<14}{up:>10}{dn:>12}"
              f"{(up / dn if dn else np.inf):>8.1f}")
    print("\nUVXY's tail is one-sided: big moves are UP. Volatility spikes")
    print("and bleeds, it does not crash.")
    return out


# ------------------------------------------------------------ C. clustering
def section_cluster(k: pd.Series) -> None:
    hdr("C. Are these independent? No — they cluster hard")
    ev = (k.abs() > 2)
    p = ev.mean()
    cond = ev[ev.shift(1).fillna(False)].mean()
    cond5 = ev[ev.shift(1).rolling(5).max().fillna(0).astype(bool)].mean()
    print(f"  unconditional P(2-sigma day)            {p:.2%}")
    print(f"  P(2-sigma | yesterday was one)          {cond:.2%}"
          f"   ({cond / p:.1f}x)")
    print(f"  P(2-sigma | one in the last 5 days)     {cond5:.2%}"
          f"   ({cond5 / p:.1f}x)")

    runs, cur = [], 0
    for x in ev:
        if x:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    print(f"\n  {len(runs)} separate episodes over {len(ev)} sessions")
    print(f"  longest consecutive run                 {max(runs)} sessions")
    print(f"  mean episode length                     {np.mean(runs):.2f}")
    print(f"  episodes of 1 day only                  "
          f"{sum(1 for r in runs if r == 1)} of {len(runs)}")

    print("\n  Gaps between episodes (trading days):")
    idx = np.where(ev.to_numpy())[0]
    starts = [idx[0]] + [b for a, b in zip(idx, idx[1:]) if b - a > 1]
    gaps = np.diff(starts)
    print(f"    median {np.median(gaps):.0f}   mean {gaps.mean():.0f}   "
          f"max {gaps.max()}   min {gaps.min()}")

    print("\n  By calendar year:")
    print(f"{'  year':<10}{'sessions':>10}{'2-sigma days':>14}{'rate':>9}")
    for y, g in ev.groupby(ev.index.year):
        print(f"{'  ' + str(y):<10}{len(g):>10}{int(g.sum()):>14}"
              f"{g.mean():>9.2%}")


# ------------------------------------------------------------- D. aftermath
def section_after(k: pd.Series, z: pd.Series) -> None:
    hdr("D. What happens next — the reason to ask in the first place")
    px = daily_close("UVXY")
    lp = np.log(px)
    print("Forward log return after a 2-sigma day, against the unconditional")
    print("mean of the same sample. A tradeable edge would show a large,")
    print("consistent difference.\n")
    print("**The h=1 t-stats are honest; the h=5 and h=20 ones are NOT.** Those")
    print("windows overlap 5:1 and 20:1 and their t-stats are inflated by")
    print("roughly sqrt(h) — DRIVERS.md §1 shows what that does. Read h=20")
    print("for the sign and the size, never for the significance.\n")
    print(f"{'condition':<26}{'n':>6}{'h=1':>9}{'t':>7}{'h=5':>9}{'t':>7}"
          f"{'h=20':>10}{'t':>7}")
    conds = {
        "all days": pd.Series(True, index=lp.index),
        "after r > +2 sigma": (k > 2).reindex(lp.index).fillna(False),
        "after r < -2 sigma": (k < -2).reindex(lp.index).fillna(False),
        "close above upper band": (z > 2).reindex(lp.index).fillna(False),
        "close below lower band": (z < -2).reindex(lp.index).fillna(False),
    }
    for name, m in conds.items():
        row = f"{name:<26}{int(m.sum()):>6}"
        for h in (1, 5, 20):
            fwd = (lp.shift(-h) - lp).reindex(lp.index)
            g = fwd[m].dropna()
            t = g.mean() / (g.std() / np.sqrt(len(g))) if len(g) > 2 and g.std() else np.nan
            row += f"{g.mean() * 1e4:>+9.0f}{t:>7.2f}"
        print(row)
    print("\nRead the 'all days' row as the ruler: every other row has to beat")
    print("it, not zero. UVXY loses money on an average day by construction.")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    zs = section_band()
    ks = section_shock()
    section_cluster(ks["UVXY"])
    section_after(ks["UVXY"], zs["UVXY"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
