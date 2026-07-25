import pandas as pd
import numpy as np
import os

# ==============================================================================
# STRATEGY 2: REGIME SWITCHING (WITH DURATION TRACKING)
# ==============================================================================
SYMBOL = "SOXL"
STARTING_CAPITAL = 100000.0  

# Regime Switch Toggle 
# TWEAK HERE: Change to 20 for faster regime switching and more trades
TREND_SMA_WINDOW = 20
RISK_FREE_RATE = 0.05 / 252  

# Optional Call Income 
CALL_TARGET_DELTA = 0.10  
# TWEAK HERE: Change MIN to 5 and MAX to 15 to trade rapid "Weeklies"
CALL_DTE_MIN = 14
CALL_DTE_MAX = 45
CALL_TAKE_PROFIT = 0.50   

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

def run_regime_switching():
    print(f"Loading data for Strategy 2 (Regime Switching)...")
    df = load_data()
    if df is None: return

    all_dates = sorted(df['Date_Parsed'].dt.date.unique())
    daily_underlying = df.groupby(df['Date_Parsed'].dt.date)['underlying_close'].first()
    sma_series = daily_underlying.rolling(window=TREND_SMA_WINDOW, min_periods=1).mean()
    sma_dict = sma_series.to_dict()
    
    cash = STARTING_CAPITAL
    shares = 0
    active_call = None
    
    peak_portfolio_value = STARTING_CAPITAL
    max_drawdown = 0.0
    portfolio_log = []
    trade_log = []
    
    print(f"Running simulation over {len(all_dates)} days...")
    
    for current_date in all_dates:
        today_data = df[df['Date_Parsed'].dt.date == current_date]
        if today_data.empty: continue
        
        underlying_price = today_data['underlying_close'].iloc[0]
        current_sma = sma_dict.get(current_date, underlying_price)
        is_uptrend = underlying_price > current_sma
        
        call_price = 0
        
        # ==========================================
        # THE REGIME SWITCH LOGIC
        # ==========================================
        if not is_uptrend:
            # --- BEAR REGIME (LIQUIDATE & GO TO CASH) ---
            if active_call:
                call_market = today_data[(today_data['Expiration'].dt.date == active_call['Expiration']) & 
                                         (today_data['strike'] == active_call['Strike']) & 
                                         (today_data['right'].str.startswith('C'))]
                call_price = call_market['close'].iloc[0] if not call_market.empty and call_market['close'].iloc[0] > 0 else max(underlying_price - active_call['Strike'], 0)
                
                cash -= (call_price * 100 * active_call['Contracts'])
                active_call['Exit_Date'] = current_date
                active_call['Exit_Price'] = call_price
                active_call['Exit_Reason'] = "Regime Switch (Bailout)"
                active_call['PnL'] = (active_call['Entry_Price'] - call_price) * 100 * active_call['Contracts']
                
                # Metric calculation: Days Held
                active_call['Days_Held'] = (current_date - active_call['Entry_Date']).days
                trade_log.append(active_call)
                active_call = None
                call_price = 0

            if shares > 0:
                cash += (shares * underlying_price)
                shares = 0
            
            cash += cash * RISK_FREE_RATE

        else:
            # --- BULL REGIME (BUY SOXL & SELL CALLS) ---
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
                    
                    # Metric calculation: Days Held
                    active_call['Days_Held'] = (current_date - active_call['Entry_Date']).days
                    trade_log.append(active_call)
                    active_call = None
                    call_price = 0 

            affordable_blocks = int(cash // (underlying_price * 100))
            if affordable_blocks > 0:
                new_shares = affordable_blocks * 100
                shares += new_shares
                cash -= (new_shares * underlying_price)
                
            current_contracts = shares // 100

            if not active_call and shares > 0:
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
                    
                    income = best_call['close'] * 100 * current_contracts
                    cash += income
                    call_price = best_call['close'] 
                    active_call = {
                        'Leg': 'Short Call', 'Entry_Date': current_date, 'Expiration': best_call['Expiration'].date(),
                        'Strike': best_call['strike'], 'Entry_Price': best_call['close'], 'Entry_Underlying': underlying_price,
                        'Contracts': current_contracts
                    }

        # TRACK PORTFOLIO & DRAWDOWN
        stock_val = shares * underlying_price
        call_val = (-call_price * 100 * active_call['Contracts']) if active_call else 0
        current_portfolio_value = cash + stock_val + call_val
        
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

    pd.DataFrame(portfolio_log).to_csv("raw_data/V4_Regime_Portfolio.csv", index=False)
    trade_df = pd.DataFrame(trade_log) if trade_log else pd.DataFrame()
    if not trade_df.empty:
        trade_df.to_csv("raw_data/V4_Regime_Trades.csv", index=False)
    
    print("\n========================================")
    print("STRATEGY 2: REGIME SWITCHING RESULTS")
    print("========================================")
    print(f"Final Shares Owned: {shares}")
    if not trade_df.empty:
        calls = trade_df[trade_df['Leg'] == 'Short Call']
        print(f"Short Calls Executed: {len(calls)} | Total Call PnL: ${calls['PnL'].sum():,.2f}")
        
        # New Metric Display
        if len(calls) > 0:
            avg_hold_time = calls['Days_Held'].mean()
            print(f"Average Duration from Entry: {avg_hold_time:.1f} days")
            
    final_val = portfolio_log[-1]['Portfolio_Value'] if portfolio_log else STARTING_CAPITAL
    print(f"Final Portfolio Value: ${final_val:,.2f}")
    print(f"Total ROI: {((final_val - STARTING_CAPITAL)/STARTING_CAPITAL)*100:.2f}%")
    print(f"Max Portfolio Drawdown: {max_drawdown*100:.2f}%")

if __name__ == "__main__":
    run_regime_switching()