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
    
    portfolio = {
        'cash': INITIAL_CAPITAL,
        'sweep_cash': 0.0,
        'shares': 0,
        'share_cost_basis': 0.0,
        'active_put': None,
        'active_call': None,
        'prev_week_entry_price': None,
        'weekly_log': []
    }
    
    print("\n--- [2] Executing Weekly State Machine (v3 Corrected Architecture) ---")
    
    for week_idx, week in enumerate(weeks):
        week_bars = df_stock[df_stock['YearWeek'] == week]
        if len(week_bars) == 0:
            continue
            
        # Track starting operating cash for exact weekly realized cash flow reporting
        week_start_cash = portfolio['cash']
        put_roll_triggered = False
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
        
        # 1. Evaluate Put Roll-Up (Rule 2.5)
        if portfolio['active_put'] is not None and portfolio['prev_week_entry_price'] is not None:
            price_appreciation = (underlying_price - portfolio['prev_week_entry_price']) / portfolio['prev_week_entry_price']
            if price_appreciation >= 0.10:
                old_put = daily_chain[
                    (daily_chain[col_map['right']] == 'P') & 
                    (daily_chain[col_map['exp']].dt.date == portfolio['active_put']['exp']) &
                    (daily_chain[col_map['strike']] == portfolio['active_put']['strike'])
                ]
                if len(old_put) > 0:
                    sell_price = get_execution_price(old_put.iloc[0][col_map['bid']], old_put.iloc[0][col_map['ask']], is_buy=False)
                    if sell_price:
                        portfolio['cash'] += sell_price * 100 * (portfolio['shares'] // 100)
                portfolio['active_put'] = None
                put_roll_triggered = True

        # 2. Unified Collar Lot Allocation (Put Priority Rule)
        if portfolio['shares'] == 0:
            target_put_strike = round(underlying_price)
            min_exp = mon_date.date() + timedelta(days=120)
            max_exp = mon_date.date() + timedelta(days=180)
            
            put_options = daily_chain[
                (daily_chain[col_map['right']] == 'P') & 
                (daily_chain[col_map['exp']].dt.date >= min_exp) &
                (daily_chain[col_map['exp']].dt.date <= max_exp) &
                (daily_chain[col_map['strike']] == target_put_strike)
            ].sort_values(by=col_map['exp'])
            
            put_exec_price = 0.0
            selected_put_exp = None
            if len(put_options) > 0:
                opt = put_options.iloc[0]
                price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=True)
                if price:
                    put_exec_price = price
                    selected_put_exp = opt[col_map['exp']].date()
            
            # Combine share price + put premium into a unified 100-share unit cost
            unit_cost = (underlying_price * 100) + (put_exec_price * 100)
            invest_amount = portfolio['cash'] * REINVEST_RATE
            lots = int(invest_amount // unit_cost)
            
            if lots > 0:
                new_shares = lots * 100
                share_cost = new_shares * underlying_price
                put_cost = lots * 100 * put_exec_price
                
                portfolio['shares'] += new_shares
                portfolio['cash'] -= (share_cost + put_cost)
                portfolio['share_cost_basis'] = underlying_price
                
                if put_exec_price > 0:
                    portfolio['active_put'] = {'strike': target_put_strike, 'premium': put_exec_price, 'exp': selected_put_exp}
        
        # 3. Supplemental Put Purchase (if shares carried over but put was rolled or expired)
        elif portfolio['active_put'] is None and portfolio['shares'] >= 100:
            target_put_strike = round(underlying_price)
            min_exp = mon_date.date() + timedelta(days=120)
            max_exp = mon_date.date() + timedelta(days=180)
            
            put_options = daily_chain[
                (daily_chain[col_map['right']] == 'P') & 
                (daily_chain[col_map['exp']].dt.date >= min_exp) &
                (daily_chain[col_map['exp']].dt.date <= max_exp) &
                (daily_chain[col_map['strike']] == target_put_strike)
            ].sort_values(by=col_map['exp'])
            
            if len(put_options) > 0:
                opt = put_options.iloc[0]
                exec_price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=True)
                if exec_price:
                    put_cost = exec_price * 100 * (portfolio['shares'] // 100)
                    if portfolio['cash'] >= put_cost:
                        portfolio['cash'] -= put_cost
                        portfolio['active_put'] = {'strike': target_put_strike, 'premium': exec_price, 'exp': opt[col_map['exp']].date()}

        portfolio['prev_week_entry_price'] = underlying_price

        # 4. Covered Call Writing (Rule 1.2 & Rule 2.10 Dynamic Strike Reset)
        if portfolio['shares'] >= 100 and portfolio['active_call'] is None:
            # Rule 2.10: Always price ~5% above CURRENT market price, not historical cost basis
            target_call_strike = round(underlying_price * 1.05)
            friday_date = mon_date.date() + timedelta(days=(4 - mon_date.weekday()))
            
            call_options = daily_chain[
                (daily_chain[col_map['right']] == 'C') & 
                (daily_chain[col_map['exp']].dt.date >= friday_date) &
                (daily_chain[col_map['strike']] == target_call_strike)
            ].sort_values(by=col_map['exp'])
            
            if len(call_options) > 0:
                opt = call_options.iloc[0]
                exec_price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=False)
                if exec_price:
                    contracts = portfolio['shares'] // 100
                    premium_collected = exec_price * 100 * contracts
                    portfolio['cash'] += premium_collected
                    portfolio['active_call'] = {'strike': target_call_strike, 'premium': exec_price, 'exp': opt[col_map['exp']].date()}

        # ------------------------------------------------------------------
        # FRIDAY PM EVALUATION (End of Week - 3-Tier Clearing)
        # ------------------------------------------------------------------
        last_day = week_bars['Date'].dt.date.max()
        fri_bars = week_bars[(week_bars['Date'].dt.date == last_day) & (week_bars['Date'].dt.time <= time(15, 30))]
        
        if len(fri_bars) == 0:
            continue
        fri_exec_bar = fri_bars.iloc[-1]
        fri_price = fri_exec_bar['Close']
        
        pct_change = (fri_price - underlying_price) / underlying_price
        settlement_tier = "Tier 2: OTM Expiration (Modest Gain 0-5%)" if pct_change >= 0.0 else "Tier 3: OTM Expiration (Loss)"
        call_assigned = False
        
        if portfolio['active_call'] is not None:
            call_strike = portfolio['active_call']['strike']
            
            # TIER 1: Stock finishes above Call Strike (ITM Assignment)
            if fri_price >= call_strike:
                settlement_tier = "Tier 1: ITM Assignment (Gain >= 10% - Put Roll Candidate)" if pct_change >= 0.10 else "Tier 1: ITM Assignment (Gain >= 5%)"
                proceeds = portfolio['shares'] * call_strike
                capital_gain = proceeds - (portfolio['shares'] * portfolio['share_cost_basis'])
                
                portfolio['cash'] += proceeds
                
                # Capital Rule 3: Sweep 25% of net realized capital gains
                if capital_gain > 0:
                    sweep_amt = capital_gain * SWEEP_RATE
                    portfolio['cash'] -= sweep_amt
                    portfolio['sweep_cash'] += sweep_amt
                
                portfolio['shares'] = 0
                portfolio['share_cost_basis'] = 0.0
                call_assigned = True
            elif pct_change > 0.00:
                settlement_tier = "Tier 2: OTM Expiration (Modest Gain 0-5%)"
            else:
                settlement_tier = "Tier 3: OTM Expiration (Loss)"

        portfolio['active_call'] = None
        
        # Financial reporting metrics
        realized_cash_flow = portfolio['cash'] - week_start_cash
        unrealized_paper_pnl = portfolio['shares'] * (fri_price - portfolio['share_cost_basis']) if portfolio['shares'] > 0 else 0.0
        total_equity = portfolio['cash'] + portfolio['sweep_cash'] + (portfolio['shares'] * fri_price)
        
        portfolio['weekly_log'].append({
            'Week': week,
            'Mon_Date': mon_date.strftime('%Y-%m-%d %H:%M'),
            'Mon_Price': round(underlying_price, 2),
            'Share_Cost_Basis': round(portfolio['share_cost_basis'], 2) if portfolio['shares'] > 0 else 0.0,
            'Carried_Over_Shares': carried_over_shares,
            'Short_Call_Strike': portfolio['active_call']['strike'] if portfolio['active_call'] else (round(underlying_price * 1.05) if not call_assigned else 0),
            'Active_Put_Strike': portfolio['active_put']['strike'] if portfolio['active_put'] else 0,
            'Put_Roll_Triggered': put_roll_triggered,
            'Fri_Price': round(fri_price, 2),
            'Weekly_Return_Pct': round(pct_change * 100, 2),
            'Settlement_Tier': settlement_tier,
            'Call_Assigned': call_assigned,
            'Realized_Cash_Flow': round(realized_cash_flow, 2),
            'Unrealized_Paper_Pnl': round(unrealized_paper_pnl, 2),
            'Total_Portfolio_Equity': round(total_equity, 2)
        })

    print("--- [3] Backtest Complete. Exporting 15-Column Audit Trail ---")
    df_log = pd.DataFrame(portfolio['weekly_log'])
    print("\nFinal 10 Weeks Execution Summary:")
    print(df_log[['Week', 'Mon_Price', 'Share_Cost_Basis', 'Short_Call_Strike', 'Active_Put_Strike', 'Settlement_Tier', 'Realized_Cash_Flow', 'Total_Portfolio_Equity']].tail(10).to_string(index=False))
    
    output_filename = 'SOXL_Strategy_Audit_Trail_v3.csv'
    df_log.to_csv(output_filename, index=False)
    print(f"\nComplete v3 audit trail successfully saved to '{output_filename}'.")

if __name__ == "__main__":
    run_backtest()