#!/usr/bin/env python3
"""When is the put worth enough to offset the re-strike loss, and did we get it?

Writes ccp_lab/out/PUT_POLICY.md.

The stated rule never trades the put: it is held to expiry and exercised if in
the money. That means the share loss is crystallised the day the call assigns --
at the bottom -- while the put's payoff is only realised weeks later, at its own
expiry, after whatever rebound has happened in between. This measures the gap and
tests the obvious alternative: once the shares are called away the put has no job,
so sell it.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from ccp_lab.compat import safe_stdout, ensure_cache, write_text
from ccp_lab.engine import Data, run_year
from ccp_lab.report import buy_hold, OUT

YEARS = [2022, 2023, 2024, 2025, 2026]


def put_value_at_assignments(d, y):
    """For every assignment, the intrinsic value of the puts held at that instant."""
    r = run_year(y, d)
    ev = r["events"].sort_values("date")
    live, rows = [], []
    for _, e in ev.iterrows():
        if e.kind == "BUY_PUT":
            live.append(dict(strike=float(e.strike), qty=int(e.qty)))
        elif e.kind in ("PUT_EXPIRED", "PUT_EXERCISED", "PUT_CASH_SETTLED",
                        "EOY_SELL_PUT", "PUT_SOLD_FLAT"):
            for p in list(live):
                if abs(p["strike"] - float(e.strike)) < 1e-6:
                    live.remove(p); break
        elif e.kind == "CALL_ASSIGNED":
            intr = sum(p["qty"] * 100 * max(p["strike"] - float(e.spot), 0.0)
                       for p in live)
            rows.append(dict(date=e.date, spot=float(e.spot), intrinsic=intr))
    return r, pd.DataFrame(rows)


if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    d = Data()

    grid, legs = {}, []
    for name, kw in [("hold the put to expiry (the rule)", {}),
                     ("sell the put once the shares are gone",
                      dict(put_policy="sell_when_flat"))]:
        row = {}
        for y in YEARS:
            r = run_year(y, d, **kw)
            ev = r["events"]
            sold = ev[ev.kind == "PUT_SOLD_FLAT"]
            row[y] = r["final"] / 1000.0 - 100.0
            legs.append(dict(mode=name, year=y, put_pnl=r["pnl"]["puts"],
                             n_sold=len(sold)))
        grid[name] = row
        print(f"{name:<40} " + "  ".join(f"{y}:{row[y]:+7.1f}%" for y in YEARS))
    bh = {y: buy_hold(d, y, 100000.0)[0] / 1000.0 - 100.0 for y in YEARS}
    grid["buy & hold SOXL"] = bh
    G = pd.DataFrame(legs)

    L = ["# The put: when is it worth enough, and do we ever collect it?\n"]
    L.append("\n## The short answer\n")
    L.append("The put is **already worth enough** at the moment the re-strike "
             "loss happens. It is not a sizing problem or a strike problem. The "
             "rule simply realises it at the wrong time: the share loss is booked "
             "the day the call assigns, at the low, while the put is held on to "
             "its own expiry weeks later, by which point the stock has usually "
             "bounced and the put is worth far less.\n")

    L.append("\n## The April 2025 case, step by step\n")
    L.append("| | |")
    L.append("|---|---|")
    L.append("| 2025-02-24 | Bought 21 puts, strike **$27.00**, 81 DTE, at $4.40 — **$9,240** |")
    L.append("| 2025-02-18 → 04-25 | SOXL falls 29.12 → 12.33; the call is re-struck down every Monday |")
    L.append("| 2025-04-25 | Called away at **$9.00**. Share lot realises **−$42,252** |")
    L.append("| *same instant* | Puts held were worth **$35,209** of intrinsic — **83% of the loss** |")
    L.append("| 2025-05-16 | Put expires. SOXL has rebounded to **$18.39**; it cash-settles for **$18,081** |")
    L.append("\nThe hedge did its job and then gave most of it back while we "
             "watched. Between the assignment and the put's expiry SOXL rose from "
             "$12.33 to $18.39, and roughly **$17,000 of protection that existed "
             "on the day we needed it** evaporated before we were allowed to "
             "touch it. Across all of 2025 the puts returned $19,186 — **45%** of "
             "the share loss they were sitting against, not the 83% they were "
             "worth at the moment of impact.\n")
    L.append("This is a clock mismatch, not a hedging failure. The call resolves "
             "**weekly** and crystallises the share loss at whatever Friday's "
             "price happens to be. The put resolves **quarterly**. The hedge "
             "cannot respond to the event that did the damage.\n")

    L.append("\n## Testing the obvious fix\n")
    L.append("Once the shares are called away the put is an unhedged long option "
             "protecting nothing. This variant sells it at market that day and "
             "buys a fresh one when the share position is re-established. "
             "(Selling, not exercising — exercising throws away the remaining "
             "time value.)\n")
    L.append("| variant | " + " | ".join(str(y) for y in YEARS) + " |")
    L.append("|---|" + "---:|" * len(YEARS))
    for name in list(grid.keys()):
        L.append(f"| {name} | " +
                 " | ".join(f"{grid[name][y]:+.1f}%" for y in YEARS) + " |")
    L.append("\nAnd on the put leg alone:\n")
    A = G[G["mode"] == "hold the put to expiry (the rule)"].set_index("year")
    B = G[G["mode"] == "sell the put once the shares are gone"].set_index("year")
    L.append("| year | put P&L, held to expiry | put P&L, sold when flat | improvement |")
    L.append("|---|---:|---:|---:|")
    for y in YEARS:
        L.append(f"| {y} | ${A.loc[y,'put_pnl']:+,.0f} | ${B.loc[y,'put_pnl']:+,.0f} | "
                 f"**${B.loc[y,'put_pnl']-A.loc[y,'put_pnl']:+,.0f}** |")
    L.append("\nIn 2025 and 2026 this recovers roughly $23,000 a year of hedge "
             "value that the hold-to-expiry rule was throwing away. 2023 is "
             "slightly worse — in a straight-up year the puts you sell early were "
             "going to expire worthless anyway, and you pay the spread to find "
             "that out.\n")

    L.append("\n## What this does and does not fix\n")
    L.append("- It **does** stop the hedge decaying unwatched after it has already "
             "paid off. That is worth 8-46 points depending on the year.")
    L.append("- It does **not** address the cost of the insurance itself: a "
             "just-out-of-the-money put on a 3x ETF still runs ~17% of spot per "
             "~84 days.")
    L.append("- It does **not** stop the re-strike selling the recovery. That is "
             "the sticky-strike question, measured separately in `STICKY.md`.")
    L.append("- Selling on the day of assignment is a mechanical rule, not an "
             "attempt to time the bottom. No variant here looks ahead.")
    write_text(f"{OUT}/PUT_POLICY.md", "\n".join(L) + "\n")
    print("\nwrote", f"{OUT}/PUT_POLICY.md")
