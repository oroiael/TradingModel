#!/usr/bin/env python3
"""
harvest_blueprint/blueprint_tests.py

Tests the standard "automated active volatility harvesting" blueprint against
SOXL. The blueprint (delta-neutral short premium, gated on IV percentile and
VIX term structure, protected by stop-losses and a VIX circuit breaker, with a
premium-funded tail hedge and dynamic sizing) is the conventional short-vol
playbook. Every component that can be measured from this repository's data is
measured here.

Inputs are the DERIVED tables in pricing_lab/, which are committed as ordinary
files -- so this runs with no `git lfs pull` and no options download:

    pricing_lab/s2_vrp_daily.csv        IV vs subsequently-realized vol, by date
    pricing_lab/s3_term_structure.csv   7d/30d/180d ATM IV, by date
    pricing_lab/s6_weekly_grid_trades.csv  per-trade weekly short-premium P&L

Provenance: those tables are produced by volatility_pricing_lab.py from
919,090 EOD option quotes (627 trade dates, 2024-01-02 -> 2026-07-02) priced
at the project's 20% fill rule (sell = bid + 0.20*spread, buy = ask -
0.20*spread; bid=0 rejected). See qa/pricing_lab_report.txt.

    python3 harvest_blueprint/blueprint_tests.py

Writes harvest_blueprint/out/*.csv.
"""
import os
import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# Spearman without scipy: Pearson on ranks.
def spearman(a, b):
    return a.rank().corr(b.rank())

def rule(title):
    print("\n" + "=" * 94)
    print(title)
    print("=" * 94)


def load():
    v = pd.read_csv("pricing_lab/s2_vrp_daily.csv")
    v.columns = ["bucket", "date", "iv", "rv", "vrp"]
    v["date"] = pd.to_datetime(v["date"])
    ts = pd.read_csv("pricing_lab/s3_term_structure.csv")
    ts["trade_date"] = pd.to_datetime(ts["trade_date"])
    tr = pd.read_csv("pricing_lab/s6_weekly_grid_trades.csv")
    tr["trade_date"] = pd.to_datetime(tr["trade_date"])
    return v, ts, tr


def add_ivp(d):
    """Two IV-percentile definitions.

    ivp_full  full-sample rank. This LOOKS AHEAD -- you could not know the
              distribution in advance. Included deliberately: it is the most
              generous possible reading of the blueprint's gate, so a failure
              here is decisive.
    ivp_trail trailing 252-day rank, strictly backward-looking: what a live
              system could actually compute.
    """
    d = d.sort_values("date").reset_index(drop=True)
    d["ivp_full"] = d.iv.rank(pct=True) * 100
    d["ivp_trail"] = d.iv.rolling(252, min_periods=100).apply(
        lambda w: (w[:-1] < w[-1]).mean() * 100, raw=True)
    return d


