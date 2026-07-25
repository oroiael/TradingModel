import pandas as pd
import warnings
import math
import time
import yfinance as yf
from datetime import timedelta

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')
warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')

class HedgedRealWorldSimulator:
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
        else:
            self.daily_prices = {}

        # --- FETCH INTRADAY TRIPWIRES ---
        min_date = self.df['Date'].min() - timedelta(days=5)
        max_date = self.df['Date'].max() + timedelta(days=5)
        print("Fetching Intraday SOXL Flash-Crash Data from Yahoo Finance...")
        soxl_data = yf.download("SOXL", start=min_date.strftime('%Y-%m-%d'), end=max_date.strftime('%Y-%m-%d'), progress=False)
        
        if isinstance(soxl_data.columns, pd.MultiIndex): lows = soxl_data['Low']['SOXL']
        else: lows = soxl_data['Low']
            
        lows.index = pd.to_datetime(lows.index).tz_localize(None).normalize()
        self.daily_lows = lows.to_dict()
        print("Meat Grinder Ready: Slippage + Intraday Crashes + Real Data Hedges Enabled.\n")

    def run_hedged_simulation(self):
        # EXACT PARAMETERS FROM ROW 1
        dte_range = (30, 60)
        target_width = 5.0
        min_credit = 0.85
        alloc_pct = 0.15
        max_trades = 5
        stop_loss_mult = 3.0
        take_profit_pct = 0.30
        
        # HEDGE & REALITY PARAMETERS
        hedge_budget_pct = 0.20     # Spend 20% of collected premium on a far-OTM Put
        slippage_per_leg = 0.05     # $5 slippage per leg
        base_sweep_pct = 0.10       # Sweep 10%
        max_contracts = 300         # Contract Cap
                       
        print("--- EXECUTING HEDGED MEAT GRINDER SIMULATION ---")
        trading_days = sorted(self.daily_prices.keys())
        
        trading_balance = self.initial_capital
        swept_cash = 0.0
        high_water_mark = self.initial_capital
        open_trades = []
        closed_trades = []
        start_time = time.time()

        for current_date in trading_days:
            current_underlying_price = self.daily_prices.get(current_date)
            current_underlying_low = self.daily_lows.get(current_date, current_underlying_price)
            
            # ==========================================
            # 1. PROCESS OPEN TRADES
            # ==========================================
            still_open = []
            for trade in open_trades:
                
                # Fetch REAL EOD options data for today
                curr_short_price = self.options_cache.get((current_date, trade['Expiration'], trade['Short Strike']))
                curr_long_price = self.options_cache.get((current_date, trade['Expiration'], trade['Long Strike']))
                curr_hedge_price = self.options_cache.get((current_date, trade['Expiration'], trade['Hedge Strike']))
                
                if current_date >= trade['Expiration'] and (curr_short_price is None or curr_long_price is None):
                    curr_short_price = max(0, trade['Short Strike'] - current_underlying_price)
                    curr_long_price = max(0, trade['Long Strike'] - current_underlying_price)
                    curr_hedge_price = max(0, trade['Hedge Strike'] - current_underlying_price)
                elif curr_short_price is None or curr_long_price is None:
                    still_open.append(trade)
                    continue
                
                if curr_hedge_price is None: curr_hedge_price = 0.0 # Assume hedge is worthless if data missing
                
                current_spread_cost = curr_short_price - curr_long_price
                
                is_closed = False
                res_reason = ""
                net_pnl_per_contract = 0.0
                
                # A. INTRADAY TRIPWIRE (Flash Crash)
                if current_underlying_low <= trade['Short Strike']:
                    gross_spread_loss = (trade['Entry Net Credit'] * stop_loss_mult) - trade['Entry Net Credit']
                    # Hedge Payout (Real EOD Price - Entry Price)
                    hedge_profit = curr_hedge_price - trade['Hedge Entry Price']
                    
                    net_loss_raw = gross_spread_loss - hedge_profit
                    # Add $15 slippage (3 legs: exit short, exit long, exit hedge)
                    net_pnl_per_contract = -(net_loss_raw + (slippage_per_leg * 3)) * 100
                    
                    # Cap loss at theoretical max risk
                    net_pnl_per_contract = max(net_pnl_per_contract, -trade['Base Risk'])
                    is_closed = True
                    res_reason = "CRASH + HEDGE PAYOUT"

                # B. EXPIRATION
                elif current_date >= trade['Expiration']:
                    gross_pnl = trade['Entry Net Credit'] - current_spread_cost
                    hedge_profit = curr_hedge_price - trade['Hedge Entry Price']
                    net_pnl_per_contract = (gross_pnl + hedge_profit - (slippage_per_leg * 3)) * 100
                    is_closed = True
                    res_reason = "EXPIRATION"

                # C. TAKE PROFIT (Normal Win)
                elif current_spread_cost <= (trade['Entry Net Credit'] * (1 - take_profit_pct)):
                    gross_pnl = trade['Entry Net Credit'] - current_spread_cost
                    # Assume hedge decays to zero on a win to be highly conservative
                    hedge_loss = -trade['Hedge Entry Price'] 
                    net_pnl_per_contract = (gross_pnl + hedge_loss - (slippage_per_leg * 3)) * 100
                    is_closed = True
                    res_reason = f"TAKE-PROFIT ({int(take_profit_pct*100)}%)"

                if is_closed:
                    total_combined_pnl = net_pnl_per_contract * trade['Contracts']
                    
                    sweep_amount = 0.0
                    if total_combined_pnl > 0:
                        if trade['Contracts'] >= max_contracts: sweep_amount = total_combined_pnl
                        else: sweep_amount = total_combined_pnl * base_sweep_pct
                        swept_cash += sweep_amount
                        trading_balance += (total_combined_pnl - sweep_amount)
                    else:
                        trading_balance += total_combined_pnl

                    total_net_worth = trading_balance + swept_cash
                    if total_net_worth > high_water_mark: high_water_mark = total_net_worth
                    
                    drawdown_pct = ((high_water_mark - total_net_worth) / high_water_mark) * 100 if high_water_mark > 0 else 0
                    
                    closed_trades.append({
                        'Entry Date': trade['Entry Date'],
                        'Exit Date': current_date,
                        'Reason': res_reason,
                        'Contracts': trade['Contracts'],
                        'Net PnL': round(total_combined_pnl, 2),
                        'Trading Balance': round(trading_balance, 2),
                        'Cash Vault': round(swept_cash, 2),
                        'Total Net Worth': round(total_net_worth, 2),
                        'Drawdown (%)': round(drawdown_pct, 2)
                    })
                else:
                    still_open.append(trade)
                    
            open_trades = still_open

            # ==========================================
            # 2. PROCESS NEW ENTRIES
            # ==========================================
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
                    if target_width - 0.5 <= (short_put['strike'] - long_put['strike']) <= target_width + 0.5:
                        valid_long = long_put
                        break
                
                if valid_long is None: continue
                
                net_credit_raw = short_put['close'] - valid_long['close']
                
                if (net_credit_raw * 100) >= (min_credit * 100):
                    # --- FIND THE REAL DATA HEDGE ---
                    hedge_budget = net_credit_raw * hedge_budget_pct
                    hedge_candidates = daily_puts[(daily_puts['Expiration'] == short_put['Expiration']) & (daily_puts['close'] <= hedge_budget)]
                    
                    if hedge_candidates.empty: continue # Skip trade if no valid hedge exists
                    hedge_put = hedge_candidates.iloc[(hedge_candidates['close'] - hedge_budget).abs().argsort()].iloc[0]
                    
                    # Apply slippage on ENTRY to all 3 legs
                    net_credit_realized = net_credit_raw - hedge_put['close'] - (slippage_per_leg * 3)
                    max_risk_dollars = ((short_put['strike'] - valid_long['strike']) - net_credit_realized) * 100
                    
                    if max_risk_dollars > 0:
                        contracts = math.floor((trading_balance * alloc_pct) / max_risk_dollars)
                        if contracts > max_contracts: contracts = max_contracts
                            
                        if contracts >= 1:
                            open_trades.append({
                                'Entry Date': current_date,
                                'Expiration': short_put['Expiration'],
                                'Short Strike': short_put['strike'],
                                'Long Strike': valid_long['strike'],
                                'Hedge Strike': hedge_put['strike'],
                                'Entry Net Credit': net_credit_raw, 
                                'Hedge Entry Price': hedge_put['close'],
                                'Base Risk': max_risk_dollars,
                                'Contracts': contracts
                            })

        # --- FINAL REPORTING ---
        pnl_df = pd.DataFrame(closed_trades)
        if pnl_df.empty:
            print("No trades executed. Market conditions never met parameters.")
            return

        for col in ['Entry Date', 'Exit Date']:
            pnl_df[col] = pd.to_datetime(pnl_df[col]).dt.strftime('%Y-%m-%d')
            
        pnl_df.to_csv('SOXL_Hedged_Reality_Audit.csv', index=False)
        
        wins = len(pnl_df[pnl_df['Net PnL'] > 0])
        losses = len(pnl_df[pnl_df['Net PnL'] <= 0])
        tripwires = len(pnl_df[pnl_df['Reason'] == "CRASH + HEDGE PAYOUT"])
        win_rate = (wins / len(pnl_df)) * 100
        
        final_nw = pnl_df['Total Net Worth'].iloc[-1]
        roi = ((final_nw - self.initial_capital) / self.initial_capital) * 100
        max_dd = pnl_df['Drawdown (%)'].max()
        
        print(f"\n--- HEDGED MEAT GRINDER COMPLETE ({round(time.time() - start_time, 1)} sec) ---")
        print(f"Total Trades:          {len(pnl_df)}")
        print(f"Wins / Losses:         {wins} / {losses}")
        print(f"Intraday Crashes:      {tripwires} (Hedge Activated)")
        print(f"Brutalized Win Rate:   {win_rate:.2f}%")
        print("-" * 60)
        print(f"Initial Capital:       ${self.initial_capital:,.2f}")
        print(f"Final Trading Margin:  ${pnl_df['Trading Balance'].iloc[-1]:,.2f}")
        print(f"Cash Vault (Safe):     ${pnl_df['Cash Vault'].iloc[-1]:,.2f}")
        print(f"Final Total Net Worth: ${final_nw:,.2f}")
        print(f"TRUE EXPECTED ROI:     {roi:.2f}%")
        print("-" * 60)
        print(f"TRUE MAX DRAWDOWN:     {max_dd:.2f}%")
        print("-" * 60)

if __name__ == "__main__":
    env = HedgedRealWorldSimulator("SOXL_Master_Cleaned.csv", 150000)
    env.run_hedged_simulation()