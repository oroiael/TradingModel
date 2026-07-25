import pandas as pd
import numpy as np
import os

class WeeklyCollarBacktester:
    def __init__(self, data_path="SOXL_Master_Cleaned.csv", initial_capital=100000.0, rally_threshold_pct=0.20):
        self.data_path = data_path
        self.initial_capital = initial_capital
        self.trading_balance = initial_capital
        self.cash_vault = 0.0
        
        # Strategy Parameters (Easily Adjustable for Stress Testing)
        self.allocation_pct = 0.25               # 25% of trading capital per cycle
        self.profit_sweep_pct = 0.20             # 20% of net profits swept to Cash Vault
        self.reinvest_pct = 0.80                 # 80% reinvested
        self.put_target_dte = 180                # ~6 months out
        self.call_target_dte = 5                 # Weekly Friday expiration (~5 days)
        self.rally_threshold_pct = rally_threshold_pct # Exposes threshold as 0.20 (20%), etc.
        self.rally_roll_multiplier = 1.0 + rally_threshold_pct # Internal multiplier (1.20)
        
        # State Tracking
        self.open_position = None
        self.trade_logs = []
        self.data = None
        self.options_cache = {}
        self.daily_underlying_map = {}

    def load_and_prep_data(self):
        print(f"Loading master dataset from {self.data_path}...")
        if not os.path.exists(self.data_path):
            print(f"WARNING: File {self.data_path} not found. Generating synthetic test market data...")
            self.generate_synthetic_data()
            return
            
        # low_memory=False resolves mixed Dtype warnings on large option chains
        df = pd.read_csv(self.data_path, low_memory=False)
        
        # --- PRIORITY COLUMN STANDARDIZER ---
        col_map = {}
        cols_lower = {str(c).strip().lower(): c for c in df.columns}
        
        for candidate in ['date', 'quote_date', 'timestamp', 'underlying_timestamp', 'ms_of_day']:
            if candidate in cols_lower:
                col_map[cols_lower[candidate]] = 'Date'
                break
                
        for candidate in ['expiration', 'exp', 'expiry', 'expiration_date']:
            if candidate in cols_lower:
                col_map[cols_lower[candidate]] = 'Expiration'
                break
                
        for candidate in ['strike', 'strike_price']:
            if candidate in cols_lower:
                col_map[cols_lower[candidate]] = 'strike'
                break
                
        for candidate in ['right', 'type', 'option_type', 'put_call']:
            if candidate in cols_lower:
                col_map[cols_lower[candidate]] = 'type'
                break
                
        for candidate in ['close', 'c', 'option_close', 'price']:
            if candidate in cols_lower:
                col_map[cols_lower[candidate]] = 'close'
                break
                
        for candidate in ['underlying_price', 'underlying_close', 'underlying', 'stock_close', 'stock_price']:
            if candidate in cols_lower and cols_lower[candidate] not in col_map:
                col_map[cols_lower[candidate]] = 'underlying_price'
                break
        
        df = df.rename(columns=col_map)
        df = df.loc[:, ~df.columns.duplicated()]
        
        if 'Date' not in df.columns:
            raise KeyError(f"Could not locate a timestamp column in CSV. Found columns: {list(df.columns)}")
            
        # --- TIMEZONE-PROOF DATE PARSING ---
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()
        df = df.dropna(subset=['Date'])
        
        if 'Expiration' in df.columns:
            df['Expiration'] = pd.to_datetime(df['Expiration'], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()
            
        self.data = df.sort_values('Date')
        
        # Build RAM options price cache
        if 'type' in df.columns and 'strike' in df.columns and 'close' in df.columns:
            print("Building RAM options price cache...")
            for _, row in df.iterrows():
                key = (row['Date'], row['Expiration'], str(row['type']).strip().upper()[0], float(row['strike']))
                self.options_cache[key] = row['close']
                
                if 'underlying_price' in row and pd.notna(row['underlying_price']):
                    self.daily_underlying_map[row['Date']] = float(row['underlying_price'])
                elif 'close' in row and 'type' not in row:
                    self.daily_underlying_map[row['Date']] = float(row['close'])
                    
        print(f"Dataset ready. Cached {len(self.options_cache):,} option prints across {len(self.data['Date'].unique()):,} trading days.")

    def generate_synthetic_data(self):
        dates = pd.date_range(start="2023-01-02", end="2026-06-30", freq="B")
        np.random.seed(42)
        prices = [10.0]
        for _ in range(len(dates)-1):
            change = np.random.normal(0.001, 0.03)
            prices.append(max(2.0, prices[-1] * (1 + change)))
        
        df = pd.DataFrame({'Date': dates, 'underlying_price': prices, 'close': prices})
        df['day_name'] = df['Date'].dt.day_name()
        for d, p in zip(dates, prices):
            self.daily_underlying_map[d.normalize()] = p
        self.data = df

    def get_underlying_price(self, date):
        if date in self.daily_underlying_map:
            return self.daily_underlying_map[date]
        day_rows = self.data[self.data['Date'] == date]
        if 'underlying_price' in day_rows.columns and not day_rows['underlying_price'].isna().all():
            return float(day_rows['underlying_price'].dropna().iloc[0])
        return float(day_rows['close'].iloc[0])

    def get_option_price(self, date, expiration, opt_type, strike, underlying_price, dte):
        key = (date, expiration, opt_type.upper()[0], float(strike))
        if key in self.options_cache:
            return self.options_cache[key]
        
        iv = 0.80
        time_yrs = max(1.0, dte) / 365.0
        intrinsic = max(0.0, underlying_price - strike) if opt_type == 'C' else max(0.0, strike - underlying_price)
        extrinsic = underlying_price * iv * np.sqrt(time_yrs) * 0.4 * np.exp(-0.5 * ((strike - underlying_price)/underlying_price)**2)
        return round(intrinsic + extrinsic, 2)

    def run_simulation(self):
        self.load_and_prep_data()
        unique_dates = sorted(self.data['Date'].unique())
        print(f"Running simulation with {int(self.rally_threshold_pct*100)}% Rally Roll Hurdle...")
        
        for curr_date in unique_dates:
            curr_price = self.get_underlying_price(curr_date)
            day_name = pd.to_datetime(curr_date).day_name()
            
            # --- MONDAY AM: ENTRY OR RE-WRITING CALLS ---
            if day_name == 'Monday' or (self.open_position is None and day_name in ['Tuesday', 'Wednesday']):
                if self.open_position is None:
                    self.execute_initial_entry(curr_date, curr_price)
                else:
                    self.write_weekly_call(curr_date, curr_price)
            
            # --- FRIDAY PM (Last 3 Minutes): DECISION & ROLLING LOGIC ---
            elif day_name == 'Friday' and self.open_position is not None:
                self.evaluate_friday_close(curr_date, curr_price)

        self.print_summary()
        self.export_logs()

    def execute_initial_entry(self, date, price):
        atm_strike = round(price * 2) / 2.0
        call_exp = date + pd.Timedelta(days=4)
        put_exp = date + pd.Timedelta(days=self.put_target_dte)
        
        call_credit = self.get_option_price(date, call_exp, 'C', atm_strike, price, 5)
        put_debit = self.get_option_price(date, put_exp, 'P', atm_strike, price, self.put_target_dte)
        
        net_cost_per_share = price + put_debit - call_credit
        if net_cost_per_share <= 0: return
        
        allocated_capital = self.trading_balance * self.allocation_pct
        shares = int((allocated_capital / net_cost_per_share) // 100) * 100
        if shares == 0: return
        
        contracts = shares // 100
        total_debit = shares * net_cost_per_share
        self.trading_balance -= total_debit
        
        self.open_position = {
            'entry_date': date,
            'entry_price': price,
            'shares': shares,
            'contracts': contracts,
            'call_strike': atm_strike,
            'call_exp': call_exp,
            'call_credit': call_credit,
            'put_strike': atm_strike,
            'put_exp': put_exp,
            'put_debit': put_debit,
            'put_current_val': put_debit,
            'total_invested': total_debit,
            'realized_call_gains': call_credit * contracts * 100
        }

    def write_weekly_call(self, date, price):
        pos = self.open_position
        atm_strike = round(price * 2) / 2.0
        call_exp = date + pd.Timedelta(days=4)
        call_credit = self.get_option_price(date, call_exp, 'C', atm_strike, price, 5)
        
        pos['call_strike'] = atm_strike
        pos['call_exp'] = call_exp
        pos['call_credit'] = call_credit
        pos['realized_call_gains'] += (call_credit * pos['contracts'] * 100)
        self.trading_balance += (call_credit * pos['contracts'] * 100)

    def evaluate_friday_close(self, date, price):
        pos = self.open_position
        contracts = pos['contracts']
        shares = pos['shares']
        
        put_dte = max(1, (pos['put_exp'] - date).days)
        current_put_val = self.get_option_price(date, pos['put_exp'], 'P', pos['put_strike'], price, put_dte)
        
        # Check Condition 1: Run-up >= Adjustable Threshold (e.g., 20%)
        run_up_pct = (price - pos['entry_price']) / pos['entry_price']
        
        if run_up_pct >= self.rally_threshold_pct:
            new_put_strike = round(price * 2) / 2.0
            new_put_exp = pos['put_exp'] + pd.Timedelta(days=7)
            new_put_debit = self.get_option_price(date, new_put_exp, 'P', new_put_strike, price, put_dte + 7)
            
            roll_cost = (new_put_debit - current_put_val) * contracts * 100
            self.trading_balance -= roll_cost
            pos['put_strike'] = new_put_strike
            pos['put_exp'] = new_put_exp
            pos['put_current_val'] = new_put_debit
            roll_note = f"ROLLED PUT ATM (+{round(run_up_pct*100,1)}% Rally)"
        else:
            roll_note = "PUT HELD"

        # Check Condition 2: Short Call Assignment (Price >= Call Strike)
        if price >= pos['call_strike']:
            stock_rev = shares * pos['call_strike']
            put_rev = contracts * 100 * current_put_val
            total_rev = stock_rev + put_rev
            
            cycle_pnl = total_rev - pos['total_invested'] + pos['realized_call_gains']
            
            if cycle_pnl > 0:
                sweep_amt = cycle_pnl * self.profit_sweep_pct
                reinvest_amt = cycle_pnl * self.reinvest_pct
                self.cash_vault += sweep_amt
                self.trading_balance += (pos['total_invested'] + reinvest_amt)
            else:
                sweep_amt = 0.0
                self.trading_balance += total_rev
                
            self.log_trade(date, price, "CALLED AWAY (CYCLE COMPLETE)", cycle_pnl, sweep_amt, roll_note)
            self.open_position = None
            
        else:
            if price < pos['put_strike']:
                status_note = "BELOW PUT STRIKE (HOLD & WRITE NEXT MON)"
            else:
                status_note = "CALL EXPIRED OTM (HOLD & WRITE NEXT MON)"
            
            unrealized_pnl = (shares * price) + (contracts * 100 * current_put_val) - pos['total_invested'] + pos['realized_call_gains']
            self.log_trade(date, price, status_note, unrealized_pnl, 0.0, roll_note)

    def log_trade(self, date, price, status, pnl, sweep, note):
        pos = self.open_position
        self.trade_logs.append({
            'Date': date.strftime('%Y-%m-%d'),
            'SOXL_Price': round(price, 2),
            'Status': status,
            'Shares': pos['shares'],
            'Call_Strike': pos['call_strike'],
            'Put_Strike': pos['put_strike'],
            'Put_Exp': pos['put_exp'].strftime('%Y-%m-%d'),
            'Cycle_PnL': round(pnl, 2),
            'Cash_Swept': round(sweep, 2),
            'Trading_Balance': round(self.trading_balance, 2),
            'Cash_Vault': round(self.cash_vault, 2),
            'Total_Net_Worth': round(self.trading_balance + self.cash_vault, 2),
            'Roll_Action': note
        })

    def print_summary(self):
        if not self.trade_logs:
            print("No completed cycles logged.")
            return
            
        df = pd.DataFrame(self.trade_logs)
        completed_cycles = df[df['Status'].str.contains("CALLED AWAY")]
        total_wins = len(completed_cycles[completed_cycles['Cycle_PnL'] > 0])
        total_losses = len(completed_cycles[completed_cycles['Cycle_PnL'] <= 0])
        win_rate = (total_wins / len(completed_cycles) * 100) if len(completed_cycles) > 0 else 0.0
        
        rolls_triggered = len(df[df['Roll_Action'].str.contains("ROLLED PUT ATM")])
        final_worth = self.trading_balance + self.cash_vault
        total_roi = ((final_worth - self.initial_capital) / self.initial_capital) * 100
        
        print("\n========================================================")
        print("          WEEKLY ROLLING COLLAR BACKTEST RESULTS        ")
        print("========================================================")
        print(f"Tested Rally Roll Hurdle: {int(self.rally_threshold_pct*100)}%")
        print(f"Total Weeks Evaluated:    {len(df)}")
        print(f"Full Cycles Completed:    {len(completed_cycles)} (Called Away)")
        print(f"Mid-Cycle Puts Rolled:    {rolls_triggered} Times")
        print(f"Cycle Win Rate:           {win_rate:.2f}% ({total_wins} Wins / {total_losses} Losses)")
        print("--------------------------------------------------------")
        print(f"Initial Capital:          ${self.initial_capital:,.2f}")
        print(f"Final Trading Capital:    ${self.trading_balance:,.2f} (Active Margin)")
        print(f"Final Cash Vault:         ${self.cash_vault:,.2f} (Untouchable Sweeps)")
        print(f"FINAL TOTAL NET WORTH:    ${final_worth:,.2f}")
        print(f"TOTAL SYSTEM ROI:         {total_roi:.2f}%")
        print("========================================================\n")

    def export_logs(self):
        if not self.trade_logs: return
        output_file = f"SOXL_Weekly_Collar_Log_{int(self.rally_threshold_pct*100)}pct.csv"
        pd.DataFrame(self.trade_logs).to_csv(output_file, index=False)
        print(f"Detailed line-by-line trade audit saved to '{output_file}'.")

if __name__ == "__main__":
    # Stress test by modifying rally_threshold_pct (0.20 = 20%, 0.15 = 15%, 0.40 = 40%)
    engine = WeeklyCollarBacktester(
        data_path="SOXL_Master_Cleaned.csv", 
        initial_capital=100000.0, 
        rally_threshold_pct=0.20
    )
    engine.run_simulation()