import pandas as pd
import numpy as np

print("1. Loading Master Dataset...")
df = pd.read_csv("Master_Backtest_Data_SOXL.csv")
df['Date'] = pd.to_datetime(df['Date'])
df['expiration'] = pd.to_datetime(df['expiration'])
df = df.sort_values(['Date', 'expiration', 'strike'])
trading_days = sorted(df['Date'].unique())

# --- V2 STRATEGY PARAMETERS ---
STARTING_CAPITAL = 100000.0

# Anchor Parameters (The Vault)
PUT_TARGET_DTE = 120
PUT_TARGET_DELTA = -0.15
PUT_PROFIT_MULTIPLIER = 4.0   # Sell if Put jumps 400% (Crash Monetization)
PUT_ROLL_DTE = 21             # Roll to a new put if it gets within 21 days of expiration

# Harvester Parameters (The Active Manager)
CALL_TARGET_DTE = 14
CALL_TARGET_DELTA = 0.20
CALL_PROFIT_TARGET = 0.80     # Buy back at 80% max profit
CALL_DELTA_STOP = 0.50        # Stop loss: Buy back if Delta hits 0.50 (ATM)
CALL_RSI_EXHAUSTION = 80      # Buy back early if SOXL hits RSI 80 (Overbought)

print("2. Initializing V2 Asynchronous State Machine...\n")

# Portfolio State Variables
cash = STARTING_CAPITAL
shares_owned = 0
active_put = None   
active_call = None  

portfolio_history = []
trade_log = []

peak_portfolio_value = STARTING_CAPITAL
max_drawdown = 0.0

