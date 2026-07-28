"""
V7 test: sweep the max-trades-per-day cap 1..10 on the locked core config
(dip 1% / target 1% / stop 4%, orq5 filter, ATR5>=6 gate, start 10:30).
The cap was an untested assumption (STRATEGY_SPEC.md V7) -- this closes it.

Output: band_lab/out/cap_sweep.csv
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars
from churn_harvest import sim_day

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
    tradable = daily.index[(daily["or30"] < orq5_thr) & (daily["atr5"] >= 6)]

    rows = []
    for cap in range(1, 11):
        pnl, ntr, capped = {}, {}, 0
        for dd, gb in g:
            if dd not in tradable:
                continue
            o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
            if len(c) < 14:
                continue
            p, n = sim_day(o, h, l, c, 12, .01, .01, .04, max_trades=cap)
            pnl[dd] = p; ntr[dd] = n
            if n >= cap:
                capped += 1
        ser = pd.Series(pnl); tr = pd.Series(ntr)
        sh = ser.mean() / ser.std() * np.sqrt(252) if ser.std() > 0 else 0
        rows.append({"cap": cap, "days": len(ser),
                     "days_cap_binds": capped,
                     "trades_per_day": round(tr.mean(), 2),
                     "bp_day": round(ser.mean() * 1e4, 1),
                     "sharpe": round(sh, 2),
                     "worst_day_pct": round(ser.min() * 100, 1),
                     "cum_uncomp_pct": round(ser.sum() * 100, 0)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "out", "cap_sweep.csv"), index=False)
    print("max-trades cap sweep (locked core config, gated days only):")
    print(df.to_string(index=False))

if __name__ == "__main__":
    main()
