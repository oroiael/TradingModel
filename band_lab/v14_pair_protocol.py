"""
V14 — full protocol on the SOXL+SOXS pair (plan: V14_PAIR_PROTOCOL.md).
T1 SOXS cost re-derivation -> T2 walk-forward on w -> T3 plateau ->
T4 mechanism attribution -> T5 capital rule -> T6 practical checks.

Outputs: band_lab/out/v14_*.csv
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cycle_lab"))
sys.path.insert(0, HERE)
from transfer_test import load_symbol, build_daily
from etf_scaling_test import run_cell

OUT = os.path.join(HERE, "out")
WGRID = [0.0, 0.25, 0.50, 0.75, 1.0]
SHARPE = lambda x: x.mean() / x.std() * np.sqrt(252) if len(x) > 2 and x.std() > 0 else np.nan

def sleeve(sym):
    d, g = build_daily(load_symbol(sym))
    _, on = run_cell(d, g, 6.0, .01, .01, .04, sym)
    trades = {}
    v9 = (d["or30"] < d["thr80"]) | ((d["or30"] >= d["thr80"]) & (d["pos10"] >= 2/3))
    onm = v9 & (d["atr5"] >= 6)
    return d, g, on, onm

# CURRENT prices (last close in each file). Historical prices in these
# files are ADJUSTED (SOXL split-adjusted; SOXS back-adjusted, so its
# early prints are astronomically inflated and are NOT tradeable prices).
# A forward-looking cost estimate must use what you would trade at today.
CURRENT_PX = {"SOXL": 158.41, "SOXS": 51.61}

def cost_bp(price, trades_per_day, capital=150000):
    """IBKR Pro Fixed, per round trip, expressed in bp of position."""
    shares = capital / price
    comm_side = max(0.005 * shares, 1.00)          # $0.005/sh, $1 min
    comm_bp_side = comm_side / capital * 1e4
    reg_bp_sell = 0.35                              # SEC+TAF on sells
    # spread: assume 1 cent quoted; half-spread crossed on stops & EOD only
    spread_bp = (0.01 / price) * 1e4
    # entries and targets are resting limits (no cross); ~1 exit in 4 crosses
    cross_frac = 0.30
    per_rt = 2 * comm_bp_side + reg_bp_sell + cross_frac * spread_bp
    return per_rt, per_rt * trades_per_day, comm_bp_side, spread_bp

def main():
    dL, gL, soxl, onL = sleeve("SOXL")
    dX, gX, soxs, onX = sleeve("SOXS")

    # ---------------- T1 costs
    print("=" * 92); print("T1. SOXS COST RE-DERIVATION (IBKR Pro Fixed, $150K)"); print("=" * 92)
    rows = []
    for sym, d, on, tpd in [("SOXL", dL, soxl, 3.17), ("SOXS", dX, soxs, 3.36)]:
        px = CURRENT_PX[sym]
        rt, per_day, comm_side, spr = cost_bp(px, tpd)
        rows.append({"sleeve": sym, "mean_price": round(px, 2),
                     "comm_bp_per_side": round(comm_side, 2),
                     "spread_bp_1cent": round(spr, 2),
                     "cost_bp_per_round_trip": round(rt, 2),
                     "trades_per_day": tpd,
                     "cost_bp_per_day": round(per_day, 1),
                     "gross_bp_day": round(on.mean() * 1e4, 1),
                     "NET_bp_day": round(on.mean() * 1e4 - per_day, 1)})
    ct = pd.DataFrame(rows); print(ct.to_string(index=False))
    ct.to_csv(os.path.join(OUT, "v14_costs.csv"), index=False)
    cL = ct.loc[ct.sleeve == "SOXL", "cost_bp_per_day"].iloc[0] / 1e4
    cX = ct.loc[ct.sleeve == "SOXS", "cost_bp_per_day"].iloc[0] / 1e4
    print(f"\n  SOXS costs {ct.loc[1,'cost_bp_per_day']/ct.loc[0,'cost_bp_per_day']:.1f}x SOXL per day in bp, "
          f"driven by price (${ct.loc[1,'mean_price']:.2f} vs ${ct.loc[0,'mean_price']:.2f}): IBKR charges "
          f"per SHARE and a 1c spread is proportionally wider on the cheaper instrument.")

    # net series
    nL = (soxl - cL); nX = (soxs - cX)
    cal = pd.date_range(min(nL.index.min(), nX.index.min()),
                        max(nL.index.max(), nX.index.max()), freq="B")
    a = nL.reindex(cal).fillna(0.0); b = nX.reindex(cal).fillna(0.0)
    onLc = pd.Series(False, index=cal); onLc[nL.index] = True
    onXc = pd.Series(False, index=cal); onXc[nX.index] = True

    def series(w, mode="static"):
        if mode == "static":
            return w * a + (1 - w) * b
        act = onLc.astype(float) * w + onXc.astype(float) * (1 - w)
        sc = np.where(act > 0, 1.0 / act.replace(0, np.nan), 0.0)
        sc = pd.Series(sc, index=cal).fillna(0.0)
        return (w * a + (1 - w) * b) * sc

    def stats(r, label):
        eq = (1 + r).cumprod(); pk = eq.cummax()
        yrs = (cal[-1] - cal[0]).days / 365.25
        return {"variant": label, "bp_cal_day": round(r.mean() * 1e4, 1),
                "sharpe": round(SHARPE(r), 2),
                "maxDD_%": round(((eq - pk) / pk).min() * 100, 1),
                "CAGR_%": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1)}

    # ---------------- T3 plateau (net)
    print()
    print("=" * 92); print("T3. PLATEAU IN w (NET of costs, static allocation)"); print("=" * 92)
    prow = [stats(series(w), f"w={w:.3f}") for w in np.arange(0, 1.0001, 0.125)]
    pdf = pd.DataFrame(prow); print(pdf.to_string(index=False))
    pdf.to_csv(os.path.join(OUT, "v14_plateau.csv"), index=False)

    # ---------------- T2 walk-forward (net)
    print()
    print("=" * 92); print("T2. WALK-FORWARD ON w (selected on prior years only, NET)"); print("=" * 92)
    oos, oos_solo, picks = [], [], []
    for yr in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{yr}-01-01"); t1 = pd.Timestamp(f"{yr+1}-01-01")
        best, bs = None, -99
        for w in WGRID:
            tr = series(w)[series(w).index < t0]
            s_ = SHARPE(tr)
            if not np.isnan(s_) and s_ > bs:
                bs, best = s_, w
        te = series(best); te = te[(te.index >= t0) & (te.index < t1)]
        solo = a[(a.index >= t0) & (a.index < t1)]
        oos.append(te); oos_solo.append(solo); picks.append((yr, best))
        print(f"  {yr}: picked w={best:.2f} -> pair OOS {te.mean()*1e4:+6.1f} bp/cal-day "
              f"Sharpe {SHARPE(te):5.2f}  |  SOXL-alone {solo.mean()*1e4:+6.1f} bp Sharpe {SHARPE(solo):5.2f}"
              f"   {'PAIR WINS' if SHARPE(te) > SHARPE(solo) else 'solo wins'}")
    A = pd.concat(oos).sort_index(); B = pd.concat(oos_solo).sort_index()
    wins = sum(1 for t, s in zip(oos, oos_solo) if SHARPE(t) > SHARPE(s))
    print(f"\n  ALL OOS pair: {A.mean()*1e4:.1f} bp, Sharpe {SHARPE(A):.2f} | "
          f"SOXL-alone: {B.mean()*1e4:.1f} bp, Sharpe {SHARPE(B):.2f}")
    eqA = (1+A).cumprod(); eqB = (1+B).cumprod()
    print(f"  OOS maxDD pair {((eqA-eqA.cummax())/eqA.cummax()).min()*100:.1f}% | "
          f"solo {((eqB-eqB.cummax())/eqB.cummax()).min()*100:.1f}%")
    print(f"  ADOPTION BAR: pair beats solo on Sharpe in {wins}/5 years (need >=4)")
    pd.DataFrame({"year": [p[0] for p in picks], "w_picked": [p[1] for p in picks]}
                 ).to_csv(os.path.join(OUT, "v14_walkforward.csv"), index=False)

    # ---------------- T4 mechanism attribution
    print()
    print("=" * 92); print("T4. MECHANISM ATTRIBUTION (net, w=0.5 static vs SOXL-alone)"); print("=" * 92)
    pair = series(0.5)
    diff = pair - a
    both = onLc & onXc; xonly = (~onLc) & onXc; lonly = onLc & (~onXc)
    tot = diff.sum()
    for nm, m in [("both ON", both), ("SOXS-only (predicted source)", xonly),
                  ("SOXL-only", lonly)]:
        print(f"  {nm:30s} n={int(m.sum()):4d}  contribution to (pair - solo): "
              f"{diff[m].sum()*100:+7.1f}% of capital")
    print(f"  {'NET TOTAL':30s}        {tot*100:+7.1f}% of capital")

    # ---------------- T5 capital rule
    print()
    print("=" * 92); print("T5. CAPITAL RULE (net)"); print("=" * 92)
    t5 = [stats(a, "SOXL alone"), stats(series(.5), "pair 50/50 static"),
          stats(series(.5, "dynamic"), "pair 50/50 dynamic")]
    print(pd.DataFrame(t5).to_string(index=False))
    pd.DataFrame(t5).to_csv(os.path.join(OUT, "v14_capital_rule.csv"), index=False)

    # ---------------- T6 practical
    print()
    print("=" * 92); print("T6. PRACTICAL"); print("=" * 92)
    for sym, g, on in [("SOXL", gL, soxl), ("SOXS", gX, soxs)]:
        dv = []
        for dd in on.index:
            gb = g.get_group(dd)
            dv.append((gb["Close"] * gb["Volume"]).sum())
        print(f"  {sym}: median daily dollar volume on ON days ${np.median(dv)/1e9:.2f}B "
              f"-> a $150K order is {150000/np.median(dv)*1e4:.2f} bp of a day's volume")
    print(f"  days both sleeves ON (capital contended): {int(both.sum())}")

if __name__ == "__main__":
    main()
