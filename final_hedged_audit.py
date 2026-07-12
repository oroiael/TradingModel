import math

import pandas as pd


def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def black_scholes_put(S, K, T, r, sigma):
    if T <= 0: return max(0.0, K - S)
    if sigma <= 0: return max(0.0, K - S) * math.exp(-r * T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def structure_max_loss(short_k, long_k, sell_k, buy_k, hedge_ratio,
                       net_credit_raw, prb_net_cost, friction):
    """Worst-case P&L (per share, positive number) of the combined 6-leg
    structure at expiration. The payoff is piecewise linear, so evaluating
    at the strike kinks (and 0, and above the top strike) is exact. This is
    the number position sizing must use -- the income-spread width alone
    ignores the backspread's loss trough between its strikes."""
    def pnl(s):
        income = net_credit_raw - (max(0.0, short_k - s) - max(0.0, long_k - s))
        hedge = (hedge_ratio * max(0.0, buy_k - s) - max(0.0, sell_k - s)) - prb_net_cost
        return income + hedge - friction
    kinks = [0.0, buy_k, long_k, sell_k, short_k, short_k + 1.0]
    return -min(pnl(s) for s in kinks)


class FinalAuditSimulator:
    def __init__(self, options_data_path, ibkr_5min_path, initial_capital=150000):
        self.initial_capital = initial_capital

        print(f"Loading Options EOD Dataset: {options_data_path}...")
        df = pd.read_csv(options_data_path, low_memory=False)

        date_col = next((c for c in ('date', 'trade_date') if c in df.columns), None)
        if date_col is None:
            raise ValueError("Options file needs a 'date' or 'trade_date' column.")
        type_col = next((c for c in ('type', 'right') if c in df.columns), None)
        if type_col is None:
            raise ValueError("Options file needs a 'type' or 'right' column.")
        for col in ('expiration', 'strike', 'close', 'delta', 'underlying_price'):
            if col not in df.columns:
                raise ValueError(f"Options file is missing required column '{col}'.")

        df['Date'] = pd.to_datetime(df[date_col])
        df['Expiration'] = pd.to_datetime(df['expiration'])
        df['DTE'] = (df['Expiration'] - df['Date']).dt.days
        self.df = df

        print("Building True Data Options Price & IV Cache in RAM...")
        put_df = df[df[type_col].astype(str).str.upper().isin(['P', 'PUT'])].copy()
        if put_df.empty:
            raise ValueError("No put rows found in the options file.")

        # Normalize the delta sign convention once: put deltas are negative
        # from here on, regardless of how the vendor stored them.
        put_df['delta'] = -put_df['delta'].abs()

        dupes = int(put_df.duplicated(subset=['Date', 'Expiration', 'strike']).sum())
        if dupes:
            print(f"WARNING: {dupes} duplicate (date, expiration, strike) put rows; keeping the last of each.")

        self.put_df = put_df
        self.options_cache = put_df.set_index(['Date', 'Expiration', 'strike'])['close'].to_dict()

        iv_cols = ['iv', 'implied_volatility', 'implied_vol', 'volatility', 'implied_volatility_1545']
        iv_col = next((col for col in put_df.columns if col.lower() in iv_cols), None)
        if iv_col:
            iv_series = pd.to_numeric(put_df[iv_col], errors='coerce')
            med = iv_series.median()
            if pd.notna(med) and med > 3.0:
                print(f"NOTE: IV column '{iv_col}' looks like percent (median {med:.1f}); dividing by 100.")
                iv_series = iv_series / 100.0
            self.iv_cache = put_df.assign(_iv=iv_series).set_index(
                ['Date', 'Expiration', 'strike'])['_iv'].to_dict()
        else:
            print("WARNING: no IV column found; model marks will use the default fallback IV.")
            self.iv_cache = {}

        self.daily_prices = df.groupby('Date')['underlying_price'].first().sort_index().to_dict()
        if not self.daily_prices:
            raise ValueError("No usable underlying prices in the options file.")

        print(f"Loading IBKR 5-Minute Intraday Data: {ibkr_5min_path}...")
        ibkr_df = pd.read_csv(ibkr_5min_path)
        ib_date_col = next((c for c in ibkr_df.columns if 'date' in c.lower() or 'time' in c.lower()), None)
        ib_low_col = next((c for c in ibkr_df.columns if c.lower() == 'low'), None) \
            or next((c for c in ibkr_df.columns if 'low' in c.lower()), None)
        if ib_date_col is None or ib_low_col is None:
            raise ValueError("IBKR file needs a date/time column and a 'low' column.")

        stamps = pd.to_datetime(ibkr_df[ib_date_col].astype(str), format='%Y%m%d %H:%M:%S', errors='coerce')
        if stamps.isna().all():
            stamps = pd.to_datetime(ibkr_df[ib_date_col].astype(str), errors='coerce')
        if stamps.isna().all():
            raise ValueError(f"Could not parse IBKR datetime column '{ib_date_col}'.")
        if stamps.isna().any():
            print(f"WARNING: dropped {int(stamps.isna().sum())} unparseable IBKR rows.")
        ibkr_df = ibkr_df.assign(FlatDate=stamps.dt.normalize()).dropna(subset=['FlatDate'])
        self.daily_lows = ibkr_df.groupby('FlatDate')[ib_low_col].min().to_dict()

        missing_lows = sum(1 for d in self.daily_prices if d not in self.daily_lows)
        if missing_lows:
            print(f"WARNING: {missing_lows} trading day(s) have no IBKR intraday low; "
                  f"the tripwire uses the EOD price on those days.")

        # data-coverage instrumentation: every leg mark is counted by source
        self.coverage = {'quote': 0, 'intrinsic': 0, 'bs_model': 0,
                         'iv_fallback': 0, 'decision_gap_days': 0}

        print("Final Audit Engine Ready.\n")

    def put_value(self, date, exp, strike, spot, fallback_iv, r):
        """Mark one put leg. Priority: real quote -> intrinsic (at/after
        expiry) -> Black-Scholes with the day's IV or the caller's fallback
        IV. A missing quote is never a silent $0.00."""
        v = self.options_cache.get((date, exp, strike))
        if v is not None:
            self.coverage['quote'] += 1
            return v
        if date >= exp:
            self.coverage['intrinsic'] += 1
            return max(0.0, strike - spot)
        iv = self.iv_cache.get((date, exp, strike))
        if iv is None or not iv > 0:
            iv = fallback_iv
            self.coverage['iv_fallback'] += 1
        self.coverage['bs_model'] += 1
        t = max(1, (exp - date).days) / 365.0
        return black_scholes_put(spot, strike, t, r, iv)

    def mark_trade(self, trade, date, spot, r, hedge_ratio, iv_mult=1.0):
        """Unrealized P&L per contract (per share) of one open trade, entry
        friction included."""
        ivs = trade['Leg IVs']
        exp = trade['Expiration']
        sp = self.put_value(date, exp, trade['Short Strike'], spot, ivs[trade['Short Strike']] * iv_mult, r)
        lp = self.put_value(date, exp, trade['Long Strike'], spot, ivs[trade['Long Strike']] * iv_mult, r)
        hs = self.put_value(date, exp, trade['Hedge Sell Strike'], spot, ivs[trade['Hedge Sell Strike']] * iv_mult, r)
        hb = self.put_value(date, exp, trade['Hedge Buy Strike'], spot, ivs[trade['Hedge Buy Strike']] * iv_mult, r)
        income_u = trade['Entry Net Credit'] - (sp - lp)
        hedge_u = (hedge_ratio * hb - hs) - trade['PRB Entry Net Cost']
        return income_u + hedge_u - trade['Entry Friction']

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
        slippage_per_leg = 0.05           # $0.05 slippage per executed leg
        commission_per_contract = 0.65    # $0.65 per contract per executed leg
        base_sweep_pct = 0.10             # 10% Cash sweep
        max_contracts = 300               # Contract Limit
        default_iv = 0.80                 # last-resort IV for model marks

        legs_per_side = 2 + 1 + hedge_ratio
        per_leg_cost = slippage_per_leg + commission_per_contract / 100.0
        friction_side = legs_per_side * per_leg_cost      # one side, per share
        friction_round_trip = friction_side * 2.0

        print("--- EXECUTING FINAL TRADE-BY-TRADE AUDIT ---")
        trading_days = sorted(self.daily_prices.keys())

        trading_balance = self.initial_capital
        swept_cash = 0.0
        open_trades, closed_trades = [], []

        equity_curve = []
        high_water_mark = self.initial_capital
        max_drawdown_pct = 0.0

        for current_date in trading_days:
            current_underlying_price = self.daily_prices.get(current_date)
            current_underlying_low = self.daily_lows.get(current_date, current_underlying_price)

            # --- 1. PROCESS OPEN TRADES ---
            still_open = []
            for trade in open_trades:
                exp = trade['Expiration']
                ivs = trade['Leg IVs']
                curr_short_price = self.options_cache.get((current_date, exp, trade['Short Strike']))
                curr_long_price = self.options_cache.get((current_date, exp, trade['Long Strike']))
                income_quotes_ok = curr_short_price is not None and curr_long_price is not None

                is_closed, res_reason = False, ""
                income_pnl, hedge_pnl = 0.0, 0.0

                # A. INTRADAY TRIPWIRE (Flash Crash) -- checked FIRST because
                # it needs only the intraday low, never option quotes. A quote
                # gap must not disable the stop-loss.
                if current_underlying_low <= trade['Short Strike']:
                    # Income engine: assume the stop fills at stop_loss_mult x
                    # credit; if the EOD spread is worth even more, assume the
                    # worse (slipped) fill instead.
                    exit_cost = trade['Entry Net Credit'] * stop_loss_mult
                    if income_quotes_ok:
                        exit_cost = max(exit_cost, curr_short_price - curr_long_price)
                    income_pnl = trade['Entry Net Credit'] - exit_cost

                    # Hedge engine: mark both legs at the EOD price (same fill
                    # assumption as the income side). Real quotes win; the
                    # model fallback uses a vega-shocked IV.
                    hs = self.put_value(current_date, exp, trade['Hedge Sell Strike'],
                                        current_underlying_price,
                                        ivs[trade['Hedge Sell Strike']] * vega_shock_multiplier,
                                        risk_free_rate)
                    hb = self.put_value(current_date, exp, trade['Hedge Buy Strike'],
                                        current_underlying_price,
                                        ivs[trade['Hedge Buy Strike']] * vega_shock_multiplier,
                                        risk_free_rate)
                    hedge_pnl = ((hedge_ratio * hb) - hs) - trade['PRB Entry Net Cost']
                    is_closed, res_reason = True, "CRASH (TRIPWIRE)"

                # B. EXPIRATION -- every leg settles at quote or intrinsic,
                # never a silent $0.00 for a missing row.
                elif current_date >= exp:
                    sp = self.put_value(current_date, exp, trade['Short Strike'],
                                        current_underlying_price, ivs[trade['Short Strike']], risk_free_rate)
                    lp = self.put_value(current_date, exp, trade['Long Strike'],
                                        current_underlying_price, ivs[trade['Long Strike']], risk_free_rate)
                    hs = self.put_value(current_date, exp, trade['Hedge Sell Strike'],
                                        current_underlying_price, ivs[trade['Hedge Sell Strike']], risk_free_rate)
                    hb = self.put_value(current_date, exp, trade['Hedge Buy Strike'],
                                        current_underlying_price, ivs[trade['Hedge Buy Strike']], risk_free_rate)
                    income_pnl = trade['Entry Net Credit'] - (sp - lp)
                    hedge_pnl = ((hedge_ratio * hb) - hs) - trade['PRB Entry Net Cost']
                    is_closed, res_reason = True, "EXPIRATION"

                # C. EOD STOP-LOSS / TAKE-PROFIT -- decisions still require
                # real income quotes; a gap day is counted, not guessed.
                elif income_quotes_ok:
                    current_spread_cost = curr_short_price - curr_long_price
                    if current_spread_cost >= trade['Entry Net Credit'] * stop_loss_mult:
                        is_closed, res_reason = True, "STOP-LOSS (EOD)"
                    elif current_spread_cost <= trade['Entry Net Credit'] * (1 - take_profit_pct):
                        is_closed, res_reason = True, "TAKE-PROFIT"
                    if is_closed:
                        income_pnl = trade['Entry Net Credit'] - current_spread_cost
                        hs = self.put_value(current_date, exp, trade['Hedge Sell Strike'],
                                            current_underlying_price, ivs[trade['Hedge Sell Strike']], risk_free_rate)
                        hb = self.put_value(current_date, exp, trade['Hedge Buy Strike'],
                                            current_underlying_price, ivs[trade['Hedge Buy Strike']], risk_free_rate)
                        hedge_pnl = ((hedge_ratio * hb) - hs) - trade['PRB Entry Net Cost']
                else:
                    self.coverage['decision_gap_days'] += 1

                if is_closed:
                    # friction: every executed leg pays slippage + commission,
                    # on BOTH sides; legs that expire are settled, not traded
                    exit_legs = 0 if res_reason == "EXPIRATION" else legs_per_side
                    entry_slip = legs_per_side * slippage_per_leg
                    exit_slip = exit_legs * slippage_per_leg
                    commissions = (legs_per_side + exit_legs) * commission_per_contract / 100.0
                    total_friction = entry_slip + exit_slip + commissions

                    net_pnl_per_contract = (income_pnl + hedge_pnl - total_friction) * 100

                    # No loss cap: report what the model produced. Losses can
                    # exceed the expiration-payoff max risk pre-expiry (vol
                    # marks); flag them loudly instead of rewriting them.
                    if net_pnl_per_contract < -trade['Max Risk Per Contract'] - 0.01:
                        print(f"WARNING {current_date.date()}: realized loss "
                              f"{net_pnl_per_contract:,.2f}/contract exceeds the structural "
                              f"max risk {-trade['Max Risk Per Contract']:,.2f} (pre-expiry marks).")

                    total_combined_pnl = net_pnl_per_contract * trade['Contracts']

                    sweep_amount = 0.0
                    if total_combined_pnl > 0:
                        if trade['Contracts'] >= max_contracts: sweep_amount = total_combined_pnl
                        else: sweep_amount = total_combined_pnl * base_sweep_pct
                        swept_cash += sweep_amount
                        trading_balance += (total_combined_pnl - sweep_amount)
                    else:
                        trading_balance += total_combined_pnl

                    closed_trades.append({
                        'Entry Date': trade['Entry Date'],
                        'Exit Date': current_date,
                        'Reason': res_reason,
                        'Contracts': trade['Contracts'],
                        'Inc. Short Strike': f"${trade['Short Strike']:.2f}",
                        'Inc. Long Strike': f"${trade['Long Strike']:.2f}",
                        'Hdg. Sell Strike': f"${trade['Hedge Sell Strike']:.2f}",
                        'Hdg. Buy Strike': f"${trade['Hedge Buy Strike']:.2f}",
                        'Max Risk/Ct ($)': round(trade['Max Risk Per Contract'], 2),
                        'Net Income PnL ($)': round(income_pnl * 100 * trade['Contracts'], 2),
                        'Net Hedge PnL ($)': round(hedge_pnl * 100 * trade['Contracts'], 2),
                        'Slippage Paid ($)': round((entry_slip + exit_slip) * 100 * trade['Contracts'], 2),
                        'Commissions ($)': round(commissions * 100 * trade['Contracts'], 2),
                        'Total Net PnL ($)': round(total_combined_pnl, 2),
                        'Trading Balance ($)': round(trading_balance, 2),
                        'Cash Vault ($)': round(swept_cash, 2),
                        'Realized Net Worth ($)': round(trading_balance + swept_cash, 2),
                    })
                else:
                    still_open.append(trade)

            open_trades = still_open

            # --- 2. PROCESS NEW ENTRIES ---
            if len(open_trades) < max_trades:
                daily_puts = self.put_df[(self.put_df['Date'] == current_date) & (self.put_df['DTE'].between(*dte_range))]
                if not daily_puts.empty:
                    self._try_enter(daily_puts, current_date, trading_balance, open_trades,
                                    target_width, min_credit, alloc_pct, max_contracts,
                                    hedge_ratio, target_sell_delta, max_hedge_debit,
                                    friction_round_trip, default_iv)

            # --- 3. DAILY MARK-TO-MARKET EQUITY CURVE ---
            open_mtm = sum(
                self.mark_trade(t, current_date, current_underlying_price, risk_free_rate, hedge_ratio)
                * 100 * t['Contracts']
                for t in open_trades)
            equity = trading_balance + swept_cash + open_mtm
            equity_curve.append({'Date': current_date, 'Equity': equity})
            if equity > high_water_mark: high_water_mark = equity
            if high_water_mark > 0:
                dd = (high_water_mark - equity) / high_water_mark * 100
                if dd > max_drawdown_pct: max_drawdown_pct = dd

        self._report(closed_trades, open_trades, equity_curve, trading_balance,
                     swept_cash, max_drawdown_pct, trading_days, risk_free_rate)

    def _try_enter(self, daily_puts, current_date, trading_balance, open_trades,
                   target_width, min_credit, alloc_pct, max_contracts,
                   hedge_ratio, target_sell_delta, max_hedge_debit,
                   friction_round_trip, default_iv):
        short_candidates = daily_puts.iloc[(daily_puts['delta'].abs() - 0.20).abs().argsort()]
        long_candidates = daily_puts.iloc[(daily_puts['delta'].abs() - 0.05).abs().argsort()]
        if short_candidates.empty or long_candidates.empty: return
        short_put = short_candidates.iloc[0]

        valid_long = None
        for _, long_put in long_candidates.iterrows():
            if short_put['Expiration'] != long_put['Expiration']: continue
            if target_width - 0.5 <= (short_put['strike'] - long_put['strike']) <= target_width + 0.5:
                valid_long = long_put
                break
        if valid_long is None: return

        net_credit_raw = short_put['close'] - valid_long['close']
        if net_credit_raw < min_credit: return

        # 1. Target Sell Delta (deltas are normalized negative at load)
        prb_sell_cands = daily_puts[daily_puts['Expiration'] == short_put['Expiration']]
        if prb_sell_cands.empty: return
        prb_sell = prb_sell_cands.iloc[(prb_sell_cands['delta'] - target_sell_delta).abs().argsort()].iloc[0]

        # 2. Target Buy Strikes under max debit
        target_buy_cost_max = (prb_sell['close'] + max_hedge_debit) / hedge_ratio
        prb_buy_cands = daily_puts[(daily_puts['Expiration'] == short_put['Expiration'])
                                   & (daily_puts['strike'] < prb_sell['strike'])
                                   & (daily_puts['close'] <= target_buy_cost_max)]
        if prb_buy_cands.empty: return
        prb_buy = prb_buy_cands.sort_values(by='strike', ascending=False).iloc[0]
        prb_net_cost = (hedge_ratio * prb_buy['close']) - prb_sell['close']

        net_credit_realized = net_credit_raw - prb_net_cost - friction_round_trip
        if net_credit_realized < 0.20: return

        # Size on the TRUE worst case of the combined 6-leg structure, not
        # just the income-spread width.
        max_risk_dollars = structure_max_loss(
            short_put['strike'], valid_long['strike'], prb_sell['strike'], prb_buy['strike'],
            hedge_ratio, net_credit_raw, prb_net_cost, friction_round_trip) * 100
        if max_risk_dollars <= 0: return

        contracts = math.floor((trading_balance * alloc_pct) / max_risk_dollars)
        if contracts > max_contracts: contracts = max_contracts
        if contracts < 1: return

        def entry_iv(strike):
            v = self.iv_cache.get((current_date, short_put['Expiration'], strike))
            return v if (v is not None and v == v and v > 0) else default_iv

        leg_ivs = {
            strike: entry_iv(strike)
            for strike in {short_put['strike'], valid_long['strike'],
                           prb_sell['strike'], prb_buy['strike']}
        }

        legs_per_side = 2 + 1 + hedge_ratio
        open_trades.append({
            'Entry Date': current_date,
            'Expiration': short_put['Expiration'],
            'Short Strike': short_put['strike'],
            'Long Strike': valid_long['strike'],
            'Entry Net Credit': net_credit_raw,
            'Hedge Sell Strike': prb_sell['strike'],
            'Hedge Buy Strike': prb_buy['strike'],
            'PRB Entry Net Cost': prb_net_cost,
            'Leg IVs': leg_ivs,
            'Entry Friction': friction_round_trip / 2.0,
            'Max Risk Per Contract': max_risk_dollars,
            'Contracts': contracts,
        })

    def _report(self, closed_trades, open_trades, equity_curve, trading_balance,
                swept_cash, max_drawdown_pct, trading_days, risk_free_rate):
        pnl_df = pd.DataFrame(closed_trades)
        eq_df = pd.DataFrame(equity_curve)

        if pnl_df.empty:
            print("No trades executed.")
            return

        for col in ['Entry Date', 'Exit Date']:
            pnl_df[col] = pd.to_datetime(pnl_df[col]).dt.strftime('%Y-%m-%d')
        pnl_df.to_csv('SOXL_Final_Hedged_Audit.csv', index=False)
        eq_df.to_csv('SOXL_Final_Hedged_Equity_Curve.csv', index=False)

        wins = len(pnl_df[pnl_df['Total Net PnL ($)'] > 0])
        tripwires = len(pnl_df[pnl_df['Reason'] == "CRASH (TRIPWIRE)"])
        win_rate = (wins / len(pnl_df)) * 100

        final_equity = eq_df['Equity'].iloc[-1]
        open_mtm = final_equity - trading_balance - swept_cash
        roi = ((final_equity - self.initial_capital) / self.initial_capital) * 100

        n_days = (trading_days[-1] - trading_days[0]).days
        cagr = ((final_equity / self.initial_capital) ** (365.25 / n_days) - 1) * 100 if n_days > 0 and final_equity > 0 else float('nan')

        rets = eq_df['Equity'].pct_change().dropna()
        sharpe = float('nan')
        if len(rets) > 2 and rets.std() > 0:
            sharpe = (rets.mean() - risk_free_rate / 252) / rets.std() * math.sqrt(252)

        px = [self.daily_prices[d] for d in trading_days]
        buy_hold_roi = (px[-1] / px[0] - 1) * 100 if px[0] else float('nan')

        print(f"\n--- FINAL AUDIT COMPLETE ---")
        print(f"Total Closed Trades:   {len(pnl_df)}")
        print(f"Open at End (MTM):     {len(open_trades)} trade(s), ${open_mtm:,.2f} unrealized")
        print(f"Intraday Crashes:      {tripwires} (PRB Protected)")
        print(f"Win Rate (closed):     {win_rate:.2f}%")
        print("-" * 60)
        print(f"Final Trading Margin:  ${trading_balance:,.2f}")
        print(f"Final Cash Vault:      ${swept_cash:,.2f}")
        print(f"Final Equity (MTM):    ${final_equity:,.2f}")
        print(f"Total ROI:             {roi:.2f}%")
        print(f"CAGR:                  {cagr:.2f}%")
        print(f"Sharpe (daily, ann.):  {sharpe:.2f}")
        print(f"Max Drawdown (daily MTM): {max_drawdown_pct:.2f}%")
        print(f"SOXL Buy & Hold ROI:   {buy_hold_roi:.2f}%  (same window)")
        print("-" * 60)
        c = self.coverage
        total_marks = c['quote'] + c['intrinsic'] + c['bs_model']
        if total_marks:
            print(f"Data coverage: {c['quote']}/{total_marks} leg marks from real quotes "
                  f"({c['quote'] / total_marks * 100:.1f}%), {c['intrinsic']} intrinsic settles, "
                  f"{c['bs_model']} model marks ({c['iv_fallback']} used fallback IV).")
        if c['decision_gap_days']:
            print(f"Quote-gap days (TP/stop decision skipped, tripwire still active): {c['decision_gap_days']}")
        print(">> 'SOXL_Final_Hedged_Audit.csv' and 'SOXL_Final_Hedged_Equity_Curve.csv' generated.")


if __name__ == "__main__":
    env = FinalAuditSimulator("SOXL_Master_Cleaned.csv", "SOXL_5min_3Years.csv", 150000)
    env.run_audit()
