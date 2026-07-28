"""
CORRECTED simulator + re-run of the load-bearing results.

Bug found during V5 (the 09:35 start's Sharpe 5.7 was the tell): the old
sims updated the rolling high with the CURRENT bar before checking entry,
and allowed the entry bar's own high to fill the +1% target. A single bar
with >=1% range could therefore set a trigger 1% below its own high and
instantly "win" off that same high -- unknowable intrabar sequencing
booked as profit. Severity scales with bar range, so it inflated morning
starts massively and the 10:30 core modestly.

Corrected rules (conservative):
  * the trigger uses only PRIOR bars' highs (a resting limit order);
  * on the entry bar itself, only the STOP may fire (adverse case);
    the target can fill from the NEXT bar onward;
  * everything else unchanged (gap-through entries at the open, stop
    checked before target within a bar, 2-stop breaker, cap 5).

Re-run here: T2 map, T1 start sweep, locked-core baseline vs breaker,
cap sweep spot-check, T5 walk-forward on start time.
Outputs: band_lab/out/v5_corrected_*.csv
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

def sim_trades_fixed(o, h, l, c, start_i, last_entry_i=None):
    trades = []
    roll_hi = h[:max(start_i, 1)].max()      # prior bars only
    state = 0; entry = 0.0; entry_i = -1
    for i in range(max(start_i, 1), len(c)):
        if state == 1:
            tgt = entry * (1 + T); stp = entry * (1 - S)
            if l[i] <= stp:
                r = -S if o[i] > stp else o[i] / entry - 1
                trades.append((entry_i, r, "stop")); state = 0
            elif i > entry_i and h[i] >= tgt:
                r = T if o[i] < tgt else o[i] / entry - 1
                trades.append((entry_i, r, "target")); state = 0
        if (state == 0 and len(trades) < MAXTR
                and (last_entry_i is None or i <= last_entry_i)):
            trig = roll_hi * (1 - D)          # roll_hi excludes bar i
            if l[i] <= trig:
                entry = min(trig, o[i]); entry_i = i; state = 1
                stp = entry * (1 - S)         # same-bar stop only
                if l[i] <= stp:
                    trades.append((entry_i, -S if o[i] > stp
                                   else min(o[i] / entry - 1, -S), "stop"))
                    state = 0
        roll_hi = max(roll_hi, h[i])          # update AFTER all checks
    if state == 1:
        trades.append((entry_i, c[-1] / entry - 1, "eod"))
    return trades

def day_pnl(trades, max_stops=MAXSTOP):
    pnl = 0.0; stops = 0
    for _, r, out in trades:
        if stops >= max_stops:
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
    or30 = {d: (gb["High"].to_numpy()[:6].max() - gb["Low"].to_numpy()[:6].min())
               / gb["Open"].iloc[0] * 100 for d, gb in g}
    daily["or30"] = pd.Series(or30)
    orq5_ok = daily["or30"] < daily["or30"].quantile(.8)
    gated = set(daily.index[(daily["atr5"] >= 6) & orq5_ok])
    arrays = {dd: tuple(gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
              for dd, gb in g if dd in gated and len(gb) >= 14}
    res = []

    print("=" * 70)
    print("CORRECTED ENGINE -- LOAD-BEARING RESULTS RE-RUN")
    print("=" * 70)

    # locked core at 10:30: flat vs breaker
    for ms, lbl in [(99, "core 10:30 no breaker"), (2, "core 10:30 breaker2")]:
        p = {dd: day_pnl(sim_trades_fixed(o, h, l, c, 12), ms)
             for dd, (o, h, l, c) in arrays.items()}
        ser = pd.Series(p)
        m = metrics(ser, lbl); res.append(m)
        print(f"{lbl:26s} {m['bp_day']:>6} bp/day  sharpe {m['sharpe']:>5}  "
              f"worst {m['worst_day_pct']}%")
        if ms == 2:
            print("   by year:", byyear(ser))

    # T2 map corrected
    recs = []
    for dd, (o, h, l, c) in arrays.items():
        for ei, r, out in sim_trades_fixed(o, h, l, c, 1):
            recs.append({"bar": ei, "ret": r, "outcome": out})
    tl = pd.DataFrame(recs)
    tl["bucket"] = (tl["bar"] // 6) * 6
    tab = tl.groupby("bucket").agg(
        n=("ret", "size"), mean_bp=("ret", lambda x: round(x.mean() * 1e4, 1)),
        stop_pct=("outcome", lambda x: round((x == "stop").mean() * 100, 0)),
        tgt_pct=("outcome", lambda x: round((x == "target").mean() * 100, 0)))
    tab.index = [bar_time(b) for b in tab.index]
    print("\nT2 corrected edge-by-entry-time:")
    print(tab.to_string())
    tab.to_csv(os.path.join(OUT, "v5_corrected_edge_by_time.csv"))

    # T1 corrected start sweep
    print("\nT1 corrected start sweep:")
    starts = [(1, "09:35"), (6, "10:00"), (9, "10:15"), (12, "10:30*"),
              (18, "11:00"), (24, "11:30"), (30, "12:00"), (42, "13:00")]
    series = {}
    rows = []
    for si, lbl in starts:
        p = {dd: day_pnl(sim_trades_fixed(o, h, l, c, si))
             for dd, (o, h, l, c) in arrays.items()}
        ser = pd.Series(p); series[lbl] = ser
        m = metrics(ser, f"start {lbl}")
        rows.append(m); res.append(m)
    print(pd.DataFrame(rows).to_string(index=False))
    for lbl in ("09:35", "10:00", "10:30*"):
        print(f"  {lbl:7s} by year:", byyear(series[lbl]))

    # T5 walk-forward on corrected series
    print("\nT5 corrected walk-forward (start selected on prior years):")
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
        print(f"  {year}: picked {best:7s} -> OOS {te.mean()*1e4:+.1f} bp/day")
    allo = pd.concat(oos).sort_index()
    sh = allo.mean() / allo.std() * np.sqrt(252)
    print(f"  ALL OOS: {allo.mean()*1e4:.1f} bp/day, Sharpe {sh:.2f}")

    pd.DataFrame(res).to_csv(os.path.join(OUT, "v5_corrected_results.csv"),
                             index=False)

if __name__ == "__main__":
    main()
