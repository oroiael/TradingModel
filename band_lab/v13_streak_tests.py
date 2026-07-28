"""
V13 mini-program — streak-based de-risking (drawdown-mechanism defense).

Motivation: the sleeve's max drawdown (-36.5%) is a SEQUENCE of capped
losing days during chop (SOXL rose +11.9% through the worst episode), so
directional hedges (puts: tested, fail; SOXS: marginal) miss the
mechanism. The only untested defense that targets sequences directly is
sizing on the streak itself.

PRESPECIFIED (fixed before running):
  T1 measurement — E[next ON-day pnl | k consecutive losing ON-days],
     k = 0..4+, and E[next | trailing-10-ON-day sum bucket]. If losing
     streaks carry NO negative continuation signal, the rules below are
     expected to fail (halving after losses just halves the recovery).
  T2 rules (exactly three, decided from prior days only, no lookahead):
     R1: f=0.5 after 2 consecutive losing ON-days; back to 1 after any
         winning ON-day.
     R2: f=0.5 after 1 losing ON-day; restore after a winner.
     R3: f=0.5 while trailing-10-ON-day sum < -10%; restore when >= 0.
  Adoption bar: maxDD improvement >= 5 pts with proportionally smaller
  CAGR cost, consistent by-year, mechanism visible in the 2025-11..
  2026-03 episode. Otherwise rejected and documented.

Outputs: band_lab/out/v13_results.csv + printed report.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from put_overlay_test import core_series

OUT = os.path.join(HERE, "out")

def equity_stats(f_ser, on, daily_index, label):
    """f_ser: per-ON-day sizing fraction; on: ON-day pnl series."""
    r = (f_ser * on)
    full = r.reindex(daily_index).fillna(0.0)
    eq = (1 + full).cumprod()
    pk = eq.cummax()
    dd = ((eq - pk) / pk)
    yrs = (daily_index[-1] - daily_index[0]).days / 365.25
    ep = dd.loc["2025-11-01":"2026-05-15"]
    return {"variant": label,
            "bp_ON_day": round(r.mean() * 1e4, 1),
            "cal_cagr_pct": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
            "max_dd_pct": round(dd.min() * 100, 1),
            "episode_dd_pct": round(ep.min() * 100, 1),
            "avg_f": round(f_ser.mean(), 2)}

def main():
    daily, full = core_series()
    on = full[full != 0.0].sort_index()      # ON-day pnl (f=1 base)

    # ---------------- T1 measurement
    print("=" * 66); print("T1. IS THERE A STREAK SIGNAL?"); print("=" * 66)
    loss = (on < 0).to_numpy()
    streak = np.zeros(len(on), dtype=int)    # losing streak BEFORE day i
    for i in range(1, len(on)):
        streak[i] = streak[i - 1] + 1 if loss[i - 1] else 0
    t1 = pd.DataFrame({"streak": np.minimum(streak, 4), "pnl": on.to_numpy()})
    tab = t1.groupby("streak")["pnl"].agg(["count", "mean", "std"])
    tab["mean_bp"] = (tab["mean"] * 1e4).round(1)
    tab["shp"] = (tab["mean"] / tab["std"] * np.sqrt(252)).round(2)
    print("E[ON-day pnl | k prior consecutive losing ON-days]  (4 = 4+):")
    print(tab[["count", "mean_bp", "shp"]].to_string())
    roll10 = on.rolling(10).sum().shift(1)
    b = pd.cut(roll10, [-np.inf, -.10, 0, .10, np.inf],
               labels=["<-10%", "-10..0", "0..10%", ">10%"])
    tb = on.groupby(b, observed=True).agg(["count", "mean"])
    tb["mean_bp"] = (tb["mean"] * 1e4).round(1)
    print("\nE[ON-day pnl | trailing-10-ON-day sum]:")
    print(tb[["count", "mean_bp"]].to_string())

    # ---------------- T2 rules
    print(); print("=" * 66); print("T2. RULES"); print("=" * 66)
    f_base = pd.Series(1.0, index=on.index)
    # R1 / R2
    f_r1 = pd.Series(np.where(streak >= 2, 0.5, 1.0), index=on.index)
    f_r2 = pd.Series(np.where(streak >= 1, 0.5, 1.0), index=on.index)
    # R3 state machine on trailing-10 sum (prior days only)
    f_r3 = []
    half = False
    for d in on.index:
        s10 = roll10.get(d, np.nan)
        if not np.isnan(s10):
            if not half and s10 < -.10:
                half = True
            elif half and s10 >= 0:
                half = False
        f_r3.append(0.5 if half else 1.0)
    f_r3 = pd.Series(f_r3, index=on.index)

    rows = [equity_stats(f_base, on, daily.index, "baseline f=1"),
            equity_stats(f_r1, on, daily.index, "R1 half after 2 losses"),
            equity_stats(f_r2, on, daily.index, "R2 half after 1 loss"),
            equity_stats(f_r3, on, daily.index, "R3 half in -10% trailing DD")]
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    df.to_csv(os.path.join(OUT, "v13_results.csv"), index=False)
    # by-year for baseline vs best rule
    for nm, f_ in [("baseline", f_base), ("R1", f_r1), ("R3", f_r3)]:
        r = f_ * on
        print(f"  {nm:9s} by year (bp/ON-day):",
              {y: round(v * 1e4, 1) for y, v in r.groupby(r.index.year).mean().items()})

if __name__ == "__main__":
    main()
