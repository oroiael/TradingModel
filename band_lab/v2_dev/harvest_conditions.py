"""
Which conditions, if any, move P(+0.5% before -0.5%) away from a coin flip?

The sweep established that no parameter setting of the rule survives costs.
The remaining hope is conditional entry: not trading every minute, but only
minutes whose measurable state says the odds are better than even. This script
measures whether any such state exists, before any strategy is built on it.

Method, and why it differs from the backtest
---------------------------------------------
Every eligible minute is treated as an independent starting point, rather than
following the sequential chain the backtest trades. The chain's entries depend
on prior outcomes, which biases any conditional estimate; starting fresh from
every minute does not. The barrier test itself is imported from
harvest_one_day.py so it matches the rule exactly.

Features are computed strictly from bars BEFORE the entry bar. Nothing here
may see the bar it is predicting.

What is being separated
------------------------
INTERNAL features are deterministic functions of the same price series being
traded -- trailing volatility, trailing return, position in the day's range.
They cannot add information the price path does not already contain, and
because they are mined on the same data they are tested on, they carry the
whole multiple-testing hazard the parameter sweep already demonstrated.

The theory says only two things can move a symmetric barrier probability:
DRIFT and SERIAL CORRELATION of the path. Volatility cannot -- it changes how
fast a barrier is reached, not which one. Testing that claim is the point of
the vol rows: if the hit rate is flat across volatility deciles, an entire
family of candidate filters is dead on mechanism rather than on a backtest.

    python3 band_lab/v2_dev/harvest_conditions.py
    python3 band_lab/v2_dev/harvest_conditions.py --pct 0.01
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_one_day import NO_NEW_MIN, resolve  # noqa: E402
from harvest_series import load_sessions  # noqa: E402

LOOKBACK = 30          # bars of history each feature may use
TRAIN_FRAC = 0.70      # first 70% of sessions fit, last 30% checks


def day_features(bars, prev_close, prev_open):
    """Per-bar features, each using only bars strictly before it."""
    o = np.array([b[1] for b in bars])
    c = np.array([b[4] for b in bars])
    n = len(bars)
    r = np.zeros(n)
    r[1:] = c[1:] / c[:-1] - 1

    vol = np.full(n, np.nan)
    mom = np.full(n, np.nan)
    vratio = np.full(n, np.nan)
    for i in range(LOOKBACK + 1, n):
        w = r[i - LOOKBACK:i]                       # ends at i-1, excludes i
        sd = w.std(ddof=1)
        vol[i] = sd
        mom[i] = c[i - 1] / c[i - 1 - LOOKBACK] - 1
        if sd > 0:
            # Variance ratio: >1 trending, <1 mean-reverting. The mechanism
            # that can actually move a symmetric barrier.
            five = w.reshape(-1, 5).sum(axis=1)
            vratio[i] = five.var(ddof=1) / (5 * sd ** 2)

    return dict(
        minute=np.array([b[0] for b in bars]),
        vol=vol, mom=mom, vratio=vratio,
        from_open=o / o[0] - 1,
        gap=np.full(n, o[0] / prev_close - 1 if prev_close else np.nan),
        prev_ret=np.full(n, prev_close / prev_open - 1 if prev_open else np.nan))


def collect(sessions, pct):
    """One row per eligible starting minute, with its outcome and features."""
    rows = []
    prev_close = prev_open = None
    for day, bars in sessions.items():
        f = day_features(bars, prev_close, prev_open)
        for i, b in enumerate(bars):
            if b[0] >= NO_NEW_MIN:
                break
            entry = b[1]
            out, _j, _fill, amb = resolve(bars, i, entry * (1 + pct),
                                          entry * (1 - pct))
            if out == "open":
                continue                             # never resolved, no verdict
            rows.append((day, b[0], out == "up", amb, f["vol"][i], f["mom"][i],
                         f["vratio"][i], f["from_open"][i], f["gap"][i],
                         f["prev_ret"][i]))
        prev_close, prev_open = bars[-1][4], bars[0][1]

    return pd.DataFrame(rows, columns=[
        "date", "minute", "up", "ambiguous", "vol", "mom", "vratio",
        "from_open", "gap", "prev_ret"])


def decile_table(df, col, label, train_days, bins=10):
    """Hit rate by decile of one feature, in-sample and out-of-sample."""
    d = df.dropna(subset=[col])
    if d.empty:
        return None
    tr = d[d.date.isin(train_days)]
    te = d[~d.date.isin(train_days)]
    if len(tr) < 500 or len(te) < 500:
        return None
    try:
        edges = np.unique(np.nanquantile(tr[col], np.linspace(0, 1, bins + 1)))
    except (ValueError, IndexError):
        return None
    if len(edges) < 3:
        return None

    print(f"\n  {label}")
    print(f"    {'decile':<8}{'range':>26}{'train n':>10}{'train':>9}"
          f"{'test n':>10}{'test':>9}{'consistent':>12}")
    rates = []
    for k in range(len(edges) - 1):
        lo, hi = edges[k], edges[k + 1]
        last = k == len(edges) - 2
        mtr = (tr[col] >= lo) & ((tr[col] <= hi) if last else (tr[col] < hi))
        mte = (te[col] >= lo) & ((te[col] <= hi) if last else (te[col] < hi))
        if mtr.sum() < 100 or mte.sum() < 100:
            continue
        a, b = tr.up[mtr].mean(), te.up[mte].mean()
        rates.append((a, b))
        same = "yes" if (a - 0.5) * (b - 0.5) > 0 else "-"
        print(f"    {k + 1:<8}{f'{lo:+.4g} .. {hi:+.4g}':>26}{mtr.sum():>10,}"
              f"{a * 100:>8.1f}%{mte.sum():>10,}{b * 100:>8.1f}%{same:>12}")
    if len(rates) >= 3:
        a = np.array(rates)
        spread_tr = (a[:, 0].max() - a[:, 0].min()) * 100
        agree = np.mean((a[:, 0] - 0.5) * (a[:, 1] - 0.5) > 0) * 100
        corr = np.corrcoef(a[:, 0], a[:, 1])[0, 1] if len(a) > 2 else np.nan
        print(f"    train spread {spread_tr:.1f}pp   "
              f"deciles agreeing in sign out-of-sample {agree:.0f}%   "
              f"train/test corr {corr:+.2f}")
    return rates


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL")
    p.add_argument("--pct", type=float, default=0.005)
    p.add_argument("--since", default=None)
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    sessions = load_sessions(a.symbol, a.since)
    print(f"loaded {len(sessions):,} sessions; testing every eligible minute "
          f"as an independent start")
    df = collect(sessions, a.pct)

    days = sorted(df.date.unique())
    cut = int(len(days) * TRAIN_FRAC)
    train_days = set(days[:cut])
    base_tr = df[df.date.isin(train_days)].up.mean()
    base_te = df[~df.date.isin(train_days)].up.mean()

    print(f"\n{'=' * 92}")
    print(f"  BASELINE   {len(df):,} resolved starts   "
          f"threshold +/-{a.pct:.2%}")
    print(f"{'=' * 92}")
    print(f"    train {pd.Timestamp(days[0]).date()} -> "
          f"{pd.Timestamp(days[cut - 1]).date()}   hit rate {base_tr * 100:.2f}%")
    print(f"    test  {pd.Timestamp(days[cut]).date()} -> "
          f"{pd.Timestamp(days[-1]).date()}   hit rate {base_te * 100:.2f}%")
    print(f"    ambiguous bars resolved adversely: "
          f"{df.ambiguous.mean() * 100:.2f}% of starts")
    print(f"\n    A symmetric barrier on a driftless walk pays 50.00%. "
          f"Costs need roughly 55%.")

    # Hour of day is a coarse drift proxy and the cheapest thing to check.
    df["hour"] = (df.minute // 60)
    print(f"\n  HIT RATE BY HOUR OF ENTRY")
    print(f"    {'hour':<8}{'train n':>10}{'train':>9}{'test n':>10}{'test':>9}")
    for h in sorted(df.hour.unique()):
        m = df.hour == h
        tr = df[m & df.date.isin(train_days)]
        te = df[m & ~df.date.isin(train_days)]
        if len(tr) < 100 or len(te) < 100:
            continue
        print(f"    {h:02d}:00{'':<3}{len(tr):>10,}{tr.up.mean() * 100:>8.1f}%"
              f"{len(te):>10,}{te.up.mean() * 100:>8.1f}%")

    for col, label in (
            ("vol", "TRAILING 30-MIN REALISED VOL  (theory says this is FLAT)"),
            ("vratio", "VARIANCE RATIO  (>1 trending, <1 mean-reverting)"),
            ("mom", "TRAILING 30-MIN RETURN  (momentum / reversal)"),
            ("from_open", "PRICE VS THE DAY'S OPEN  (intraday drift so far)"),
            ("gap", "OVERNIGHT GAP  (day-level, known before the open)"),
            ("prev_ret", "PRIOR DAY RETURN  (day-level, known before the open)")):
        decile_table(df, col, label, train_days)

    os.makedirs(a.outdir, exist_ok=True)
    span = f"{pd.Timestamp(days[0]).date()}_{pd.Timestamp(days[-1]).date()}"
    path = os.path.join(a.outdir, f"harvest_conditions_{a.symbol}_{span}.csv")
    df.to_csv(path, index=False)
    print(f"\n  per-start rows -> {path}\n")


if __name__ == "__main__":
    main()
