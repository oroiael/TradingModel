"""
SPXL vol-scaled variants + SOXL/SPXL capital-overlap analysis.

STATUS: EXPLORATORY. Nothing here is adopted. These cells are a first
pass to see whether the mechanism survives on SPXL once the SOXL-
calibrated constants are rescaled to SPXL's volatility. Adoption would
require the full protocol used for every SOXL variable (prespecified
plan, walk-forward with prior-years-only selection, plateau support,
mechanism attribution) — none of which is run here.

Two separate knobs, commonly conflated:
  GATE  (ATR5 threshold) decides WHICH DAYS trade  -> why SPXL fired on
        only 63 days under locked settings
  DIP   (entry trigger)  decides HOW MANY TRADES per active day

Scaling factor: SPXL median daily range 2.92% / SOXL 6.67% = 0.44.
Two independent derivations of the gate agree: 6.0 x 0.44 = 2.6, and the
percentile-matched threshold (same 52% ON-rate as SOXL) = 2.94.

Prespecified cells:
  A locked            gate 6.00, dip/tgt 1.0%, stop 4%   (the §9 result)
  B gate-scaled       gate 2.94, dip/tgt 1.0%, stop 4%
  C gate+dip scaled   gate 2.94, dip/tgt 0.5%, stop 4%   (user's suggestion)
  D fully scaled      gate 2.94, dip/tgt 0.5%, stop 2%   (stop scaled too)
Plus a resolution diagnostic: with 0.5% levels on 5-min bars, how often
do entry and exit land in the same or the immediately following bar?
(High same-bar rates mean the result is an artifact of bar coarseness
and needs 1-minute data before it can be believed.)

Outputs: band_lab/out/spxl_scaling.csv, band_lab/out/sleeve_overlap.csv
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cycle_lab"))
sys.path.insert(0, HERE)
from transfer_test import load_symbol, build_daily

OUT = os.path.join(HERE, "out")
START_I, MAXTR, MAXSTOP = 18, 5, 2

def sim(o, h, l, c, dip, tgt, stop):
    """Corrected engine + breaker. Also returns bar-gap diagnostics."""
    roll_hi = h[:START_I].max()
    state = 0; entry = 0.0; entry_i = -1
    pnl = 0.0; trades = 0; stops = 0
    gaps = []                      # bars between entry and exit
    for i in range(START_I, len(c)):
        if state == 1:
            t_, s_ = entry * (1 + tgt), entry * (1 - stop)
            if l[i] <= s_:
                pnl += -stop if o[i] > s_ else o[i] / entry - 1
                stops += 1; state = 0; gaps.append(i - entry_i)
            elif i > entry_i and h[i] >= t_:
                pnl += tgt if o[i] < t_ else o[i] / entry - 1
                state = 0; gaps.append(i - entry_i)
        if state == 0 and trades < MAXTR and stops < MAXSTOP:
            trig = roll_hi * (1 - dip)
            if l[i] <= trig:
                entry = min(trig, o[i]); entry_i = i; state = 1; trades += 1
                s_ = entry * (1 - stop)
                if l[i] <= s_:
                    pnl += -stop if o[i] > s_ else min(o[i] / entry - 1, -stop)
                    stops += 1; state = 0; gaps.append(0)
        roll_hi = max(roll_hi, h[i])
    if state == 1:
        pnl += c[-1] / entry - 1; gaps.append(len(c) - 1 - entry_i)
    return pnl, trades, gaps

def run_cfg(sym, gate, dip, tgt, stop, label):
    bars = load_symbol(sym)
    d, g = build_daily(bars)
    v9 = (d["or30"] < d["thr80"]) | ((d["or30"] >= d["thr80"]) & (d["pos10"] >= 2/3))
    on_mask = v9 & (d["atr5"] >= gate)
    pnl, ntr, allgaps = {}, [], []
    for dd, gb in g:
        if not on_mask.get(dd, False) or len(gb) < 20:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        p, t, gp = sim(o, h, l, c, dip, tgt, stop)
        pnl[dd] = p; ntr.append(t); allgaps += gp
    on = pd.Series(pnl).sort_index()
    cal = d.index; yrs = (cal[-1] - cal[0]).days / 365.25
    fullc = on.reindex(cal).fillna(0.0)
    eq = (1 + fullc).cumprod(); pk = eq.cummax()
    sh = on.mean() / on.std() * np.sqrt(252) if len(on) > 2 and on.std() > 0 else np.nan
    gp = np.array(allgaps) if allgaps else np.array([0])
    yrly = on.groupby(on.index.year).mean() * 1e4
    return {
        "cell": label, "gate": gate, "dip_tgt_%": dip * 100, "stop_%": stop * 100,
        "ON_days": len(on), "trades_per_ON_day": round(np.mean(ntr), 2) if ntr else 0,
        "bp_per_ON_day": round(on.mean() * 1e4, 1) if len(on) else np.nan,
        "sharpe": round(sh, 2) if not np.isnan(sh) else np.nan,
        "win_%": round((on > 0).mean() * 100, 1) if len(on) else np.nan,
        "worst_day_%": round(on.min() * 100, 1) if len(on) else np.nan,
        "maxDD_%": round(((eq - pk) / pk).min() * 100, 1),
        "CAGR_%": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
        "yrs_positive": f"{int((yrly > 0).sum())}/{len(yrly)}",
        "same_bar_exit_%": round((gp == 0).mean() * 100, 1),
        "exit_within_1bar_%": round((gp <= 1).mean() * 100, 1),
    }, on

def main():
    print("=" * 108)
    print("SPXL VOL-SCALED CELLS — EXPLORATORY, NOT ADOPTED")
    print("=" * 108)
    cells = [
        ("A locked (§9)",        6.00, .010, .010, .04),
        ("B gate-scaled",        2.94, .010, .010, .04),
        ("C gate+dip scaled",    2.94, .005, .005, .04),
        ("D fully scaled",       2.94, .005, .005, .02),
    ]
    rows, sers = [], {}
    for label, gate, dip, tgt, stop in cells:
        r, on = run_cfg("SPXL", gate, dip, tgt, stop, label)
        rows.append(r); sers[label] = on
    # SOXL reference on the same engine
    r_soxl, on_soxl = run_cfg("SOXL", 6.00, .010, .010, .04, "SOXL reference")
    rows.append(r_soxl)
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    df.to_csv(os.path.join(OUT, "spxl_scaling.csv"), index=False)
    print("\nby-year bp/ON-day:")
    for label, on in sers.items():
        if len(on):
            print(f"  {label:22s}",
                  {int(y): round(v * 1e4, 1) for y, v in on.groupby(on.index.year).mean().items()})
    print(f"  {'SOXL reference':22s}",
          {int(y): round(v * 1e4, 1) for y, v in on_soxl.groupby(on_soxl.index.year).mean().items()})

    # ---------------- capital / overlap analysis
    print()
    print("=" * 108)
    print("CAPITAL & OVERLAP — can the two sleeves share an account?")
    print("=" * 108)
    best = "C gate+dip scaled"
    sp = sers[best]
    both = sp.index.intersection(on_soxl.index)
    only_sp = sp.index.difference(on_soxl.index)
    only_sx = on_soxl.index.difference(sp.index)
    print(f"SPXL cell used for overlap: {best}")
    print(f"  SOXL ON days {len(on_soxl)} | SPXL ON days {len(sp)} | BOTH ON {len(both)}")
    print(f"  SPXL-only days {len(only_sp)} (SOXL idle) | SOXL-only days {len(only_sx)}")
    if len(both) > 2:
        print(f"  correlation of daily P&L on days BOTH are on: "
              f"{sp[both].corr(on_soxl[both]):.2f}")
        print(f"  SPXL mean on both-on days {sp[both].mean()*1e4:+.1f} bp | "
              f"on SPXL-only days {sp[only_sp].mean()*1e4:+.1f} bp")
    ov = pd.DataFrame([{"soxl_on": len(on_soxl), "spxl_on": len(sp),
                        "both_on": len(both), "spxl_only": len(only_sp),
                        "soxl_only": len(only_sx),
                        "corr_both_on": round(sp[both].corr(on_soxl[both]), 3)
                        if len(both) > 2 else np.nan}])
    ov.to_csv(os.path.join(OUT, "sleeve_overlap.csv"), index=False)
    print("\n  Capital reading: days where BOTH fire need capital for two")
    print("  simultaneous positions (or half-size each); SPXL-only days are")
    print("  free diversification (SOXL idle, capital otherwise unused).")

if __name__ == "__main__":
    main()
