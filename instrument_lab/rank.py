"""Rank instruments as weekly covered-call underlyings, and state the spec."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import screen as sc
from ibkr_weekly import SPY, XLU

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
W = pd.Timestamp("2022-01-01")


def rets(px):
    s = pd.Series(px)
    return s.pct_change().dropna()


if __name__ == "__main__":
    soxl = sc.weekly_from_5min("SOXL_5min_6Years.csv")
    fas = sc.weekly_from_5min("FAS_5min_6Years.csv")
    universe = [
        ("SOXL   3x semis",        soxl[soxl.index >= W], 1.0),
        ("FAS    3x financials",   fas[fas.index >= W], 1.0),
        ("semis  1x (SOXL/3)",     soxl[soxl.index >= W], 1 / 3),
        ("fin    1x (FAS/3)",      fas[fas.index >= W], 1 / 3),
        ("SPY    S&P 500",         rets(SPY), 1.0),
        ("XLU    utilities",       rets(XLU), 1.0),
        ("SPY    2x synthetic",    rets(SPY), 2.0),
        ("XLU    3x synthetic",    rets(XLU), 3.0),
    ]
    rows = [sc.profile(r, l, scale=s) for l, r, s in universe]
    d = pd.DataFrame(rows).set_index("instrument")
    # best strike per instrument
    best = []
    for l, r, s in universe:
        sw = sc.delta_sweep(r, l, scale=s,
                            deltas=(0.40, 0.30, 0.25, 0.20, 0.15, 0.10, 0.05))
        b = sw.loc[sw.edge_ann.idxmax()]
        best.append(dict(instrument=l, best_delta=b.delta, best_otm=b.otm,
                         best_prem_wk=b.prem, best_edge_ann=b.edge_ann,
                         p_assign=b.p_assign))
    bd = pd.DataFrame(best).set_index("instrument")
    out = d[["ann_drift", "ann_vol", "skew", "kurt"]].join(bd)
    out["prem_ann"] = out.best_prem_wk * 52
    out = out.sort_values("best_edge_ann", ascending=False)
    print("=" * 134)
    print("WEEKLY COVERED-CALL SCREEN. Premium priced at the instrument's OWN realised vol,")
    print("i.e. assuming ZERO variance risk premium -- so any positive edge is structural,")
    print("earned from drift and shape alone, before the market pays you a single vol point.")
    print("edge = covered call MINUS buy & hold, exactly.  2022-01 -> 2026-08.")
    print("=" * 134)
    print(out.to_string(formatters={
        "ann_drift": "{:+.1%}".format, "ann_vol": "{:.1%}".format, "skew": "{:+.2f}".format,
        "kurt": "{:.1f}".format, "best_delta": "{:.2f}".format, "best_otm": "{:.2%}".format,
        "best_prem_wk": "{:.3%}".format, "best_edge_ann": "{:+.2%}".format,
        "p_assign": "{:.1%}".format, "prem_ann": "{:.1%}".format}))
    print("\nNote: these are PRICE returns. Dividends accrue to the holder and are NOT capped")
    print("by the call, and ex-div drops lower the price drift the call has to overcome --")
    print("so a high yield helps twice. XLU ~3%/yr and SPY ~1.2%/yr sit on top of the edge above.")

    print("\n" + "=" * 134)
    print("WHAT DRIVES IT -- annualised edge with one property neutralised at a time")
    print("=" * 134)
    cf = pd.DataFrame([sc.counterfactual(r, l, scale=s) for l, r, s in universe]).set_index("instrument")
    cf["drift_cost"] = cf.actual - cf.no_drift
    cf["skew_cost"] = cf.actual - cf.skew_flipped
    print(cf.to_string(float_format=lambda v: f"{v:+.2%}"))
    out.to_csv(f"{OUT}/screen_rank.csv"); cf.to_csv(f"{OUT}/screen_drivers.csv")

    print("\n" + "=" * 134)
    print("SENSITIVITY OF THE EDGE TO DRIFT -- the single dominant variable")
    print("=" * 134)
    base = rets(SPY)
    print("  SPY's own return series, shifted to different annual drifts, 20-delta strike:")
    for tgt in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50):
        r = base - base.mean() + tgt / 52
        p = sc.profile(r, "", delta_tgt=0.20)
        print(f"    drift {tgt:+5.0%}/yr -> weekly premium {p['prem_pct']:.3%}, "
              f"cap cost {p['cap_pct']:.3%}, edge {p['edge_ann']:+.2%}/yr")
