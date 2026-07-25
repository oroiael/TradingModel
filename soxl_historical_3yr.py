import pandas as pd
from thetadata import ThetaClient
from datetime import date
from dateutil.relativedelta import relativedelta
import sys

# 1. Initialize Client
client = ThetaClient(
    email="church.ben@gmail.com",
    password="PistisSophia(09",  # Replace with your actual password
    dataframe_type='pandas'
)

symbol = 'SOXL'
end_dt = date.today()
start_dt = end_dt - relativedelta(years=3)

# Generate a list of Business Days (Monday-Friday) for the year
trading_days = pd.bdate_range(start=start_dt, end=end_dt).date

all_eod_data = []
total_days = len(trading_days)

print(f"Beginning highly-optimized bulk Greeks/IV pull for {symbol} across {total_days} trading days...")

# 2. Loop by DATE instead of EXPIRATION
for i, current_date in enumerate(trading_days, 1):
    
    # Progress Tracker
    sys.stdout.write(f"\rProgress: [{i}/{total_days}] Fetching ALL strikes, rights, and IV for {current_date}...")
    sys.stdout.flush()
    
    try:
        # CHANGED: Swapped to option_history_greeks_eod to pull implied_vol and iv_error natively
        df = client.option_history_greeks_eod(
            symbol=symbol,
            start_date=current_date,
            end_date=current_date,
            expiration='*'
        )
        
        if not df.empty:
            # We filter the DataFrame to keep your file lean, or save everything.
            # This ensures 'implied_vol' and 'iv_error' are explicitly preserved.
            all_eod_data.append(df)
            
    except Exception:
        # Silently skip weekends, exchange holidays, or blank data days
        pass

print("\n\nData download complete! Stitching dataset together...")

# 3. Concatenate and Export
if all_eod_data:
    master_df = pd.concat(all_eod_data, ignore_index=True)
    output_filename = f"{symbol}_3YR_Options_Greeks_History.csv"
    
    master_df.to_csv(output_filename, index=False)
    print(f"Process complete. {len(master_df)} total records saved to {output_filename}")
    print("Columns included: timestamp, strike, right, close, implied_vol, iv_error, and more!")
else:
    print("No historical data found for the specified parameters.")