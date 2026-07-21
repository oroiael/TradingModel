#!/usr/bin/env python3
"""
profile_data.py  --  ground-truth data-quality report for the call-spread lab.

Answers, from the data only, every question the backtester depends on:
  1. underlying price path (and hunt for the $300 anomaly / split artifacts)
  2. what expirations exist and whether ~7 / ~14 / ~30 DTE tenors are available
     on a typical entry day (weekly / two-week / monthly trades)
  3. strike spacing and how many strikes are non-whole (would be dropped)
  4. option quote quality: zero-bid, inverted, zero-IV rates by moneyness/DTE
  5. a concrete ATM call chain sample so we can see a real spread being built

Run:  python3 call_spread_lab/profile_data.py
Writes a plain-text report to stdout and outputs/underlying_path.png.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data_loader import load_options, underlying_daily_from_options, load_5min, ROOT
from pathlib import Path

OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)


def hr(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def main():
    opt = load_options(verbose=True)
    calls = opt[opt["right"] == "CALL"].copy()

    # ---------------------------------------------------------------- underlying
    hr("1.  UNDERLYING PRICE PATH  (from option snapshots' underlying_price)")
    u = underlying_daily_from_options(opt)
    print(f"trade dates: {len(u)}   {u['trade_date'].min().date()} -> "
          f"{u['trade_date'].max().date()}")
    print(f"close range: {u['close'].min():.2f} .. {u['close'].max():.2f}")
    # year-by-year span
    u["year"] = u["trade_date"].dt.year
    yr = u.groupby("year")["close"].agg(["first", "min", "max", "last", "count"])
    print("\nper-year underlying close (first / min / max / last / n days):")
    print(yr.round(2).to_string())

    # anomaly hunt: daily % change of the EOD underlying
    u = u.sort_values("trade_date").reset_index(drop=True)
    u["ret"] = u["close"].pct_change()
    big = u.reindex(u["ret"].abs().sort_values(ascending=False).index).head(12)
    print("\n12 largest day-over-day underlying moves (candidate split/data breaks):")
    print(big[["trade_date", "close", "ret"]].to_string(index=False))

    # how many days have an implausible underlying (SOXL never > ~ $75 real)
    hi = u[u["close"] > 80]
    print(f"\ndays with underlying_price > $80 (implausible for SOXL): {len(hi)}")
    if len(hi):
        print(hi[["trade_date", "close"]].head(20).to_string(index=False))

    # -------------------------------------------------------------- expirations
    hr("2.  EXPIRATION / DTE AVAILABILITY  (can we trade 7 / 14 / 30 DTE?)")
    exps = sorted(opt["expiration"].unique())
    print(f"distinct expirations: {len(exps)}   "
          f"{exps[0]} -> {exps[-1]}")
    # weekday of expirations
    exp_wd = pd.Series([pd.Timestamp(e).day_name() for e in exps]).value_counts()
    print("\nexpiration weekday counts:\n" + exp_wd.to_string())

    # For each trade_date, list available DTEs; measure how often a tenor near
    # 7 / 14 / 30 calendar days exists (tolerance windows).
    per_day = (opt.groupby("trade_date")["dte"]
                  .apply(lambda s: sorted(set(s))).reset_index(name="dtes"))

    def has_dte(dtes, lo, hi):
        return any(lo <= d <= hi for d in dtes)

    windows = {"weekly ~7 (4-10)": (4, 10),
               "two-week ~14 (11-18)": (11, 18),
               "monthly ~30 (25-38)": (25, 38)}
    n = len(per_day)
    print(f"\nof {n} trade dates, fraction with at least one expiration in window:")
    for label, (lo, hi) in windows.items():
        frac = per_day["dtes"].apply(lambda d: has_dte(d, lo, hi)).mean()
        print(f"   {label:26s}: {frac:6.1%}")

    # typical count of distinct expirations offered per day
    ndte = per_day["dtes"].apply(len)
    print(f"\ndistinct expirations offered per trade date: "
          f"min {ndte.min()}, median {int(ndte.median())}, max {ndte.max()}")

    # -------------------------------------------------------------- strikes
    hr("3.  STRIKE GRID  (whole-number enforcement impact)")
    frac_whole = (opt["strike"] % 1 == 0).mean()
    print(f"rows with whole-number strike: {frac_whole:6.2%}  "
          f"(non-whole get dropped by the spec filter)")
    # strike spacing near ATM for a sample recent day
    sday = sorted(calls["trade_date"].unique())[-40]
    s_spot = u.loc[u["trade_date"] == pd.Timestamp(sday), "close"]
    spot = float(s_spot.iloc[0]) if len(s_spot) else np.nan
    near = (calls[(calls["trade_date"] == sday)]
            .assign(dist=lambda d: (d["strike"] - spot).abs()))
    strikes_sorted = np.sort(near["strike"].unique())
    if len(strikes_sorted) > 1:
        diffs = np.diff(strikes_sorted)
        vals, cnts = np.unique(np.round(diffs, 2), return_counts=True)
        print(f"\nstrike spacing on {sday} (spot {spot:.2f}): "
              + ", ".join(f"${v}:{c}x" for v, c in zip(vals, cnts)))

    # -------------------------------------------------------------- quote quality
    hr("4.  CALL QUOTE QUALITY  (illiquid / zero-bid / inverted / zero-IV)")
    c = calls.copy()
    c["moneyness"] = c["strike"] / c["underlying_price"] - 1.0  # + = OTM call
    c["zero_bid"] = c["bid"] <= 0
    c["inverted"] = c["ask"] < c["bid"]
    c["zero_ask"] = c["ask"] <= 0
    c["zero_iv"] = ~(c["implied_vol"] > 0)
    total = len(c)
    print(f"total call rows: {total:,}")
    for col in ["zero_bid", "zero_ask", "inverted", "zero_iv"]:
        print(f"   {col:9s}: {c[col].mean():6.2%}")

    # focus on the region this strategy actually trades: slightly-OTM calls, short DTE
    band = c[(c["moneyness"].between(0.0, 0.15)) & (c["dte"].between(3, 40))]
    print(f"\nSTRATEGY BAND (0-15% OTM calls, 3-40 DTE): {len(band):,} rows")
    for col in ["zero_bid", "zero_ask", "inverted", "zero_iv"]:
        print(f"   {col:9s}: {band[col].mean():6.2%}")
    print("   median bid/ask/mid & spread%:")
    b = band[(band["bid"] > 0) & (band["ask"] >= band["bid"])]
    mid = (b["bid"] + b["ask"]) / 2
    spr = (b["ask"] - b["bid"]) / mid.replace(0, np.nan)
    print(f"     bid {b['bid'].median():.2f}  ask {b['ask'].median():.2f}  "
          f"mid {mid.median():.2f}  spread/mid median {spr.median():.1%}")

    # -------------------------------------------------------------- sample chain
    hr("5.  SAMPLE ATM CALL CHAIN  (build one real spread by hand)")
    # pick a mid-sample Monday with a ~7 DTE expiration
    sample_td = None
    for td in sorted(opt["trade_date"].unique()):
        if pd.Timestamp(td).year != 2024:
            continue
        sub = calls[(calls["trade_date"] == td) & (calls["dte"].between(4, 10))]
        if len(sub) and pd.Timestamp(td).day_name() == "Monday":
            sample_td = td
            break
    if sample_td is not None:
        spot = float(calls.loc[calls["trade_date"] == sample_td,
                               "underlying_price"].iloc[0])
        exp = calls[(calls["trade_date"] == sample_td) &
                    (calls["dte"].between(4, 10))]["expiration"].min()
        chain = (calls[(calls["trade_date"] == sample_td) &
                       (calls["expiration"] == exp) &
                       (calls["strike"] % 1 == 0)]
                 .sort_values("strike"))
        chain = chain[(chain["strike"] >= spot - 3) & (chain["strike"] <= spot + 8)]
        print(f"trade_date {sample_td}  spot {spot:.2f}  expiration {exp} "
              f"(DTE {(pd.Timestamp(exp)-pd.Timestamp(sample_td)).days})")
        print(chain[["strike", "bid", "ask", "close", "delta",
                     "implied_vol", "volume"]].to_string(index=False))

    # -------------------------------------------------------------- plot
    fig, ax = plt.subplots(figsize=(11, 4))
    good = u[u["close"] <= 80]
    ax.plot(good["trade_date"], good["close"], lw=0.9)
    bad = u[u["close"] > 80]
    if len(bad):
        ax.scatter(bad["trade_date"], bad["close"], c="red", s=12,
                   label=f"underlying>$80 ({len(bad)})")
        ax.legend()
    ax.set_title("SOXL EOD underlying (from option snapshots)")
    ax.set_ylabel("price")
    fig.tight_layout()
    fig.savefig(OUT / "underlying_path.png", dpi=110)
    print(f"\nsaved {OUT/'underlying_path.png'}")


if __name__ == "__main__":
    main()
