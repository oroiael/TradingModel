import pandas as pd
import numpy as np
from datetime import time

STOCK_FILE = 'SOXL_5min_3Years.csv'
OPTIONS_FILE = 'SOXL_Master_Cleaned.csv'

def run_final_audit():
    print("="*60)
    print("PHASE 1 (REV C): FINAL INTEGRITY & SYNCHRONIZATION AUDIT")
    print("="*60)

    # ---------------------------------------------------------
    # 1. STOCK DATA - EXACT STRING TRANSFORMATION
    # ---------------------------------------------------------
    print("\n--- [1] 5-Minute Stock Data Re-Audit ---")
    df_stock = pd.read_csv(STOCK_FILE)
    
    # Remove timezone suffix and parse exact string structure: YYYYMMDD HH:MM:SS
    df_stock['Date_Clean'] = df_stock['Date'].astype(str).str.replace(' America/New_York', '', regex=False)
    df_stock['Date'] = pd.to_datetime(df_stock['Date_Clean'], format='%Y%m%d %H:%M:%S', errors='coerce')
    
    df_stock = df_stock.dropna(subset=['Date']).sort_values(by='Date').reset_index(drop=True)
    
    start_stock = df_stock['Date'].min()
    end_stock = df_stock['Date'].max()
    print(f"VERIFIED Stock Date Range: {start_stock} to {end_stock} ({len(df_stock):,} valid rows)")

    # Strategy Critical Timestamp Check
    df_stock['day_name'] = df_stock['Date'].dt.day_name()
    df_stock['time_val'] = df_stock['Date'].dt.time

    mon_10am = df_stock[(df_stock['day_name'] == 'Monday') & (df_stock['time_val'] == time(10, 0))]
    fri_330pm = df_stock[(df_stock['day_name'] == 'Friday') & (df_stock['time_val'] == time(15, 30))]

    print(f"Exact Monday 10:00 AM Bars Found: {len(mon_10am)}")
    print(f"Exact Friday 3:30 PM Bars Found: {len(fri_330pm)}")

    # ---------------------------------------------------------
    # 2. OPTIONS DATA - VERIFIED SCHEMA
    # ---------------------------------------------------------
    print("\n--- [2] Daily Options Data Verification ---")
    df_opt = pd.read_csv(OPTIONS_FILE, low_memory=False)
    
    col_map = {
        'date': 'trade_date',
        'exp': 'expiration',
        'strike': 'strike',
        'bid': 'bid',
        'ask': 'ask',
        'iv': 'implied_vol',
        'right': 'right'
    }

    df_opt[col_map['date']] = pd.to_datetime(df_opt[col_map['date']], errors='coerce')
    df_opt[col_map['exp']] = pd.to_datetime(df_opt[col_map['exp']], errors='coerce')

    start_opt = df_opt[col_map['date']].min()
    end_opt = df_opt[col_map['date']].max()
    print(f"VERIFIED Options Date Range: {start_opt} to {end_opt}")

    # ---------------------------------------------------------
    # 3. SYNCHRONIZATION ANALYSIS
    # ---------------------------------------------------------
    print("\n--- [3] Date Synchronization Analysis ---")
    stock_days = set(df_stock['Date'].dt.date)
    opt_days = set(df_opt[col_map['date']].dt.date)

    common_days = sorted(list(stock_days.intersection(opt_days)))
    missing_opts = sorted(list(stock_days - opt_days))
    missing_stock = sorted(list(opt_days - stock_days))

    print(f"Total Synchronized Trading Days: {len(common_days)}")
    if len(common_days) > 0:
        print(f"Synchronized Period: {common_days[0]} to {common_days[-1]}")
    print(f"Stock Days missing Options Data: {len(missing_opts)}")
    print(f"Options Days missing Stock Data: {len(missing_stock)}")

    print("\n" + "="*60)
    print("READY FOR PHASE 2 EXECUTION ENGINE DEVELOPMENT.")
    print("="*60)

if __name__ == "__main__":
    run_final_audit()