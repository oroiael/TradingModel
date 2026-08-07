"""How much of the result is the rules, and how much is the calendar?

Same rules, same data -- only the week you happen to start on changes. If the
strategy has an edge, the spread across start weeks should be modest.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import data, backtest as bt

R = dict(cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019)


def bh_cagr(d0, d1, start=100_000.0):
    c = data.daily_close(); c = c[(c.index >= d0) & (c.index <= d1)]
    s10 = data.spot_at(600)
    n = int(start // float(s10.loc[c.index[0], "px"]))
    cash = start - n * float(s10.loc[c.index[0], "px"])
    e = n * c + cash
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    return (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1, e.iloc[-1], (e / e.cummax() - 1).min()


if __name__ == "__main__":
    days = data.trading_days()
    days = days[(days >= bt.START) & (days <= bt.END)]
    mondays = [d for d in days if d.dayofweek == 0][:14]
    rows = []
    for i, d0 in enumerate(mondays):
        eq, led, meta = bt.run(start=d0, **R)
        s = bt.stats(eq, f"start {d0:%Y-%m-%d} (+{i}w)")
        b_cagr, b_fin, b_dd = bh_cagr(d0, bt.END)
        rows.append(dict(label=s["label"], final=s["final"], cagr=s["cagr"],
                         maxdd=s["maxdd"], bh_cagr=b_cagr, bh_final=b_fin,
                         excess=s["cagr"] - b_cagr,
                         assigned=int((led.act == "CALL_ASSIGNED").sum()),
                         **meta["pnl"]))
    df = pd.DataFrame(rows).set_index("label")
    print("=" * 120)
    print("START-WEEK ROBUSTNESS -- identical rules, only the first Monday differs")
    print("(with commissions + measured half-spread; buy & hold measured over the same window)")
    print("=" * 120)
    print(df[["final", "cagr", "maxdd", "bh_final", "bh_cagr", "excess", "assigned",
              "shares", "calls", "puts"]].to_string(formatters={
        "final": "{:,.0f}".format, "cagr": "{:+.2%}".format, "maxdd": "{:.1%}".format,
        "bh_final": "{:,.0f}".format, "bh_cagr": "{:+.2%}".format,
        "excess": "{:+.2%}".format, "shares": "{:+,.0f}".format,
        "calls": "{:+,.0f}".format, "puts": "{:+,.0f}".format}))
    print("\nSPREAD ACROSS 14 START WEEKS")
    print(f"  final equity : min ${df.final.min():,.0f}   median ${df.final.median():,.0f}"
          f"   max ${df.final.max():,.0f}   (max/min = {df.final.max()/df.final.min():.1f}x)")
    print(f"  CAGR         : min {df.cagr.min():+.2%}   median {df.cagr.median():+.2%}"
          f"   max {df.cagr.max():+.2%}")
    print(f"  vs buy&hold  : median excess {df.excess.median():+.2%}   "
          f"beat buy&hold in {(df.excess > 0).sum()} of {len(df)} start weeks")
    df.to_csv(f"{bt.OUT}/robustness_startweek.csv")
