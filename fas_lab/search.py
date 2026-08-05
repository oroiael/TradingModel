"""Fit FAS on its own terms, in-sample, then check the choice out-of-sample.

band_lab's cells were SOXL's parameters rescaled. This searches FAS's own grid.
IS  = 2020-07-16 .. 2024-06-30   (parameters chosen here, and only here)
OOS = 2024-07-01 .. 2026-07-21   (never consulted during selection)
"""
import os, sys, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import engine

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
FAS, SOXL = "FAS_5min_6Years.csv", "SOXL_5min_6Years.csv"
IS = ("2020-07-16", "2024-06-30")
OOS = ("2024-07-01", "2026-07-21")
pd.set_option("display.width", 200)


COST = 3.0        # bp per round trip for FAS (SOXL calibrates at 2; FAS is thinner)


def ev(sym, window, cost=COST, **kw):
    d, t = engine.run(sym, start=window[0], end=window[1], cost_bp=cost, **kw)
    return engine.stats(d, t, ""), d


if __name__ == "__main__":
    grid = list(itertools.product(
        [2.5, 3.0, 3.34, 3.74, 4.25, 5.0],            # gate, FAS ATR5 %
        [.0020, .0025, .0030, .0040, .0050, .0055, .0070, .0085, .0100],  # dip = target
        [.015, .0221, .030, .040]))                   # stop
    rows = []
    for g, dt, st in grid:
        s, _ = ev(FAS, IS, gate=g, dip=dt, target=dt, stop=st)
        if s["on_days"] < 150:
            continue
        rows.append(dict(gate=g, dip=dt, stop=st, **{f"is_{k}": v for k, v in s.items() if k != "label"}))
    r = pd.DataFrame(rows)
    r = r.sort_values("is_on_sharpe", ascending=False)
    print(f"{len(r)} cells with >=150 in-sample ON days.  NET of {COST} bp/round-trip.")
    print("TOP 10 BY IN-SAMPLE ON-DAY SHARPE:")
    top = r.head(10).copy()
    print(top[["gate", "dip", "stop", "is_on_days", "is_trades_per_on_day", "is_bp_per_on_day",
               "is_on_sharpe", "is_maxdd"]].to_string(index=False, formatters={
        "dip": "{:.2%}".format, "stop": "{:.2%}".format, "is_bp_per_on_day": "{:+.1f}".format,
        "is_on_sharpe": "{:.2f}".format, "is_maxdd": "{:.1%}".format,
        "is_trades_per_on_day": "{:.2f}".format}))

    print("\nOUT-OF-SAMPLE for those same 10 cells (parameters frozen):")
    oos = []
    for _, x in top.iterrows():
        s, _ = ev(FAS, OOS, gate=x.gate, dip=x.dip, target=x.dip, stop=x.stop)
        oos.append(dict(gate=x.gate, dip=x.dip, stop=x.stop, is_bp=x.is_bp_per_on_day,
                        is_sharpe=x.is_on_sharpe, **{f"oos_{k}": v for k, v in s.items() if k != "label"}))
    o = pd.DataFrame(oos)
    print(o[["gate", "dip", "stop", "is_bp", "is_sharpe", "oos_on_days",
             "oos_bp_per_on_day", "oos_on_sharpe", "oos_maxdd"]].to_string(index=False, formatters={
        "dip": "{:.2%}".format, "stop": "{:.2%}".format, "is_bp": "{:+.1f}".format,
        "is_sharpe": "{:.2f}".format, "oos_bp_per_on_day": "{:+.1f}".format,
        "oos_on_sharpe": "{:.2f}".format, "oos_maxdd": "{:.1%}".format}))
    print(f"\nIS->OOS bp correlation across the top 10: {np.corrcoef(o.is_bp, o.oos_bp_per_on_day)[0,1]:+.3f}")
    print(f"cells positive in-sample: {(o.is_bp>0).sum()}/10   still positive out-of-sample: {(o.oos_bp_per_on_day>0).sum()}/10")

    print("\nSOXL over the same two windows, parameters untouched (the control):")
    for nm, w in [("IS", IS), ("OOS", OOS)]:
        s, _ = ev(SOXL, w, cost=2.0)
        print(f"  SOXL {nm}: ON {s['on_days']:4d}  bp {s['bp_per_on_day']:+.1f}  "
              f"Sharpe {s['on_sharpe']:.2f}  maxDD {s['maxdd']:.1%}")
    r.to_csv(f"{OUT}/fas_grid.csv", index=False); o.to_csv(f"{OUT}/fas_oos.csv", index=False)
