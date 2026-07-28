"""
Transfer test — run the LOCKED SOXL core, settings untouched, on another
3x ETF. Closes §7 item 3 of the master document.

Locked rules applied verbatim (no re-tuning):
  gate   ATR5 >= 6.0% (ABSOLUTE — not rescaled to the new instrument)
  filter OR30 >= trailing-2yr 80th pct AND 10:00 print below top third
         of the opening range -> stand down  (self-calibrating: the
         percentile is computed from the instrument's own history)
  entry  from 11:00, resting limit at 0.99 x session high (prior bars)
  exits  +1% limit (fills next bar earliest) / -4% stop (same-bar allowed)
  caps   5 entries or 2 stop-outs; flat at the close
  engine corrected (v5_corrected_rerun.sim_trades_fixed)

Usage: python3 transfer_test.py [SYMBOL ...]     (default: SPXL)
Data:  <SYMBOL>_5min_6Years.csv in the repo root.

Split handling: the loader scans for close-to-close discontinuities >35%
and reports them rather than silently adjusting; SOXL's known 15:1
(2021-03-02) is applied by cycle_lab.one_pct_cycle_lab.load_bars, which
is used for SOXL. Other files in this repo are already back-adjusted.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cycle_lab"))
sys.path.insert(0, HERE)
from v5_corrected_rerun import sim_trades_fixed, day_pnl

OUT = os.path.join(HERE, "out")
START_I = 18          # 11:00
GATE = 6.0            # absolute ATR5 threshold — deliberately NOT rescaled

def load_symbol(sym):
    f = os.path.join(ROOT, f"{sym}_5min_6Years.csv")
    df = pd.read_csv(f)
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    df = df.assign(dt=dt, date=dt.dt.normalize())
    if sym == "SOXL":                      # known 15:1 split
        pre = df["date"] < pd.Timestamp("2021-03-02")
        for c in ["Open", "High", "Low", "Close"]:
            df.loc[pre, c] = df.loc[pre, c] / 15.0
    return df.sort_values("dt").reset_index(drop=True)

def build_daily(bars):
    g = bars.groupby("date")
    d = g.agg(o=("Open", "first"), h=("High", "max"),
              l=("Low", "min"), c=("Close", "last"))
    d["range_pct"] = (d["h"] - d["l"]) / d["o"] * 100
    d["atr5"] = d["range_pct"].rolling(5).mean().shift()
    or30, pos10 = {}, {}
    for dd, gb in g:
        hh = gb["High"].to_numpy()[:6]; ll = gb["Low"].to_numpy()[:6]
        cc = gb["Close"].to_numpy()
        orh, orl = hh.max(), ll.min()
        or30[dd] = (orh - orl) / gb["Open"].iloc[0] * 100
        pos10[dd] = (cc[5] - orl) / (orh - orl) if orh > orl and len(cc) > 5 else .5
    d["or30"] = pd.Series(or30); d["pos10"] = pd.Series(pos10)
    d["thr80"] = d["or30"].shift(1).rolling(504, min_periods=120).quantile(.8)
    return d, g

def run(sym, verbose=True):
    bars = load_symbol(sym)
    d, g = build_daily(bars)
    disc = d["c"].pct_change().abs()
    big = disc[disc > 0.35]
    if verbose and len(big):
        print(f"  [!] {sym}: close-to-close jumps >35% at "
              f"{[str(x.date()) for x in big.index]} — verify these are real moves")
    v9 = (d["or30"] < d["thr80"]) | ((d["or30"] >= d["thr80"]) & (d["pos10"] >= 2/3))
    on_mask = v9 & (d["atr5"] >= GATE)
    pnl = {}
    for dd, gb in g:
        if not on_mask.get(dd, False) or len(gb) < 20:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        pnl[dd] = day_pnl(sim_trades_fixed(o, h, l, c, START_I))
    on = pd.Series(pnl).sort_index()
    cal = d.index
    yrs = (cal[-1] - cal[0]).days / 365.25
    fullc = on.reindex(cal).fillna(0.0)
    eq = (1 + fullc).cumprod(); pk = eq.cummax(); dd_ = ((eq - pk) / pk)
    wk = fullc.groupby(pd.Grouper(freq="W")).sum() * 150000
    sh = on.mean() / on.std() * np.sqrt(252) if len(on) > 2 and on.std() > 0 else np.nan
    return {
        "symbol": sym,
        "median_day_range_%": round(d["range_pct"].median(), 2),
        "ON_days": len(on),
        "ON_rate_%": round(len(on) / len(cal) * 100, 1),
        "bp_per_ON_day": round(on.mean() * 1e4, 1) if len(on) else np.nan,
        "sharpe": round(sh, 2) if not np.isnan(sh) else np.nan,
        "ON_win_rate_%": round((on > 0).mean() * 100, 1) if len(on) else np.nan,
        "worst_day_%": round(on.min() * 100, 1) if len(on) else np.nan,
        "maxDD_%": round(dd_.min() * 100, 1),
        "CAGR_%": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
        "wk_mean_$150k": round(wk.mean()),
        "final_from_150k": round(150000 * eq.iloc[-1]),
    }, on

def main():
    syms = sys.argv[1:] or ["SPXL"]
    rows, series = [], {}
    for s in syms:
        print(f"running {s} ...", flush=True)
        r, on = run(s)
        rows.append(r); series[s] = on
    df = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print("TRANSFER TEST — locked SOXL rules applied verbatim (gate NOT rescaled)")
    print("=" * 100)
    print(df.to_string(index=False))
    df.to_csv(os.path.join(OUT, "transfer_test.csv"), index=False)
    for s, on in series.items():
        if len(on):
            print(f"\n{s} by year (bp/ON-day, n days):")
            byy = on.groupby(on.index.year).agg(["mean", "size"])
            print({int(y): (round(v["mean"] * 1e4, 1), int(v["size"]))
                   for y, v in byy.iterrows()})

if __name__ == "__main__":
    main()
