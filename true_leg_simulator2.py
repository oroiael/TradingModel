import pandas as pd
import warnings
import math
import time

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

class TrueLegByLegSimulator:
    def __init__(self, data_path, initial_capital=150000):
        self.initial_capital = initial_capital
        print(f"Loading Master Dataset: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)
        
        self.df['Date'] = pd.to_datetime(self.df['date'] if 'date' in self.df.columns else self.df['trade_date'])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        print("Building True Data O(1) Hash Map for EXACT Options Prices...")
        self.put_df = self.df[self.df['type'].str.upper().isin(['P', 'PUT'])].copy() if 'type' in self.df.columns else self.df[self.df['right'].str.upper().isin(['P', 'PUT'])].copy()
        
        # O(1) Lookup Cache for EXACT Historical Option Prices
        self.options_cache = self.put_df.set_index(['Date', 'Expiration', 'strike'])['close'].to_dict()

        if 'underlying_price' in self.df.columns:
            daily_px = self.df.groupby('Date')['underlying_price'].first().sort_index()
            self.daily_prices = daily_px.to_dict()
            self.sma_50 = daily_px.rolling(window=50).mean().to_dict()
        else:
            self.daily_prices, self.sma_50 = {}, {}
            
        print(f"Engine Ready: {len(self.df)} records cached. STRICT Leg-by-Leg routing enabled.\n")

    def run_simulation(self, dte_range=(20, 45), target_width=5.0, min_credit=0.80, 
                       alloc_pct=0.15, max_trades=2, stop_loss_mult=1.5, 
                       take_profit_pct=0.40, require_uptrend=False, 
                       base_sweep_pct=0.10, max_contracts=300):
                       
        print("--- EXECUTING TRUE DATA LEG-BY-LEG SIMULATION ---")
        trading_days = sorted(self.daily_prices.keys())
        
        # Cash Management Architecture
        trading_balance = self.initial_capital
        swept_cash = 0.0
        high_water_mark = self.initial_capital
        
        open_trades = []
        closed_trades = []
        
        start_time = time.time()

        for current_date in trading_days:
            current_underlying_price = self.daily_prices.get(current_date)
            current_sma = self.sma_50.get(current_date)
            
            if pd.isna(current_sma): continue
            
            # ==========================================
            # 1. PROCESS OPEN TRADES (EXACT DATA LOOKUP)
            # ==========================================
            still_open = []
            for trade in open_trades:
                
                # Fetch EXACT historical prices for TODAY for both specific legs
                curr_short_price = self.options_cache.get((current_date, trade['Expiration'], trade['Short Strike']))
                curr_long_price = self.options_cache.get((current_date, trade['Expiration'], trade['Long Strike']))
                
                # Expiration Day Fallback (If options lack volume on expiry day, force settlement)
                if current_date >= trade['Expiration'] and (curr_short_price is None or curr_long_price is None):
                    curr_short_price = max(0, trade['Short Strike'] - current_underlying_price)
                    curr_long_price = max(0, trade['Long Strike'] - current_underlying_price)
                elif curr_short_price is None or curr_long_price is None:
                    # Missing data on a random Tuesday, hold the trade
                    still_open.append(trade)
                    continue
                
                current_spread_cost = curr_short_price - curr_long_price
                is_closed = False
                res_reason = ""
                
                # Check Exits
                if current_date >= trade['Expiration']:
                    is_closed = True
                    res_reason = "EXPIRATION"
                elif current_spread_cost >= (trade['Entry Net Credit'] * stop_loss_mult):
                    is_closed = True
                    res_reason = f"STOP-LOSS ({stop_loss_mult}x)"
                elif current_spread_cost <= (trade['Entry Net Credit'] * (1 - take_profit_pct)):
                    is_closed = True
                    res_reason = f"TAKE-PROFIT ({int(take_profit_pct*100)}%)"

                if is_closed:
                    # --- MATHEMATICAL LEG-BY-LEG PNL ---
                    # Short Put PnL: You sold to open, bought to close. (Entry - Exit)
                    short_leg_pnl_per_contract = (trade['Entry Short Price'] - curr_short_price) * 100
                    total_short_pnl = short_leg_pnl_per_contract * trade['Contracts']
                    
                    # Long Put PnL: You bought to open, sold to close. (Exit - Entry)
                    long_leg_pnl_per_contract = (curr_long_price - trade['Entry Long Price']) * 100
                    total_long_pnl = long_leg_pnl_per_contract * trade['Contracts']
                    
                    total_combined_pnl = total_short_pnl + total_long_pnl
                    
                    # --- CASH MANAGEMENT & SWEEP LOGIC ---
                    sweep_amount = 0.0
                    
                    if total_combined_pnl > 0:
                        # If we are capped at 300 contracts, we sweep 100% of the profit to the cash 
                        # account so the trading balance stops artificially compounding.
                        if trade['Contracts'] >= max_contracts:
                            sweep_amount = total_combined_pnl
                        else:
                            sweep_amount = total_combined_pnl * base_sweep_pct
                            
                        swept_cash += sweep_amount
                        trading_balance += (total_combined_pnl - sweep_amount)
                    else:
                        # Loser: Comes purely out of the trading balance, no sweep.
                        trading_balance += total_combined_pnl

                    # Calculate Total Net Worth for Drawdown
                    total_net_worth = trading_balance + swept_cash
                    if total_net_worth > high_water_mark:
                        high_water_mark = total_net_worth
                    
                    drawdown_dol = high_water_mark - total_net_worth
                    drawdown_pct = (drawdown_dol / high_water_mark) * 100 if high_water_mark > 0 else 0
                    
                    # Log the exact Leg-by-Leg execution
                    closed_trades.append({
                        'Entry Date': trade['Entry Date'],
                        'Exit Date': current_date,
                        'Expiration': trade['Expiration'],
                        'Reason': res_reason,
                        'Contracts': trade['Contracts'],
                        'Short Strike': trade['Short Strike'],
                        'Long Strike': trade['Long Strike'],
                        'Entry Short $': round(trade['Entry Short Price'], 2),
                        'Entry Long $': round(trade['Entry Long Price'], 2),
                        'Entry Net Credit': round(trade['Entry Net Credit'], 2),
                        'Exit Short $': round(curr_short_price, 2),
                        'Exit Long $': round(curr_long_price, 2),
                        'Exit Net Cost': round(current_spread_cost, 2),
                        'Short Leg PnL': round(total_short_pnl, 2),
                        'Long Leg PnL': round(total_long_pnl, 2),
                        'Total Trade PnL': round(total_combined_pnl, 2),
                        'Cash Swept': round(sweep_amount, 2),
                        'Trading Balance': round(trading_balance, 2),
                        'Cash Vault': round(swept_cash, 2),
                        'Total Account Value': round(total_net_worth, 2),
                        'Drawdown (%)': round(drawdown_pct, 2)
                    })
                else:
                    still_open.append(trade)
                    
            open_trades = still_open

            # ==========================================
            # 2. PROCESS NEW ENTRIES
            # ==========================================
            if require_uptrend and current_underlying_price < current_sma:
                continue
                
            if len(open_trades) < max_trades:
                daily_puts = self.put_df[(self.put_df['Date'] == current_date) & (self.put_df['DTE'].between(*dte_range))]
                if daily_puts.empty: continue
                
                short_candidates = daily_puts.iloc[(daily_puts['delta'].abs() - 0.20).abs().argsort()]
                long_candidates = daily_puts.iloc[(daily_puts['delta'].abs() - 0.05).abs().argsort()]
                
                if short_candidates.empty or long_candidates.empty: continue
                short_put = short_candidates.iloc[0]
                
                valid_long = None
                for _, long_put in long_candidates.iterrows():
                    if short_put['Expiration'] != long_put['Expiration']: continue
                    if 2.50 <= (short_put['strike'] - long_put['strike']) <= target_width:
                        valid_long = long_put
                        break
                
                if valid_long is None: continue

                raw_short_price = short_put['close']
                raw_long_price = valid_long['close']
                net_credit_raw = raw_short_price - raw_long_price
                
                if (net_credit_raw * 100) >= (min_credit * 100):
                    max_risk_raw = (short_put['strike'] - valid_long['strike']) - net_credit_raw
                    max_risk_dollars = max_risk_raw * 100
                    
                    if max_risk_dollars > 0:
                        # Determine contracts based strictly on active Trading Balance
                        contracts = math.floor((trading_balance * alloc_pct) / max_risk_dollars)
                        
                        # Apply the 300 Contract Cap
                        if contracts > max_contracts:
                            contracts = max_contracts
                            
                        if contracts >= 1:
                            open_trades.append({
                                'Entry Date': current_date,
                                'Expiration': short_put['Expiration'],
                                'Short Strike': short_put['strike'],
                                'Long Strike': valid_long['strike'],
                                'Entry Short Price': raw_short_price,  
                                'Entry Long Price': raw_long_price,
                                'Entry Net Credit': net_credit_raw,
                                'Contracts': contracts
                            })

        # --- FINAL REPORTING ---
        pnl_df = pd.DataFrame(closed_trades)
        if pnl_df.empty:
            print("No trades executed.")
            return

        for col in ['Entry Date', 'Exit Date', 'Expiration']:
            pnl_df[col] = pd.to_datetime(pnl_df[col]).dt.strftime('%Y-%m-%d')
            
        pnl_df.to_csv('SOXL_Leg_By_Leg_True_Data.csv', index=False)
        
        wins = len(pnl_df[pnl_df['Total Trade PnL'] > 0])
        losses = len(pnl_df[pnl_df['Total Trade PnL'] <= 0])
        win_rate = (wins / len(pnl_df)) * 100
        
        final_trading_bal = pnl_df['Trading Balance'].iloc[-1]
        final_swept_cash = pnl_df['Cash Vault'].iloc[-1]
        final_total_account = pnl_df['Total Account Value'].iloc[-1]
        
        total_pnl_dollars = final_total_account - self.initial_capital
        total_roi = (total_pnl_dollars / self.initial_capital) * 100
        max_dd_pct = pnl_df['Drawdown (%)'].max()
        
        print(f"\n--- TRUE DATA LEG-BY-LEG SIMULATION COMPLETE ({round(time.time() - start_time, 1)} sec) ---")
        print(f"Total Trades Executed: {len(pnl_df)}")
        print(f"Total Wins:            {wins}")
        print(f"Total Losses:          {losses}")
        print(f"Historical Win Rate:   {win_rate:.2f}%")
        print("-" * 60)
        print(f"Initial Capital:         ${self.initial_capital:,.2f}")
        print(f"Final Trading Balance:   ${final_trading_bal:,.2f} (Margin at Risk)")
        print(f"Final Cash Vault:        ${final_swept_cash:,.2f} (Safe, Swept Profits)")
        print(f"Final Total Net Worth:   ${final_total_account:,.2f}")
        print(f"Total Net Return:        ${total_pnl_dollars:,.2f} ({total_roi:.2f}%)")
        print("-" * 60)
        print(f"MAXIMUM DRAWDOWN:        {max_dd_pct:.2f}%")
        print("-" * 60)
        print(">> 'SOXL_Leg_By_Leg_True_Data.csv' generated.")
        print(">> Open it to see the EXACT entry/exit price and PnL for every individual leg.")

if __name__ == "__main__":
    # Baseline setup from your most successful Matrix run
    env = TrueLegByLegSimulator(data_path="SOXL_Master_Cleaned.csv", initial_capital=150000)
    
    env.run_simulation(
        dte_range=(20, 45), 
        target_width=5.0, 
        min_credit=0.70, 
        alloc_pct=0.15,          # 15% Risk
        max_trades=2,            # 2 Concurrent Trades Maximum
        stop_loss_mult=1.5,      # Strict 1.5x Premium Stop
        take_profit_pct=0.30,    # Fast 40% Premium Capture
        require_uptrend=False,   # Trading all market conditions
        base_sweep_pct=0.05,     # Sweep 10% of all standard wins
        max_contracts=300        # Contract Cap (100% profit sweep when hit)
    )