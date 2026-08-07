"""Phase 4c -- corrected cost accounting, and the final basket-vs-single question.

Correction: p3 reported the gated overnight sleeve at 5.86 round-trips/year and
therefore a 276bp break-even.  That counted GATE TRANSITIONS.  An overnight
sleeve is flat every day by construction, so it round-trips on every day the
gate is ON -- exposure * 252, roughly 147/yr.  The break-even below is ~20x
smaller than the number p3 printed and is the one to use.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from common import OUT, SYMBOLS, TRADING_DAYS, banner, load_raw, max_drawdown, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 230)

raw = {s: load_raw(s) for s in SYMBOLS}
sess = {s: session_ohlc(raw[s]) for s in SYMBOLS}
common = sorted(set.intersection(*[set(sess[s].index) for s in SYMBOLS]))
TRAIN_END = pd.Timestamp("2023-12-31")

k = {s: sess[s].loc[common] for s in SYMBOLS}
ov = {s: np.log(k[s]["open"] / k[s]["close"].shift(1)).dropna() for s in SYMBOLS}
full = {s: np.log(k[s]["close"] / k[s]["close"].shift(1)).dropna() for s in SYMBOLS}
rv21 = full["SPXL"].rolling(21).std() * np.sqrt(TRADING_DAYS)
gate = (rv21.shift(1) < 0.45).reindex(ov["SPXL"].index).fillna(False)


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if r.std() > 0 else np.nan


print(banner("CORRECTED COST ACCOUNTING -- overnight sleeves round-trip DAILY"))
cands = {
    "ON SPXL (ungated)": (ov["SPXL"], pd.Series(True, index=ov["SPXL"].index)),
    "ON FAS (ungated)": (ov["FAS"], pd.Series(True, index=ov["FAS"].index)),
    "ON 50/50 (ungated)": (0.5 * ov["SPXL"] + 0.5 * ov["FAS"],
                           pd.Series(True, index=ov["SPXL"].index)),
    "ON SPXL (gated rv21<45%)": (ov["SPXL"], gate),
    "ON FAS (gated rv21<45%)": (ov["FAS"], gate),
    "ON 50/50 (gated rv21<45%)": (0.5 * ov["SPXL"] + 0.5 * ov["FAS"], gate),
}
rows = []
for nm, (base, g) in cands.items():
    r = base.where(g, 0.0)
    days_on = int(g.sum())
    rt_yr = days_on / (len(r) / TRADING_DAYS)      # one round trip per ON day
    ann = r.mean() * TRADING_DAYS
    rec = {"strategy": nm, "exposure": g.mean(), "rt_per_yr": rt_yr,
           "ann_ret": ann, "ann_vol": r.std() * np.sqrt(TRADING_DAYS),
           "sharpe_gross": sharpe(r), "max_dd": max_drawdown(r.cumsum()),
           "breakeven_bp": ann / rt_yr * 1e4}
    for c in (1, 2, 3, 5, 10):
        rc = r - (c / 1e4) * g.astype(float)       # cost only charged on ON days
        rec[f"SR@{c}bp"] = sharpe(rc)
        rec[f"ret@{c}bp"] = rc.mean() * TRADING_DAYS
    rows.append(rec)
ct = pd.DataFrame(rows).set_index("strategy")
print(ct[["exposure", "rt_per_yr", "ann_ret", "ann_vol", "sharpe_gross", "max_dd",
          "breakeven_bp"]].to_string(float_format=lambda x: f"{x:.4f}"))
print("\nSharpe net of round-trip cost:")
print(ct[[c for c in ct.columns if c.startswith("SR@")]].to_string(
    float_format=lambda x: f"{x:+.4f}"))
print("\nAnnual return net of round-trip cost:")
print(ct[[c for c in ct.columns if c.startswith("ret@")]].to_string(
    float_format=lambda x: f"{x:+.2%}"))

print(banner("DOES THE BASKET BEAT THE SINGLE NAME?  (the whole question)"))
comp = {
    "SPXL alone, gated overnight": ov["SPXL"].where(gate, 0.0),
    "SPXL+FAS 50/50, gated overnight": (0.5 * ov["SPXL"] + 0.5 * ov["FAS"]).where(gate, 0.0),
    "SPXL+FAS+VXX equal, gated overnight": (
        (ov["SPXL"] + ov["FAS"] + ov["VXX"]) / 3).where(gate, 0.0),
    "SPXL buy & hold": full["SPXL"],
}
rows = []
for nm, r in comp.items():
    rows.append({"portfolio": nm, "ann_ret": r.mean() * TRADING_DAYS,
                 "ann_vol": r.std() * np.sqrt(TRADING_DAYS), "sharpe": sharpe(r),
                 "sr_train": sharpe(r[r.index <= TRAIN_END]),
                 "sr_test": sharpe(r[r.index > TRAIN_END]),
                 "max_dd": max_drawdown(r.cumsum()),
                 "worst_day": r.min(),
                 "cvar95": r[r <= r.quantile(0.05)].mean()})
print(pd.DataFrame(rows).set_index("portfolio").to_string(float_format=lambda x: f"{x:.4f}"))

print(banner("CAPACITY -- what size can this actually trade?"))
print("Overnight execution is MOC/MOO, which is the deepest liquidity of the day,")
print("so the 5-min bar profile understates capacity. Reported both ways.\n")
for s in ("SPXL", "FAS"):
    d = raw[s].copy()
    d["notional"] = d["Close"] * d["Volume"]
    d = d[d["ts"] >= d["ts"].max() - pd.Timedelta(days=730)]
    close_bar = d[d["tod"] == pd.Timestamp("15:55").time()]["notional"]
    open_bar = d[d["tod"] == pd.Timestamp("09:30").time()]["notional"]
    daily = d.groupby("session")["notional"].sum()
    print(f"  {s}:")
    print(f"    15:55 bar notional   median ${close_bar.median():>12,.0f}   "
          f"p05 ${close_bar.quantile(0.05):>12,.0f}")
    print(f"    09:30 bar notional   median ${open_bar.median():>12,.0f}   "
          f"p05 ${open_bar.quantile(0.05):>12,.0f}")
    print(f"    full-day notional    median ${daily.median():>12,.0f}   "
          f"p05 ${daily.quantile(0.05):>12,.0f}")
    print(f"    at 5% of the p05 closing bar: ${close_bar.quantile(0.05)*0.05:>12,.0f} "
          f"max position")

ct.to_csv(OUT / "p5_corrected_costs.csv")
print(f"\n[saved] {OUT}/p5_corrected_costs.csv")
