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
    
    # Filter whole number strikes (Rule #5)
    df_opt = df_opt[df_opt[col_map['strike']] % 1 == 0].copy()
    
    start_date = max(df_stock['Date'].min().date(), df_opt[col_map['date']].min().date())
    end_date = min(df_stock['Date'].max().date(), df_opt[col_map['date']].max().date())
    
    df_stock = df_stock[(df_stock['Date'].dt.date >= start_date) & (df_stock['Date'].dt.date <= end_date)]
    df_opt = df_opt[(df_opt[col_map['date']].dt.date >= start_date) & (df_opt[col_map['date']].dt.date <= end_date)]
    
    print(f"Synchronized Window: {start_date} to {end_date}")
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
    
    portfolio = {
        'cash': INITIAL_CAPITAL,
        'sweep_cash': 0.0,
        'shares': 0,
        'tax_cost_basis': 0.0,
        'active_put': None,
        'active_call': None,
        'prev_week_mon_price': None,
        'weekly_log': []
    }
    
    print("\n--- [2] Executing Strategy ---")
    
    for week_idx, week in enumerate(weeks):
        week_bars = df_stock[df_stock['YearWeek'] == week]
        if len(week_bars) == 0:
            continue
            
        week_start_cash = portfolio['cash']
        put_roll_triggered = False
        put_roll_cash = 0.0
        call_row_id = "N/A"
        put_row_id = "N/A"
        
        # ------------------------------------------------------------------
        # MONDAY AM EXECUTION (10:00 AM)
        # ------------------------------------------------------------------
        first_day = week_bars['Date'].dt.date.min()
        mon_bars = week_bars[(week_bars['Date'].dt.date == first_day) & (week_bars['Date'].dt.time >= time(10, 0))]
        if len(mon_bars) == 0:
            continue
            
        mon_exec_bar = mon_bars.iloc[0]
        mon_date = mon_exec_bar['Date']
        underlying_price = mon_exec_bar['Close']
        daily_chain = df_opt[df_opt[col_map['date']].dt.date == mon_date.date()]
        
        # Diagnostic print for Week 00 to audit raw chain availability
        if week_idx == 0:
            print(f"\n[WEEK 00 AUDIT] Mon Date: {mon_date.date()}, Underlying: ${underlying_price:.2f}")
            print(f"[WEEK 00 AUDIT] Total option rows available for this date in CSV: {len(daily_chain)}")

        # 1. Evaluate Put Roll-Up (Rule 2.5)
        if portfolio['active_put'] is not None and portfolio['prev_week_mon_price'] is not None:
            if (underlying_price - portfolio['prev_week_mon_price']) / portfolio['prev_week_mon_price'] >= 0.10:
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
                portfolio['active_put'] = None
                put_roll_triggered = True

        # 2. Independent Stock Purchase (Leg 1)
        if portfolio['shares'] == 0:
            invest_amount = portfolio['cash'] * REINVEST_RATE
            new_shares = int(invest_amount // underlying_price)
            new_shares = (new_shares // 100) * 100  # Maintain 100-share lots for option contracts
            if new_shares > 0:
                cost = new_shares * underlying_price
                portfolio['shares'] += new_shares
                portfolio['cash'] -= cost
                portfolio['tax_cost_basis'] = underlying_price

        # 3. Independent Long Put Purchase (Leg 3) - 120 to 180 DTE
        if portfolio['active_put'] is None and portfolio['shares'] >= 100:
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
                for idx, opt in put_options.iterrows():
                    price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=True)
                    if price and (portfolio['cash'] >= price * 100 * (portfolio['shares'] // 100)):
                        put_cost = price * 100 * (portfolio['shares'] // 100)
                        portfolio['cash'] -= put_cost
                        portfolio['active_put'] = {'strike': opt[col_map['strike']], 'premium': price, 'exp': opt[col_map['exp']].date(), 'dte': (opt[col_map['exp']].date() - mon_date.date()).days}
                        put_row_id = str(idx)
                        break

        portfolio['prev_week_mon_price'] = underlying_price

        # 4. Independent Covered Call Writing (Leg 2) - ~5% Above Current Price
        call_target_strike = round(underlying_price * 1.05) if portfolio['shares'] >= 100 else 0
        call_actual_strike = 0
        call_premium = 0.0
        
        if portfolio['shares'] >= 100 and portfolio['active_call'] is None:
            # Find nearest Friday expiration
            friday_date = mon_date.date() + timedelta(days=(4 - mon_date.weekday()))
            call_options = daily_chain[
                (daily_chain[col_map['right']] == 'C') & 
                (daily_chain[col_map['exp']].dt.date >= friday_date)
            ]
            if len(call_options) > 0:
                call_options = call_options.assign(diff=abs(call_options[col_map['strike']] - call_target_strike)).sort_values(by=['diff', col_map['exp']])
                for idx, opt in call_options.iterrows():
                    exec_price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=False)
                    if exec_price:
                        call_actual_strike = opt[col_map['strike']]
                        call_premium = exec_price
                        contracts = portfolio['shares'] // 100
                        portfolio['cash'] += exec_price * 100 * contracts
                        portfolio['active_call'] = {'strike': call_actual_strike, 'premium': exec_price, 'exp': opt[col_map['exp']].date()}
                        call_row_id = str(idx)
                        break
                        
            if week_idx == 0:
                print(f"[WEEK 00 AUDIT] Call Written: Strike ${call_actual_strike}, Premium: ${call_premium:.2f}, CSV Row ID: {call_row_id}")

        # ------------------------------------------------------------------
        # FRIDAY PM EVALUATION (3:30 PM)
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
        proceeds = 0.0
        
        # Literal Rules Enforcement: Positive Week = Assignment/Exercise, Negative Week = Expiration/Carry
        if portfolio['active_call'] is not None:
            active_strike = portfolio['active_call']['strike']
            if pct_change >= 0.00:  # Any gain triggers assignment/exercise per literal instructions
                call_status = "Assigned (Positive Return)"
                proceeds = portfolio['shares'] * active_strike
                stock_realized_pnl = proceeds - (portfolio['shares'] * portfolio['tax_cost_basis'])
                portfolio['cash'] += proceeds
                
                # Rule Capital 3: Sweep 25% of net cash generated
                if stock_realized_pnl > 0:
                    sweep_amt = stock_realized_pnl * SWEEP_RATE
                    portfolio['cash'] -= sweep_amt
                    portfolio['sweep_cash'] += sweep_amt
                    
                portfolio['shares'] = 0
                portfolio['tax_cost_basis'] = 0.0
            else:
                call_status = "Expired (Negative Return - Shares Carried Over)"

        portfolio['active_call'] = None

        # ------------------------------------------------------------------
        # LOGGING & AUDIT TRAIL
        # ------------------------------------------------------------------
        stock_val = portfolio['shares'] * fri_price
        stock_unrealized = portfolio['shares'] * (fri_price - portfolio['tax_cost_basis']) if portfolio['shares'] > 0 else 0.0
        
        call_realized_cash = (call_premium * 100 * (portfolio['shares'] // 100)) if (call_status != "Assigned (Positive Return)" and portfolio['shares'] > 0) else 0.0
        if call_status == "Assigned (Positive Return)":
            call_realized_cash = call_premium * 100 * ((proceeds // active_strike) // 100)
            
        put_strike = portfolio['active_put']['strike'] if portfolio['active_put'] else 0
        put_dte = portfolio['active_put']['dte'] if portfolio['active_put'] else 0
        put_premium_paid = portfolio['active_put']['premium'] if portfolio['active_put'] else 0.0
        
        portfolio['weekly_log'].append({
            'Week': week,
            'Mon_Date': mon_date.strftime('%Y-%m-%d'),
            'Stock_Shares': portfolio['shares'] if call_status != "Assigned (Positive Return)" else int(proceeds // active_strike),
            'Stock_Tax_Basis': round(portfolio['tax_cost_basis'] if portfolio['tax_cost_basis'] > 0 else underlying_price, 2),
            'Stock_Mon_Open': round(underlying_price, 2),
            'Stock_Fri_Close': round(fri_price, 2),
            'Stock_Weekly_Return_Pct': round(pct_change * 100, 2),
            'Stock_Realized_PnL': round(stock_realized_pnl, 2),
            'Stock_Unrealized_PnL': round(stock_unrealized, 2),
            'Call_Target_Strike': call_target_strike,
            'Call_Actual_Strike': call_actual_strike,
            'Call_Premium_Collected': round(call_premium, 2),
            'Call_CSV_Row_ID': call_row_id,
            'Call_Settlement_Status': call_status,
            'Call_Realized_Cash': round(call_realized_cash, 2),
            'Put_Active_Strike': put_strike,
            'Put_DTE': put_dte,
            'Put_Premium_Paid': round(put_premium_paid, 2),
            'Put_CSV_Row_ID': put_row_id,
            'Put_Roll_Triggered': put_roll_triggered,
            'Put_Realized_Roll_Cash': round(put_roll_cash, 2),
            'Weekly_Net_Operating_Cash_Flow': round(portfolio['cash'] - week_start_cash, 2),
            'Cumulative_Sweep_Account': round(portfolio['sweep_cash'], 2),
            'Total_Mark_to_Market_Equity': round(portfolio['cash'] + portfolio['sweep_cash'] + stock_val, 2)
        })

    print("\n--- [3] Exporting Verified Ledger ---")
    df_log = pd.DataFrame(portfolio['weekly_log'])
    
    print("\nFirst 5 Weeks Execution Summary (Notice Week 00 and CSV Row IDs):")
    summary_cols = ['Week', 'Stock_Mon_Open', 'Stock_Fri_Close', 'Call_Actual_Strike', 'Call_CSV_Row_ID', 'Call_Settlement_Status']
    print(df_log[summary_cols].head(5).to_string(index=False))
    
    output_filename = 'SOXL_Strategy_Audit_Trail_v5.csv'
    df_log.to_csv(output_filename, index=False)
    print(f"\nSaved to '{output_filename}'.")

if __name__ == "__main__":
    run_backtest()