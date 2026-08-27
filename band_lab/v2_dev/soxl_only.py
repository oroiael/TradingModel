"""
SOXL alone vs the pair, under the corrected fill model.

**Read this first.** SOXL is being singled out *because it is the sleeve that
survived the correction*. That is selection after the fact — the same move that
produced the numbers this whole exercise just demolished. Nothing here is
evidence that SOXL works; it is a description of what SOXL did on the sample
that motivated looking at it. The only honest test of SOXL-alone is out of
sample, and this project has no out-of-sample data left.

What this script is for: showing what dropping SOXS costs, since SOXS was
carried to control drawdown and that job is separate from whether it makes
money.

    python3 band_lab/v2_dev/soxl_only.py
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
ROOT = os.path.dirname(_BAND_LAB)
for _p in (os.path.join(_BAND_LAB, "live"), os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest_as_executed import (COST_BP_PER_FILL, START, replay_session,
                                  norm_sf)                          # noqa: E402
from intrabar import load_1min_sessions                             # noqa: E402
from replay import backtest_config, load_sessions                   # noqa: E402
from sleeve import SleeveStateMachine                               # noqa: E402
from strategy_core import FeatureHistory, session_stats             # noqa: E402

SLEEVES = ("SOXL", "SOXS")
#: The corrected simulator: re-buy waits a minute, whole shares, real tick
#: sizes, size off the limit, exit at 15:55 rather than free at 15:50.
AS_EXECUTED = dict(wait_bars=1, flatten_at_open_of_next=True)
LIVE_CFG = dict(whole_shares=True, tick_rounding=True, sizing_basis="limit")


def sleeve_daily(symbol):
    fine = dict(load_1min_sessions(symbol, ROOT))
    sessions = load_sessions(symbol, ROOT)
    dates = {d for d, _ in sessions} & set(fine)
    dates = {d for d in dates if d >= START}
    cfg = dataclasses.replace(backtest_config(symbol), **LIVE_CFG)
    history = FeatureHistory()
    returns, fills = {}, {}
    for date, dbars in sessions:
        stats = session_stats(dbars)
        atr5, thr80 = history.atr5(), history.thr80()
        if date in dates:
            sm = SleeveStateMachine(cfg)
            g = sm.begin_session(date, atr5, stats.is_half_day, stats.late_open)
            if g.ok and sm.apply_morning_filter(stats.or30, thr80, stats.pos10).ok:
                replay_session(dbars, fine.get(date, dbars), sm,
                               5 if date in fine else 1, **AS_EXECUTED)
                returns[date] = sm.pnl
                fills[date] = len(sm.trades)
        history.append(stats)
    on = pd.Series(returns, dtype=float).sort_index()
    f = pd.Series(fills, dtype=float).reindex(on.index).fillna(0)
    return on - f * COST_BP_PER_FILL[symbol] / 1e4


def metrics(daily, label, ann_days):
    m, sd = daily.mean(), daily.std(ddof=1)
    sem = sd / math.sqrt(len(daily))
    eq = (1.0 + daily).cumprod()
    dd = float((eq / eq.cummax() - 1.0).min())
    ann = (1 + m) ** ann_days - 1
    return dict(label=label, n=len(daily), mean_bp=m * 1e4, sd_bp=sd * 1e4,
                t=m / sem if sem else float("nan"),
                ann_pct=ann * 100, vol_pct=sd * math.sqrt(ann_days) * 100,
                sharpe=m / sd * math.sqrt(ann_days) if sd else float("nan"),
                mdd_pct=dd * 100, total_pct=(eq.iloc[-1] - 1) * 100,
                win=float((daily > 0).mean()) * 100,
                worst_pct=daily.min() * 100)


def main() -> int:
    argparse.ArgumentParser(description="SOXL alone vs the pair").parse_args()

    d = {s: sleeve_daily(s) for s in SLEEVES}
    cal = pd.DatetimeIndex(sorted(set(d["SOXL"].index) | set(d["SOXS"].index)))
    years = (cal[-1] - cal[0]).days / 365.25

    books = {}
    # Same position size in each case; only the second sleeve changes.
    books["SOXL only, w=0.5 (half the account unused)"] = \
        0.5 * d["SOXL"].reindex(cal).fillna(0.0)
    books["SOXL + SOXS, w=0.5 each  (what you run today)"] = sum(
        0.5 * d[s].reindex(cal).fillna(0.0) for s in SLEEVES)
    books["SOXL only, w=1.0 (whole account on SOXL)"] = \
        1.0 * d["SOXL"].reindex(cal).fillna(0.0)

    active = {k: v[v != 0.0] for k, v in books.items()}
    ann_days = {k: len(v) / years for k, v in active.items()}

    w = 104
    print("=" * w)
    print("SOXL ALONE vs THE PAIR — corrected simulator (re-buy waits a minute, "
          "15:55 exit), 2022+")
    print("=" * w)
    print(f"{'book':<46}{'ann':>8}{'vol':>8}{'Sharpe':>8}{'maxDD':>9}"
          f"{'total':>9}{'win%':>7}{'t':>7}")
    rows = []
    for k, v in active.items():
        r = metrics(v, k, ann_days[k])
        rows.append(r)
        print(f"{k:<46}{r['ann_pct']:>+7.1f}%{r['vol_pct']:>7.1f}%"
              f"{r['sharpe']:>8.2f}{r['mdd_pct']:>8.1f}%{r['total_pct']:>+8.1f}%"
              f"{r['win']:>7.1f}{r['t']:>7.2f}")

    print(f"\n  What SOXS is actually doing (it is not making money):")
    l, p = active["SOXL only, w=0.5 (half the account unused)"], \
        active["SOXL + SOXS, w=0.5 each  (what you run today)"]
    ml, mp = metrics(l, "", ann_days[list(active)[0]]), \
        metrics(p, "", ann_days[list(active)[1]])
    print(f"    volatility   SOXL alone {ml['vol_pct']:.1f}%  ->  "
          f"with SOXS {mp['vol_pct']:.1f}%   "
          f"({(mp['vol_pct']/ml['vol_pct']-1)*100:+.0f}%)")
    print(f"    max drawdown SOXL alone {ml['mdd_pct']:.1f}%  ->  "
          f"with SOXS {mp['mdd_pct']:.1f}%")
    print(f"    worst day    SOXL alone {ml['worst_pct']:.2f}%  ->  "
          f"with SOXS {mp['worst_pct']:.2f}%")
    print(f"    correlation of the two sleeves on days both traded: "
          f"{pd.concat({s: d[s] for s in SLEEVES}, axis=1).dropna().corr().iloc[0,1]:+.3f}")

    print("\n" + "=" * w)
    print("SOXL YEAR BY YEAR — does the result depend on one good year?")
    print("=" * w)
    x = d["SOXL"]
    print(f"{'year':>6}{'ON-days':>9}{'bp/ON-day':>12}{'total':>10}"
          f"{'win%':>8}{'maxDD':>9}")
    for y, g in x.groupby(x.index.year):
        eq = (1.0 + g).cumprod()
        print(f"{y:>6}{len(g):>9}{g.mean()*1e4:>+12.2f}"
              f"{(eq.iloc[-1]-1)*100:>+9.1f}%{float((g>0).mean())*100:>7.1f}%"
              f"{float((eq/eq.cummax()-1).min())*100:>8.1f}%")
    pos = sum(1 for _, g in x.groupby(x.index.year) if g.mean() > 0)
    n_y = x.index.year.nunique()
    print(f"\n  positive years: {pos} of {n_y}")

    print("\n" + "=" * w)
    print("HOW MUCH OF SOXL's RESULT IS THE BEST FEW DAYS?")
    print("=" * w)
    srt = x.sort_values(ascending=False)
    tot = x.sum()
    for frac in (0.01, 0.05, 0.10, 0.25):
        k = max(1, int(round(frac * len(srt))))
        print(f"  best {frac:4.0%} of ON-days ({k:3d} days) carry "
              f"{srt.head(k).sum()/tot*100:6.1f}% of the total return")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
