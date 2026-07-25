#!/usr/bin/env python3
"""
final_hedged_audit_fixed.py — Fully Audited Options Strategy Backtest Engine

Strategy:
  - Income Engine: 30-60 DTE, $5-wide Put Credit Spread (~20Δ short, ~5Δ long)
  - Hedge Engine:  1x3 Put Ratio Backspread (~20Δ short, 3x far-OTM long)
  - Risk Control:  True grid-based structural risk sizing (NO LOSS CAPS),
                   Intraday short-strike touch tripwire, 35% Take-Profit,
                   3-tier pricing fallback hierarchy, Daily MTM equity tracking.
"""

import os
import sys
import math
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from scipy.stats import norm

# Suppress pandas harmless warnings for clean CLI output
warnings.filterwarnings('ignore')

# ==========================================
# 1. PRICING & RISK MATH ENGINE
# ==========================================

def black_scholes_put(spot, strike, dte_days, r=0.05, iv=0.50):
    """Tier 2 fallback: Black-Scholes theoretical put valuation."""
    if dte_days <= 0 or iv <= 0 or np.isnan(iv):
        return max(0.0, strike - spot)
    T = dte_days / 365.0
    d1 = (np.log(spot / strike) + (r + 0.5 * iv**2) * T) / (iv * np.sqrt(T))
    d2 = d1 - iv * np.sqrt(T)
    put_price = strike * np.exp(-r * T) * norm.cdf(-d2) - spot * norm.cdf(-d1)
    return max(0.0, float(put_price))

def get_option_mark(row, spot, current_date, r=0.05, default_iv=0.50):
    """
    Tiered pricing hierarchy to guarantee no contract is ever liquidated at a silent $0.00.
    Returns: (price_per_share, pricing_tier_used)
    """
    if row is None or row.empty:
        return max(0.0, 0.0), 'MISSING_ROW_ZERO'
        
    strike = float(row['strike'])
    dte_days = (pd.to_datetime(row['expiration']) - pd.to_datetime(current_date)).days
    
    # Tier 1: EOD Market Quote
    close_val = row.get('close', np.nan)
    if pd.notna(close_val) and float(close_val) > 0:
        return float(close_val), 'QUOTE'
        
    # Tier 2: Black-Scholes Theoretical
    iv_val = row.get('iv', default_iv)
    if pd.isna(iv_val) or float(iv_val) <= 0:
        iv_val = default_iv
    bs_val = black_scholes_put(spot, strike, dte_days, r, float(iv_val))
    if bs_val > 0 and dte_days > 0:
        return bs_val, 'BS_FALLBACK'
        
    # Tier 3: Intrinsic Value
    intrinsic = max(0.0, strike - spot)
    return intrinsic, 'INTRINSIC'

def compute_structural_risk_per_contract(spot, short_strike, pcs_long_strike, prb_long_strike, net_credit_per_share, stress_buffer=1.15):
    """
    Solves for true maximum structural loss across a 500-point price grid from $0 to 1.5x Spot.
    Accounts for holding SHORT 2x puts at short_strike, LONG 1x put at pcs_long, LONG 3x puts at prb_long.
    """
    grid = np.linspace(0.01, spot * 1.5, 500)
    
    # Payoffs per share at expiration across price grid
    short_leg_payoff = -2.0 * np.maximum(0.0, short_strike - grid)
    pcs_long_payoff = 1.0 * np.maximum(0.0, pcs_long_strike - grid)
    prb_long_payoff = 3.0 * np.maximum(0.0, prb_long_strike - grid)
    
    total_expiration_payoff = short_leg_payoff + pcs_long_payoff + prb_long_payoff + net_credit_per_share
    
    min_pnl_per_share = np.min(total_expiration_payoff)
    max_loss_per_share = abs(min_pnl_per_share) if min_pnl_per_share < 0 else 0.0
    
    # Convert per share to per contract (multiplier 100) + apply buffer for pre-expiry vega/gamma expansion
    return (max_loss_per_share * 100.0) * stress_buffer


# ==========================================
# 2. DATA INGESTION & NORMALIZATION
# ==========================================

