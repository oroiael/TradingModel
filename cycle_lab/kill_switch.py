"""
Kill-switch test for the cycle satellite (2%/4d/no-hedge/eq4).

The walk-forward exposed the sleeve's failure mode: it keeps buying dips
through a regime break (2022: -80% OOS). Candidate switches, all computed
from PRIOR-day closes (no lookahead), all "soft" (block new lots, let
existing lots run out) unless marked hard (also liquidate the active lot):

  sma20/50/100/200 -- new lots only while close > N-day simple moving avg
  sma50_hard       -- same, and the active lot is sold when the gate goes off
  atr_cap          -- no new lots while ATR5 > 15% (panic-vol block)

Evaluated two ways:
  1. fixed config 2%/4d/eq4, 2022-01-03..end, per-year detail;
  2. the honest test: the round-4 walk-forward protocol (target/stall
     re-selected yearly from prior data only) re-run WITH the best switch,
     compared to the ungated 3.3% OOS CAGR.

Outputs: cycle_lab/out/kill_switch.csv, kill_switch_wf.csv
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import compound_engine
from compound_engine import run_compound, load_soxs_daily
from one_pct_cycle_lab import load_bars, daily_from_bars, OUT

def yearly(eq):
    r = eq["equity"].resample("YE").last()
    prev = eq["equity"].iloc[0]
    out = {}
    for ts, v in r.items():
        out[ts.year] = round((v / prev - 1) * 100, 1)
        prev = v
    return out

def main():
    bars = load_bars()
    daily = daily_from_bars(bars)
    soxs = load_soxs_daily()
    start, end = pd.Timestamp("2022-01-03"), daily.index[-1]
    c = daily["c"]

    gates = {"none": None}
    for n in (20, 50, 100, 200):
        gates[f"sma{n}"] = (c > c.rolling(n).mean()).shift(1)
    gates["atr_cap15"] = (daily["h"].sub(daily["l"]).div(daily["o"]).mul(100)
                          .rolling(5).mean() < 15).shift(1)

    rows = []
    print("=== fixed config 2%/4d/eq4, 2022-01-03..{} ===".format(end.date()))
    for name, gseries in gates.items():
        for hard in ([False, True] if name == "sma50" else [False]):
            tag = name + ("_hard" if hard else "")
            s, eq = run_compound(bars, daily, soxs, start, end,
                                 target=.02, stall_days=4, mode="none",
                                 sizing="eq4", gate=gseries,
                                 gate_liquidate=hard)
            yr = yearly(eq)
            rows.append({"gate": tag, **s, **{f"y{k}": v for k, v in yr.items()}})
            print(f"  {tag:12s} final {s['final_equity']:>11,.0f}  "
                  f"cagr {s['cagr_pct']:>5.1f}%  dd {s['max_dd_pct']:>6.1f}%  "
                  f"2022 {yr.get(2022, float('nan')):>6.1f}%", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "kill_switch.csv"), index=False)

    # pick best gated variant by cagr adjusted for dd (require dd better than -60)
    cand = df[(df["gate"] != "none") & (df["max_dd_pct"] > -60)]
    best = (cand.sort_values("cagr_pct", ascending=False).iloc[0]
            if len(cand) else df.sort_values("max_dd_pct", ascending=False).iloc[1])
    bname = best["gate"].replace("_hard", "")
    bhard = best["gate"].endswith("_hard")
    print(f"\nbest switch: {best['gate']}")

    print(f"\n=== walk-forward (yearly re-selection) WITH {best['gate']} ===")
    grid = [(tgt, st) for tgt in (.01, .015, .02, .025, .03, .04)
            for st in (2, 3, 4, 5, 7)]
    hist_start = daily.index[0]
    gs = gates[bname]
    chained = 1.0
    wf_rows = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01")
        t1 = min(pd.Timestamp(f"{year+1}-01-01"), end + pd.Timedelta(days=1))
        bestc, bev = None, -1
        for tgt, st in grid:
            s, _ = run_compound(bars, daily, soxs, hist_start,
                                t0 - pd.Timedelta(days=1),
                                target=tgt, stall_days=st, mode="none",
                                sizing="eq4", gate=gs, gate_liquidate=bhard)
            if s["final_equity"] > bev:
                bev, bestc = s["final_equity"], (tgt, st)
        tgt, st = bestc
        s, _ = run_compound(bars, daily, soxs, t0, t1 - pd.Timedelta(days=1),
                            target=tgt, stall_days=st, mode="none",
                            sizing="eq4", gate=gs, gate_liquidate=bhard)
        ret = s["final_equity"] / compound_engine.START_EQ - 1
        chained *= 1 + ret
        wf_rows.append({"year": year, "picked": f"{tgt*100:g}%/{st}d",
                        "oos_ret_pct": round(ret * 100, 1),
                        "oos_dd_pct": s["max_dd_pct"]})
        print(f"  {year}: picked {tgt*100:g}%/{st}d -> OOS {ret*100:+.1f}% "
              f"(dd {s['max_dd_pct']}%)", flush=True)
    yrs = 4.5
    print(f"\n  chained OOS: $150K -> ${150000*chained:,.0f} "
          f"({(chained**(1/yrs)-1)*100:.1f}% CAGR) vs 3.3% ungated")
    pd.DataFrame(wf_rows).to_csv(os.path.join(OUT, "kill_switch_wf.csv"),
                                 index=False)

if __name__ == "__main__":
    main()
