"""
Generalized transfer + vol-scaling test for any 3x ETF, plus the
churn-density comparison and the SOXL capital-overlap analysis.

STATUS: EXPLORATORY for every instrument except SOXL. Nothing here is
adopted. Adoption would require the full protocol (prespecified plan,
walk-forward with prior-years-only selection, plateau support, mechanism
attribution).

Per instrument the scale factor k = median daily range / SOXL's 6.67%.
Cells (same structure as the SPXL run in MASTER §9.1):
  A locked          gate 6.00, dip/tgt 1.0%,  stop 4%
  B gate-scaled     gate = percentile-matched to SOXL's 52% ON-rate
  C gate+dip scaled gate matched, dip/tgt = round(1.0% x k, 2)
  D fully scaled    as C, stop = 4% x k

Usage: python3 etf_scaling_test.py FAS [SPXL TQQQ ...]
Outputs: band_lab/out/etf_scaling_<SYM>.csv, etf_churn_density.csv,
         etf_overlap_<SYM>.csv
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cycle_lab"))
sys.path.insert(0, HERE)
from transfer_test import load_symbol, build_daily
from spxl_scaling_test import sim
from band_analysis import zigzag_legs

OUT = os.path.join(HERE, "out")
SOXL_MEDIAN_RANGE = 6.67
SOXL_ON_RATE = 0.521

def profile(sym):
    bars = load_symbol(sym)
    d, g = build_daily(bars)
    z1, z2 = [], []
    for dd, gb in g:
        h = gb["High"].to_numpy(); l = gb["Low"].to_numpy()
        z1.append(zigzag_legs(h, l, 0.01)); z2.append(zigzag_legs(h, l, 0.02))
    z1 = np.array(z1); z2 = np.array(z2)
    med = d["range_pct"].median()
    k = med / SOXL_MEDIAN_RANGE
    gate_matched = float(np.nanquantile(d["atr5"].dropna(), 1 - SOXL_ON_RATE))
    return {"symbol": sym, "median_range_%": round(med, 2), "scale_k": round(k, 3),
            "swings_1pct_mean": round(z1.mean(), 1),
            "swings_1pct_median": int(np.median(z1)),
            "swings_2pct_mean": round(z2.mean(), 1),
            "zero_swing_days_%": round((z1 == 0).mean() * 100, 1),
            "gate_matched_%": round(gate_matched, 2),
            "gate6_ON_rate_%": round((d["atr5"] >= 6).mean() * 100, 1)}, d, g, k, gate_matched

def run_cell(d, g, gate, dip, tgt, stop, label):
    v9 = (d["or30"] < d["thr80"]) | ((d["or30"] >= d["thr80"]) & (d["pos10"] >= 2/3))
    on_mask = v9 & (d["atr5"] >= gate)
    pnl, ntr, gaps = {}, [], []
    for dd, gb in g:
        if not on_mask.get(dd, False) or len(gb) < 20:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        p, t, gp = sim(o, h, l, c, dip, tgt, stop)
        pnl[dd] = p; ntr.append(t); gaps += gp
    on = pd.Series(pnl).sort_index()
    cal = d.index; yrs = (cal[-1] - cal[0]).days / 365.25
    eq = (1 + on.reindex(cal).fillna(0.0)).cumprod(); pk = eq.cummax()
    sh = on.mean() / on.std() * np.sqrt(252) if len(on) > 2 and on.std() > 0 else np.nan
    gp = np.array(gaps) if gaps else np.array([0])
    yr = on.groupby(on.index.year).mean() * 1e4 if len(on) else pd.Series(dtype=float)
    return {"cell": label, "gate": round(gate, 2), "dip_tgt_%": round(dip * 100, 2),
            "stop_%": round(stop * 100, 2), "ON_days": len(on),
            "trades_per_ON_day": round(np.mean(ntr), 2) if ntr else 0,
            "bp_per_ON_day": round(on.mean() * 1e4, 1) if len(on) else np.nan,
            "sharpe": round(sh, 2) if not np.isnan(sh) else np.nan,
            "win_%": round((on > 0).mean() * 100, 1) if len(on) else np.nan,
            "worst_day_%": round(on.min() * 100, 1) if len(on) else np.nan,
            "maxDD_%": round(((eq - pk) / pk).min() * 100, 1),
            "CAGR_%": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
            "yrs_positive": f"{int((yr > 0).sum())}/{len(yr)}" if len(yr) else "-",
            "same_bar_exit_%": round((gp == 0).mean() * 100, 1)}, on

def main():
    syms = sys.argv[1:] or ["FAS"]
    # SOXL reference (locked)
    ref_prof, dS, gS, _, _ = profile("SOXL")
    ref_row, soxl_on = run_cell(dS, gS, 6.0, .01, .01, .04, "SOXL locked (reference)")
    prof_rows = [ref_prof]

    for sym in syms:
        p, d, g, k, gm = profile(sym)
        prof_rows.append(p)
        dip = round(0.01 * k, 4)
        cells = [("A locked",          6.0, .01, .01, .04),
                 ("B gate-scaled",     gm,  .01, .01, .04),
                 ("C gate+dip scaled", gm,  dip, dip, .04),
                 ("D fully scaled",    gm,  dip, dip, round(.04 * k, 4))]
        rows, sers = [], {}
        for label, gate, dp, tg, st in cells:
            r, on = run_cell(d, g, gate, dp, tg, st, label)
            rows.append(r); sers[label] = on
        rows.append(ref_row)
        df = pd.DataFrame(rows)
        print("\n" + "=" * 112)
        print(f"{sym} — vol-scaled cells (k={k:.3f}, matched gate {gm:.2f}%) — EXPLORATORY")
        print("=" * 112)
        print(df.to_string(index=False))
        df.to_csv(os.path.join(OUT, f"etf_scaling_{sym}.csv"), index=False)
        for label, on in sers.items():
            if len(on):
                print(f"  {label:20s} by year:",
                      {int(y): round(v * 1e4, 1)
                       for y, v in on.groupby(on.index.year).mean().items()})
        # overlap vs SOXL using cell C
        c = sers["C gate+dip scaled"]
        both = c.index.intersection(soxl_on.index)
        only = c.index.difference(soxl_on.index)
        print(f"\n  OVERLAP vs SOXL (cell C): both ON {len(both)} | {sym}-only {len(only)}"
              f" | SOXL-only {len(soxl_on.index.difference(c.index))}")
        if len(both) > 2:
            print(f"    corr on both-ON days: {c[both].corr(soxl_on[both]):.2f}")
            print(f"    {sym} mean when SOXL ON:   {c[both].mean()*1e4:+.1f} bp")
            print(f"    {sym} mean when SOXL IDLE: {c[only].mean()*1e4:+.1f} bp "
                  f"(n={len(only)}, cumulative {c[only].sum()*100:+.1f}% of capital)")
        pd.DataFrame([{"symbol": sym, "both_on": len(both), "sym_only": len(only),
                       "corr_both_on": round(c[both].corr(soxl_on[both]), 3)
                       if len(both) > 2 else np.nan,
                       "bp_when_soxl_on": round(c[both].mean() * 1e4, 1) if len(both) else np.nan,
                       "bp_when_soxl_idle": round(c[only].mean() * 1e4, 1) if len(only) else np.nan
                       }]).to_csv(os.path.join(OUT, f"etf_overlap_{sym}.csv"), index=False)

    pdf = pd.DataFrame(prof_rows)
    print("\n" + "=" * 112)
    print("CHURN DENSITY — is SOXL unique among 3x ETFs?")
    print("=" * 112)
    print(pdf.to_string(index=False))
    pdf.to_csv(os.path.join(OUT, "etf_churn_density.csv"), index=False)

if __name__ == "__main__":
    main()
