import pandas as pd
import numpy as np

print("1. Loading Master Dataset...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])

# Sort chronologically
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- STRATEGY PARAMETERS ---
# You will change these later to find the "optimal" setup
TARGET_CALL_DTE = 14
TARGET_CALL_DELTA = 0.20
TARGET_PUT_DTE = 90
TARGET_PUT_DELTA = -0.20

print(f"2. Initializing Engine: {TARGET_CALL_DTE}DTE Call / {TARGET_PUT_DTE}DTE Put...")

trades = []
current_day_idx = 0

while current_day_idx < len(trading_days) - 1:
    entry_date = trading_days[current_day_idx]
    daily_options = df[df['Date'] == entry_date]
    
    underlying_price = daily_options['Underlying_Close'].iloc[0]
    
    # --- FIND THE CALL (Short) ---
    calls = daily_options[(daily_options['flag'] == 'c') & (daily_options['DTE'] >= TARGET_CALL_DTE - 3) & (daily_options['DTE'] <= TARGET_CALL_DTE + 5)].copy()
    if calls.empty:
        current_day_idx += 1
        continue
    # Find closest Delta
    calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - TARGET_CALL_DELTA)
    best_call = calls.loc[calls['delta_diff'].idxmin()]
    
    # --- FIND THE PUT (Long) ---
    puts = daily_options[(daily_options['flag'] == 'p') & (daily_options['DTE'] >= TARGET_PUT_DTE - 10) & (daily_options['DTE'] <= TARGET_PUT_DTE + 20)].copy()
    if puts.empty:
        current_day_idx += 1
        continue
    # Puts have negative delta, so we match against -0.20
    puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - TARGET_PUT_DELTA)
    best_put = puts.loc[puts['delta_diff'].idxmin()]
    
    # --- FAST FORWARD TO EXIT DATE ---
    # We exit the entire unit when the short call expires (or closest trading day to it)
    exit_date_target = best_call['expiration']
    
    # Find the actual trading day closest to, but not after, the exit date
    future_days = [d for d in trading_days if d > entry_date and d <= exit_date_target]
    if not future_days:
        break # Reached the end of the dataset
        
    exit_date = future_days[-1]
    exit_data = df[df['Date'] == exit_date]
    
    if exit_data.empty:
        current_day_idx += 1
        continue
        
    exit_underlying = exit_data['Underlying_Close'].iloc[0]
    
    # Find our specific option contracts on the exit date
    exit_call_data = exit_data[(exit_data['strike'] == best_call['strike']) & (exit_data['flag'] == 'c') & (exit_data['expiration'] == best_call['expiration'])]
    exit_put_data = exit_data[(exit_data['strike'] == best_put['strike']) & (exit_data['flag'] == 'p') & (exit_data['expiration'] == best_put['expiration'])]
    
    # If the quotes are missing on the exit day, assume they expired worthless if OTM, or intrinsic value if ITM
    exit_call_price = exit_call_data['close'].iloc[0] if not exit_call_data.empty else max(0, exit_underlying - best_call['strike'])
    exit_put_price = exit_put_data['close'].iloc[0] if not exit_put_data.empty else max(0, best_put['strike'] - exit_underlying)
    
    # --- CALCULATE PNL (Per 100 Shares/1 Contract) ---
    stock_pnl = (exit_underlying - underlying_price) * 100
    call_pnl = (best_call['close'] - exit_call_price) * 100  # We sold this, so entry - exit
    put_pnl = (exit_put_price - best_put['close']) * 100     # We bought this, so exit - entry
    
    total_pnl = stock_pnl + call_pnl + put_pnl
    capital_required = (underlying_price * 100) + (best_put['close'] * 100) # Stock + Put Premium
    return_pct = total_pnl / capital_required
    
    trades.append({
        'Entry Date': entry_date.date(),
        'Exit Date': exit_date.date(),
        'Days Held': (exit_date - entry_date).days,
        'SOXL Entry': underlying_price,
        'Call Strike': best_call['strike'],
        'Put Strike': best_put['strike'],
        'Stock PnL': stock_pnl,
        'Call PnL': call_pnl,
        'Put PnL': put_pnl,
        'Total Trade PnL': total_pnl,
        'Return %': return_pct * 100
    })
    
    # Move to the day after exit to start the next trade
    current_day_idx = trading_days.index(exit_date) + 1

# --- REPORTING ---
results_df = pd.DataFrame(trades)

print("\n=== STRATEGY PERFORMANCE ===")
print(f"Total Trades Executed: {len(results_df)}")
if not results_df.empty:
    wins = len(results_df[results_df['Total Trade PnL'] > 0])
    win_rate = (wins / len(results_df)) * 100
    total_profit = results_df['Total Trade PnL'].sum()
    avg_return_pct = results_df['Return %'].mean()
    
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Total Cumulative PnL: ${total_profit:.2f}")
    print(f"Average Return per Trade: {avg_return_pct:.2f}%")
    
    results_df.to_csv("Collar_Baseline_Results.csv", index=False)
    print("\nDetailed trade log saved to 'Collar_Baseline_Results.csv'")