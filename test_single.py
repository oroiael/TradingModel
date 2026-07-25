import pandas as pd
from thetadata import ThetaClient
from datetime import date
from dateutil.relativedelta import relativedelta

# Initialize the Client
client = ThetaClient(
    email="church.ben@gmail.com",
    password="PistisSophia(09", # Replace with your actual password
    dataframe_type='pandas'
)

# 1. Format the start and end dates as YYYYMMDD integers!
start_dt_int = int((date.today() - relativedelta(years=1)).strftime('%Y%m%d'))
end_dt_int = int(date.today().strftime('%Y%m%d'))
exp_dt_int = 20240119 # Jan 19, 2024 formatted as an integer

print("Attempting to fetch a single SOXL contract...")

try:
    test_data = client.option_history_eod(
        symbol='SOXL',
        expiration=exp_dt_int, 
        strike=30,
        right='CALL',
        start_date=start_dt_int,
        end_date=end_dt_int
    )
    print("Success! Data found:")
    print(test_data.head())
    
except Exception as e:
    print("\n==================================")
    print(f"THE EXACT ERROR IS:\n{e}")
    print("==================================\n")