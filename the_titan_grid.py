import pandas as pd
import warnings
import math
import time
import itertools

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

class UltimateGridSearch:
    def __init__(self, data_path, initial_capital=150000):
        self.initial_capital = initial_capital
        print(f"Loading Master Dataset: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)
        
        self.df['Date'] = pd.to_datetime(self.df['date'] if 'date' in self.df.columns else self.df['trade_date'])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        print("Building True Data Options Price Cache in RAM...")
        self.put_df = self.df[self.df['type'].str.upper().isin(['P', 'PUT'])].copy() if 'type' in self.df.columns else self.df[self.df['right'].str.upper().isin(['P', 'PUT'])].copy()
        
        self.options_cache = self.put_df.set_index(['Date', 'Expiration', 'strike'])['close'].to_dict()

        if 'underlying_price' in self.df.columns:
            daily_px = self.df.groupby('Date')['underlying_price'].first().sort_index()
            self.daily_prices = daily_px.to_dict()
            self.sma_50 = daily_px.rolling(window=50).mean().to_dict()
        else:
            self.daily_prices, self.sma_50 = {}, {}
            
        print(f"Engine Ready. O(1) Hash Map built.\n")

    def extract_structural_setups(self, dte_range, target_width, min_credit):
        trading_days = sorted(self.daily_prices.keys())
        setups = []

        for date in trading_days:
            daily_puts = self.put_df[(self.put_df['Date'] == date) & (self.put_df['DTE'].between(*dte_range))]
            if daily_puts.empty: continue
            
            short_candidates = daily_puts.iloc[(daily_puts['delta'].abs() - 0.20).abs().argsort()]
            long_candidates = daily_puts.iloc[(daily_puts['delta'].abs() - 0.05).abs().argsort()]
            
            if short_candidates.empty or long_candidates.empty: continue
            short_put = short_candidates.iloc[0]
            
            valid_long = None
            for _, long_put in long_candidates.iterrows():
                if short_put['Expiration'] != long_put['Expiration']: continue
                # Allowed widths down to $1.50 to catch $2.00 spreads
                spread_width = short_put['strike'] - long_put['strike']
                if 1.50 <= spread_width <= target_width:
                    valid_long = long_put
                    break
            
            if valid_long is None: continue

            raw_credit = short_put['close'] - valid_long['close']
            net_credit = raw_credit * 100
            
            if net_credit >= (min_credit * 100):
                max_risk = ((short_put['strike'] - valid_long['strike']) * 100) - net_credit
                if max_risk > 0:
                    setups.append({
                        'Entry Date': pd.to_datetime(date), 
                        'Expiration': short_put['Expiration'],
                        'Short Strike': short_put['strike'],
                        'Long Strike': valid_long['strike'],
                        'Entry Short Price': short_put['close'],
                        'Entry Long Price': valid_long['close'],
                        'Base Credit_Raw': raw_credit,  
                        'Base Credit': net_credit,
                        'Base Risk': max_risk
                    })
        return pd.DataFrame(setups)

    def simulate_true_data(self, setups_df, require_uptrend, stop_loss_mult, take_profit_pct, alloc_pct, max_trades, sweep_pct, max_contracts=300):
        all_dates = sorted(self.daily_prices.keys())
        max_dataset_date = all_dates[-1]
        
        trading_balance = self.initial_capital
        swept_cash = 0.0
        high_water_mark = self.initial_capital
        
        open_trades = []
        closed_trades = []
        
        filtered_setups = setups_df.copy()
        if require_uptrend:
            valid_dates = [d for d in all_dates if self.daily_prices.get(d, 0) > self.sma_50.get(d, float('inf'))]
            filtered_setups = filtered_setups[filtered_setups['Entry Date'].isin(valid_dates)]
            
        if filtered_setups.empty: return 0, 0, 0, 0, self.initial_capital, 0, 0

        setups_by_date = filtered_setups.groupby('Entry Date')

        for current_date in all_dates:
            current_price = self.daily_prices.get(current_date)
            if current_price is None: continue
            
            # --- PROCESS OPEN TRADES ---
            still_open = []
            for trade in open_trades:
                curr_short_price = self.options_cache.get((current_date, trade['Expiration'], trade['Short Strike']))
                curr_long_price = self.options_cache.get((current_date, trade['Expiration'], trade['Long Strike']))
                
                if current_date >= trade['Expiration'] and (curr_short_price is None or curr_long_price is None):
                    curr_short_price = max(0, trade['Short Strike'] - current_price)
                    curr_long_price = max(0, trade['Long Strike'] - current_price)
                elif curr_short_price is None or curr_long_price is None:
                    still_open.append(trade)
                    continue
                
                current_spread_cost = curr_short_price - curr_long_price
                is_closed = False
                
                if current_date >= trade['Expiration']: is_closed = True
                elif current_spread_cost >= (trade['Base Credit_Raw'] * stop_loss_mult): is_closed = True
                elif current_spread_cost <= (trade['Base Credit_Raw'] * (1 - take_profit_pct)): is_closed = True
                
                if is_closed:
                    short_pnl = (trade['Entry Short Price'] - curr_short_price) * 100
                    long_pnl = (curr_long_price - trade['Entry Long Price']) * 100
                    combined_pnl = (short_pnl + long_pnl) * trade['Contracts']
                    
                    sweep_amount = 0.0
                    if combined_pnl > 0:
                        if trade['Contracts'] >= max_contracts: sweep_amount = combined_pnl
                        else: sweep_amount = combined_pnl * sweep_pct
                            
                        swept_cash += sweep_amount
                        trading_balance += (combined_pnl - sweep_amount)
                    else:
                        trading_balance += combined_pnl

                    total_net_worth = trading_balance + swept_cash
                    if total_net_worth > high_water_mark: high_water_mark = total_net_worth
                    
                    closed_trades.append({'PnL': combined_pnl, 'Drawdown': high_water_mark - total_net_worth})
                else:
                    still_open.append(trade)
                    
            open_trades = still_open

            # --- OPEN NEW TRADES ---
            if current_date in setups_by_date.groups and len(open_trades) < max_trades:
                setup = setups_by_date.get_group(current_date).iloc[0]
                available_exit_dates = [d for d in all_dates if d <= setup['Expiration']]
                if not available_exit_dates: continue
                if max(available_exit_dates) > max_dataset_date: continue 
                    
                contracts = math.floor((trading_balance * alloc_pct) / setup['Base Risk'])
                if contracts > max_contracts: contracts = max_contracts
                
                if contracts >= 1:
                    open_trades.append({
                        'Entry Date': current_date,
                        'Expiration': setup['Expiration'],
                        'Short Strike': setup['Short Strike'],
                        'Long Strike': setup['Long Strike'],
                        'Entry Short Price': setup['Entry Short Price'],
                        'Entry Long Price': setup['Entry Long Price'],
                        'Base Credit_Raw': setup['Base Credit_Raw'],
                        'Contracts': contracts
                    })

        pnl_df = pd.DataFrame(closed_trades)
        if pnl_df.empty: return 0, 0, 0, 0, self.initial_capital, 0, 0
        
        wins = len(pnl_df[pnl_df['PnL'] > 0])
        win_rate = (wins / len(pnl_df)) * 100
        total_net_worth = trading_balance + swept_cash
        net_return = total_net_worth - self.initial_capital
        roi_pct = (net_return / self.initial_capital) * 100
        max_dd_pct = (pnl_df['Drawdown'].max() / high_water_mark) * 100 if high_water_mark > 0 else 0
        
        return len(pnl_df), win_rate, net_return, roi_pct, total_net_worth, swept_cash, max_dd_pct

    def run_ultimate_grid(self):
        # 1. Structural Arrays
        dte_ranges = [(10, 30), (20, 45), (30, 60)]
        widths = [2.0, 3.0, 4.0, 5.0, 6.0]
        credits = [0.40, 0.55, 0.70, 0.85, 1.00, 1.15]
        
        # 2. Execution Arrays
        allocations = [0.10, 0.15, 0.25, 0.50]
        concurrent_limits = [1, 2, 3, 4, 5]
        # 25% to 85% in 5% increments
        take_profits = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
        stop_losses = [1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
        trend_filters = [True, False]
        sweeps = [0.0, 0.05, 0.10, 0.15, 0.20]

        total_structural = len(dte_ranges) * len(widths) * len(credits)
        total_execution = len(allocations) * len(concurrent_limits) * len(take_profits) * len(stop_losses) * len(trend_filters) * len(sweeps)
        grand_total = total_structural * total_execution
        
        print(f"ULTIMATE MATRIX INITIATED.")
        print(f"Total True Data Permutations: {grand_total:,}")
        print("This will process ~140,000 simulations. Hang tight...\n")
        
        results = []
        count = 0
        start_time = time.time()

        for dte in dte_ranges:
            for width in widths:
                for min_c in credits:
                    setups_df = self.extract_structural_setups(dte, width, min_c)
                    
                    if setups_df.empty:
                        count += total_execution
                        continue
                        
                    for alloc, max_t, tp, sl, trend, sweep in itertools.product(allocations, concurrent_limits, take_profits, stop_losses, trend_filters, sweeps):
                        count += 1
                        
                        trades, win_rate, net_ret, roi, total_nw, vaulted, max_dd = self.simulate_true_data(
                            setups_df=setups_df,
                            require_uptrend=trend,
                            stop_loss_mult=sl,
                            take_profit_pct=tp,
                            alloc_pct=alloc,
                            max_trades=max_t,
                            sweep_pct=sweep
                        )
                        
                        if trades > 0:
                            results.append({
                                'DTE': f"{dte[0]}-{dte[1]}",
                                'Width': f"${width}",
                                'Min Credit': f"${min_c}",
                                'Uptrend': trend,
                                'Take Profit': f"{int(tp*100)}%",
                                'Stop Loss': f"{sl}x",
                                'Alloc': f"{int(alloc*100)}%",
                                'Max Trades': max_t,
                                'Sweep': f"{int(sweep*100)}%",
                                'Trades': trades,
                                'Win Rate %': round(win_rate, 2),
                                'Max DD %': round(max_dd, 2),
                                'Vault Cash $': round(vaulted, 2),
                                'Total ROI %': round(roi, 2)
                            })
                            
                        if count % 2000 == 0:
                            elapsed = round(time.time() - start_time, 1)
                            speed = count / elapsed if elapsed > 0 else 0
                            remaining_sec = (grand_total - count) / speed if speed > 0 else 0
                            print(f"Processed {count:,}/{grand_total:,} ... (ETA: {round(remaining_sec/60, 1)} min)")

        # Dump ALL results to CSV (No Drawdown Filter)
        res_df = pd.DataFrame(results)
        res_df = res_df.sort_values(by='Total ROI %', ascending=False)
        res_df.to_csv("SOXL_ULTIMATE_GRID.csv", index=False)
        
        end_time = time.time()
        print(f"\nOptimization Complete in {round((end_time - start_time)/60, 2)} minutes.")
        print(f"Exported ALL {len(res_df):,} executed configurations to 'SOXL_ULTIMATE_GRID.csv'")
        
        # Display top 10 viable to terminal
        viable_df = res_df[res_df['Max DD %'] <= 35.0]
        print("\n=== TOP 10 VIABLE CONFIGURATIONS (Drawdown <= 35%) ===")
        if not viable_df.empty:
            print(viable_df.head(10).to_string(index=False))
        else:
            print("No configurations met the < 35% drawdown threshold. Check the CSV for full list.")

if __name__ == "__main__":
    optimizer = UltimateGridSearch(data_path="SOXL_Master_Cleaned.csv", initial_capital=150000)
    optimizer.run_ultimate_grid()