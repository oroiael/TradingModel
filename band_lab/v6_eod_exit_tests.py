"""
V6 EOD-exit program — execution (spec: V6_EOD_EXIT_TESTS.md).
Corrected engine rules throughout (prior-bar trigger, next-bar target,
same-bar stop). Locked config: start 11:00 (bar 18), dip 1%, target 1%,
stop 4%, cap 5, 2-stop breaker, orq5 filter, ATR5>=6 gate.

T1 anatomy of forced EOD exits (+ held-position pricing)
T2 exit-time sweep
T3 overnight-hold variants (a) to-open (b) to-resolution<=3d (c) winners-only
T4 cutoff interaction (only if T3 adopts)
T5 walk-forward + gap stress + role review inputs

Outputs: band_lab/out/v6_*.csv + printed report.
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
D, T, S, MAXTR, MAXSTOP, START_I = .01, .01, .04, 5, 2, 18

def sim_v6(o, h, l, c, end_i=None):
    """Corrected-engine sim; returns trade dicts. end_i = forced-flat bar
    (entries stop there too); None = last bar (incumbent)."""
    last = len(c) - 1 if end_i is None else min(end_i, len(c) - 1)
    trades = []
    roll_hi = h[:START_I].max()
    state = 0; entry = 0.0; entry_i = -1
    for i in range(START_I, last + 1):
        if state == 1:
            tgt = entry * (1 + T); stp = entry * (1 - S)
            if l[i] <= stp:
                r = -S if o[i] > stp else o[i] / entry - 1
                trades.append({"entry_i": entry_i, "entry": entry, "ret": r,
                               "outcome": "stop"}); state = 0
            elif i > entry_i and h[i] >= tgt:
                r = T if o[i] < tgt else o[i] / entry - 1
                trades.append({"entry_i": entry_i, "entry": entry, "ret": r,
                               "outcome": "target"}); state = 0
        if state == 0 and len(trades) < MAXTR and i < last:
            trig = roll_hi * (1 - D)
            if l[i] <= trig:
                entry = min(trig, o[i]); entry_i = i; state = 1
                stp = entry * (1 - S)
                if l[i] <= stp:
                    trades.append({"entry_i": entry_i, "entry": entry,
                                   "ret": -S if o[i] > stp
                                   else min(o[i] / entry - 1, -S),
                                   "outcome": "stop"})
                    state = 0
        roll_hi = max(roll_hi, h[i])
    if state == 1:
        trades.append({"entry_i": entry_i, "entry": entry,
                       "ret": c[last] / entry - 1, "outcome": "eod"})
    return trades

def day_pnl(trades):
    pnl = 0.0; stops = 0; eod_open = None
    for tr in trades:
        if stops >= MAXSTOP:
            break
        if tr["outcome"] == "eod":
            eod_open = tr
        pnl += tr["ret"]
        if tr["outcome"] == "stop":
            stops += 1
    return pnl, eod_open

def resolve_forward(entry, day_list, arrays, start_pos, max_days=3):
    """Held position: work target/stop over the next max_days sessions."""
    tgt = entry * (1 + T); stp = entry * (1 - S)
    for k in range(1, max_days + 1):
        if start_pos + k >= len(day_list):
            break
        dd = day_list[start_pos + k]
        if dd not in arrays:
            continue
        o, h, l, c = arrays[dd]
        for i in range(len(c)):
            if l[i] <= stp:
                px = o[i] if o[i] < stp else stp
                return px / entry - 1, k
            if h[i] >= tgt:
                px = o[i] if o[i] > tgt else tgt
                return px / entry - 1, k
        if k == max_days:
            return c[-1] / entry - 1, k
    return None, None

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
    all_days = list(daily.index)
    day_pos = {d: i for i, d in enumerate(all_days)}
    arrays = {dd: tuple(gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
              for dd, gb in g if len(gb) >= 20}
    garrays = {dd: a for dd, a in arrays.items() if dd in gated}

    # base trades + eod inventory
    base_p = {}; eods = []
    n_trades = 0
    for dd, (o, h, l, c) in garrays.items():
        trades = sim_v6(o, h, l, c)
        p, eod = day_pnl(trades)
        base_p[dd] = p
        n_trades += len(trades)
        if eod is not None:
            eods.append({"date": dd, **eod})
    base = pd.Series(base_p)

    # ---------------- T1 anatomy
    print("=" * 70); print("T1. FORCED-EOD-EXIT ANATOMY"); print("=" * 70)
    ed = pd.DataFrame(eods)
    print(f"trades total {n_trades}; forced EOD exits {len(ed)} "
          f"({len(ed)/n_trades*100:.1f}% of trades, "
          f"{len(ed)/len(base)*100:.0f}% of days)")
    print(f"forced-exit return: mean {ed['ret'].mean()*1e4:+.1f} bp, "
          f"median {ed['ret'].median()*1e4:+.1f} bp, "
          f"share negative {(ed['ret']<0).mean()*100:.0f}%")
    marks = {"held_to_open": [], "held_to_1100": [], "held_to_resolution": []}
    res_days = []
    for _, row in ed.iterrows():
        pos = day_pos[row["date"]]
        if pos + 1 >= len(all_days):
            continue
        nd = all_days[pos + 1]
        if nd not in arrays:
            continue
        o, h, l, c = arrays[nd]
        E = row["entry"]
        marks["held_to_open"].append(o[0] / E - 1)
        marks["held_to_1100"].append(c[min(17, len(c) - 1)] / E - 1)
        rr, k = resolve_forward(E, all_days, arrays, pos)
        if rr is not None:
            marks["held_to_resolution"].append(rr); res_days.append(k)
    for k2, v in marks.items():
        v = pd.Series(v)
        print(f"{k2:20s}: mean {v.mean()*1e4:+.1f} bp  median "
              f"{v.median()*1e4:+.1f} bp  min {v.min()*100:.1f}%  "
              f"P5 {v.quantile(.05)*100:.1f}%")
    print(f"resolution length: median {np.median(res_days):.0f} day(s)")
    fx = ed["ret"].mean(); ho = np.mean(marks["held_to_open"])
    print(f"\nheld-to-open minus forced-exit: {(ho-fx)*1e4:+.1f} bp per EOD trade")
    ed.to_csv(os.path.join(OUT, "v6_eod_trades.csv"), index=False)

    # ---------------- T2 exit-time sweep
    print(); print("=" * 70); print("T2. EXIT-TIME SWEEP"); print("=" * 70)
    rows = []
    for ei, lbl in [(71, "15:30"), (74, "15:45"), (76, "15:55"),
                    (None, "close*")]:
        p = {dd: day_pnl(sim_v6(o, h, l, c, ei))[0]
             for dd, (o, h, l, c) in garrays.items()}
        rows.append(metrics(pd.Series(p), f"flat {lbl}"))
    print(pd.DataFrame(rows).to_string(index=False))

    # ---------------- T3 overnight variants
    print(); print("=" * 70); print("T3. OVERNIGHT-HOLD VARIANTS"); print("=" * 70)
    variants = {"incumbent flat": base}
    # (a) hold to next open ; (c) winners-only to next open
    for name, cond in [("a) hold-to-open", lambda r, cl: True),
                       ("c) winners-only", lambda r, cl: cl > r["entry"])]:
        p = dict(base_p)
        worst_gap = 0.0
        for _, row in ed.iterrows():
            dd = row["date"]; pos = day_pos[dd]
            cl = arrays[dd][3][-1]
            if pos + 1 >= len(all_days) or all_days[pos + 1] not in arrays:
                continue
            if not cond(row, cl):
                continue
            no = arrays[all_days[pos + 1]][0][0]
            gap = no / row["entry"] - 1
            p[dd] = p[dd] - row["ret"] + gap        # replace forced exit
            worst_gap = min(worst_gap, no / cl - 1)
        ser = pd.Series(p); variants[name] = ser
        m = metrics(ser, f"T3 {name}")
        m["worst_overnight_gap"] = f"{worst_gap*100:.1f}%"
        rows.append(m)
        print(pd.DataFrame([m]).to_string(index=False))
        print("   by year:", byyear(ser))
    # (b) hold to resolution
    p = dict(base_p)
    for _, row in ed.iterrows():
        dd = row["date"]; pos = day_pos[dd]
        rr, _ = resolve_forward(row["entry"], all_days, arrays, pos)
        if rr is not None:
            p[dd] = p[dd] - row["ret"] + rr
    ser = pd.Series(p); variants["b) hold-to-resolution"] = ser
    m = metrics(ser, "T3 b) hold-to-resolution")
    rows.append(m)
    print(pd.DataFrame([m]).to_string(index=False))
    print("   by year:", byyear(ser))
    print("   (note: (b) modeled without blocking next-day entries — "
          "optimistic on capital; only matters if (b) wins)")

    # ---------------- T5 walk-forward + gap stress
    print(); print("=" * 70); print("T5. WALK-FORWARD + GAP STRESS"); print("=" * 70)
    oos = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01"); t1_ = pd.Timestamp(f"{year+1}-01-01")
        best, bs = None, -99
        for name, ser in variants.items():
            tr = ser[ser.index < t0]
            sh = tr.mean() / tr.std() * np.sqrt(252) if tr.std() > 0 else -99
            if sh > bs:
                bs, best = sh, name
        te = variants[best][(variants[best].index >= t0)
                            & (variants[best].index < t1_)]
        oos.append(te)
        print(f"  {year}: picked {best:22s} -> OOS {te.mean()*1e4:+.1f} bp/day")
    allo = pd.concat(oos).sort_index()
    print(f"  ALL OOS: {allo.mean()*1e4:.1f} bp/day, Sharpe "
          f"{allo.mean()/allo.std()*np.sqrt(252):.2f}")
    gaps = (daily["o"] / daily["c"].shift() - 1).dropna()
    big = gaps.abs().nlargest(5)
    print("\n  five biggest overnight gaps in sample (stress inputs):")
    for dt, gv in big.items():
        print(f"    {dt.date()}: {gaps[dt]*100:+.1f}%")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "v6_results.csv"), index=False)

if __name__ == "__main__":
    main()
