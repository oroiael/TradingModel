import pandas as pd
import numpy as np
import itertools
import sys
import time

print("1. Loading Master Dataset into Memory...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- THE PARAMETER GRID ---
# 4 x 4 x 4 x 4 = 256 Total Combinations
CALL_DTES = [7, 14, 21, 30]
CALL_DELTAS = [0.15, 0.20, 0.25, 0.30]
PUT_DTES = [60, 90, 120, 150]
PUT_DELTAS = [-0.10, -0.15, -0.20, -0.25]

# Generate all possible combinations
grid = list(itertools.product(CALL_DTES, CALL_DELTAS, PUT_DTES, PUT_DELTAS))
total_runs = len(grid)
print(f"2. Grid Search Initialized. Testing {total_runs} combinations...\n")

def run_backtest(target_call_dte, target_call_delta, target_put_dte, target_put_delta):
    current_day_idx = 0
    total_pnl = 0
    capital_required = 0
    wins = 0
    trades = 0
    
    while current_day_idx < len(trading_days) - 1:
        entry_date = trading_days[current_day_idx]
        daily_options = df[df['Date'] == entry_date]
        if daily_options.empty:
            current_day_idx += 1
            continue
            
        underlying_price = daily_options['Underlying_Close'].iloc[0]
        
        # FIND THE CALL
        calls = daily_options[(daily_options['flag'] == 'c') & 
                              (daily_options['DTE'] >= target_call_dte - 3) & 
                              (daily_options['DTE'] <= target_call_dte + 5)].copy()
        if calls.empty:
            current_day_idx += 1
            continue
        calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - target_call_delta)
        best_call = calls.loc[calls['delta_diff'].idxmin()]
        
        # FIND THE PUT
        puts = daily_options[(daily_options['flag'] == 'p') & 
                             (daily_options['DTE'] >= target_put_dte - 10) & 
                             (daily_options['DTE'] <= target_put_dte + 20)].copy()
        if puts.empty:
            current_day_idx += 1
            continue
        puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - target_put_delta)
        best_put = puts.loc[puts['delta_diff'].idxmin()]
        
        # FAST FORWARD TO EXIT DATE
        exit_date_target = best_call['expiration']
        future_days = [d for d in trading_days if d > entry_date and d <= exit_date_target]
        if not future_days:
            break 
            
        exit_date = future_days[-1]
        exit_data = df[df['Date'] == exit_date]
        if exit_data.empty:
            current_day_idx += 1
            continue
            
        exit_underlying = exit_data['Underlying_Close'].iloc[0]
        
        exit_call_data = exit_data[(exit_data['strike'] == best_call['strike']) & 
                                   (exit_data['flag'] == 'c') & 
                                   (exit_data['expiration'] == best_call['expiration'])]
        exit_put_data = exit_data[(exit_data['strike'] == best_put['strike']) & 
                                  (exit_data['flag'] == 'p') & 
                                  (exit_data['expiration'] == best_put['expiration'])]
        
        exit_call_price = exit_call_data['close'].iloc[0] if not exit_call_data.empty else max(0, exit_underlying - best_call['strike'])
        exit_put_price = exit_put_data['close'].iloc[0] if not exit_put_data.empty else max(0, best_put['strike'] - exit_underlying)
        
        # PNL MATH
        stock_pnl = (exit_underlying - underlying_price) * 100
        call_pnl = (best_call['close'] - exit_call_price) * 100  
        put_pnl = (exit_put_price - best_put['close']) * 100     
        
        trade_pnl = stock_pnl + call_pnl + put_pnl
        total_pnl += trade_pnl
        capital_required += (underlying_price * 100) + (best_put['close'] * 100)
        
        trades += 1
        if trade_pnl > 0:
            wins += 1
            
        current_day_idx = trading_days.index(exit_date) + 1
        
    # Return summary stats for this specific combination
    if trades == 0:
        return None
        
    win_rate = (wins / trades) * 100
    avg_return_pct = (total_pnl / capital_required) * 100 if capital_required > 0 else 0
    
    return {
        'Call_DTE': target_call_dte,
        'Call_Delta': target_call_delta,
        'Put_DTE': target_put_dte,
        'Put_Delta': target_put_delta,
        'Total_Trades': trades,
        'Win_Rate_%': round(win_rate, 2),
        'Total_PnL_$': round(total_pnl, 2),
        'Avg_Return_On_Capital_%': round(avg_return_pct, 2)
    }

# --- EXECUTE GRID SEARCH ---
results = []
start_time = time.time()

for i, (c_dte, c_del, p_dte, p_del) in enumerate(grid, 1):
    # Print dynamic progress bar
    sys.stdout.write(f"\rProcessing combination [{i}/{total_runs}] | Call: {c_dte}DTE/{c_del}Δ | Put: {p_dte}DTE/{p_del}Δ ...")
    sys.stdout.flush()
    
    stats = run_backtest(c_dte, c_del, p_dte, p_del)
    if stats:
        results.append(stats)

print(f"\n\nGrid search complete in {round(time.time() - start_time, 1)} seconds.")

# --- RANK AND EXPORT ---
if results:
    results_df = pd.DataFrame(results)
    
    # Sort the dataframe by the highest Total Profit
    ranked_df = results_df.sort_values(by='Total_PnL_$', ascending=False)
    
    output_name = "Collar_Grid_Optimization_Results.csv"
    ranked_df.to_csv(output_name, index=False)
    
    print("\n=== TOP 5 OPTIMAL COMBINATIONS ===")
    print(ranked_df.head(5).to_string(index=False))
    print(f"\nFull ranked scoreboard saved to '{output_name}'")
else:
    print("No valid trades found for any combination.")