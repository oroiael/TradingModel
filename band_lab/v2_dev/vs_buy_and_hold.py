"""
Is the strategy better than just owning the thing it trades?

Compares, over one identical window and from the same price files:

  - the strategy on the corrected simulator (SOXL sleeve, and the pair)
  - buy and hold SOXX, the unlevered semiconductor index ETF
  - buy and hold SOXL, the 3x instrument the strategy actually buys

**What is NOT here: the S&P 500.** The repository's SPY/SPX/SPXL files are Git
LFS pointers and the LFS budget on the remote is exhausted, so there is no S&P
price series on this machine. Rather than quote a number from memory next to
numbers computed from real files, it is left out. Drop a SPY daily CSV in the
repo root and this will pick it up.

    python3 band_lab/v2_dev/vs_buy_and_hold.py
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
ROOT = os.path.dirname(_BAND_LAB)
for _p in (_HERE, os.path.join(_BAND_LAB, "live"),
           os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soxl_only import sleeve_daily                                   # noqa: E402

SLEEVES = ("SOXL", "SOXS")
START = pd.Timestamp("2022-01-01")


def daily_closes(symbol):
    """Session closes from the 5-minute file. Real prices, not adjusted."""
    path = os.path.join(ROOT, f"{symbol}_5min_6Years.csv")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        if fh.read(40).startswith(b"version https://git-lfs"):
            return None                       # LFS pointer, not data
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    df = df.assign(dt=dt, date=dt.dt.normalize()).sort_values("dt")
    return df.groupby("date")["Close"].last()


def metrics(daily, label, exposure_note=""):
    d = daily.dropna()
    if not len(d):
        return None
    yrs = (d.index[-1] - d.index[0]).days / 365.25
    eq = (1.0 + d).cumprod()
    total = eq.iloc[-1] - 1.0
    cagr = (1.0 + total) ** (1.0 / yrs) - 1.0
    per_yr = len(d) / yrs
    vol = d.std(ddof=1) * math.sqrt(per_yr)
    sem = d.std(ddof=1) / math.sqrt(len(d))
    t = d.mean() / sem if sem else float("nan")
    return dict(label=label, cagr=cagr * 100, vol=vol * 100,
                sharpe=(d.mean() / d.std(ddof=1) * math.sqrt(per_yr)
                        if d.std(ddof=1) else float("nan")),
                mdd=float((eq / eq.cummax() - 1).min()) * 100,
                total=total * 100, t=t, n=len(d), note=exposure_note)


def main() -> int:
    argparse.ArgumentParser(description="strategy vs buy and hold").parse_args()

    strat = {s: sleeve_daily(s) for s in SLEEVES}
    cal = pd.DatetimeIndex(sorted(set(strat["SOXL"].index)
                                  | set(strat["SOXS"].index)))
    lo, hi = cal[0], cal[-1]

    books = []
    soxl_half = 0.5 * strat["SOXL"].reindex(cal).fillna(0.0)
    pair = sum(0.5 * strat[s].reindex(cal).fillna(0.0) for s in SLEEVES)
    books.append(metrics(soxl_half, "STRATEGY  SOXL sleeve, w=0.5",
                         f"{strat['SOXL'].notna().sum()} days in market"))
    books.append(metrics(pair, "STRATEGY  SOXL+SOXS, w=0.5 each", ""))

    for sym in ("SOXX", "SOXL"):
        c = daily_closes(sym)
        if c is None:
            books.append(dict(label=f"BUY+HOLD  {sym}", cagr=float("nan"),
                              vol=float("nan"), sharpe=float("nan"),
                              mdd=float("nan"), total=float("nan"),
                              t=float("nan"), n=0,
                              note="file is an LFS pointer, no data"))
            continue
        c = c[(c.index >= lo) & (c.index <= hi)]
        books.append(metrics(c.pct_change().dropna(), f"BUY+HOLD  {sym}",
                             "every day, overnight included"))

    spy = daily_closes("SPY")
    if spy is not None:
        spy = spy[(spy.index >= lo) & (spy.index <= hi)]
        books.append(metrics(spy.pct_change().dropna(), "BUY+HOLD  SPY", ""))

    w = 96
    print("=" * w)
    print(f"SAME WINDOW: {lo.date()} to {hi.date()}   "
          f"({(hi - lo).days / 365.25:.2f} years)")
    print("=" * w)
    print(f"{'book':<36}{'CAGR':>9}{'vol':>8}{'Sharpe':>8}{'maxDD':>9}"
          f"{'total':>10}{'t':>7}")
    for b in books:
        if b is None:
            continue
        if b["n"] == 0:
            print(f"{b['label']:<36}{'--':>9}{'--':>8}{'--':>8}{'--':>9}"
                  f"{'--':>10}{'--':>7}   {b['note']}")
            continue
        print(f"{b['label']:<36}{b['cagr']:>+8.1f}%{b['vol']:>7.1f}%"
              f"{b['sharpe']:>8.2f}{b['mdd']:>8.1f}%{b['total']:>+9.1f}%"
              f"{b['t']:>7.2f}")

    print("\n  SPY / S&P 500 is absent: the repo's index files are LFS pointers "
          "and the\n  remote's LFS budget is exhausted. No number is quoted for "
          "it rather than\n  putting a remembered figure beside measured ones.")

    # ---- the comparison that actually decides it: you can just hold less.
    soxx = daily_closes("SOXX")
    if soxx is not None:
        r = soxx[(soxx.index >= lo) & (soxx.index <= hi)].pct_change().dropna()
        print("\n" + "=" * w)
        print("THE ONE THAT DECIDES IT — hold SOXX at reduced size, do nothing else")
        print("=" * w)
        print(f"{'book':<36}{'CAGR':>9}{'vol':>8}{'Sharpe':>8}{'maxDD':>9}"
              f"{'total':>10}")
        me = books[0]
        print(f"{'STRATEGY  SOXL sleeve, w=0.5':<36}{me['cagr']:>+8.1f}%"
              f"{me['vol']:>7.1f}%{me['sharpe']:>8.2f}{me['mdd']:>8.1f}%"
              f"{me['total']:>+9.1f}%")
        for frac in (0.40, 0.45, 0.50, 0.60):
            b = metrics(r * frac, f"BUY+HOLD  SOXX at {frac:.0%}, rest in cash")
            print(f"{b['label']:<36}{b['cagr']:>+8.1f}%{b['vol']:>7.1f}%"
                  f"{b['sharpe']:>8.2f}{b['mdd']:>8.1f}%{b['total']:>+9.1f}%")
        print("\n  Cash is assumed to earn 0%, which understates buy-and-hold: "
              "T-bills paid\n  4-5% for much of this window and that return is "
              "not credited here.")

    # ---- what the t-stat actually means for the headline CAGR
    s = books[0]
    print("\n" + "=" * w)
    print("WHAT '15% A YEAR' ACTUALLY MEANS AT t = 1.71")
    print("=" * w)
    lo_c = s["cagr"] * (1 - 1.96 / s["t"])
    hi_c = s["cagr"] * (1 + 1.96 / s["t"])
    print(f"  point estimate                 {s['cagr']:+.1f}% a year")
    print(f"  95% confidence interval        {lo_c:+.1f}%  to  {hi_c:+.1f}%")
    print(f"  -> the honest statement is 'somewhere between {lo_c:+.0f}% and "
          f"{hi_c:+.0f}%', not '{s['cagr']:.0f}%'")

    # ---- exposure
    on = strat["SOXL"].notna().sum()
    print(f"\n  time in the market: SOXL sleeve holds a position on {on} of "
          f"{len(cal)} sessions,\n  roughly 11:00 to 15:55 — about "
          f"{on / len(cal) * 100:.0f}% of days and ~{4.9 / 6.5 * 100:.0f}% of "
          f"each of those.\n  Call it {on / len(cal) * 4.9 / 6.5 * 100:.0f}% of "
          f"the market exposure buy-and-hold carries, and no overnight risk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
