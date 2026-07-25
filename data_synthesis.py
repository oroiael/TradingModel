import pandas as pd
import numpy as np
import py_vollib.black_scholes_merton.implied_volatility as iv
import py_vollib.black_scholes_merton.greeks.analytical as greeks

print("1. Loading IBKR Underlying Data...")
ibkr_df = pd.read_csv("SOXL_IBKR_1YR_EOD.csv")
ibkr_df['Date'] = pd.to_datetime(ibkr_df['Date']).dt.normalize()
underlying_df = ibkr_df[['Date', 'Close']].rename(columns={'Close': 'Underlying_Close'})

print("2. Loading Theta Data Options History...")
opt_df = pd.read_csv("SOXL_1YR_Options_History.csv")
print("   Parsing timestamps...")
opt_df['Date'] = pd.to_datetime(opt_df['created'], format='mixed', utc=True).dt.tz_localize(None).dt.normalize()
opt_df['expiration'] = pd.to_datetime(opt_df['expiration'], format='mixed', utc=True).dt.tz_localize(None).dt.normalize()
opt_df = opt_df.dropna(subset=['Date', 'expiration'])

print("3. Merging datasets on Trade Date...")
master_df = pd.merge(opt_df, underlying_df, on='Date', how='inner')
print(f"   Successfully matched {len(master_df)} option records.")

print("4. Sanitizing Data...")
master_df['close'] = pd.to_numeric(master_df['close'], errors='coerce')
master_df['strike'] = pd.to_numeric(master_df['strike'], errors='coerce')
master_df['Underlying_Close'] = pd.to_numeric(master_df['Underlying_Close'], errors='coerce')
master_df = master_df.dropna(subset=['close', 'strike', 'Underlying_Close'])
master_df = master_df[(master_df['close'] > 0.0) & (master_df['Underlying_Close'] > 0.0)]

print("5. Engineering Base Features...")
master_df['DTE'] = (master_df['expiration'] - master_df['Date']).dt.days
master_df = master_df[master_df['DTE'] > 0].copy()
master_df['Time_to_Expiry_Years'] = master_df['DTE'] / 365.0
master_df['Moneyness'] = master_df['strike'] / master_df['Underlying_Close']
master_df['flag'] = master_df['right'].str.lower().str[0]

print("6. Executing Stable Black-Scholes Engine (IV & Delta)...")
risk_free_rate = 0.05 

# Create safe scalar functions that CANNOT crash the script
def safe_iv(price, S, K, t, flag):
    try:
        # Pre-filter impossible intrinsic values
        if flag == 'c' and price < (S - K): return np.nan
        if flag == 'p' and price < (K - S): return np.nan
        return iv.implied_volatility(price, S, K, t, risk_free_rate, 0.0, flag)
    except:
        return np.nan

def safe_delta(flag, S, K, t, sigma):
    try:
        if np.isnan(sigma) or sigma <= 0.0: return np.nan
        return greeks.delta(flag, S, K, t, risk_free_rate, 0.0, sigma)
    except:
        return np.nan

# Vectorize the safe functions natively in C via NumPy
vec_iv = np.vectorize(safe_iv)
vec_delta = np.vectorize(safe_delta)

# Apply to dataframe columns
master_df['IV'] = vec_iv(
    master_df['close'], 
    master_df['Underlying_Close'], 
    master_df['strike'], 
    master_df['Time_to_Expiry_Years'], 
    master_df['flag']
)

master_df['Delta'] = vec_delta(
    master_df['flag'],
    master_df['Underlying_Close'],
    master_df['strike'],
    master_df['Time_to_Expiry_Years'],
    master_df['IV']
)

print("7. Finalizing...")
# Drop any rows where the quote was stale/invalid and resulted in a NaN calculation
master_df = master_df.dropna(subset=['IV', 'Delta'])
output_name = "Master_Backtest_Data_SOXL.csv"
master_df.to_csv(output_name, index=False)
print(f"\nSynthesis Complete! {len(master_df)} pristine options records saved to {output_name}.")