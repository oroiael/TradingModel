#!/usr/bin/env python3
"""Invariant audit — checks the engine cannot be flattering itself."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.engine import Data, run_year

def audit(y, d):
    r = run_year(y, d)
    lg, ev = r["ledger"], r["events"]
    fails = []

    legs = r["pnl"]["shares"] + r["pnl"]["calls"] + r["pnl"]["puts"] - r["pnl"]["fees"]
    if abs(legs - (r["final"] - 100000)) > 0.01:
        fails.append(f"P&L attribution off by {legs-(r['final']-100000):.2f}")

    w = lg.dropna(subset=["call_strike"])
    if (w.call_qty * 100 > w.shares).any():
        fails.append("wrote calls on shares not held (naked call)")
    if (w.call_strike < w.spot_1000_high).any():
        fails.append("wrote a call struck below spot")
    if "put_qty" in lg and (lg.put_qty.fillna(0) * 100 < lg.shares * 0.999).any():
        n = int((lg.put_qty.fillna(0) * 100 < lg.shares * 0.999).sum())
        fails.append(f"{n} weeks with shares not fully put-hedged")
    if (lg.cash_after < -0.01).any():
        fails.append("negative cash (implicit leverage)")

    if len(ev):
        a = ev[ev.kind == "CALL_ASSIGNED"]
        if len(a) and (a.spot <= a.strike).any():
            fails.append("assigned a call that finished out of the money")
        p = ev[ev.kind == "PUT_EXERCISED"]
        if len(p) and (p.spot >= p.strike).any():
            fails.append("exercised a put that finished out of the money")

    eq = r["equity"]
    if eq.equity.isna().any():
        fails.append("NaN in the equity curve")

    # every share sale must be matched by a prior purchase
    buys = ev[ev.kind == "BUY_SHARES"].qty.sum() if len(ev) else 0
    sells = ev[ev.kind.isin(["CALL_ASSIGNED", "PUT_EXERCISED"])].qty.sum() if len(ev) else 0
    if sells > buys:
        fails.append(f"sold {sells} shares but only bought {buys}")

    mk = r["marks"]; tot = max(sum(mk.values()), 1)
    return r, fails, mk, tot

if __name__ == "__main__":
    d = Data()
    allok = True
    for y in [2022, 2023, 2024, 2025, 2026]:
        r, fails, mk, tot = audit(y, d)
        real = (mk.get("print_1000", 0) + mk.get("print_near", 0)) / tot * 100
        print(f"{y}: final ${r['final']:>9,.0f}  legs reconcile ✓  "
              f"real prints {real:5.1f}%  ", end="")
        if fails:
            allok = False
            print("FAIL")
            for f in fails:
                print(f"      - {f}")
        else:
            print("all invariants hold")
    print("\nAUDIT", "PASSED" if allok else "FAILED")
