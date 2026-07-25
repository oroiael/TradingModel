import numpy as np
import pandas as pd

ANN = 252

def simulate_consolidated_portfolio(d, option_greeks, slip_bps=0.0003, borrow_cost_ann=0.08):
    """
    Simulates the true netted portfolio exposure.
    
    Parameters:
    d: DataFrame with daily Open, Close, Prev_Close, and trailing RV.
    option_greeks: DataFrame mapped to dates containing the daily delta of the held straddle.
    slip_bps: Half-spread + market impact per trade (e.g., 3 bps).
    borrow_cost_ann: Annualized cost to borrow SOXL when net short (e.g., 8%).
    """
    # 1. Define external rates (Using a synthetic SOFR proxy for the 2020-2026 window)
    # In live implementation, merge actual daily SOFR rates here.
    sofr_proxy = np.where(d.index.year <= 2021, 0.001, 
                 np.where(d.index.year == 2022, 0.02, 0.05))
    daily_cash_rate = sofr_proxy / ANN
    daily_borrow_rate = borrow_cost_ann / ANN

    # 2. Daily Gating and Target Weights
    rv20 = (d["open"] / d["prev_close"] - 1).rolling(20).std().shift(1) * np.sqrt(ANN)
    up_trend = (d["close"] > d["close"].rolling(50).mean()).shift(1).fillna(False)
    
    # Overnight sleeve target weight (0% to 100%)
    w_overnight = np.clip((0.60 / rv20).fillna(0.0), 0, 1.0) * up_trend
    
    # Portfolio allocation weights (e.g., 40% Overnight strategy / 60% Straddle)
    alloc_ON = 0.40
    alloc_OPT = 0.60

    # 3. State Tracking
    pnl = np.zeros(len(d))
    current_soxl_weight = 0.0  # Net SOXL exposure as a % of NAV

    for i in range(1, len(d)):
        td = d.index[i]
        
        # Extract daily option delta (delta of the straddle, so we need to hold -delta to hedge)
        # Note: If no options are held due to VRP gate, opt_delta = 0
        opt_delta = option_greeks.get(td, 0.0) 
        hedge_weight = alloc_OPT * (-opt_delta)
        
        # ==========================================
        # STATE 1: 15:55 (Close) - Enter Overnight
        # ==========================================
        # Target net SOXL = (Overnight target) + (Option hedge)
        target_soxl_close = (alloc_ON * w_overnight.iloc[i]) + hedge_weight
        
        # Calculate Netting & Trading Costs
        trade_size_close = abs(target_soxl_close - current_soxl_weight)
        pnl[i] -= trade_size_close * slip_bps
        current_soxl_weight = target_soxl_close
        
        # Calculate Overnight Holding PnL & Costs
        on_return = (d["open"].iloc[i] / d["prev_close"].iloc[i]) - 1
        pnl[i] += current_soxl_weight * on_return
        
        # Borrow cost applies if net position is negative overnight
        if current_soxl_weight < 0:
            pnl[i] -= abs(current_soxl_weight) * daily_borrow_rate
            
        # ==========================================
        # STATE 2: 09:30 (Open) - Exit Overnight
        # ==========================================
        # Overnight weight drops to 0. We ONLY hold the option hedge intraday.
        target_soxl_open = hedge_weight 
        
        # Calculate Netting & Trading Costs at Open
        trade_size_open = abs(target_soxl_open - current_soxl_weight)
        pnl[i] -= trade_size_open * slip_bps
        current_soxl_weight = target_soxl_open
        
        # Calculate Intraday Holding PnL (Only the hedge moves intraday)
        id_return = (d["close"].iloc[i] / d["open"].iloc[i]) - 1
        pnl[i] += current_soxl_weight * id_return
        
        # ==========================================
        # CASH YIELD
        # ==========================================
        # Uninvested cash earns the risk-free rate
        cash_weight = 1.0 - abs(current_soxl_weight)
        if cash_weight > 0:
            pnl[i] += cash_weight * daily_cash_rate[i]

    # Combine with Option Premium PnL (handled separately in your bracket_weekly module)
    # total_pnl = pnl + option_premium_pnl
    return pd.Series(pnl, index=d.index)