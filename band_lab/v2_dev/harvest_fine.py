"""
The barrier grid at 0.1% resolution, and what each cell must beat.

Earlier sweeps used six threshold values -- 0.25, 0.5, 0.75, 1.0, 1.5, 2.0
percent -- which leaves 50-basis-point holes between the wide ones. This walks
both barriers in 0.1% steps so nothing can hide between the old rungs.

It measures the expectation directly rather than backtesting every cell, for
two reasons: a backtest of 900 cells invites exactly the multiple-testing
error the earlier sweeps demonstrated, and the expectation is what decides the
question. Every eligible minute is an independent start, so the number is a
property of the price series and not of a trading rule.

Each cell gets three numbers:

  EV gross      the mean return over EVERY start, with a start that never
                reaches a barrier marked at the 15:55 close rather than
                discarded -- discarding them conditions the sample on
                resolution and manufactures an edge out of a wide stop
  EV net        the same after a round trip of slippage at SOXL's median price
  edge/tick     the gross edge divided by ONE CENT at the median price

The third is the one that matters. A US equity quotes in one-cent increments,
so a cent is the smallest unit of price you can be wrong by. An edge worth
less than a fraction of a tick cannot be collected by an order that crosses
the spread, whatever its Sharpe looks like in a fill-model backtest.

    python3 band_lab/v2_dev/harvest_fine.py
    python3 band_lab/v2_dev/harvest_fine.py --step 0.0005 --stride 10
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_one_day import NO_NEW_MIN, resolve  # noqa: E402
from harvest_series import load_sessions  # noqa: E402


def surface(sessions, ups, dns, stride, med_px, slip):
    """P(up first) and expectation for every barrier pair."""
    rows, t0, k = [], time.time(), 0
    total = len(ups) * len(dns)
    for up in ups:
        for dn in dns:
            n_up = n_dn = n_open = 0
            open_ret = 0.0
            for bars in sessions.values():
                eod = bars[-1][4]
                for i in range(0, len(bars), stride):
                    if bars[i][0] >= NO_NEW_MIN:
                        break
                    e = bars[i][1]
                    out, _j, _f, _a = resolve(bars, i, e * (1 + up), e * (1 - dn))
                    if out == "up":
                        n_up += 1
                    elif out == "down":
                        n_dn += 1
                    else:
                        # A start that never reaches either barrier is not a
                        # non-event: the position is closed at 15:55 like any
                        # other. Dropping these silently conditions the sample
                        # on resolution, and because a wide stop is what keeps
                        # a losing drift unresolved, dropping them invents an
                        # edge. At a 3.0% stop a third of starts land here.
                        n_open += 1
                        open_ret += eod / e - 1
            k += 1
            tot = n_up + n_dn
            n_all = tot + n_open
            if not n_all:
                continue
            obs = n_up / tot if tot else float("nan")
            ev = (n_up * up - n_dn * dn + open_ret) / n_all
            # Binomial standard error on the win rate, propagated to EV. Starts
            # overlap heavily, so this UNDERSTATES the true error -- if a cell
            # is not significant even here, it is certainly not significant.
            se_p = np.sqrt(obs * (1 - obs) / tot) if tot else float("nan")
            rows.append(dict(up=up, dn=dn, n=n_all, n_resolved=tot,
                             unresolved=n_open / n_all, p_up=obs,
                             theory=dn / (up + dn), ev=ev,
                             ev_se=se_p * (up + dn),
                             ev_net=ev - 2 * slip / med_px,
                             edge_ticks=ev * med_px / 0.01))
            if k % 100 == 0 or k == total:
                print(f"    {k}/{total} cells  {time.time() - t0:.0f}s", flush=True)
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL")
    p.add_argument("--step", type=float, default=0.001, help="grid step, default 0.1%%")
    p.add_argument("--lo", type=float, default=0.001)
    p.add_argument("--hi", type=float, default=0.030)
    p.add_argument("--stride", type=int, default=5)
    p.add_argument("--slippage", type=float, default=0.005)
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    sessions = load_sessions(a.symbol)
    px = np.array([b[1] for bars in sessions.values() for b in bars])
    med = float(np.median(px))
    steps = int(round((a.hi - a.lo) / a.step)) + 1
    ups = [round(a.lo + k * a.step, 6) for k in range(steps)]
    print(f"loaded {len(sessions):,} sessions   median price ${med:.2f}   "
          f"one cent = {0.01 / med * 100:.4f}%")
    print(f"grid {len(ups)} x {len(ups)} = {len(ups) ** 2:,} cells, "
          f"{a.lo * 100:.1f}%..{a.hi * 100:.1f}% in {a.step * 100:.1f}% steps, "
          f"every {a.stride}th minute\n")

    df = surface(sessions, ups, ups, a.stride, med, a.slippage)

    print(f"\n{'=' * 96}")
    print(f"  GROSS EXPECTATION ACROSS {len(df):,} CELLS")
    print(f"{'=' * 96}")
    print(f"    positive EV gross          {int((df.ev > 0).sum()):>6,} "
          f"({(df.ev > 0).mean() * 100:.1f}%)")
    print(f"    positive by more than 2 SE {int((df.ev > 2 * df.ev_se).sum()):>6,}"
          f"   (binomial SE, which understates the true error)")
    print(f"    best  EV/trade {df.ev.max() * 100:+.4f}%   "
          f"worst {df.ev.min() * 100:+.4f}%")
    print(f"    mean |P(up) - theory| across the grid: "
          f"{(df.p_up - df.theory).abs().mean() * 100:.3f} pp")

    top = df.sort_values("ev", ascending=False).head(20)
    print(f"\n  TOP 20 CELLS BY GROSS EV")
    print(f"    {'up':>7}{'down':>7}{'n':>10}{'P(up)':>9}{'theory':>9}"
          f"{'EV gross':>11}{'+/-2SE':>10}{'edge/tick':>11}{'EV net':>11}")
    for _, r in top.iterrows():
        print(f"    {r['up'] * 100:>6.1f}%{r['dn'] * 100:>6.1f}%{r['n']:>10,.0f}"
              f"{r['unresolved'] * 100:>7.1f}%{r['p_up'] * 100:>8.2f}%"
              f"{r['theory'] * 100:>8.2f}%{r['ev'] * 100:>+10.4f}%"
              f"{r['edge_ticks']:>11.2f}{r['ev_net'] * 100:>+10.4f}%")

    print(f"\n{'=' * 96}")
    print(f"  THE TEST THAT DECIDES IT: is any edge bigger than a tick?")
    print(f"{'=' * 96}")
    print(f"    one cent at ${med:.2f} = {0.01 / med * 100:.4f}% of position")
    print(f"    cells whose gross edge exceeds ONE tick   "
          f"{int((df.edge_ticks > 1).sum()):>6,} of {len(df):,}")
    print(f"    cells whose gross edge exceeds HALF a tick "
          f"{int((df.edge_ticks > 0.5).sum()):>6,} of {len(df):,}")
    print(f"    best edge anywhere on the grid: "
          f"{df.edge_ticks.max():.2f} ticks")
    print(f"\n    after a ${a.slippage}/side round trip:")
    print(f"      cells still positive  {int((df.ev_net > 0).sum()):>6,} "
          f"of {len(df):,}")
    if (df.ev_net > 0).any():
        b = df.sort_values("ev_net", ascending=False).iloc[0]
        print(f"      best net cell: up {b['up'] * 100:.1f}% / down "
              f"{b['dn'] * 100:.1f}%  EV net {b['ev_net'] * 100:+.4f}%  "
              f"({b['ev_net'] / b['ev_se'] if b['ev_se'] else 0:.1f} SE)")

    # Where the old six-value grid sat, so the holes are visible.
    old = (0.0025, 0.005, 0.0075, 0.010, 0.015, 0.020)
    on = df[df.up.isin(old) & df.dn.isin(old)]
    print(f"\n  the earlier 6-value grid covered {len(on)} of these {len(df):,} "
          f"cells ({len(on) / len(df) * 100:.1f}%)")
    print(f"    best EV on the old rungs   {on.ev.max() * 100:+.4f}%")
    print(f"    best EV anywhere on 0.1%   {df.ev.max() * 100:+.4f}%")
    print(f"    -> the finer grid finds "
          f"{(df.ev.max() - on.ev.max()) * 100:+.4f}% more edge per trade")

    os.makedirs(a.outdir, exist_ok=True)
    path = os.path.join(a.outdir, f"harvest_fine_surface_{a.symbol}.csv")
    df.to_csv(path, index=False)
    print(f"\n  full surface -> {path}\n")


if __name__ == "__main__":
    main()
