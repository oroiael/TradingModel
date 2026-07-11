import pandas as pd
import numpy as np
import os

class HybridCollarBacktester:
    def __init__(self, 
                 options_path="SOXL_Master_Cleaned.csv", 
                 intraday_path="SOXL_5min_3Years.csv",
                 initial_capital=100000.0, 
                 rally_threshold_pct=0.20):
        
        self.options_path = options_path
        self.intraday_path = intraday_path
        self.initial_capital = initial_capital
        self.trading_balance = initial_capital
        self.cash_vault = 0.0
        
        # Strategy Parameters
        self.allocation_pct = 0.25               
        self.profit_sweep_pct = 0.10             
        self.reinvest_pct = 0.90                 
        self.put_target_dte = 180                
        self.call_target_dte = 5                 
        self.rally_threshold_pct = rally_threshold_pct
        
        # State Tracking
        self.open_position = None
        self.trade_logs = []
        self.options_cache = {}
        self.intraday_data = None
        self.trading_days = []

    def load_and_prep_data(self):
        print(f"Loading 5-minute intraday stock data from {self.intraday_path}...")
        if not os.path.exists(self.intraday_path):
            raise FileNotFoundError(f"Cannot find {self.intraday_path}. Please ensure it is in the working directory.")
            
        # 1. Load IBKR 5-Minute Intraday Data
        df_5m = pd.read_csv(self.intraday_path, low_memory=False)
        
        # Standardize timestamp column names
        col_map_5m = {}
        for col in df_5m.columns:
            c_low = str(col).strip().lower()
            if c_low in ['date', 'datetime', 'time', 'timestamp', 'bar_time']:
                col_map_5m[col] = 'Datetime'
            elif c_low in ['close', 'c', 'price', 'last']:
                col_map_5m[col] = 'close'
        df_5m = df_5m.rename(columns=col_map_5m)
        
        if 'Datetime' not in df_5m.columns:
            print(f"CRITICAL ERROR: No valid time column found in {self.intraday_path}. Found columns: {list(df_5m.columns)}")
            return

        # --- BULLETPROOF IBKR TIMESTAMP PARSER ---
        df_5m = df_5m.dropna(subset=['Datetime', 'close'])
        raw_dates = df_5m['Datetime'].astype(str).str.strip()
        
        # 1. Normalize spaces (fix IBKR double-spaces)
        raw_dates = raw_dates.str.replace(r'\s+', ' ', regex=True)
        # 2. Strip rogue timezone tags (e.g., "US/Eastern", "America/New_York")
        raw_dates = raw_dates.str.replace(r' [a-zA-Z_]+/[a-zA-Z_]+$', '', regex=True)
        
        # Multi-stage parsing attempt
        # Attempt 1: Explicitly known IBKR format: YYYYMMDD HH:MM:SS
        parsed_dates = pd.to_datetime(raw_dates, format='%Y%m%d %H:%M:%S', errors='coerce', utc=True)
        
        # Attempt 2: Fallback Standard YYYY-MM-DD HH:MM:SS
        if parsed_dates.isna().any():
            parsed_dates = parsed_dates.fillna(pd.to_datetime(raw_dates, format='%Y-%m-%d %H:%M:%S', errors='coerce', utc=True))
            
        # Attempt 3: UNIX timestamp fallback (10 or 13 digits)
        if parsed_dates.isna().any():
            unix_mask = raw_dates.str.match(r'^\d+$')
            if unix_mask.any():
                temp_unix = pd.to_datetime(raw_dates[unix_mask].astype(float), unit='s', utc=True)
                parsed_dates.loc[unix_mask] = temp_unix
                
        # Attempt 4: Pandas generic guess for anything remaining
        if parsed_dates.isna().any():
            parsed_dates = parsed_dates.fillna(pd.to_datetime(raw_dates, errors='coerce', utc=True))
            
        # --- DIAGNOSTIC CHECK ---
        if parsed_dates.isna().all():
            print("\n=======================================================")
            print("CRITICAL PARSING ERROR: Could not read the timestamps.")
            print("Here is exactly what the first 5 rows of your Date column look like:")
            print(df_5m['Datetime'].head(5).tolist())
            print("=======================================================\n")
            return
            
        # Strip UTC wrapper for clean midnight normalizations
        df_5m['Datetime'] = parsed_dates.dt.tz_localize(None)
        
        # Drop completely invalid rows and sort chronologically
        df_5m = df_5m.dropna(subset=['Datetime']).sort_values('Datetime')
        df_5m['Date'] = df_5m['Datetime'].dt.normalize()
        
        self.intraday_data = df_5m
        self.trading_days = sorted(df_5m['Date'].unique())
        print(f"Loaded {len(df_5m):,} 5-minute bars across {len(self.trading_days)} trading days.")

        # 2. Load ThetaData EOD Options Data
        print(f"Loading options chains from {self.options_path}...")
        if not os.path.exists(self.options_path):
            print(f"WARNING: File {self.options_path} not found.")
            return

        df_opt = pd.read_csv(self.options_path, low_memory=False)
        col_map_opt = {}
        for col in df_opt.columns:
            c_low = str(col).strip().lower()
            if c_low in ['date', 'quote_date', 'timestamp', 'underlying_timestamp']:
                col_map_opt[col] = 'Date'
            elif c_low in ['expiration', 'exp', 'expiry', 'expiration_date']:
                col_map_opt[col] = 'Expiration'
            elif c_low in ['strike', 'strike_price']:
                col_map_opt[col] = 'strike'
            elif c_low in ['right', 'type', 'option_type', 'put_call']:
                col_map_opt[col] = 'type'
            elif c_low in ['close', 'c', 'option_close', 'price']:
                col_map_opt[col] = 'close'
                
        df_opt = df_opt.rename(columns=col_map_opt)
        df_opt = df_opt.loc[:, ~df_opt.columns.duplicated()]
        df_opt['Date'] = pd.to_datetime(df_opt['Date'], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()
        df_opt = df_opt.dropna(subset=['Date'])
        
        if 'Expiration' in df_opt.columns:
            df_opt['Expiration'] = pd.to_datetime(df_opt['Expiration'], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()

        print("Caching RAM option chain dictionary...")
        if 'type' in df_opt.columns and 'strike' in df_opt.columns and 'close' in df_opt.columns:
            for _, row in df_opt.iterrows():
                key = (row['Date'], row['Expiration'], str(row['type']).strip().upper()[0], float(row['strike']))
                self.options_cache[key] = row['close']
        print(f"Options cache ready ({len(self.options_cache):,} contracts indexed).")

    def get_intraday_price(self, date, target_hour, target_minute):
        """Fetches the exact 5-minute stock price closest to target timestamp (e.g. 09:35 or 15:55)."""
        day_bars = self.intraday_data[self.intraday_data['Date'] == date]
        if day_bars.empty:
            return None
            
        target_time = date + pd.Timedelta(hours=target_hour, minutes=target_minute)
        time_diffs = (day_bars['Datetime'] - target_time).abs()
        closest_idx = time_diffs.idxmin()
        return float(day_bars.loc[closest_idx, 'close'])

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
        if not self.trading_days:
            print("\nError: No trading days loaded. Cannot run simulation.")
            return
            
        print(f"\nStarting Hybrid Simulation (Rally Hurdle: {int(self.rally_threshold_pct*100)}%)...")
        
        for curr_date in self.trading_days:
            day_name = pd.to_datetime(curr_date).day_name()
            
            # --- MONDAY AM: EXECUTE AT 09:35 AM BAR ---
            if day_name == 'Monday' or (self.open_position is None and day_name in ['Tuesday', 'Wednesday']):
                am_price = self.get_intraday_price(curr_date, target_hour=9, target_minute=35)
                if am_price is None: continue
                
                if self.open_position is None:
                    self.execute_initial_entry(curr_date, am_price)
                else:
                    self.write_weekly_call(curr_date, am_price)
            
            # --- FRIDAY PM: EVALUATE AT 15:55 PM (3:55 PM) BAR ---
            elif day_name == 'Friday' and self.open_position is not None:
                pm_price = self.get_intraday_price(curr_date, target_hour=15, target_minute=55)
                if pm_price is None: continue
                self.evaluate_friday_close(curr_date, pm_price)

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
            roll_note = f"ROLLED PUT ATM (+{round(run_up_pct*100,1)}% at 15:55)"
        else:
            roll_note = "PUT HELD"

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
            'SOXL_5min_Trigger_Price': round(price, 2),
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
        print("       HYBRID 5-MIN ROLLING COLLAR BACKTEST RESULTS     ")
        print("========================================================")
        print(f"Intraday Source File:     {self.intraday_path}")
        print(f"Tested Rally Roll Hurdle: {int(self.rally_threshold_pct*100)}%")
        print(f"Total Weeks Evaluated:    {len(df)}")
        print(f"Full Cycles Completed:    {len(completed_cycles)} (Called Away at 15:55 PM)")
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
        output_file = f"SOXL_Hybrid_Collar_Log_{int(self.rally_threshold_pct*100)}pct.csv"
        pd.DataFrame(self.trade_logs).to_csv(output_file, index=False)
        print(f"Detailed 5-minute execution audit saved to '{output_file}'.")

if __name__ == "__main__":
    engine = HybridCollarBacktester(
        options_path="SOXL_Master_Cleaned.csv", 
        intraday_path="SOXL_5min_3Years.csv",
        initial_capital=100000.0, 
        rally_threshold_pct=0.10 
    )
    engine.run_simulation()