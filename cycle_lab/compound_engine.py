"""
Round 3: $150K compounding engine for the SOXL cycle strategy.

Changes vs the fixed-100-share engine (one_pct_cycle_lab.py):
  * Starts with $150,000 cash; every lot is sized from current capital and all
    proceeds are reinvested (compounding).
  * No options. On a stall the choices are:
      - 'none': park the stalled lot for ~1 month (21 trading days), start a
        new lot (round-1/2 "no hedge" behavior);
      - 'stop': sell the stalled lot immediately and restart;
      - 'soxs': park the stalled lot AND buy a dollar-matched slug of SOXS
        (-3x inverse) at the stall close as a temporary hedge. SOXS exit rule:
          'recover' -- sell the SOXS the first day SOXL closes back above the
                       stall-day close (hedge only while the fall continues);
          'fixedN'  -- sell after N trading days;
          'lot'     -- hold until the parked lot is sold.
  * Lot sizing: 'half_cash' = each new lot spends half of available cash
    (always leaves reserve for stall doubling); 'eq4'/'eq6' = equity/4 or /6
    capped at cash; 'full' = all cash (sensible only for 'stop', which never
    holds two lots).

Data: SOXL_5min_6Years.csv (split-adjusted in-code) for intraday fills,
      SOXS_5min_6Years.csv daily closes (file is already back-adjusted).

Outputs: cycle_lab/out/compound_grid.csv, compound_focus.csv
"""

import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from one_pct_cycle_lab import load_bars, daily_from_bars, ROOT, OUT

START_EQ = 150_000.0

def load_soxs_daily():
    df = pd.read_csv(os.path.join(ROOT, "SOXS_5min_6Years.csv"))
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    df = df.assign(date=dt.dt.normalize())
    return df.groupby("date")["Close"].last()

def run_compound(bars, daily, soxs, start, end,
                 target=0.015, stall_days=3, mode="none",
                 soxs_exit="recover", soxs_fixed_n=5,
                 hold_tdays=21, sizing="half_cash"):
    days = [d for d in daily.index if start <= d <= end]
    pos = {d: i for i, d in enumerate(days)}
    bars_w = bars[(bars["date"] >= start) & (bars["date"] <= end)]
    bars_by_day = {d: (g["Open"].to_numpy(), g["High"].to_numpy(),
                       g["Close"].to_numpy()) for d, g in bars_w.groupby("date")}
    soxs = soxs.reindex(daily.index).ffill()

    cash = START_EQ
    active = None            # {shares, entry, entry_i}
    parked = []              # {shares, entry, exit_i, stall_px, soxs_sh, soxs_px, stall_i}
    wins = stalls = 0
    soxs_pnl_total = 0.0
    eq_curve = []

    def equity(spot, sx):
        e = cash + (active["shares"] * spot if active else 0.0)
        for p in parked:
            e += p["shares"] * spot
            if p["soxs_sh"]:
                e += p["soxs_sh"] * sx
        return e

    def budget(spot, sx):
        if sizing == "half_cash":
            return cash * 0.5
        if sizing == "full":
            return cash
        n = int(sizing[2:])          # eq3, eq4, eq6, ...
        return min(cash, equity(spot, sx) / n)

    def open_lot(price, i, sx):
        nonlocal cash, active
        sh = math.floor(budget(price, sx) / price)
        if sh >= 1:
            cash -= sh * price
            active = {"shares": sh, "entry": price, "entry_i": i}
        else:
            active = None

    for d in days:
        i = pos[d]
        if d not in bars_by_day:
            continue
        o, h, c = bars_by_day[d]
        sx = float(soxs.loc[d])

        if active is None:
            open_lot(c[0], i, sx)

        # ---- intraday limit sells on the active lot
        b = 0
        while b < len(c) and active is not None:
            tgt = active["entry"] * (1 + target)
            if h[b] >= tgt:
                fill = o[b] if o[b] > tgt else tgt
                cash += active["shares"] * fill
                wins += 1
                open_lot(c[b], i, sx)
            b += 1

        spot = c[-1]

        # ---- EOD: manage parked lots and their SOXS hedges
        keep = []
        for p in parked:
            if p["soxs_sh"]:
                sell_soxs = (
                    (soxs_exit == "recover" and spot >= p["stall_px"]) or
                    (soxs_exit.startswith("fixed") and i - p["stall_i"] >= soxs_fixed_n) or
                    i >= p["exit_i"])
                if sell_soxs:
                    cash += p["soxs_sh"] * sx
                    soxs_pnl_total += p["soxs_sh"] * (sx - p["soxs_px"])
                    p["soxs_sh"] = 0
            if i >= p["exit_i"]:
                cash += p["shares"] * spot
            else:
                keep.append(p)
        parked = keep

        # ---- EOD: stall check
        if active is not None and i - active["entry_i"] >= stall_days:
            stalls += 1
            if mode == "stop":
                cash += active["shares"] * spot
                active = None
                open_lot(spot, i, sx)
            else:
                p = {"shares": active["shares"], "entry": active["entry"],
                     "exit_i": i + hold_tdays, "stall_px": spot,
                     "stall_i": i, "soxs_sh": 0, "soxs_px": sx}
                if mode == "soxs":
                    want = active["shares"] * spot          # dollar-matched
                    spend = min(want, cash)
                    p["soxs_sh"] = spend / sx               # fractional ok
                    cash -= spend
                parked.append(p)
                active = None
                open_lot(spot, i, sx)

        eq_curve.append({"date": d, "equity": equity(spot, sx),
                         "deployed": 1 - cash / max(equity(spot, sx), 1)})

    # liquidate
    last = days[-1]; spot = float(daily.loc[last, "c"]); sx = float(soxs.loc[last])
    if active:
        cash += active["shares"] * spot
        active = None
    for p in parked:
        cash += p["shares"] * spot
        if p["soxs_sh"]:
            cash += p["soxs_sh"] * sx
            soxs_pnl_total += p["soxs_sh"] * (sx - p["soxs_px"])
    parked = []

    eq = pd.DataFrame(eq_curve).set_index("date")
    years = (days[-1] - days[0]).days / 365.25
    peak = eq["equity"].cummax()
    max_dd = ((eq["equity"] - peak) / peak).min()
    return {
        "final_equity": round(cash, 0),
        "total_ret_pct": round((cash / START_EQ - 1) * 100, 1),
        "cagr_pct": round(((cash / START_EQ) ** (1 / years) - 1) * 100, 1),
        "max_dd_pct": round(max_dd * 100, 1),
        "avg_deployed_pct": round(eq["deployed"].mean() * 100, 1),
        "wins": wins, "stalls": stalls,
        "soxs_pnl": round(soxs_pnl_total, 0),
    }, eq

