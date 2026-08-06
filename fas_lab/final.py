"""The recommended FAS configuration: plateau check, leverage, and whether it adds
anything to a SOXL sleeve."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import engine

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
FAS, SOXL = "FAS_5min_6Years.csv", "SOXL_5min_6Years.csv"
PICK = dict(gate=4.25, dip=.0030, target=.0030, stop=.030)     # from search.py, IS-selected
COST_F, COST_S = 3.0, 2.0
pd.set_option("display.width", 210)


def go(sym, cost, **kw):
    d, t = engine.run(sym, cost_bp=cost, **kw)
    return engine.stats(d, t, ""), d, t


if __name__ == "__main__":
    print("=" * 128)
    print("PLATEAU CHECK -- is the chosen cell a stable region or a knife edge?  (full sample, net 3bp)")
    print("gate 4.25 / dip=target 0.30% / stop 3.0%; one axis varied at a time")
    print("=" * 128)
    for axis, vals in [("gate", [3.34, 3.74, 4.25, 4.75, 5.25]),
                       ("dip", [.0020, .0025, .0030, .0035, .0040]),
                       ("stop", [.020, .025, .030, .035, .040])]:
        line = []
        for v in vals:
            kw = dict(PICK)
            kw[axis] = v
            if axis == "dip": kw["target"] = v
            s, _, _ = go(FAS, COST_F, **kw)
            line.append(f"{v if axis=='gate' else f'{v:.2%}'}: {s['bp_per_on_day']:+5.1f}bp/"
                        f"{s['on_sharpe']:.2f}({s['on_days']})")
        print(f"  {axis:5s} " + "   ".join(line))

    print("\n" + "=" * 128)
    print("THE RECOMMENDED FAS SLEEVE vs SOXL (full sample 2020-07..2026-07, net of costs)")
    print("=" * 128)
    rows = []
    sS, dS, tS = go(SOXL, COST_S)
    sS["label"] = "SOXL locked (net 2bp)"; rows.append(sS)
    for lev in (1.0, 2.0, 3.0):
        s, d, t = go(FAS, COST_F, lev=lev, **PICK)
        s["label"] = f"FAS recommended, lev {lev:.0f}x"; rows.append(s)
        if lev == 1.0: dF = d
    C = ["on_days", "on_rate", "trades_per_on_day", "bp_per_on_day", "on_sharpe",
         "maxdd", "cagr", "win_rate", "worst_day", "yrs_pos"]
    print(pd.DataFrame(rows).set_index("label")[C].to_string(formatters={
        "on_rate": "{:.0%}".format, "trades_per_on_day": "{:.2f}".format,
        "bp_per_on_day": "{:+.1f}".format, "on_sharpe": "{:.2f}".format,
        "maxdd": "{:.1%}".format, "cagr": "{:+.1%}".format,
        "win_rate": "{:.1%}".format, "worst_day": "{:.1%}".format}))

    print("\nby calendar year (sum of daily net returns):")
    yr = pd.DataFrame({"SOXL": dS.ret.groupby(dS.index.year).sum() * 100,
                       "FAS recommended": dF.ret.groupby(dF.index.year).sum() * 100,
                       "FAS ON days": dF.on.groupby(dF.index.year).sum()})
    print(yr.to_string(float_format=lambda v: f"{v:+.1f}"))

    print("\n" + "=" * 128)
    print("DOES FAS EARN INDEPENDENTLY?  (band_lab found SPXL and FAS both LOSE when SOXL is idle)")
    print("=" * 128)
    j = pd.DataFrame({"fas": dF.ret, "fas_on": dF.on, "soxl_on": dS.on, "soxl": dS.ret}).dropna()
    both = j[j.fas_on & j.soxl_on]; only = j[j.fas_on & ~j.soxl_on]
    print(f"  FAS ON and SOXL ON : n={len(both):4d}   FAS {both.fas.mean()*1e4:+.1f} bp/day"
          f"   cumulative {both.fas.sum()*100:+.1f}%")
    print(f"  FAS ON, SOXL IDLE  : n={len(only):4d}   FAS {only.fas.mean()*1e4:+.1f} bp/day"
          f"   cumulative {only.fas.sum()*100:+.1f}%")
    if len(both) > 2:
        print(f"  correlation of daily returns on both-ON days: {both.fas.corr(both.soxl):+.3f}")

    print("\n" + "=" * 128)
    print("PORTFOLIO -- does adding a FAS sleeve improve a SOXL book? (w each, rest cash)")
    print("=" * 128)
    for wS, wF in [(1.0, 0.0), (0.9, 0.1), (0.75, 0.25), (0.5, 0.5), (0.0, 1.0)]:
        r = (wS * j.soxl + wF * j.fas)
        eq = (1 + r).cumprod(); yrs = (j.index[-1] - j.index[0]).days / 365.25
        print(f"  SOXL {wS:.2f} / FAS {wF:.2f}:  CAGR {eq.iloc[-1]**(1/yrs)-1:+7.1%}   "
              f"maxDD {(eq/eq.cummax()-1).min():7.1%}   Sharpe {r.mean()/r.std()*np.sqrt(252):5.2f}")
    dF.to_csv(f"{OUT}/fas_recommended_days.csv")
