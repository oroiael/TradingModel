import pandas as pd
import numpy as np
import os
import gc
import yfinance as yf

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SYMBOLS = ["SOXL", "TQQQ"]
DATA_DIR = "raw_data" # Change to "" if files are in the same folder
LOOKBACK_WINDOW = 252 # 1 Trading Year for IV Rank

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def calculate_historical_volatility(prices_series, window=20):
    """Calculates 20-day annualized historical volatility (HV20)."""
    log_returns = np.log(prices_series / prices_series.shift(1))
    return log_returns.rolling(window=window).std() * np.sqrt(252)

def calculate_iv_rank(iv_series, window=LOOKBACK_WINDOW):
    """Calculates Implied Volatility Rank (IVR) over a rolling window."""
    rolling_min = iv_series.rolling(window=window, min_periods=20).min()
    rolling_max = iv_series.rolling(window=window, min_periods=20).max()
    iv_rank = ((iv_series - rolling_min) / (rolling_max - rolling_min)) * 100
    return iv_rank.fillna(50).clip(0, 100)

def find_column(df, possible_names):
    """Finds a column case-insensitively."""
    for col in df.columns:
        if col.lower() in possible_names:
            return col
    return None

# ==============================================================================
# MAIN ENGINEERING ENGINE
# ==============================================================================
def engineer_features():
    for symbol in SYMBOLS:
        input_file = os.path.join(DATA_DIR, f"{symbol}_MASTER_DATA.csv")
        output_file = os.path.join(DATA_DIR, f"{symbol}_ENGINEERED_DATA.csv")
        
        if not os.path.exists(input_file):
            print(f"[!] Cannot find {input_file}. Skipping.")
            continue
            
        print(f"\n========================================")
        print(f"Engineering Features for {symbol}...")
        print(f"========================================")
        
        print(" -> Loading massive options dataset into RAM...")
        df = pd.read_csv(input_file, low_memory=False)
        
        date_col = find_column(df, ['date', 'quote_date', 'timestamp', 'datadate'])
        exp_col = find_column(df, ['expiration', 'exp'])
        strike_col = find_column(df, ['strike', 'strike_price'])
        iv_col = find_column(df, ['iv', 'implied_vol', 'implied_volatility'])
        
        if not all([date_col, exp_col, strike_col, iv_col]):
            print(f"[!] CRITICAL ERROR: Missing a required column.")
            continue
        
        print(" -> Scrubbing invalid rows and fixing dates...")
        # Convert to pure pandas datetime which safely turns junk into NaT (Not-a-Time)
        parsed_dates = pd.to_datetime(df[date_col].astype(str), errors='coerce', utc=True)
        
        # THE SCRUBBER: Drop any row that resulted in NaT (blank lines, duplicate headers, etc.)
        valid_mask = parsed_dates.notna()
        df = df[valid_mask].copy()
        parsed_dates = parsed_dates[valid_mask]
        
        if df.empty:
            print(" -> [!] ERROR: No valid rows left after scrubbing bad dates.")
            continue
            
        # Safely extract min/max using purely valid datetimes
        min_date = parsed_dates.min().strftime('%Y-%m-%d')
        max_date = parsed_dates.max().strftime('%Y-%m-%d')
        
        # Lock in the clean string format for merging
        df['Date_Parsed'] = parsed_dates.dt.strftime('%Y-%m-%d')
        
        print(f" -> Downloading {symbol} underlying prices from {min_date} to {max_date} via Yahoo Finance...")
        start_fetch = (parsed_dates.min() - pd.Timedelta(days=40)).strftime('%Y-%m-%d')
        end_fetch = (parsed_dates.max() + pd.Timedelta(days=2)).strftime('%Y-%m-%d')
        
        try:
            hist = yf.download(symbol, start=start_fetch, end=end_fetch, progress=False)
            if hist.empty:
                print(f" -> [!] ERROR: Yahoo Finance returned no data.")
                continue
                
            # Safely handle Yahoo's MultiIndex format
            if isinstance(hist.columns, pd.MultiIndex):
                close_prices = hist['Close'][symbol]
            else:
                close_prices = hist['Close']
                
            hist_slim = pd.DataFrame({
                'Date_Parsed': close_prices.index.tz_localize(None).strftime('%Y-%m-%d'),
                'Underlying_Close': close_prices.values
            })
        except Exception as e:
            print(f" -> [!] ERROR during Yahoo Finance fetch: {e}")
            continue
        
        print(" -> Injecting underlying prices into the options chain...")
        df = pd.merge(df, hist_slim, on='Date_Parsed', how='left')
        df['Underlying_Close'] = df['Underlying_Close'].ffill()
        
        print(" -> Calculating Daily ETF Metrics (IV Index & Historical Volatility)...")
        df[iv_col] = pd.to_numeric(df[iv_col], errors='coerce')
        
        daily_summary = df.groupby('Date_Parsed').agg(
            Daily_IV=(iv_col, 'mean'),
            Underlying_Price=('Underlying_Close', 'first')
        ).reset_index()
        
        daily_summary = daily_summary.sort_values('Date_Parsed')
        daily_summary['HV20'] = calculate_historical_volatility(daily_summary['Underlying_Price'])
        daily_summary['IV_Rank'] = calculate_iv_rank(daily_summary['Daily_IV'])
        daily_summary['VRP'] = daily_summary['Daily_IV'] - daily_summary['HV20']
        
        print(" -> Mapping daily metrics back to individual option contracts...")
        metrics_to_merge = daily_summary[['Date_Parsed', 'Daily_IV', 'IV_Rank', 'HV20', 'VRP']]
        df = pd.merge(df, metrics_to_merge, on='Date_Parsed', how='left')
        
        print(" -> Calculating Contract Metrics (Distance to Strike, Days to Expiration)...")
        df[strike_col] = pd.to_numeric(df[strike_col], errors='coerce')
        
        df['exp_parsed'] = pd.to_datetime(df[exp_col].astype(str), errors='coerce', utc=True)
        temp_date = pd.to_datetime(df['Date_Parsed'], utc=True)
        df['DTE'] = (df['exp_parsed'] - temp_date).dt.days
        
        df['Moneyness_Pct'] = ((df[strike_col] - df['Underlying_Close']) / df['Underlying_Close']) * 100
        
        df = df.drop(columns=['Date_Parsed', 'exp_parsed'])
        
        print(f" -> Saving Engineered dataset to {output_file} (Writing to disk)...")
        df.to_csv(output_file, index=False)
        print(f" -> SUCCESS: {symbol} engineering complete.")
        
        del df
        del daily_summary
        gc.collect()

if __name__ == "__main__":
    engineer_features()
    print("\nFeature Engineering Complete. Ready for Phase 3: The Backtester.")