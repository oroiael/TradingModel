"""
Regime gate for the churn harvester: condition daily P&L of the best
dip-buy configs on trailing 5-day average daily range (ATR5), the signal
that is known before the open.

Finding: the harvester's edge lives almost entirely in ATR5 quartiles 2-4;
gating at ATR5 >= 6% makes the dip1%/tgt1%/stop4%/orq5 config positive in
every year 2020-2026 with Sharpe ~2.1 on traded days.
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cycle_lab"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from one_pct_cycle_lab import load_bars
from churn_harvest import sim_day

def main():
    bars = load_bars()
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    daily["gap_pct"] = (daily["o"] / daily["c"].shift() - 1) * 100
    daily["atr5"] = daily["range_pct"].rolling(5).mean().shift()
    or30 = {d: (gb["High"].to_numpy()[:6].max() - gb["Low"].to_numpy()[:6].min())
               / gb["Open"].iloc[0] * 100 for d, gb in g}
    daily["or30"] = pd.Series(or30)
    orq5_thr = daily["or30"].quantile(.8)

    configs = [("dip1/t1/s4 orq5", .01, .01, .04, "orq5"),
               ("dip2/t1/s4 gap2", .02, .01, .04, "gap2")]
    out_rows = []
    for name, d_, t_, s_, filt in configs:
        pnl = {}
        for dd, gb in g:
            o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
            if len(c) < 14:
                continue
            p, _ = sim_day(o, h, l, c, 12, d_, t_, s_)
            pnl[dd] = p
        ser = pd.Series(pnl)
        if filt == "orq5":
            ser = ser[ser.index.isin(daily.index[daily["or30"] < orq5_thr])]
        else:
            ser = ser[ser.index.isin(daily.index[daily["gap_pct"].abs() <= 2])]
        j = daily[["atr5"]].join(ser.rename("pnl"), how="inner").dropna()
        j["atr_q"] = pd.qcut(j["atr5"], 4, labels=False) + 1
        print(f"\n=== {name}: pnl by trailing-5d-ATR quartile (bp/day) ===")
        print((j.groupby("atr_q")["pnl"].agg(["mean", "count"])
               .assign(mean=lambda x: (x["mean"] * 1e4).round(1))).to_string())
        for thr in [6, 8]:
            s2 = j.loc[j["atr5"] >= thr, "pnl"]
            if len(s2) < 30:
                continue
            shp = s2.mean() / s2.std() * np.sqrt(252)
            print(f"gated ATR5>={thr}%: {len(s2)} days, {s2.mean()*1e4:.1f} bp/day, "
                  f"sharpe {shp:.2f}, worst {s2.min()*100:.1f}%")
            byyr = {y: round(v * 1e4, 1) for y, v in
                    s2.groupby(s2.index.year).mean().items()}
            print(f"  by year (bp/day): {byyr}")
            out_rows.append({"config": name, "gate": f"atr5>={thr}",
                             "days": len(s2), "bp_day": round(s2.mean() * 1e4, 1),
                             "sharpe": round(shp, 2),
                             "worst_day_pct": round(s2.min() * 100, 1), **byyr})
    pd.DataFrame(out_rows).to_csv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "out",
                     "regime_gate.csv"), index=False)

if __name__ == "__main__":
    main()
