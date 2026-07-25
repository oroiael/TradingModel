import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta

# ==========================================
# FILE PATHS & STRATEGY CONSTANTS
# ==========================================
STOCK_FILE = 'SOXL_5min_3Years.csv'
OPTIONS_FILE = 'SOXL_Master_Cleaned.csv'
INITIAL_CAPITAL = 150000.0
REINVEST_RATE = 0.75
SWEEP_RATE = 0.25

def load_and_prep_data():
    print("--- [1] Loading and Synchronizing Data ---")
    df_stock = pd.read_csv(STOCK_FILE)
    df_stock['Date_Clean'] = df_stock['Date'].astype(str).str.replace(' America/New_York', '', regex=False)
    df_stock['Date'] = pd.to_datetime(df_stock['Date_Clean'], format='%Y%m%d %H:%M:%S', errors='coerce')
    df_stock = df_stock.dropna(subset=['Date']).sort_values(by='Date').reset_index(drop=True)
    
    df_opt = pd.read_csv(OPTIONS_FILE, low_memory=False)
    col_map = {'date': 'trade_date', 'exp': 'expiration', 'strike': 'strike', 
               'bid': 'bid', 'ask': 'ask', 'iv': 'implied_vol', 'right': 'right'}
    
    df_opt[col_map['date']] = pd.to_datetime(df_opt[col_map['date']], errors='coerce')
    df_opt[col_map['exp']] = pd.to_datetime(df_opt[col_map['exp']], errors='coerce')
    
    # Parameter #5: Whole number strikes only
    df_opt = df_opt[df_opt[col_map['strike']] % 1 == 0].copy()
    
    start_date = max(df_stock['Date'].min().date(), df_opt[col_map['date']].min().date())
    end_date = min(df_stock['Date'].max().date(), df_opt[col_map['date']].max().date())
    
    df_stock = df_stock[(df_stock['Date'].dt.date >= start_date) & (df_stock['Date'].dt.date <= end_date)]
    df_opt = df_opt[(df_opt[col_map['date']].dt.date >= start_date) & (df_opt[col_map['date']].dt.date <= end_date)]
    
    print(f"Synchronized Backtest Window: {start_date} to {end_date}")
    return df_stock, df_opt, col_map

def get_execution_price(bid, ask, is_buy=True):
    """Rule #6: 20% above low end of spread for sell, reverse for buy."""
    if pd.isna(bid) or pd.isna(ask) or bid <= 0 or ask <= 0 or ask < bid:
        return None
    spread = ask - bid
    return (ask - 0.20 * spread) if is_buy else (bid + 0.20 * spread)

