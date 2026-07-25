import pandas as pd
import numpy as np

print("1. Loading Master Dataset...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- DYNAMIC STRATEGY PARAMETERS ---
STARTING_CAPITAL = 100000.0   # $100k starting portfolio
CALL_PROFIT_TARGET = 0.50     # Close if Call premium drops by 50% (capture 50% max profit)
PUT_PROFIT_TARGET = 2.00      # Close if Put price increases by 200% (triple value)

TARGET_CALL_DTE = 14
TARGET_CALL_DELTA = 0.20
TARGET_PUT_DTE = 90
TARGET_PUT_DELTA = -0.20

print(f"2. Initializing Dynamic Engine with ${STARTING_CAPITAL:,.2f} Starting Capital...")

portfolio_capital = STARTING_CAPITAL
trades = []
current_day_idx = 0

# --- OUTER LOOP: FINDING ENTRIES ---
while current_day_idx < len(trading_days) - 1:
    entry_date = trading_days[current_day_idx]
    daily_options = df[df['Date'] == entry_date]
    if daily_options.empty:
        current_day_idx += 1
        continue
        
    underlying_price = daily_options['Underlying_Close'].iloc[0]
    
    # 1. Find the Call
    calls = daily_options[(daily_options['flag'] == 'c') & 
                          (daily_options['DTE'] >= TARGET_CALL_DTE - 3) & 
                          (daily_options['DTE'] <= TARGET_CALL_DTE + 5)].copy()
    if calls.empty:
        current_day_idx += 1
        continue
    calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - TARGET_CALL_DELTA)
    best_call = calls.loc[calls['delta_diff'].idxmin()]
    
    # 2. Find the Put
    puts = daily_options[(daily_options['flag'] == 'p') & 
                         (daily_options['DTE'] >= TARGET_PUT_DTE - 10) & 
                         (daily_options['DTE'] <= TARGET_PUT_DTE + 20)].copy()
    if puts.empty:
        current_day_idx += 1
        continue
    puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - TARGET_PUT_DELTA)
    best_put = puts.loc[puts['delta_diff'].idxmin()]
    
    # 3. Dynamic Position Sizing (Compounding)
    # Unit Cost = 100 shares of stock + 1 Long Put
    unit_cost = (underlying_price * 100) + (best_put['close'] * 100)
    units_to_trade = int(portfolio_capital // unit_cost)
    
    if units_to_trade == 0:
        print(f"[{entry_date.date()}] Out of capital. Portfolio blew up. Ending simulation.")
        break
        
    # --- INNER LOOP: DAILY MANAGEMENT STEPPER ---
    trade_active = True
    eval_day_idx = current_day_idx + 1
    
    exit_reason = ""
    exit_date = None
    exit_underlying = 0
    exit_call_price = 0
    exit_put_price = 0
    
    while trade_active and eval_day_idx < len(trading_days):
        eval_date = trading_days[eval_day_idx]
        eval_data = df[df['Date'] == eval_date]
        
        if eval_data.empty:
            eval_day_idx += 1
            continue
            
        current_underlying = eval_data['Underlying_Close'].iloc[0]
        
        # Look up current prices for our specific contracts
        curr_call = eval_data[(eval_data['strike'] == best_call['strike']) & (eval_data['flag'] == 'c') & (eval_data['expiration'] == best_call['expiration'])]
        curr_put = eval_data[(eval_data['strike'] == best_put['strike']) & (eval_data['flag'] == 'p') & (eval_data['expiration'] == best_put['expiration'])]
        
        # Fallback to intrinsic value if quote is missing on a specific day
        c_price = curr_call['close'].iloc[0] if not curr_call.empty else max(0, current_underlying - best_call['strike'])
        p_price = curr_put['close'].iloc[0] if not curr_put.empty else max(0, best_put['strike'] - current_underlying)
        
        # --- CHECK TRIGGERS ---
        trigger_hit = False
        
        # Trigger 1: Call Profit Target (Bought back at 50% of credit received)
        if c_price <= (best_call['close'] * (1.0 - CALL_PROFIT_TARGET)):
            exit_reason = f"Call {CALL_PROFIT_TARGET*100}% Profit Hit"
            trigger_hit = True
            
        # Trigger 2: Put Profit Target (Monetize the crash)
        elif p_price >= (best_put['close'] * (1.0 + PUT_PROFIT_TARGET)):
            exit_reason = f"Put {PUT_PROFIT_TARGET*100}% Profit Hit"
            trigger_hit = True
            
        # Trigger 3: Expiration Date Reached (Time Stop)
        elif eval_date >= best_call['expiration']:
            exit_reason = "Expiration Reached"
            trigger_hit = True
            
        if trigger_hit:
            exit_date = eval_date
            exit_underlying = current_underlying
            exit_call_price = c_price
            exit_put_price = p_price
            trade_active = False
        else:
            eval_day_idx += 1
            
    # --- END OF TRADE MATH ---
    # If we reached the end of the dataset without hitting a trigger, force exit
    if trade_active:
        exit_date = trading_days[-1]
        exit_underlying = df[df['Date'] == exit_date]['Underlying_Close'].iloc[0]
        exit_call_price = max(0, exit_underlying - best_call['strike'])
        exit_put_price = max(0, best_put['strike'] - exit_underlying)
        exit_reason = "End of Data"
        
    # Calculate PnL (Scaled by Compounding Units)
    stock_pnl = (exit_underlying - underlying_price) * 100 * units_to_trade
    call_pnl = (best_call['close'] - exit_call_price) * 100 * units_to_trade  # Sold
    put_pnl = (exit_put_price - best_put['close']) * 100 * units_to_trade     # Bought
    
    trade_total_pnl = stock_pnl + call_pnl + put_pnl
    portfolio_capital += trade_total_pnl # COMPOUNDING: Add profit/loss to the master pool
    
    trades.append({
        'Entry Date': entry_date.date(),
        'Exit Date': exit_date.date(),
        'Exit Reason': exit_reason,
        'Units Traded': units_to_trade,
        'Days Held': (exit_date - entry_date).days,
        'Stock PnL': round(stock_pnl, 2),
        'Call PnL': round(call_pnl, 2),
        'Put PnL': round(put_pnl, 2),
        'Trade Net PnL': round(trade_total_pnl, 2),
        'Portfolio Value': round(portfolio_capital, 2)
    })
    
    # Move to the day after exit to start the next trade
    current_day_idx = trading_days.index(exit_date) + 1

# --- REPORTING ---
results_df = pd.DataFrame(trades)

print("\n=== DYNAMIC COMPOUNDING PERFORMANCE ===")
print(f"Total Trades Executed: {len(results_df)}")
if not results_df.empty:
    wins = len(results_df[results_df['Trade Net PnL'] > 0])
    win_rate = (wins / len(results_df)) * 100
    total_net_profit = portfolio_capital - STARTING_CAPITAL
    roi_pct = (total_net_profit / STARTING_CAPITAL) * 100
    
    # Calculate Max Drawdown
    results_df['Peak'] = results_df['Portfolio Value'].cummax()
    results_df['Drawdown'] = (results_df['Portfolio Value'] - results_df['Peak']) / results_df['Peak']
    max_drawdown = results_df['Drawdown'].min() * 100
    
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Starting Capital: ${STARTING_CAPITAL:,.2f}")
    print(f"Ending Capital:   ${portfolio_capital:,.2f}")
    print(f"Total Net Profit: ${total_net_profit:,.2f} ({roi_pct:.2f}% ROI)")
    print(f"Maximum Drawdown: {max_drawdown:.2f}%")
    
    # Tally the exit reasons
    print("\n--- Exit Reasons ---")
    print(results_df['Exit Reason'].value_counts().to_string())
    
    results_df.to_csv("Dynamic_Collar_Results.csv", index=False)
    print("\nDetailed trade log saved to 'Dynamic_Collar_Results.csv'")