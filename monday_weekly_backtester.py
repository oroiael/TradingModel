import pandas as pd
import numpy as np

print("1. Loading Master Dataset...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- THE MONDAY WEEKLY PARAMETERS ---
STARTING_CAPITAL = 100000.0
# FIX: Monday to the next Friday is 11 Days. 
TARGET_CALL_DTE = 11        
TARGET_CALL_DELTA = 0.20
TARGET_PUT_DTE = 120       
TARGET_PUT_DELTA = -0.15

portfolio_capital = STARTING_CAPITAL
current_day_idx = 0
trades = []

print("2. Executing Monday-Only Entry Strategy...")

while current_day_idx < len(trading_days) - 1:
    entry_date = trading_days[current_day_idx]
    
    # ONLY ENTER ON MONDAYS
    if entry_date.weekday() != 0:
        current_day_idx += 1
        continue
        
    daily_options = df[df['Date'] == entry_date]
    if daily_options.empty:
        current_day_idx += 1
        continue
        
    underlying_price = daily_options['Underlying_Close'].iloc[0]
    
    # FIND CONTRACTS (Widened the search window slightly to ensure a match)
    calls = daily_options[(daily_options['flag'] == 'c') & (daily_options['DTE'] >= TARGET_CALL_DTE - 3) & (daily_options['DTE'] <= TARGET_CALL_DTE + 3)].copy()
    if calls.empty:
        current_day_idx += 1
        continue
    calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - TARGET_CALL_DELTA)
    best_call = calls.loc[calls['delta_diff'].idxmin()]
    
    puts = daily_options[(daily_options['flag'] == 'p') & (daily_options['DTE'] >= TARGET_PUT_DTE - 10) & (daily_options['DTE'] <= TARGET_PUT_DTE + 20)].copy()
    if puts.empty:
        current_day_idx += 1
        continue
    puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - TARGET_PUT_DELTA)
    best_put = puts.loc[puts['delta_diff'].idxmin()]
    
    unit_cost = (underlying_price * 100) + (best_put['close'] * 100)
    units_to_trade = int(portfolio_capital // unit_cost)
    
    if units_to_trade == 0:
        break
        
    # DAILY STEPPER
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
        
        # Hold until Friday expiration, OR if Put explodes 300% on a crash
        if eval_date >= best_call['expiration']: 
            trade_active = False
        elif p_price >= (best_put['close'] * 4.0): 
            trade_active = False
            
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
    stock_pnl = (exit_underlying - underlying_price) * 100 * units_to_trade
    call_pnl = (best_call['close'] - exit_call_price) * 100 * units_to_trade  
    put_pnl = (exit_put_price - best_put['close']) * 100 * units_to_trade     
    
    trade_net = stock_pnl + call_pnl + put_pnl
    portfolio_capital += trade_net
    
    trades.append({
        'Entry Date': entry_date.date(),
        'Exit Date': exit_date.date(),
        'Days Held': (exit_date - entry_date).days,
        'Stock PnL': stock_pnl,
        'Call PnL': call_pnl,
        'Put PnL': put_pnl,
        'Total Trade PnL': trade_net
    })
    
    current_day_idx = trading_days.index(exit_date) + 1

# --- REPORTING WITH SAFETY NET ---
results_df = pd.DataFrame(trades)

print("\n=== MONDAY-WEEKLY PERFORMANCE ===")
if not results_df.empty:
    wins = len(results_df[results_df['Total Trade PnL'] > 0])
    win_rate = (wins / len(results_df)) * 100
    roi_pct = ((portfolio_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    
    print(f"Total Trades: {len(results_df)}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Ending Capital: ${portfolio_capital:,.2f}")
    print(f"Total ROI: {roi_pct:.2f}%")
else:
    print("0 trades were executed. Check entry filters and dataset dates.")