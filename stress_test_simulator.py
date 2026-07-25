import pandas as pd
import warnings
import math
import time
import yfinance as yf
from datetime import timedelta

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')
warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')

class IntradayStressTestSimulator:
    def __init__(self, data_path, initial_capital=150000):
        self.initial_capital = initial_capital
        print(f"Loading Master Dataset: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)
        
        self.df['Date'] = pd.to_datetime(self.df['date'] if 'date' in self.df.columns else self.df['trade_date'])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        # --- 1. BUILD OPTIONS CACHE ---
        print("Building True Data Options Price Cache in RAM...")
        self.put_df = self.df[self.df['type'].str.upper().isin(['P', 'PUT'])].copy() if 'type' in self.df.columns else self.df[self.df['right'].str.upper().isin(['P', 'PUT'])].copy()
        self.options_cache = self.put_df.set_index(['Date', 'Expiration', 'strike'])['close'].to_dict()

        if 'underlying_price' in self.df.columns:
            daily_px = self.df.groupby('Date')['underlying_price'].first().sort_index()
            self.daily_prices = daily_px.to_dict()
            self.sma_50 = daily_px.rolling(window=50).mean().to_dict()
        else:
            self.daily_prices, self.sma_50 = {}, {}

        # --- 2. FETCH YAHOO FINANCE INTRADAY DATA ---
        min_date = self.df['Date'].min() - timedelta(days=5)
        max_date = self.df['Date'].max() + timedelta(days=5)
        print(f"Fetching Intraday SOXL Stress Data from Yahoo Finance ({min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')})...")
        
        soxl_data = yf.download("SOXL", start=min_date.strftime('%Y-%m-%d'), end=max_date.strftime('%Y-%m-%d'), progress=False)
        
        # Handle yfinance multi-index vs single-index output changes
        if isinstance(soxl_data.columns, pd.MultiIndex):
            lows = soxl_data['Low']['SOXL']
        else:
            lows = soxl_data['Low']
            
        # Map localized timezone dates to flat dates to match your CSV
        lows.index = pd.to_datetime(lows.index).tz_localize(None).normalize()
        self.daily_lows = lows.to_dict()
            
        print(f"Engine Ready: EOD Options Pricing + Intraday Stock Lows loaded.\n")

    def run_stress_simulation(self, dte_range=(30, 60), target_width=5.0, min_credit=1.00, 
                              alloc_pct=0.20, max_trades=5, stop_loss_mult=3.0, 
                              take_profit_pct=0.35, require_uptrend=False, 
                              base_sweep_pct=0.10, max_contracts=300, slippage_per_leg=0.05):
                       
        print("--- EXECUTING INTRADAY STRESS TEST (W/ SLIPPAGE) ---")
        trading_days = sorted(self.daily_prices.keys())
        
        trading_balance = self.initial_capital
        swept_cash = 0.0
        high_water_mark = self.initial_capital
        
        open_trades = []
        closed_trades = []
        
        start_time = time.time()

        for current_date in trading_days:
            current_underlying_price = self.daily_prices.get(current_date)
            current_underlying_low = self.daily_lows.get(current_date)
            current_sma = self.sma_50.get(current_date)
            
            # Fallback to EOD price if Yahoo Finance misses a day
            if pd.isna(current_underlying_low):
                current_underlying_low = current_underlying_price
            if pd.isna(current_sma): continue
            
            # ==========================================
            # 1. PROCESS OPEN TRADES
            # ==========================================
            still_open = []
            for trade in open_trades:
                
                # A. CHECK THE INTRADAY TRIPWIRE FIRST
                if current_underlying_low <= trade['Short Strike']:
                    # Intraday crash hit our strike! Trigger instant 3.0x loss + Slippage
                    exact_cost_to_close = trade['Entry Net Credit'] * stop_loss_mult
                    gross_loss_per_contract = exact_cost_to_close - trade['Entry Net Credit']
                    
                    # Apply slippage on the exit
                    net_loss_per_contract = (gross_loss_per_contract + (slippage_per_leg * 2)) * 100
                    
                    # Cap at Max Risk just in case
                    net_loss_per_contract = min(net_loss_per_contract, trade['Base Risk'])
                    total_combined_pnl = -net_loss_per_contract * trade['Contracts']
                    
                    trading_balance += total_combined_pnl
                    self._log_trade(closed_trades, trade, current_date, "INTRADAY TRIPWIRE (STOP-LOSS)", total_combined_pnl, trading_balance, swept_cash, high_water_mark)
                    continue

                # B. NO INTRADAY CRASH -> CHECK EOD OPTIONS PRICING
                curr_short_price = self.options_cache.get((current_date, trade['Expiration'], trade['Short Strike']))
                curr_long_price = self.options_cache.get((current_date, trade['Expiration'], trade['Long Strike']))
                
                if current_date >= trade['Expiration'] and (curr_short_price is None or curr_long_price is None):
                    curr_short_price = max(0, trade['Short Strike'] - current_underlying_price)
                    curr_long_price = max(0, trade['Long Strike'] - current_underlying_price)
                elif curr_short_price is None or curr_long_price is None:
                    still_open.append(trade)
                    continue
                
                current_spread_cost = curr_short_price - curr_long_price
                is_closed = False
                res_reason = ""
                
                if current_date >= trade['Expiration']:
                    is_closed = True
                    res_reason = "EXPIRATION"
                elif current_spread_cost <= (trade['Entry Net Credit'] * (1 - take_profit_pct)):
                    is_closed = True
                    res_reason = f"TAKE-PROFIT ({int(take_profit_pct*100)}%)"

                if is_closed:
                    gross_pnl_per_contract = (trade['Entry Net Credit'] - current_spread_cost) * 100
                    
                    # Apply slippage to the exit
                    net_pnl_per_contract = gross_pnl_per_contract - (slippage_per_leg * 2 * 100)
                    total_combined_pnl = net_pnl_per_contract * trade['Contracts']
                    
                    sweep_amount = 0.0
                    if total_combined_pnl > 0:
                        if trade['Contracts'] >= max_contracts:
                            sweep_amount = total_combined_pnl
                        else:
                            sweep_amount = total_combined_pnl * base_sweep_pct
                            
                        swept_cash += sweep_amount
                        trading_balance += (total_combined_pnl - sweep_amount)
                    else:
                        trading_balance += total_combined_pnl

                    self._log_trade(closed_trades, trade, current_date, res_reason, total_combined_pnl, trading_balance, swept_cash, high_water_mark)
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

                net_credit_raw = short_put['close'] - valid_long['close']
                
                if (net_credit_raw * 100) >= (min_credit * 100):
                    # Account for slippage on ENTRY
                    net_credit_realized = (net_credit_raw - (slippage_per_leg * 2))
                    max_risk_raw = (short_put['strike'] - valid_long['strike']) - net_credit_realized
                    max_risk_dollars = max_risk_raw * 100
                    
                    if max_risk_dollars > 0:
                        contracts = math.floor((trading_balance * alloc_pct) / max_risk_dollars)
                        if contracts > max_contracts: contracts = max_contracts
                            
                        if contracts >= 1:
                            open_trades.append({
                                'Entry Date': current_date,
                                'Expiration': short_put['Expiration'],
                                'Short Strike': short_put['strike'],
                                'Long Strike': valid_long['strike'],
                                'Entry Net Credit': net_credit_raw, # Use raw for trigger math
                                'Base Risk': max_risk_dollars,
                                'Contracts': contracts
                            })

        # --- FINAL REPORTING ---
        pnl_df = pd.DataFrame(closed_trades)
        if pnl_df.empty:
            print("No trades executed.")
            return

        for col in ['Entry Date', 'Exit Date', 'Expiration']:
            pnl_df[col] = pd.to_datetime(pnl_df[col]).dt.strftime('%Y-%m-%d')
            
        pnl_df.to_csv('SOXL_Stress_Test_Log.csv', index=False)
        
        wins = len(pnl_df[pnl_df['Total Trade PnL'] > 0])
        losses = len(pnl_df[pnl_df['Total Trade PnL'] <= 0])
        tripwire_hits = len(pnl_df[pnl_df['Reason'] == "INTRADAY TRIPWIRE (STOP-LOSS)"])
        win_rate = (wins / len(pnl_df)) * 100
        
        final_trading_bal = pnl_df['Trading Balance'].iloc[-1]
        final_swept_cash = pnl_df['Cash Vault'].iloc[-1]
        final_total_account = pnl_df['Total Account Value'].iloc[-1]
        
        total_pnl_dollars = final_total_account - self.initial_capital
        total_roi = (total_pnl_dollars / self.initial_capital) * 100
        max_dd_pct = pnl_df['Drawdown (%)'].max()
        
        print(f"\n--- STRESS TEST COMPLETE ({round(time.time() - start_time, 1)} sec) ---")
        print(f"Total Trades Executed: {len(pnl_df)}")
        print(f"Total Wins:            {wins}")
        print(f"Total Losses:          {losses} (Intraday Tripwire Hits: {tripwire_hits})")
        print(f"Stress-Tested Win Rate:{win_rate:.2f}%")
        print("-" * 60)
        print(f"Initial Capital:         ${self.initial_capital:,.2f}")
        print(f"Final Trading Balance:   ${final_trading_bal:,.2f} (Margin at Risk)")
        print(f"Final Cash Vault:        ${final_swept_cash:,.2f} (Safe, Swept Profits)")
        print(f"Final Total Net Worth:   ${final_total_account:,.2f}")
        print(f"Total Net Return:        ${total_pnl_dollars:,.2f} ({total_roi:.2f}%)")
        print("-" * 60)
        print(f"STRESS MAX DRAWDOWN:     {max_dd_pct:.2f}%")
        print("-" * 60)

    def _log_trade(self, closed_trades, trade, current_date, res_reason, total_combined_pnl, trading_balance, swept_cash, high_water_mark):
        total_net_worth = trading_balance + swept_cash
        if total_net_worth > high_water_mark:
            high_water_mark = total_net_worth
        
        drawdown_dol = high_water_mark - total_net_worth
        drawdown_pct = (drawdown_dol / high_water_mark) * 100 if high_water_mark > 0 else 0
        
        closed_trades.append({
            'Entry Date': trade['Entry Date'],
            'Exit Date': current_date,
            'Expiration': trade['Expiration'],
            'Reason': res_reason,
            'Contracts': trade['Contracts'],
            'Short Strike': trade['Short Strike'],
            'Long Strike': trade['Long Strike'],
            'Total Trade PnL': round(total_combined_pnl, 2),
            'Trading Balance': round(trading_balance, 2),
            'Cash Vault': round(swept_cash, 2),
            'Total Account Value': round(total_net_worth, 2),
            'Drawdown (%)': round(drawdown_pct, 2)
        })

if __name__ == "__main__":
    env = IntradayStressTestSimulator(data_path="SOXL_Master_Cleaned.csv", initial_capital=150000)
    
    env.run_stress_simulation(
        dte_range=(30, 60), 
        target_width=5.0, 
        min_credit=1.00, 
        alloc_pct=0.20,          # MARGIN COMPLIANT: 20% Risk Per Trade
        max_trades=5,            # Max 100% Margin Utilization
        stop_loss_mult=3.0,      # 3.0x Stop Loss
        take_profit_pct=0.35,    # 35% Take profit
        require_uptrend=False,   # Trade all environments
        base_sweep_pct=0.10,     # Sweep 10% wins to vault
        max_contracts=300,       # Capped compounding
        slippage_per_leg=0.05    # $10 slippage applied to entry AND exit
    )