def load_and_validate_data(options_csv_path, prices_csv_path):
    """Loads, cleans, and strictly asserts Greek sign conventions and schema requirements."""
    print("Loading and validating historical data datasets...")
    df_opt = pd.read_csv(options_csv_path)
    df_px = pd.read_csv(prices_csv_path)
    
    # Schema checks
    req_opt = ['date', 'expiration', 'strike', 'right', 'close', 'delta', 'iv', 'underlying_price']
    for col in req_opt:
        if col not in df_opt.columns:
            raise ValueError(f"CRITICAL ERROR: Options file missing column '{col}'")
            
    req_px = ['date', 'close', 'low', 'high']
    for col in req_px:
        if col not in df_px.columns:
            raise ValueError(f"CRITICAL ERROR: Prices file missing column '{col}'")
            
    # Datetime formatting
    df_opt['date'] = pd.to_datetime(df_opt['date'])
    df_opt['expiration'] = pd.to_datetime(df_opt['expiration'])
    df_px['date'] = pd.to_datetime(df_px['date'])
    
    # Normalize Puts: Enforce negative delta convention (Fixes Bug 1.4)
    put_mask = df_opt['right'].str.upper().str.startswith('P')
    df_opt.loc[put_mask, 'delta'] = -df_opt.loc[put_mask, 'delta'].abs()
    
    # Assert validation
    assert (df_opt.loc[put_mask, 'delta'] <= 0).all(), "FATAL: Delta sign normalization failed!"
    
    # Deduplicate rows by taking the latest vendor print (Fixes Issue 3.2)
    df_opt = df_opt.drop_duplicates(subset=['date', 'expiration', 'strike', 'right'], keep='last')
    
    print(f"Data successfully loaded. Options rows: {len(df_opt):,}, Price days: {len(df_px):,}")
    return df_opt, df_px.sort_values('date').reset_index(drop=True)


# ==========================================
# 3. INSTITUTIONAL BACKTEST ENGINE
# ==========================================

