import pandas as pd
import numpy as np
from datetime import time

# ==========================================
# FILE PATHS - Adjust if files are in a subfolder
# ==========================================
STOCK_FILE = 'SOXL_5min_3Years.csv'
OPTIONS_FILE = 'SOXL_Master_Cleaned.csv'

def run_quality_control():
    print("="*60)
    print("PHASE 1: DATA QUALITY & INTEGRITY AUDIT")
    print("="*60)

    # ---------------------------------------------------------
    # 1. LOAD & INSPECT 5-MINUTE STOCK DATA
    # ---------------------------------------------------------
    print("\n--- [1] Loading 5-Minute Stock Data ---")
    try:
        df_stock = pd.read_csv(STOCK_FILE)
        print(f"Stock Data Loaded Successfully: {len(df_stock):,} rows.")
        print("Stock Columns Detected:", list(df_stock.columns))
    except Exception as e:
        print(f"CRITICAL ERROR loading {STOCK_FILE}: {e}")
        return

    # Identify date/time column (common names: 'date', 'datetime', 'time', 'timestamp')
    time_col = next((col for col in df_stock.columns if 'time' in col.lower() or 'date' in col.lower()), None)
    if not time_col:
        print("CRITICAL ERROR: Could not identify a timestamp column in stock data.")
        return

    df_stock[time_col] = pd.to_datetime(df_stock[time_col], errors='coerce')
    df_stock = df_stock.dropna(subset=[time_col]).sort_values(by=time_col).reset_index(drop=True)
    
    start_date_stock = df_stock[time_col].min()
    end_date_stock = df_stock[time_col].max()
    print(f"Stock Date Range: {start_date_stock} to {end_date_stock}")

    # Check for basic pricing anomalies (zeros, negatives, NaNs)
    price_cols = [c for c in df_stock.columns if any(p in c.lower() for p in ['open', 'high', 'low', 'close'])]
    for col in price_cols:
        zeros = (df_stock[col] <= 0).sum()
        nans = df_stock[col].isna().sum()
        if zeros > 0 or nans > 0:
            print(f"WARNING: Column '{col}' contains {zeros} zero/negative values and {nans} NaNs.")
        else:
            print(f"Price Integrity OK for '{col}': No zeros or NaNs detected.")

    # Check for Strategy Critical Timestamps: Monday 10:00 AM & Friday 3:30 PM
    df_stock['day_of_week'] = df_stock[time_col].dt.day_name()
    df_stock['time_only'] = df_stock[time_col].dt.time

    mondays = df_stock[df_stock['day_of_week'] == 'Monday']
    fridays = df_stock[df_stock['day_of_week'] == 'Friday']

    # We check for 10:00 AM (or closest bar) on Mondays
    mon_10am = mondays[mondays['time_only'] == time(10, 0)]
    unique_mondays = mondays[time_col].dt.date.nunique()
    print(f"\nMonday Execution Check: Found {len(mon_10am)} exact 10:00 AM bars out of {unique_mondays} trading Mondays.")
    if len(mon_10am) < unique_mondays:
        print(" -> NOTE: Some Mondays lack an exact 10:00 AM bar (likely market holidays or delayed opens). We will code a fallback to the nearest available timestamp after 10:00 AM.")

    # We check for 3:30 PM on Fridays
    fri_330pm = fridays[fridays['time_only'] == time(15, 30)]
    unique_fridays = fridays[time_col].dt.date.nunique()
    print(f"Friday Execution Check: Found {len(fri_330pm)} exact 3:30 PM bars out of {unique_fridays} trading Fridays.")

    # ---------------------------------------------------------
    # 2. LOAD & INSPECT DAILY OPTIONS DATA
    # ---------------------------------------------------------
    print("\n--- [2] Loading Daily Options Data ---")
    try:
        df_opt = pd.read_csv(OPTIONS_FILE)
        print(f"Options Data Loaded Successfully: {len(df_opt):,} rows.")
        print("Options Columns Detected:", list(df_opt.columns))
    except Exception as e:
        print(f"CRITICAL ERROR loading {OPTIONS_FILE}: {e}")
        return

    # Map essential option columns (case-insensitive)
    opt_cols = {col.lower(): col for col in df_opt.columns}
    
    # Identify quote date and expiration date columns
    quote_col = next((opt_cols[c] for c in opt_cols if 'date' in c or 'quote' in c), None)
    exp_col = next((opt_cols[c] for c in opt_cols if 'exp' in c), None)
    strike_col = next((opt_cols[c] for c in opt_cols if 'strike' in c), None)
    bid_col = next((opt_cols[c] for c in opt_cols if 'bid' in c), None)
    ask_col = next((opt_cols[c] for c in opt_cols if 'ask' in c), None)
    iv_col = next((opt_cols[c] for c in opt_cols if 'iv' in c or 'vol' in c), None)

    print(f"Mapped Options Schema -> Date: {quote_col}, Exp: {exp_col}, Strike: {strike_col}, Bid: {bid_col}, Ask: {ask_col}, IV: {iv_col}")

    if not all([quote_col, exp_col, strike_col, bid_col, ask_col]):
        print("CRITICAL ERROR: Missing one or more required columns (Date, Expiration, Strike, Bid, Ask) in options file.")
        return

    df_opt[quote_col] = pd.to_datetime(df_opt[quote_col], errors='coerce')
    df_opt[exp_col] = pd.to_datetime(df_opt[exp_col], errors='coerce')
    
    start_date_opt = df_opt[quote_col].min()
    end_date_opt = df_opt[quote_col].max()
    print(f"Options Date Range: {start_date_opt} to {end_date_opt}")

    # Check Parameter #5: Whole number strikes
    non_whole_strikes = df_opt[df_opt[strike_col] % 1 != 0]
    print(f"Strike Price Audit: Found {len(non_whole_strikes):,} rows with decimal strikes out of {len(df_opt):,}.")
    if len(non_whole_strikes) > 0:
        print(" -> ACTION REQUIRED BY RULE #5: We must filter for whole number strikes (e.g., 100.0) during strategy execution.")

    # Check Parameter #6 & #7: Bid/Ask Spread and IV Integrity
    invalid_spreads = df_opt[(df_opt[bid_col] <= 0) | (df_opt[ask_col] <= 0) | (df_opt[ask_col] < df_opt[bid_col])]
    print(f"Bid/Ask Spread Audit: Found {len(invalid_spreads):,} rows with $0.00 bids, $0.00 asks, or inverted spreads (Ask < Bid).")
    if len(invalid_spreads) > 0:
        print(" -> NOTE: Zero bids are common for deep OTM/ITM options. Our execution engine will require fallback pricing or exclusion rules when spreads are invalid.")

    if iv_col:
        zero_iv = (df_opt[iv_col] <= 0).sum() + df_opt[iv_col].isna().sum()
        print(f"Implied Volatility Audit: Found {zero_iv:,} rows with missing or zero IV (relevant for Black-Scholes fallback).")

    # ---------------------------------------------------------
    # 3. SYNCHRONIZATION & DATE ALIGNMENT CHECK
    # ---------------------------------------------------------
    print("\n--- [3] Date Synchronization Audit ---")
    stock_dates = set(df_stock[time_col].dt.date)
    opt_dates = set(df_opt[quote_col].dt.date)
    
    common_dates = stock_dates.intersection(opt_dates)
    missing_in_opt = stock_dates - opt_dates
    missing_in_stock = opt_dates - stock_dates

    print(f"Synchronized Trading Days: {len(common_dates)}")
    print(f"Days in Stock Data missing from Options Data: {len(missing_in_opt)}")
    print(f"Days in Options Data missing from Stock Data: {len(missing_in_stock)}")

    if len(missing_in_opt) > 0:
        sample_missing = sorted(list(missing_in_opt))[:5]
        print(f" -> Sample stock dates missing option quotes: {sample_missing}")

    print("\n" + "="*60)
    print("AUDIT COMPLETE. READY FOR PHASE 2 LOGIC VERIFICATION.")
    print("="*60)

if __name__ == "__main__":
    run_quality_control()