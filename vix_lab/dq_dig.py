"""Two follow-ups the first pass raised.

1. The "split jump" flags on 2020-03-09 and 2024-08-05. A reverse split and a
   genuine gap look identical in one series; they do not look identical in two.
   If VXX gapped the same way on the same day it was the market, not a split.

2. The 2022 residual cluster (corr 0.888 vs ~0.9997 every other year). Locate
   the fault: is it UVXY, is it VXX, or is it the way the daily close is taken?
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dq_uvxy import ROOT, hdr, load_raw  # noqa: E402


def daily(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("date").agg(o=("Open", "first"), h=("High", "max"),
                                  l=("Low", "min"), c=("Close", "last"),
                                  v=("Volume", "sum"), n=("Close", "size"))


def main() -> None:
    uvxy = load_raw(os.path.join(ROOT, "UVXY_1min.csv"))
    vxx = load_raw(os.path.join(ROOT, "VXX_5min_6Years.csv"))
    du, dv = daily(uvxy), daily(vxx)

    # ---------------------------------------------------------------- (1)
    hdr("1. Are 2020-03-09 and 2024-08-05 splits, or real gaps?")
    print("A reverse split multiplies UVXY's price and leaves VXX alone.")
    print("A VIX event moves both. VXX's own gap is the discriminator.\n")
    print(f"{'date':<12}{'UVXY gap':>10}{'VXX gap':>10}{'UVXY day':>10}"
          f"{'VXX day':>10}  note")
    for d in ("2020-03-09", "2024-08-05"):
        t = pd.Timestamp(d)
        pu = du.index[du.index.get_indexer([t]) [0] - 1]
        gu = du.loc[t, "o"] / du.loc[pu, "c"] - 1
        iu = du.loc[t, "c"] / du.loc[t, "o"] - 1
        if t in dv.index:
            pv = dv.index[dv.index.get_indexer([t])[0] - 1]
            gv = dv.loc[t, "o"] / dv.loc[pv, "c"] - 1
            iv = dv.loc[t, "c"] / dv.loc[t, "o"] - 1
            note = "both gapped -> real event" if abs(gv) > 0.15 else "VXX flat -> SPLIT"
        else:
            gv = iv = float("nan")
            note = "no VXX coverage"
        print(f"{d:<12}{gu:>9.1%}{gv:>10.1%}{iu:>10.1%}{iv:>10.1%}  {note}")

    print("\nAny *downward* session-boundary jump (the signature a raw series")
    print("would show if it had a forward split, and the shape a botched")
    print("back-adjustment leaves behind):")
    r = du["o"] / du["c"].shift(1)
    down = r[r < 0.80].dropna()
    print(f"  jumps below -20% overnight: {len(down)}")
    for d, x in down.items():
        gv = (dv.loc[d, "o"] / dv["c"].shift(1).loc[d] - 1) if d in dv.index else float("nan")
        print(f"    {d.date()}  UVXY {x - 1:+.1%}   VXX {gv:+.1%}")

    # decay implied by the series
    yrs = (du.index[-1] - du.index[0]).days / 365.25
    cagr = (du["c"].iloc[-1] / du["c"].iloc[0]) ** (1 / yrs) - 1
    print(f"\nimplied CAGR of the series: {cagr:.1%}/yr over {yrs:.2f} years")
    print("  (UVXY's published long-run decay is roughly -60% to -75%/yr; a")
    print("   RAW series would instead show large upward split jumps and a")
    print("   much shallower drift)")

    # ---------------------------------------------------------------- (2)
    hdr("2. The 2022 residual cluster — which file is at fault?")
    print("VXX bars/session by year (the 5-minute file should hold 78):")
    print(f"{'year':<8}{'sessions':>10}{'n=78':>8}{'n<78':>8}{'min n':>8}{'median n':>10}")
    for y, g in dv.groupby(dv.index.year):
        print(f"{y:<8}{len(g):>10}{int((g['n'] == 78).sum()):>8}"
              f"{int((g['n'] < 78).sum()):>8}{int(g['n'].min()):>8}"
              f"{g['n'].median():>10.0f}")

    print("\nUVXY bars/session by year (1-minute file, 390 expected):")
    print(f"{'year':<8}{'sessions':>10}{'n=390':>8}{'n<390':>8}{'min n':>8}")
    for y, g in du.groupby(du.index.year):
        print(f"{y:<8}{len(g):>10}{int((g['n'] == 390).sum()):>8}"
              f"{int((g['n'] < 390).sum()):>8}{int(g['n'].min()):>8}")

    # close-to-close vs open-to-close: does the fault live in the overnight?
    j = pd.concat([du["c"].pct_change().rename("u_cc"),
                   dv["c"].pct_change().rename("v_cc"),
                   (du["c"] / du["o"] - 1).rename("u_oc"),
                   (dv["c"] / dv["o"] - 1).rename("v_oc")], axis=1).dropna()
    print("\nbeta / corr computed two ways, by year:")
    print(f"{'year':<7}{'n':>5}{'beta cc':>10}{'corr cc':>10}"
          f"{'beta oc':>10}{'corr oc':>10}")
    for y, g in j.groupby(j.index.year):
        bcc = float((g.u_cc * g.v_cc).sum() / (g.v_cc ** 2).sum())
        boc = float((g.u_oc * g.v_oc).sum() / (g.v_oc ** 2).sum())
        print(f"{y:<7}{len(g):>5}{bcc:>10.4f}{g.u_cc.corr(g.v_cc):>10.5f}"
              f"{boc:>10.4f}{g.u_oc.corr(g.v_oc):>10.5f}")

    print("\nThe 8 worst close-to-close residual days, opened up:")
    resid = j.u_cc - 1.5 * j.v_cc
    print(f"{'date':<12}{'UVXY cc':>9}{'VXX cc':>9}{'UVXY oc':>9}{'VXX oc':>9}"
          f"{'VXX bars':>9}{'VXX last':>10}")
    for d in resid.abs().nlargest(8).index:
        lastbar = vxx.loc[vxx["date"] == d, "dt"].max()
        print(f"{str(d.date()):<12}{j.loc[d,'u_cc']*100:>9.2f}{j.loc[d,'v_cc']*100:>9.2f}"
              f"{j.loc[d,'u_oc']*100:>9.2f}{j.loc[d,'v_oc']*100:>9.2f}"
              f"{int(dv.loc[d,'n']):>9}"
              f"{lastbar.strftime('%H:%M'):>10}")

    # Is VXX's 2022 series internally sane? A 1x VIX-futures ETN cannot make
    # a smaller move than a 1.5x one on the same index, day after day.
    hdr("3. VXX 2022 internal sanity")
    y22 = j[j.index.year == 2022]
    ratio = (y22.u_cc / y22.v_cc).replace([np.inf, -np.inf], np.nan).dropna()
    ratio = ratio[y22.v_cc.abs() > 0.01]     # avoid dividing by noise
    print(f"UVXY/VXX daily-return ratio on days |VXX| > 1%  (n={len(ratio)}):")
    print(f"  median {ratio.median():.3f}   IQR {ratio.quantile(.25):.3f}"
          f"-{ratio.quantile(.75):.3f}   min {ratio.min():.2f}  max {ratio.max():.2f}")
    off = y22[(y22.u_cc - 1.5 * y22.v_cc).abs() > 0.03]
    print(f"days in 2022 off the 1.5x line by >3%: {len(off)} of {len(y22)}")
    print("\nsame statistic for 2023 (the control year):")
    y23 = j[j.index.year == 2023]
    off23 = y23[(y23.u_cc - 1.5 * y23.v_cc).abs() > 0.03]
    print(f"days in 2023 off the 1.5x line by >3%: {len(off23)} of {len(y23)}")

    # Does the VXX file's own close move when we take 15:55 instead of last bar?
    print("\nVXX 2022 — distribution of the last bar's timestamp:")
    v22 = vxx[vxx["date"].dt.year == 2022]
    lastbars = v22.groupby("date")["dt"].max().dt.strftime("%H:%M")
    print("  " + ", ".join(f"{k}:{v}" for k, v in lastbars.value_counts().items()))
    print("\nUVXY 2022 — distribution of the last bar's timestamp:")
    u22 = uvxy[uvxy["date"].dt.year == 2022]
    lb = u22.groupby("date")["dt"].max().dt.strftime("%H:%M")
    print("  " + ", ".join(f"{k}:{v}" for k, v in lb.value_counts().items()))


if __name__ == "__main__":
    main()
