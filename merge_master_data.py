import pandas as pd
import os
import gc

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SYMBOLS = ["SOXL", "TQQQ"]
YEARS = [2024, 2025, 2026]
DATA_DIR = "raw_data" # Change to "" if files are in the same folder as the script

# ==============================================================================
# HELPER: DYNAMIC COLUMN FINDER
# ==============================================================================
def find_date_column(df, possible_names):
    """Finds the date column case-insensitively."""
    for col in df.columns:
        if col.lower() in possible_names:
            return col
    return None

# ==============================================================================
# MERGE ENGINE
# ==============================================================================
def create_master_files():
    for symbol in SYMBOLS:
        print(f"\n========================================")
        print(f"Building Master File for {symbol}...")
        print(f"========================================")
        
        # 1. Combine the Multi-Year Options Data
        appended_data = []
        for year in YEARS:
            file_name = os.path.join(DATA_DIR, f"{symbol}_options_{year}.csv")
            if os.path.exists(file_name):
                print(f" -> Loading {file_name}...")
                
                # Load CSV. low_memory=False prevents mixed-type guessing errors on huge files
                df = pd.read_csv(file_name, low_memory=False)
                appended_data.append(df)
            else:
                print(f" -> [!] WARNING: {file_name} not found. Skipping.")
                
        if not appended_data:
            print(f"[!] No options data found for {symbol}. Moving to next.")
            continue
            
        print(" -> Concatenating options years (This may take a moment for large files)...")
        options_df = pd.concat(appended_data, ignore_index=True)
        
        # Dynamically find the Options Date Column
        opt_date_col = find_date_column(options_df, ['date', 'quote_date', 'timestamp', 'datadate', 'time'])
        
        if not opt_date_col:
            print(f"\n[!] CRITICAL ERROR: Could not identify a Date column in the Options data.")
            continue
            
        print(f" -> Identified options date column as: '{opt_date_col}'")
        
        # THE FIX: Add utc=True to normalize mixed timezones (EST/EDT) and .dt.date to isolate the day
        options_df['Date_Parsed'] = pd.to_datetime(options_df[opt_date_col].astype(str), errors='coerce', utc=True).dt.date
        
        # 2. Load the IBKR Underlying Data
        underlying_file = os.path.join(DATA_DIR, f"{symbol}_underlying.csv")
        if os.path.exists(underlying_file):
            print(f" -> Loading underlying data from {underlying_file}...")
            underlying_df = pd.read_csv(underlying_file)
            
            ibkr_date_col = find_date_column(underlying_df, ['date', 'time', 'timestamp'])
            
            if not ibkr_date_col:
                print(f" -> [!] WARNING: Could not find Date column in IBKR data.")
                master_df = options_df
            else:
                # Apply the exact same timezone normalization to the IBKR dates
                underlying_df['Date_Parsed'] = pd.to_datetime(underlying_df[ibkr_date_col].astype(str), errors='coerce', utc=True).dt.date
                
                close_col = find_date_column(underlying_df, ['close', 'c', 'last'])
                if not close_col:
                    print(f" -> [!] WARNING: Could not find a 'Close' price column in IBKR data.")
                    master_df = options_df
                else:
                    # Keep only what we need to save memory
                    underlying_slim = underlying_df[['Date_Parsed', close_col]].rename(columns={close_col: 'Underlying_Close'})
                    
                    print(" -> Merging underlying price into options chain...")
                    master_df = pd.merge(options_df, underlying_slim, on='Date_Parsed', how='left')
        else:
            print(f" -> [!] WARNING: {underlying_file} not found. Master file will lack underlying prices.")
            master_df = options_df
            
        # Clean up the temporary parsing column
        if 'Date_Parsed' in master_df.columns:
            master_df = master_df.drop(columns=['Date_Parsed'])
            
        # 3. Save the Master File
        output_file = os.path.join(DATA_DIR, f"{symbol}_MASTER_DATA.csv")
        print(f" -> Saving {output_file} (Writing to disk)...")
        master_df.to_csv(output_file, index=False)
        print(f" -> SUCCESS: Saved {len(master_df)} total rows.")
        
        # Free up RAM before processing the next symbol
        del options_df
        del master_df
        del appended_data
        gc.collect()

if __name__ == "__main__":
    create_master_files()
    print("\nAll Master files generated successfully. Ready for the Analysis Engine.")