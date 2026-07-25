import pandas as pd
import numpy as np

print("1. Loading Master Dataset...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- OUR PROVEN #1 BASELINE ---
STARTING_CAPITAL = 100000.0
C_DTE = 45
C_DEL = 0.20
P_DTE = 60
P_DEL = -0.20
CALL_TGT = 0.80
PUT_TGT = 2.00

# --- THE NEW ACTIVE MANAGERS ---
# Test different Delta stop-loss levels (0.50 is ATM, 0.70 is deeply ITM)
DELTA_STOPS = [0.40, 0.50, 0.60, 0.70, 1.00] # 1.00 means no stop-loss (our original baseline)

def run_delta_defense(delta_stop):
    portfolio_capital = STARTING_CAPITAL
    current_day_idx = 0
    trades_executed = 0
    wins = 0
    peak_capital = STARTING_CAPITAL
    max_drawdown = 0.0
    
    while current_day_idx < len(trading_days) - 1:
        entry_date = trading_days[current_day_idx]
        daily_options = df[df['Date'] == entry_date]
        if daily_options.empty:
            current_day_idx += 1
            continue
            
        underlying_price = daily_options['Underlying_Close'].iloc[0]
        
        # FIND CONTRACTS
        calls = daily_options[(daily_options['flag'] == 'c') & (daily_options['DTE'] >= C_DTE - 3) & (daily_options['DTE'] <= C_DTE + 5)].copy()
        if calls.empty:
            current_day_idx += 1
            continue
        calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - C_DEL)
        best_call = calls.loc[calls['delta_diff'].idxmin()]
        
        puts = daily_options[(daily_options['flag'] == 'p') & (daily_options['DTE'] >= P_DTE - 10) & (daily_options['DTE'] <= P_DTE + 20)].copy()
        if puts.empty:
            current_day_idx += 1
            continue
        puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - P_DEL)
        best_put = puts.loc[puts['delta_diff'].idxmin()]
        
        unit_cost = (underlying_price * 100) + (best_put['close'] * 100)
        units_to_trade = int(portfolio_capital // unit_cost)
        
        if units_to_trade == 0: break
            
        trade_active = True
        eval_day_idx = current_day_idx + 1
        exit_reason = ""
        
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
            
            # Extract the current Delta of the Call to check for danger
            current_call_delta = curr_call['Delta'].iloc[0] if not curr_call.empty else 1.0
            
            # --- THE DYNAMIC EXIT TRIGGERS ---
            if c_price <= (best_call['close'] * (1.0 - CALL_TGT)): 
                trade_active = False
            elif p_price >= (best_put['close'] * (1.0 + PUT_TGT)): 
                trade_active = False
            elif eval_date >= best_call['expiration']: 
                trade_active = False
            # THE NEW DELTA DEFENSE: Stop out if Delta breaches threshold
            elif current_call_delta >= delta_stop:
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
            
        trade_net = ((exit_underlying - underlying_price) * 100 * units_to_trade) + ((best_call['close'] - exit_call_price) * 100 * units_to_trade) + ((exit_put_price - best_put['close']) * 100 * units_to_trade)     
        portfolio_capital += trade_net
        trades_executed += 1
        if trade_net > 0: wins += 1
            
        if portfolio_capital > peak_capital: peak_capital = portfolio_capital
        current_drawdown = (peak_capital - portfolio_capital) / peak_capital
        if current_drawdown > max_drawdown: max_drawdown = current_drawdown
            
        current_day_idx = trading_days.index(exit_date) + 1
        
    if trades_executed == 0: return None
    return {
        'Call_Delta_Stop': delta_stop if delta_stop != 1.00 else "No Stop (Original Baseline)",
        'Total_Trades': trades_executed,
        'Win_Rate_%': round((wins / trades_executed) * 100, 1),
        'Max_Drawdown_%': round(max_drawdown * 100, 2),
        'Total_ROI_%': round(((portfolio_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100, 2),
        'Ending_Capital_$': round(portfolio_capital, 2)
    }

print("\n2. Testing Dynamic Delta Defense...")
results = []
for stop in DELTA_STOPS:
    res = run_delta_defense(stop)
    if res: results.append(res)

if results:
    results_df = pd.DataFrame(results)
    print("\n=== DELTA DEFENSE SCOREBOARD ===")
    print(results_df.to_string(index=False))