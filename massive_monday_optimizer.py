import pandas as pd
import numpy as np
import itertools
import time
import concurrent.futures
import multiprocessing
import sys

print("1. Loading Master Dataset into Memory...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- THE MONDAY PARAMETER GRID ---
# Call DTEs perfectly aligned to hit Friday expirations from a Monday entry
CALL_DTES = [4, 11, 18, 25, 32]                     
CALL_DELTAS = [0.10, 0.15, 0.20, 0.25, 0.30]         
PUT_DTES = [60, 90, 120, 150, 180]                     
PUT_DELTAS = [-0.05, -0.10, -0.15, -0.20, -0.25]              
CALL_PROFIT_TARGETS = [0.50, 0.70, 0.80, 0.90, 0.95]  
PUT_PROFIT_TARGETS = [1.0, 2.0, 3.0, 5.0]            

grid = list(itertools.product(
    CALL_DTES, CALL_DELTAS, PUT_DTES, PUT_DELTAS, CALL_PROFIT_TARGETS, PUT_PROFIT_TARGETS
))
total_runs = len(grid)
cpu_cores = multiprocessing.cpu_count()
print(f"2. Monday-Only Full Factorial. Testing {total_runs} permutations across {cpu_cores} CPU Cores...\n")

def run_monday_backtest(params):
    c_dte, c_del, p_dte, p_del, call_tgt, put_tgt = params
    STARTING_CAPITAL = 100000.0
    portfolio_capital = STARTING_CAPITAL
    
    current_day_idx = 0
    trades_executed = 0
    wins = 0
    peak_capital = STARTING_CAPITAL
    max_drawdown = 0.0
    
    while current_day_idx < len(trading_days) - 1:
        entry_date = trading_days[current_day_idx]
        
        # --- THE MONDAY FILTER ---
        if entry_date.weekday() != 0:
            current_day_idx += 1
            continue
            
        daily_options = df[df['Date'] == entry_date]
        if daily_options.empty:
            current_day_idx += 1
            continue
            
        underlying_price = daily_options['Underlying_Close'].iloc[0]
        
        # FIND CONTRACTS (Wider window to catch holidays where Friday expires on Thursday)
        calls = daily_options[(daily_options['flag'] == 'c') & 
                              (daily_options['DTE'] >= c_dte - 2) & (daily_options['DTE'] <= c_dte + 2)].copy()
        if calls.empty:
            current_day_idx += 1
            continue
        calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - c_del)
        best_call = calls.loc[calls['delta_diff'].idxmin()]
        
        puts = daily_options[(daily_options['flag'] == 'p') & 
                             (daily_options['DTE'] >= p_dte - 10) & (daily_options['DTE'] <= p_dte + 20)].copy()
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
            if c_price <= (best_call['close'] * (1.0 - call_tgt)):
                trade_active = False
            elif p_price >= (best_put['close'] * (1.0 + put_tgt)):
                trade_active = False
            elif eval_date >= best_call['expiration']:
                trade_active = False
                
            if not trade_active:
                exit_underlying = current_underlying
                exit_call_price = c_price
                exit_put_price = p_price
                exit_date = eval_date
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
        trades_executed += 1
        
        if trade_net > 0:
            wins += 1
            
        # TRACK DRAWDOWN
        if portfolio_capital > peak_capital:
            peak_capital = portfolio_capital
        
        current_drawdown = (peak_capital - portfolio_capital) / peak_capital
        if current_drawdown > max_drawdown:
            max_drawdown = current_drawdown
            
        current_day_idx = trading_days.index(exit_date) + 1
        
    if trades_executed == 0:
        return None
        
    win_rate = (wins / trades_executed) * 100
    roi_pct = ((portfolio_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    
    return {
        'Call_DTE': c_dte,
        'Call_Delta': c_del,
        'Put_DTE': p_dte,
        'Put_Delta': p_del,
        'Call_Harvest_%': int(call_tgt * 100),
        'Put_Harvest_%': int(put_tgt * 100),
        'Total_Trades': trades_executed,
        'Win_Rate_%': round(win_rate, 2),
        'Max_Drawdown_%': round(max_drawdown * 100, 2),
        'Ending_Capital_$': round(portfolio_capital, 2),
        'Total_ROI_%': round(roi_pct, 2)
    }

# --- EXECUTE MULTI-CORE GRID ---
if __name__ == '__main__':
    results = []
    start_time = time.time()
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=cpu_cores) as executor:
        futures = {executor.submit(run_monday_backtest, params): params for params in grid}
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            if completed % 50 == 0 or completed == total_runs:
                elapsed = time.time() - start_time
                rate = completed / elapsed
                remaining = (total_runs - completed) / rate
                sys.stdout.write(f"\rProgress: {completed}/{total_runs} combinations complete... (Est. {round(remaining/60, 1)} mins remaining)")
                sys.stdout.flush()
                
            try:
                stats = future.result()
                if stats:
                    results.append(stats)
            except Exception as e:
                pass
                
    print(f"\n\nOptimization complete in {round((time.time() - start_time)/60, 2)} minutes.")

    if results:
        results_df = pd.DataFrame(results)
        ranked_df = results_df.sort_values(by='Ending_Capital_$', ascending=False)
        output_name = "Massive_Monday_Optimization_Scoreboard.csv"
        ranked_df.to_csv(output_name, index=False)
        
        print("\n=== TOP 5 MONDAY GLOBAL OPTIMA ===")
        print(ranked_df.head(5).to_string(index=False))
        print(f"\nFull 12,500-row ranked scoreboard saved to '{output_name}'")