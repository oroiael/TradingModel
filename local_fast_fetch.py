import os
import sys
import requests
import pandas as pd

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SYMBOLS = ["SOXL", "QQQ", "SPY"]
START_DATE = "20250101" # YYYYMMDD format
END_DATE = "20251231"
OUTPUT_DIR = "raw_data"

# ==============================================================================
# DIRECT LOCAL REST ENGINE (Bypasses buggy ThetaClient SDK)
# ==============================================================================
def fetch_local_rest():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # The ThetaTerminal JAR runs a local server on port 25520
    base_url = "http://127.0.0.1:25520/v2/hist/option/eod"
    
    # Generate list of business days
    days = pd.bdate_range(start="2025-01-01", end="2025-12-31").strftime("%Y%m%d").tolist()
    total_days = len(days)

    for symbol in SYMBOLS:
        print(f"\n========================================")
        print(f"Processing {symbol} (Direct Local API)")
        print(f"========================================")
        
        symbol_data = []
        
        for i, day in enumerate(days):
            # Visually track the days
            sys.stdout.write(f"\r      Downloading Day {i+1}/{total_days} ({day[:4]}-{day[4:6]}-{day[6:]})...")
            sys.stdout.flush()
            
            # The API requires querying Calls (C) and Puts (P) separately
            for right in ['C', 'P']:
                params = {
                    "root": symbol,
                    "exp": 0,        # 0 = ALL Expirations in the raw API
                    "strike": 0,     # 0 = ALL Strikes
                    "right": right,
                    "start_date": day,
                    "end_date": day
                }
                
                try:
                    # Ping the local Java Terminal directly
                    res = requests.get(base_url, params=params, timeout=10)
                    
                    if res.status_code == 200:
                        data = res.json()
                        
                        # ThetaData returns data in a 'response' array
                        if 'response' in data and len(data['response']) > 0:
                            # Attach the headers provided by the API
                            df = pd.DataFrame(data['response'], columns=data.get('header'))
                            df['Option_Right'] = right
                            symbol_data.append(df)
                except Exception as e:
                    # Ignore connection blips on empty days
                    pass
                    
        print("\n   - Compiling and Saving...")
        if symbol_data:
            master_df = pd.concat(symbol_data, ignore_index=True)
            output_path = os.path.join(OUTPUT_DIR, f"{symbol}_options_2025.csv")
            master_df.to_csv(output_path, index=False)
            print(f"   -> Success: {len(master_df)} records saved to {output_path}")
        else:
            print("   [!] No data found for this symbol.")

if __name__ == "__main__":
    print("Checking connection to local Theta Terminal...")
    try:
        requests.get("http://127.0.0.1:25520", timeout=2)
        fetch_local_rest()
    except requests.exceptions.ConnectionError:
        print("[!] CRITICAL ERROR: Cannot connect to local terminal.")
        print("Please ensure 'java -jar ThetaTerminalv3.jar' is running in another terminal window.")