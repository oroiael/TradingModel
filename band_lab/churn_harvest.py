"""
Churn harvester v2 -- informed by band_analysis.py findings:
  * the band is ~68% set by 10:30, so trade after it is known;
  * steep excursions are morning/gap phenomena with OR30 ~5.7% signatures;
  * 15 completed >=1% swings happen per day.

Day plan tested here (long-only, % terms, one unit per trade, no compounding):
  from 10:30, buy when price has dipped `d`% off the intraday rolling high;
  sell at +`t`% from entry; optional stop at -`s`%; force-flat at the close
  (never holds overnight => structurally neutral to overnight/gap breakouts).
  Optional entry filters from the signal work:
    orq5  -- skip days whose opening-30-min range is in the top quintile
             (trend/excursion signature);
    gap2  -- skip days with |overnight gap| > 2%;
    exc   -- skip the day after an excursion day (32% repeat probability).

Outputs: band_lab/out/churn_grid.csv (+ printed report)
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
from one_pct_cycle_lab import load_bars

OUT = os.path.join(HERE, "out")

def sim_day(o, h, l, c, start_i, d, t, s, max_trades=5):
    pnl = 0.0; trades = 0
    roll_hi = h[:start_i].max() if start_i > 0 else h[0]
    state = 0; entry = 0.0
    for i in range(start_i, len(c)):
        roll_hi = max(roll_hi, h[i])
        if state == 0 and trades < max_trades:
            trig = roll_hi * (1 - d)
            if l[i] <= trig:
                entry = min(trig, o[i])   # gap-through fills at the open
                state = 1; trades += 1
        if state == 1:
            tgt = entry * (1 + t)
            stp = entry * (1 - s)
            if l[i] <= stp:
                pnl += -s if o[i] > stp else o[i] / entry - 1
                state = 0
            elif h[i] >= tgt:
                pnl += t if o[i] < tgt else o[i] / entry - 1
                state = 0
    if state == 1:
        pnl += c[-1] / entry - 1
    return pnl, trades

def main():
    bars = load_bars()
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["gap_pct"] = (daily["o"] / daily["c"].shift() - 1) * 100

    or30, steep = {}, {}
    day_arrays = {}
    for dd, gb in g:
        o = gb["Open"].to_numpy(); h = gb["High"].to_numpy()
        l = gb["Low"].to_numpy(); c = gb["Close"].to_numpy()
        day_arrays[dd] = (o, h, l, c)
        or30[dd] = (h[:6].max() - l[:6].min()) / o[0] * 100
        m = pd.Series(c).pct_change(6).abs()
        steep[dd] = m.max() * 100 if len(c) > 6 else 0
    daily["or30"] = pd.Series(or30)
    daily["steep30"] = pd.Series(steep)
    orq5_thr = daily["or30"].quantile(.8)
    exc_thr = daily["steep30"].quantile(.9)
    daily["excursion"] = daily["steep30"] >= exc_thr
    daily["skip_orq5"] = daily["or30"] >= orq5_thr
    daily["skip_gap2"] = daily["gap_pct"].abs() > 2
    daily["skip_exc"] = daily["excursion"].shift(fill_value=False)

    START_I = 12   # 10:30 (12 bars from 09:30)
    filters = {
        "none":        None,
        "orq5":        ["skip_orq5"],
        "gap2":        ["skip_gap2"],
        "orq5+gap2":   ["skip_orq5", "skip_gap2"],
        "orq5+exc":    ["skip_orq5", "skip_exc"],
    }
    rows = []
    daily_pnls = {}
    for d in [0.01, 0.015, 0.02, 0.03]:
        for t in [0.01, 0.015, 0.02]:
            for s in [0.02, 0.04, 9.9]:
                pnl = {}
                ntr = 0
                for dd, (o, h, l, c) in day_arrays.items():
                    if len(c) < START_I + 2:
                        continue
                    p, n = sim_day(o, h, l, c, START_I, d, t, s)
                    pnl[dd] = p; ntr += n
                ser = pd.Series(pnl)
                for fname, fcols in filters.items():
                    if fcols is None:
                        sel = ser
                    else:
                        mask = ~daily[fcols].any(axis=1)
                        sel = ser[ser.index.isin(mask[mask].index)]
                    if len(sel) == 0:
                        continue
                    rows.append({
                        "dip": d * 100, "tgt": t * 100,
                        "stop": None if s > 1 else s * 100, "filter": fname,
                        "days_traded": int((sel != 0).sum()),
                        "mean_bp_day": round(sel.mean() * 1e4, 1),
                        "ann_pct": round(sel.mean() * 252 * 100, 1),
                        "win_days_pct": round((sel[sel != 0] > 0).mean() * 100, 0),
                        "worst_day_pct": round(sel.min() * 100, 1),
                        "sharpe": round(sel.mean() / sel.std() * np.sqrt(252), 2)
                        if sel.std() > 0 else 0})
                    if fname == "none":
                        daily_pnls[(d, t, s)] = ser
    gdf = pd.DataFrame(rows)
    gdf.to_csv(os.path.join(OUT, "churn_grid.csv"), index=False)

    print("=== intraday dip-buy churn harvester (long-only, flat overnight) ===")
    print("top 15 by annualized % (1 unit/trade, no costs):")
    cols = ["dip", "tgt", "stop", "filter", "days_traded", "mean_bp_day",
            "ann_pct", "win_days_pct", "worst_day_pct", "sharpe"]
    print(gdf.sort_values("ann_pct", ascending=False)[cols].head(15).to_string(index=False))
    print("\ntop 10 by Sharpe:")
    print(gdf.sort_values("sharpe", ascending=False)[cols].head(10).to_string(index=False))

    best = gdf.sort_values("sharpe", ascending=False).iloc[0]
    bk = (best["dip"] / 100, best["tgt"] / 100,
          9.9 if pd.isna(best["stop"]) else best["stop"] / 100)
    if bk in daily_pnls:
        ser = daily_pnls[bk]
        if best["filter"] != "none":
            mask = ~daily[filters[best["filter"]]].any(axis=1)
            ser = ser[ser.index.isin(mask[mask].index)]
        print(f"\nbest-Sharpe config by year (mean bp/day):")
        print((ser.groupby(ser.index.year).mean() * 1e4).round(1).to_string())

if __name__ == "__main__":
    main()
