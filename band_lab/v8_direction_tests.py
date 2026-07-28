"""
V8 direction & concurrency program — execution (spec: V8_DIRECTION_TESTS.md).
Order: T1 mirror short -> T2 SOXS vehicle -> T6 audit -> T3 two-sided ->
T4 pyramiding -> T5 excursion momentum.

Short side inherits the locked long parameters mirrored (dip->rally 1%,
target 1%, stop 4%, start 10:30, cap 5, 2-stop breaker, orq5 filter,
ATR5>=6 gate). T1b re-runs the mirror with signal-bar-CLOSE fills so the
T2-T1b gap isolates vehicle drag from fill-style drag.

Outputs: band_lab/out/v8_results.csv + printed report.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars, ROOT
from v11_sizing_tests import metrics, byyear

OUT = os.path.join(HERE, "out")

D, T, S = .01, .01, .04
MAXTR, MAXSTOP, START_I = 5, 2, 12

def sim_short(o, h, l, c, sx=None, fill="touch"):
    """Mirror of the locked core. sx = aligned SOXS closes (T2 vehicle);
    with sx, entries/exits happen at signal-bar SOXS closes."""
    roll_lo = l[:START_I].min()
    state = 0; trades = 0; stops = 0; pnl = 0.0
    entry_sig = entry_veh = 0.0
    for i in range(START_I, len(c)):
        roll_lo = min(roll_lo, l[i])
        if state == 0 and trades < MAXTR and stops < MAXSTOP:
            trig = roll_lo * (1 + D)
            if h[i] >= trig:
                entry_sig = max(trig, o[i]) if fill == "touch" else c[i]
                entry_veh = sx[i] if sx is not None else entry_sig
                state = 1; trades += 1
        if state == 1:
            tgt = entry_sig * (1 - T); stp = entry_sig * (1 + S)
            hit_stop = h[i] >= stp
            hit_tgt = l[i] <= tgt
            if hit_stop or hit_tgt:
                if sx is not None:                      # vehicle: SOXS close
                    pnl += sx[i] / entry_veh - 1
                elif fill == "close":
                    pnl += 1 - c[i] / entry_sig
                elif hit_stop:
                    pnl += -S if o[i] < stp else 1 - o[i] / entry_sig
                else:
                    pnl += T if o[i] > tgt else 1 - o[i] / entry_sig
                if hit_stop:
                    stops += 1
                state = 0
    if state == 1:
        pnl += (sx[-1] / entry_veh - 1) if sx is not None else 1 - c[-1] / entry_sig
    return pnl, trades

def sim_pyramid(o, h, l, c, mode):
    """Two units, unit2 added 1% below unit1's entry, f/2 per unit."""
    roll_hi = h[:START_I].max()
    units = []; trades = 0; stops = 0; pnl = 0.0
    for i in range(START_I, len(c)):
        roll_hi = max(roll_hi, h[i])
        if not units and trades < MAXTR and stops < MAXSTOP:
            trig = roll_hi * (1 - D)
            if l[i] <= trig:
                units = [min(trig, o[i])]; trades += 1
        elif len(units) == 1 and trades < MAXTR and stops < MAXSTOP:
            trig2 = units[0] * (1 - D)
            if l[i] <= trig2:
                units.append(min(trig2, o[i])); trades += 1
        if units and mode == "shared":
            tgt = units[0] * (1 + T); stp = units[0] * (1 - S)
            if l[i] <= stp:
                px = o[i] if o[i] < stp else stp
                pnl += 0.5 * sum(px / e - 1 for e in units)
                stops += 1; units = []
            elif h[i] >= tgt:
                px = o[i] if o[i] > tgt else tgt
                pnl += 0.5 * sum(px / e - 1 for e in units)
                units = []
        elif units and mode == "perunit":
            keep = []
            for e in units:
                tgt = e * (1 + T); stp = e * (1 - S)
                if l[i] <= stp:
                    px = o[i] if o[i] < stp else stp
                    pnl += 0.5 * (px / e - 1); stops += 1
                elif h[i] >= tgt:
                    px = o[i] if o[i] > tgt else tgt
                    pnl += 0.5 * (px / e - 1)
                else:
                    keep.append(e)
            units = keep
    for e in units:
        pnl += 0.5 * (c[-1] / e - 1)
    return pnl, trades

def sim_breakout(o, h, l, c):
    orh = h[:6].max(); orl = l[:6].min(); orr = orh - orl
    if orr <= 0:
        return 0.0
    mid = (orh + orl) / 2; bo = orh + 0.25 * orr
    for i in range(6, len(c)):
        if h[i] >= bo:
            entry = max(bo, o[i])
            for j in range(i, len(c)):
                if l[j] <= mid:
                    px = o[j] if o[j] < mid else mid
                    return px / entry - 1
            return c[-1] / entry - 1
    return 0.0