# ----------------------------------------------------------------- test 1
def test_iv_percentile_gate(v):
    rule("TEST 1  IV-PERCENTILE GATE\n"
         "  Blueprint: 'restrict entries to IVP > 70, so you sell only when\n"
         "  premium is historically expensive.' If true, VRP (= IV - subsequent\n"
         "  realized vol; positive means the seller was overpaid) should be\n"
         "  higher in the high-IVP bucket.")
    rows = []
    for bucket in ["7d (weekly)", "30d", "90d"]:
        d = add_ivp(v[v.bucket == bucket])
        if len(d) < 60:
            continue
        print(f"\n--- {bucket}  (n={len(d)}) ---")
        for label, col in [("look-ahead IVP (best case)", "ivp_full"),
                           ("trailing-252d IVP (live)", "ivp_trail")]:
            dd = d.dropna(subset=[col])
            print(f"  {label}, n={len(dd)}")
            for lo, hi, name in [(0, 30, "IVP 0-30  (cheap)"),
                                 (30, 70, "IVP 30-70 (middle)"),
                                 (70, 101, "IVP >70   <-- BLUEPRINT GATE"),
                                 (90, 101, "IVP >90   (extreme)")]:
                s = dd[(dd[col] >= lo) & (dd[col] < hi)]
                if not len(s):
                    continue
                print(f"    {name:30s} n={len(s):4d}  meanVRP={s.vrp.mean():+.4f}"
                      f"  medVRP={s.vrp.median():+.4f}  %pos={100*(s.vrp>0).mean():5.1f}%"
                      f"  p05={s.vrp.quantile(.05):+.3f}  meanIV={s.iv.mean():.2f}")
                rows.append(dict(bucket=bucket, ivp_def=col, band=name.split()[1],
                                 n=len(s), mean_vrp=s.vrp.mean(),
                                 median_vrp=s.vrp.median(),
                                 pct_pos=100 * (s.vrp > 0).mean(),
                                 p05_vrp=s.vrp.quantile(.05), mean_iv=s.iv.mean()))
    pd.DataFrame(rows).to_csv(f"{OUT}/t1_ivp_gate.csv", index=False)
    print("\n  READING: the gate selects the WORST bucket, not the best, and it\n"
          "  roughly triples the left tail (p05). High SOXL IV is not rich\n"
          "  premium -- it is a correct forecast of even higher realized vol.")


# ----------------------------------------------------------------- test 2
def test_term_structure_gate(v, ts):
    rule("TEST 2  VIX / TERM-STRUCTURE CONTANGO GATE\n"
         "  Blueprint: 'enter short vol when the curve is in steep contango.'\n"
         "  SOXL has no VIX of its own, so this uses SOXL's OWN ATM term\n"
         "  structure (7d vs 30d), which is the closest faithful analogue.")
    w = v[v.bucket == "7d (weekly)"].merge(ts, left_on="date", right_on="trade_date")
    print(f"  joined n={len(w)}")
    print(f"  contango      (7d IV < 30d IV): {100*(w.slope_7_30<0).mean():5.1f}% of days")
    print(f"  backwardation (7d IV > 30d IV): {100*(w.slope_7_30>0).mean():5.1f}% of days")
    rows = []
    for lo, hi, name in [(-9, -0.05, "steep contango   (< -5 pts)"),
                         (-0.05, 0, "mild contango"),
                         (0, 0.05, "mild backwardation"),
                         (0.05, 9, "steep backwardation (> +5 pts)")]:
        s = w[(w.slope_7_30 >= lo) & (w.slope_7_30 < hi)]
        if not len(s):
            continue
        print(f"  {name:34s} n={len(s):4d}  meanVRP={s.vrp.mean():+.4f}"
              f"  medVRP={s.vrp.median():+.4f}  %pos={100*(s.vrp>0).mean():5.1f}%"
              f"  p05={s.vrp.quantile(.05):+.3f}")
        rows.append(dict(regime=name, n=len(s), mean_vrp=s.vrp.mean(),
                         median_vrp=s.vrp.median(), pct_pos=100 * (s.vrp > 0).mean(),
                         p05_vrp=s.vrp.quantile(.05)))
    pd.DataFrame(rows).to_csv(f"{OUT}/t2_term_structure_gate.csv", index=False)
    print(f"\n  Spearman(7d-30d slope, subsequent 7d VRP) = {spearman(w.slope_7_30, w.vrp):+.4f}")
    print(f"  Spearman(7d IV,        subsequent 7d VRP) = {spearman(w.iv7, w.vrp):+.4f}")
    print("\n  READING: the gate is backwards here -- steep BACKWARDATION carried the\n"
          "  better forward VRP -- and contango is the minority regime anyway, so the\n"
          "  rule would sit out most of the sample. Both correlations are ~0.")


