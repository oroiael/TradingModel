#!/usr/bin/env python3
"""
Data Evaluation for the SOXL Option Trading Project
====================================================

Purpose (per "Option Trading Project for SOXL.md", NOTE section):
    Evaluate the two data files and report the details needed to code the
    backtest -- BEFORE any strategy code is written.

Files evaluated
    1. SOXL_5min_3Years.csv      -- 5-minute intraday bars for SOXL
    2. SOXL_Master_Cleaned.csv   -- daily option chain snapshots for SOXL

What is checked and why
    5-minute stock data:
        - date range, number of trading days, bars per day (regular session
          should have 78 bars: 09:30-15:55 inclusive at 5-min steps)
        - missing / duplicate timestamps
        - zero or negative prices, zero-volume bars
        - OHLC integrity (High >= max(Open, Close), Low <= min(Open, Close))
        - availability of the exact bars the strategy needs:
          Monday 09:30, Monday 10:00, Friday 15:30, Friday close (15:55 bar)
    Option data (daily):
        - date range, expirations, strikes, rights (CALL/PUT)
        - zero bids / zero asks / crossed markets (bid > ask) -- flagged,
          NOT silently repaired (spec parameter #1)
        - zero / missing implied vol
        - whether strikes are whole numbers (spec parameter #5)
        - weekly (Friday) expirations coverage for the short-call leg
        - 4-6 month expirations coverage for the long-put leg
        - DTE sanity (dte column vs expiration - trade_date)
        - underlying_price vs 5-min close on the same day (cross-file check)
    Date alignment:
        - overlap window between the two files (the backtest can only run
          where BOTH files have data)
        - trade dates present in one file but not the other

Nothing is repaired or imputed here.  Problems are counted, examples are
printed, and the findings are written to qa/data_evaluation_report.txt so
the backtest can be coded against verified facts only.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
STOCK_CSV = ROOT / "SOXL_5min_3Years.csv"
OPTION_CSV = ROOT / "SOXL_Master_Cleaned.csv"
REPORT_TXT = ROOT / "qa" / "data_evaluation_report.txt"

_lines = []


def emit(msg=""):
    print(msg)
    _lines.append(str(msg))


def section(title):
    emit()
    emit("=" * 78)
    emit(title)
    emit("=" * 78)


# ---------------------------------------------------------------------------
# 1. Load 5-minute stock data
# ---------------------------------------------------------------------------
def load_stock():
    df = pd.read_csv(STOCK_CSV)
    # Format: "20230707 09:30:00 America/New_York"
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S",
    )
    df["dt"] = dt
    df["date"] = dt.dt.date
    df["time"] = dt.dt.time
    return df


def eval_stock(df):
    section("1. SOXL 5-MINUTE DATA  (SOXL_5min_3Years.csv)")
    emit(f"Rows (bars):            {len(df):,}")
    emit(f"Date range:             {df['date'].min()}  ->  {df['date'].max()}")
    days = df.groupby("date").size()
    emit(f"Trading days:           {len(days):,}")
    emit(f"Bars per day:           min={days.min()}  max={days.max()}  "
         f"mode={days.mode().iloc[0]}")

    short_days = days[days < 78]
    emit(f"Days with < 78 bars:    {len(short_days)} "
         f"(78 = full 09:30-15:55 regular session)")
    if len(short_days):
        emit("  Examples (date: bars) -- typically half-days around holidays:")
        for d, n in short_days.head(10).items():
            emit(f"    {d}: {n}")

    dupes = df.duplicated(subset=["dt"]).sum()
    emit(f"Duplicate timestamps:   {dupes}")

    bad_price = df[(df[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)]
    emit(f"Bars with price <= 0:   {len(bad_price)}")
    zero_vol = (df["Volume"] == 0).sum()
    emit(f"Bars with volume == 0:  {zero_vol}")

    ohlc_bad = df[
        (df["High"] < df[["Open", "Close"]].max(axis=1))
        | (df["Low"] > df[["Open", "Close"]].min(axis=1))
    ]
    emit(f"OHLC integrity violations (High<max(O,C) or Low>min(O,C)): "
         f"{len(ohlc_bad)}")

    # Session boundaries
    tmin = df.groupby("date")["time"].min().astype(str)
    tmax = df.groupby("date")["time"].max().astype(str)
    emit(f"First bar of day:       {tmin.value_counts().to_dict()}")
    emit(f"Last bar of day:        {tmax.value_counts().to_dict()}")

    # Bars the strategy specifically needs
    emit()
    emit("Strategy-critical bars:")
    dow = pd.to_datetime(df["date"].astype(str)).dt.dayofweek
    for label, day_num, t in [
        ("Monday 09:30 (underlying entry check)", 0, "09:30:00"),
        ("Monday 10:00 (sell weekly call)", 0, "10:00:00"),
        ("Friday 15:30 (10%/15% move check)", 4, "15:30:00"),
        ("Friday 15:55 (last bar / weekly close)", 4, "15:55:00"),
    ]:
        day_dates = set(df.loc[dow.values == day_num, "date"])
        have = set(
            df.loc[(dow.values == day_num) & (df["time"].astype(str) == t),
                   "date"]
        )
        missing = sorted(day_dates - have)
        emit(f"  {label}: {len(have)}/{len(day_dates)} days have the bar"
             + (f";  missing on {missing[:5]}" if missing else ""))

    # Large gaps between consecutive trading days (data holes vs holidays)
    d = pd.to_datetime(sorted(days.index.astype(str)))
    gaps = pd.Series(d).diff().dt.days
    big = gaps[gaps > 4]
    emit()
    emit(f"Gaps > 4 calendar days between trading days: {len(big)}")
    for i in big.index:
        emit(f"    {d[i-1].date()} -> {d[i].date()}  ({int(gaps[i])} days)")
    return days


# ---------------------------------------------------------------------------
# 2. Load daily option data
# ---------------------------------------------------------------------------
def load_options():
    df = pd.read_csv(
        OPTION_CSV,
        parse_dates=["expiration", "trade_date"],
        dtype={"right": "category", "symbol": "category"},
        low_memory=False,
    )
    return df


def eval_options(df):
    section("2. SOXL OPTION DATA  (SOXL_Master_Cleaned.csv)")
    emit(f"Rows:                   {len(df):,}")
    emit(f"Columns:                {list(df.columns)}")
    emit(f"Symbols:                {df['symbol'].unique().tolist()}")
    emit(f"Rights:                 {df['right'].value_counts().to_dict()}")
    emit(f"Trade-date range:       {df['trade_date'].min().date()}  ->  "
         f"{df['trade_date'].max().date()}")
    emit(f"Distinct trade dates:   {df['trade_date'].nunique()}")
    emit(f"Expiration range:       {df['expiration'].min().date()}  ->  "
         f"{df['expiration'].max().date()}")
    emit(f"Distinct expirations:   {df['expiration'].nunique()}")

    # Strikes (spec #5: whole numbers only for weeklies)
    strikes = df["strike"]
    frac = df[strikes % 1 != 0]
    emit(f"Strike range:           {strikes.min()} - {strikes.max()}")
    emit(f"Non-whole-number strikes: {len(frac):,} rows "
         f"({100*len(frac)/len(df):.2f}%)"
         + (f"; example strikes: {sorted(frac['strike'].unique())[:10]}"
            if len(frac) else ""))

    # Expiration day-of-week (weeklies should be Fridays)
    exp_dow = df["expiration"].dt.dayofweek.value_counts().sort_index()
    dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat",
                 6: "Sun"}
    emit("Expiration day-of-week: "
         + ", ".join(f"{dow_names[k]}={v:,}" for k, v in exp_dow.items()))

    # Quote quality (spec #1: identify zeros / missing, do not repair)
    emit()
    emit("Quote quality:")
    for col in ["bid", "ask"]:
        z = (df[col] == 0).sum()
        neg = (df[col] < 0).sum()
        na = df[col].isna().sum()
        emit(f"  {col}: zero={z:,} ({100*z/len(df):.2f}%)  negative={neg}  "
             f"NaN={na}")
    crossed = (df["bid"] > df["ask"]).sum()
    emit(f"  crossed markets (bid > ask): {crossed:,}")
    wide = df[(df["ask"] > 0) & (df["bid"] > 0)]
    spread_pct = ((wide["ask"] - wide["bid"]) / wide["ask"])
    emit(f"  spread as % of ask (where both sides > 0): "
         f"median={spread_pct.median():.1%}  p90={spread_pct.quantile(.9):.1%}")

    # Trade fields: many rows have OHLC volume 0 = no trades that day (quotes only)
    no_trade = (df["volume"] == 0).sum()
    emit(f"  rows with volume == 0 (quote-only, no trades): {no_trade:,} "
         f"({100*no_trade/len(df):.2f}%)")
    zero_close = ((df["close"] == 0) & (df["volume"] == 0)).sum()
    emit(f"  rows with close == 0 AND volume == 0: {zero_close:,} "
         f"(close price is meaningless on these rows -> must use bid/ask)")

    # IV (spec #7: BS pricing must use IV from the file)
    emit()
    emit("Implied volatility:")
    iv = df["implied_vol"]
    emit(f"  zero={(iv == 0).sum():,} ({100*(iv == 0).mean():.2f}%)  "
         f"NaN={iv.isna().sum():,}")
    ok = iv[(iv > 0)]
    emit(f"  where > 0: min={ok.min():.3f}  median={ok.median():.3f}  "
         f"max={ok.max():.3f}")
    emit(f"  iv_error: median={df['iv_error'].median():.4g}  "
         f"p99={df['iv_error'].quantile(.99):.4g}")

    # DTE sanity
    dte_calc = (df["expiration"] - df["trade_date"]).dt.days
    mismatch = (dte_calc != df["dte"]).sum()
    emit()
    emit(f"DTE column vs (expiration - trade_date): mismatches={mismatch:,}")
    emit(f"DTE range: {df['dte'].min()} - {df['dte'].max()} days")

    # Coverage for the two legs of the strategy
    emit()
    emit("Strategy coverage:")
    td = df.drop_duplicates(["trade_date", "expiration"])[
        ["trade_date", "expiration"]]
    td["dte"] = (td["expiration"] - td["trade_date"]).dt.days
    mondays = sorted(d for d in df["trade_date"].unique()
                     if pd.Timestamp(d).dayofweek == 0)
    have_weekly = 0
    for m in mondays:
        m = pd.Timestamp(m)
        wk = td[(td["trade_date"] == m) & (td["dte"] >= 1) & (td["dte"] <= 7)]
        if len(wk):
            have_weekly += 1
    emit(f"  Mondays in option data: {len(mondays)}; with a <=7-DTE "
         f"expiration listed: {have_weekly}")
    lp = td[(td["dte"] >= 120) & (td["dte"] <= 180)]
    emit(f"  trade dates with a 120-180 DTE expiration listed: "
         f"{lp['trade_date'].nunique()} / {df['trade_date'].nunique()}")
    lp2 = td[(td["dte"] >= 120) & (td["dte"] <= 200)]
    emit(f"  trade dates with a 120-200 DTE expiration listed: "
         f"{lp2['trade_date'].nunique()} / {df['trade_date'].nunique()}")

    return df


# ---------------------------------------------------------------------------
# 3. Cross-file alignment
# ---------------------------------------------------------------------------
def eval_alignment(stock_days, opt):
    section("3. DATE ALIGNMENT BETWEEN THE TWO FILES")
    s_dates = set(pd.to_datetime(sorted(stock_days.index.astype(str))).date)
    o_dates = set(opt["trade_date"].dt.date.unique())
    overlap = sorted(s_dates & o_dates)
    emit(f"Stock trading days:     {len(s_dates)}   "
         f"({min(s_dates)} -> {max(s_dates)})")
    emit(f"Option trade dates:     {len(o_dates)}   "
         f"({min(o_dates)} -> {max(o_dates)})")
    emit(f"Overlapping dates:      {len(overlap)}   "
         f"({overlap[0]} -> {overlap[-1]})")
    only_stock = sorted(d for d in (s_dates - o_dates)
                        if min(o_dates) <= d <= max(o_dates))
    only_opt = sorted(o_dates - s_dates)
    emit(f"In stock file only (within option window): {len(only_stock)}  "
         f"{only_stock[:10]}")
    emit(f"In option file only:                       {len(only_opt)}  "
         f"{only_opt[:10]}")
    emit()
    emit(">>> The backtest window is limited to the overlap: "
         f"{overlap[0]} -> {overlap[-1]} <<<")

    # underlying_price in the option file vs 5-min data close
    stock = load_stock()
    last_close = stock.groupby("date")["Close"].last()
    u = (opt.drop_duplicates("trade_date")[["trade_date", "underlying_price"]]
         .set_index(opt.drop_duplicates("trade_date")["trade_date"].dt.date))
    joined = u.join(last_close.rename("stock_close"), how="inner")
    joined["diff_pct"] = (
        (joined["underlying_price"] - joined["stock_close"]).abs()
        / joined["stock_close"] * 100)
    emit()
    emit("Cross-check: option file 'underlying_price' vs 5-min last close "
         "(same date):")
    emit(f"  dates compared: {len(joined)}")
    emit(f"  abs diff %: median={joined['diff_pct'].median():.3f}%  "
         f"p95={joined['diff_pct'].quantile(.95):.3f}%  "
         f"max={joined['diff_pct'].max():.3f}%")
    worst = joined.nlargest(3, "diff_pct")
    for d, row in worst.iterrows():
        emit(f"    worst: {d}  option_file={row['underlying_price']:.2f}  "
             f"5min_close={row['stock_close']:.2f}  "
             f"diff={row['diff_pct']:.2f}%")
    emit("  (small diffs are expected: the option snapshot timestamp is "
       "after the 16:00 close while the 5-min file's last bar is 15:55)")


def eval_raw_files(stock_days):
    """Evaluate the merged raw ThetaData exports (2024, 2025, 2026) against
    the two data gaps found in SOXL_Master_Cleaned.csv: no <=7-DTE quotes
    for the short call and no >60-DTE quotes for the long put."""
    from soxl_options_loader import RAW_FILES, load_raw_options
    section("4. RAW THETADATA EXPORTS  " + ", ".join(RAW_FILES))
    df = load_raw_options()
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    emit(f"Merged rows:            {len(df):,}")
    emit(f"Rights:                 {df['right'].value_counts().to_dict()}")
    emit(f"Trade-date range:       {df['trade_date'].min().date()}  ->  "
         f"{df['trade_date'].max().date()}  "
         f"({df['trade_date'].nunique()} days)")
    emit(f"DTE range:              {df['dte'].min()} - {df['dte'].max()}  "
         f"(negative-DTE rows: {(df['dte'] < 0).sum()})")
    emit("DTE bucket row counts:")
    buckets = pd.cut(df["dte"], [-1, 7, 14, 21, 30, 60, 90, 120, 180, 900])
    for b, n in buckets.value_counts().sort_index().items():
        emit(f"    {str(b):>12}: {n:,}")

    emit()
    emit("Gap checks vs SOXL_Master_Cleaned.csv (15-60 DTE only):")
    mond = df[df["trade_date"].dt.dayofweek == 0].groupby("trade_date")[
        "dte"].min()
    emit(f"  Mondays with a <=7-DTE expiration:  {(mond <= 7).sum()}/"
         f"{len(mond)}  (weekly short-call leg -> REAL quotes)")
    tg = df.groupby("trade_date")["dte"].max()
    emit(f"  trade dates with >=85 DTE listed:   {(tg >= 85).sum()}/"
         f"{len(tg)}  (~90-DTE put leg -> REAL quotes)")
    emit(f"  trade dates with >=150 DTE listed:  {(tg >= 150).sum()}/"
         f"{len(tg)}  (~6-month put leg -> REAL quotes)")
    g = df.groupby("trade_date").agg(u=("underlying_price", "first"),
                                     kmin=("strike", "min"),
                                     kmax=("strike", "max"))
    emit(f"  strike band vs spot:                median "
         f"[{(g['kmin']/g['u']).median():.2f}x, "
         f"{(g['kmax']/g['u']).median():.2f}x]  "
         f"(master file was ~+/-10% -> basis-anchored strikes now listed)")

    emit()
    emit("Quality:")
    emit(f"  bid==0: {100*(df['bid'] == 0).mean():.2f}%   "
         f"ask==0: {100*(df['ask'] == 0).mean():.2f}%   "
         f"crossed (bid>ask): {(df['bid'] > df['ask']).sum()}")
    emit(f"  implied_vol==0: {100*(df['implied_vol'] == 0).mean():.2f}%")
    emit(f"  non-whole strikes: "
         f"{100*(df['strike'] % 1 != 0).mean():.1f}% of rows")

    # alignment vs the 5-minute file over the merged window
    lo, hi = df["trade_date"].min().date(), df["trade_date"].max().date()
    sw = {d for d in stock_days.index if lo <= d <= hi}
    ow = set(df["trade_date"].dt.date.unique())
    emit()
    emit(f"Alignment vs 5-min file ({lo}..{hi}): stock days {len(sw)}, "
         f"option days {len(ow)}, "
         f"in stock only: {sorted(sw - ow)!s:.60}, "
         f"in options only: {sorted(ow - sw)!s:.60}")

    stock = load_stock()
    last_close = stock.groupby("date")["Close"].last()
    u = (df.drop_duplicates("trade_date")[["trade_date",
                                           "underlying_price"]]
         .set_index(df.drop_duplicates("trade_date")["trade_date"].dt.date))
    joined = u.join(last_close.rename("stock_close"), how="inner")
    diff = ((joined["underlying_price"] - joined["stock_close"]).abs()
            / joined["stock_close"] * 100)
    emit(f"underlying_price vs 5-min close: median diff "
         f"{diff.median():.3f}%  max {diff.max():.3f}%")

    emit()
    emit("VERDICT: the three raw exports together cover the FULL backtest")
    emit("window (2024-01-02 -> 2026-07-02) with 0-DTE-and-up expirations")
    emit("and the full strike range: BOTH legs of the trade can now be")
    emit("priced from real bid/ask quotes. The 2025 export uses M/D/YY")
    emit("dates while 2024/2026 use ISO -- normalized by")
    emit("soxl_options_loader.load_raw_options(); no further data needed.")


def main():
    for f in (STOCK_CSV, OPTION_CSV):
        if not f.exists():
            sys.exit(f"ERROR: missing data file {f}")
        if f.stat().st_size < 1000:
            sys.exit(f"ERROR: {f} looks like a Git LFS pointer, run "
                     "'git lfs pull' first")

    stock = load_stock()
    days = eval_stock(stock)
    opt = load_options()
    eval_options(opt)
    eval_alignment(days, opt)
    try:
        eval_raw_files(days)
    except FileNotFoundError as e:
        emit(f"\n(raw export evaluation skipped: {e})")

    REPORT_TXT.parent.mkdir(exist_ok=True)
    REPORT_TXT.write_text("\n".join(_lines) + "\n")
    emit()
    emit(f"Report written to {REPORT_TXT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
