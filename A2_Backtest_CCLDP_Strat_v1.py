import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta

# ==========================================
# FILE PATHS & CONSTANTS
# ==========================================
STOCK_FILE = 'SOXL_5min_3Years.csv'
OPTIONS_FILE = 'SOXL_Master_Cleaned.csv'
INITIAL_CAPITAL = 150000.0
REINVEST_RATE = 0.75
SWEEP_RATE = 0.25

def load_and_prep_data():
    print("--- [1] Loading and Synchronizing Data ---")
    # Load 5-min Stock Data (Using Rev C verified parsing)
    df_stock = pd.read_csv(STOCK_FILE)
    df_stock['Date_Clean'] = df_stock['Date'].astype(str).str.replace(' America/New_York', '', regex=False)
    df_stock['Date'] = pd.to_datetime(df_stock['Date_Clean'], format='%Y%m%d %H:%M:%S', errors='coerce')
    df_stock = df_stock.dropna(subset=['Date']).sort_values(by='Date').reset_index(drop=True)
    
    # Load Options Data
    df_opt = pd.read_csv(OPTIONS_FILE, low_memory=False)
    col_map = {'date': 'trade_date', 'exp': 'expiration', 'strike': 'strike', 
               'bid': 'bid', 'ask': 'ask', 'iv': 'implied_vol', 'right': 'right'}
    
    df_opt[col_map['date']] = pd.to_datetime(df_opt[col_map['date']], errors='coerce')
    df_opt[col_map['exp']] = pd.to_datetime(df_opt[col_map['exp']], errors='coerce')
    
    # Filter for whole number strikes only (Rule #5)
    df_opt = df_opt[df_opt[col_map['strike']] % 1 == 0].copy()
    
    # Filter both datasets to overlapping date window (Jan 2024 - July 2026)
    start_date = max(df_stock['Date'].min().date(), df_opt[col_map['date']].min().date())
    end_date = min(df_stock['Date'].max().date(), df_opt[col_map['date']].max().date())
    
    df_stock = df_stock[(df_stock['Date'].dt.date >= start_date) & (df_stock['Date'].dt.date <= end_date)]
    df_opt = df_opt[(df_opt[col_map['date']].dt.date >= start_date) & (df_opt[col_map['date']].dt.date <= end_date)]
    
    print(f"Synchronized Backtest Window: {start_date} to {end_date}")
    return df_stock, df_opt, col_map

def get_execution_price(bid, ask, is_buy=True):
    """Rule #6: 20% above low end of spread for sell, reverse for buy."""
    if pd.isna(bid) or pd.isna(ask) or bid <= 0 or ask <= 0 or ask < bid:
        return None # Triggers audit flag / fallback
    spread = ask - bid
    if is_buy:
        return ask - (0.20 * spread)
    else:
        return bid + (0.20 * spread)