def load_soxs_bars():
    df = pd.read_csv(os.path.join(ROOT, "SOXS_5min_6Years.csv"))
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    return df.assign(dt=dt, date=dt.dt.normalize())

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
    orq5_thr = daily["or30"].quantile(.8)
    orq5_ok = daily["or30"] < orq5_thr
    gated = daily.index[(daily["atr5"] >= 6) & orq5_ok]

    soxs = load_soxs_bars()
    sg = {d: gb for d, gb in soxs.groupby("date")}

    res = []
    # ---------- T1 / T1b / T2 ----------
    print("=" * 70); print("T1/T1b/T2. SHORT SIDE"); print("=" * 70)
    p_touch, p_close, p_soxs = {}, {}, {}
    for dd, gb in g:
        if dd not in gated:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        if len(c) < 14:
            continue
        p_touch[dd], _ = sim_short(o, h, l, c, fill="touch")
        p_close[dd], _ = sim_short(o, h, l, c, fill="close")
        sb = sg.get(dd)
        if sb is not None:
            m = pd.merge(gb[["dt"]].reset_index(drop=True).assign(i=range(len(gb))),
                         sb[["dt", "Close"]], on="dt", how="inner")
            if len(m) == len(gb):
                p_soxs[dd], _ = sim_short(o, h, l, c,
                                          sx=m["Close"].to_numpy(), fill="close")
    t1 = pd.Series(p_touch); t1b = pd.Series(p_close); t2 = pd.Series(p_soxs)
    for name, ser in [("T1 mirror short (touch fills)", t1),
                      ("T1b mirror short (close fills)", t1b),
                      ("T2 via SOXS long", t2)]:
        res.append(metrics(ser, name))
        print(f"{name:34s} {res[-1]['bp_day']:>7} bp/day  sharpe "
              f"{res[-1]['sharpe']:>5}  worst {res[-1]['worst_day_pct']}%")
        print("   by year:", byyear(ser))
    print(f"\nfill-style drag (T1b-T1): {(t1b.mean()-t1.mean())*1e4:+.1f} bp/day")
    common = t1b.index.intersection(t2.index)
    print(f"vehicle drag (T2-T1b, {len(common)} common days): "
          f"{(t2[common].mean()-t1b[common].mean())*1e4:+.1f} bp/day")

    # ---------- T6 audit ----------
    print(); print("=" * 70); print("T6. SHORT REALITY AUDIT"); print("=" * 70)
    ssr_trig = daily["l"] <= daily["c"].shift() * 0.90
    ssr_active = (ssr_trig | ssr_trig.shift(fill_value=False))
    print(f"SSR (uptick rule) active: {ssr_active.mean()*100:.1f}% of ALL days, "
          f"{ssr_active.reindex(gated).mean()*100:.1f}% of GATED days")
    for ann in (0.01, 0.05, 0.10):
        print(f"borrow drag at {ann*100:.0f}%/yr, ~2h avg hold: "
              f"{ann/252*2/6.5*1e4:.1f} bp/traded-day")

    # ---------- T3 two-sided ----------
    print(); print("=" * 70); print("T3. TWO-SIDED"); print("=" * 70)
    from v11_sizing_tests import sim_day_trades
    p_long = {}
    for dd, gb in g:
        if dd not in gated:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        if len(c) < 14:
            continue
        trs = sim_day_trades(o, h, l, c, START_I, D, T, S)
        pnl = 0.0; stops = 0
        for tr in trs:
            if stops >= MAXSTOP:
                break
            pnl += tr["ret"]
            if tr["outcome"] == "stop":
                stops += 1
        p_long[dd] = pnl
    pl = pd.Series(p_long)
    both = pl.index.intersection(t1.index)
    corr = pl[both].corr(t1[both])
    print(f"long/short daily P&L correlation: {corr:.2f}")
    fifty = 0.5 * pl[both] + 0.5 * t1[both]
    res.append(metrics(fifty, "T3 50/50 long+mirror-short"))
    print(pd.DataFrame([metrics(pl[both], "long core alone"),
                        res[-1]]).to_string(index=False))

    # ---------- T4 pyramiding ----------
    print(); print("=" * 70); print("T4. PYRAMIDING (equal max capital)"); print("=" * 70)
    for mode in ("shared", "perunit"):
        p = {}
        for dd, gb in g:
            if dd not in gated:
                continue
            o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
            if len(c) < 14:
                continue
            p[dd], _ = sim_pyramid(o, h, l, c, mode)
        ser = pd.Series(p)
        res.append(metrics(ser, f"T4 pyramid {mode} (f/2 per unit)"))
        print(pd.DataFrame([res[-1]]).to_string(index=False))
        print("   by year:", byyear(ser))
    print(pd.DataFrame([metrics(pl, "baseline core f=1 (ref)")]).to_string(index=False))

    # ---------- T5 excursion momentum ----------
    print(); print("=" * 70); print("T5. EXCURSION-DAY MOMENTUM"); print("=" * 70)
    for label, cohort in [
            ("orq5-skipped days", daily.index[~orq5_ok]),
            ("orq5-skipped & ATR>=6", daily.index[~orq5_ok & (daily["atr5"] >= 6)])]:
        p = {}
        for dd in cohort:
            if dd not in g.groups:
                continue
            gb = g.get_group(dd)
            o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
            if len(c) < 10:
                continue
            p[dd] = sim_breakout(o, h, l, c)
        ser = pd.Series(p)
        traded = ser[ser != 0]
        res.append(metrics(ser, f"T5 breakout ride ({label})"))
        print(f"{label}: {len(ser)} days, triggered {len(traded)} "
              f"({len(traded)/max(len(ser),1)*100:.0f}%), mean "
              f"{ser.mean()*1e4:+.1f} bp/day, trig-day mean "
              f"{traded.mean()*100:+.2f}%, win {((traded>0).mean()*100):.0f}%")
        print("   by year:", byyear(ser))

    pd.DataFrame(res).to_csv(os.path.join(OUT, "v8_results.csv"), index=False)

if __name__ == "__main__":
    main()
