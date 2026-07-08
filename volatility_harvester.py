import pandas as pd
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

class SOXLVolatilityHarvester:
    def __init__(self, data_path):
        print(f"Loading Master Dataset from: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)
        
        self.df['Date'] = pd.to_datetime(self.df['date'] if 'date' in self.df.columns else self.df['trade_date'])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        # Create a quick lookup for daily underlying prices
        if 'underlying_price' in self.df.columns:
            self.daily_prices = self.df.groupby('Date')['underlying_price'].first().to_dict()
        else:
            self.daily_prices = {}
            
        print(f"Engine Ready: {len(self.df)} clean records loaded.")

    def run_production_backtest(self, dte_range=(20, 45), target_width=5.0, min_credit=0.50):
        print(f"\n--- 1. BUILDING TRADE SETUPS ---")
        puts = self.df[self.df['type'].str.upper().isin(['P', 'PUT'])].copy() if 'type' in self.df.columns else self.df[self.df['right'].str.upper().isin(['P', 'PUT'])].copy()
        
        trading_days = puts['Date'].unique()
        trades = []

        for date in trading_days:
            daily = puts[(puts['Date'] == date) & (puts['DTE'].between(*dte_range))]
            if daily.empty: continue
            
            short_candidates = daily.iloc[(daily['delta'].abs() - 0.20).abs().argsort()]
            long_candidates = daily.iloc[(daily['delta'].abs() - 0.05).abs().argsort()]
            
            if short_candidates.empty or long_candidates.empty: continue
            
            short_put = short_candidates.iloc[0]
            
            valid_long = None
            for _, long_put in long_candidates.iterrows():
                spread_width = short_put['strike'] - long_put['strike']
                if 2.50 <= spread_width <= target_width:
                    valid_long = long_put
                    break
            
            if valid_long is None: continue

            net_credit = (short_put['close'] - valid_long['close']) * 100
            if net_credit >= (min_credit * 100):
                actual_width = short_put['strike'] - valid_long['strike']
                max_risk = (actual_width * 100) - net_credit
                
                if max_risk > 0:
                    trades.append({
                        'Entry Date': pd.to_datetime(date), 
                        'Expiration': short_put['Expiration'],
                        'DTE': short_put['DTE'],
                        'Short Strike': short_put['strike'],
                        'Long Strike': valid_long['strike'],
                        'Net Credit': net_credit, 
                        'Max Risk': max_risk
                    })

        if not trades:
            return None
            
        return pd.DataFrame(trades)

    def simulate_outcomes(self, trades_df):
        print(f"\n--- 2. SIMULATING TRADE OUTCOMES (PnL) ---")
        if not self.daily_prices:
            print("Error: 'underlying_price' column missing. Cannot simulate outcomes.")
            return

        results = []
        for _, trade in trades_df.iterrows():
            exp_date = trade['Expiration']
            
            # Find the underlying price at or right before expiration
            available_dates = [d for d in self.daily_prices.keys() if d <= exp_date]
            if not available_dates:
                continue
                
            exit_date = max(available_dates)
            settlement_price = self.daily_prices[exit_date]
            
            # Put Credit Spread Logic at Expiration:
            # If SOXL ends ABOVE short strike, we keep the full credit.
            if settlement_price >= trade['Short Strike']:
                pnl = trade['Net Credit']
                result = "WIN"
            # If SOXL ends BELOW long strike, we take the max loss.
            elif settlement_price <= trade['Long Strike']:
                pnl = -trade['Max Risk']
                result = "MAX LOSS"
            # If it ends between the strikes, partial loss/win
            else:
                intrinsic_value = (trade['Short Strike'] - settlement_price) * 100
                pnl = trade['Net Credit'] - intrinsic_value
                result = "PARTIAL"

            results.append({
                'Entry Date': trade['Entry Date'].strftime('%Y-%m-%d'),
                'Expiration': exp_date.strftime('%Y-%m-%d'),
                'Short Strike': trade['Short Strike'],
                'Settlement Price': round(settlement_price, 2),
                'Result': result,
                'PnL ($)': round(pnl, 2)
            })
            
        pnl_df = pd.DataFrame(results)
        
        wins = len(pnl_df[pnl_df['PnL ($)'] > 0])
        losses = len(pnl_df[pnl_df['PnL ($)'] <= 0])
        win_rate = (wins / len(pnl_df)) * 100
        total_pnl = pnl_df['PnL ($)'].sum()
        
        print(f"Total Trades Evaluated: {len(pnl_df)}")
        print(f"Total Wins:   {wins}")
        print(f"Total Losses: {losses}")
        print(f"Historical Win Rate: {win_rate:.2f}%")
        print("-" * 40)
        print(f"TOTAL SYSTEM PnL (1 Contract): ${total_pnl:,.2f}")
        print(f"Average PnL per Trade:         ${pnl_df['PnL ($)'].mean():.2f}")
        print("-" * 40)
        
if __name__ == "__main__":
    env = SOXLVolatilityHarvester("SOXL_Master_Cleaned.csv")
    report = env.run_production_backtest()
    
    if report is not None:
        env.simulate_outcomes(report)