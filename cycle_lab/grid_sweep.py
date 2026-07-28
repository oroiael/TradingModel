"""
Grid sweep for the 1% cycle strategy (see one_pct_cycle_lab.py for the engine).

Round 2, per user request:
  * deep in-the-money covered calls after a stall ("clears fast at max fee"):
    strike 5/10/20% BELOW spot, 7-day and 30-day tenors -- the stalled lot is
    almost certainly assigned at the strike, so the loss is realized quickly
    while pocketing the full premium (intrinsic + time value at the bid);
  * a "repair" covered call struck nearest the lot's original entry price
    (shares called away at ~breakeven if SOXL recovers);
  * a full grid: target 1..3% x stall 3/5/10d x hedge mode.

Outputs: cycle_lab/out/focused_variants.csv, cycle_lab/out/grid_sweep.csv
"""

import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from one_pct_cycle_lab import (load_bars, daily_from_bars, load_opts, OptBook,
                               run_strategy, summarize, OUT)

def main():
    bars = load_bars()
    daily = daily_from_bars(bars)
    putbook = OptBook(load_opts())
    start = pd.Timestamp("2022-01-03")
    end = min(pd.Timestamp("2026-07-02"), daily.index[-1])

    def run(name, **kw):
        t0 = time.time()
        led, eq, cash = run_strategy(bars, daily, putbook, start, end, **kw)
        s = summarize(name, led, eq, cash)
        s["params"] = str(kw)
        print(f"  {name:34s} pnl {s['total_pnl']:>9,.0f}  dd {s['max_dd_$']:>9,.0f}  "
              f"cap {s['max_capital']:>8,.0f}  roc {s['ret_on_max_cap']:>5.1f}%  "
              f"({time.time()-t0:.1f}s)", flush=True)
        return s, led

    # ---------------- focused: deep-ITM / repair covered calls
    focused = []
    fvars = [
        # baseline anchors
        ("1pct/5d cc justOTM 30d",  dict(target=.01, stall_days=5, mode="cc")),
        ("2pct/5d cc justOTM 30d",  dict(target=.02, stall_days=5, mode="cc")),
        # deep ITM covered calls, 30d
        ("1pct/5d cc ITM5 30d",     dict(target=.01, stall_days=5, mode="cc", otm_pct=-.05)),
        ("1pct/5d cc ITM10 30d",    dict(target=.01, stall_days=5, mode="cc", otm_pct=-.10)),
        ("1pct/5d cc ITM20 30d",    dict(target=.01, stall_days=5, mode="cc", otm_pct=-.20)),
        # deep ITM, weekly tenor -- "clears fast"
        ("1pct/5d cc ITM10 7d",     dict(target=.01, stall_days=5, mode="cc", otm_pct=-.10, dte_target=7)),
        ("1pct/5d cc ITM20 7d",     dict(target=.01, stall_days=5, mode="cc", otm_pct=-.20, dte_target=7)),
        ("1pct/5d cc justOTM 7d",   dict(target=.01, stall_days=5, mode="cc", dte_target=7)),
        ("2pct/5d cc ITM10 7d",     dict(target=.02, stall_days=5, mode="cc", otm_pct=-.10, dte_target=7)),
        ("2pct/5d cc ITM20 7d",     dict(target=.02, stall_days=5, mode="cc", otm_pct=-.20, dte_target=7)),
        ("3pct/5d cc ITM10 7d",     dict(target=.03, stall_days=5, mode="cc", otm_pct=-.10, dte_target=7)),
        # repair call: strike nearest original entry
        ("1pct/5d cc @entry 30d",   dict(target=.01, stall_days=5, mode="cc", strike_ref="entry")),
        ("2pct/5d cc @entry 30d",   dict(target=.02, stall_days=5, mode="cc", strike_ref="entry")),
    ]
    print("=== focused variants ===", flush=True)
    for name, kw in fvars:
        s, led = run(name, **kw)
        focused.append(s)
        tag = (name.replace(" ", "_").replace("%", "pct").replace("/", "-")
                   .replace("@", "at"))
        led.to_csv(os.path.join(OUT, f"ledger_{tag}.csv"), index=False)
    pd.DataFrame(focused).to_csv(os.path.join(OUT, "focused_variants.csv"), index=False)

    # ---------------- full grid
    grid = []
    modes = [
        ("none",     dict(mode="none")),
        ("stop",     dict(mode="stop")),
        ("put_30d",  dict(mode="put")),
        ("cc_otm30", dict(mode="cc")),
        ("cc_itm10_7d", dict(mode="cc", otm_pct=-.10, dte_target=7)),
    ]
    print("=== grid sweep ===", flush=True)
    for tgt in [0.01, 0.015, 0.02, 0.025, 0.03]:
        for stall in [3, 5, 10]:
            for mname, mkw in modes:
                name = f"t{tgt*100:g}_s{stall}_{mname}"
                s, _ = run(name, target=tgt, stall_days=stall, **mkw)
                s.update({"target": tgt * 100, "stall": stall, "mode": mname})
                grid.append(s)
    gdf = pd.DataFrame(grid)
    gdf.to_csv(os.path.join(OUT, "grid_sweep.csv"), index=False)

    cols = ["variant", "total_pnl", "max_dd_$", "max_capital", "ret_on_max_cap",
            "cycle_wins", "stalls", "put_pnl"]
    print("\n=== grid: top 12 by total P&L ===")
    print(gdf.sort_values("total_pnl", ascending=False)[cols].head(12).to_string(index=False))
    print("\n=== grid: top 12 by return on max capital ===")
    print(gdf.sort_values("ret_on_max_cap", ascending=False)[cols].head(12).to_string(index=False))
    gdf["pnl_per_dd"] = (gdf["total_pnl"] / gdf["max_dd_$"].abs()).round(2)
    print("\n=== grid: top 12 by P&L / max-drawdown ===")
    print(gdf.sort_values("pnl_per_dd", ascending=False)[cols + ["pnl_per_dd"]]
          .head(12).to_string(index=False))

if __name__ == "__main__":
    main()
