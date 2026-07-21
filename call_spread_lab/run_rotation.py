#!/usr/bin/env python3
"""
run_rotation.py  --  fix the 2023 failure with a volatility-regime rotation.

Diagnosis (by-year regime table): 2023 broke the strangle not because it trended
but because REALIZED VOL collapsed (rvol 0.83 vs 0.99-1.31 elsewhere) -- there was
little movement to harvest, and the put side just bled. Note 2023 and 2026 had
nearly identical VRP (~0) but opposite outcomes, so realized vol -- not VRP -- is
the separating signal.

Rule: when trailing 20-day realized vol < `vol_thresh`, the long-vol edge is gone,
so ROTATE OUT of the symmetric strangle:
   * "trend"  -> keep only the trend-aligned side (calls if spot>SMA50 else puts):
     ride the drift instead of paying for two-sided gamma that won't pay.
   * "cash"   -> liquidate and sit out until vol returns (exit and wait).
When rvol >= vol_thresh, run the full strangle. All signals are trailing (no
look-ahead). Compared against the always-on strangle over the full 2022-2026.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data_loader import load_options
from verticals import build_index
from signals import build_signals
from strangle_harvest import HConfig, simulate, stats, compact_index

OUT = Path(__file__).resolve().parent / "outputs"
BEST = dict(dte_target=120, dte_tol=20, dist=0.075, take=0.50, leg_frac=0.15)
pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 82 + f"\n{t}\n" + "=" * 82)


def regime_sides(sig, vol_thresh, mode):
    """{td -> frozenset of sides to maintain}. Below vol_thresh, rotate."""
    BOTH = frozenset({"CALL", "PUT"})
    out = {}
    for d, r in sig.iterrows():
        rv, sma = r["rvol20"], r["sma50"]
        if not (rv == rv) or not (sma == sma):     # warm-up: default strangle
            out[d] = BOTH; continue
        if rv >= vol_thresh:
            out[d] = BOTH
        elif mode == "cash":
            out[d] = frozenset()
        else:  # trend side
            out[d] = frozenset({"CALL"}) if r["close"] > sma else frozenset({"PUT"})
    return out


def by_year(res):
    eq = pd.Series(res["equity"], index=pd.to_datetime(res["dates"]))
    yr = eq.groupby(eq.index.year).agg(["first", "last"])
    return (yr["last"] / yr["first"] - 1).round(3)


def main():
    hr("LOAD + signals")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt)
    compact = compact_index(idx)
    sig = build_signals(opt)

    base = simulate(idx, HConfig(**BEST), compact)
    s0 = stats(base, HConfig(**BEST))
    hr("BASELINE: always-on strangle (120 DTE, 7.5%, take +50%, leg_frac 15%)")
    print(f"end ${s0['end_equity']:,.0f}  CAGR {s0['cagr']:+.0%}  maxDD {s0['max_dd']:+.0%}")
    print("by year:\n" + by_year(base).to_string())

    hr("ROTATION sweep (vol_thresh x rotate-to)  -- does it fix 2023 without hurting the rest?")
    print(f"{'vol_thresh':>10} {'mode':>7} {'end_equity':>13} {'CAGR':>7} {'maxDD':>7} "
          f"{'2023':>7} {'rotate_days':>11}")
    curves = {"strangle always": base}
    for mode in ("trend", "cash"):
        for vt in (0.85, 0.90, 0.95):
            rs = regime_sides(sig, vt, mode)
            r = simulate(idx, HConfig(**BEST), compact, regime_sides=rs)
            s = stats(r, HConfig(**BEST))
            y = by_year(r)
            rot_days = sum(1 for v in rs.values() if v != frozenset({"CALL", "PUT"}))
            print(f"{vt:>10.2f} {mode:>7} {s['end_equity']:>13,.0f} {s['cagr']:>+7.0%} "
                  f"{s['max_dd']:>+7.0%} {y.get(2023, float('nan')):>+7.0%} {rot_days:>11}")
            if vt == 0.90:
                curves[f"rotate->{mode} (vt.90)"] = r

    hr("BEST ROTATION vs BASELINE -- full by-year")
    rs = regime_sides(sig, 0.90, "trend")
    r_best = simulate(idx, HConfig(**BEST), compact, regime_sides=rs)
    comp = pd.DataFrame({"strangle_always": by_year(base),
                         "rotate_to_trend_vt0.90": by_year(r_best)})
    print(comp.to_string())
    s = stats(r_best, HConfig(**BEST))
    print(f"\nrotate->trend vt0.90:  end ${s['end_equity']:,.0f}  CAGR {s['cagr']:+.0%}  "
          f"maxDD {s['max_dd']:+.0%}   (baseline end ${s0['end_equity']:,.0f}, "
          f"CAGR {s0['cagr']:+.0%}, maxDD {s0['max_dd']:+.0%})")
    # what does the rotation hold during 2023?
    r23 = r_best["log"]
    r23 = r23[(pd.to_datetime(r23["date"]).dt.year == 2023)]
    print(f"\n2023 actions: {r23['action'].value_counts().to_dict()}")

    _plot(curves)
    print("\nsaved outputs/rotation_curves.png")


def _plot(curves):
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for k, r in curves.items():
        e = pd.Series(r["equity"], index=pd.to_datetime(r["dates"]))
        ax.plot(e.index, e.values, label=k, lw=1.3)
    ax.axhline(100_000, color="k", lw=0.6, ls="--")
    ax.set_yscale("log"); ax.set_ylabel("equity ($, log)")
    ax.axvspan(pd.Timestamp("2023-01-01"), pd.Timestamp("2023-12-31"),
               color="orange", alpha=0.10, label="2023 (low-vol)")
    ax.set_title("Vol-regime rotation vs always-on strangle (120 DTE, 7.5%)")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "rotation_curves.png", dpi=110)


if __name__ == "__main__":
    main()
