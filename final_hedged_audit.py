import pandas as pd
import warnings
import math
import time

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def black_scholes_put(S, K, T, r, sigma):
    if T <= 0: return max(0.0, K - S)
    if sigma <= 0: return max(0.0, K - S) * math.exp(-r * T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)

class FinalAuditSimulator:
    def __init__(self, options_data_path, ibkr_5min_path, initial_capital=150000):
        self.initial_capital = initial_capital
        
        print(f"Loading Options EOD Dataset: {options_data_path}...")
        self.df = pd.read_csv(options_data_path, low_memory=False)
        self.df['Date'] = pd.to_datetime(self.df['date'] if 'date' in self.df.columns else self.df['trade_date'])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        print("Building True Data Options Price & IV Cache in RAM...")
        self.put_df = self.df[self.df['type'].str.upper().isin(['P', 'PUT'])].copy() if 'type' in self.df.columns else self.df[self.df['right'].str.upper().isin(['P', 'PUT'])].copy()
        
        self.options_cache = self.put_df.set_index(['Date', 'Expiration', 'strike'])['close'].to_dict()
        
        iv_cols = ['iv', 'implied_volatility', 'implied_vol', 'volatility', 'implied_volatility_1545']
        iv_col = next((col for col in self.put_df.columns if col.lower() in iv_cols), None)
        
        if iv_col:
            self.iv_cache = self.put_df.set_index(['Date', 'Expiration', 'strike'])[iv_col].to_dict()
        else:
            self.iv_cache = {}

        if 'underlying_price' in self.df.columns:
            daily_px = self.df.groupby('Date')['underlying_price'].first().sort_index()
            self.daily_prices = daily_px.to_dict()
        else:
            self.daily_prices = {}

        print(f"Loading IBKR 5-Minute Intraday Data: {ibkr_5min_path}...")
        ibkr_df = pd.read_csv(ibkr_5min_path)
        date_col = next((col for col in ibkr_df.columns if 'date' in col.lower() or 'time' in col.lower()), None)
        low_col = next((col for col in ibkr_df.columns if 'low' in col.lower()), None)
        
        ibkr_df['FlatDate'] = pd.to_datetime(ibkr_df[date_col].astype(str).str[:8], format='%Y%m%d')
        self.daily_lows = ibkr_df.groupby('FlatDate')[low_col].min().to_dict()
        
        print("Final Audit Engine Ready.\n")

    def run_audit(self):
        # LOCKED VARIABLES FROM ROW 5
        dte_range = (30, 60)
        target_width = 5.0
        min_credit = 0.85
        alloc_pct = 0.15
        max_trades = 5
        stop_loss_mult = 3.0
        take_profit_pct = 0.35
        
        # LOCKED HEDGE VARIABLES FROM ROW 5
        hedge_ratio = 3           # 1x3 Ratio
        target_sell_delta = -0.20 # 20 Delta Start
        max_hedge_debit = 0.50    # Pay up to $0.50 for insurance
        
        # REALITY TAXES
        risk_free_rate = 0.05
        vega_shock_multiplier = 1.30 
        slippage_per_leg = 0.05   # $0.05 slippage per leg
        base_sweep_pct = 0.10     # 10% Cash sweep
        max_contracts = 300       # Contract Limit
                       
        print("--- EXECUTING FINAL TRADE-BY-TRADE AUDIT ---")
        trading_days = sorted(self.daily_prices.keys())
        
        trading_balance = self.initial_capital
        swept_cash = 0.0
        high_water_mark = self.initial_capital
        open_trades, closed_trades = [], []

        for current_date in trading_days:
            current_underlying_price = self.daily_prices.get(current_date)
            current_underlying_low = self.daily_lows.get(current_date, current_underlying_price)
            
            # --- 1. PROCESS OPEN TRADES ---
            still_open = []
            for trade in open_trades:
                curr_short_price = self.options_cache.get((current_date, trade['Expiration'], trade['Short Strike']))
                curr_long_price = self.options_cache.get((current_date, trade['Expiration'], trade['Long Strike']))
                
                if current_date >= trade['Expiration'] and (curr_short_price is None or curr_long_price is None):
                    curr_short_price = max(0, trade['Short Strike'] - current_underlying_price)
                    curr_long_price = max(0, trade['Long Strike'] - current_underlying_price)
                elif curr_short_price is None or curr_long_price is None:
                    still_open.append(trade)
                    continue
                
                current_spread_cost = curr_short_price - curr_long_price
                is_closed, res_reason = False, ""
                income_pnl, hedge_pnl, total_slippage = 0.0, 0.0, 0.0
                
                # A. INTRADAY TRIPWIRE (Flash Crash)
                if current_underlying_low <= trade['Short Strike']:
                    # Income Engine PnL
                    income_pnl = trade['Entry Net Credit'] - (trade['Entry Net Credit'] * stop_loss_mult)
                    
                    # Hedge Engine PnL (Black-Scholes Vegas Shock)
                    dte_remaining = max(1, (trade['Expiration'] - current_date).days)
                    t_years = dte_remaining / 365.0
                    
                    shocked_iv_sell = trade['Hedge Sell IV'] * vega_shock_multiplier
                    shocked_iv_buy = trade['Hedge Buy IV'] * vega_shock_multiplier
                    
                    bs_hedge_sell = black_scholes_put(current_underlying_low, trade['Hedge Sell Strike'], t_years, risk_free_rate, shocked_iv_sell)
                    bs_hedge_buy = black_scholes_put(current_underlying_low, trade['Hedge Buy Strike'], t_years, risk_free_rate, shocked_iv_buy)
                    
                    prb_value_at_crash = (hedge_ratio * bs_hedge_buy) - bs_hedge_sell
                    hedge_pnl = prb_value_at_crash - trade['PRB Entry Net Cost']
                    
                    is_closed = True
                    res_reason = "CRASH (TRIPWIRE)"

                # B. NORMAL TAKE PROFIT / EXPIRATION
                elif current_spread_cost <= (trade['Entry Net Credit'] * (1 - take_profit_pct)) or current_date >= trade['Expiration']:
                    income_pnl = trade['Entry Net Credit'] - current_spread_cost
                    
                    curr_hedge_sell = self.options_cache.get((current_date, trade['Expiration'], trade['Hedge Sell Strike']), 0)
                    curr_hedge_buy = self.options_cache.get((current_date, trade['Expiration'], trade['Hedge Buy Strike']), 0)
                    
                    prb_eod_value = (hedge_ratio * curr_hedge_buy) - curr_hedge_sell
                    hedge_pnl = prb_eod_value - trade['PRB Entry Net Cost']
                    
                    is_closed = True
                    res_reason = "EXPIRATION" if current_date >= trade['Expiration'] else "TAKE-PROFIT"

                if is_closed:
                    total_legs_to_close = 2 + 1 + hedge_ratio
                    total_slippage = slippage_per_leg * total_legs_to_close
                    
                    net_pnl_per_contract = (income_pnl + hedge_pnl - total_slippage) * 100
                    
                    # Cap catastrophic loss at Max Risk (safeguard)
                    if net_pnl_per_contract < 0:
                        net_pnl_per_contract = max(net_pnl_per_contract, -trade['Base Risk'])
                        
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
                        'Inc. Short Strike': f"${trade['Short Strike']:.2f}",
                        'Inc. Long Strike': f"${trade['Long Strike']:.2f}",
                        'Hdg. Sell Strike': f"${trade['Hedge Sell Strike']:.2f}",
                        'Hdg. Buy Strike': f"${trade['Hedge Buy Strike']:.2f}",
                        'Net Income PnL ($)': round(income_pnl * 100 * trade['Contracts'], 2),
                        'Net Hedge PnL ($)': round(hedge_pnl * 100 * trade['Contracts'], 2),
                        'Slippage Paid ($)': round(total_slippage * 100 * trade['Contracts'], 2),
                        'Total Net PnL ($)': round(total_combined_pnl, 2),
                        'Trading Balance ($)': round(trading_balance, 2),
                        'Cash Vault ($)': round(swept_cash, 2),
                        'Total Net Worth ($)': round(total_net_worth, 2),
                        'Drawdown (%)': round(drawdown_pct, 2)
                    })
                else:
                    still_open.append(trade)
                    
            open_trades = still_open

            # --- 2. PROCESS NEW ENTRIES ---
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
                    # 1. Target Sell Delta
                    prb_sell_cands = daily_puts[(daily_puts['Expiration'] == short_put['Expiration'])]
                    if prb_sell_cands.empty: continue
                    prb_sell = prb_sell_cands.iloc[(prb_sell_cands['delta'] - target_sell_delta).abs().argsort()].iloc[0]
                    
                    # 2. Target Buy Strikes under max debit
                    target_buy_cost_max = (prb_sell['close'] + max_hedge_debit) / hedge_ratio
                    prb_buy_cands = daily_puts[(daily_puts['Expiration'] == short_put['Expiration']) & (daily_puts['strike'] < prb_sell['strike']) & (daily_puts['close'] <= target_buy_cost_max)]
                    
                    if prb_buy_cands.empty: continue
                    
                    prb_buy = prb_buy_cands.sort_values(by='strike', ascending=False).iloc[0]
                    prb_net_cost = (hedge_ratio * prb_buy['close']) - prb_sell['close']
                    
                    total_legs = 2 + 1 + hedge_ratio
                    net_credit_realized = net_credit_raw - prb_net_cost - (slippage_per_leg * total_legs)
                    
                    if net_credit_realized >= 0.20:  
                        max_risk_dollars = ((short_put['strike'] - valid_long['strike']) - net_credit_realized) * 100
                        if max_risk_dollars > 0:
                            contracts = math.floor((trading_balance * alloc_pct) / max_risk_dollars)
                            if contracts > max_contracts: contracts = max_contracts
                                
                            if contracts >= 1:
                                iv_sell = self.iv_cache.get((current_date, short_put['Expiration'], prb_sell['strike']), 0.80)
                                iv_buy = self.iv_cache.get((current_date, short_put['Expiration'], prb_buy['strike']), 0.80)
                                
                                open_trades.append({
                                    'Entry Date': current_date,
                                    'Expiration': short_put['Expiration'],
                                    'Short Strike': short_put['strike'],
                                    'Long Strike': valid_long['strike'],
                                    'Entry Net Credit': net_credit_raw, 
                                    'Hedge Sell Strike': prb_sell['strike'],
                                    'Hedge Buy Strike': prb_buy['strike'],
                                    'PRB Entry Net Cost': prb_net_cost,
                                    'Hedge Sell IV': iv_sell,
                                    'Hedge Buy IV': iv_buy,
                                    'Base Risk': max_risk_dollars,
                                    'Contracts': contracts
                                })

        pnl_df = pd.DataFrame(closed_trades)
        if pnl_df.empty:
            print("No trades executed.")
            return

        for col in ['Entry Date', 'Exit Date']: pnl_df[col] = pd.to_datetime(pnl_df[col]).dt.strftime('%Y-%m-%d')
        pnl_df.to_csv('SOXL_Final_Hedged_Audit.csv', index=False)
        
        wins = len(pnl_df[pnl_df['Total Net PnL ($)'] > 0])
        tripwires = len(pnl_df[pnl_df['Reason'] == "CRASH (TRIPWIRE)"])
        win_rate = (wins / len(pnl_df)) * 100
        roi = ((pnl_df['Total Net Worth ($)'].iloc[-1] - self.initial_capital) / self.initial_capital) * 100
        
        print(f"\n--- FINAL AUDIT COMPLETE ---")
        print(f"Total Trades:          {len(pnl_df)}")
        print(f"Intraday Crashes:      {tripwires} (PRB Protected)")
        print(f"Win Rate:              {win_rate:.2f}%")
        print("-" * 60)
        print(f"Final Trading Margin:  ${pnl_df['Trading Balance ($)'].iloc[-1]:,.2f}")
        print(f"Final Cash Vault:      ${pnl_df['Cash Vault ($)'].iloc[-1]:,.2f}")
        print(f"Final Total Net Worth: ${pnl_df['Total Net Worth ($)'].iloc[-1]:,.2f}")
        print(f"Total ROI:             {roi:.2f}%")
        print(f"Max Drawdown:          {pnl_df['Drawdown (%)'].max():.2f}%")
        print("-" * 60)
        print(">> 'SOXL_Final_Hedged_Audit.csv' generated. Open it to see exact strikes, slippage, and PnL per leg.")

if __name__ == "__main__":
    env = FinalAuditSimulator("SOXL_Master_Cleaned.csv", "SOXL_5min_3Years.csv", 150000)
    env.run_audit()