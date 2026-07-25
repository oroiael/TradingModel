import pandas as pd
from thetadata import ThetaClient
from datetime import date

client = ThetaClient(
    email="church.ben@gmail.com",
    password="YOUR_PASSWORD_HERE", # Replace with your password
    dataframe_type='pandas'
)

symbol = 'SOXL'
exp = date(2024, 1, 19)

print("1. Requesting strikes...")
strikes_df = client.option_list_strikes(symbol=symbol, expiration=exp)
print(f"Found {len(strikes_df)} strikes.")

if not strikes_df.empty:
    # THE REAL FIX: Strip the numpy wrapper and cast exactly to a native Python float
    test_strike = float(strikes_df['strike'].iloc[0])
    print(f"\n2. Requesting EOD History for Strike {test_strike}...")
    
    try:
        eod_data = client.option_history_eod(
            symbol=symbol,
            expiration=exp,
            strike=test_strike,
            right="CALL",  # Using the standard string format
            start_date=date(2023, 1, 1),
            end_date=date.today()
        )
        print(f"\nSUCCESS! Pulled {len(eod_data)} rows of historical pricing:")
        print(eod_data.head())
        
    except Exception as e:
        print(f"\nFailed to pull history. Error: {e}")
else:
    print("\nError: Strikes list returned empty.")