import pandas as pd
import numpy as np
import os

# ==============================================================================
# ASYNCHRONOUS COLLAR CONFIGURATION (AUTO-COMPOUNDING & TREND FILTERED)
# ==============================================================================
SYMBOL = "SOXL"
STARTING_CAPITAL = 100000.0  

# Trend Filter (Only sell calls if Price < SMA)
TREND_SMA_WINDOW = 50

# Short Call Rules (Income Generation)
CALL_TARGET_DELTA = 0.10  # OPTIMIZATION #1: Widened from 0.20 to 0.10
CALL_DTE_MIN = 15
CALL_DTE_MAX = 45
CALL_TAKE_PROFIT = 0.50   

# Long Put Rules (Downside Protection)
PUT_TARGET_DELTA = 0.15   
PUT_DTE_MIN = 60          
PUT_DTE_MAX = 120         
PUT_TIME_STOP = 21        
PUT_TAKE_PROFIT = 3.0     

def load_data():
    file_path = f"raw_data/{SYMBOL}_ENGINEERED_DATA.csv"
    if not os.path.exists(file_path): 
        print(f"ERROR: Cannot find {file_path}")
        return None
        
    df = pd.read_csv(file_path, low_memory=False)
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    date_col = next((c for c in df.columns if c in ['date_parsed', 'date', 'quote_date', 'timestamp']), None)
    exp_col = next((c for c in df.columns if c in ['expiration', 'exp', 'exp_parsed']), None)
    
    if not date_col or not exp_col: return None
    
    df['Date_Parsed'] = pd.to_datetime(df[date_col].astype(str), errors='coerce', utc=True)
    df['Expiration'] = pd.to_datetime(df[exp_col].astype(str), errors='coerce', utc=True)
    
    for col in ['strike', 'close', 'delta', 'underlying_close', 'dte']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
            
    right_col = next((c for c in df.columns if c in ['right', 'option_type', 'type', 'option_right']), None)
    if right_col: df['right'] = df[right_col].astype(str).str.upper()
        
    return df.dropna(subset=['Date_Parsed', 'Expiration'])

