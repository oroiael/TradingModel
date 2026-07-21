#!/usr/bin/env python3
"""
run_strangle.py  --  the active long-strangle harvesting study on SOXL.

Answers, from the data:
  1. GRID: the user's matrix -- expirations {30,60,90,120,150,180} x strike
     distances {2,5,7.5,10,12.5,15%} -- which tenor/strike harvests best?
  2. SIZING: what "invest 100%" actually does (leg_frac 0.5) vs fractional
     sizing -- the drawdown question.
  3. HARVEST TRIGGER: sweep the "+X% on the leg" take level (the user's 2-5%
     is the floor) + a no-harvest baseline.
  4. BY-YEAR regime behavior + equity curves for the best config.

Outputs outputs/strangle_scoreboard.csv, strangle_heatmap.png, strangle_curves.png.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

from data_loader import load_options
from verticals import build_index
from strangle_harvest import HConfig, simulate, stats, compact_index

OUT = Path(__file__).resolve().parent / "outputs"
CAP0 = 100_000.0
DTES = [30, 60, 90, 120, 150, 180]
DISTS = [0.02, 0.05, 0.075, 0.10, 0.125, 0.15]
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 40)


def hr(t): print("\n" + "=" * 84 + f"\n{t}\n" + "=" * 84)


def run(idx, compact, **kw):
    cfg = HConfig(**kw)
    return simulate(idx, cfg, compact), cfg


def by_year(res):
    eq = pd.Series(res["equity"], index=pd.to_datetime(res["dates"]))
    yr = eq.groupby(eq.index.year).agg(["first", "last"])
    yr["ret"] = yr["last"] / yr["first"] - 1
    return yr["ret"].round(3)


def main():
    hr("LOAD + index")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt)
    compact = compact_index(idx)

    # ---------------------------------------------------------------- 2. SIZING first
    hr("SIZING -- what 'invest 100%' does vs fractional (90 DTE, 10% dist, take +50%)")
    print(f"{'leg_frac':>9} {'end_equity':>14} {'CAGR':>8} {'maxDD':>8} {'peakDeploy':>11} {'harvests':>9}")
    for lf in (0.05, 0.10, 0.15, 0.25, 0.50):
        r, c = run(idx, compact, dte_target=90, dist=0.10, take=0.50, leg_frac=lf)
        s = stats(r, c)
        tag = "  <- invest~100%" if lf == 0.50 else ""
        print(f"{lf:>9.0%} {s['end_equity']:>14,.0f} {s['cagr']:>+8.0%} "
              f"{s['max_dd']:>+8.0%} {s['peak_deploy']:>11.0%} {s['n_harvests']:>9}{tag}")
    REF_LF = 0.15
    print(f"\n-> grid uses leg_frac={REF_LF:.0%} (a survivable reference); invest-100% "
          "is reported but is ruinous (see maxDD above).")

    # ---------------------------------------------------------------- 1. GRID
    hr(f"GRID -- expiration x strike-distance  (take +50%, leg_frac {REF_LF:.0%})")
    recs = []
    for dte in DTES:
        tol = 10 if dte <= 60 else 20
        for dist in DISTS:
            r, c = run(idx, compact, dte_target=dte, dte_tol=tol, dist=dist,
                       take=0.50, leg_frac=REF_LF)
            s = stats(r, c)
            recs.append(dict(dte=dte, dist=dist, **s))
    sb = pd.DataFrame(recs)
    sb.to_csv(OUT / "strangle_scoreboard.csv", index=False)
    print("\nCAGR by expiration (rows) x strike distance (cols):")
    print((sb.pivot(index="dte", columns="dist", values="cagr") * 100).round(0)
          .to_string(float_format=lambda x: f"{x:+.0f}%"))
    print("\nmax drawdown by expiration x distance:")
    print((sb.pivot(index="dte", columns="dist", values="max_dd") * 100).round(0)
          .to_string(float_format=lambda x: f"{x:.0f}%"))
    best = sb.sort_values("cagr", ascending=False).iloc[0]
    print(f"\nbest cell by CAGR: {int(best['dte'])} DTE, {best['dist']:.1%} dist  "
          f"-> CAGR {best['cagr']:+.0%}, maxDD {best['max_dd']:+.0%}, "
          f"end ${best['end_equity']:,.0f}, {int(best['n_harvests'])} harvests")

    # ---------------------------------------------------------------- 3. TAKE sweep
    bd, bdist = int(best["dte"]), float(best["dist"])
    hr(f"HARVEST TRIGGER sweep at best cell ({bd} DTE, {bdist:.1%} dist, leg_frac {REF_LF:.0%})")
    print(f"{'take':>12} {'end_equity':>14} {'CAGR':>8} {'maxDD':>8} {'harvests':>9} {'mean harvest ret':>17}")
    for take in (0.05, 0.10, 0.25, 0.50, 1.00, 2.00, 999):
        r, c = run(idx, compact, dte_target=bd, dte_tol=(10 if bd <= 60 else 20),
                   dist=bdist, take=take, leg_frac=REF_LF)
        s = stats(r, c)
        lbl = "no-harvest" if take == 999 else f"+{take:.0%}"
        mh = s["harvest_mean_ret"]
        print(f"{lbl:>12} {s['end_equity']:>14,.0f} {s['cagr']:>+8.0%} {s['max_dd']:>+8.0%} "
              f"{s['n_harvests']:>9} {('' if mh!=mh else f'{mh:+.0%}'):>17}")

    # ---------------------------------------------------------------- 4. BY-YEAR + curves
    hr(f"BY-YEAR (best cell {bd} DTE {bdist:.1%}, take +50%, leg_frac {REF_LF:.0%})")
    r_best, _ = run(idx, compact, dte_target=bd, dte_tol=(10 if bd <= 60 else 20),
                    dist=bdist, take=0.50, leg_frac=REF_LF)
    print(by_year(r_best).to_string())
    r_100, _ = run(idx, compact, dte_target=bd, dte_tol=(10 if bd <= 60 else 20),
                   dist=bdist, take=0.50, leg_frac=0.50)

    _plots(sb, r_best, r_100, bd, bdist, REF_LF)
    print(f"\nsaved strangle_scoreboard.csv, strangle_heatmap.png, strangle_curves.png")


def _plots(sb, r_best, r_100, bd, bdist, ref_lf):
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))
    piv = sb.pivot(index="dte", columns="dist", values="cagr") * 100
    im = axes[0].imshow(piv.values, cmap="RdYlGn", vmin=-60, vmax=60, aspect="auto")
    axes[0].set_xticks(range(len(piv.columns)))
    axes[0].set_xticklabels([f"{d:.1%}" for d in piv.columns])
    axes[0].set_yticks(range(len(piv.index))); axes[0].set_yticklabels(piv.index)
    axes[0].set_xlabel("strike distance"); axes[0].set_ylabel("DTE")
    axes[0].set_title(f"CAGR (%) grid  (take +50%, leg_frac {ref_lf:.0%})")
    for i in range(len(piv.index)):
        for j in range(len(piv.columns)):
            axes[0].text(j, i, f"{piv.values[i,j]:+.0f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=axes[0])

    e1 = pd.Series(r_best["equity"], index=pd.to_datetime(r_best["dates"]))
    e2 = pd.Series(r_100["equity"], index=pd.to_datetime(r_100["dates"]))
    axes[1].plot(e1.index, e1.values, label=f"leg_frac {ref_lf:.0%} (survivable)", color="green")
    axes[1].plot(e2.index, e2.values, label="leg_frac 50% (invest~100%)", color="crimson", lw=1)
    axes[1].axhline(CAP0, color="k", lw=0.6, ls="--")
    axes[1].set_yscale("log"); axes[1].set_ylabel("equity ($, log)")
    axes[1].set_title(f"Best cell {bd} DTE {bdist:.1%} dist -- sizing matters")
    axes[1].legend()
    fig.tight_layout(); fig.savefig(OUT / "strangle_curves.png", dpi=110)
    # keep a standalone heatmap too
    fig.savefig(OUT / "strangle_heatmap.png", dpi=110)


if __name__ == "__main__":
    main()
