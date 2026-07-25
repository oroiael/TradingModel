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

# --- THE FIXED V2 CORE PARAMETERS ---
STARTING_CAPITAL = 100000.0
PUT_TARGET_DTE = 120
PUT_TARGET_DELTA = -0.15
PUT_ROLL_DTE = 21
CALL_TARGET_DTE = 14
CALL_BASE_DELTA = 0.20
CALL_PROFIT_TARGET = 0.80
CALL_DELTA_STOP = 0.50
COOL_OFF_DAYS = 3  # The proven whipsaw killer

# --- THE FINAL OPTIMIZATION GRID ---
PUT_PROFIT_MULTIPLIERS = [1.0, 2.0, 3.0, 4.0]
CALL_TIME_STOPS = [0, 4, 7]  # 0 = hold to expiration, 4/7 = exit early
CALL_RSI_EXITS = [70, 75, 80, 85, 100] # 100 = effectively disabled

grid = list(itertools.product(PUT_PROFIT_MULTIPLIERS, CALL_TIME_STOPS, CALL_RSI_EXITS))
total_runs = len(grid)
cpu_cores = multiprocessing.cpu_count()
print(f"2. Final V2 Factorial. Testing {total_runs} parameter variations across {cpu_cores} CPU Cores...\n")

def run_v2_optimization(params):
    put_mult, call_t_stop, rsi_exit = params
    
    cash = STARTING_CAPITAL
    shares_owned = 0
    active_put = None   
    active_call = None  
    
    peak_portfolio_value = STARTING_CAPITAL
    max_drawdown = 0.0
    trades_executed = 0
    cool_off_counter = 0
    
    for current_date in trading_days:
        daily_chain = df[df['Date'] == current_date]
        if daily_chain.empty: continue
        
        current_underlying = daily_chain['Underlying_Close'].iloc[0]
        current_rsi = daily_chain['RSI_14'].iloc[0] if 'RSI_14' in daily_chain.columns else 50
        
        if cool_off_counter > 0:
            cool_off_counter -= 1
            
        # 1. ANCHOR MANAGEMENT
        if shares_owned == 0 or active_put is None:
            puts = daily_chain[(daily_chain['flag'] == 'p') & (daily_chain['DTE'] >= PUT_TARGET_DTE - 10) & (daily_chain['DTE'] <= PUT_TARGET_DTE + 20)].copy()
            if not puts.empty:
                puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - PUT_TARGET_DELTA)
                target_put = puts.loc[puts['delta_diff'].idxmin()]
                unit_cost = (current_underlying * 100) + (target_put['close'] * 100)
                units_to_buy = int(cash // unit_cost)
                
                if units_to_buy > 0:
                    shares_owned += units_to_buy * 100
                    cash -= (target_put['close'] * 100 * units_to_buy) + (current_underlying * 100 * units_to_buy)
                    active_put = {'strike': target_put['strike'], 'expiration': target_put['expiration'], 'units': units_to_buy, 'entry_price': target_put['close']}

        # 2. HARVESTER ENTRY
        if shares_owned > 0 and active_call is None and cool_off_counter == 0:
            calls = daily_chain[(daily_chain['flag'] == 'c') & (daily_chain['DTE'] >= CALL_TARGET_DTE - 3) & (daily_chain['DTE'] <= CALL_TARGET_DTE + 5)].copy()
            if not calls.empty:
                calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - CALL_BASE_DELTA)
                target_call = calls.loc[calls['delta_diff'].idxmin()]
                calls_to_sell = shares_owned // 100
                cash += (target_call['close'] * 100 * calls_to_sell)
                active_call = {'strike': target_call['strike'], 'expiration': target_call['expiration'], 'units': calls_to_sell, 'entry_price': target_call['close']}
                trades_executed += 1

        # 3. END OF DAY EVALUATION
        current_put_value = 0
        current_call_liability = 0
        
        if active_put is not None:
            put_data = daily_chain[(daily_chain['strike'] == active_put['strike']) & (daily_chain['flag'] == 'p') & (daily_chain['expiration'] == active_put['expiration'])]
            p_price = put_data['close'].iloc[0] if not put_data.empty else max(0, active_put['strike'] - current_underlying)
            current_put_value = p_price * 100 * active_put['units']
            days_to_put_expiry = (active_put['expiration'] - current_date).days
            
            if p_price >= (active_put['entry_price'] * put_mult) or days_to_put_expiry <= PUT_ROLL_DTE or current_date >= active_put['expiration']:
                cash += current_put_value
                active_put = None 
                
        if active_call is not None:
            call_data = daily_chain[(daily_chain['strike'] == active_call['strike']) & (daily_chain['flag'] == 'c') & (daily_chain['expiration'] == active_call['expiration'])]
            c_price = call_data['close'].iloc[0] if not call_data.empty else max(0, current_underlying - active_call['strike'])
            c_delta = call_data['Delta'].iloc[0] if not call_data.empty else 1.0
            current_call_liability = c_price * 100 * active_call['units']
            
            days_to_call_expiry = (active_call['expiration'] - current_date).days
            
            action_taken = False
            was_stopped = False
            
            # The Multi-Factor Exit Matrix
            if c_price <= (active_call['entry_price'] * (1.0 - CALL_PROFIT_TARGET)): 
                action_taken = True
            elif current_rsi >= rsi_exit: 
                action_taken = True
            elif days_to_call_expiry <= call_t_stop or current_date >= active_call['expiration']: 
                action_taken = True
            elif c_delta >= CALL_DELTA_STOP: 
                action_taken = True
                was_stopped = True
                
            if action_taken:
                cash -= current_call_liability
                active_call = None
                if was_stopped:
                    cool_off_counter = COOL_OFF_DAYS

        # 4. MARK TO MARKET
        stock_value = shares_owned * current_underlying
        current_portfolio_value = cash + stock_value + current_put_value - current_call_liability
        
        if current_portfolio_value > peak_portfolio_value: 
            peak_portfolio_value = current_portfolio_value
            
        current_dd = (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value
        if current_dd > max_drawdown: 
            max_drawdown = current_dd

    roi_pct = ((current_portfolio_value - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    
    return {
        'Put_Multiplier': put_mult,
        'Call_Time_Stop_DTE': call_t_stop,
        'Call_RSI_Exit': rsi_exit if rsi_exit != 100 else "Disabled",
        'Harvester_Trades': trades_executed,
        'Max_Drawdown_%': round(max_drawdown * 100, 2),
        'Ending_Capital_$': round(current_portfolio_value, 2),
        'Total_ROI_%': round(roi_pct, 2)
    }

if __name__ == '__main__':
    results = []
    start_time = time.time()
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=cpu_cores) as executor:
        futures = {executor.submit(run_v2_optimization, params): params for params in grid}
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            if completed % 10 == 0 or completed == total_runs:
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
        
        # Sort by best Drawdown first, then by ROI to find the ultimate stability curve
        ranked_df = results_df.sort_values(by=['Max_Drawdown_%', 'Total_ROI_%'], ascending=[True, False])
        
        output_name = "V2_Final_Optimization_Scoreboard.csv"
        ranked_df.to_csv(output_name, index=False)
        
        print("\n=== TOP 5 LOWEST DRAWDOWN / HIGHEST ROI SETUPS ===")
        print(ranked_df.head(5).to_string(index=False))
        print(f"\nFull ranked scoreboard saved to '{output_name}'")