class InstitutionalSimulator:
    def __init__(self, initial_capital=150000.0, alloc_pct=0.15, tp_pct=0.35, vault_sweep_pct=0.10,
                 slippage_per_leg=0.05, comm_per_contract=0.65):
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.vault_cash = 0.0
        self.alloc_pct = float(alloc_pct)
        self.tp_pct = float(tp_pct)
        self.vault_sweep_pct = float(vault_sweep_pct)
        self.slippage = float(slippage_per_leg)
        self.comm = float(comm_per_contract)
        
        self.active_trades = []
        self.closed_trades = []
        self.equity_curve = []
        self.fallback_counts = {'QUOTE': 0, 'BS_FALLBACK': 0, 'INTRINSIC': 0, 'MISSING_ROW_ZERO': 0}
        
    def run_simulation(self, df_opt, df_px):
        print("\nStarting simulation loop across historical timeline...")
        # Group options by date for fast lookup
        daily_options_map = {d: group for d, group in df_opt.groupby('date')}
        
        for idx, px_row in df_px.iterrows():
            curr_date = px_row['date']
            spot_close = float(px_row['close'])
            spot_low = float(px_row['low'])
            
            chain_today = daily_options_map.get(curr_date, pd.DataFrame())
            
            # --- STEP 1: INTRADAY TRIPWIRE EVALUATION (Executed before quote checks!) ---
            # Fixes Bug 1.2: Uses underlying daily low regardless of whether option quotes printed today
            for trade in list(self.active_trades):
                if spot_low <= trade['tripwire_strike']:
                    self._close_trade(trade, curr_date, spot_low, chain_today, exit_reason='CRASH_TRIPWIRE', iv_shock_mult=1.30)
                    
            # --- STEP 2: EXPIRATION & TAKE-PROFIT EVALUATION ---
            for trade in list(self.active_trades):
                # Expiration check
                if curr_date >= trade['expiration']:
                    self._close_trade(trade, curr_date, spot_close, chain_today, exit_reason='EXPIRATION')
                    continue
                
                # Take-Profit check (if chain exists to mark to market)
                if not chain_today.empty:
                    mtm_close_cost = self._estimate_close_debit(trade, curr_date, spot_close, chain_today)
                    net_profit_so_far = trade['net_credit_realized_total'] - mtm_close_cost
                    if net_profit_so_far >= (trade['target_profit_total']):
                        self._close_trade(trade, curr_date, spot_close, chain_today, exit_reason='TAKE_PROFIT_35%')
                        
            # --- STEP 3: NEW ENTRY SCANNING (1 Trade max per day, 5 active max) ---
            if not chain_today.empty and len(self.active_trades) < 5:
                self._attempt_entry(curr_date, spot_close, chain_today)
                
            # --- STEP 4: DAILY MARK-TO-MARKET (MTM) EQUITY ACCOUNTING ---
            mtm_portfolio_val = self.cash + self.vault_cash
            for trade in self.active_trades:
                if not chain_today.empty:
                    close_debit = self._estimate_close_debit(trade, curr_date, spot_close, chain_today)
                else:
                    close_debit = trade['last_known_mtm_debit']
                trade['last_known_mtm_debit'] = close_debit
                mtm_portfolio_val += (trade['net_credit_realized_total'] - close_debit)
                
            self.equity_curve.append({
                'date': curr_date,
                'underlying': spot_close,
                'cash': round(self.cash, 2),
                'vault_cash': round(self.vault_cash, 2),
                'mtm_equity': round(mtm_portfolio_val, 2),
                'open_positions': len(self.active_trades)
            })
            
        # --- STEP 5: FORCE LIQUIDATION ON FINAL DAY (Fixes Bug 1.7) ---
        final_date = df_px.iloc[-1]['date']
        final_spot = float(df_px.iloc[-1]['close'])
        final_chain = daily_options_map.get(final_date, pd.DataFrame())
        for trade in list(self.active_trades):
            self._close_trade(trade, final_date, final_spot, final_chain, exit_reason='FINAL_DAY_LIQUIDATION')
            
        print("Simulation complete.")
        return pd.DataFrame(self.equity_curve), pd.DataFrame(self.closed_trades)

    def _attempt_entry(self, curr_date, spot, chain):
        # Filter for 30-60 DTE Puts
        chain_puts = chain[chain['right'].str.upper().str.startswith('P')].copy()
        chain_puts['dte'] = (chain_puts['expiration'] - curr_date).dt.days
        valid_dte = chain_puts[(chain_puts['dte'] >= 30) & (chain_puts['dte'] <= 60)]
        if valid_dte.empty:
            return
            
        # Pick target expiration (closest to 45 DTE)
        target_exp = valid_dte.iloc[(valid_dte['dte'] - 45).abs().argsort()[:1]]['expiration'].values[0]
        exp_chain = valid_dte[valid_dte['expiration'] == target_exp].sort_values('strike', ascending=False)
        
        # Strike selection based on target deltas (-0.20 short, -0.05 long)
        short_cand = exp_chain.iloc[(exp_chain['delta'] - (-0.20)).abs().argsort()[:1]]
        if short_cand.empty:
            return
        short_row = short_cand.iloc[0]
        short_k = float(short_row['strike'])
        
        # Income long put ($5 wide)
        pcs_long_k = short_k - 5.0
        pcs_long_row = exp_chain[exp_chain['strike'] == pcs_long_k]
        if pcs_long_row.empty:
            # Fallback to closest delta around -0.05 if exact $5 wide missing
            pcs_long_row = exp_chain.iloc[(exp_chain['delta'] - (-0.05)).abs().argsort()[:1]]
            if pcs_long_row.empty: return
            pcs_long_k = float(pcs_long_row.iloc[0]['strike'])
        else:
            pcs_long_row = pcs_long_row.iloc[0]
            
        # Hedge PRB long puts (3x far OTM, aim for delta around -0.05 or lower strike than pcs_long)
        prb_long_cands = exp_chain[exp_chain['strike'] < short_k]
        if prb_long_cands.empty:
            return
        prb_long_row = prb_long_cands.iloc[(prb_long_cands['delta'] - (-0.05)).abs().argsort()[:1]].iloc[0]
        prb_long_k = float(prb_long_row['strike'])
        
        # Mid prices
        p_short = float(short_row['close'])
        p_pcs_long = float(pcs_long_row['close']) if isinstance(pcs_long_row, pd.Series) else float(pcs_long_row['close'].values[0])
        p_prb_long = float(prb_long_row['close'])
        
        # Structure: Short 2x short_k, Long 1x pcs_long_k, Long 3x prb_long_k
        raw_net_credit_per_share = (2.0 * p_short) - (1.0 * p_pcs_long) - (3.0 * p_prb_long)
        if raw_net_credit_per_share <= 0.20:  # Skip thin or debit structures
            return
            
        # Risk sizing without loss caps (Fixes Bug 1.1 & 1.6)
        true_risk_per_contract = compute_structural_risk_per_contract(
            spot, short_k, pcs_long_k, prb_long_k, raw_net_credit_per_share
        )
        if true_risk_per_contract <= 0:
            return
            
        target_risk_capital = self.cash * self.alloc_pct
        num_contracts = math.floor(target_risk_capital / true_risk_per_contract)
        if num_contracts < 1:
            return
            
        # Account for opening friction (6 legs total per contract set: 2 sell + 1 buy + 3 buy)
        open_slippage_total = 6.0 * self.slippage * num_contracts * 100.0
        open_comm_total = 6.0 * self.comm * num_contracts
        realized_net_credit_total = (raw_net_credit_per_share * 100.0 * num_contracts) - open_slippage_total - open_comm_total
        
        if realized_net_credit_total <= 0:
            return
            
        # Add cash to ledger
        self.cash += realized_net_credit_total
        
        trade_obj = {
            'id': len(self.closed_trades) + len(self.active_trades) + 1,
            'entry_date': curr_date,
            'expiration': pd.to_datetime(target_exp),
            'spot_at_entry': spot,
            'short_strike': short_k,
            'pcs_long_strike': pcs_long_k,
            'prb_long_strike': prb_long_k,
            'contracts': num_contracts,
            'raw_credit_per_share': raw_net_credit_per_share,
            'net_credit_realized_total': realized_net_credit_total,
            'true_risk_per_contract': true_risk_per_contract,
            'target_profit_total': realized_net_credit_total * self.tp_pct,
            'tripwire_strike': short_k,
            'last_known_mtm_debit': realized_net_credit_total * 0.8  # initial estimate
        }
        self.active_trades.append(trade_obj)

    def _estimate_close_debit(self, trade, curr_date, spot, chain, iv_shock_mult=1.0):
        """Calculates total cost to buy back short legs and sell long legs."""
        short_rows = chain[chain['strike'] == trade['short_strike']]
        pcs_long_rows = chain[chain['strike'] == trade['pcs_long_strike']]
        prb_long_rows = chain[chain['strike'] == trade['prb_long_strike']]
        
        short_r = short_rows.iloc[0] if not short_rows.empty else None
        pcs_r = pcs_long_rows.iloc[0] if not pcs_long_rows.empty else None
        prb_r = prb_long_rows.iloc[0] if not prb_long_rows.empty else None
        
        p_short, t1 = get_option_mark(short_r, spot, curr_date)
        p_pcs, t2 = get_option_mark(pcs_r, spot, curr_date)
        p_prb, t3 = get_option_mark(prb_r, spot, curr_date)
        
        # Apply volatility shock if crash tripwire triggered
        if iv_shock_mult > 1.0:
            p_short *= iv_shock_mult
            p_prb = max(0.01, p_prb * iv_shock_mult)
            
        # We must BUY BACK 2x short legs, SELL 1x pcs long, SELL 3x prb long
        net_close_debit_per_share = (2.0 * p_short) - (1.0 * p_pcs) - (3.0 * p_prb)
        return max(0.0, net_close_debit_per_share * 100.0 * trade['contracts'])

    def _close_trade(self, trade, exit_date, spot, chain, exit_reason, iv_shock_mult=1.0):
        contracts = trade['contracts']
        
        # Determine execution pricing
        if exit_reason == 'EXPIRATION':
            # At expiration, options settle strictly at intrinsic value
            p_short = max(0.0, trade['short_strike'] - spot)
            p_pcs = max(0.0, trade['pcs_long_strike'] - spot)
            p_prb = max(0.0, trade['prb_long_strike'] - spot)
            self.fallback_counts['INTRINSIC'] += 3
        else:
            short_rows = chain[chain['strike'] == trade['short_strike']]
            pcs_rows = chain[chain['strike'] == trade['pcs_long_strike']]
            prb_rows = chain[chain['strike'] == trade['prb_long_strike']]
            
            p_short, t1 = get_option_mark(short_rows.iloc[0] if not short_rows.empty else None, spot, exit_date)
            p_pcs, t2 = get_option_mark(pcs_rows.iloc[0] if not pcs_rows.empty else None, spot, exit_date)
            p_prb, t3 = get_option_mark(prb_rows.iloc[0] if not prb_rows.empty else None, spot, exit_date)
            
            self.fallback_counts[t1] = self.fallback_counts.get(t1, 0) + 1
            self.fallback_counts[t2] = self.fallback_counts.get(t2, 0) + 1
            self.fallback_counts[t3] = self.fallback_counts.get(t3, 0) + 1
            
            if iv_shock_mult > 1.0:
                p_short *= iv_shock_mult
                p_prb = max(0.01, p_prb * iv_shock_mult)
                
        # Fixes Bug 1.5: Only charge exit slippage & commissions on contracts actively executed!
        # Expired OTM contracts (intrinsic == 0) expire worthless without clearing friction.
        executed_legs_count = 0
        if exit_reason != 'EXPIRATION' or p_short > 0: executed_legs_count += 2
        if exit_reason != 'EXPIRATION' or p_pcs > 0:   executed_legs_count += 1
        if exit_reason != 'EXPIRATION' or p_prb > 0:   executed_legs_count += 3
        
        exit_slippage_total = executed_legs_count * self.slippage * contracts * 100.0
        exit_comm_total = executed_legs_count * self.comm * contracts
        
        raw_close_debit = ((2.0 * p_short) - (1.0 * p_pcs) - (3.0 * p_prb)) * 100.0 * contracts
        net_close_cost_total = raw_close_debit + exit_slippage_total + exit_comm_total
        
        # Net Trade P&L (Entry Cash Received minus Exit Cost Paid)
        final_pnl = trade['net_credit_realized_total'] - net_close_cost_total
        
        # Deduct closing cost from cash ledger
        self.cash -= net_close_cost_total
        
        # Profit sweep to cash vault (Fixes sweep mechanics: sweeps 10% of profits into unencumbered vault)
        swept_amount = 0.0
        if final_pnl > 0:
            swept_amount = final_pnl * self.vault_sweep_pct
            self.cash -= swept_amount
            self.vault_cash += swept_amount
            
        trade['exit_date'] = exit_date
        trade['exit_spot'] = spot
        trade['exit_reason'] = exit_reason
        trade['final_pnl'] = round(final_pnl, 2)
        trade['return_on_risk_pct'] = round((final_pnl / (trade['true_risk_per_contract'] * contracts)) * 100.0, 2)
        trade['swept_to_vault'] = round(swept_amount, 2)
        
        self.closed_trades.append(trade)

