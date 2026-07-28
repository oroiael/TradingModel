"""
V5 start-time program — execution (spec: V5_START_TIME_TESTS.md).
Order: T2 edge-by-entry-time map -> T1 start sweep -> T4 last-entry cutoff
-> T3 conditional start -> T5 walk-forward + plateau.

Locked core throughout: dip 1%, target 1%, stop 4%, cap 5, 2-stop breaker,
orq5 filter, ATR5>=6 gate. Bar i covers 09:30+5i min (start 10:30 = bar 12).

Outputs: band_lab/out/v5_results.csv + printed report.
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
D, T, S, MAXTR, MAXSTOP = .01, .01, .04, 5, 2

def sim_trades(o, h, l, c, start_i, last_entry_i=None):
    trades = []
    roll_hi = h[:start_i].max() if start_i > 0 else h[0]
    state = 0; entry = 0.0; entry_i = 0
    for i in range(start_i, len(c)):
        roll_hi = max(roll_hi, h[i])
        if (state == 0 and len(trades) < MAXTR
                and (last_entry_i is None or i <= last_entry_i)):
            trig = roll_hi * (1 - D)
            if l[i] <= trig:
                entry = min(trig, o[i]); entry_i = i; state = 1
        if state == 1:
            tgt = entry * (1 + T); stp = entry * (1 - S)
            if l[i] <= stp:
                r = -S if o[i] > stp else o[i] / entry - 1
                trades.append((entry_i, r, "stop")); state = 0
            elif h[i] >= tgt:
                r = T if o[i] < tgt else o[i] / entry - 1
                trades.append((entry_i, r, "target")); state = 0
    if state == 1:
        trades.append((entry_i, c[-1] / entry - 1, "eod"))
    return trades

def day_pnl(trades):
    """apply the 2-stop breaker"""
    pnl = 0.0; stops = 0
    for _, r, out in trades:
        if stops >= MAXSTOP:
            break
        pnl += r
        if out == "stop":
            stops += 1
    return pnl

def bar_time(i):
    m = 9 * 60 + 30 + 5 * i
    return f"{m//60:02d}:{m%60:02d}"

def main():
    bars = load_bars()
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    daily["atr5"] = daily["range_pct"].rolling(5).mean().shift()
    daily["gap_pct"] = (daily["o"] / daily["c"].shift() - 1) * 100
    or30 = {d: (gb["High"].to_numpy()[:6].max() - gb["Low"].to_numpy()[:6].min())
               / gb["Open"].iloc[0] * 100 for d, gb in g}
    daily["or30"] = pd.Series(or30)
    orq5_ok = daily["or30"] < daily["or30"].quantile(.8)
    gated = set(daily.index[(daily["atr5"] >= 6) & orq5_ok])
    arrays = {}
    for dd, gb in g:
        if dd in gated and len(gb) >= 14:
            arrays[dd] = tuple(gb[x].to_numpy()
                               for x in ["Open", "High", "Low", "Close"])
    res = []

    # ---------------- T2: edge-by-entry-time map (start 09:35, raw trades)
    print("=" * 70); print("T2. EDGE BY ENTRY TIME (start 09:35, no breaker)")
    print("=" * 70)
    recs = []
    for dd, (o, h, l, c) in arrays.items():
        for ei, r, out in sim_trades(o, h, l, c, 1):
            recs.append({"date": dd, "bar": ei, "ret": r, "outcome": out})
    tl = pd.DataFrame(recs)
    tl["bucket"] = (tl["bar"] // 6) * 6
    tab = tl.groupby("bucket").agg(
        n=("ret", "size"), mean_bp=("ret", lambda x: round(x.mean() * 1e4, 1)),
        stop_pct=("outcome", lambda x: round((x == "stop").mean() * 100, 0)),
        tgt_pct=("outcome", lambda x: round((x == "target").mean() * 100, 0)),
        eod_pct=("outcome", lambda x: round((x == "eod").mean() * 100, 0)))
    tab.index = [bar_time(b) for b in tab.index]
    print(tab.to_string())
    tab.to_csv(os.path.join(OUT, "v5_edge_by_time.csv"))

    # ---------------- T1: start-time sweep
    print(); print("=" * 70); print("T1. START-TIME SWEEP"); print("=" * 70)
    starts = [(1, "09:35"), (6, "10:00"), (9, "10:15"), (12, "10:30*"),
              (18, "11:00"), (24, "11:30"), (30, "12:00"), (42, "13:00")]
    series = {}
    for si, lbl in starts:
        p = {dd: day_pnl(sim_trades(o, h, l, c, si))
             for dd, (o, h, l, c) in arrays.items()}
        ser = pd.Series(p); series[lbl] = ser
        ntr = np.mean([min(len(sim_trades(o, h, l, c, si)), 5)
                       for (o, h, l, c) in list(arrays.values())[:200]])
        m = metrics(ser, f"start {lbl}")
        m["trades_day"] = round(ntr, 2)
        res.append(m)
    t1 = pd.DataFrame([r for r in res if r["variant"].startswith("start")])
    print(t1.to_string(index=False))
    for lbl in ("09:35", "10:00", "10:30*", "11:00"):
        print(f"  {lbl:7s} by year:", byyear(series[lbl]))

    # ---------------- T4: last-entry cutoff (on incumbent start unless beaten)
    best_start_lbl = t1.sort_values("sharpe", ascending=False).iloc[0]["variant"].split()[1]
    incumbent = "10:30*"
    # plateau standard: challenger must beat on sharpe AND worst-day
    ch = t1[t1["variant"] == f"start {best_start_lbl}"].iloc[0]
    inc = t1[t1["variant"] == f"start {incumbent}"].iloc[0]
    use = best_start_lbl if (ch["sharpe"] > inc["sharpe"] and
                             ch["worst_day_pct"] >= inc["worst_day_pct"] and
                             best_start_lbl != incumbent) else incumbent
    use_i = dict((lbl, si) for si, lbl in starts)[use]
    print(f"\nT4 uses start {use} (plateau verdict)")
    print("=" * 70); print("T4. LAST-ENTRY CUTOFF"); print("=" * 70)
    for cei, lbl in [(54, "14:00"), (66, "15:00"), (72, "15:30"), (None, "none*")]:
        p = {dd: day_pnl(sim_trades(o, h, l, c, use_i, cei))
             for dd, (o, h, l, c) in arrays.items()}
        m = metrics(pd.Series(p), f"cutoff {lbl}")
        res.append(m)
    print(pd.DataFrame(res[-4:]).to_string(index=False))

    # ---------------- T3: conditional start (one prespecified rule)
    print(); print("=" * 70); print("T3. CONDITIONAL START"); print("=" * 70)
    med_or30 = daily["or30"].rolling(252).median().shift()
    p = {}
    for dd, (o, h, l, c) in arrays.items():
        calm = (abs(daily.loc[dd, "gap_pct"]) < 1
                and daily.loc[dd, "or30"] < med_or30.get(dd, np.inf))
        p[dd] = day_pnl(sim_trades(o, h, l, c, 6 if calm else 18))
    ser = pd.Series(p)
    m = metrics(ser, "T3 conditional 10:00/11:00")
    res.append(m)
    print(pd.DataFrame([m]).to_string(index=False))
    print("  by year:", byyear(ser))

    # ---------------- T5: walk-forward + plateau on start time
    print(); print("=" * 70); print("T5. WALK-FORWARD (start selected on prior years)")
    print("=" * 70)
    oos = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01"); t1_ = pd.Timestamp(f"{year+1}-01-01")
        best, bs = None, -99
        for si, lbl in starts:
            tr = series[lbl][series[lbl].index < t0]
            sh = tr.mean() / tr.std() * np.sqrt(252) if tr.std() > 0 else -99
            if sh > bs:
                bs, best = sh, lbl
        te = series[best][(series[best].index >= t0) & (series[best].index < t1_)]
        oos.append(te)
        print(f"  {year}: picked {best:7s} -> OOS {te.mean()*1e4:+.1f} bp/day "
              f"({len(te)} days)")
    allo = pd.concat(oos).sort_index()
    sh = allo.mean() / allo.std() * np.sqrt(252)
    print(f"  ALL OOS: {allo.mean()*1e4:.1f} bp/day, Sharpe {sh:.2f} "
          f"(incumbent 10:30 full-sample: 44.9 bp, 2.25)")

    pd.DataFrame(res).to_csv(os.path.join(OUT, "v5_results.csv"), index=False)

if __name__ == "__main__":
    main()
