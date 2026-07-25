import pandas as pd
import numpy as np

print("1. Loading Master Dataset...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- V2 STRATEGY CORE PARAMETERS ---
STARTING_CAPITAL = 100000.0
PUT_TARGET_DTE, PUT_TARGET_DELTA, PUT_PROFIT_MULTIPLIER, PUT_ROLL_DTE = 120, -0.15, 4.0, 21
CALL_TARGET_DTE, CALL_BASE_DELTA, CALL_PROFIT_TARGET, CALL_DELTA_STOP, CALL_RSI_EXHAUSTION = 14, 0.20, 0.80, 0.50, 80

# --- THE 4 TESTING MODES ---
TEST_MODES = [
    "Baseline (No Controls)",
    "Test 1: Cool-Off Timer (3 Days)",
    "Test 2: RSI Entry Filter (< 70)",
    "Test 3: Dynamic Strike Roll (0.10 Delta)"
]

def run_v2_engine(mode):
    cash = STARTING_CAPITAL
    shares_owned = 0
    active_put = None   
    active_call = None  
    
    peak_portfolio_value = STARTING_CAPITAL
    max_drawdown = 0.0
    trades_executed = 0
    
    # Control State Variables
    cool_off_counter = 0
    last_trade_was_stop = False
    
    for current_date in trading_days:
        daily_chain = df[df['Date'] == current_date]
        if daily_chain.empty: continue
        current_underlying = daily_chain['Underlying_Close'].iloc[0]
        current_rsi = daily_chain['RSI_14'].iloc[0] if 'RSI_14' in daily_chain.columns else 50
        
        # Decrement cool-off timer daily
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

        # 2. HARVESTER ENTRY MANAGEMENT (THE TESTING ARENA)
        if shares_owned > 0 and active_call is None:
            can_enter = True
            target_delta = CALL_BASE_DELTA
            
            # Apply Test 1 Logic
            if mode == "Test 1: Cool-Off Timer (3 Days)" and cool_off_counter > 0:
                can_enter = False
                
            # Apply Test 2 Logic
            if mode == "Test 2: RSI Entry Filter (< 70)" and current_rsi > 70:
                can_enter = False
                
            # Apply Test 3 Logic
            if mode == "Test 3: Dynamic Strike Roll (0.10 Delta)" and last_trade_was_stop:
                target_delta = 0.10 # Roll further out of the money
                
            if can_enter:
                calls = daily_chain[(daily_chain['flag'] == 'c') & (daily_chain['DTE'] >= CALL_TARGET_DTE - 3) & (daily_chain['DTE'] <= CALL_TARGET_DTE + 5)].copy()
                if not calls.empty:
                    calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - target_delta)
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
            
            if p_price >= (active_put['entry_price'] * PUT_PROFIT_MULTIPLIER) or days_to_put_expiry <= PUT_ROLL_DTE or current_date >= active_put['expiration']:
                cash += current_put_value
                active_put = None 
                
        if active_call is not None:
            call_data = daily_chain[(daily_chain['strike'] == active_call['strike']) & (daily_chain['flag'] == 'c') & (daily_chain['expiration'] == active_call['expiration'])]
            c_price = call_data['close'].iloc[0] if not call_data.empty else max(0, current_underlying - active_call['strike'])
            c_delta = call_data['Delta'].iloc[0] if not call_data.empty else 1.0
            current_call_liability = c_price * 100 * active_call['units']
            
            action_taken = False
            was_stopped = False
            
            if c_price <= (active_call['entry_price'] * (1.0 - CALL_PROFIT_TARGET)): action_taken = True
            elif current_rsi >= CALL_RSI_EXHAUSTION: action_taken = True
            elif current_date >= active_call['expiration']: action_taken = True
            elif c_delta >= CALL_DELTA_STOP: 
                action_taken = True
                was_stopped = True
                
            if action_taken:
                cash -= current_call_liability
                active_call = None
                # Update control variables for the next cycle
                if was_stopped:
                    last_trade_was_stop = True
                    cool_off_counter = 3
                else:
                    last_trade_was_stop = False

        # 4. MARK TO MARKET
        stock_value = shares_owned * current_underlying
        current_portfolio_value = cash + stock_value + current_put_value - current_call_liability
        
        if current_portfolio_value > peak_portfolio_value: peak_portfolio_value = current_portfolio_value
        current_dd = (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value
        if current_dd > max_drawdown: max_drawdown = current_dd

    roi_pct = ((current_portfolio_value - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    
    return {
        'Test Mode': mode,
        'Harvester Trades': trades_executed,
        'Max Drawdown %': round(max_drawdown * 100, 2),
        'Ending Capital $': round(current_portfolio_value, 2),
        'Total ROI %': round(roi_pct, 2)
    }

print(f"2. Running {len(TEST_MODES)} Isolated Control Tests...\n")
results = []
for test_mode in TEST_MODES:
    print(f"   Executing {test_mode}...")
    res = run_v2_engine(test_mode)
    results.append(res)

print("\n=== V2 HARVESTER CONTROL SCOREBOARD ===")
results_df = pd.DataFrame(results)
print(results_df.to_string(index=False))