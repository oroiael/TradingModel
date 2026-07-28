"""
V10 vol-gate program — execution (spec: V10_GATE_TESTS.md).
Corrected engine, start 11:00, breaker, V9 direction-aware filter ON
everywhere. Baseline = incumbent gate ATR5 >= 6.0.

Outputs: band_lab/out/v10_*.csv + printed report.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars, ROOT
from v5_corrected_rerun import sim_trades_fixed, day_pnl
from v11_sizing_tests import metrics, byyear

OUT = os.path.join(HERE, "out")
START_I = 18

def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 2 and x.std() > 0 else 0

def cal_cagr(sel, years):
    return ((1 + sel).prod() ** (1 / years) - 1) * 100

def main():
    bars = load_bars()
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    for n in (3, 5, 10, 20, 63):
        daily[f"atr{n}"] = daily["range_pct"].rolling(n).mean().shift()
    or30, pos10 = {}, {}
    for d, gb in g:
        hh = gb["High"].to_numpy()[:6]; ll = gb["Low"].to_numpy()[:6]
        cc = gb["Close"].to_numpy()
        orh, orl = hh.max(), ll.min()
        or30[d] = (orh - orl) / gb["Open"].iloc[0] * 100
        pos10[d] = (cc[5] - orl) / (orh - orl) if orh > orl and len(cc) > 5 else .5
    daily["or30"] = pd.Series(or30); daily["pos10"] = pd.Series(pos10)
    daily["thr80"] = daily["or30"].shift(1).rolling(504, min_periods=120).quantile(.8)
    v9_pass = daily.index[(daily["or30"] < daily["thr80"]) |
                          ((daily["or30"] >= daily["thr80"]) & (daily["pos10"] >= 2/3))]

    # SOXX-derived ATR5 (x3 to SOXL scale)
    sx = pd.read_csv(os.path.join(ROOT, "SOXX_5min_6Years.csv"))
    dt = pd.to_datetime(sx["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    sx = sx.assign(date=dt.dt.normalize())
    sxd = sx.groupby("date").agg(o=("Open", "first"), h=("High", "max"),
                                 l=("Low", "min"))
    soxx_atr5 = ((sxd["h"] - sxd["l"]) / sxd["o"] * 100).rolling(5).mean().shift() * 3
    daily["soxx_atr5"] = soxx_atr5.reindex(daily.index)

    # daily P&L for every V9-pass day (NO vol gate)
    pnl = {}
    for dd, gb in g:
        if dd not in v9_pass or len(gb) < 20:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        pnl[dd] = day_pnl(sim_trades_fixed(o, h, l, c, START_I))
    base = pd.Series(pnl)
    j = daily.loc[base.index].assign(pnl=base)
    years_span = (daily.index[-1] - daily.index[0]).days / 365.25
    rows = []

    # ---------------- T1 fine map + era split
    print("=" * 70); print("T1. FINE ATR5 EDGE MAP (V9 filter on, no gate)"); print("=" * 70)
    bins = [0, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 99]
    jj = j.dropna(subset=["atr5"])
    jj = jj.assign(bin=pd.cut(jj["atr5"], bins))
    t1 = jj.groupby("bin", observed=True).agg(
        n=("pnl", "size"), mean_bp=("pnl", lambda x: round(x.mean() * 1e4, 1)),
        shp=("pnl", lambda x: round(sharpe(x), 2)),
        worst=("pnl", lambda x: round(x.min() * 100, 1)))
    print(t1.to_string())
    t1.to_csv(os.path.join(OUT, "v10_fine_map.csv"))
    print("\nera split (mean bp/day per bin):")
    era = jj.assign(era=np.where(jj.index < pd.Timestamp("2023-01-01"),
                                 "2020-22", "2023-26"))
    print((era.pivot_table(values="pnl", index="bin", columns="era",
                           aggfunc="mean", observed=True) * 1e4).round(1).to_string())

    # ---------------- T2 cutoff sweep
    print(); print("=" * 70); print("T2. CUTOFF SWEEP (absolute ATR5)"); print("=" * 70)
    series = {}
    for X in (4, 5, 5.5, 6, 6.5, 7, 8):
        sel = base[base.index.isin(j.index[j["atr5"] >= X])]
        series[f"abs{X:g}"] = sel
        m = metrics(sel, f"ATR5>={X:g}" + ("*" if X == 6 else ""))
        m["days_on"] = len(sel)
        m["cal_cagr_pct"] = round(cal_cagr(sel, years_span), 1)
        rows.append(m)
    print(pd.DataFrame(rows).to_string(index=False))

    # ---------------- T3 forms + input
    print(); print("=" * 70); print("T3. FORMS + INPUT SOURCE"); print("=" * 70)
    t3 = []
    for p in (50, 60, 70):
        thr = j["atr5"].shift(1).rolling(504, min_periods=120).quantile(p / 100)
        sel = base[base.index.isin(j.index[j["atr5"] >= thr])]
        series[f"pct{p}"] = sel
        m = metrics(sel, f"pctile>={p}"); m["days_on"] = len(sel)
        m["cal_cagr_pct"] = round(cal_cagr(sel, years_span), 1); t3.append(m)
    for k in (1.0, 1.15, 1.3):
        sel = base[base.index.isin(j.index[j["atr5"] >= k * j["atr63"]])]
        series[f"ratio{k:g}"] = sel
        m = metrics(sel, f"ATR5>={k:g}xATR63"); m["days_on"] = len(sel)
        m["cal_cagr_pct"] = round(cal_cagr(sel, years_span), 1); t3.append(m)
    sel = base[base.index.isin(j.index[j["soxx_atr5"] >= 6])]
    series["soxx6"] = sel
    m = metrics(sel, "SOXXx3 ATR5>=6"); m["days_on"] = len(sel)
    m["cal_cagr_pct"] = round(cal_cagr(sel, years_span), 1); t3.append(m)
    print(pd.DataFrame(t3).to_string(index=False))
    rows += t3
    inc = series["abs6"]; sx6 = series["soxx6"]
    ov = len(inc.index.intersection(sx6.index))
    print(f"  SOXX vs SOXL gate day-overlap: {ov}/{len(inc)} incumbent days shared")

    # ---------------- T4 lookback sweep (matched ON-rate)
    print(); print("=" * 70); print("T4. LOOKBACK SWEEP (ON-rate matched to incumbent)"); print("=" * 70)
    on_rate = (j["atr5"] >= 6).mean()
    t4 = []
    for n in (3, 5, 10, 20):
        col = f"atr{n}"
        cut = j[col].quantile(1 - on_rate)
        sel = base[base.index.isin(j.index[j[col] >= cut])]
        series[f"lb{n}"] = sel
        m = metrics(sel, f"ATR{n}>={cut:.1f} (matched)")
        m["days_on"] = len(sel)
        m["cal_cagr_pct"] = round(cal_cagr(sel, years_span), 1)
        t4.append(m)
    print(pd.DataFrame(t4).to_string(index=False))
    rows += t4

    # ---------------- T5 whipsaw, hysteresis, walk-forward
    print(); print("=" * 70); print("T5. WHIPSAW / HYSTERESIS / WALK-FORWARD"); print("=" * 70)
    gate = (daily["atr5"] >= 6)
    trans = (gate != gate.shift()).sum()
    eps = []
    run = 0
    for v in gate.fillna(False):
        if v: run += 1
        elif run: eps.append(run); run = 0
    eps = pd.Series(eps)
    print(f"incumbent gate: {trans/years_span:.0f} transitions/yr, "
          f"episode length median {eps.median():.0f}d, mean {eps.mean():.1f}d, max {eps.max()}d")
    # first/mid/last ON-day edge
    pos_in_ep = {}
    run_days = []
    for d, v in gate.fillna(False).items():
        if v:
            run_days.append(d)
        else:
            for i2, dd in enumerate(run_days):
                pos_in_ep[dd] = ("first" if i2 == 0 else
                                 "last" if i2 == len(run_days) - 1 else "mid")
            run_days = []
    pe = pd.Series(pos_in_ep)
    onp = base[base.index.isin(pe.index)]
    tab = pd.DataFrame({"pnl": onp, "pos": pe.reindex(onp.index)})
    print("edge by position in ON-episode:")
    print((tab.groupby("pos")["pnl"].agg(["count", "mean"])
           .assign(mean=lambda x: (x["mean"] * 1e4).round(1))).to_string())
    # hysteresis on6/off5
    state = False; hyst = {}
    for d in daily.index:
        a = daily.loc[d, "atr5"]
        if not np.isnan(a):
            if not state and a >= 6: state = True
            elif state and a < 5: state = False
        hyst[d] = state
    hser = pd.Series(hyst)
    sel = base[base.index.isin(hser.index[hser])]
    series["hyst6_5"] = sel
    m = metrics(sel, "hysteresis on6/off5"); m["days_on"] = len(sel)
    m["cal_cagr_pct"] = round(cal_cagr(sel, years_span), 1)
    rows.append(m)
    print(pd.DataFrame([m]).to_string(index=False))
    # walk-forward
    cands = {k: series[k] for k in ("abs5", "abs5.5", "abs6", "abs6.5",
                                    "pct50", "pct60", "ratio1.15", "soxx6",
                                    "lb3", "hyst6_5") if k in series}
    oos = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01"); t1_ = pd.Timestamp(f"{year+1}-01-01")
        best, bs = None, -99
        for nm, ser in cands.items():
            tr = ser[ser.index < t0]
            s_ = sharpe(tr)
            if s_ > bs: bs, best = s_, nm
        te = cands[best][(cands[best].index >= t0) & (cands[best].index < t1_)]
        oos.append(te)
        print(f"  {year}: picked {best:9s} -> OOS {te.mean()*1e4:+.1f} bp/day ({len(te)} d)")
    allo = pd.concat(oos).sort_index()
    print(f"  ALL OOS: {allo.mean()*1e4:.1f} bp/day, Sharpe {sharpe(allo):.2f}")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "v10_results.csv"), index=False)

if __name__ == "__main__":
    main()