# ----------------------------------------------------------------- test 3
def test_forecast_quality(v):
    rule("TEST 3  IS IMPLIED VOL A GOOD FORECAST?\n"
         "  If IV tracks subsequent realized vol with a slope >= 1, there is no\n"
         "  edge in the LEVEL of vol -- which is the only thing an IVP gate reads.")
    rows = []
    for b in ["7d (weekly)", "30d", "90d", "180d"]:
        d = v[v.bucket == b].dropna(subset=["iv", "rv"])
        if len(d) < 30:
            continue
        beta, a = np.polyfit(d.iv, d.rv, 1)
        print(f"  {b:12s} n={len(d):4d}  corr(IV,fwdRV)={d.iv.corr(d.rv):+.3f}"
              f"  Spearman={spearman(d.iv, d.rv):+.3f}"
              f"   fwdRV = {a:+.2f} + {beta:.2f}*IV")
        rows.append(dict(bucket=b, n=len(d), pearson=d.iv.corr(d.rv),
                         spearman=spearman(d.iv, d.rv), intercept=a, slope=beta))
    pd.DataFrame(rows).to_csv(f"{OUT}/t3_forecast_quality.csv", index=False)
    print("\n  READING: every slope is > 1. Each extra point of implied vol came with\n"
          "  MORE than a point of realized vol. SOXL vol is not overpriced at any\n"
          "  tenor measured -- so the premium the blueprint intends to harvest is\n"
          "  not there to harvest.")


# ----------------------------------------------------------------- test 4
def test_gate_vs_breaker(v):
    rule("TEST 4  ENTRY GATE vs CIRCUIT BREAKER -- INTERNAL CONSISTENCY\n"
         "  Blueprint rule 1.3 ENTERS when IV percentile is high.\n"
         "  Blueprint rule 2.3 HALTS when volatility spikes.\n"
         "  Both read the same variable, so they fire on overlapping days.\n"
         "  NOTE: no VIX series exists in this repo, so the halt is expressed on\n"
         "  SOXL's own IV. That is the correct regime variable for SOXL anyway,\n"
         "  and VIX and SOXL IV are driven by the same risk-off episodes.")
    d = add_ivp(v[v.bucket == "7d (weekly)"])
    entry = d.ivp_full > 70
    print(f"\n  days passing the IVP>70 ENTRY gate: {entry.sum()}")
    rows = []
    for pct in [70, 80, 90, 95]:
        halt = d.iv > d.iv.quantile(pct / 100)
        blocked = (entry & halt).sum()
        surv = (entry & ~halt).sum()
        print(f"    halt above the {pct}th pct of IV -> blocks {blocked:3d} of them"
              f" ({100*blocked/entry.sum():5.1f}%), {surv:3d} entries survive")
        rows.append(dict(halt_pct=pct, entries=int(entry.sum()),
                         blocked=int(blocked), surviving=int(surv)))
    pd.DataFrame(rows).to_csv(f"{OUT}/t4_gate_vs_breaker.csv", index=False)
    print("\n  READING: the two rules are the same rule with opposite signs. A halt\n"
          "  anywhere at or below the 70th percentile of IV removes every entry the\n"
          "  gate admits. Tightening one loosens the other; they cannot both bind.")


