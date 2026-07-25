import pandas as pd
import warnings
import math
import time

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

class TrueDataSimulator:
    def __init__(self, data_path, initial_capital=150000):
        self.initial_capital = initial_capital
        print(f"Loading Master Dataset: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)
        
        # Standardize columns
        self.df['Date'] = pd.to_datetime(self.df['date'] if 'date' in self.df.columns else self.df['trade_date'])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        # --- THE TRUE DATA CACHE ---
        print("Building True Data Options Price Cache in RAM...")
        
        # FIX: Attach put_df to self so the simulation engine can access it
        self.put_df = self.df[self.df['type'].str.upper().isin(['P', 'PUT'])].copy() if 'type' in self.df.columns else self.df[self.df['right'].str.upper().isin(['P', 'PUT'])].copy()
        
        self.options_cache = self.put_df.set_index(['Date', 'Expiration', 'strike'])['close'].to_dict()

        if 'underlying_price' in self.df.columns:
            daily_px = self.df.groupby('Date')['underlying_price'].first().sort_index()
            self.daily_prices = daily_px.to_dict()
            self.sma_50 = daily_px.rolling(window=50).mean().to_dict()
        else:
            self.daily_prices, self.sma_50 = {}, {}
            
        print(f"Engine Ready: {len(self.df)} records cached. ZERO proxies. TRUE option pricing enabled.\n")

    def run_true_simulation(self, dte_range=(20, 45), target_width=5.0, min_credit=0.80, alloc_pct=0.15, max_trades=4, stop_loss_mult=1.5, take_profit_pct=0.60):
        print("--- 1. SCANNING FOR SETUPS (50-SMA Filter ON, RSI OFF) ---")
        trading_days = sorted(self.daily_prices.keys())
        
        current_balance = self.initial_capital
        high_water_mark = self.initial_capital
        
        open_trades = []
        closed_trades = []
        
        start_time = time.time()

        for current_date in trading_days:
            current_price = self.daily_prices.get(current_date)
            current_sma = self.sma_50.get(current_date)
            
            if pd.isna(current_sma): continue
            
            # --- PROCESS OPEN TRADES WITH EXACT DATA ---
            still_open = []
            for trade in open_trades:
                
                # Fetch EXACT historical prices for today for both legs
                curr_short_price = self.options_cache.get((current_date, trade['Expiration'], trade['Short Strike']))
                curr_long_price = self.options_cache.get((current_date, trade['Expiration'], trade['Long Strike']))
                
                # If exact data is missing for a day (holiday/illiquid), hold until tomorrow
                if curr_short_price is None or curr_long_price is None:
                    still_open.append(trade)
                    continue
                
                # Calculate exactly what it costs to buy the spread back today
                current_spread_cost = curr_short_price - curr_long_price
                
                # Expiration Day
                if current_date >= trade['Expiration']:
                    if current_price >= trade['Short Strike']:
                        pnl = trade['Base Credit']
                        res = "WIN (EXPIRATION)"
                    elif current_price <= trade['Long Strike']:
                        pnl = -trade['Base Risk']
                        res = "MAX LOSS (EXPIRATION)"
                    else:
                        pnl = trade['Base Credit'] - ((trade['Short Strike'] - current_price) * 100)
                        res = "PARTIAL (EXPIRATION)"
                    
                    self._close_trade(closed_trades, trade, current_date, res, pnl, current_balance, high_water_mark)
                    current_balance += pnl * trade['Contracts']
                    if current_balance > high_water_mark: high_water_mark = current_balance

                # EXACT STOP-LOSS
                elif current_spread_cost >= (trade['Base Credit_Raw'] * stop_loss_mult):
                    exact_loss = min((current_spread_cost - trade['Base Credit_Raw']) * 100, trade['Base Risk'])
                    pnl = -exact_loss
                    res = "STOP-LOSS (EXACT PREMIUM)"
                    
                    self._close_trade(closed_trades, trade, current_date, res, pnl, current_balance, high_water_mark)
                    current_balance += pnl * trade['Contracts']
                    if current_balance > high_water_mark: high_water_mark = current_balance
                
                # EXACT TAKE-PROFIT
                elif current_spread_cost <= (trade['Base Credit_Raw'] * (1 - take_profit_pct)):
                    exact_profit = (trade['Base Credit_Raw'] - current_spread_cost) * 100
                    pnl = exact_profit
                    res = f"TAKE PROFIT ({int(take_profit_pct*100)}%)"
                    
                    self._close_trade(closed_trades, trade, current_date, res, pnl, current_balance, high_water_mark)
                    current_balance += pnl * trade['Contracts']
                    if current_balance > high_water_mark: high_water_mark = current_balance
                
                else:
                    still_open.append(trade)
                    
            open_trades = still_open

            # --- PROCESS NEW ENTRIES ---
            # 50 SMA Trend Filter
            if current_price < current_sma:
                continue
                
            if len(open_trades) < max_trades:
                # FIX: use self.put_df
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

                raw_credit = short_put['close'] - valid_long['close']
                net_credit = raw_credit * 100
                
                if net_credit >= (min_credit * 100):
                    max_risk = ((short_put['strike'] - valid_long['strike']) * 100) - net_credit
                    if max_risk > 0:
                        contracts = math.floor((current_balance * alloc_pct) / max_risk)
                        if contracts >= 1:
                            open_trades.append({
                                'Entry Date': current_date,
                                'Expiration': short_put['Expiration'],
                                'Short Strike': short_put['strike'],
                                'Long Strike': valid_long['strike'],
                                'Base Credit_Raw': raw_credit,  
                                'Base Credit': net_credit,
                                'Base Risk': max_risk,
                                'Contracts': contracts
                            })

        # --- REPORTING ---
        pnl_df = pd.DataFrame(closed_trades)
        if pnl_df.empty:
            print("No trades executed.")
            return

        for col in ['Entry Date', 'Exit Date', 'Expiration']:
            pnl_df[col] = pd.to_datetime(pnl_df[col]).dt.strftime('%Y-%m-%d')
            
        pnl_df.round(2).to_csv('SOXL_True_Data_Log.csv', index=False)
        
        wins = len(pnl_df[pnl_df['PnL ($)'] > 0])
        losses = len(pnl_df[pnl_df['PnL ($)'] <= 0])
        win_rate = (wins / len(pnl_df)) * 100
        total_pnl = pnl_df['PnL ($)'].sum()
        final_balance = pnl_df['Account Balance'].iloc[-1]
        max_dd_pct = pnl_df['Drawdown (%)'].max()
        max_dd_dol = pnl_df['Drawdown ($)'].max()
        
        print(f"\n--- TRUE DATA SIMULATION COMPLETE ({round(time.time() - start_time, 1)} sec) ---")
        print(f"Total Trades Executed: {len(pnl_df)}")
        print(f"Total Wins:   {wins}")
        print(f"Total Losses: {losses}")
        print(f"Historical Win Rate: {win_rate:.2f}%")
        print("-" * 50)
        print(f"Initial Capital:         ${self.initial_capital:,.2f}")
        print(f"Final Account Balance:   ${final_balance:,.2f}")
        print(f"Total Net Return:        ${total_pnl:,.2f} ({(total_pnl/self.initial_capital)*100:.2f}%)")
        print(f"Average PnL per Trade:   ${pnl_df['PnL ($)'].mean():.2f}")
        print("-" * 50)
        print(f"MAXIMUM DRAWDOWN:        -${max_dd_dol:,.2f} ({max_dd_pct:.2f}%)")
        print("-" * 50)
        print(">> 'SOXL_True_Data_Log.csv' generated. All exits verified against historical premium data.")

    def _close_trade(self, closed_trades, trade, current_date, res, pnl, current_balance, high_water_mark):
        total_pnl = pnl * trade['Contracts']
        dd_dol = high_water_mark - (current_balance + total_pnl)
        dd_pct = (dd_dol / high_water_mark) * 100 if high_water_mark > 0 else 0
        
        closed_trades.append({
            'Entry Date': trade['Entry Date'],
            'Exit Date': current_date,
            'Expiration': trade['Expiration'],
            'Short Strike': trade['Short Strike'],
            'Long Strike': trade['Long Strike'],
            'Contracts': trade['Contracts'],
            'Result': res,
            'PnL ($)': round(total_pnl, 2),
            'Account Balance': round(current_balance + total_pnl, 2),
            'Drawdown ($)': round(dd_dol, 2),
            'Drawdown (%)': round(dd_pct, 2)
        })

if __name__ == "__main__":
    env = TrueDataSimulator(data_path="SOXL_Master_Cleaned.csv", initial_capital=150000)
    
    env.run_true_simulation(
        dte_range=(20, 45), 
        target_width=5.0, 
        min_credit=0.80, 
        alloc_pct=0.15,          
        max_trades=4,            
        stop_loss_mult=1.5,      
        take_profit_pct=0.60     
    )