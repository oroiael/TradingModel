import pandas as pd
import numpy as np

print("1. Loading Master Dataset...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- DATA PREP: INDICATORS ---
all_prices = df[['Date', 'Underlying_Close']].drop_duplicates().set_index('Date')
sma200 = all_prices['Underlying_Close'].rolling(window=200).mean()
daily_returns = all_prices['Underlying_Close'].pct_change()
vol_proxy = daily_returns.rolling(window=20).std()
vol_threshold = vol_proxy.quantile(0.80)

df = df.merge(sma200.rename('SMA200'), on='Date', how='left')
df = df.merge(vol_proxy.rename('VolProxy'), on='Date', how='left')

# --- V2 FIXED CORE ---
STARTING_CAPITAL = 100000.0
PUT_TARGET_DTE, PUT_TARGET_DELTA, PUT_ROLL_DTE = 120, -0.15, 21
CALL_TARGET_DTE, CALL_BASE_DELTA, CALL_PROFIT_TARGET, CALL_DELTA_STOP = 14, 0.20, 0.80, 0.50
COOL_OFF_DAYS = 3

def run_v2_logic_test(mode):
    cash = STARTING_CAPITAL
    shares_owned, active_put, active_call = 0, None, None
    peak_val, max_dd, trades = STARTING_CAPITAL, 0.0, 0
    cool_off_timer = 0
    
    for current_date in trading_days:
        daily_chain = df[df['Date'] == current_date]
        if daily_chain.empty: continue
        current_underlying = daily_chain['Underlying_Close'].iloc[0]
        sma200_val = daily_chain['SMA200'].iloc[0]
        current_vol = daily_chain['VolProxy'].iloc[0]
        
        if cool_off_timer > 0: cool_off_timer -= 1
            
        # 1. ANCHOR MANAGEMENT
        if shares_owned == 0 or active_put is None:
            if mode == "Test A: Market Regime (SMA200)" and current_underlying < sma200_val: continue
            
            allocation_pct = 1.0
            if mode == "Test C: VIX Governor (Volatility)" and current_vol > vol_threshold:
                allocation_pct = 0.5
            elif mode == "Test B: Capital Governor (75%)":
                allocation_pct = 0.75
            
            puts = daily_chain[(daily_chain['flag'] == 'p') & (daily_chain['DTE'] >= 90)].copy()
            if not puts.empty:
                puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - PUT_TARGET_DELTA)
                target_put = puts.loc[puts['delta_diff'].idxmin()]
                
                unit_cost = (current_underlying * 100) + (target_put['close'] * 100)
                units_to_buy = int((cash * allocation_pct) // unit_cost)
                
                if units_to_buy > 0:
                    shares_owned += units_to_buy * 100
                    cash -= (target_put['close'] * 100 * units_to_buy) + (current_underlying * 100 * units_to_buy)
                    active_put = {'strike': target_put['strike'], 'expiration': target_put['expiration'], 'units': units_to_buy, 'entry_price': target_put['close']}

        # 2. HARVESTER ENTRY
        if shares_owned > 0 and active_call is None and cool_off_timer == 0:
            calls = daily_chain[(daily_chain['flag'] == 'c') & (daily_chain['DTE'] >= 11) & (daily_chain['DTE'] <= 19)].copy()
            if not calls.empty:
                target_call = calls.loc[abs(calls['Delta'] - CALL_BASE_DELTA).idxmin()]
                calls_to_sell = shares_owned // 100
                cash += (target_call['close'] * 100 * calls_to_sell)
                active_call = {'strike': target_call['strike'], 'expiration': target_call['expiration'], 'units': calls_to_sell, 'entry_price': target_call['close']}
                trades += 1

        # 3. EVALUATION
        current_put_val, current_call_liab = 0, 0
        
        # DEFENSIVE LOOKUP: Put
        if active_put:
            put_data = daily_chain[(daily_chain['strike'] == active_put['strike']) & (daily_chain['flag'] == 'p') & (daily_chain['expiration'] == active_put['expiration'])]
            if not put_data.empty:
                p_price = put_data['close'].iloc[0]
            else:
                p_price = max(0, active_put['strike'] - current_underlying) # Estimate if missing
            
            current_put_val = p_price * 100 * active_put['units']
            if (active_put['expiration'] - current_date).days <= PUT_ROLL_DTE or current_date >= active_put['expiration']:
                cash += current_put_val
                active_put = None
                
        # DEFENSIVE LOOKUP: Call
        if active_call:
            call_data = daily_chain[(daily_chain['strike'] == active_call['strike']) & (daily_chain['flag'] == 'c') & (daily_chain['expiration'] == active_call['expiration'])]
            if not call_data.empty:
                c_price = call_data['close'].iloc[0]
                c_delta = call_data['Delta'].iloc[0]
            else:
                c_price = max(0, current_underlying - active_call['strike'])
                c_delta = 1.0 # Assume ITM if data missing
            
            current_call_liab = c_price * 100 * active_call['units']
            
            if c_price <= (active_call['entry_price'] * (1.0 - CALL_PROFIT_TARGET)) or c_delta >= CALL_DELTA_STOP or current_date >= active_call['expiration']:
                cash -= current_call_liab
                active_call = None
                if c_delta >= CALL_DELTA_STOP: cool_off_timer = COOL_OFF_DAYS

        # 4. MTM
        port_val = cash + (shares_owned * current_underlying) + current_put_val - current_call_liab
        if port_val > peak_val: peak_val = port_val
        current_dd = (peak_val - port_val) / peak_val
        if current_dd > max_dd: max_dd = current_dd

    roi = ((port_val - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    return {'Mode': mode, 'Max Drawdown %': round(max_dd * 100, 2), 'Total ROI %': round(roi, 2)}

results = [
    run_v2_logic_test("Baseline"), 
    run_v2_logic_test("Test A: Market Regime (SMA200)"), 
    run_v2_logic_test("Test B: Capital Governor (75%)"),
    run_v2_logic_test("Test C: VIX Governor (Volatility)")
]
print("\n=== LOGIC TEST SCOREBOARD ===")
print(pd.DataFrame(results).to_string(index=False))