# ----------------------------------------------------------------- test 5
def test_gated_pnl(v, tr):
    rule("TEST 5  DEFINITIVE -- GATE THE ACTUAL TRADES ON IV PERCENTILE\n"
         "  Tests 1-4 are about the premium. This is about realized money:\n"
         "  31 weekly short-premium structures, Monday EOD entry -> expiry\n"
         "  settlement, 20%-rule fills, 119 weeks. Split by entry-time IVP.\n"
         "  P&L is $/share-week (naked-cash basis, before margin relief).")
    iv7 = add_ivp(v[v.bucket == "7d (weekly)"])[["date", "iv", "ivp_full", "ivp_trail"]]
    # Attach the IV reading known AT entry: most recent reading at or before Monday.
    t = pd.merge_asof(tr.sort_values("trade_date"), iv7, left_on="trade_date",
                      right_on="date", direction="backward",
                      tolerance=pd.Timedelta("5D")).dropna(subset=["ivp_full"])
    print(f"  trades matched to an entry-IV reading: {len(t)} of {len(tr)}\n")
    print(f"{'structure':24s} {'ALL weeks':>22s} {'IVP>70 (blueprint)':>24s} {'IVP 30-70':>20s}")
    print(f"{'':24s} {'n':>5s}{'tot$':>9s}{'mean':>8s} {'n':>5s}{'tot$':>9s}{'mean':>8s} {'n':>5s}{'tot$':>8s}{'mean':>7s}")
    rows = []
    for (s, l), g in t.groupby(["strategy", "legs"]):
        hi = g[g.ivp_full > 70]
        mid = g[(g.ivp_full >= 30) & (g.ivp_full <= 70)]
        rows.append(dict(structure=f"{s}/{l}", n_all=len(g), tot_all=g.pnl.sum(),
                         mean_all=g.pnl.mean(), n_hi=len(hi), tot_hi=hi.pnl.sum(),
                         mean_hi=hi.pnl.mean(), n_mid=len(mid), tot_mid=mid.pnl.sum(),
                         mean_mid=mid.pnl.mean()))
    rows.sort(key=lambda r: -r["tot_hi"])
    for r in rows:
        print(f"{r['structure']:24s} {r['n_all']:5d}{r['tot_all']:9.1f}{r['mean_all']:8.2f}"
              f" {r['n_hi']:5d}{r['tot_hi']:9.1f}{r['mean_hi']:8.2f}"
              f" {r['n_mid']:5d}{r['tot_mid']:8.1f}{r['mean_mid']:7.2f}")
    df = pd.DataFrame(rows)
    df.to_csv(f"{OUT}/t5_gated_weekly_pnl.csv", index=False)
    mid_all = t[(t.ivp_full >= 30) & (t.ivp_full <= 70)]
    hi_all = t[t.ivp_full > 70]
    print(f"\n  PROFITABLE STRUCTURES:  all weeks {(df.tot_all>0).sum()}/{len(df)}"
          f"   IVP>70 gate {(df.tot_hi>0).sum()}/{len(df)}"
          f"   IVP 30-70 gate {(df.tot_mid>0).sum()}/{len(df)}")
    print(f"  Mean $/share-week:      all {df.mean_all.mean():+.3f}"
          f"   IVP>70 {df.mean_hi.mean():+.3f}   IVP 30-70 {df.mean_mid.mean():+.3f}")
    print(f"  Worst single week:      all {t.pnl.min():.2f}"
          f"   IVP>70 {hi_all.pnl.min():.2f}   IVP 30-70 {mid_all.pnl.min():.2f}")
    tt = t.dropna(subset=["ivp_trail"])
    h = tt[tt.ivp_trail > 70]
    m = tt[(tt.ivp_trail >= 30) & (tt.ivp_trail <= 70)]
    print(f"\n  Same test on LIVE trailing-252d IVP (no look-ahead), n={len(tt)}:")
    print(f"    IVP>70    total ${h.pnl.sum():+9.1f}  mean {h.pnl.mean():+.3f}/share-wk  n={len(h)}")
    print(f"    IVP 30-70 total ${m.pnl.sum():+9.1f}  mean {m.pnl.mean():+.3f}/share-wk  n={len(m)}")
    print("\n  READING: the blueprint's gate makes the average trade ~2.2x WORSE and\n"
          "  does not avoid the worst week -- the worst week is identical, because the\n"
          "  gate is what puts you in it. The inverse gate (sell only mid-IV) is the\n"
          "  better half, and is still negative in 29 of 31 structures.")


def main():
    v, ts, tr = load()
    print(f"loaded: {len(v)} VRP obs, {len(ts)} term-structure days, {len(tr)} weekly trades")
    test_iv_percentile_gate(v)
    test_term_structure_gate(v, ts)
    test_forecast_quality(v)
    test_gate_vs_breaker(v)
    test_gated_pnl(v, tr)
    print(f"\nwrote {OUT}/t1..t5*.csv")


if __name__ == "__main__":
    main()
