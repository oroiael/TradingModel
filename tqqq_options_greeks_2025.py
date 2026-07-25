import os
import sys
import time
import pandas as pd
from datetime import date
from thetadata import ThetaClient
from dotenv import load_dotenv

# Load your credentials from the .env file in ~/TradingModel
load_dotenv()

def fetch_soxl_options_data():
    print("Authenticating with local Theta Terminal...")
    # Initialize the client. Ensure the local Java Terminal (port 25503) is running.
    client = ThetaClient(
    email='church.ben@gmail.com',
    password='PistisSophia(09',
    dataframe_type='pandas'
    )
    # --- CONFIGURATION ---
    # Change this variable to the year you want to extract
    TARGET_YEAR = 2025 
    SYMBOL = 'TQQQ'
    # ---------------------

    print(f"Authenticating with local Theta Terminal...")
    # Ensure your Theta Terminal (Java app) is running before executing
    #client = ThetaClient(dataframe_type='pandas')
    
    # Define the calendar year window
    start_dt = date(TARGET_YEAR, 1, 1)
    end_dt = date(TARGET_YEAR, 12, 31)
    
    print(f"Fetching valid trading dates for {SYMBOL} for year {TARGET_YEAR}...")
    
    try:
        # Fetch the official list of trading dates from ThetaData
        dates_df = client.stock_list_dates(request_type='quote', symbol=[SYMBOL])
        dates_df['date'] = pd.to_datetime(dates_df['date']).dt.date
        
        # Filter for the specific year
        valid_dates = dates_df[(dates_df['date'] >= start_dt) & (dates_df['date'] <= end_dt)]['date'].tolist()
    except Exception as e:
        print(f"Failed to fetch trading dates from API. Error: {e}")
        return

    if not valid_dates:
        print(f"No trading dates found for {TARGET_YEAR}. Check your input.")
        return

    print(f"Found {len(valid_dates)} trading days. Beginning Inverted Cache Loop...")
    
    all_data = []
    
    # INVERTED CACHE LOOP: Iterate through dates to save RAM/CPU
    for i, current_date in enumerate(valid_dates, 1):
        # Progress counter
        sys.stdout.write(f"\rProgress: [{i}/{len(valid_dates)}] Fetching data for {current_date}...")
        sys.stdout.flush()
        
        try:
            # Fetch EOD Greeks and Prices
            daily_df = client.option_history_greeks_eod(
                symbol=SYMBOL,
                start_date=current_date,
                end_date=current_date,
                expiration='*'  
            )
            
            if daily_df is not None and not daily_df.empty:
                daily_df['trade_date'] = current_date
                all_data.append(daily_df)
                
        except Exception as e:
            # Print error but continue to allow the loop to finish for other days
            print(f"\n[!] Failed on {current_date} - Error: {e}")
            continue
            
        # Small delay to keep the local terminal stable
        time.sleep(0.02)
        
    print("\n\nData download complete! Stitching dataset together...")
    
    if all_data:
        master_df = pd.concat(all_data, ignore_index=True)
        
        # Save to ~/TradingModel
        output_dir = os.path.expanduser("~/TradingModel")
        os.makedirs(output_dir, exist_ok=True)
        
        # File name automatically includes the year
        output_file = os.path.join(output_dir, f"{SYMBOL}_Options_{TARGET_YEAR}.csv")
        
        master_df.to_csv(output_file, index=False)
        print(f"SUCCESS: Saved {len(master_df)} option records to {output_file}")
    else:
        print("[!] No data was collected. Please verify your subscription tier and Theta Terminal status.")

if __name__ == "__main__":
    fetch_soxl_options_data()