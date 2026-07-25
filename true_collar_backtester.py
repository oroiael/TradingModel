import pandas as pd
import numpy as np
import math
import warnings

# Suppress warnings for cleaner terminal output
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

class TrueCollarBacktester:
    def __init__(self, data_path, starting_capital=150000.0):
        print(f"Loading Master Dataset for True Collar: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)
        
        # Standardize date columns
        date_col = 'date' if 'date' in self.df.columns else 'trade_date'
        self.df['Date'] = pd.to_datetime(self.df[date_col])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        # Create a dictionary of daily underlying prices
        if 'underlying_price' in self.df.columns:
            self.daily_prices = self.df.groupby('Date')['underlying_price'].first().to_dict()
        else:
            print("Error: 'underlying_price' column missing from dataset.")
            self.daily_prices = {}
            
        self.capital = starting_capital
        print(f"Engine Ready. Starting Capital: ${self.capital:,.2f}")

    def run_simulation(self, call_delta_target=0.30, put_delta_target=0.10):
        print("\n--- RUNNING TRUE COLLAR SIMULATION ---")
        print(f"Strategy: Hold SOXL Shares | Sell {call_delta_target} Delta Call | Buy {put_delta_target} Delta Put")
        
        trading_days = sorted(list(self.daily_prices.keys()))
        
        cash = self.capital
        shares = 0
        
        active_call = None
        active_put = None
        
        peak_portfolio = self.capital
        max_drawdown = 0.0
        
        trades_executed = 0

        for current_date in trading_days:
            current_price = self.daily_prices[current_date]
            
            # ---------------------------------------------------
            # 1. EXPIRATION CHECK: Do we need to settle options?
            # ---------------------------------------------------
            if active_call is not None and active_put is not None:
                if current_date >= active_call['Expiration']:
                    if current_price > active_call['Strike']:
                        # Shares called away at the Call Strike
                        cash += shares * active_call['Strike']
                        shares = 0
                    elif current_price < active_put['Strike']:
                        # Put exercised, preventing further disaster
                        cash += shares * active_put['Strike']
                        shares = 0
                    else:
                        # Options expire worthless, we keep the shares and the cash premium
                        pass
                        
                    active_call = None
                    active_put = None

            # ---------------------------------------------------
            # 2. BUY SHARES: If we are in cash, buy back into SOXL
            # ---------------------------------------------------
            if shares == 0 and cash >= current_price * 100:
                # We buy in blocks of 100 shares to legally sell covered calls
                shares_to_buy = math.floor(cash / (current_price * 100)) * 100
                if shares_to_buy > 0:
                    cash -= shares_to_buy * current_price
                    shares = shares_to_buy

            # ---------------------------------------------------
            # 3. APPLY COLLAR: If we have shares, buy put / sell call
            # ---------------------------------------------------
            if shares > 0 and active_call is None and active_put is None:
                daily_ops = self.df[self.df['Date'] == current_date]
                
                # Target ~30 DTE Options
                target_ops = daily_ops[(daily_ops['DTE'] >= 20) & (daily_ops['DTE'] <= 45)]
                
                if not target_ops.empty:
                    # Separate Calls and Puts
                    calls = target_ops[target_ops['type'].str.upper().isin(['C', 'CALL'])] if 'type' in target_ops.columns else target_ops[target_ops['right'].str.upper().isin(['C', 'CALL'])]
                    puts = target_ops[target_ops['type'].str.upper().isin(['P', 'PUT'])] if 'type' in target_ops.columns else target_ops[target_ops['right'].str.upper().isin(['P', 'PUT'])]
                    
                    if not calls.empty and not puts.empty:
                        # Find closest matches to our target Deltas
                        best_call = calls.iloc[(calls['delta'].abs() - call_delta_target).abs().argsort()].iloc[0]
                        best_put = puts.iloc[(puts['delta'].abs() - put_delta_target).abs().argsort()].iloc[0]
                        
                        num_contracts = shares // 100
                        
                        # Calculate Net Premium (Income from Call minus Cost of Put)
                        call_income = best_call['close'] * 100 * num_contracts
                        put_cost = best_put['close'] * 100 * num_contracts
                        net_premium = call_income - put_cost
                        
                        cash += net_premium
                        
                        active_call = {'Expiration': best_call['Expiration'], 'Strike': best_call['strike']}
                        active_put = {'Expiration': best_put['Expiration'], 'Strike': best_put['strike']}
                        trades_executed += 1
            
            # ---------------------------------------------------
            # 4. TRACK DRAWDOWN: Daily Mark-to-Market
            # ---------------------------------------------------
            portfolio_value = cash + (shares * current_price)
            if portfolio_value > peak_portfolio:
                peak_portfolio = portfolio_value
            drawdown = (peak_portfolio - portfolio_value) / peak_portfolio
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Final settlement value on the last day of the dataset
        final_portfolio_value = cash + (shares * self.daily_prices[trading_days[-1]])
        roi = ((final_portfolio_value - self.capital) / self.capital) * 100
        
        print("\n" + "=" * 55)
        print("     TRUE COLLAR SIMULATION RESULTS (3-YEAR)     ")
        print("=" * 55)
        print(f"Total Collars Executed: {trades_executed}")
        print("-" * 55)
        print(f"Starting Capital:       ${self.capital:,.2f}")
        print(f"Final Portfolio Value:  ${final_portfolio_value:,.2f}")
        print(f"Net Profit:             ${(final_portfolio_value - self.capital):,.2f}")
        print(f"Total ROI:              {roi:.2f}%")
        print(f"Max Portfolio Drawdown: {max_drawdown * 100:.2f}%")
        print("=" * 55)

if __name__ == "__main__":
    # Pointing exactly to your validated master dataset
    tester = TrueCollarBacktester("SOXL_Master_Cleaned.csv", starting_capital=150000.0)
    
    # Target 0.30 Delta Call (Income) and 0.10 Delta Put (Insurance)
    tester.run_simulation(call_delta_target=0.30, put_delta_target=0.10)