def run_collar_analysis():
    print(f"Loading data for Asynchronous Collar Analysis...")
    df = load_data()
    if df is None: return

    all_dates = sorted(df['Date_Parsed'].dt.date.unique())
    
    # Pre-calculate the 50-day SMA for the Trend Filter
    daily_underlying = df.groupby(df['Date_Parsed'].dt.date)['underlying_close'].first()
    sma_series = daily_underlying.rolling(window=TREND_SMA_WINDOW, min_periods=1).mean()
    sma_dict = sma_series.to_dict()
    
    # Portfolio State
    cash = STARTING_CAPITAL
    shares = 0
    active_call = None
    active_put = None
    
    # Drawdown Trackers
    peak_portfolio_value = STARTING_CAPITAL
    max_drawdown = 0.0
    
    portfolio_log = []
    trade_log = []
    
    print(f"Running simulation over {len(all_dates)} days with Trend Filter...")
    
    for current_date in all_dates:
        today_data = df[df['Date_Parsed'].dt.date == current_date]
        if today_data.empty: continue
        
        underlying_price = today_data['underlying_close'].iloc[0]
        current_sma = sma_dict.get(current_date, underlying_price)
        is_uptrend = underlying_price > current_sma
        
        put_price = 0
        call_price = 0
        
        # 1. MANAGE EXITS FIRST
        if active_put:
            put_market = today_data[(today_data['Expiration'].dt.date == active_put['Expiration']) & 
                                    (today_data['strike'] == active_put['Strike']) & 
                                    (today_data['right'].str.startswith('P'))]
            
            put_price = put_market['close'].iloc[0] if not put_market.empty and put_market['close'].iloc[0] > 0 else max(active_put['Strike'] - underlying_price, 0)
            current_dte = (active_put['Expiration'] - current_date).days
            
            exit_reason = None
            if current_dte <= PUT_TIME_STOP: exit_reason = "Time Stop (Roll)"
            elif current_dte <= 0: exit_reason = "Expired"
            elif put_price >= (active_put['Entry_Price'] * PUT_TAKE_PROFIT): exit_reason = "Target Hit (Monetized Hedge)"
            
            if exit_reason:
                cash += (put_price * 100 * active_put['Contracts'])
                active_put['Exit_Date'] = current_date
                active_put['Exit_Price'] = put_price
                active_put['Exit_Reason'] = exit_reason
                active_put['PnL'] = (put_price - active_put['Entry_Price']) * 100 * active_put['Contracts']
                trade_log.append(active_put)
                active_put = None
                put_price = 0 

        if active_call:
            call_market = today_data[(today_data['Expiration'].dt.date == active_call['Expiration']) & 
                                     (today_data['strike'] == active_call['Strike']) & 
                                     (today_data['right'].str.startswith('C'))]
            
            call_price = call_market['close'].iloc[0] if not call_market.empty and call_market['close'].iloc[0] > 0 else max(underlying_price - active_call['Strike'], 0)
            current_dte = (active_call['Expiration'] - current_date).days
            
            exit_reason = None
            if call_price <= (active_call['Entry_Price'] * (1 - CALL_TAKE_PROFIT)): exit_reason = "Take Profit"
            elif current_dte <= 0: exit_reason = "Expired"
            elif call_price > active_call['Entry_Price'] * 3: exit_reason = "Stop Loss (Stock Rallied)" 
            
            if exit_reason:
                cash -= (call_price * 100 * active_call['Contracts'])
                active_call['Exit_Date'] = current_date
                active_call['Exit_Price'] = call_price
                active_call['Exit_Reason'] = exit_reason
                active_call['PnL'] = (active_call['Entry_Price'] - call_price) * 100 * active_call['Contracts']
                trade_log.append(active_call)
                active_call = None
                call_price = 0 

        # 2. INITIALIZE & AUTO-COMPOUND STOCK POSITION
        # NEW RULE: Only sweep cash into new shares if we are in an UPTREND
        if is_uptrend:
            available_for_shares = max(cash * 0.90, 0)
            affordable_blocks = int(available_for_shares // (underlying_price * 100))
            if affordable_blocks > 0:
                new_shares = affordable_blocks * 100
                shares += new_shares
                cash -= (new_shares * underlying_price)
            
        if shares == 0: continue 
        current_contracts = shares // 100
            
        # 3. IDENTIFY NEW OPTION LEGS 
        needs_put = not active_put
        
        # OPTIMIZATION #3: The Trend Filter
        # Only sell a call if we are NOT in an uptrend
        needs_call = not active_call and not is_uptrend 
        
        best_put = None
        best_call = None

        if needs_put:
            valid_puts = today_data[(today_data['right'].str.startswith('P')) & (today_data['close'] > 0)].copy()
            puts_in_window = valid_puts[(valid_puts['dte'] >= PUT_DTE_MIN) & (valid_puts['dte'] <= PUT_DTE_MAX)]
            
            if puts_in_window.empty: 
                puts_in_window = valid_puts[(valid_puts['dte'] >= 30) & (valid_puts['dte'] <= 180)] 
                
            if not puts_in_window.empty:
                if puts_in_window['delta'].notna().any():
                    puts_in_window['delta_diff'] = (puts_in_window['delta'].abs() - PUT_TARGET_DELTA).abs()
                    best_put = puts_in_window.loc[puts_in_window['delta_diff'].idxmin()]
                else:
                    target_strike = underlying_price * 0.85
                    puts_in_window['strike_diff'] = (puts_in_window['strike'] - target_strike).abs()
                    best_put = puts_in_window.loc[puts_in_window['strike_diff'].idxmin()]

        if needs_call:
            valid_calls = today_data[(today_data['dte'] >= CALL_DTE_MIN) & (today_data['dte'] <= CALL_DTE_MAX) & 
                                     (today_data['right'].str.startswith('C')) & (today_data['close'] > 0)].copy()
            if not valid_calls.empty:
                if valid_calls['delta'].notna().any():
                    valid_calls['delta_diff'] = (valid_calls['delta'].abs() - CALL_TARGET_DELTA).abs()
                    best_call = valid_calls.loc[valid_calls['delta_diff'].idxmin()]
                else:
                    target_strike = underlying_price * 1.15
                    valid_calls['strike_diff'] = (valid_calls['strike'] - target_strike).abs()
                    best_call = valid_calls.loc[valid_calls['strike_diff'].idxmin()]

        # THE KILLSWITCH
        if not active_put and best_put is None:
            best_call = None 

        # 4. EXECUTE ENTRIES
        if best_put is not None:
            cost = best_put['close'] * 100 * current_contracts
            cash -= cost 
            put_price = best_put['close'] 
            active_put = {
                'Leg': 'Long Put', 'Entry_Date': current_date, 'Expiration': best_put['Expiration'].date(),
                'Strike': best_put['strike'], 'Entry_Price': best_put['close'], 'Entry_Underlying': underlying_price,
                'Contracts': current_contracts
            }

        if best_call is not None:
            income = best_call['close'] * 100 * current_contracts
            cash += income
            call_price = best_call['close'] 
            active_call = {
                'Leg': 'Short Call', 'Entry_Date': current_date, 'Expiration': best_call['Expiration'].date(),
                'Strike': best_call['strike'], 'Entry_Price': best_call['close'], 'Entry_Underlying': underlying_price,
                'Contracts': current_contracts
            }

        # 5. TRACK PORTFOLIO VALUE & DRAWDOWN
        stock_val = shares * underlying_price
        put_val = (put_price * 100 * active_put['Contracts']) if active_put else 0
        call_val = (-call_price * 100 * active_call['Contracts']) if active_call else 0
        current_portfolio_value = cash + stock_val + put_val + call_val
        
        # Drawdown Logic
        if current_portfolio_value > peak_portfolio_value:
            peak_portfolio_value = current_portfolio_value
            
        daily_drawdown = (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value
        if daily_drawdown > max_drawdown:
            max_drawdown = daily_drawdown
            
        portfolio_log.append({
            'Date': current_date,
            'Underlying_Price': underlying_price,
            'Shares_Owned': shares,
            'Portfolio_Value': current_portfolio_value,
            'Cash': cash
        })

    pd.DataFrame(portfolio_log).to_csv("raw_data/V4_Collar_Portfolio.csv", index=False)
    trade_df = pd.DataFrame(trade_log)
    trade_df.to_csv("raw_data/V4_Collar_Trades.csv", index=False)
    
    puts = trade_df[trade_df['Leg'] == 'Long Put']
    calls = trade_df[trade_df['Leg'] == 'Short Call']
    
    print("\n========================================")
    print("ASYNCHRONOUS COLLAR RESULTS (TREND FILTERED)")
    print("========================================")
    print(f"Final Shares Owned: {shares}")
    print(f"Short Calls Executed: {len(calls)} | Total Call Income: ${calls['PnL'].sum():,.2f}")
    print(f"Long Puts Executed: {len(puts)} | Total Put Cost/Payoff: ${puts['PnL'].sum():,.2f}")
    final_val = portfolio_log[-1]['Portfolio_Value'] if portfolio_log else STARTING_CAPITAL
    print(f"Final Portfolio Value: ${final_val:,.2f}")
    print(f"Total ROI: {((final_val - STARTING_CAPITAL)/STARTING_CAPITAL)*100:.2f}%")
    print(f"Max Portfolio Drawdown: {max_drawdown*100:.2f}%")

if __name__ == "__main__":
    run_collar_analysis()