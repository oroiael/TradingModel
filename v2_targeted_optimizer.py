import pandas as pd
import numpy as np
import itertools
import concurrent.futures
import sys
import time

# 1. SETUP AND DATA LOADING
print("1. Loading Master Dataset...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# 2. TARGETED GRID CONFIGURATION
# We are optimizing the Harvester's "agile" levers:
# - C_Delta: How aggressive we are with the short call
# - P_Target: How much profit we harvest before rolling
# - D_Stop: At what point we admit defeat and roll the call
CALL_DELTAS = [0.10, 0.15, 0.20, 0.25]
PROFIT_TARGETS = [0.50, 0.70, 0.80, 0.90]
DELTA_STOPS = [0.30, 0.40, 0.50, 0.60]

grid = list(itertools.product(CALL_DELTAS, PROFIT_TARGETS, DELTA_STOPS))
total_runs = len(grid)

# 3. THE V2 ASYNCHRONOUS ENGINE (COMPLETE)
def run_targeted_v2_engine(params):
    c_delta, p_target, d_stop = params
    STARTING_CAPITAL = 100000.0
    cash = STARTING_CAPITAL
    shares_owned, active_put, active_call = 0, None, None
    peak_val, max_dd = STARTING_CAPITAL, 0.0
    cool_off_timer = 0
    
    for current_date in trading_days:
        daily_chain = df[df['Date'] == current_date]
        if daily_chain.empty: continue
        current_underlying = daily_chain['Underlying_Close'].iloc[0]
        
        if cool_off_timer > 0: cool_off_timer -= 1
            
        # ANCHOR MANAGEMENT
        if shares_owned == 0 or active_put is None:
            puts = daily_chain[(daily_chain['flag'] == 'p') & (daily_chain['DTE'] >= 90)].copy()
            if not puts.empty:
                puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - (-0.15))
                target_put = puts.loc[puts['delta_diff'].idxmin()]
                unit_cost = (current_underlying * 100) + (target_put['close'] * 100)
                units_to_buy = int(cash // unit_cost)
                if units_to_buy > 0:
                    shares_owned += units_to_buy * 100
                    cash -= (target_put['close'] * 100 * units_to_buy) + (current_underlying * 100 * units_to_buy)
                    active_put = {'strike': target_put['strike'], 'expiration': target_put['expiration'], 'units': units_to_buy, 'entry_price': target_put['close']}

        # HARVESTER ENTRY
        if shares_owned > 0 and active_call is None and cool_off_timer == 0:
            calls = daily_chain[(daily_chain['flag'] == 'c') & (daily_chain['DTE'] >= 11) & (daily_chain['DTE'] <= 19)].copy()
            if not calls.empty:
                target_call = calls.loc[abs(calls['Delta'] - c_delta).idxmin()]
                calls_to_sell = shares_owned // 100
                cash += (target_call['close'] * 100 * calls_to_sell)
                active_call = {'strike': target_call['strike'], 'expiration': target_call['expiration'], 'units': calls_to_sell, 'entry_price': target_call['close']}

        # EVALUATION
        current_put_val, current_call_liab = 0, 0
        if active_put:
            put_data = daily_chain[(daily_chain['strike'] == active_put['strike']) & (daily_chain['flag'] == 'p')]
            p_price = put_data['close'].iloc[0] if not put_data.empty else max(0, active_put['strike'] - current_underlying)
            current_put_val = p_price * 100 * active_put['units']
            if (active_put['expiration'] - current_date).days <= 21 or current_date >= active_put['expiration']:
                cash += current_put_val
                active_put = None
                
        if active_call:
            call_data = daily_chain[(daily_chain['strike'] == active_call['strike']) & (daily_chain['flag'] == 'c')]
            c_price = call_data['close'].iloc[0] if not call_data.empty else max(0, current_underlying - active_call['strike'])
            c_delta = call_data['Delta'].iloc[0] if not call_data.empty else 1.0
            current_call_liab = c_price * 100 * active_call['units']
            
            if c_price <= (active_call['entry_price'] * (1.0 - p_target)) or c_delta >= d_stop or current_date >= active_call['expiration']:
                cash -= current_call_liab
                active_call = None
                if c_delta >= d_stop: cool_off_timer = 3

        # MTM
        port_val = cash + (shares_owned * current_underlying) + current_put_val - current_call_liab
        if port_val > peak_val: peak_val = port_val
        current_dd = (peak_val - port_val) / peak_val
        if current_dd > max_dd: max_dd = current_dd

    return {'C_Delta': c_delta, 'P_Target': p_target, 'D_Stop': d_stop, 
            'ROI': round(((port_val - STARTING_CAPITAL) / STARTING_CAPITAL) * 100, 2), 
            'Max_DD': round(max_dd * 100, 2)}

# 4. EXECUTION
if __name__ == '__main__':
    print(f"Executing {total_runs} targeted optimizations...")
    results = []
    with concurrent.futures.ProcessPoolExecutor() as executor:
        results = list(executor.map(run_targeted_v2_engine, grid))
    
    results_df = pd.DataFrame(results)
    print("\n=== TARGETED OPTIMIZATION SCOREBOARD (TOP 10 BY ROI) ===")
    print(results_df.sort_values('ROI', ascending=False).head(10).to_string(index=False))