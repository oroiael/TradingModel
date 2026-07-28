"""
Walk-forward validation + combined two-sleeve backtest.

Part 1 -- day sleeve (dip-buy churn harvester) walk-forward:
  For each test year 2022..2026, select the config (dip/target/stop x filter
  x ATR gate) with the best Sharpe on ALL data before that year (min 150
  traded train days; the OR30 filter threshold is computed on train data
  only), then trade the test year with it. Reports out-of-sample results.

Part 2 -- cycle sleeve walk-forward:
  Same scheme over the compounding cycle grid (target x stall, no-hedge,
  lot=equity/4): pick by train-period final equity, run the test year
  fresh, chain the yearly OOS returns.

Part 3 -- combined $150K backtest (2022-01-03..end of data):
  Sub-account A: cycle sleeve, 2%/4d/no-hedge/eq4 (round-3 winner).
  Sub-account B: day sleeve, dip1%/tgt1%/stop4%/orq5/ATR5>=6 (band-lab pick).
  Independent compounding (no cross-funding), splits 100/50 and 75/75.

Outputs: band_lab/out/wf_day_sleeve.csv, wf_cycle_sleeve.csv, combo_equity.csv
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars, daily_from_bars
from churn_harvest import sim_day
import compound_engine
from compound_engine import run_compound, load_soxs_daily

OUT = os.path.join(HERE, "out")

def prep(bars):
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    daily["gap_pct"] = (daily["o"] / daily["c"].shift() - 1) * 100
    daily["atr5"] = daily["range_pct"].rolling(5).mean().shift()
    or30 = {d: (gb["High"].to_numpy()[:6].max() - gb["Low"].to_numpy()[:6].min())
               / gb["Open"].iloc[0] * 100 for d, gb in g}
    daily["or30"] = pd.Series(or30)
    return g, daily

def day_sleeve_pnls(g):
    """Pre-compute daily pnl series for every (dip,tgt,stop) combo."""
    combos = [(d, t, s) for d in (.01, .015, .02) for t in (.01, .015)
              for s in (.02, .04)]
    out = {}
    for d, t, s in combos:
        pnl = {}
        for dd, gb in g:
            o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
            if len(c) < 14:
                continue
            p, _ = sim_day(o, h, l, c, 12, d, t, s)
            pnl[dd] = p
        out[(d, t, s)] = pd.Series(pnl)
    return out

def apply_day_filter(ser, daily, filt, gate, orq5_thr):
    idx = ser.index
    keep = pd.Series(True, index=idx)
    if filt == "orq5":
        keep &= daily.loc[idx, "or30"] < orq5_thr
    elif filt == "gap2":
        keep &= daily.loc[idx, "gap_pct"].abs() <= 2
    if gate:
        keep &= daily.loc[idx, "atr5"] >= gate
    return ser[keep.fillna(False)]

def sharpe(s):
    return s.mean() / s.std() * np.sqrt(252) if len(s) > 2 and s.std() > 0 else -9

def main():
    bars = load_bars()
    g, daily = prep(bars)
    soxs = load_soxs_daily()
    base_pnls = day_sleeve_pnls(g)
    last_day = daily.index[-1]

    # ---------------- Part 1: day-sleeve walk-forward
    print("=" * 74)
    print("1. DAY SLEEVE WALK-FORWARD (config re-selected yearly, OOS only)")
    print("=" * 74)
    filters = ["none", "orq5", "gap2"]
    gates = [None, 6.0, 8.0]
    oos = []
    rows = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01")
        t1 = pd.Timestamp(f"{year + 1}-01-01")
        train_days = daily.index[daily.index < t0]
        orq5_thr = daily.loc[train_days, "or30"].quantile(.8)
        best, best_s = None, -99
        for k, ser in base_pnls.items():
            tr_all = ser[ser.index < t0]
            for f in filters:
                for gate in gates:
                    tr = apply_day_filter(tr_all, daily, f, gate, orq5_thr)
                    if (tr != 0).sum() < 150:
                        continue
                    sh = sharpe(tr)
                    if sh > best_s:
                        best_s, best = sh, (k, f, gate)
        (d, t, s), f, gate = best
        te = base_pnls[(d, t, s)]
        te = te[(te.index >= t0) & (te.index < t1)]
        te = apply_day_filter(te, daily, f, gate, orq5_thr)
        oos.append(te)
        rows.append({"year": year, "dip": d * 100, "tgt": t * 100, "stop": s * 100,
                     "filter": f, "gate": gate, "train_sharpe": round(best_s, 2),
                     "oos_days": int((te != 0).sum()),
                     "oos_bp_day": round(te.mean() * 1e4, 1),
                     "oos_sharpe": round(sharpe(te), 2),
                     "oos_sum_pct": round(te.sum() * 100, 1)})
        r = rows[-1]
        print(f"  {year}: picked dip{r['dip']:g}/t{r['tgt']:g}/s{r['stop']:g} "
              f"{r['filter']}/gate{r['gate']}  (train shp {r['train_sharpe']})  ->  "
              f"OOS {r['oos_bp_day']} bp/day, shp {r['oos_sharpe']}, "
              f"sum {r['oos_sum_pct']}%", flush=True)
    wf_day = pd.DataFrame(rows)
    wf_day.to_csv(os.path.join(OUT, "wf_day_sleeve.csv"), index=False)
    all_oos = pd.concat(oos).sort_index()
    print(f"\n  ALL OOS 2022-2026: {all_oos.mean()*1e4:.1f} bp/day, "
          f"Sharpe {sharpe(all_oos):.2f}, "
          f"{(all_oos != 0).sum()} traded days, "
          f"cum (uncompounded) {all_oos.sum()*100:.0f}%")
    print(f"  (full-sample tuned config was 43.5 bp/day, Sharpe 2.14)")

    # ---------------- Part 2: cycle-sleeve walk-forward
    print()
    print("=" * 74)
    print("2. CYCLE SLEEVE WALK-FORWARD (target/stall re-selected yearly)")
    print("=" * 74)
    grid = [(tgt, st) for tgt in (.01, .015, .02, .025, .03, .04)
            for st in (2, 3, 4, 5, 7)]
    hist_start = daily.index[0]
    rows = []
    chained = 1.0
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01")
        t1 = min(pd.Timestamp(f"{year + 1}-01-01"), last_day + pd.Timedelta(days=1))
        best, best_eq = None, -1
        for tgt, st in grid:
            s, _ = run_compound(bars, daily, soxs, hist_start, t0 - pd.Timedelta(days=1),
                                target=tgt, stall_days=st, mode="none", sizing="eq4")
            if s["final_equity"] > best_eq:
                best_eq, best = s["final_equity"], (tgt, st)
        tgt, st = best
        s, _ = run_compound(bars, daily, soxs, t0, t1 - pd.Timedelta(days=1),
                            target=tgt, stall_days=st, mode="none", sizing="eq4")
        yr_ret = s["final_equity"] / compound_engine.START_EQ - 1
        chained *= 1 + yr_ret
        rows.append({"year": year, "picked_target": tgt * 100, "picked_stall": st,
                     "oos_ret_pct": round(yr_ret * 100, 1),
                     "oos_max_dd_pct": s["max_dd_pct"]})
        print(f"  {year}: picked target {tgt*100:g}% / stall {st}d  ->  "
              f"OOS {yr_ret*100:+.1f}%  (dd {s['max_dd_pct']}%)", flush=True)
    wf_cyc = pd.DataFrame(rows)
    wf_cyc.to_csv(os.path.join(OUT, "wf_cycle_sleeve.csv"), index=False)
    yrs = 4.5
    print(f"\n  chained OOS 2022-2026: $150K -> ${150000*chained:,.0f} "
          f"({(chained**(1/yrs)-1)*100:.1f}% CAGR)")
    print(f"  (full-sample tuned 2%/4d was 46.1% CAGR on the same span)")

    # ---------------- Part 3: combined two-sleeve $150K backtest
    print()
    print("=" * 74)
    print("3. COMBINED $150K BACKTEST 2022-01-03..{} (fixed configs)".format(
        last_day.date()))
    print("=" * 74)
    start = pd.Timestamp("2022-01-03")
    _, eq_cycle = run_compound(bars, daily, soxs, start, last_day,
                               target=.02, stall_days=4, mode="none", sizing="eq4")
    cyc_curve = eq_cycle["equity"] / compound_engine.START_EQ   # growth multiple

    orq5_thr = daily.loc[daily.index < start, "or30"].quantile(.8)
    day_ser = apply_day_filter(base_pnls[(.01, .01, .04)], daily, "orq5", 6.0,
                               orq5_thr)
    day_ser = day_ser[day_ser.index >= start]
    day_daily = day_ser.reindex(cyc_curve.index).fillna(0.0)
    day_curve = (1 + day_daily).cumprod()

    cyc_ret = cyc_curve.pct_change().fillna(0)
    corr = cyc_ret.corr(day_daily)
    print(f"  sleeve daily-return correlation: {corr:.2f}")

    rows = []
    for a, b in [(150, 0), (100, 50), (75, 75), (0, 150)]:
        eq = a * 1000 * cyc_curve + b * 1000 * day_curve
        yrs = (eq.index[-1] - eq.index[0]).days / 365.25
        cagr = (eq.iloc[-1] / 150000) ** (1 / yrs) - 1
        dd = ((eq - eq.cummax()) / eq.cummax()).min()
        rows.append({"split_cycle_k": a, "split_day_k": b,
                     "final": round(eq.iloc[-1], 0),
                     "cagr_pct": round(cagr * 100, 1),
                     "max_dd_pct": round(dd * 100, 1)})
        print(f"  cycle ${a}K + day ${b}K:  final ${eq.iloc[-1]:>11,.0f}  "
              f"CAGR {cagr*100:5.1f}%  maxDD {dd*100:6.1f}%", flush=True)
        if (a, b) == (100, 50):
            pd.DataFrame({"cycle_eq": a * 1000 * cyc_curve,
                          "day_eq": b * 1000 * day_curve,
                          "total": eq}).to_csv(os.path.join(OUT, "combo_equity.csv"))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "combo_summary.csv"), index=False)

if __name__ == "__main__":
    main()
