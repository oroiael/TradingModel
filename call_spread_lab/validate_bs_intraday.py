#!/usr/bin/env python3
"""
validate_bs_intraday.py  --  does the Part-4 Black-Scholes intraday model match
the REAL intraday option prices now available (2024-2025)?

Part 4 estimated a leg's intraday value with BS(underlying_intraday_extreme, K, T,
prior-EOD IV). Here we test that estimator bar-by-bar against the actual 5-min
option trade price (vwap), and -- the part that actually drives harvesting -- we
compare BS at the underlying's intraday HIGH/LOW to the option's OWN intraday
high/low (the peak the harvester would sell into).

If BS tracks the real prices, the Part-4 intraday result (extrapolated to years
without intraday option data: 2022/2023/2026) is trustworthy. If it is biased, we
quantify the correction.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from data_loader import load_options, load_5min
from intraday_options import load_all_present
from bs import bs_call, bs_put

pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 80 + f"\n{t}\n" + "=" * 80)


def main():
    hr("LOAD intraday options + underlying 5-min + daily IV")
    io = load_all_present()
    print(f"intraday option bars: {len(io):,} | {io['date'].min()} -> {io['date'].max()} "
          f"| {io['expiration'].nunique()} expirations")

    fm = load_5min()
    fm["ts_naive"] = pd.to_datetime(fm["ts"])
    umap = dict(zip(fm["ts_naive"], fm["Close"]))
    fm["date"] = fm["ts_naive"].dt.date
    day_hilo = fm.groupby("date").agg(hi=("High", "max"), lo=("Low", "min"))

    # prior-EOD IV per contract from the daily file
    day = load_options(years=[2024, 2025])
    day = day.sort_values("trade_date")
    ivkey = {(td, ex, k, r): iv for td, ex, k, r, iv in
             zip(day.trade_date, day.expiration, day.strike, day.right, day.implied_vol)
             if iv == iv and iv > 0}
    tds = sorted(day["trade_date"].unique())
    prev_td = {tds[i]: tds[i - 1] for i in range(1, len(tds))}

    hr("1.  BAR-BY-BAR: BS(S_bar, K, T, prior-EOD IV) vs real option vwap")
    io2 = io.copy()
    io2["S"] = io2["ts_naive"].map(umap)
    io2 = io2[io2["S"].notna()]
    io2["mny"] = io2["strike"] / io2["S"] - 1
    # focus on the tradeable band and a live sample for speed
    band = io2[(io2["mny"].abs() <= 0.20)].copy()
    band = band.sample(min(60000, len(band)), random_state=1)
    bs_px = []
    for r in band.itertuples(index=False):
        ptd = prev_td.get(r.date)
        iv = ivkey.get((ptd, r.expiration, float(r.strike), r.right)) if ptd else None
        if iv is None:
            iv = ivkey.get((r.date, r.expiration, float(r.strike), r.right))
        if iv is None:
            bs_px.append(np.nan); continue
        T = max((pd.Timestamp(r.expiration) - pd.Timestamp(r.date)).days, 0) / 365.0
        p = bs_call(r.S, r.strike, T, iv) if r.right == "CALL" else bs_put(r.S, r.strike, T, iv)
        bs_px.append(p)
    band["bs"] = bs_px
    b = band[band["bs"].notna() & (band["vwap"] > 0.05)].copy()
    b["err"] = b["bs"] - b["vwap"]
    b["rel"] = b["err"] / b["vwap"]
    print(f"matched bars: {len(b):,}")
    print(f"  correlation BS vs real vwap: {b['bs'].corr(b['vwap']):.4f}")
    print(f"  median signed rel error (BS-real)/real: {b['rel'].median():+.1%}")
    print(f"  median ABS rel error: {b['rel'].abs().median():.1%}   "
          f"(IQR {b['rel'].abs().quantile(.25):.1%}..{b['rel'].abs().quantile(.75):.1%})")
    print("\n  by moneyness bucket (median abs rel error, median signed):")
    b["bucket"] = pd.cut(b["mny"], [-0.2, -0.05, 0.05, 0.2],
                         labels=["put 5-20% OTM", "ATM +/-5%", "call 5-20% OTM"])
    print(b.groupby("bucket", observed=True)["rel"].agg(
        n="size", abs_med=lambda s: s.abs().median(), signed_med="median").round(3).to_string())

    hr("2.  HARVEST-RELEVANT: BS at underlying intraday extreme vs option's OWN daily high")
    # for each (contract, date): option's real intraday high vs BS at underlying hi(call)/lo(put)
    g = io2.groupby(["date", "expiration", "strike", "right"]).agg(
        opt_hi=("high", "max")).reset_index()
    rows = []
    for r in g.itertuples(index=False):
        if r.date not in day_hilo.index:
            continue
        ptd = prev_td.get(r.date)
        iv = ivkey.get((ptd, r.expiration, float(r.strike), r.right)) if ptd else None
        if iv is None or not (r.opt_hi > 0.05):
            continue
        T = max((pd.Timestamp(r.expiration) - pd.Timestamp(r.date)).days, 0) / 365.0
        S_ext = day_hilo.loc[r.date, "hi"] if r.right == "CALL" else day_hilo.loc[r.date, "lo"]
        bs_ext = bs_call(S_ext, r.strike, T, iv) if r.right == "CALL" else bs_put(S_ext, r.strike, T, iv)
        rows.append((r.right, r.strike, r.opt_hi, bs_ext))
    h = pd.DataFrame(rows, columns=["right", "strike", "opt_hi", "bs_ext"])
    h["rel"] = (h["bs_ext"] - h["opt_hi"]) / h["opt_hi"]
    print(f"contract-days: {len(h):,}")
    print(f"  BS-at-underlying-extreme vs option real intraday high:")
    print(f"    median signed rel: {h['rel'].median():+.1%}  (BS>0 = overestimates the peak)")
    print(f"    median abs rel:    {h['rel'].abs().median():.1%}")
    print(f"    corr: {h['bs_ext'].corr(h['opt_hi']):.4f}")

    hr("READ")
    print("If abs error is small and correlation high, the Part-4 BS harvest trigger\n"
          "faithfully reproduces real intraday option behavior -> the 2022/2023/2026\n"
          "intraday extrapolation is trustworthy. A consistent signed bias tells us to\n"
          "haircut (or credit) the modeled harvest price by that amount.")


if __name__ == "__main__":
    main()
