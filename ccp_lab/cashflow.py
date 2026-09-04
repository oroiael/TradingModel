#!/usr/bin/env python3
"""Brokerage-statement view: every dollar in and out, reconciled to final equity.

No opportunity-cost attribution, no notional marks. Just cash.

    python ccp_lab/cashflow.py            # all years
    python ccp_lab/cashflow.py 2025       # one year
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.compat import safe_stdout, ensure_cache, write_text
from ccp_lab.engine import Data, run_year, START_CASH
from ccp_lab.report import OUT


def statement(y, d, **kw):
    r = run_year(y, d, **kw)
    ev, lg = r["events"], r["ledger"]
    w = lg.dropna(subset=["call_strike"])

    def s(kind, col):
        g = ev[ev.kind == kind]
        return float((g.qty * g[col]).sum()) if len(g) else 0.0

    rows = [
        ("Opening cash",                     START_CASH),
        ("Shares bought",                   -s("BUY_SHARES", "spot")),
        ("Shares sold at market",            s("SELL_SHARES", "spot")),
        ("Shares called away, at the strike", s("CALL_ASSIGNED", "strike")),
        ("Shares put-exercised, at the strike", s("PUT_EXERCISED", "strike")),
        ("Call premium received",            float(w.call_premium.sum())),
        ("Calls bought back to roll",       -(s("CALL_ROLLED_CLOSE", "px") * 100),),
        ("Premium on rolled-out calls",      s("CALL_ROLLED_OPEN", "px") * 100),
        ("Put premium paid",                -(s("BUY_PUT", "px") * 100)),
        ("Puts cash-settled",                s("PUT_CASH_SETTLED", "strike") * 0
                                             + float(((ev[ev.kind == "PUT_CASH_SETTLED"].qty * 100) *
                                                      (ev[ev.kind == "PUT_CASH_SETTLED"].strike -
                                                       ev[ev.kind == "PUT_CASH_SETTLED"].spot)).sum())
                                             if (ev.kind == "PUT_CASH_SETTLED").any() else 0.0),
        ("Year-end: shares sold",            s("EOY_SELL_SHARES", "spot")),
        ("Year-end: open call bought back", -(s("EOY_CLOSE_CALL", "px") * 100)),
        ("Year-end: open put sold",          s("EOY_SELL_PUT", "px") * 100),
        ("Commissions and fees",            -r["pnl"]["fees"]),
    ]
    total = sum(v for _, v in rows)
    return r, rows, total


def render(y, rows, total, final):
    L = [f"### {y}\n", "| line | cash |", "|---|---:|"]
    for n, v in rows:
        if abs(v) < 0.005:
            continue
        L.append(f"| {n} | {v:+,.0f} |")
    L.append(f"| **Closing equity** | **{total:+,.0f}** |")
    L.append(f"\nReconciles to the engine's final equity (${final:,.0f}) to "
             f"{abs(total-final):.2f} of a dollar.\n")
    return L


if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()
    years = [int(a) for a in sys.argv[1:]] or [2022, 2023, 2024, 2025, 2026]
    L = ["# Cash-flow statement — every dollar in and out\n",
         "This is the same backtest as `summary_<year>.md`, with no attribution "
         "and no notional marks: only cash that actually moved. Assignment is a "
         "**sale at the strike**, not a payment — money comes in, never out.\n"]
    for y in years:
        r, rows, total = statement(y, d)
        L += render(y, rows, total, r["final"])
        print(f"{y}: statement total {total:,.0f}  engine {r['final']:,.0f}  "
              f"diff {total-r['final']:+.2f}")
    write_text(f"{OUT}/CASHFLOW.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/CASHFLOW.md")
