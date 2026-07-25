import pandas as pd
import math
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

class V5PortfolioEngine:
    def __init__(self, data_path, starting_capital=150000.0, risk_per_trade_pct=0.15, max_concurrent_trades=3, max_contracts_per_trade=100, profit_harvest_pct=0.50):
        print(f"Loading Options Data from: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)
        self.df['Date'] = pd.to_datetime(self.df['date'] if 'date' in self.df.columns else self.df['trade_date'])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days
        
        if 'underlying_price' in self.df.columns:
            self.daily_prices = self.df.groupby('Date')['underlying_price'].first().to_dict()
        else:
            self.daily_prices = {}
            
        # System Parameters
        self.starting_capital = starting_capital
        self.risk_pct = risk_per_trade_pct
        self.max_concurrent = max_concurrent_trades
        self.max_contracts = max_contracts_per_trade
        self.harvest_pct = profit_harvest_pct
        
        print(f"Engine Ready.")
        print(f"Start Capital: ${self.starting_capital:,.2f} | Risk/Trade: {self.risk_pct*100}% | Concurrency: {self.max_concurrent}")
        print(f"Liquidity Cap: {self.max_contracts} contracts | Cash Harvest: {self.harvest_pct*100}% of profits")

    def run_full_simulation(self, dte_range=(20, 45), target_width=6.0, min_credit=0.80):
        print("\n[Phase 1] Scanning 3-year history for valid trade setups...")
        puts = self.df[self.df['type'].str.upper().isin(['P', 'PUT'])].copy() if 'type' in self.df.columns else self.df[self.df['right'].str.upper().isin(['P', 'PUT'])].copy()
        
        trading_days = puts['Date'].unique()
        trades = []

        for date in trading_days:
            daily = puts[(puts['Date'] == date) & (puts['DTE'].between(*dte_range))]
            if daily.empty: continue
            
            short_cands = daily.iloc[(daily['delta'].abs() - 0.20).abs().argsort()]
            long_cands = daily.iloc[(daily['delta'].abs() - 0.05).abs().argsort()]
            if short_cands.empty or long_cands.empty: continue
            
            short_put = short_cands.iloc[0]
            valid_long = None
            for _, long_put in long_cands.iterrows():
                spread_width = short_put['strike'] - long_put['strike']
                if 2.50 <= spread_width <= target_width:
                    valid_long = long_put
                    break
            
            if valid_long is None: continue

            net_credit = (short_put['close'] - valid_long['close']) * 100
            if net_credit >= (min_credit * 100):
                max_risk = ((short_put['strike'] - valid_long['strike']) * 100) - net_credit
                if max_risk > 0:
                    trades.append({
                        'Entry_Date': pd.to_datetime(date), 
                        'Expiration': pd.to_datetime(short_put['Expiration']),
                        'Short_Strike': short_put['strike'],
                        'Long_Strike': valid_long['strike'],
                        'Credit_Per_Contract': net_credit, 
                        'Risk_Per_Contract': max_risk
                    })

        if not trades:
            print("No valid trades found.")
            return

        print(f"[Phase 2] Grading {len(trades)} executed trades against historical expiration prices...")
        graded_trades = []
        for t in trades:
            exp_date = t['Expiration']
            available_dates = [d for d in self.daily_prices.keys() if d <= exp_date]
            if not available_dates: continue
            
            settlement_price = self.daily_prices[max(available_dates)]
            
            if settlement_price >= t['Short_Strike']:
                pnl = t['Credit_Per_Contract']
            elif settlement_price <= t['Long_Strike']:
                pnl = -t['Risk_Per_Contract']
            else:
                pnl = t['Credit_Per_Contract'] - ((t['Short_Strike'] - settlement_price) * 100)
                
            t['PnL_Per_Contract'] = pnl
            graded_trades.append(t)

        print("\n[Phase 3] Running Live Portfolio Simulation (With Cash Sweeps)...")
        balance = self.starting_capital
        available_margin = self.starting_capital
        harvested_cash = 0.0
        
        events = []
        for idx, t in enumerate(graded_trades):
            events.append({'date': t['Entry_Date'], 'type': 'OPEN', 'trade_idx': idx, 'data': t})
            events.append({'date': t['Expiration'], 'type': 'CLOSE', 'trade_idx': idx, 'data': t})
            
        events.sort(key=lambda x: (x['date'], 0 if x['type'] == 'CLOSE' else 1))
        
        peak_equity = self.starting_capital
        max_drawdown_pct = 0.0
        active_trades = {}

        for event in events:
            t = event['data']
            idx = event['trade_idx']
            
            if event['type'] == 'OPEN':
                # Concurrency limit
                if len(active_trades) >= self.max_concurrent:
                    continue 
                
                target_risk_dollars = balance * self.risk_pct
                contracts = math.floor(target_risk_dollars / t['Risk_Per_Contract'])
                
                # Liquidity ceiling overlay
                if contracts > self.max_contracts:
                    contracts = self.max_contracts
                
                margin_required = contracts * t['Risk_Per_Contract']
                if margin_required > available_margin:
                    contracts = math.floor(available_margin / t['Risk_Per_Contract'])
                    margin_required = contracts * t['Risk_Per_Contract']
                
                if contracts > 0:
                    active_trades[idx] = {'contracts': contracts, 'margin_used': margin_required}
                    available_margin -= margin_required
                    
            elif event['type'] == 'CLOSE':
                if idx in active_trades:
                    trade_record = active_trades.pop(idx)
                    contracts_held = trade_record['contracts']
                    
                    # 1. Release the margin hold
                    available_margin += trade_record['margin_used']
                    
                    # 2. Add/Subtract the Realized PnL
                    total_pnl = contracts_held * t['PnL_Per_Contract']
                    
                    # 3. Apply the Cash Harvesting Logic
                    if total_pnl > 0:
                        swept_amount = total_pnl * self.harvest_pct
                        reinvested_amount = total_pnl - swept_amount
                        harvested_cash += swept_amount
                        balance += reinvested_amount
                        available_margin += reinvested_amount 
                    else:
                        # If a loss, the entire loss hits the trading balance
                        balance += total_pnl
                        available_margin += total_pnl 
                    
                    # 4. Calculate Drawdown based on Total Equity (Balance + Vault)
                    current_equity = balance + harvested_cash
                    if current_equity > peak_equity:
                        peak_equity = current_equity
                    current_drawdown = (peak_equity - current_equity) / peak_equity
                    if current_drawdown > max_drawdown_pct:
                        max_drawdown_pct = current_drawdown

        total_final_equity = balance + harvested_cash
        total_return = ((total_final_equity - self.starting_capital) / self.starting_capital) * 100
        
        print("=" * 60)
        print("   V6 PORTFOLIO COMPOUNDING RESULTS (WITH CASH HARVESTING)   ")
        print("=" * 60)
        print(f"Starting Balance:          ${self.starting_capital:,.2f}")
        print(f"Final Trading Balance:     ${balance:,.2f}")
        print(f"Safe Cash Vault (Swept):   ${harvested_cash:,.2f}")
        print("-" * 60)
        print(f"Total System Equity:       ${total_final_equity:,.2f}")
        print(f"Net Profit:                ${(total_final_equity - self.starting_capital):,.2f}")
        print(f"Total ROI:                 {total_return:.2f}%")
        print(f"Max Portfolio Drawdown:    {max_drawdown_pct * 100:.2f}%")
        print("=" * 60)

if __name__ == "__main__":
    # YOU CAN ADJUST ALL YOUR MAIN VARIABLES RIGHT HERE
    engine = V5PortfolioEngine(
        "SOXL_Master_Cleaned.csv", 
        starting_capital=160000.0, 
        risk_per_trade_pct=0.20,         # Risking 15% per trade
        max_concurrent_trades=4,         # Max 3 trades open at once 
        max_contracts_per_trade=500,     # INCREASED: Liquidity Cap to 200 contracts
        profit_harvest_pct=0.50          # DECREASED: Sweep 10% of winning profits into vault
    )
    
    # You can also adjust your trade finding parameters here
    engine.run_full_simulation(dte_range=(20, 45), target_width=6.0, min_credit=0.80)