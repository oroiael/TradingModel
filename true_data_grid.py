import pandas as pd
import warnings
import math
import time

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

class TrueDataGridSearch:
    def __init__(self, data_path, initial_capital=150000):
        self.initial_capital = initial_capital
        print(f"Loading Master Dataset: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)
        
        self.df['Date'] = pd.to_datetime(self.df['date'] if 'date' in self.df.columns else self.df['trade_date'])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        print("Building True Data Options Price Cache in RAM...")
        self.put_df = self.df[self.df['type'].str.upper().isin(['P', 'PUT'])].copy() if 'type' in self.df.columns else self.df[self.df['right'].str.upper().isin(['P', 'PUT'])].copy()
        
        # O(1) Lookup Cache for EXACT Historical Option Prices
        self.options_cache = self.put_df.set_index(['Date', 'Expiration', 'strike'])['close'].to_dict()

        if 'underlying_price' in self.df.columns:
            daily_px = self.df.groupby('Date')['underlying_price'].first().sort_index()
            self.daily_prices = daily_px.to_dict()
            self.sma_50 = daily_px.rolling(window=50).mean().to_dict()
        else:
            self.daily_prices, self.sma_50 = {}, {}
            
        print(f"Engine Ready: {len(self.df)} records cached. ZERO proxies. TRUE option pricing enabled.\n")

    def extract_setups(self, dte_range=(20, 45), target_width=5.0, min_credit=0.80):
        """Extract all valid setups once to feed the simulation loops."""
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
                if 2.50 <= (short_put['strike'] - long_put['strike']) <= target_width:
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
                        'Base Credit_Raw': raw_credit,  
                        'Base Credit': net_credit,
                        'Base Risk': max_risk
                    })
        return pd.DataFrame(setups)

    def simulate_true_data(self, setups_df, require_uptrend, stop_loss_mult, take_profit_pct, alloc_pct, max_trades):
        all_dates = sorted(self.daily_prices.keys())
        max_dataset_date = all_dates[-1]
        
        current_balance = self.initial_capital
        high_water_mark = self.initial_capital
        
        open_trades = []
        closed_trades = []
        
        filtered_setups = setups_df.copy()
        if require_uptrend:
            valid_dates = [d for d in all_dates if self.daily_prices.get(d, 0) > self.sma_50.get(d, float('inf'))]
            filtered_setups = filtered_setups[filtered_setups['Entry Date'].isin(valid_dates)]
            
        if filtered_setups.empty: return 0, 0, 0, 0, current_balance, 0

        setups_by_date = filtered_setups.groupby('Entry Date')

        for current_date in all_dates:
            current_price = self.daily_prices.get(current_date)
            if current_price is None: continue
            
            # Process Open Trades
            still_open = []
            for trade in open_trades:
                
                # TRUE DATA LOOKUP
                curr_short_price = self.options_cache.get((current_date, trade['Expiration'], trade['Short Strike']))
                curr_long_price = self.options_cache.get((current_date, trade['Expiration'], trade['Long Strike']))
                
                if curr_short_price is None or curr_long_price is None:
                    still_open.append(trade)
                    continue
                
                current_spread_cost = curr_short_price - curr_long_price
                
                # Expiration
                if current_date >= trade['Expiration']:
                    if current_price >= trade['Short Strike']:
                        pnl = trade['Base Credit']
                    elif current_price <= trade['Long Strike']:
                        pnl = -trade['Base Risk']
                    else:
                        pnl = trade['Base Credit'] - ((trade['Short Strike'] - current_price) * 100)
                    
                    total_pnl = pnl * trade['Contracts']
                    current_balance += total_pnl
                    if current_balance > high_water_mark: high_water_mark = current_balance
                    closed_trades.append({'PnL': total_pnl, 'Drawdown': high_water_mark - current_balance})

                # EXACT STOP-LOSS
                elif current_spread_cost >= (trade['Base Credit_Raw'] * stop_loss_mult):
                    exact_loss = min((current_spread_cost - trade['Base Credit_Raw']) * 100, trade['Base Risk'])
                    total_pnl = -exact_loss * trade['Contracts']
                    current_balance += total_pnl
                    if current_balance > high_water_mark: high_water_mark = current_balance
                    closed_trades.append({'PnL': total_pnl, 'Drawdown': high_water_mark - current_balance})
                
                # EXACT TAKE-PROFIT
                elif current_spread_cost <= (trade['Base Credit_Raw'] * (1 - take_profit_pct)):
                    exact_profit = (trade['Base Credit_Raw'] - current_spread_cost) * 100
                    total_pnl = exact_profit * trade['Contracts']
                    current_balance += total_pnl
                    if current_balance > high_water_mark: high_water_mark = current_balance
                    closed_trades.append({'PnL': total_pnl, 'Drawdown': high_water_mark - current_balance})
                
                else:
                    still_open.append(trade)
                    
            open_trades = still_open

            # Open New Trades
            if current_date in setups_by_date.groups and len(open_trades) < max_trades:
                setup = setups_by_date.get_group(current_date).iloc[0]
                available_exit_dates = [d for d in all_dates if d <= setup['Expiration']]
                if not available_exit_dates: continue
                target_exit_date = max(available_exit_dates)
                if target_exit_date > max_dataset_date: continue 
                    
                contracts = math.floor((current_balance * alloc_pct) / setup['Base Risk'])
                if contracts >= 1:
                    open_trades.append({
                        'Entry Date': current_date,
                        'Expiration': setup['Expiration'],
                        'Target Exit Date': target_exit_date,
                        'Short Strike': setup['Short Strike'],
                        'Long Strike': setup['Long Strike'],
                        'Base Credit_Raw': setup['Base Credit_Raw'],
                        'Base Credit': setup['Base Credit'],
                        'Base Risk': setup['Base Risk'],
                        'Contracts': contracts
                    })

        pnl_df = pd.DataFrame(closed_trades)
        if pnl_df.empty: return 0, 0, 0, 0, current_balance, 0
        
        wins = len(pnl_df[pnl_df['PnL'] > 0])
        win_rate = (wins / len(pnl_df)) * 100
        net_return = current_balance - self.initial_capital
        roi_pct = (net_return / self.initial_capital) * 100
        max_dd_pct = (pnl_df['Drawdown'].max() / high_water_mark) * 100 if high_water_mark > 0 else 0
        
        return len(pnl_df), win_rate, net_return, roi_pct, current_balance, max_dd_pct

    def run_grid_search(self):
        print("Pre-calculating all valid options setups...")
        all_setups = self.extract_setups()
        if all_setups is None or all_setups.empty:
            print("No valid setups found in data.")
            return

        # ==============================================================
        # THE TRUE DATA MEGA-MATRIX: 1,500 Permutations
        # ==============================================================
        allocations = [0.10, 0.15, 0.20, 0.25, 0.30]
        concurrent_limits = [2, 3, 4, 5, 6]
        take_profits = [0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
        stop_losses = [1.5, 2.0, 2.5, 3.0, 4.0]
        trend_filters = [True, False]

        total_iterations = len(allocations) * len(concurrent_limits) * len(take_profits) * len(stop_losses) * len(trend_filters)
        print(f"Matrix Loaded. Running {total_iterations:,} TRUE DATA permutations. Let the M1 eat...\n")
        
        results = []
        count = 0
        start_time = time.time()

        for trend in trend_filters:
            for tp in take_profits:
                for sl in stop_losses:
                    for alloc in allocations:
                        for max_t in concurrent_limits:
                            count += 1
                            
                            trades, win_rate, net_ret, roi, final_bal, max_dd = self.simulate_true_data(
                                setups_df=all_setups,
                                require_uptrend=trend,
                                stop_loss_mult=sl,
                                take_profit_pct=tp,
                                alloc_pct=alloc,
                                max_trades=max_t
                            )
                            
                            if trades > 0:
                                results.append({
                                    'Uptrend Reqd': trend,
                                    'Take Profit': f"{int(tp*100)}%",
                                    'Stop Loss': f"{sl}x",
                                    'Alloc/Trade': f"{int(alloc*100)}%",
                                    'Max Trades': max_t,
                                    'Total Trades': trades,
                                    'Win Rate %': round(win_rate, 2),
                                    'Max Drawdown %': round(max_dd, 2),
                                    'Total ROI %': round(roi, 2)
                                })
                            
                            if count % 250 == 0:
                                elapsed = round(time.time() - start_time, 1)
                                print(f"Processed {count:,}/{total_iterations:,} iterations... ({elapsed}s elapsed)")

        # Filter out suicidal drawdowns, sort by ROI
        res_df = pd.DataFrame(results)
        
        # Let's filter for strategies that survived with a drawdown under 55%
        viable_df = res_df[res_df['Max Drawdown %'] <= 55.0].sort_values(by='Total ROI %', ascending=False)
        
        viable_df.to_csv("SOXL_TRUE_DATA_Grid_Results.csv", index=False)
        
        end_time = time.time()
        print(f"\nOptimization Complete in {round(end_time - start_time, 1)} seconds.")
        print(f"Exported viable configurations to 'SOXL_TRUE_DATA_Grid_Results.csv'")
        print("\n=== TOP 20 CONFIGURATIONS (TRUE DATA, Drawdown <= 55%) ===")
        print(viable_df.head(20).to_string(index=False))

if __name__ == "__main__":
    optimizer = TrueDataGridSearch(data_path="SOXL_Master_Cleaned.csv", initial_capital=150000)
    optimizer.run_grid_search()