def run_backtest():
    df_stock, df_opt, col_map = load_and_prep_data()
    
    # Create weekly trading calendar (Group by Year-Week)
    df_stock['YearWeek'] = df_stock['Date'].dt.strftime('%Y-%U')
    weeks = sorted(df_stock['YearWeek'].unique())
    
    # Portfolio State Machine
    portfolio = {
        'cash': INITIAL_CAPITAL,
        'sweep_cash': 0.0,
        'shares': 0,
        'share_cost_basis': 0.0,
        'active_put': None,
        'active_call': None,
        'weekly_log': []
    }
    
    print("\n--- [2] Executing Weekly State Machine ---")
    
    for week_idx, week in enumerate(weeks):
        week_bars = df_stock[df_stock['YearWeek'] == week]
        if len(week_bars) == 0:
            continue
            
        # ------------------------------------------------------------------
        # MONDAY AM EXECUTION (Start of Week)
        # ------------------------------------------------------------------
        # Fallback for market holidays: Get first bar at or after 10:00 AM on first trading day
        first_day = week_bars['Date'].dt.date.min()
        mon_bars = week_bars[(week_bars['Date'].dt.date == first_day) & (week_bars['Date'].dt.time >= time(10, 0))]
        
        if len(mon_bars) == 0:
            continue
        mon_exec_bar = mon_bars.iloc[0]
        mon_date = mon_exec_bar['Date']
        underlying_price = mon_exec_bar['Close'] # Rule 2.1: Use Close of 5-min segment
        
        # 1. Share Re-balancing / Purchase (Invest 75% of available cash in whole shares)
        if portfolio['shares'] == 0:
            invest_amount = portfolio['cash'] * REINVEST_RATE
            new_shares = int(invest_amount // underlying_price)
            cost = new_shares * underlying_price
            portfolio['shares'] += new_shares
            portfolio['cash'] -= cost
            portfolio['share_cost_basis'] = underlying_price
        
        # 2. Covered Call Writing (Rule 1.2 & 2.7)
        # If shares held from previous week uncalled, strike is nearest to original purchase price
        # If new shares bought, strike is ~5% above purchase price
        target_call_strike = round(portfolio['share_cost_basis'] * 1.05)
        
        # Look up option chain for Monday date
        daily_chain = df_opt[df_opt[col_map['date']].dt.date == mon_date.date()]
        
        # Find Weekly Call expiring this Friday
        friday_date = mon_date.date() + timedelta(days=(4 - mon_date.weekday()))
        call_options = daily_chain[
            (daily_chain[col_map['right']] == 'C') & 
            (daily_chain[col_map['exp']].dt.date == friday_date) &
            (daily_chain[col_map['strike']] == target_call_strike)
        ]
        
        if len(call_options) > 0:
            opt = call_options.iloc[0]
            exec_price = get_execution_price(opt[col_map['bid']], opt[col_map['ask']], is_buy=False)
            if exec_price:
                premium_collected = exec_price * 100 * portfolio['shares'] # 1 contract per 100 shares
                portfolio['cash'] += premium_collected
                portfolio['active_call'] = {'strike': target_call_strike, 'premium': exec_price, 'exp': friday_date}
        
        # 3. Long Put Management / Purchase (Rule 1.5, 1.6, 2.5)
        if portfolio['active_put'] is None:
            target_put_strike = round(underlying_price)
            # Find 4-6 months DTE put (120 - 180 days)
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
        
        # ------------------------------------------------------------------
        # FRIDAY PM EVALUATION (End of Week)
        # ------------------------------------------------------------------
        last_day = week_bars['Date'].dt.date.max()
        fri_bars = week_bars[(week_bars['Date'].dt.date == last_day) & (week_bars['Date'].dt.time <= time(15, 30))]
        
        if len(fri_bars) == 0:
            continue
        fri_exec_bar = fri_bars.iloc[-1] # Closest bar to 3:30 PM
        fri_price = fri_exec_bar['Close']
        
        # Check 10% appreciation rule from Monday entry (Rule 2.4 & 2.6)
        pct_change = (fri_price - underlying_price) / underlying_price
        call_exercised = False
        
        if pct_change >= 0.10 and portfolio['active_call'] is not None:
            # Call is exercised: Sell shares at Call Strike price
            strike_price = portfolio['active_call']['strike']
            proceeds = portfolio['shares'] * strike_price
            profit = proceeds - (portfolio['shares'] * portfolio['share_cost_basis'])
            
            portfolio['cash'] += proceeds
            portfolio['shares'] = 0
            portfolio['share_cost_basis'] = 0.0
            call_exercised = True
            
            # Sweep 25% of positive cash generated (profit + net premium) to separate account (Rule Capital 3)
            if profit > 0:
                sweep_amt = profit * SWEEP_RATE
                portfolio['cash'] -= sweep_amt
                portfolio['sweep_cash'] += sweep_amt
                
        # Expire weekly call
        portfolio['active_call'] = None
        
        # Log weekly results for audit
        portfolio['weekly_log'].append({
            'Week': week,
            'Mon_Date': mon_date.strftime('%Y-%m-%d %H:%M'),
            'Mon_Price': underlying_price,
            'Fri_Price': fri_price,
            'Pct_Change': round(pct_change * 100, 2),
            'Call_Exercised': call_exercised,
            'Shares_Held': portfolio['shares'],
            'Operating_Cash': round(portfolio['cash'], 2),
            'Sweep_Account': round(portfolio['sweep_cash'], 2),
            'Total_Equity': round(portfolio['cash'] + portfolio['sweep_cash'] + (portfolio['shares'] * fri_price), 2)
        })

    print("--- [3] Backtest Complete. Generating Audit Trail ---")
    df_log = pd.DataFrame(portfolio['weekly_log'])
    print(df_log.tail(10).to_string(index=False))
    
    # Save complete audit log to CSV
    df_log.to_csv('SOXL_Strategy_Audit_Trail.csv', index=False)
    print("\nFull audit trail successfully saved to 'SOXL_Strategy_Audit_Trail.csv'.")

if __name__ == "__main__":
    run_backtest()