def run_backtest():
    df_stock, df_opt, col_map = load_and_prep_data()
    
    df_stock['YearWeek'] = df_stock['Date'].dt.strftime('%Y-%U')
    weeks = sorted(df_stock['YearWeek'].unique())
    
    # 3-Legged Portfolio State Machine
    portfolio = {
        'cash': INITIAL_CAPITAL,
        'sweep_cash': 0.0,
        'shares': 0,
        'tax_cost_basis': 0.0,      # Historical cash cost per share
        'active_put': None,
        'active_call': None,
        'prev_week_mon_price': None, # Active weekly baseline for 10% roll evaluation
        'weekly_log': []
    }
    
    print("\n--- [2] Executing Weekly State Machine (v4 Three-Legged Ledger) ---")
    
    for week_idx, week in enumerate(weeks):
        week_bars = df_stock[df_stock['YearWeek'] == week]
        if len(week_bars) == 0:
            continue
            
        week_start_cash = portfolio['cash']
        put_roll_triggered = False
        put_roll_cash = 0.0
        carried_over_shares = portfolio['shares'] > 0
        
        # ------------------------------------------------------------------
        # MONDAY AM EXECUTION (Start of Week)
        # ------------------------------------------------------------------
        first_day = week_bars['Date'].dt.date.min()
        mon_bars = week_bars[(week_bars['Date'].dt.date == first_day) & (week_bars['Date'].dt.time >= time(10, 0))]
        
        if len(mon_bars) == 0:
            continue
        mon_exec_bar = mon_bars.iloc[0]
        mon_date = mon_exec_bar['Date']
        underlying_price = mon_exec_bar['Close']
        daily_chain = df_opt[df_opt[col_map['date']].dt.date == mon_date.date()]
        
        # 1. LEG 3 MANAGEMENT: Evaluate Put Roll-Up (Rule 2.5 & 2.6)
        if portfolio['active_put'] is not None and portfolio['prev_week_mon_price'] is not None:
            price_appreciation = (underlying_price - portfolio['prev_week_mon_price']) / portfolio['prev_week_mon_price']
            if price_appreciation >= 0.10:
                old_put = daily_chain[
                    (daily_chain[col_map['right']] == 'P') & 
                    (daily_chain[col_map['exp']].dt.date == portfolio['active_put']['exp']) &
                    (daily_chain[col_map['strike']] == portfolio['active_put']['strike'])
                ]
                if len(old_put) > 0:
                    sell_price = get_execution_price(old_put.iloc[0][col_map['bid']], old_put.iloc[0][col_map['ask']], is_buy=False)
                    if sell_price:
                        put_roll_cash = sell_price * 100 * (portfolio['shares'] // 100)
                        portfolio['cash'] += put_roll_cash
                portfolio['active_put'] = None # Cleared for roll-up re-purchase below
                put_roll_triggered = True

        # 2. LEG 1 & 3 ALLOCATION: Unified Collar Lot Purchase (Put Priority)
        if portfolio['shares'] == 0:
            target_put_strike = round(underlying_price)
            min_exp = mon_date.date() + timedelta(days=120)
            max_exp = mon_date.date() + timedelta(days=180)
            
            put_options = daily_chain[
                (daily_chain[col_map['right']] == 'P') & 
                (daily_chain[col_map['exp']].dt.date >= min_exp) &
                (daily_chain[col_map['exp']].dt.date <= max_exp)
            ]
            
            put_exec_price = 0.0
            selected_put_exp = None
            selected_put_strike = target_put_strike
            
            if len(put_options) > 0:
                # Nearest neighbor strike search for Long Put
                put_options = put_options.assign(diff=abs(put_options[col_map['strike']] - target_put_strike)).sort_values(by=['diff', col_map['exp']])
                opt = put_options.iloc[0]
                price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=True)
                if price:
                    put_exec_price = price
                    selected_put_strike = opt[col_map['strike']]
                    selected_put_exp = opt[col_map['exp']].date()
            
            # Reinvest 75% cash into 100-share collar units
            unit_cost = (underlying_price * 100) + (put_exec_price * 100)
            invest_amount = portfolio['cash'] * REINVEST_RATE
            lots = int(invest_amount // unit_cost)
            
            if lots > 0:
                new_shares = lots * 100
                share_cost = new_shares * underlying_price
                put_cost = lots * 100 * put_exec_price
                
                portfolio['shares'] += new_shares
                portfolio['cash'] -= (share_cost + put_cost)
                portfolio['tax_cost_basis'] = underlying_price
                
                if put_exec_price > 0:
                    portfolio['active_put'] = {'strike': selected_put_strike, 'premium': put_exec_price, 'exp': selected_put_exp, 'dte': (selected_put_exp - mon_date.date()).days}
        
        # 3. LEG 3 SUPPLEMENTAL: Buy Put if shares carried over but protection rolled or expired
        elif portfolio['active_put'] is None and portfolio['shares'] >= 100:
            target_put_strike = round(underlying_price)
            min_exp = mon_date.date() + timedelta(days=120)
            max_exp = mon_date.date() + timedelta(days=180)
            
            put_options = daily_chain[
                (daily_chain[col_map['right']] == 'P') & 
                (daily_chain[col_map['exp']].dt.date >= min_exp) &
                (daily_chain[col_map['exp']].dt.date <= max_exp)
            ]
            
            if len(put_options) > 0:
                put_options = put_options.assign(diff=abs(put_options[col_map['strike']] - target_put_strike)).sort_values(by=['diff', col_map['exp']])
                opt = put_options.iloc[0]
                exec_price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=True)
                if exec_price:
                    put_cost = exec_price * 100 * (portfolio['shares'] // 100)
                    if portfolio['cash'] >= put_cost:
                        portfolio['cash'] -= put_cost
                        portfolio['active_put'] = {'strike': opt[col_map['strike']], 'premium': exec_price, 'exp': opt[col_map['exp']].date(), 'dte': (opt[col_map['exp']].date() - mon_date.date()).days}

        portfolio['prev_week_mon_price'] = underlying_price

        # 4. LEG 2 MANAGEMENT: Covered Call Writing with Nearest-Neighbor Strike Search
        call_target_strike = round(underlying_price * 1.05) if portfolio['shares'] >= 100 else 0
        call_actual_strike = 0
        call_premium = 0.0
        
        if portfolio['shares'] >= 100 and portfolio['active_call'] is None:
            friday_date = mon_date.date() + timedelta(days=(4 - mon_date.weekday()))
            call_options = daily_chain[
                (daily_chain[col_map['right']] == 'C') & 
                (daily_chain[col_map['exp']].dt.date >= friday_date)
            ]
            
            if len(call_options) > 0:
                # Nearest neighbor search resolves the strike-spacing lockout
                call_options = call_options.assign(diff=abs(call_options[col_map['strike']] - call_target_strike)).sort_values(by=['diff', col_map['exp']])
                opt = call_options.iloc[0]
                exec_price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=False)
                
                if exec_price:
                    call_actual_strike = opt[col_map['strike']]
                    call_premium = exec_price
                    contracts = portfolio['shares'] // 100
                    premium_collected = exec_price * 100 * contracts
                    portfolio['cash'] += premium_collected
                    portfolio['active_call'] = {'strike': call_actual_strike, 'premium': exec_price, 'exp': opt[col_map['exp']].date()}

        # ------------------------------------------------------------------
        # FRIDAY PM EVALUATION (End of Week Clearing)
        # ------------------------------------------------------------------
        last_day = week_bars['Date'].dt.date.max()
        fri_bars = week_bars[(week_bars['Date'].dt.date == last_day) & (week_bars['Date'].dt.time <= time(15, 30))]
        
        if len(fri_bars) == 0:
            continue
        fri_exec_bar = fri_bars.iloc[-1]
        fri_price = fri_exec_bar['Close']
        
        pct_change = (fri_price - underlying_price) / underlying_price
        call_status = "No Call Written"
        stock_realized_pnl = 0.0
        
        # Evaluate Call Leg Settlement
        if portfolio['active_call'] is not None:
            active_strike = portfolio['active_call']['strike']
            
            # TIER 1: ITM Assignment (Stock finishes at or above Call Strike)
            if fri_price >= active_strike:
                call_status = "Assigned ITM - Shares Called Away"
                proceeds = portfolio['shares'] * active_strike
                stock_realized_pnl = proceeds - (portfolio['shares'] * portfolio['tax_cost_basis'])
                
                portfolio['cash'] += proceeds
                
                # Capital Rule 3: Sweep 25% of net realized capital gains
                if stock_realized_pnl > 0:
                    sweep_amt = stock_realized_pnl * SWEEP_RATE
                    portfolio['cash'] -= sweep_amt
                    portfolio['sweep_cash'] += sweep_amt
                
                portfolio['shares'] = 0
                portfolio['tax_cost_basis'] = 0.0
                
            # TIER 2 & 3: OTM Expiration (Shares retained)
            elif pct_change >= 0.00:
                call_status = "Expired OTM - Modest Gain (Shares Retained)"
            else:
                call_status = "Expired OTM - Loss (Shares Retained)"

        portfolio['active_call'] = None # Weekly call cleared
        
        # ------------------------------------------------------------------
        # 3-LEGGED LEDGER ACCOUNTING
        # ------------------------------------------------------------------
        # Leg 1: Stock Value & Unrealized PnL
        stock_val = portfolio['shares'] * fri_price
        stock_unrealized = portfolio['shares'] * (fri_price - portfolio['tax_cost_basis']) if portfolio['shares'] > 0 else 0.0
        
        # Leg 2: Call Realized Cash
        call_realized_cash = (call_premium * 100 * (portfolio['shares'] // 100)) if (call_status != "Assigned ITM - Shares Called Away" and portfolio['shares'] > 0) else 0.0
        if call_status == "Assigned ITM - Shares Called Away":
            # If assigned, previous premium collected is retained as realized gain
            call_realized_cash = call_premium * 100 * ((proceeds // active_strike) // 100)
            
        # Leg 3: Put Metrics
        put_strike = portfolio['active_put']['strike'] if portfolio['active_put'] else 0
        put_dte = portfolio['active_put']['dte'] if portfolio['active_put'] else 0
        put_premium_paid = portfolio['active_put']['premium'] if portfolio['active_put'] else 0.0
        
        # Account Totals
        net_operating_cash_flow = portfolio['cash'] - week_start_cash
        total_equity = portfolio['cash'] + portfolio['sweep_cash'] + stock_val
        
        portfolio['weekly_log'].append({
            'Week': week,
            'Mon_Date': mon_date.strftime('%Y-%m-%d'),
            # Leg 1: Stock
            'Stock_Shares': portfolio['shares'] if call_status != "Assigned ITM - Shares Called Away" else int(proceeds // active_strike),
            'Stock_Tax_Basis': round(portfolio['tax_cost_basis'] if portfolio['tax_cost_basis'] > 0 else underlying_price, 2),
            'Stock_Mon_Open': round(underlying_price, 2),
            'Stock_Fri_Close': round(fri_price, 2),
            'Stock_Weekly_Return_Pct': round(pct_change * 100, 2),
            'Stock_Realized_PnL': round(stock_realized_pnl, 2),
            'Stock_Unrealized_PnL': round(stock_unrealized, 2),
            # Leg 2: Short Call
            'Call_Target_Strike': call_target_strike,
            'Call_Actual_Strike': call_actual_strike,
            'Call_Premium_Collected': round(call_premium, 2),
            'Call_Settlement_Status': call_status,
            'Call_Realized_Cash': round(call_realized_cash, 2),
            # Leg 3: Long Put
            'Put_Active_Strike': put_strike,
            'Put_DTE': put_dte,
            'Put_Premium_Paid': round(put_premium_paid, 2),
            'Put_Roll_Triggered': put_roll_triggered,
            'Put_Realized_Roll_Cash': round(put_roll_cash, 2),
            # Account Ledger Totals
            'Weekly_Net_Operating_Cash_Flow': round(net_operating_cash_flow, 2),
            'Cumulative_Sweep_Account': round(portfolio['sweep_cash'], 2),
            'Total_Mark_to_Market_Equity': round(total_equity, 2)
        })

    print("--- [3] Backtest Complete. Exporting 22-Column Master Ledger ---")
    df_log = pd.DataFrame(portfolio['weekly_log'])
    
    print("\nFinal 5 Weeks Multi-Leg Execution Summary:")
    summary_cols = ['Week', 'Stock_Mon_Open', 'Stock_Fri_Close', 'Call_Actual_Strike', 'Call_Settlement_Status', 'Put_Roll_Triggered', 'Total_Mark_to_Market_Equity']
    print(df_log[summary_cols].tail(5).to_string(index=False))
    
    output_filename = 'SOXL_Strategy_Audit_Trail_v4.csv'
    df_log.to_csv(output_filename, index=False)
    print(f"\nComplete 3-legged master ledger successfully saved to '{output_filename}'.")

if __name__ == "__main__":
    run_backtest()