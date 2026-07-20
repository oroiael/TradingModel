#!/usr/bin/env python3
"""Cross-check the 2026 underlying_price anomaly against the independent 5-min feed
and against the option strike ranges actually quoted. Decides if 2026 is usable."""
from __future__ import annotations
import pandas as pd
from data_loader import load_options, underlying_daily_from_options, load_5min

opt = load_options(years=[2025, 2026])
u = underlying_daily_from_options(opt)
fm = load_5min()
# 5-min EOD close per day (last bar of the session)
fm_eod = fm.groupby("date")["Close"].last().rename("fivemin_eod").reset_index()
fm_eod["trade_date"] = pd.to_datetime(fm_eod["date"])

m = u.merge(fm_eod[["trade_date", "fivemin_eod"]], on="trade_date", how="inner")
m["ratio"] = m["close"] / m["fivemin_eod"]

print("A) OPTIONS underlying_price vs 5-MIN EOD close  (should be ~1.0 if consistent)")
print("   sampling 2025-12 through 2026-07:")
sample = m[m["trade_date"] >= "2025-12-15"].iloc[::4]
print(sample[["trade_date", "close", "fivemin_eod", "ratio"]]
      .to_string(index=False, formatters={"close": "{:.2f}".format,
                                           "fivemin_eod": "{:.2f}".format,
                                           "ratio": "{:.3f}".format}))

print("\nB) ratio stats by month (options_underlying / 5min_close):")
m["ym"] = m["trade_date"].dt.to_period("M")
print(m.groupby("ym")["ratio"].agg(["mean", "min", "max", "count"]).round(3).to_string())

print("\nC) Are the OPTION STRIKES consistent with the ~$180 underlying, or with ~$45?")
for td in ["2026-06-05", "2026-06-11"]:
    day = opt[(opt["trade_date"] == pd.Timestamp(td).date()) & (opt["right"] == "CALL")]
    if len(day):
        up = day["underlying_price"].iloc[0]
        print(f"   {td}: options underlying_price={up:.2f}  "
              f"strike range {day['strike'].min():.1f}..{day['strike'].max():.1f}  "
              f"n_strikes={day['strike'].nunique()}")
        # where is the ATM cluster of strikes?
        med = day["strike"].median()
        print(f"           median strike quoted={med:.1f}")