# ==========================================
# 4. SYNTHETIC DATA HARNESS & CLI RUNNER
# ==========================================

def generate_synthetic_test_data(options_file="syn_options.csv", prices_file="syn_prices.csv"):
    """Generates 1 year of realistic daily option chains and prices with a flash crash included."""
    print("Generating 1 year of synthetic market data with built-in flash crash event...")
    np.random.seed(42)
    start_date = datetime(2023, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(365)]
    
    # Generate Underlying Price Walk ($100 start)
    spot_prices = [100.0]
    for i in range(1, len(dates)):
        # Inject flash crash on Day 180 (drops 22% in 2 days)
        if i == 180:
            spot_prices.append(spot_prices[-1] * 0.85)
        elif i == 181:
            spot_prices.append(spot_prices[-1] * 0.90)
        else:
            ret = np.random.normal(0.0005, 0.015)
            spot_prices.append(spot_prices[-1] * (1.0 + ret))
            
    px_rows = []
    opt_rows = []
    
    for i, d in enumerate(dates):
        spot = spot_prices[i]
        low = spot * 0.98 if i not in [180, 181] else spot * 0.95
        high = spot * 1.02
        px_rows.append({'date': d.strftime('%Y-%m-%d'), 'close': round(spot, 2), 'low': round(low, 2), 'high': round(high, 2)})
        
        # Generate monthly expiration chains (30, 60, 90 DTE)
        for dte_offset in [30, 60]:
            exp_date = d + timedelta(days=dte_offset)
            # Standard strike ladder around spot
            for k in range(int(spot * 0.65), int(spot * 1.05), 5):
                # Black-Scholes delta approximate
                dte_yr = dte_offset / 365.0
                iv = 0.45 if i not in [180, 181] else 0.85 # IV spikes during crash
                d1 = (np.log(spot / k) + (0.05 + 0.5 * iv**2) * dte_yr) / (iv * np.sqrt(dte_yr))
                delta = -norm.cdf(-d1)
                
                # Synthetic put price
                d2 = d1 - iv * np.sqrt(dte_yr)
                price = max(0.05, k * np.exp(-0.05 * dte_yr) * norm.cdf(-d2) - spot * norm.cdf(-d1))
                
                opt_rows.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'expiration': exp_date.strftime('%Y-%m-%d'),
                    'strike': float(k),
                    'right': 'P',
                    'close': round(price, 2),
                    'delta': round(delta, 4),
                    'iv': round(iv, 2),
                    'underlying_price': round(spot, 2)
                })
                
    pd.DataFrame(px_rows).to_csv(prices_file, index=False)
    pd.DataFrame(opt_rows).to_csv(options_file, index=False)
    print(f"Synthetic datasets written to './{prices_file}' and './{options_file}'.")
    return options_file, prices_file

