"""Re-strike the weekly call every Monday instead of holding the old strike.

Rule under test: when the call expires worthless the shares are kept, but the
NEXT week's call is written two listed strikes above Monday's 10:00 spot --
i.e. the strike is re-based to the market every week rather than left where it
was. The put leg is unchanged (2 strikes OTM, ~91 DTE, 1 per lot).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import backtest as bt, data

COST = dict(cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019)
pd.set_option("display.width", 210)


def diag(label, **kw):
    eq, led, meta = bt.run(**{**COST, **kw})
    w = led[led.act == "SELL_CALL"]
    asg = led[led.act == "CALL_ASSIGNED"]
    # weeks with no share position on the Friday close
    flat = int((eq.shares == 0).sum())
    rb = []
    for _, a in asg.iterrows():
        nxt = led[(led.date > a.date) & (led.act == "BUY_SHARES")]
        if len(nxt):
            rb.append(100 * (nxt.iloc[0].px - a.K) / a.K)
    s = bt.stats(eq, label); s.update(meta["pnl"])
    s.update(dict(assigned=len(asg), pct_assigned=len(asg) / max(len(w), 1),
                  prem=float((w.px * w.qty * 100).sum()),
                  intrinsic=float((asg.itm * asg.qty * 100).sum()),
                  otm=w.otm_pct.median(), flat_days=flat,
                  whipsaw=float(np.median(rb)) if rb else np.nan))
    return s, eq, led


COLS = ["final", "cagr", "maxdd", "sharpe", "shares", "calls", "puts",
        "assigned", "pct_assigned", "otm", "prem", "intrinsic", "whipsaw", "flat_days"]
F = {"final": "{:,.0f}".format, "cagr": "{:+.2%}".format, "maxdd": "{:.1%}".format,
     "sharpe": "{:.2f}".format, "shares": "{:+,.0f}".format, "calls": "{:+,.0f}".format,
     "puts": "{:+,.0f}".format, "pct_assigned": "{:.0%}".format, "otm": "{:.1f}".format,
     "prem": "{:,.0f}".format, "intrinsic": "{:,.0f}".format, "whipsaw": "{:+.1f}".format}

if __name__ == "__main__":
    rows = []
    rows.append(diag("SPEC: 2 strikes, STICKY (original)")[0])
    rows.append(diag("NEW: 2 strikes, RESET every Monday", sticky=False)[0])
    for n in (3, 4, 6):
        rows.append(diag(f"RESET at {n} strikes", n_otm=n, sticky=False)[0])
    rows.append(diag("RESET at 10% fixed OTM", strike_mode="pct", call_pct=0.10, sticky=False)[0])
    rows.append(diag("RESET at 0.20 delta", strike_mode="delta", call_delta=0.20, sticky=False)[0])
    print("=" * 190)
    print("SINGLE PATH 2022-01-03 -> 2026-07-02, realistic costs.  otm = median % OTM at write, "
          "whipsaw = median % rebuy above strike sold")
    print("=" * 190)
    print(pd.DataFrame(rows).set_index("label")[COLS].to_string(formatters=F))

    # --- 14 start weeks: does the ranking hold? ---
    days = data.trading_days(); days = days[(days >= bt.START) & (days <= bt.END)]
    starts = [d for d in days if d.dayofweek == 0][:14]
    CFG = {"2 strikes STICKY (spec)": {},
           "2 strikes RESET (new rule)": dict(sticky=False),
           "6 strikes RESET": dict(n_otm=6, sticky=False),
           "10% OTM RESET": dict(strike_mode="pct", call_pct=0.10, sticky=False),
           "6 strikes STICKY": dict(n_otm=6),
           "10% OTM STICKY": dict(strike_mode="pct", call_pct=0.10)}
    out = []
    for d0 in starts:
        for n, kw in CFG.items():
            eq, _, _ = bt.run(start=d0, **{**COST, **kw})
            s = bt.stats(eq, n)
            out.append(dict(cfg=n, start=d0, cagr=s["cagr"], final=s["final"], dd=s["maxdd"]))
        print(f"  {d0:%Y-%m-%d} done", flush=True)
    df = pd.DataFrame(out); df.to_csv(f"{bt.OUT}/reset_rule_robustness.csv", index=False)
    g = df.groupby("cfg").agg(cagr_min=("cagr", "min"), cagr_med=("cagr", "median"),
                              cagr_max=("cagr", "max"), final_med=("final", "median"),
                              dd_med=("dd", "median"))
    g["ret_per_DD"] = g.cagr_med / g.dd_med.abs()
    print("\n" + "=" * 110)
    print("14 START WEEKS -- does RESET ever beat STICKY at the same strike distance?")
    print("=" * 110)
    print(g.loc[list(CFG)].to_string(formatters={
        "cagr_min": "{:+.1%}".format, "cagr_med": "{:+.1%}".format, "cagr_max": "{:+.1%}".format,
        "final_med": "{:,.0f}".format, "dd_med": "{:.1%}".format, "ret_per_DD": "{:.2f}".format}))
