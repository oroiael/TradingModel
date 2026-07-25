import pandas as pd
import numpy as np
import os

# ==============================================================================
# STRATEGY CONFIGURATION
# ==============================================================================
SYMBOL = "SOXL"
DATA_FILE = f"raw_data/{SYMBOL}_ENGINEERED_DATA.csv"
OUTPUT_FILE = f"raw_data/{SYMBOL}_Trade_Log.csv"

# Trading Rules
MIN_IV_RANK = 1.0       # Only enter when IV Rank is > 50
TARGET_DELTA = 0.40      # Target the 20 Delta Put
TARGET_DTE_MIN = 0      # Minimum days to expiration for entry
TARGET_DTE_MAX = 28     # Maximum days to expiration for entry
TAKE_PROFIT_PCT = 0.25   # Close at 50% max profit
TIME_STOP_DTE = 90      # Close trade when it hits 21 DTE

def find_column(df, possible_names):
    for col in df.columns:
        if col.lower() in possible_names:
            return col
    return None

def run_backtest():
    print(f"Loading {DATA_FILE} into memory...")
    try:
        df = pd.read_csv(DATA_FILE, low_memory=False)
    except FileNotFoundError:
        print(f"[!] Could not find {DATA_FILE}. Check your path.")
        return

    # Dynamically find required columns
    date_col = find_column(df, ['date_parsed', 'date', 'timestamp', 'datadate'])
    exp_col = find_column(df, ['expiration', 'exp', 'exp_parsed'])
    strike_col = find_column(df, ['strike'])
    close_col = find_column(df, ['close', 'mark', 'price']) 
    delta_col = find_column(df, ['delta'])
    right_col = find_column(df, ['right', 'option_type', 'type', 'option_right'])

    print(" -> Parsing dates and aligning timezones...")
    df[date_col] = pd.to_datetime(df[date_col].astype(str), errors='coerce', utc=True)
    df[exp_col] = pd.to_datetime(df[exp_col].astype(str), errors='coerce', utc=True)
    df = df.dropna(subset=[date_col, exp_col])

    df[close_col] = pd.to_numeric(df[close_col], errors='coerce')
    df[delta_col] = pd.to_numeric(df[delta_col], errors='coerce')
    
    # Filter for Puts only
    if right_col:
        df = df[df[right_col].astype(str).str.upper().str.startswith('P')]
    df['Abs_Delta'] = df[delta_col].abs()

    df = df.sort_values(date_col)
    unique_dates = df[date_col].dt.date.unique()

    print(f"Starting simulation across {len(unique_dates)} trading days...")

    trade_log = []
    active_trade = None

    for current_date in unique_dates:
        day_data = df[df[date_col].dt.date == current_date]
        if day_data.empty: continue
        
        current_iv_rank = day_data['IV_Rank'].iloc[0]
        underlying_today = day_data['Underlying_Close'].iloc[0]
        
        # --- 1. MANAGE ACTIVE TRADE ---
        if active_trade is not None:
            # Track DTE securely using the real calendar, ignoring missing data
            current_dte_calendar = (active_trade['Expiration'] - current_date).days
            
            # Find contract (Rounding strike safely to avoid float precision bugs)
            contract_today = day_data[(day_data[exp_col].dt.date == active_trade['Expiration']) & 
                                      (day_data[strike_col].round(2) == round(active_trade['Strike'], 2))]
            
            current_price = None
            if not contract_today.empty:
                cp = contract_today[close_col].iloc[0]
                if pd.notna(cp) and cp > 0:
                    current_price = cp
            
            exit_reason = None
            final_price = None
            
            # CHECK 1: Take Profit (Only if we have a valid market price today)
            if current_price is not None:
                profit_target = active_trade['Entry_Price'] * (1 - TAKE_PROFIT_PCT)
                if current_price <= profit_target:
                    exit_reason = "Take Profit"
                    final_price = current_price
            
            # CHECK 2: Time Stop
            if exit_reason is None and current_dte_calendar <= TIME_STOP_DTE:
                exit_reason = f"Time Stop ({TIME_STOP_DTE} DTE)"
                
            # CHECK 3: Expiration
            if exit_reason is None and current_dte_calendar <= 0:
                exit_reason = "Expiration"
                
            # EXECUTE EXIT
            if exit_reason:
                if final_price is None:
                    if current_price is not None:
                        final_price = current_price
                    else:
                        # FALLBACK: If contract had 0 volume today, calculate actual intrinsic value
                        final_price = max(active_trade['Strike'] - underlying_today, 0)
                        
                pnl = active_trade['Entry_Price'] - final_price # Short selling PnL logic
                
                active_trade.update({
                    'Exit_Date': current_date,
                    'Exit_Price': final_price,
                    'Exit_Reason': exit_reason,
                    'PnL': pnl,
                    'Days_Held': (current_date - active_trade['Entry_Date']).days
                })
                trade_log.append(active_trade)
                active_trade = None

        # --- 2. LOOK FOR NEW ENTRY ---
        if active_trade is None and current_iv_rank >= MIN_IV_RANK:
            # FIX: Force strictly valid prices (>0) and valid deltas
            valid_options = day_data[
                (day_data['DTE'] >= TARGET_DTE_MIN) & 
                (day_data['DTE'] <= TARGET_DTE_MAX) & 
                (day_data[close_col] > 0) & 
                (day_data['Abs_Delta'].notna())
            ].copy()
            
            if not valid_options.empty:
                valid_options['Delta_Diff'] = (valid_options['Abs_Delta'] - TARGET_DELTA).abs()
                best_option = valid_options.loc[valid_options['Delta_Diff'].idxmin()]
                
                active_trade = {
                    'Entry_Date': current_date,
                    'Expiration': best_option[exp_col].date(),
                    'Strike': best_option[strike_col],
                    'Entry_Price': best_option[close_col],
                    'Entry_IV_Rank': current_iv_rank,
                    'Entry_Delta': best_option[delta_col],
                    'Entry_Underlying': underlying_today
                }

    if active_trade is not None:
        print(" -> Dataset ended with an open trade. Dropping it from the log.")

    # --- 3. ANALYZE RESULTS ---
    if trade_log:
        results_df = pd.DataFrame(trade_log)
        results_df.to_csv(OUTPUT_FILE, index=False)
        
        wins = results_df[results_df['PnL'] > 0]
        win_rate = (len(wins) / len(results_df)) * 100
        total_pnl = results_df['PnL'].sum() * 100 # x100 Options Multiplier
        
        print("\n========================================")
        print("BACKTEST RESULTS (1 Contract per Trade)")
        print("========================================")
        print(f"Total Trades: {len(results_df)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Avg Days Held: {results_df['Days_Held'].mean():.1f} days")
        print(f"Total Premium Captured (PnL): ${total_pnl:,.2f}")
        print(f"\nTrade log saved to: {OUTPUT_FILE}")
    else:
        print("\n[!] No trades triggered. The filters might be too strict.")

if __name__ == "__main__":
    run_backtest()