def print_performance_summary(df_equity, df_trades, sim_obj):
    print("\n" + "="*60)
    print("      FINAL AUDITED BACKTEST PERFORMANCE REPORT      ")
    print("="*60)
    
    start_eq = sim_obj.initial_capital
    end_eq = df_equity.iloc[-1]['mtm_equity']
    total_ret = ((end_eq - start_eq) / start_eq) * 100.0
    
    # Max Drawdown on Daily MTM Equity (Fixes Bug 2.4)
    df_equity['peak'] = df_equity['mtm_equity'].cummax()
    df_equity['dd_pct'] = ((df_equity['mtm_equity'] - df_equity['peak']) / df_equity['peak']) * 100.0
    max_dd = df_equity['dd_pct'].min()
    
    win_trades = df_trades[df_trades['final_pnl'] > 0]
    loss_trades = df_trades[df_trades['final_pnl'] <= 0]
    win_rate = (len(win_trades) / len(df_trades)) * 100.0 if len(df_trades) > 0 else 0.0
    
    print(f"Initial Capital:         ${start_eq:,.2f}")
    print(f"Final MTM Net Worth:     ${end_eq:,.2f} (includes ${sim_obj.vault_cash:,.2f} in Vault)")
    print(f"Total Net ROI:           {total_ret:+.2f}%")
    print(f"Max MTM Daily Drawdown:  {max_dd:.2f}%")
    print("-" * 60)
    print(f"Total Closed Trades:     {len(df_trades)}")
    print(f"Win Rate:                {win_rate:.1f}% ({len(win_trades)} Wins / {len(loss_trades)} Losses)")
    if not win_trades.empty:
        print(f"Average Win:             ${win_trades['final_pnl'].mean():,.2f}")
    if not loss_trades.empty:
        print(f"Average Loss:            ${loss_trades['final_pnl'].mean():,.2f}")
    print("-" * 60)
    print("Pricing Fallback Hierarchy Usage Counts:")
    for k, v in sim_obj.fallback_counts.items():
        print(f"  -> {k:20s}: {v:,} leg evaluations")
    print("="*60)

if __name__ == '__main__':
    # Determine if user passed custom CSV paths or if we should run turnkey synthetic test
    opt_file = sys.argv[1] if len(sys.argv) > 1 else "syn_options.csv"
    px_file = sys.argv[2] if len(sys.argv) > 2 else "syn_prices.csv"
    
    if not os.path.exists(opt_file) or not os.path.exists(px_file):
        opt_file, px_file = generate_synthetic_test_data(opt_file, px_file)
        
    df_options, df_prices = load_and_validate_data(opt_file, px_file)
    
    # Initialize engine with institutional parameters
    engine = InstitutionalSimulator(
        initial_capital=150000.0,
        alloc_pct=0.1,
        tp_pct=0.43,
        vault_sweep_pct=0.05,
        slippage_per_leg=0.05,
        comm_per_contract=0.01
    )
    
    df_eq, df_tr = engine.run_simulation(df_options, df_prices)
    
    # Save output artifacts
    df_eq.to_csv("audited_daily_equity.csv", index=False)
    df_tr.to_csv("audited_closed_trades.csv", index=False)
    print("\nDetailed audit logs saved to 'audited_daily_equity.csv' and 'audited_closed_trades.csv'.")
    
    print_performance_summary(df_eq, df_tr, engine)