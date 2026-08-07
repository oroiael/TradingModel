"""Cost sensitivity and rule variants for the covered-call + long-put strategy."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import backtest as bt, analyze

def row(label, **kw):
    eq, led, meta = bt.run(**kw)
    s = bt.stats(eq, label)
    s.update(meta["pnl"])
    s["assigned"] = int((led.act == "CALL_ASSIGNED").sum())
    s["prem"] = float((led[led.act=="SELL_CALL"].px * led[led.act=="SELL_CALL"].qty * 100).sum())
    return s

def show(rows, title):
    df = pd.DataFrame(rows).set_index("label")
    df = df[["final","cagr","maxdd","sharpe","shares","calls","puts","assigned","prem"]]
    print("\n" + "="*118); print(title); print("="*118)
    print(df.to_string(formatters={
        "final":"{:,.0f}".format, "cagr":"{:+.2%}".format, "maxdd":"{:.1%}".format,
        "sharpe":"{:.2f}".format, "shares":"{:+,.0f}".format, "calls":"{:+,.0f}".format,
        "puts":"{:+,.0f}".format, "prem":"{:,.0f}".format}))

if __name__ == "__main__":
    # ---- transaction costs ----
    cost = [
        row("A  frictionless (base)"),
        row("B  + $0.65/contract comm", cost_per_contract=0.65, share_cost=0.005),
        row("C  + measured half-spread (5.5% call / 1.9% put)",
            cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019),
        row("D  + double half-spread (11% / 3.8%)",
            cost_per_contract=0.65, share_cost=0.005, slip_call=0.110, slip_put=0.038),
        row("E  C + 4% interest on idle cash",
            cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019,
            cash_rate=0.04),
    ]
    show(cost, "TRANSACTION-COST SENSITIVITY  (all else = the specified rules)")

    R = dict(cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019)
    # ---- rule variants, all at realistic cost level C ----
    var = [row("2 strikes OTM, sticky  (AS SPECIFIED)", **R)]
    for n in (1, 3, 4, 6):
        var.append(row(f"{n} strikes OTM, sticky", n_otm=n, **R))
    var.append(row("2 strikes OTM, RESET every week (no sticky)", sticky=False, **R))
    for n in (3, 4, 6):
        var.append(row(f"{n} strikes OTM, RESET every week", n_otm=n, sticky=False, **R))
    show(var, "RULE VARIANTS  (with commissions + measured half-spread)")

    ten = [row("put ~91d (AS SPECIFIED)", **R)]
    for d in (30, 60, 180, 270):
        ten.append(row(f"put ~{d}d", put_dte=d, **R))
    ten.append(row("put qty frozen at purchase", freeze_put_qty=True, **R))
    ten.append(row("no put (covered call only)", use_put=False, **R))
    ten.append(row("no call (shares + put only)", use_call=False, **R))
    show(ten, "PUT-LEG VARIANTS  (with commissions + measured half-spread)")
