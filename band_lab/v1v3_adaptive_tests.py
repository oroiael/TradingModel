"""
V1/V3 adaptive-levels program — execution (spec: V1_V3_ADAPTIVE_TESTS.md).
Corrected engine, start 11:00, cap 5, 2-stop breaker, V9 direction
filter, ATR5>=6 gate. Baseline fixed dip 1% / target 1% / stop 4%.

T1 migration map (go/no-go) -> T2 adaptive dip -> T3 adaptive target ->
T4 joint symmetric (+stop geometry) -> T5 walk-forward + mechanism.

Outputs: band_lab/out/v1v3_*.csv + printed report.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars
from v11_sizing_tests import metrics, byyear

OUT = os.path.join(HERE, "out")
START_I, MAXTR, MAXSTOP = 18, 5, 2

def sim_day(o, h, l, c, d, t, s):
    """Corrected engine, breaker applied. Returns (pnl, n_trades)."""
    roll_hi = h[:START_I].max()
    state = 0; entry = 0.0; entry_i = -1
    pnl = 0.0; trades = 0; stops = 0
    for i in range(START_I, len(c)):
        if state == 1:
            tgt = entry * (1 + t); stp = entry * (1 - s)
            if l[i] <= stp:
                pnl += -s if o[i] > stp else o[i] / entry - 1
                stops += 1; state = 0
            elif i > entry_i and h[i] >= tgt:
                pnl += t if o[i] < tgt else o[i] / entry - 1
                state = 0
        if state == 0 and trades < MAXTR and stops < MAXSTOP:
            trig = roll_hi * (1 - d)
            if l[i] <= trig:
                entry = min(trig, o[i]); entry_i = i; state = 1; trades += 1
                stp = entry * (1 - s)
                if l[i] <= stp:
                    pnl += -s if o[i] > stp else min(o[i] / entry - 1, -s)
                    stops += 1; state = 0
        roll_hi = max(roll_hi, h[i])
    if state == 1:
        pnl += c[-1] / entry - 1
    return pnl, trades

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
    daily["or30"] = pd.Series(or30); daily["pos10"] = pd.Series(pos10)
    daily["thr80"] = daily["or30"].shift(1).rolling(504, min_periods=120).quantile(.8)
    daily["erange"] = 1.9 * daily["or30"]
    v9 = daily.index[(daily["or30"] < daily["thr80"]) |
                     ((daily["or30"] >= daily["thr80"]) & (daily["pos10"] >= 2/3))]
    universe = [dd for dd in daily.index
                if dd in v9 and daily.loc[dd, "atr5"] >= 6]
    arrays = {dd: tuple(gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
              for dd, gb in g if dd in set(universe) and len(gb) >= 20}
    udays = sorted(arrays.keys())
    er = daily.loc[udays, "erange"]
    a5 = daily.loc[udays, "atr5"]
    er_t = pd.qcut(er, 3, labels=["narrow", "mid", "wide"])
    a5_t = pd.qcut(a5, 3, labels=["narrow", "mid", "wide"])

    def run(d_map, t_map, s_map):
        p, n = {}, {}
        for dd in udays:
            o, h, l, c = arrays[dd]
            p[dd], n[dd] = sim_day(o, h, l, c, d_map[dd], t_map[dd], s_map[dd])
        return pd.Series(p), pd.Series(n)

    const = lambda v: {dd: v for dd in udays}

    # ---------------- T1 migration map
    print("=" * 70); print("T1. MIGRATION MAP (9 fixed pairs x band terciles)")
    print("=" * 70)
    fixed = {}
    for d_ in (.01, .015, .02):
        for t_ in (.01, .015, .02):
            fixed[(d_, t_)], _ = run(const(d_), const(t_), const(.04))
    for lbl, terc in [("E[range]=1.9xOR30 terciles", er_t),
                      ("ATR5 terciles", a5_t)]:
        print(f"\n-- {lbl} --")
        for tc in ("narrow", "mid", "wide"):
            days_tc = terc.index[terc == tc]
            best = max(fixed, key=lambda k: fixed[k][fixed[k].index.isin(days_tc)].mean())
            row = {f"d{d_*100:g}/t{t_*100:g}":
                   round(fixed[(d_, t_)][fixed[(d_, t_)].index.isin(days_tc)].mean() * 1e4, 1)
                   for d_ in (.01, .015, .02) for t_ in (.01, .015, .02)}
            print(f"{tc:7s} best={best[0]*100:g}/{best[1]*100:g}  " +
                  "  ".join(f"{k}:{v}" for k, v in row.items()))
    base = fixed[(.01, .01)]
    rows = [dict(metrics(base, "fixed 1/1 (baseline)"), trades_day=None)]

    # ---------------- T2 adaptive dip
    print(); print("=" * 70); print("T2. ADAPTIVE DIP (target 1%, stop 4%)"); print("=" * 70)
    series = {"fixed": base}
    for src, sname in [("erange", "OR"), ("atr5", "ATR")]:
        for a in (.15, .20, .25):
            dmap = {dd: float(np.clip(a * daily.loc[dd, src] / 100, .0075, .03))
                    for dd in udays}
            ser, ntr = run(dmap, const(.01), const(.04))
            nm = f"dip={a:g}x{sname}"
            series[nm] = ser
            m = metrics(ser, nm); m["trades_day"] = round(ntr.mean(), 2)
            rows.append(m)
    print(pd.DataFrame(rows).to_string(index=False))

    # ---------------- T3 adaptive target
    print(); print("=" * 70); print("T3. ADAPTIVE TARGET (dip 1%, stop 4%)"); print("=" * 70)
    t3rows = []
    for src, sname in [("erange", "OR"), ("atr5", "ATR")]:
        for a in (.15, .20, .25):
            tmap = {dd: float(np.clip(a * daily.loc[dd, src] / 100, .0075, .025))
                    for dd in udays}
            ser, ntr = run(const(.01), tmap, const(.04))
            nm = f"tgt={a:g}x{sname}"
            series[nm] = ser
            m = metrics(ser, nm); m["trades_day"] = round(ntr.mean(), 2)
            t3rows.append(m)
    print(pd.DataFrame(t3rows).to_string(index=False))
    rows += t3rows

    # ---------------- T4 joint symmetric (best single-knob alpha/source)
    print(); print("=" * 70); print("T4. JOINT SYMMETRIC + STOP GEOMETRY"); print("=" * 70)
    t4rows = []
    for src, sname in [("erange", "OR"), ("atr5", "ATR")]:
        for a in (.15, .20):
            lm = {dd: float(np.clip(a * daily.loc[dd, src] / 100, .0075, .025))
                  for dd in udays}
            for stop_mode, smn in [("fixed4", const(.04)),
                                   ("4xtgt", {dd: min(4 * lm[dd], .10) for dd in udays})]:
                ser, ntr = run(lm, lm, smn)
                nm = f"sym {a:g}x{sname} stop{stop_mode}"
                series[nm] = ser
                m = metrics(ser, nm); m["trades_day"] = round(ntr.mean(), 2)
                t4rows.append(m)
    print(pd.DataFrame(t4rows).to_string(index=False))
    rows += t4rows

    # ---------------- T5 walk-forward + mechanism
    print(); print("=" * 70); print("T5. WALK-FORWARD + MECHANISM"); print("=" * 70)
    oos = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01"); t1_ = pd.Timestamp(f"{year+1}-01-01")
        best, bs = None, -99
        for nm, ser in series.items():
            tr = ser[ser.index < t0]
            s_ = sharpe(tr)
            if s_ > bs: bs, best = s_, nm
        te = series[best][(series[best].index >= t0) & (series[best].index < t1_)]
        oos.append(te)
        print(f"  {year}: picked {best:22s} -> OOS {te.mean()*1e4:+.1f} bp/day")
    allo = pd.concat(oos).sort_index()
    print(f"  ALL OOS: {allo.mean()*1e4:.1f} bp/day, Sharpe {sharpe(allo):.2f}")
    # mechanism: tercile attribution of the best full-sample adaptive vs fixed
    cand = max((nm for nm in series if nm != "fixed"),
               key=lambda nm: sharpe(series[nm]))
    print(f"\nbest adaptive full-sample: {cand}")
    diff = series[cand] - base
    print("tercile attribution of (adaptive - fixed), bp/day:")
    print(pd.DataFrame({"E[range] terc": diff.groupby(er_t.reindex(diff.index),
                                                      observed=True).mean() * 1e4}).round(1).to_string())
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "v1v3_results.csv"), index=False)

if __name__ == "__main__":
    main()
