"""Distill the 736 raw intraday 5-min option files into one parquet of trade bars.

Keeps only bars where a trade actually printed (count>0 and close present) --
per drift_lab/DATA_NOTES.md, `close` is the reliable price field and `vwap` is a
carried-forward last value that cannot be trusted per-bar.
"""
import glob, os, sys
import pandas as pd
from multiprocessing import Pool

RAW = "/home/user/TradingModel/raw_data"
OUT = "/home/user/TradingModel/cc_lp_lab/out"
COLS = ["expiration", "strike", "right", "timestamp", "close", "volume", "count"]


def one(path):
    df = pd.read_csv(path, usecols=COLS)
    df = df[(df["count"] > 0) & df["close"].notna()]
    if df.empty:
        return None
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    out = pd.DataFrame({
        "exp": pd.to_datetime(df["expiration"]).dt.date.astype("string"),
        "strike": df["strike"].astype("float32"),
        "right": df["right"].str[0].astype("string"),   # C / P
        "date": ts.dt.date.astype("string"),
        "minute": (ts.dt.hour * 60 + ts.dt.minute).astype("int16"),
        "px": df["close"].astype("float32"),
        "vol": df["volume"].astype("int32"),
    })
    return out


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(RAW, "SOXL_intraday_5m_exp_*.csv")))
    print(f"{len(files)} files", flush=True)
    parts = []
    with Pool(4) as p:
        for i, r in enumerate(p.imap_unordered(one, files, chunksize=4)):
            if r is not None:
                parts.append(r)
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(files)}", flush=True)
    df = pd.concat(parts, ignore_index=True)
    # Several capture-segment files overlap on the same expiration; drop dupes.
    df = df.drop_duplicates(subset=["exp", "strike", "right", "date", "minute"])
    df = df.sort_values(["exp", "right", "strike", "date", "minute"], ignore_index=True)
    path = os.path.join(OUT, "opt_intraday_trades.parquet")
    df.to_parquet(path, index=False, compression="zstd")
    print(f"rows={len(df):,}  -> {path}  ({os.path.getsize(path)/1e6:.0f} MB)")
    print("date range", df["date"].min(), df["date"].max())
    print("exp range ", df["exp"].min(), df["exp"].max())
