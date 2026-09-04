"""Build normalized caches for the CC+LP backtest.

Outputs (ccp_lab/cache/):
  underlying_1min_1000.parquet : one row per session, the 10:00 1-min bar (O/H/L/C)
  underlying_daily.parquet     : session open/high/low/close from the 1-min tape
  chains.parquet               : EOD option chain, normalized across the 5 vendor formats
  prints_1000.parquet          : 5-min option trade prints in the 09:30-10:30 window
"""
import os, csv, glob, sys
import pandas as pd, numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ccp_lab.compat import save_df, CACHE, PARQUET, check_sources, HOWTO, safe_stdout

os.makedirs(CACHE, exist_ok=True)

def log(*a): print(*a, flush=True)

# ---------------------------------------------------------------- underlying
def build_underlying():
    log("== underlying 1-min ==")
    df = pd.read_csv(os.path.join(ROOT, "SOXL_1min.csv"))
    df["ts"] = df["Date"].str.replace(" America/New_York", "", regex=False)
    dtx = pd.to_datetime(df["ts"], format="%Y%m%d %H:%M:%S")
    df["date"] = dtx.dt.date
    df["hm"] = dtx.dt.strftime("%H:%M")
    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})

    ten = df[df["hm"] == "10:00"][["date", "o", "h", "l", "c", "v"]].copy()
    ten = ten.drop_duplicates("date").reset_index(drop=True)
    save_df(ten, "underlying_1min_1000")
    log(f"   10:00 bars: {len(ten)}  {ten.date.min()} -> {ten.date.max()}")

    daily = df.groupby("date").agg(o=("o", "first"), h=("h", "max"),
                                   l=("l", "min"), c=("c", "last"), v=("v", "sum")).reset_index()
    save_df(daily, "underlying_daily")
    log(f"   sessions:   {len(daily)}")
    return daily

# ------------------------------------------------------------------- chains
def _pdate(s):
    """Vendor dates are ISO in 2022-24/2026 and M/D/YY in 2025."""
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return pd.NaT
    if "/" in s:
        return pd.to_datetime(s, format="%m/%d/%y", errors="coerce")
    return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="coerce")

def build_chains():
    log("== EOD chains ==")
    keep = ["expiration", "strike", "right", "timestamp", "close", "volume",
            "bid", "ask", "implied_vol", "delta", "underlying_price", "trade_date"]
    out = []
    for y in [2022, 2023, 2024, 2025, 2026]:
        p = os.path.join(ROOT, f"SOXL_Options_{y}.csv")
        df = pd.read_csv(p, usecols=keep, low_memory=False)
        df["trade_date"] = df["trade_date"].map(_pdate)
        df["expiration"] = df["expiration"].map(_pdate)
        for c in ["strike", "close", "bid", "ask", "implied_vol", "delta",
                  "underlying_price", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["year"] = y
        n0 = len(df)
        df = df.dropna(subset=["trade_date", "expiration", "strike", "right"])
        # the strike universe the strategy is allowed to trade
        frac = (df["strike"] * 100).round().astype("int64") % 100
        df["std_strike"] = frac.isin([0, 50])
        out.append(df)
        log(f"   {y}: {n0:>7} rows -> {len(df):>7} parsed, "
            f"std strikes {df.std_strike.mean()*100:5.1f}%, "
            f"{df.trade_date.min().date()} -> {df.trade_date.max().date()}")
    ch = pd.concat(out, ignore_index=True)
    ch["dte"] = (ch["expiration"] - ch["trade_date"]).dt.days
    ch["mid"] = np.where((ch.bid > 0) & (ch.ask > 0), (ch.bid + ch.ask) / 2.0, np.nan)
    save_df(ch, "chains")
    log(f"   total {len(ch)} contract-days")
    return ch

# ------------------------------------------------------------------- prints
def build_prints():
    log("== intraday 5-min prints (09:30-10:30) ==")
    files = sorted(glob.glob(os.path.join(ROOT, "raw_data", "SOXL_intraday_5m_exp_*.csv")))
    log(f"   {len(files)} files")
    frames = []
    for i, f in enumerate(files):
        try:
            df = pd.read_csv(f, usecols=["expiration", "strike", "right", "timestamp",
                                         "open", "high", "low", "close", "volume"],
                             low_memory=False)
        except Exception as e:
            log(f"   !! {os.path.basename(f)}: {e}"); continue
        if not len(df):
            continue
        # The vendor already writes Eastern local time with the offset appended
        # ("2024-01-02 09:30:00-05:00"), so the ET wall clock IS the string. Slicing
        # it avoids needing an IANA tz database, which Windows does not ship, and is
        # far faster than parsing 8M timestamps.
        ts = df["timestamp"].astype(str)
        df["date"] = pd.to_datetime(ts.str.slice(0, 10), format="%Y-%m-%d",
                                    errors="coerce").dt.date
        df["hm"] = ts.str.slice(11, 16)
        df = df[df["hm"].between("09:30", "10:30")]
        df = df[pd.to_numeric(df["close"], errors="coerce").notna()]
        df = df[pd.to_numeric(df["volume"], errors="coerce").fillna(0) > 0]
        if not len(df):
            continue
        df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
        frames.append(df[["expiration", "strike", "right", "date", "hm",
                          "open", "high", "low", "close", "volume"]])
        if (i + 1) % 100 == 0:
            log(f"   ...{i+1}/{len(files)}")
    pr = pd.concat(frames, ignore_index=True)
    for c in ["open", "high", "low", "close", "volume"]:
        pr[c] = pd.to_numeric(pr[c], errors="coerce")
    pr = pr.dropna(subset=["expiration", "strike", "close"])
    save_df(pr, "prints_1000")
    log(f"   {len(pr)} traded 5-min bars in the morning window")
    log(f"   with a 10:00 bar: {(pr.hm=='10:00').sum()}")
    return pr

if __name__ == "__main__":
    safe_stdout()
    problems = check_sources()
    if problems:
        for x in problems:
            log("  - " + x)
        log(HOWTO)
        raise SystemExit(1)
    log(f"cache format: {'parquet' if PARQUET else 'pickle (pyarrow not installed)'}")
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "underlying"): build_underlying()
    if what in ("all", "chains"):     build_chains()
    if what in ("all", "prints"):     build_prints()
    log("done.")
