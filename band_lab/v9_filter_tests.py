"""
V9 filter-boundary program — execution (spec: V9_FILTER_TESTS.md).
Corrected engine, start 11:00, breaker on, ATR5>=6 gate always on.
All OR30 thresholds are TRAILING (prior 504 sessions, min 120) — no
full-sample quantiles anywhere in a decision path.

Outputs: band_lab/out/v9_*.csv + printed report.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars
from v5_corrected_rerun import sim_trades_fixed, day_pnl
from v11_sizing_tests import metrics, byyear

OUT = os.path.join(HERE, "out")
START_I = 18

def trailing_pct_rank(s, win=504, minp=120):
    v = s.to_numpy()
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        lo = max(0, i - win)
        w = v[lo:i]
        if len(w) >= minp:
            out[i] = (w < v[i]).mean()
    return pd.Series(out, index=s.index)

def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 2 and x.std() > 0 else 0

def main():
    bars = load_bars()
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    daily["atr5"] = daily["range_pct"].rolling(5).mean().shift()
    or30, pos10 = {}, {}
    for d, gb in g:
        hh = gb["High"].to_numpy()[:6]; ll = gb["Low"].to_numpy()[:6]
        cc = gb["Close"].to_numpy()
        orh, orl = hh.max(), ll.min()
        or30[d] = (orh - orl) / gb["Open"].iloc[0] * 100
        pos10[d] = (cc[5] - orl) / (orh - orl) if orh > orl and len(cc) > 5 else .5
    daily["or30"] = pd.Series(or30)
    daily["pos10"] = pd.Series(pos10)
    daily["or30_pct"] = trailing_pct_rank(daily["or30"])
    for q in (.60, .70, .75, .80, .85, .90, .95):
        daily[f"thr{int(q*100)}"] = daily["or30"].shift(1).rolling(504, min_periods=120).quantile(q)

    gate_on = daily.index[daily["atr5"] >= 6]
    pnl = {}
    for dd, gb in g:
        if dd not in gate_on or len(gb) < 20:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        pnl[dd] = day_pnl(sim_trades_fixed(o, h, l, c, START_I))
    base = pd.Series(pnl)          # gate-on, UNFILTERED
    j = daily.loc[base.index].assign(pnl=base)
    rows = []

    # ---------------- T1: decile map + joint map
    print("=" * 70); print("T1. EDGE BY OR30 TRAILING-PERCENTILE DECILE (gate on, no filter)")
    print("=" * 70)
    jj = j.dropna(subset=["or30_pct"])
    jj = jj.assign(dec=(jj["or30_pct"] * 10).astype(int).clip(0, 9) + 1)
    t1 = jj.groupby("dec").agg(n=("pnl", "size"),
                               mean_bp=("pnl", lambda x: round(x.mean() * 1e4, 1)),
                               sharpe=("pnl", lambda x: round(sharpe(x), 2)),
                               worst_pct=("pnl", lambda x: round(x.min() * 100, 1)))
    print(t1.to_string())
    t1.to_csv(os.path.join(OUT, "v9_decile_map.csv"))
    print("\njoint map mean bp/day (OR30 tercile x ATR5 tercile):")
    jj = jj.assign(or_t=pd.qcut(jj["or30_pct"], 3, labels=["orLo", "orMid", "orHi"]),
                   atr_t=pd.qcut(jj["atr5"], 3, labels=["atrLo", "atrMid", "atrHi"]))
    print((jj.pivot_table(values="pnl", index="or_t", columns="atr_t",
                          aggfunc="mean", observed=True) * 1e4).round(1).to_string())

    # ---------------- T2: boundary sweep
    print(); print("=" * 70); print("T2. BOUNDARY SWEEP (trailing percentile)"); print("=" * 70)
    series = {}
    for q in (60, 70, 75, 80, 85, 90, 95, 100):
        if q == 100:
            sel = base
        else:
            keep = j.index[j["or30"] < j[f"thr{q}"]]
            sel = base[base.index.isin(keep)]
        series[f"pct{q}"] = sel
        m = metrics(sel, f"pct{q}" + ("*" if q == 80 else ""))
        m["days"] = len(sel)
        rows.append(m)
    print(pd.DataFrame(rows).to_string(index=False))

    # ---------------- T3: threshold forms
    print(); print("=" * 70); print("T3. THRESHOLD FORMS"); print("=" * 70)
    t3rows = []
    for X in (4, 5, 6, 7):
        sel = base[base.index.isin(j.index[j["or30"] < X])]
        series[f"abs{X}"] = sel
        m = metrics(sel, f"abs OR30<{X}%"); m["days"] = len(sel)
        t3rows.append(m)
    for k in (0.5, 0.65, 0.8, 1.0):
        sel = base[base.index.isin(j.index[j["or30"] < k * j["atr5"]])]
        series[f"rel{k}"] = sel
        m = metrics(sel, f"rel OR30<{k}xATR5"); m["days"] = len(sel)
        t3rows.append(m)
    print(pd.DataFrame(t3rows).to_string(index=False))
    rows += t3rows

    # ---------------- T4: direction-aware (conditional split first)
    print(); print("=" * 70); print("T4. DIRECTION-AWARE"); print("=" * 70)
    filt = j[j["or30"] >= j["thr80"]].dropna(subset=["pnl"])
    up = filt[filt["pos10"] >= 2 / 3]; dn = filt[filt["pos10"] < 1 / 3]
    mid = filt[(filt["pos10"] >= 1 / 3) & (filt["pos10"] < 2 / 3)]
    print(f"currently-filtered days (n={len(filt)}), unfiltered-core P&L on them:")
    for nm, ss in [("up-morning (pos>=2/3)", up), ("mid", mid),
                   ("down-morning (pos<1/3)", dn)]:
        print(f"  {nm:24s} n={len(ss):3d}  mean {ss['pnl'].mean()*1e4:+7.1f} bp  "
              f"sharpe {sharpe(ss['pnl']):+.2f}  worst {ss['pnl'].min()*100:.1f}%")
    keep = j.index[(j["or30"] < j["thr80"]) |
                   ((j["or30"] >= j["thr80"]) & (j["pos10"] >= 2 / 3))]
    sel = base[base.index.isin(keep)]
    series["dir80"] = sel
    m = metrics(sel, "T4 pct80 + readmit up-mornings"); m["days"] = len(sel)
    rows.append(m)
    print(pd.DataFrame([m]).to_string(index=False))
    print("   by year:", byyear(sel))

    # ---------------- T5: walk-forward + overlap + cadence
    print(); print("=" * 70); print("T5. VALIDATION"); print("=" * 70)
    candidates = {k: v for k, v in series.items()
                  if k in ("pct80", "pct85", "pct90", "pct100",
                           "abs5", "abs6", "rel0.8", "rel1.0", "dir80")}
    oos = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01"); t1_ = pd.Timestamp(f"{year+1}-01-01")
        best, bs = None, -99
        for nm, ser in candidates.items():
            tr = ser[ser.index < t0]
            s_ = sharpe(tr)
            if s_ > bs:
                bs, best = s_, nm
        te = candidates[best][(candidates[best].index >= t0)
                              & (candidates[best].index < t1_)]
        oos.append(te)
        print(f"  {year}: picked {best:8s} -> OOS {te.mean()*1e4:+.1f} bp/day "
              f"({len(te)} days)")
    allo = pd.concat(oos).sort_index()
    print(f"  ALL OOS: {allo.mean()*1e4:.1f} bp/day, Sharpe {sharpe(allo):.2f}")
    inc = series["pct80"]
    for nm in ("pct90", "rel1.0", "dir80"):
        ch = series[nm]
        added = ch.index.difference(inc.index)
        dropped = inc.index.difference(ch.index)
        print(f"\n  overlap {nm} vs pct80: +{len(added)} days re-admitted "
              f"(mean {base[base.index.isin(added)].mean()*1e4:+.1f} bp), "
              f"-{len(dropped)} days newly dropped "
              f"(mean {base[base.index.isin(dropped)].mean()*1e4:+.1f} bp)")
    # cadence: monthly vs quarterly vs annual refresh of the 80th-pct threshold
    print("\n  recompute-cadence sensitivity (pct80 form):")
    for freq, lbl in [("MS", "monthly"), ("QS", "quarterly"), ("YS", "annual")]:
        marks = pd.date_range(daily.index[0], daily.index[-1], freq=freq)
        thr = pd.Series(np.nan, index=daily.index)
        for mday in marks:
            hist = daily["or30"][daily.index < mday].tail(504)
            if len(hist) >= 120:
                thr[daily.index >= mday] = hist.quantile(.8)
        keep = j.index[j["or30"] < thr.reindex(j.index)]
        sel = base[base.index.isin(keep)]
        print(f"    {lbl:9s}: {len(sel)} days, {sel.mean()*1e4:.1f} bp/day, "
              f"sharpe {sharpe(sel):.2f}")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "v9_results.csv"), index=False)

if __name__ == "__main__":
    main()
