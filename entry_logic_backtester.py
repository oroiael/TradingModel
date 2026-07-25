import pandas as pd
import numpy as np

print("1. Loading Data and Calculating Technicals...")
# Load options data
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# Extract daily underlying prices for RSI calculation
daily_prices = df[['Date', 'Underlying_Close']].drop_duplicates().sort_values('Date').reset_index(drop=True)

# Calculate 14-Day RSI
delta = daily_prices['Underlying_Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
daily_prices['RSI_14'] = 100 - (100 / (1 + rs))

# Merge RSI back into the master dataset
df = pd.merge(df, daily_prices[['Date', 'RSI_14']], on='Date', how='left')

# --- THE WINNING BASELINES ---
baselines = {
    "Baseline 1 (Aggressive)": {'c_dte': 45, 'c_del': 0.20, 'p_dte': 60, 'p_del': -0.20, 'c_tgt': 0.80, 'p_tgt': 2.0},
    "Baseline 2 (Stability)":  {'c_dte': 21, 'c_del': 0.30, 'p_dte': 120, 'p_del': -0.10, 'c_tgt': 0.90, 'p_tgt': 5.0}
}

# --- THE ENTRY THRESHOLDS TO TEST ---
# 100 means enter immediately (ignore RSI). Lower numbers mean wait for a dip.
RSI_THRESHOLDS = [100, 70, 60, 50, 40] 

def run_filtered_backtest(params, max_rsi):
    c_dte, c_del, p_dte, p_del, call_tgt, put_tgt = params.values()
    STARTING_CAPITAL = 100000.0
    portfolio_capital = STARTING_CAPITAL
    
    current_day_idx = 0
    trades_executed = 0
    wins = 0
    peak_capital = STARTING_CAPITAL
    max_drawdown = 0.0
    
    while current_day_idx < len(trading_days) - 1:
        entry_date = trading_days[current_day_idx]
        daily_options = df[df['Date'] == entry_date]
        
        # --- PHASE 3: THE ENTRY FILTER ---
        current_rsi = daily_options['RSI_14'].iloc[0]
        # If RSI is too high, or RSI is NaN (first 14 days), skip the day and wait.
        if pd.isna(current_rsi) or current_rsi > max_rsi:
            current_day_idx += 1
            continue
            
        underlying_price = daily_options['Underlying_Close'].iloc[0]
        
        # FIND CONTRACTS
        calls = daily_options[(daily_options['flag'] == 'c') & (daily_options['DTE'] >= c_dte - 3) & (daily_options['DTE'] <= c_dte + 5)].copy()
        if calls.empty:
            current_day_idx += 1
            continue
        calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - c_del)
        best_call = calls.loc[calls['delta_diff'].idxmin()]
        
        puts = daily_options[(daily_options['flag'] == 'p') & (daily_options['DTE'] >= p_dte - 10) & (daily_options['DTE'] <= p_dte + 20)].copy()
        if puts.empty:
            current_day_idx += 1
            continue
        puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - p_del)
        best_put = puts.loc[puts['delta_diff'].idxmin()]
        
        # POSITION SIZING
        unit_cost = (underlying_price * 100) + (best_put['close'] * 100)
        units_to_trade = int(portfolio_capital // unit_cost)
        
        if units_to_trade == 0:
            break
            
        # DAILY STEPPER LOOP
        trade_active = True
        eval_day_idx = current_day_idx + 1
        
        while trade_active and eval_day_idx < len(trading_days):
            eval_date = trading_days[eval_day_idx]
            eval_data = df[df['Date'] == eval_date]
            if eval_data.empty:
                eval_day_idx += 1
                continue
                
            current_underlying = eval_data['Underlying_Close'].iloc[0]
            curr_call = eval_data[(eval_data['strike'] == best_call['strike']) & (eval_data['flag'] == 'c') & (eval_data['expiration'] == best_call['expiration'])]
            curr_put = eval_data[(eval_data['strike'] == best_put['strike']) & (eval_data['flag'] == 'p') & (eval_data['expiration'] == best_put['expiration'])]
            
            c_price = curr_call['close'].iloc[0] if not curr_call.empty else max(0, current_underlying - best_call['strike'])
            p_price = curr_put['close'].iloc[0] if not curr_put.empty else max(0, best_put['strike'] - current_underlying)
            
            # HARVESTING TRIGGERS
            if c_price <= (best_call['close'] * (1.0 - call_tgt)): trade_active = False
            elif p_price >= (best_put['close'] * (1.0 + put_tgt)): trade_active = False
            elif eval_date >= best_call['expiration']: trade_active = False
                
            if not trade_active:
                exit_underlying, exit_call_price, exit_put_price, exit_date = current_underlying, c_price, p_price, eval_date
            else:
                eval_day_idx += 1
                
        if trade_active: 
            exit_date = trading_days[-1]
            exit_underlying = df[df['Date'] == exit_date]['Underlying_Close'].iloc[0]
            exit_call_price = max(0, exit_underlying - best_call['strike'])
            exit_put_price = max(0, best_put['strike'] - exit_underlying)
            
        # PNL MATH
        trade_net = ((exit_underlying - underlying_price) * 100 * units_to_trade) + ((best_call['close'] - exit_call_price) * 100 * units_to_trade) + ((exit_put_price - best_put['close']) * 100 * units_to_trade)     
        portfolio_capital += trade_net
        trades_executed += 1
        if trade_net > 0: wins += 1
            
        # TRACK DRAWDOWN
        if portfolio_capital > peak_capital: peak_capital = portfolio_capital
        current_drawdown = (peak_capital - portfolio_capital) / peak_capital
        if current_drawdown > max_drawdown: max_drawdown = current_drawdown
            
        current_day_idx = trading_days.index(exit_date) + 1
        
    if trades_executed == 0: return None
    return {
        'Max_RSI_Entry': max_rsi if max_rsi != 100 else "Always In",
        'Total_Trades': trades_executed,
        'Win_Rate_%': round((wins / trades_executed) * 100, 1),
        'Max_Drawdown_%': round(max_drawdown * 100, 2),
        'Ending_Capital_$': round(portfolio_capital, 2),
        'Total_ROI_%': round(((portfolio_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100, 2)
    }

print("\n2. Testing Entry Logic...")
all_results = []
for name, params in baselines.items():
    for rsi in RSI_THRESHOLDS:
        res = run_filtered_backtest(params, rsi)
        if res:
            res['Baseline'] = name
            all_results.append(res)

if all_results:
    results_df = pd.DataFrame(all_results)
    results_df = results_df[['Baseline', 'Max_RSI_Entry', 'Total_Trades', 'Win_Rate_%', 'Max_Drawdown_%', 'Total_ROI_%', 'Ending_Capital_$']]
    
    print("\n=== ENTRY LOGIC SCOREBOARD ===")
    print(results_df.to_string(index=False))