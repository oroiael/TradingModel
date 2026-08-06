"""Two benchmarks that decide whether any call-writing variant is worth running.

1. STRIKE-RULE ISOLATION -- is a delta target actually better than just writing
   further out of the money, or is "distance" the only thing doing work?
2. STATIC ALLOCATION LADDER -- could you get the same de-risking by simply
   holding less SOXL and more cash? This is the benchmark a covered call has to
   beat, because giving up upside for a smaller drawdown is what it really does.

Both are measured over the same 14 start weeks used everywhere else, so the
numbers are comparable to factor_robust.py.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import backtest as bt, data

COST = dict(cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019)
RULES = {"2 strikes (as specified)": {},
         "6 listed strikes": dict(n_otm=6),
         "10% fixed OTM": dict(strike_mode="pct", call_pct=0.10),
         "0.20 delta": dict(strike_mode="delta", call_delta=0.20)}


def starts(n=14):
    d = data.trading_days(); d = d[(d >= bt.START) & (d <= bt.END)]
    return [x for x in d if x.dayofweek == 0][:n]


def static_ladder(weights=(0.25, 0.35, 0.45, 0.55, 0.65, 0.80, 1.0)):
    """w x SOXL + (1-w) cash, rebalanced weekly, cash at 0% to match the backtest."""
    c = data.daily_close(); rows = []
    for w in weights:
        for d0 in starts():
            cc = c[(c.index >= d0) & (c.index <= bt.END)]
            iso = cc.index.isocalendar()
            key = pd.Series(list(zip(iso.year, iso.week)), index=cc.index)
            sh = 100_000.0 * w / cc.iloc[0]; cash = 100_000.0 - sh * cc.iloc[0]
            last, eq = key.iloc[0], [100_000.0]
            for i in range(1, len(cc)):
                val = sh * cc.iloc[i] + cash
                if key.iloc[i] != last:
                    sh = val * w / cc.iloc[i]; cash = val - sh * cc.iloc[i]; last = key.iloc[i]
                eq.append(val)
            e = pd.Series(eq, index=cc.index)
            yrs = (e.index[-1] - e.index[0]).days / 365.25
            rows.append(dict(w=w, start=d0, cagr=(e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1,
                             final=e.iloc[-1], dd=(e / e.cummax() - 1).min()))
    return pd.DataFrame(rows)


def strike_isolation():
    rows = []
    for d0 in starts():
        for name, kw in RULES.items():
            eq, _, _ = bt.run(start=d0, **{**COST, **kw})
            s = bt.stats(eq, name)
            rows.append(dict(cfg=name, start=d0, cagr=s["cagr"], final=s["final"], dd=s["maxdd"]))
    return pd.DataFrame(rows)


def summarise(df, by):
    g = df.groupby(by).agg(cagr_min=("cagr", "min"), cagr_med=("cagr", "median"),
                           cagr_max=("cagr", "max"), final_med=("final", "median"),
                           dd_med=("dd", "median"))
    g["ret_per_DD"] = g.cagr_med / g.dd_med.abs()
    return g


F = {"cagr_min": "{:+.1%}".format, "cagr_med": "{:+.1%}".format, "cagr_max": "{:+.1%}".format,
     "final_med": "{:,.0f}".format, "dd_med": "{:.1%}".format, "ret_per_DD": "{:.2f}".format}

if __name__ == "__main__":
    iso = strike_isolation(); iso.to_csv(f"{bt.OUT}/iso_strike_rule.csv", index=False)
    print("=" * 100)
    print("1. STRIKE-RULE ISOLATION -- medians over 14 start weeks, realistic costs")
    print("=" * 100)
    print(summarise(iso, "cfg").loc[list(RULES)].to_string(formatters=F))
    print("\n-> a delta target is NOT the winner. Distance is the only dial that matters,")
    print("   and every rule here is just a different amount of upside surrendered.")

    st = static_ladder(); st.to_csv(f"{bt.OUT}/static_ladder.csv", index=False)
    print("\n" + "=" * 100)
    print("2. STATIC w x SOXL + CASH, rebalanced weekly -- same 14 start weeks")
    print("=" * 100)
    print(summarise(st, "w").to_string(formatters=F))
    print("\n-> compare the best call-writing variant against the static row with a")
    print("   similar drawdown. If the static row wins on BOTH axes, the option")
    print("   overlay is not buying anything you could not get by holding less.")
