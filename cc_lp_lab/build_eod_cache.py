"""Distill SOXL_Options_20XX.csv (EOD chains, real bid/ask + IV) into one parquet.

One row per (trade_date, expiration, strike, right): the listed contract, its
closing bid/ask, implied vol and delta. This is the authoritative *strike ladder*
-- "two strikes out of the money" has to be measured against listed strikes, not
against whichever strikes happened to print a trade.
"""
import os
import pandas as pd

ROOT = "/home/user/TradingModel"
OUT = os.path.join(ROOT, "cc_lp_lab/out")
COLS = ["expiration", "strike", "right", "bid", "ask", "close", "volume",
        "delta", "implied_vol", "underlying_price", "trade_date"]

parts = []
for yr in range(2022, 2027):
    f = os.path.join(ROOT, f"SOXL_Options_{yr}.csv")
    df = pd.read_csv(f, usecols=COLS)
    out = pd.DataFrame({
        "date": pd.to_datetime(df["trade_date"]).dt.date.astype("string"),
        "exp": pd.to_datetime(df["expiration"]).dt.date.astype("string"),
        "strike": df["strike"].astype("float32"),
        "right": df["right"].str[0].astype("string"),
        "bid": df["bid"].astype("float32"),
        "ask": df["ask"].astype("float32"),
        "close": df["close"].astype("float32"),
        "vol": df["volume"].fillna(0).astype("int32"),
        "delta": df["delta"].astype("float32"),
        "iv": df["implied_vol"].astype("float32"),
        "spot": df["underlying_price"].astype("float32"),
    })
    print(yr, len(out), "rows", flush=True)
    parts.append(out)

df = pd.concat(parts, ignore_index=True)
df = df.drop_duplicates(subset=["date", "exp", "strike", "right"], keep="last")
df = df.sort_values(["date", "exp", "right", "strike"], ignore_index=True)
p = os.path.join(OUT, "opt_eod_chain.parquet")
df.to_parquet(p, index=False, compression="zstd")
print(f"rows={len(df):,} -> {p} ({os.path.getsize(p)/1e6:.0f} MB)")
print("dates", df.date.min(), df.date.max())
