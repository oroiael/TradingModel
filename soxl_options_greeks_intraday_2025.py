import pandas as pd
from thetadata import ThetaClient
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import os
from dotenv import load_dotenv

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SYMBOL = "SOXL"
TARGET_YEAR = 2025
INTERVAL_MINUTES = 5  # 5-minute bars (used for logging and file naming)
INTERVAL_STR = f"{INTERVAL_MINUTES}m"  # ThetaData API expects string duration format (e.g., '5m')
OUTPUT_DIR = "raw_data"  # Ensure this folder exists

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load environment variables for ThetaData authentication
load_dotenv()
THETADATA_USERNAME = os.getenv("THETADATA_USERNAME")
THETADATA_PASSWORD = os.getenv("THETADATA_PASSWORD")

if not THETADATA_USERNAME or not THETADATA_PASSWORD:
    print("[!] ERROR: THETADATA_USERNAME or THETADATA_PASSWORD not found in .env file.")
    print("Please ensure your .env file exists in the same directory and contains your credentials.")
    exit(1)

# Generate a list of the 1st day of every month in the target year
def generate_monthly_chunks(year):
    months = []
    start_date = date(year, 1, 1)
    
    # We only want to go up to the current date if we are mid-year
    end_of_data = min(date(year, 12, 31), date.today())
    
    current = start_date
    while current <= end_of_data:
        months.append(current)
        current += relativedelta(months=1)
    return months

def fetch_intraday_data():
    print(f"Initializing Intraday Options Fetcher for {SYMBOL} ({TARGET_YEAR})")
    print(f"Interval: {INTERVAL_STR} ({INTERVAL_MINUTES} Minutes)")
    print("-" * 50)
    
    try:
        # Initialize ThetaData client with explicit authentication
        client = ThetaClient(
            email='church.ben@gmail.com', 
            password='PistisSophia(09', 
            dataframe_type='pandas'
        )

        # Get all valid trading days in the database
        print("Fetching valid market dates...")
        raw_dates_response = client.stock_list_dates(
            request_type='trade',
            symbol=SYMBOL
        )
        
        # Bulletproof extraction of the dates
        valid_dates = []
        if isinstance(raw_dates_response, pd.DataFrame):
            date_col = raw_dates_response.columns[0]
            raw_list = raw_dates_response[date_col].tolist()
        elif isinstance(raw_dates_response, pd.Series):
            raw_list = raw_dates_response.tolist()
        else:
            raw_list = list(raw_dates_response)
            
        for d in raw_list:
            d_str = str(d).strip()
            if d_str.lower() != 'date' and d_str != 'None' and d_str != '':
                try:
                    parsed_date = pd.to_datetime(d_str).date()
                    valid_dates.append(parsed_date)
                except Exception:
                    pass
                    
        valid_dates = sorted(list(set(valid_dates)))
        
        if not valid_dates:
            print("[!] ERROR: Could not extract any valid dates from the API response.")
            return

        # Fetch valid option expirations from terminal
        print("Fetching valid option expirations...")
        try:
            raw_exps_response = client.option_list_expirations(symbol=SYMBOL)
        except Exception as e:
            print(f"[!] API ERROR calling option_list_expirations: {e}")
            return
        
        valid_expirations = []
        if isinstance(raw_exps_response, pd.DataFrame) and not raw_exps_response.empty:
            if 'expiration' in raw_exps_response.columns:
                raw_exps = raw_exps_response['expiration'].tolist()
            elif 'exp' in raw_exps_response.columns:
                raw_exps = raw_exps_response['exp'].tolist()
            else:
                col_name = [c for c in raw_exps_response.columns if c.lower() not in ['root', 'symbol', 'ticker']][0]
                raw_exps = raw_exps_response[col_name].tolist()
        elif isinstance(raw_exps_response, pd.Series) and not raw_exps_response.empty:
            raw_exps = raw_exps_response.tolist()
        else:
            raw_exps = list(raw_exps_response)
            
        for e in raw_exps:
            try:
                if isinstance(e, date):
                    valid_expirations.append(e)
                else:
                    e_str = str(e).strip()
                    if len(e_str) == 8 and e_str.isdigit():
                        valid_expirations.append(datetime.strptime(e_str, '%Y%m%d').date())
                    else:
                        valid_expirations.append(pd.to_datetime(e_str).date())
            except Exception:
                pass
                
        valid_expirations = sorted(list(set(valid_expirations)))
        
        if not valid_expirations:
            print("[!] ERROR: Could not extract valid option expirations from terminal.")
            return

        # Create our monthly chunks
        month_starts = generate_monthly_chunks(TARGET_YEAR)
        
        for i in range(len(month_starts)):
            chunk_start = month_starts[i]
            
            if i + 1 < len(month_starts):
                chunk_end = month_starts[i+1] - relativedelta(days=1)
            else:
                chunk_end = min(date(TARGET_YEAR, 12, 31), date.today())
            
            print(f"\nProcessing Chunk: {chunk_start} to {chunk_end}")
            
            chunk_valid_dates = [d for d in valid_dates if chunk_start <= d <= chunk_end]
            
            if not chunk_valid_dates:
                print(" -> No valid trading days in this period. Skipping.")
                continue
            
            actual_start = chunk_valid_dates[0]
            actual_end = chunk_valid_dates[-1]
            
            # Filter expirations relevant to this chunk or target year
            chunk_exps = [exp for exp in valid_expirations if exp >= actual_start and exp.year == TARGET_YEAR]
            
            if not chunk_exps:
                print(" -> No relevant option expirations found for this chunk. Skipping.")
                continue

            for exp_date in chunk_exps:
                output_file = os.path.join(OUTPUT_DIR, f"{SYMBOL}_intraday_{INTERVAL_MINUTES}m_exp_{exp_date.strftime('%Y%m%d')}_{chunk_start.strftime('%Y_%m')}.csv")
                
                if os.path.exists(output_file):
                    print(f" -> File already exists: {output_file}. Skipping to save time.")
                    continue
                    
                print(f" -> Requesting {INTERVAL_MINUTES}-min OHLC data for Expiration: {exp_date}...")
                try:
                    # Pass duration string '5m' (INTERVAL_STR) instead of integer 5 to prevent DuckDB Binder Error
                    df = client.option_history_ohlc(
                        symbol=SYMBOL,
                        start_date=actual_start,
                        end_date=actual_end,
                        expiration=exp_date,
                        interval=INTERVAL_STR 
                    )
                    
                    if df is not None and not df.empty:
                        print(f" -> Success! Received {len(df):,} rows.")
                        print(f" -> Saving to {output_file}...")
                        df.to_csv(output_file, index=False)
                    else:
                        print(f" -> [!] Warning: Received empty dataframe for expiration {exp_date}.")
                        
                except Exception as e:
                    print(f" -> [!] ERROR during request for expiration {exp_date}: {e}")
                
    except Exception as e:
        print(f"\n[!] CRITICAL CONNECTION ERROR: {e}")
        print("Please ensure your local ThetaData Java Terminal is running and credentials are valid.")

if __name__ == "__main__":
    fetch_intraday_data()
    print("\nIntraday fetch complete.")