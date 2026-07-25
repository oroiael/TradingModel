import pandas as pd
import numpy as np
import os
import glob

def process_raw_directory(input_dir="soxl_raw_data", output_file="SOXL_Master_Cleaned.csv"):
    print(f"Scanning directory: {input_dir}/ for raw CSV files...")
    
    # Find all CSV files in the raw_data folder
    all_files = glob.glob(os.path.join(input_dir, "*.csv"))
    
    if not all_files:
        print("Error: No CSV files found in the raw_data directory.")
        return

    processed_frames = []
    
    for file in all_files:
        print(f"\nProcessing: {os.path.basename(file)}...")
        
        # 1. Load the raw data chunks
        df = pd.read_csv(file, low_memory=False)
        df.columns = df.columns.str.lower().str.strip()
        
        # Standardize Date Columns
        date_col = 'trade_date' if 'trade_date' in df.columns else 'date'
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df['expiration'] = pd.to_datetime(df['expiration'], errors='coerce')
        
        # 2. Calculate DTE and filter (Keep 15 to 60 DTE for our Harvester)
        df['dte'] = (df['expiration'] - df[date_col]).dt.days
        df = df[(df['dte'] >= 15) & (df['dte'] <= 60)]
        
        # 3. Clean Greeks without dropping essential rows
        if 'delta' in df.columns:
            df['delta'] = pd.to_numeric(df['delta'], errors='coerce').fillna(0.0)
            
        if 'implied_vol' in df.columns:
            df['implied_vol'] = pd.to_numeric(df['implied_vol'], errors='coerce')
            df['implied_vol'] = df.groupby(['trade_date', 'expiration'])['implied_vol'].transform(
                lambda x: x.fillna(x.median())
            )
        
        # 4. Dimensionality Reduction (Drop strikes that are mathematically useless)
        if 'underlying_price' in df.columns and 'strike' in df.columns:
            df['moneyness'] = df['strike'] / df['underlying_price']
            # We need deep OTM puts, so we keep 40% to 110% moneyness
            df = df[(df['moneyness'] >= 0.40) & (df['moneyness'] <= 1.10)]
        
        # 5. Price standardization
        if 'close' in df.columns:
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
        elif 'bid' in df.columns and 'ask' in df.columns:
            df['bid'] = pd.to_numeric(df['bid'], errors='coerce').fillna(0)
            df['ask'] = pd.to_numeric(df['ask'], errors='coerce').fillna(0)
            df['close'] = np.where(df['bid'] > 0, (df['bid'] + df['ask']) / 2, df['ask'] / 2)
        
        # Drop rows that literally have no price at all
        df = df.dropna(subset=['close'])
        
        processed_frames.append(df)
        print(f" -> Kept {len(df)} highly relevant rows from this file.")

    # 6. Combine all processed files into one master dataset
    print("\nMerging all processed data...")
    master_df = pd.concat(processed_frames, ignore_index=True)
    
    # Sort chronologically
    master_df.sort_values(by=[date_col, 'expiration', 'strike'], inplace=True)
    
    print(f"Total Master Dataset Size: {len(master_df)} rows.")
    master_df.to_csv(output_file, index=False)
    print(f"Success! Master file saved as: {output_file}")

if __name__ == "__main__":
    # Ensure the raw_data directory exists
    if not os.path.exists("soxl_raw_data"):
        os.makedirs("soxl_raw_data")
        print("Created 'raw_data' directory. Please place your 3 CSV files inside it and run again.")
    else:
        process_raw_directory()