# --- THE DAILY STEPPER (STATE MACHINE) ---
for current_date in trading_days:
    daily_chain = df[df['Date'] == current_date]
    if daily_chain.empty:
        continue
        
    current_underlying = daily_chain['Underlying_Close'].iloc[0]
    
    # ---------------------------------------------------------
    # STATE 1: PORTFOLIO INITIALIZATION & ANCHOR MANAGEMENT
    # ---------------------------------------------------------
    if shares_owned == 0 or active_put is None:
        puts = daily_chain[(daily_chain['flag'] == 'p') & (daily_chain['DTE'] >= PUT_TARGET_DTE - 10) & (daily_chain['DTE'] <= PUT_TARGET_DTE + 20)].copy()
        if not puts.empty:
            puts.loc[:, 'delta_diff'] = abs(puts['Delta'] - PUT_TARGET_DELTA)
            target_put = puts.loc[puts['delta_diff'].idxmin()]
            
            unit_cost = (current_underlying * 100) + (target_put['close'] * 100)
            units_to_buy = int(cash // unit_cost)
            
            if units_to_buy > 0:
                shares_owned += units_to_buy * 100
                put_cost = target_put['close'] * 100 * units_to_buy
                stock_cost = current_underlying * 100 * units_to_buy
                
                cash -= (put_cost + stock_cost)
                
                active_put = {
                    'strike': target_put['strike'],
                    'expiration': target_put['expiration'],
                    'units': units_to_buy,
                    'entry_price': target_put['close'],
                    'entry_date': current_date
                }
                trade_log.append({'Date': current_date.date(), 'Action': 'OPEN ANCHOR', 'Details': f"Bot {units_to_buy*100} shares & {units_to_buy} Puts @ {target_put['strike']}"})

    # ---------------------------------------------------------
    # STATE 2: HARVESTER MANAGEMENT (CALL SELLING & ROLLING)
    # ---------------------------------------------------------
    if shares_owned > 0 and active_call is None:
        calls = daily_chain[(daily_chain['flag'] == 'c') & (daily_chain['DTE'] >= CALL_TARGET_DTE - 3) & (daily_chain['DTE'] <= CALL_TARGET_DTE + 5)].copy()
        if not calls.empty:
            calls.loc[:, 'delta_diff'] = abs(calls['Delta'] - CALL_TARGET_DELTA)
            target_call = calls.loc[calls['delta_diff'].idxmin()]
            
            calls_to_sell = shares_owned // 100
            premium_collected = target_call['close'] * 100 * calls_to_sell
            
            cash += premium_collected 
            
            active_call = {
                'strike': target_call['strike'],
                'expiration': target_call['expiration'],
                'units': calls_to_sell,
                'entry_price': target_call['close'],
                'entry_date': current_date
            }
            trade_log.append({'Date': current_date.date(), 'Action': 'SELL CALL', 'Details': f"Sold {calls_to_sell} Calls @ {target_call['strike']} for ${premium_collected:.2f}"})

    # ---------------------------------------------------------
    # STATE 3: END OF DAY PRICING & EVALUATION
    # ---------------------------------------------------------
    current_put_value = 0
    current_call_liability = 0
    
    # Evaluate Active Put
    if active_put is not None:
        put_data = daily_chain[(daily_chain['strike'] == active_put['strike']) & (daily_chain['flag'] == 'p') & (daily_chain['expiration'] == active_put['expiration'])]
        p_price = put_data['close'].iloc[0] if not put_data.empty else max(0, active_put['strike'] - current_underlying)
        current_put_value = p_price * 100 * active_put['units']
        
        # FIX: Removed .date() to keep both variables as Pandas Timestamps
        days_to_put_expiry = (active_put['expiration'] - current_date).days
        
        if p_price >= (active_put['entry_price'] * PUT_PROFIT_MULTIPLIER):
            cash += current_put_value
            trade_log.append({'Date': current_date.date(), 'Action': 'MONETIZE PUT', 'Details': f"Crash! Sold Put for {PUT_PROFIT_MULTIPLIER}x. Added ${current_put_value:.2f}"})
            active_put = None 
            
        elif days_to_put_expiry <= PUT_ROLL_DTE:
            cash += current_put_value
            trade_log.append({'Date': current_date.date(), 'Action': 'ROLL PUT', 'Details': f"Put reached {PUT_ROLL_DTE} DTE. Closing to roll."})
            active_put = None
            
        # FIX: Removed .date() here as well
        elif current_date >= active_put['expiration']:
            cash += current_put_value
            active_put = None

    # Evaluate Active Call
    if active_call is not None:
        call_data = daily_chain[(daily_chain['strike'] == active_call['strike']) & (daily_chain['flag'] == 'c') & (daily_chain['expiration'] == active_call['expiration'])]
        c_price = call_data['close'].iloc[0] if not call_data.empty else max(0, current_underlying - active_call['strike'])
        c_delta = call_data['Delta'].iloc[0] if not call_data.empty else 1.0
        
        current_call_liability = c_price * 100 * active_call['units']
        current_rsi = daily_chain['RSI_14'].iloc[0] if 'RSI_14' in daily_chain.columns else 50
        
        action_taken = False
        
        if c_price <= (active_call['entry_price'] * (1.0 - CALL_PROFIT_TARGET)):
            cash -= current_call_liability
            trade_log.append({'Date': current_date.date(), 'Action': 'BUYBACK CALL (PROFIT)', 'Details': f"Hit {CALL_PROFIT_TARGET*100}% profit. Cost: ${current_call_liability:.2f}"})
            action_taken = True
            
        elif c_delta >= CALL_DELTA_STOP:
            cash -= current_call_liability
            trade_log.append({'Date': current_date.date(), 'Action': 'BUYBACK CALL (STOP LOSS)', 'Details': f"Delta breached {CALL_DELTA_STOP}. Cost: ${current_call_liability:.2f}"})
            action_taken = True
            
        elif current_rsi >= CALL_RSI_EXHAUSTION:
            cash -= current_call_liability
            trade_log.append({'Date': current_date.date(), 'Action': 'BUYBACK CALL (RSI)', 'Details': f"RSI hit {current_rsi:.1f}. Locking in gains early."})
            action_taken = True
            
        # FIX: Removed .date() here as well
        elif current_date >= active_call['expiration']:
            cash -= current_call_liability
            trade_log.append({'Date': current_date.date(), 'Action': 'CALL EXPIRED', 'Details': f"Call expired. Liability cleared."})
            action_taken = True
            
        if action_taken:
            active_call = None 

    # ---------------------------------------------------------
    # STATE 4: PORTFOLIO MARK-TO-MARKET
    # ---------------------------------------------------------
    stock_value = shares_owned * current_underlying
    current_portfolio_value = cash + stock_value + current_put_value - current_call_liability
    
    if current_portfolio_value > peak_portfolio_value:
        peak_portfolio_value = current_portfolio_value
        
    current_dd = (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value
    if current_dd > max_drawdown:
        max_drawdown = current_dd
        
    portfolio_history.append({
        'Date': current_date.date(),
        'Underlying': current_underlying,
        'Portfolio_Value': current_portfolio_value,
        'Cash': cash,
        'Drawdown_%': current_dd * 100
    })

# --- REPORTING ---
perf_df = pd.DataFrame(portfolio_history)
logs_df = pd.DataFrame(trade_log)

# Mark to market at the end of the simulation if we still hold assets
final_value = perf_df['Portfolio_Value'].iloc[-1]
roi_pct = ((final_value - STARTING_CAPITAL) / STARTING_CAPITAL) * 100

print("=== V2 ASYNCHRONOUS ENGINE RESULTS ===")
print(f"Starting Capital: ${STARTING_CAPITAL:,.2f}")
print(f"Ending Capital:   ${final_value:,.2f}")
print(f"Total ROI:        {roi_pct:.2f}%")
print(f"Max Drawdown:     {max_drawdown*100:.2f}%")
print(f"\nTotal Asynchronous Actions Executed: {len(logs_df)}")

print("\n--- Trade Log Sample (Last 15 Actions) ---")
print(logs_df.tail(15).to_string(index=False))

perf_df.to_csv("V2_Daily_Portfolio_Curve.csv", index=False)
logs_df.to_csv("V2_Action_Log.csv", index=False)