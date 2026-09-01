"""
Is ANY setting of the harvest rule profitable, or is the whole family dead?

Both fixed configurations tested so far lose money gross. That could mean the
parameters were wrong, or it could mean the rule has no edge at any parameter.
Those are very different conclusions and only a grid can separate them.

The grid, over every complete session in the file
--------------------------------------------------
  threshold   0.25% 0.50% 0.75% 1.00% 1.50% 2.00%
  slots       10 25 50 100          (PARK only; CLOSE holds one position)
  cutoff      11:00 12:00 13:00 14:00 15:00
  exit rule   PARK (hold the loser to 15:55) and CLOSE (sell it on the touch)

Run in two stages, because the conclusion is asymmetric
--------------------------------------------------------
Stage 1 prices every configuration GROSS -- no commission, no slippage. A
configuration that cannot make money with zero costs cannot make money with
costs, so if stage 1 finds nothing positive the question is settled and no
further compute is justified.

Stage 2 takes whatever stage 1 found positive and re-prices it twice: with
half-a-cent-per-share-per-side slippage alone, and then with slippage plus
IBKR tiered commission. Only a configuration that survives BOTH is a real
candidate.

Everything else follows harvest_series.py: $100,000, a flat $25,000 cash
reserve, slot size reset each morning to (equity - reserve) / slots, no
overnight carry, and the account freezes if it decays to the reserve.

    python3 band_lab/v2_dev/harvest_sweep.py
    python3 band_lab/v2_dev/harvest_sweep.py --since 2022-01-01
    python3 band_lab/v2_dev/harvest_sweep.py --slippage 0.01
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_one_day import ibkr_tiered  # noqa: E402
from harvest_series import load_sessions, run_series  # noqa: E402

THRESHOLDS = (0.0025, 0.005, 0.0075, 0.010, 0.015, 0.020)
SLOTS = (10, 25, 50, 100)
CUTOFFS = (11 * 60, 12 * 60, 13 * 60, 14 * 60, 15 * 60)


def score(df, equity0):
    """Collapse one configuration's daily series into comparable numbers."""
    eq = df.end_equity.to_numpy(float)
    final = float(eq[-1])
    years = (pd.Timestamp(df.date.iloc[-1]) - pd.Timestamp(df.date.iloc[0])).days / 365.25
    cagr = (final / equity0) ** (1 / years) - 1 if years > 0 and final > 0 else np.nan
    peaks = np.maximum.accumulate(eq)
    dd = float((eq / peaks - 1).min())
    r = df.ret.to_numpy(float)
    sd = r.std(ddof=1)
    traded = df.trades > 0
    frozen = None
    if traded.any() and not traded.iloc[-1]:
        frozen = str(df.date.iloc[int(np.flatnonzero(traded.to_numpy())[-1]) + 1])
    return dict(
        final=final, total=final / equity0 - 1, cagr=cagr, max_dd=dd,
        sharpe=r.mean() / sd * np.sqrt(252) if sd else np.nan,
        trades=int(df.trades.sum()), fees=float(df.fees.sum()),
        days_traded=int(traded.sum()), frozen_from=frozen,
        win_days=int((df.pnl > 0).sum()),
        capped_days=int((df.peak_open >= df.peak_open.max()).sum()))


def sweep(sessions, equity0, reserve, commission, slippage, label, configs):
    rows, t0 = [], time.time()
    for k, (park, pct, slots, cutoff) in enumerate(configs, 1):
        df, _tp, _tw = run_series(sessions, pct, park, equity0, reserve, slots,
                                  commission, slippage=slippage, cutoff=cutoff,
                                  marks=False)
        rows.append(dict(rule="PARK" if park else "CLOSE", pct=pct,
                         slots=slots if park else 1, cutoff=cutoff,
                         cost=label, **score(df, equity0)))
        if k % 40 == 0 or k == len(configs):
            print(f"    {label}: {k}/{len(configs)} configs, "
                  f"{time.time() - t0:.0f}s", flush=True)
    return pd.DataFrame(rows)


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def fmt_frozen(v):
    """A config that never froze stores None, which pandas turns into NaN.

    NaN is truthy, so `v or "-"` returned the NaN and printed it. Test for
    null explicitly instead.
    """
    return "-" if v is None or (isinstance(v, float) and v != v) else str(v)


