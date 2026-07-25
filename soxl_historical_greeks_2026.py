import os
import sys
import time
import pandas as pd
from datetime import date, timedelta
from thetadata import ThetaClient
from dotenv import load_dotenv

# Automatically loads your ThetaData credentials from the .env file
load_dotenv()

def fetch_soxl_options_data():
    print("Authenticating with local Theta Terminal...")
    # Initialize the client. Ensure the local Java Terminal (port 25503) is running.
    client = ThetaClient(
    email='church.ben@gmail.com',
    password='PistisSophia(09',
    dataframe_type='pandas'
)
    
    symbol = 'SOXL'
    
    # Define the 1-year lookback window
    #end_dt = date.today()
    #start_dt = end_dt - timedelta(days=365)
    START_DATE = date(2026, 1, 1) 
    END_DATE = date(2026, 12, 31) 
    print(f"Fetching valid trading dates for {symbol} between {start_dt} and {end_dt}...")
    
    try:
        # Fetch the official list of trading dates from ThetaData
        dates_df = client.stock_list_dates(request_type='quote', symbol=[symbol])
        dates_df['date'] = pd.to_datetime(dates_df['date']).dt.date
        valid_dates = dates_df[(dates_df['date'] >= start_dt) & (dates_df['date'] <= end_dt)]['date'].tolist()
    except Exception as e:
        print(f"Failed to fetch explicit dates from API, falling back to pandas business days. Error: {e}")
        valid_dates = pd.bdate_range(start=start_dt, end=end_dt).date.tolist()

    print(f"Found {len(valid_dates)} trading days. Beginning Inverted Cache Loop...")
    
    all_data = []
    
    # INVERTED CACHE LOOP: Iterate through dates, not expirations.
    for i, current_date in enumerate(valid_dates, 1):
        # The carriage return (\r) updates the same line so your terminal isn't flooded
        sys.stdout.write(f"\rProgress: [{i}/{len(valid_dates)}] Fetching ALL strikes, rights, Greeks & IV for {current_date}...")
        sys.stdout.flush()
        
        try:
            # option_history_greeks_eod automatically returns Pricing, IV, and Greeks
            # expiration='*' (or '') asks the terminal to return the entire chain for that specific day
            daily_df = client.option_history_greeks_eod(
                symbol=symbol,
                start_date=current_date,
                end_date=current_date,
                expiration='*'  
            )
            
            if daily_df is not None and not daily_df.empty:
                # Stamp the dataframe with the trade date for easier time-series modeling
                daily_df['trade_date'] = current_date
                all_data.append(daily_df)
                
        except Exception as e:
            print(f"\nFailed on {current_date} - Error: {str(e)}")
            # We break after one error so it doesn't spam your terminal 250 times
            break
            
        # Micro-delay to avoid HTTP 429 Too Many Requests errors from your local terminal
        time.sleep(0.02)
        
    print("\n\nData download complete! Stitching dataset together...")
    
    if all_data:
        master_df = pd.concat(all_data, ignore_index=True)
        
        # Save to the local environment specified
        output_dir = os.path.expanduser("~/TradingModel")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "SOXL_1Yr_Options_Greeks_EOD.csv")
        
        master_df.to_csv(output_file, index=False)
        print(f"SUCCESS: Saved {len(master_df)} option records to {output_file}")
    else:
        print("[!] No data found. Ensure your Theta Terminal is running, your .env file is formatted properly, and you are on the Standard Tier.")

if __name__ == "__main__":
    fetch_soxl_options_data()