def main():
    bars = load_bars()
    daily = daily_from_bars(bars)
    soxs = load_soxs_daily()
    start = pd.Timestamp("2022-01-03")
    end = pd.Timestamp("2026-07-02")

    def label(kw):
        m = kw["mode"]
        if m == "soxs":
            m += "_" + kw.get("soxs_exit", "recover")
            if kw.get("soxs_exit", "").startswith("fixed"):
                m += str(kw.get("soxs_fixed_n"))
        return m

    # ---------------- grid: target x stall x mode
    rows = []
    modes = [
        dict(mode="none", sizing="half_cash"),
        dict(mode="stop", sizing="full"),
        dict(mode="soxs", soxs_exit="recover", sizing="half_cash"),
        dict(mode="soxs", soxs_exit="fixed", soxs_fixed_n=5, sizing="half_cash"),
        dict(mode="soxs", soxs_exit="lot", sizing="half_cash"),
    ]
    print("=== $150K compounding grid, 2022-01-03..2026-07-02 ===", flush=True)
    for tgt in [0.01, 0.0125, 0.015, 0.0175, 0.02, 0.025, 0.03, 0.04]:
        for stall in [1, 2, 3, 4, 5, 7]:
            for mkw in modes:
                kw = dict(target=tgt, stall_days=stall, **mkw)
                s, _ = run_compound(bars, daily, soxs, start, end, **kw)
                s.update({"target": tgt * 100, "stall": stall,
                          "mode": label(kw), "sizing": mkw["sizing"]})
                rows.append(s)
        print(f"  target {tgt*100:g}% done", flush=True)
    gdf = pd.DataFrame(rows)
    gdf.to_csv(os.path.join(OUT, "compound_grid.csv"), index=False)

    cols = ["target", "stall", "mode", "final_equity", "cagr_pct", "max_dd_pct",
            "avg_deployed_pct", "wins", "stalls", "soxs_pnl"]
    print("\n=== top 15 by final equity ===")
    print(gdf.sort_values("final_equity", ascending=False)[cols].head(15)
          .to_string(index=False))
    gdf["ret_per_dd"] = (gdf["total_ret_pct"] / gdf["max_dd_pct"].abs()).round(2)
    print("\n=== top 10 by return/drawdown ===")
    print(gdf.sort_values("ret_per_dd", ascending=False)[cols + ["ret_per_dd"]]
          .head(10).to_string(index=False))

    # ---------------- focus: sizing sensitivity + full-history robustness
    best = gdf.sort_values("final_equity", ascending=False).iloc[0]
    bt, bs = best["target"] / 100, int(best["stall"])
    print(f"\n=== sizing sensitivity on winner (t{best['target']:g}%/s{bs}/"
          f"{best['mode']}) ===")
    focus = []
    bmode = [m for m in modes if label(dict(**m)) == best["mode"]][0]
    for sz in ["half_cash", "eq4", "eq6", "full"]:
        kw = dict(target=bt, stall_days=bs, **{**bmode, "sizing": sz})
        s, eq = run_compound(bars, daily, soxs, start, end, **kw)
        s.update({"test": f"sizing={sz}", "target": bt * 100, "stall": bs,
                  "mode": label(kw)})
        focus.append(s)
        print(f"  {sz:10s} final {s['final_equity']:>11,.0f}  cagr {s['cagr_pct']:>5.1f}%"
              f"  dd {s['max_dd_pct']:>6.1f}%  deployed {s['avg_deployed_pct']:>5.1f}%",
              flush=True)

    print("\n=== full-history robustness (2020-07-23..2026-07-21) top-3 configs ===")
    fs = pd.Timestamp("2020-07-23"); fe = daily.index[-1]
    for _, r in gdf.sort_values("final_equity", ascending=False).head(3).iterrows():
        mkw = [m for m in modes if label(dict(**m)) == r["mode"]][0]
        kw = dict(target=r["target"] / 100, stall_days=int(r["stall"]), **mkw)
        s, eq = run_compound(bars, daily, soxs, fs, fe, **kw)
        s.update({"test": "full_history", "target": r["target"],
                  "stall": int(r["stall"]), "mode": r["mode"]})
        focus.append(s)
        print(f"  t{r['target']:g}/s{int(r['stall'])}/{r['mode']:14s} "
              f"final {s['final_equity']:>11,.0f}  cagr {s['cagr_pct']:>5.1f}%  "
              f"dd {s['max_dd_pct']:>6.1f}%", flush=True)

    pd.DataFrame(focus).to_csv(os.path.join(OUT, "compound_focus.csv"), index=False)

if __name__ == "__main__":
    main()
