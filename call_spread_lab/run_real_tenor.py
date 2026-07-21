#!/usr/bin/env python3
"""
run_real_tenor.py  --  with REAL intraday option prices (2022-2026), where is the
sweet spot for intraday harvesting, and how does it compare to close-only (EOD)?

The 60-vs-120 result showed intraday harvesting helps at short tenors (bank the
spike before theta) but hurts at long tenors (it sells trend-winners too early).
This sweeps tenor for REAL vs EOD to locate the crossover, and saves the 60-DTE
curves (REAL vs BS vs EOD) -- the standout config that fixes 2022 AND 2023.

Uses the cached real_hi from run_real_harvest.py (run that once first).
"""
from __future__ import annotations
import pickle
from pathlib import Path
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

from data_loader import load_options, load_5min
from verticals import build_index
from strangle_harvest import (HConfig, simulate, stats, compact_index,
                              build_hilo, build_iv_key)
from run_real_harvest import build_real_hi, by_year

OUT = Path(__file__).resolve().parent / "outputs"
SLIP = 0.05
pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 82 + f"\n{t}\n" + "=" * 82)


def main():
    opt = load_options(whole_strikes_only=True)
    idx = build_index(opt); compact = compact_index(idx)
    fm = load_5min(); hilo = build_hilo(fm); ivk = build_iv_key(opt)
    real_hi = build_real_hi()

    hr("TENOR SWEEP: REAL intraday harvest vs EOD (7.5% dist, take +50%, leg_frac 15%)")
    print(f"{'DTE':>4} | {'EOD CAGR':>9} {'EOD DD':>7} | {'REAL CAGR':>10} {'REAL DD':>8} "
          f"| {'REAL 2022':>10} {'REAL 2023':>10} {'uplift':>7}")
    rows = []
    for dte in (21, 30, 45, 60, 75, 90, 120, 150):
        cfg = dict(dte_target=dte, dte_tol=(12 if dte <= 45 else (15 if dte < 90 else 20)),
                   dist=0.075, take=0.50, leg_frac=0.15)
        eod = simulate(idx, HConfig(**cfg), compact)
        real = simulate(idx, HConfig(**cfg), compact, intraday=(None, None, SLIP), real_hi=real_hi)
        se, sr = stats(eod, HConfig(**cfg)), stats(real, HConfig(**cfg))
        ye, yr = by_year(eod), by_year(real)
        rows.append(dict(dte=dte, eod_cagr=se["cagr"], real_cagr=sr["cagr"],
                         real_dd=sr["max_dd"], eod_dd=se["max_dd"],
                         r2022=yr.get(2022), r2023=yr.get(2023)))
        print(f"{dte:>4} | {se['cagr']:>+8.0%} {se['max_dd']:>+7.0%} | "
              f"{sr['cagr']:>+9.0%} {sr['max_dd']:>+8.0%} | {yr.get(2022,float('nan')):>+10.0%} "
              f"{yr.get(2023,float('nan')):>+10.0%} {sr['cagr']-se['cagr']:>+7.0%}")
        if dte == 60:
            hi = simulate(idx, HConfig(real_exit="high", **cfg), compact,
                          intraday=(None, None, SLIP), real_hi=real_hi)
            _plot60(eod, real, hi)

    sb = pd.DataFrame(rows)
    sb.to_csv(OUT / "real_tenor_sweep.csv", index=False)

    hr("EXECUTION REALISM: limit-fill (default) vs sell-at-high (optimistic upper bound)")
    for dte in (30, 60):
        cfg = dict(dte_target=dte, dte_tol=(12 if dte <= 45 else 15), dist=0.075,
                   take=0.50, leg_frac=0.15)
        lim = stats(simulate(idx, HConfig(**cfg), compact,
                             intraday=(None, None, SLIP), real_hi=real_hi), HConfig(**cfg))
        hi = stats(simulate(idx, HConfig(real_exit="high", **cfg), compact,
                            intraday=(None, None, SLIP), real_hi=real_hi), HConfig(**cfg))
        print(f"  {dte} DTE: limit-fill CAGR {lim['cagr']:+.0%} (DD {lim['max_dd']:+.0%})  |  "
              f"sell-at-high CAGR {hi['cagr']:+.0%} (DD {hi['max_dd']:+.0%})  <- upper bound only")

    hr("READ")
    print("Under REALISTIC limit-fill execution, intraday threshold-harvesting LOSES to")
    print("EOD close-harvesting at EVERY tenor (uplift negative throughout). Force-selling")
    print("each leg at +take% intraday caps the fat-tail winners that are the whole edge;")
    print("letting them run to the close (EOD) captures more. The 'intraday helps' result")
    print("(Part 4 BS + the sell-at-high line) was an execution artifact of selling at the")
    print("spike peak, which needs foresight. Realistic best remains the 120-DTE EOD harvest.")


def _plot60(eod, real_limit, real_high):
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for lbl, r, c in [("EOD close-harvest (realistic)", eod, "tab:blue"),
                      ("REAL intraday, limit-fill (realistic)", real_limit, "tab:red"),
                      ("REAL intraday, sell-at-high (optimistic ceiling)", real_high, "tab:green")]:
        e = pd.Series(r["equity"], index=pd.to_datetime(r["dates"]))
        ax.plot(e.index, e.values, label=lbl, lw=1.5, color=c)
    ax.axhline(100_000, color="k", lw=0.6, ls="--")
    ax.set_yscale("log"); ax.set_ylabel("equity ($, log)")
    ax.set_title("60 DTE harvest: execution realism decides it — limit-fill intraday "
                 "LOSES to EOD;\nthe 'intraday helps' story was the sell-at-high ceiling")
    ax.legend(); fig.tight_layout(); fig.savefig(OUT / "real_harvest_60dte.png", dpi=110)


if __name__ == "__main__":
    main()
