"""Do the factor 'improvements' survive the start-week test, or are they noise?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import backtest as bt, data

COST = dict(cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019)
CFG = {
    "baseline":  {},
    "F1":        dict(early_assign_pct=0.003),
    "F2":        dict(strike_mode="delta", call_delta=0.20),
    "F3":        dict(put_ratio=0.5),
    "F1+F2":     dict(early_assign_pct=0.003, strike_mode="delta", call_delta=0.20),
    "F1+F3":     dict(early_assign_pct=0.003, put_ratio=0.5),
    "F2+F3":     dict(strike_mode="delta", call_delta=0.20, put_ratio=0.5),
    "F1+F2+F3":  dict(early_assign_pct=0.003, strike_mode="delta", call_delta=0.20, put_ratio=0.5),
}

def bh(d0, d1, start=100_000.0):
    c = data.daily_close(); c = c[(c.index >= d0) & (c.index <= d1)]
    s = data.spot_at(600); n = int(start // float(s.loc[c.index[0], "px"]))
    e = n * c + (start - n * float(s.loc[c.index[0], "px"]))
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    return (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1, (e / e.cummax() - 1).min()

if __name__ == "__main__":
    days = data.trading_days(); days = days[(days >= bt.START) & (days <= bt.END)]
    starts = [d for d in days if d.dayofweek == 0][:14]
    out = []
    for d0 in starts:
        b_cagr, b_dd = bh(d0, bt.END)
        for name, kw in CFG.items():
            eq, led, meta = bt.run(start=d0, **{**COST, **kw})
            s = bt.stats(eq, name)
            out.append(dict(start=d0, cfg=name, final=s["final"], cagr=s["cagr"],
                            maxdd=s["maxdd"], bh_cagr=b_cagr, bh_dd=b_dd,
                            excess=s["cagr"] - b_cagr))
        print(f"  done {d0:%Y-%m-%d}", flush=True)
    df = pd.DataFrame(out)
    df.to_csv(f"{bt.OUT}/factor_robustness.csv", index=False)
    g = df.groupby("cfg").agg(
        cagr_min=("cagr", "min"), cagr_med=("cagr", "median"), cagr_max=("cagr", "max"),
        final_min=("final", "min"), final_med=("final", "median"), final_max=("final", "max"),
        dd_med=("maxdd", "median"), excess_med=("excess", "median"),
        beat_bh=("excess", lambda s: f"{(s > 0).sum()}/{len(s)}"))
    g["spread_x"] = g.final_max / g.final_min
    order = ["baseline", "F1", "F2", "F3", "F1+F2", "F1+F3", "F2+F3", "F1+F2+F3"]
    print("\n" + "=" * 130)
    print("START-WEEK ROBUSTNESS OF EVERY COMBINATION  (14 start weeks, realistic costs)")
    print("=" * 130)
    print(g.loc[order].to_string(formatters={
        "cagr_min": "{:+.1%}".format, "cagr_med": "{:+.1%}".format, "cagr_max": "{:+.1%}".format,
        "final_min": "{:,.0f}".format, "final_med": "{:,.0f}".format, "final_max": "{:,.0f}".format,
        "dd_med": "{:.1%}".format, "excess_med": "{:+.1%}".format, "spread_x": "{:.1f}x".format}))
    bhm = df.groupby("start").bh_cagr.first()
    print(f"\nbuy & hold over the same windows: median CAGR {bhm.median():+.1%} "
          f"(min {bhm.min():+.1%}, max {bhm.max():+.1%}), median max DD {df.bh_dd.median():.1%}")
