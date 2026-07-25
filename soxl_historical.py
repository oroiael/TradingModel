import os
import sys
import pandas as pd
from datetime import date
from thetadata import ThetaClient

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SYMBOLS = ["SOXL"] 
START_DATE = date(2025, 1, 1) 
END_DATE = date(2025, 12, 31) 
OUTPUT_DIR = "raw_data"

THETA_EMAIL = "church.ben@gmail.com"
THETA_PASSWORD = "PistisSophia(09"

# ==============================================================================
# VERIFIED DATA FETCHING ENGINE
# ==============================================================================
def fetch_historical_options():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    client = ThetaClient(email=THETA_EMAIL, password=THETA_PASSWORD, dataframe_type="pandas")
    
    for symbol in SYMBOLS:
        print(f"\nProcessing {symbol}...")
        
        # 1. Get the master list of all expirations since the dawn of time
        exp_df = client.option_list_expirations(symbol=symbol)
        
        if 'expiration' in exp_df.columns:
            raw_exps = exp_df['expiration'].tolist()
        elif 'exp' in exp_df.columns:
            raw_exps = exp_df['exp'].tolist()
        elif 'date' in exp_df.columns:
            raw_exps = exp_df['date'].tolist()
        else:
            raw_exps = exp_df.iloc[:, -1].tolist() 
            
        # 2. THE FIX: Filter out the ancient history!
        valid_expirations = []
        for exp in raw_exps:
            # Convert to date
            if isinstance(exp, pd.Timestamp):
                safe_exp = exp.date()
            elif isinstance(exp, str):
                try:
                    safe_exp = pd.to_datetime(exp).date()
                except:
                    continue
            else:
                safe_exp = exp
                
            # ONLY KEEP expirations that occur in our window (2025 and later)
            if safe_exp >= START_DATE:
                valid_expirations.append(safe_exp)
                
        print(f"Found {len(raw_exps)} historical expirations. Filtered down to {len(valid_expirations)} relevant ones.")
        
        symbol_data = []
        
        for i, safe_exp in enumerate(valid_expirations):
            sys.stdout.write(f"\r      Processing expiration {i+1}/{len(valid_expirations)}: {safe_exp}...")
            sys.stdout.flush()
            
            try:
                # 3. Request history
                df = client.option_history_eod(
                    symbol=symbol,
                    expiration=safe_exp,
                    strike="*",
                    right="both",
                    start_date=START_DATE,
                    end_date=END_DATE
                )
                
                if not df.empty:
                    symbol_data.append(df)
            except Exception:
                continue
                
        print("\n   - Compiling and Saving...")
        if symbol_data:
            master_df = pd.concat(symbol_data, ignore_index=True)
            master_df.to_csv(os.path.join(OUTPUT_DIR, f"{symbol}_options_history.csv"), index=False)
            print(f"   -> Success: {len(master_df)} records saved.")
        else:
            print("   [!] No data found.")

if __name__ == "__main__":
    fetch_historical_options()