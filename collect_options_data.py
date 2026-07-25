import os
import sys
import pandas as pd
from datetime import date
from thetadata import ThetaClient

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SYMBOLS = ["SOXL", "QQQ", "SPY"]
START_DATE = date(2023, 1, 1)
END_DATE = date(2026, 1, 1)
OUTPUT_DIR = "raw_data"

# Add your ThetaData credentials here
THETA_EMAIL = "church.ben@gmail.com"
THETA_PASSWORD = "PistisSophia(09"

# ==============================================================================
# FINAL INTEGRATED DATA FETCH
# ==============================================================================
def fetch_historical_options():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print(f"Authenticating...")
    # Authentication (v3 standard)
    client = ThetaClient(email="church.ben@gmail.com", password="PistisSophia(09", dataframe_type="pandas")
    
    # Get all trading days
    trading_days = pd.bdate_range(start=START_DATE, end=END_DATE)
    total_days = len(trading_days)
    
    for symbol in SYMBOLS:
        print(f"\nProcessing {symbol}...")
        symbol_data = []
        
        for i, day in enumerate(trading_days):
            current_day = day.date()
            sys.stdout.write(f"\r      Downloading {current_day} ({i+1}/{total_days})...")
            sys.stdout.flush()
            
            try:
                # We pull the entire snapshot for the day.
                # v3 API: passing None for expiration/strike returns the full chain.
                df = client.option_history_eod(
                    symbol=symbol,
                    expiration=None, 
                    strike=None, 
                    right="both",
                    start_date=current_day,
                    end_date=current_day
                )
                
                if not df.empty:
                    symbol_data.append(df)
            except Exception as e:
                continue 
        
        print("\n   - Compiling and Saving...")
        if symbol_data:
            master_df = pd.concat(symbol_data, ignore_index=True)
            master_df.to_csv(os.path.join(OUTPUT_DIR, f"{symbol}_options_3YR.csv"), index=False)
            print(f"   -> Success: {len(master_df)} records saved.")
        else:
            print("   [!] No data found. Check your subscription or symbol.")

if __name__ == "__main__":
    fetch_historical_options()