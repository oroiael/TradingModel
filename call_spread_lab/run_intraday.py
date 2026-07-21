#!/usr/bin/env python3
"""
run_intraday.py  --  does harvesting INTRADAY (vs at the close) improve the
strangle? SOXL's biggest spikes happen intraday and can fade by the bell; this
models catching them.

Model (honest, stated): on each day with 5-min data we take the day's HIGH (for
calls) / LOW (for puts) and price the leg with Black-Scholes using the contract's
own prior-EOD implied vol; if that modeled peak clears the take threshold we
harvest there, exiting at peak*(1-slip). Entries/rolls still use real EOD quotes.
IV is held at the prior close intraday (conservative: a real IV pop on a crash
would make the put worth MORE than modeled). Compared apples-to-apples with the
EOD-only harvest over the 5-min-covered window, with a slip sensitivity sweep.

Runs on whatever 5-min coverage exists (currently 2023-07..2026-07); extends
automatically when the full 5-year 5-min file is dropped in.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

from data_loader import load_options, load_5min
from verticals import build_index
from strangle_harvest import (HConfig, simulate, stats, compact_index,
                              build_hilo, build_iv_key)

OUT = Path(__file__).resolve().parent / "outputs"
BEST = dict(dte_target=120, dte_tol=20, dist=0.075, take=0.50, leg_frac=0.15)
pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 82 + f"\n{t}\n" + "=" * 82)


def slice_idx(idx, start, end):
    c, s, q, tds = idx
    return (c, s, q, [t for t in tds if start <= t <= end])


def by_year(res):
    eq = pd.Series(res["equity"], index=pd.to_datetime(res["dates"]))
    yr = eq.groupby(eq.index.year).agg(["first", "last"])
    return (yr["last"] / yr["first"] - 1).round(3)


def harvest_split(res):
    log = res["log"]
    if len(log) == 0:
        return 0, 0
    return (int((log["action"] == "harvest_intraday").sum()),
            int((log["action"] == "harvest").sum()))


def main():
    hr("LOAD + build 5-min high/low and IV lookup")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt)
    compact = compact_index(idx)
    fm = load_5min()
    hilo = build_hilo(fm)
    ivk = build_iv_key(opt)
    print(f"5-min days: {len(hilo)}  IV keys: {len(ivk):,}")

    # window = intersection of option trade-dates and 5-min coverage
    tds = idx[3]
    win_start = max(min(hilo.keys()), tds[0])
    win_end = min(max(hilo.keys()), tds[-1])
    sidx = slice_idx(idx, win_start, win_end)
    print(f"comparison window: {win_start} -> {win_end}  ({len(sidx[3])} trading days)")
    cfgd = {**BEST}
    print(f"config: {cfgd}")

    hr("EOD-only vs INTRADAY harvest (slip sensitivity)")
    print(f"{'mode':>22} {'end_equity':>13} {'CAGR':>7} {'maxDD':>7} "
          f"{'harvests(intra/eod)':>20}")
    r_eod = simulate(sidx, HConfig(**cfgd), compact)
    s = stats(r_eod, HConfig(**cfgd))
    print(f"{'EOD only':>22} {s['end_equity']:>13,.0f} {s['cagr']:>+7.0%} "
          f"{s['max_dd']:>+7.0%} {str(harvest_split(r_eod)):>20}")
    results = {"EOD only": r_eod}
    for slip in (0.0, 0.03, 0.05, 0.10):
        r = simulate(sidx, HConfig(**cfgd), compact, intraday=(hilo, ivk, slip))
        s = stats(r, HConfig(**cfgd))
        lbl = f"intraday slip {slip:.0%}"
        results[lbl] = r
        print(f"{lbl:>22} {s['end_equity']:>13,.0f} {s['cagr']:>+7.0%} "
              f"{s['max_dd']:>+7.0%} {str(harvest_split(r)):>20}")

    hr("BY-YEAR (EOD only vs intraday slip 5%)")
    comp = pd.DataFrame({"EOD_only": by_year(r_eod),
                         "intraday_5pct": by_year(results["intraday slip 5%"])})
    print(comp.to_string())

    hr("READ")
    print("Intraday harvesting captures spikes the close gives back; the slip sweep\n"
          "shows how much of that survives realistic exit cost. Compare the CAGR and\n"
          "the intraday/eod harvest split above. (Window limited by 5-min coverage;\n"
          "re-run after dropping in the full 5-year 5-min file for 2022-2026.)")


if __name__ == "__main__":
    main()