def show(df, title, n=15):
    print(f"\n  {title}")
    print(f"    {'rule':<6}{'thresh':>8}{'slots':>7}{'cutoff':>8}"
          f"{'final $':>14}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}"
          f"{'trades':>9}{'frozen':>12}")
    for _, r in df.head(n).iterrows():
        print(f"    {r['rule']:<6}{r['pct'] * 100:>7.2f}%{r['slots']:>7.0f}"
              f"{hhmm(int(r['cutoff'])):>8}{r['final']:>14,.0f}"
              f"{r['cagr'] * 100:>8.2f}%{r['max_dd'] * 100:>8.1f}%"
              f"{r['sharpe']:>8.2f}{r['trades']:>9,.0f}"
              f"{fmt_frozen(r['frozen_from']):>12}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL")
    p.add_argument("--equity", type=float, default=100_000)
    p.add_argument("--reserve", type=float, default=25_000)
    p.add_argument("--slippage", type=float, default=0.005,
                   help="dollars per share, charged on each side")
    p.add_argument("--since", default=None)
    p.add_argument("--until", default=None)
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    sessions = load_sessions(a.symbol, a.since, a.until)
    print(f"loaded {len(sessions):,} complete sessions "
          f"({min(sessions).date()} -> {max(sessions).date()})")

    configs = [(True, pct, sl, c)
               for pct, sl, c in itertools.product(THRESHOLDS, SLOTS, CUTOFFS)]
    configs += [(False, pct, 1, c)
                for pct, c in itertools.product(THRESHOLDS, CUTOFFS)]
    print(f"grid: {len(configs)} configurations "
          f"({sum(p for p, _, _, _ in configs)} PARK, "
          f"{sum(not p for p, _, _, _ in configs)} CLOSE)\n")

    os.makedirs(a.outdir, exist_ok=True)
    print("  STAGE 1  gross: no commission, no slippage")
    g = sweep(sessions, a.equity, a.reserve, None, 0.0, "gross", configs)
    g = g.sort_values("cagr", ascending=False)

    pos = g[g.total > 0]
    print(f"\n{'=' * 100}")
    print(f"  STAGE 1 RESULT: {len(pos)} of {len(g)} configurations made money "
          f"GROSS ({len(pos) / len(g) * 100:.1f}%)")
    print(f"{'=' * 100}")
    show(g, "BEST 15 BY CAGR (gross)")
    show(g.sort_values("cagr"), "WORST 5 BY CAGR (gross)", 5)

    print(f"\n  gross CAGR across the grid: "
          f"best {g.cagr.max() * 100:+.2f}%   median {g.cagr.median() * 100:+.2f}%"
          f"   worst {g.cagr.min() * 100:+.2f}%")
    for rule in ("PARK", "CLOSE"):
        sub = g[g.rule == rule]
        print(f"    {rule:<6} {len(sub):>3} configs   "
              f"positive {int((sub.total > 0).sum()):>3}   "
              f"best CAGR {sub.cagr.max() * 100:>+7.2f}%   "
              f"median {sub.cagr.median() * 100:>+7.2f}%")

    frames = [g]
    if len(pos):
        keep = [(r["rule"] == "PARK", r["pct"], int(r["slots"]), int(r["cutoff"]))
                for _, r in pos.iterrows()]
        print(f"\n  STAGE 2  re-pricing the {len(keep)} gross-positive "
              f"configurations with costs")
        s1 = sweep(sessions, a.equity, a.reserve, None, a.slippage,
                   f"slip{a.slippage}", keep).sort_values("cagr", ascending=False)
        s2 = sweep(sessions, a.equity, a.reserve, ibkr_tiered, a.slippage,
                   "slip+comm", keep).sort_values("cagr", ascending=False)
        show(s1, f"GROSS-POSITIVE, with ${a.slippage}/share/side slippage")
        show(s2, f"GROSS-POSITIVE, with slippage AND IBKR commission")
        print(f"\n  survivors after slippage:            "
              f"{int((s1.total > 0).sum())} of {len(s1)}")
        print(f"  survivors after slippage + commission: "
              f"{int((s2.total > 0).sum())} of {len(s2)}")
        frames += [s1, s2]
    else:
        print(f"\n  STAGE 2 SKIPPED: nothing was positive gross, and costs only "
              f"subtract.\n  The rule has no profitable setting anywhere in this "
              f"grid.")

    span = f"{min(sessions).date()}_{max(sessions).date()}"
    path = os.path.join(a.outdir, f"harvest_sweep_{a.symbol}_{span}.csv")
    pd.concat(frames).to_csv(path, index=False)
    print(f"\n  full grid -> {path}\n")


if __name__ == "__main__":
    main()
