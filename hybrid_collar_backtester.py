import math
import os
from collections import defaultdict

import numpy as np
import pandas as pd


class HybridCollarBacktester:
    """Weekly SOXL collar backtester.

    Strategy:
      * Enter on the first trading day of the week (falls back to the 2nd/3rd
        trading day if flat): buy shares in 100-lots, buy a ~put_target_dte-day
        ATM protective put, sell a weekly ATM covered call expiring that Friday.
      * On the first trading day of every later week, sell a fresh weekly call.
      * On the last trading day of the week at ~15:55, check assignment. If the
        stock is at/above the call strike the position is called away and the
        cycle completes; profit_sweep_pct of the realized cycle P&L is swept to
        an untouchable cash vault and the rest stays in the trading balance.
      * If the stock has rallied rally_threshold_pct above the CURRENT put
        strike, roll the put up to ATM (same expiration). If the put is within
        a week of expiring, roll it out to a fresh put_target_dte expiration.

    Accounting is pure cash-flow based: every external cash flow moves
    trading_balance exactly once and is appended to flow_log; a cycle's P&L is
    the sum of that cycle's flows. Net worth = trading_balance + cash_vault
    (+ mark-to-market of any open position). This holds the ledger identity
    trading_balance + cash_vault == initial_capital + sum(flow_log) at all
    times, which qa/qa_ledger_test.py asserts.

    Pricing: option marks come from the EOD options file, with contracts
    snapped to the nearest listed expiration/strike for that quote date. When
    a contract is missing, a Black-Scholes fallback (flat fallback_iv) is used
    and counted; the summary reports the fallback rate because a backtest
    priced mostly off the fallback model is not evidence about the market.
    Executions pay half the spread (option_half_spread_pct each side) plus
    commissions.
    """

    def __init__(self,
                 options_path="SOXL_Master_Cleaned.csv",
                 intraday_path="SOXL_5min_3Years.csv",
                 initial_capital=100000.0,
                 rally_threshold_pct=0.20,
                 allocation_pct=0.25,
                 profit_sweep_pct=0.10,
                 put_target_dte=180,
                 commission_per_contract=0.65,
                 stock_commission_per_share=0.005,
                 option_half_spread_pct=0.03,
                 fallback_iv=0.80,
                 risk_free_rate=0.04,
                 require_options_data=True):

        self.options_path = options_path
        self.intraday_path = intraday_path
        self.initial_capital = initial_capital
        self.trading_balance = initial_capital
        self.cash_vault = 0.0

        # Strategy Parameters
        self.allocation_pct = allocation_pct
        self.profit_sweep_pct = profit_sweep_pct
        self.put_target_dte = put_target_dte
        self.rally_threshold_pct = rally_threshold_pct

        # Friction / model parameters
        self.commission_per_contract = commission_per_contract
        self.stock_commission_per_share = stock_commission_per_share
        self.option_half_spread_pct = option_half_spread_pct
        self.fallback_iv = fallback_iv
        self.risk_free_rate = risk_free_rate
        self.require_options_data = require_options_data

        # State Tracking
        self.open_position = None
        self.trade_logs = []
        self.equity_curve = []          # (date, net_worth_mtm, underlying_price)
        self.flow_log = []              # (note, signed cash amount) for audit
        self.options_cache = {}         # (date, exp, 'C'/'P', strike) -> close
        self.chain_index = {}           # (date, 'C'/'P') -> {exp: [strikes]}
        self.intraday_by_day = {}
        self.trading_days = []

        # Diagnostics
        self.option_lookups = 0
        self.fallback_pricings = 0
        self.skipped_entries = 0
        self.skipped_rolls = 0
        self.negative_balance_events = 0

    # ------------------------------------------------------------------ data

    def load_and_prep_data(self):
        print(f"Loading 5-minute intraday stock data from {self.intraday_path}...")
        if not os.path.exists(self.intraday_path):
            raise FileNotFoundError(f"Cannot find {self.intraday_path}. Please ensure it is in the working directory.")

        df_5m = pd.read_csv(self.intraday_path, low_memory=False)

        col_map_5m = {}
        for col in df_5m.columns:
            c_low = str(col).strip().lower()
            if c_low in ['date', 'datetime', 'time', 'timestamp', 'bar_time']:
                col_map_5m[col] = 'Datetime'
            elif c_low in ['close', 'c', 'price', 'last']:
                col_map_5m[col] = 'close'
        df_5m = df_5m.rename(columns=col_map_5m)

        if 'Datetime' not in df_5m.columns or 'close' not in df_5m.columns:
            raise ValueError(f"No valid time/close columns found in {self.intraday_path}. "
                             f"Found columns: {list(df_5m.columns)}")

        # --- IBKR timestamp parser ---
        df_5m = df_5m.dropna(subset=['Datetime', 'close'])
        raw_dates = df_5m['Datetime'].astype(str).str.strip()
        raw_dates = raw_dates.str.replace(r'\s+', ' ', regex=True)
        raw_dates = raw_dates.str.replace(r' [a-zA-Z_]+/[a-zA-Z_]+$', '', regex=True)

        parsed_dates = pd.to_datetime(raw_dates, format='%Y%m%d %H:%M:%S', errors='coerce', utc=True)
        if parsed_dates.isna().any():
            parsed_dates = parsed_dates.fillna(
                pd.to_datetime(raw_dates, format='%Y-%m-%d %H:%M:%S', errors='coerce', utc=True))
        if parsed_dates.isna().any():
            sec_mask = raw_dates.str.match(r'^\d{10}$')
            ms_mask = raw_dates.str.match(r'^\d{13}$')
            if sec_mask.any():
                parsed_dates.loc[sec_mask] = pd.to_datetime(raw_dates[sec_mask].astype(np.int64), unit='s', utc=True)
            if ms_mask.any():
                parsed_dates.loc[ms_mask] = pd.to_datetime(raw_dates[ms_mask].astype(np.int64), unit='ms', utc=True)
        if parsed_dates.isna().any():
            parsed_dates = parsed_dates.fillna(pd.to_datetime(raw_dates, errors='coerce', utc=True))

        if parsed_dates.isna().all():
            raise ValueError("Could not parse any timestamps in the intraday file. "
                             f"First rows of the time column: {df_5m['Datetime'].head(5).tolist()}")

        df_5m['Datetime'] = parsed_dates.dt.tz_localize(None)
        df_5m = df_5m.dropna(subset=['Datetime']).sort_values('Datetime')
        df_5m['close'] = pd.to_numeric(df_5m['close'], errors='coerce')
        df_5m = df_5m.dropna(subset=['close'])
        df_5m['Date'] = df_5m['Datetime'].dt.normalize()

        self.intraday_by_day = {d: g[['Datetime', 'close']].reset_index(drop=True)
                                for d, g in df_5m.groupby('Date')}
        self.trading_days = sorted(self.intraday_by_day.keys())
        print(f"Loaded {len(df_5m):,} 5-minute bars across {len(self.trading_days)} trading days.")

        # --- ThetaData EOD options ---
        print(f"Loading options chains from {self.options_path}...")
        if not os.path.exists(self.options_path):
            msg = (f"Options file {self.options_path} not found - the entire backtest would run on the "
                   f"Black-Scholes fallback model and prove nothing about the market.")
            if self.require_options_data:
                raise FileNotFoundError(msg)
            print(f"WARNING: {msg}\nWARNING: Proceeding on synthetic prices (require_options_data=False).")
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

        required = {'Date', 'Expiration', 'strike', 'type', 'close'}
        missing = required - set(df_opt.columns)
        if missing:
            raise ValueError(f"Options file is missing required columns {sorted(missing)}. "
                             f"Found columns: {list(df_opt.columns)}")

        df_opt['Date'] = pd.to_datetime(df_opt['Date'], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()
        df_opt['Expiration'] = pd.to_datetime(df_opt['Expiration'], errors='coerce', utc=True).dt.tz_localize(None).dt.normalize()
        df_opt['strike'] = pd.to_numeric(df_opt['strike'], errors='coerce')
        df_opt['close'] = pd.to_numeric(df_opt['close'], errors='coerce')
        df_opt['type'] = df_opt['type'].astype(str).str.strip().str.upper().str[0]
        df_opt = df_opt.dropna(subset=['Date', 'Expiration', 'strike', 'close'])
        df_opt = df_opt[(df_opt['close'] > 0) & df_opt['type'].isin(['C', 'P'])]

        print("Caching RAM option chain dictionary...")
        keys = list(zip(df_opt['Date'], df_opt['Expiration'], df_opt['type'], df_opt['strike'].astype(float)))
        self.options_cache = dict(zip(keys, df_opt['close'].astype(float)))

        chain = defaultdict(lambda: defaultdict(set))
        for d, e, t, k in self.options_cache.keys():
            chain[(d, t)][e].add(k)
        self.chain_index = {dk: {e: sorted(s) for e, s in exps.items()} for dk, exps in chain.items()}

        if not self.options_cache:
            raise ValueError(f"Options file {self.options_path} loaded but produced zero usable quotes.")
        print(f"Options cache ready ({len(self.options_cache):,} contracts indexed).")

    # --------------------------------------------------------------- pricing

    def get_intraday_price(self, date, target_hour, target_minute, tolerance_minutes=240):
        """5-minute stock price closest to the target timestamp; None if the
        nearest bar is more than tolerance_minutes away (bad/missing data)."""
        day_bars = self.intraday_by_day.get(date)
        if day_bars is None or day_bars.empty:
            return None
        target_time = date + pd.Timedelta(hours=target_hour, minutes=target_minute)
        time_diffs = (day_bars['Datetime'] - target_time).abs()
        closest_idx = time_diffs.idxmin()
        if time_diffs.loc[closest_idx] > pd.Timedelta(minutes=tolerance_minutes):
            return None
        return float(day_bars.loc[closest_idx, 'close'])

    @staticmethod
    def _round_strike(price):
        return round(price * 2) / 2.0

    @staticmethod
    def _week_friday(date):
        return date + pd.Timedelta(days=max(0, 4 - date.dayofweek))

    def snap_contract(self, date, opt_type, target_exp, target_strike):
        """Snap to the nearest listed (expiration, strike) in the chain for this
        quote date; fall back to the raw targets when no chain data exists."""
        chains = self.chain_index.get((date, opt_type))
        if not chains:
            return target_exp, self._round_strike(target_strike)
        exp = min(chains.keys(), key=lambda e: abs((e - target_exp).days))
        strike = min(chains[exp], key=lambda k: abs(k - target_strike))
        return exp, strike

    def _bs_fallback(self, S, K, T, opt_type):
        sigma, r = self.fallback_iv, self.risk_free_rate
        if T <= 0:
            return max(0.0, S - K) if opt_type == 'C' else max(0.0, K - S)
        sqT = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqT)
        d2 = d1 - sigma * sqT
        N = lambda x: 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
        call = S * N(d1) - K * math.exp(-r * T) * N(d2)
        if opt_type == 'C':
            return round(max(0.0, call), 2)
        return round(max(0.0, call - S + K * math.exp(-r * T)), 2)

    def get_option_close(self, date, expiration, opt_type, strike, underlying_price):
        """EOD close for a contract: real quote if cached, else intrinsic at/after
        expiry, else Black-Scholes fallback (counted)."""
        self.option_lookups += 1
        key = (date, expiration, opt_type.upper()[0], float(strike))
        if key in self.options_cache:
            return self.options_cache[key]
        dte = (expiration - date).days
        if dte <= 0:
            return (max(0.0, underlying_price - strike) if opt_type.upper()[0] == 'C'
                    else max(0.0, strike - underlying_price))
        self.fallback_pricings += 1
        return self._bs_fallback(underlying_price, float(strike), dte / 365.0, opt_type.upper()[0])

    def buy_px(self, close):
        return round(close * (1.0 + self.option_half_spread_pct), 2)

    def sell_px(self, close):
        return round(max(0.0, close * (1.0 - self.option_half_spread_pct)), 2)

    # ---------------------------------------------------------------- ledger

    def _cash(self, amount, note):
        """Apply an external cash flow exactly once: to the trading balance, to
        the audit log, and to the open cycle's P&L accumulator."""
        self.trading_balance += amount
        self.flow_log.append((note, amount))
        if self.open_position is not None:
            self.open_position['cycle_flows'] += amount
        if self.trading_balance < 0:
            self.negative_balance_events += 1

    # ------------------------------------------------------------ simulation

    def run_simulation(self):
        self.load_and_prep_data()
        if not self.trading_days:
            raise RuntimeError("No trading days loaded. Cannot run simulation.")

        print(f"\nStarting Hybrid Simulation (Rally Hurdle: {int(self.rally_threshold_pct * 100)}%)...")

        days = pd.DatetimeIndex(self.trading_days)
        iso = days.isocalendar()
        week_map = defaultdict(list)
        for day, y, w in zip(days, iso['year'], iso['week']):
            week_map[(y, w)].append(day)
        first_days = {ds[0] for ds in week_map.values()}
        last_days = {ds[-1] for ds in week_map.values()}
        entry_days = {d for ds in week_map.values() for d in ds[:3]}

        for curr_date in days:
            # first trading day of the week (not literal Monday - holidays covered)
            if self.open_position is not None and curr_date in first_days:
                am_price = self.get_intraday_price(curr_date, 9, 35)
                if am_price is not None:
                    self.write_weekly_call(curr_date, am_price)
            elif self.open_position is None and curr_date in entry_days:
                am_price = self.get_intraday_price(curr_date, 9, 35)
                if am_price is not None:
                    self.execute_initial_entry(curr_date, am_price)

            # last trading day of the week (covers Friday holidays / early closes)
            if self.open_position is not None and curr_date in last_days:
                pm_price = self.get_intraday_price(curr_date, 15, 55)
                if pm_price is not None:
                    self.evaluate_week_close(curr_date, pm_price)

        self.print_summary()
        self.export_logs()

    # ----------------------------------------------------------------- legs

    def execute_initial_entry(self, date, price):
        call_exp, call_strike = self.snap_contract(date, 'C', self._week_friday(date), price)
        put_exp, put_strike = self.snap_contract(date, 'P', date + pd.Timedelta(days=self.put_target_dte), price)

        call_credit = self.sell_px(self.get_option_close(date, call_exp, 'C', call_strike, price))
        put_debit = self.buy_px(self.get_option_close(date, put_exp, 'P', put_strike, price))

        net_cost_per_share = price + put_debit - call_credit
        if net_cost_per_share <= 0:
            self.skipped_entries += 1
            return

        allocated_capital = self.trading_balance * self.allocation_pct
        shares = int(allocated_capital / net_cost_per_share) // 100 * 100
        if shares == 0:
            self.skipped_entries += 1
            return
        contracts = shares // 100

        total_cost = (shares * net_cost_per_share
                      + shares * self.stock_commission_per_share
                      + 2 * contracts * self.commission_per_contract)

        self.open_position = {
            'entry_date': date,
            'entry_price': price,
            'shares': shares,
            'contracts': contracts,
            'call_strike': call_strike,
            'call_exp': call_exp,
            'call_live': True,
            'put_strike': put_strike,
            'put_exp': put_exp,
            'cycle_flows': 0.0,
        }
        self._cash(-total_cost, f"{date.date()} entry: {shares} sh, put {put_strike} {put_exp.date()}, call {call_strike}")

    def write_weekly_call(self, date, price):
        pos = self.open_position
        if pos['call_live'] and pos['call_exp'] >= date:
            return  # existing call has not expired yet
        contracts = pos['contracts']

        call_exp, call_strike = self.snap_contract(date, 'C', self._week_friday(date), price)
        call_credit = self.sell_px(self.get_option_close(date, call_exp, 'C', call_strike, price))

        pos['call_strike'] = call_strike
        pos['call_exp'] = call_exp
        pos['call_live'] = True
        credit = call_credit * contracts * 100 - contracts * self.commission_per_contract
        self._cash(credit, f"{date.date()} sold weekly call {call_strike} exp {call_exp.date()}")

    def evaluate_week_close(self, date, price):
        pos = self.open_position
        contracts, shares = pos['contracts'], pos['shares']
        put_close = self.get_option_close(date, pos['put_exp'], 'P', pos['put_strike'], price)

        # --- assignment first: if called away, the cycle ends and the put is sold ---
        if pos['call_live'] and price >= pos['call_strike']:
            proceeds = (shares * pos['call_strike']
                        - shares * self.stock_commission_per_share
                        + contracts * 100 * self.sell_px(put_close)
                        - contracts * self.commission_per_contract)
            self._cash(proceeds, f"{date.date()} called away at {pos['call_strike']}")

            cycle_pnl = pos['cycle_flows']
            sweep_amt = cycle_pnl * self.profit_sweep_pct if cycle_pnl > 0 else 0.0
            self.trading_balance -= sweep_amt   # internal transfer, not an external flow
            self.cash_vault += sweep_amt

            self.log_trade(date, price, "CALLED AWAY (CYCLE COMPLETE)", cycle_pnl, sweep_amt,
                           "CYCLE CLOSED", position_value=0.0)
            self.open_position = None
            return

        # --- put maintenance (only when the position continues) ---
        roll_note = "PUT HELD"
        put_dte = (pos['put_exp'] - date).days

        if put_dte <= 7:
            # protection is expiring: roll out to a fresh target-DTE put
            new_exp, new_strike = self.snap_contract(date, 'P', date + pd.Timedelta(days=self.put_target_dte), price)
            new_close = self.get_option_close(date, new_exp, 'P', new_strike, price)
            roll_cost = ((self.buy_px(new_close) - self.sell_px(put_close)) * contracts * 100
                         + 2 * contracts * self.commission_per_contract)
            if roll_cost <= self.trading_balance:
                self._cash(-roll_cost, f"{date.date()} put expiry roll -> {new_strike} exp {new_exp.date()}")
                pos['put_strike'], pos['put_exp'] = new_strike, new_exp
                put_close = new_close
                roll_note = f"PUT EXPIRY ROLL to {new_strike} exp {new_exp.date()}"
            else:
                self.skipped_rolls += 1
                roll_note = "PUT EXPIRY ROLL SKIPPED (INSUFFICIENT CASH)"

        elif price >= pos['put_strike'] * (1 + self.rally_threshold_pct):
            # rally measured from the CURRENT put strike so the baseline resets
            # after each roll and identical-strike churn rolls are impossible
            new_exp, new_strike = self.snap_contract(date, 'P', pos['put_exp'], price)
            if new_strike > pos['put_strike']:
                new_close = self.get_option_close(date, new_exp, 'P', new_strike, price)
                roll_cost = ((self.buy_px(new_close) - self.sell_px(put_close)) * contracts * 100
                             + 2 * contracts * self.commission_per_contract)
                if roll_cost <= self.trading_balance:
                    gain_pct = (price - pos['put_strike']) / pos['put_strike'] * 100
                    self._cash(-roll_cost, f"{date.date()} rally roll put {pos['put_strike']} -> {new_strike}")
                    pos['put_strike'], pos['put_exp'] = new_strike, new_exp
                    put_close = new_close
                    roll_note = f"ROLLED PUT UP to {new_strike} (+{gain_pct:.1f}% above old strike at 15:55)"
                else:
                    self.skipped_rolls += 1
                    roll_note = "RALLY ROLL SKIPPED (INSUFFICIENT CASH)"

        # --- status + mark-to-market ---
        if not pos['call_live']:
            status_note = "NO CALL THIS WEEK (HOLD & WRITE NEXT WEEK)"
        elif price < pos['put_strike']:
            status_note = "BELOW PUT STRIKE (HOLD & WRITE NEXT WEEK)"
        else:
            status_note = "CALL EXPIRED OTM (HOLD & WRITE NEXT WEEK)"
        pos['call_live'] = False  # this week's call is expired either way

        position_value = shares * price + contracts * 100 * put_close
        unrealized_pnl = pos['cycle_flows'] + position_value
        self.log_trade(date, price, status_note, unrealized_pnl, 0.0, roll_note, position_value)

    # -------------------------------------------------------------- reporting

    def log_trade(self, date, price, status, pnl, sweep, note, position_value):
        pos = self.open_position
        net_worth = self.trading_balance + self.cash_vault + position_value
        self.equity_curve.append((date, net_worth, price))
        self.trade_logs.append({
            'Date': date.strftime('%Y-%m-%d'),
            'SOXL_5min_Trigger_Price': round(price, 2),
            'Status': status,
            'Shares': pos['shares'],
            'Call_Strike': pos['call_strike'],
            'Call_Exp': pos['call_exp'].strftime('%Y-%m-%d'),
            'Put_Strike': pos['put_strike'],
            'Put_Exp': pos['put_exp'].strftime('%Y-%m-%d'),
            'Cycle_PnL': round(pnl, 2),
            'Cash_Swept': round(sweep, 2),
            'Trading_Balance': round(self.trading_balance, 2),
            'Cash_Vault': round(self.cash_vault, 2),
            'Net_Worth_MTM': round(net_worth, 2),
            'Roll_Action': note,
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
        rolls_triggered = int(df['Roll_Action'].str.contains("ROLLED PUT UP").sum())
        expiry_rolls = int(df['Roll_Action'].str.contains("PUT EXPIRY ROLL to").sum())

        worths = [w for _, w, _ in self.equity_curve]
        dates = [d for d, _, _ in self.equity_curve]
        prices = [p for _, _, p in self.equity_curve]
        final_worth = worths[-1]
        total_roi = (final_worth - self.initial_capital) / self.initial_capital * 100

        span_days = max(1, (dates[-1] - pd.Timestamp(self.trading_days[0])).days)
        cagr = ((final_worth / self.initial_capital) ** (365.25 / span_days) - 1) * 100

        running_max, max_dd = -np.inf, 0.0
        for w in worths:
            running_max = max(running_max, w)
            max_dd = max(max_dd, (running_max - w) / running_max)

        rets = np.diff(worths) / np.array(worths[:-1])
        sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(52)) if len(rets) > 1 and np.std(rets) > 0 else float('nan')

        bench_roi = (prices[-1] / prices[0] - 1) * 100 if prices[0] else float('nan')
        fallback_rate = self.fallback_pricings / max(1, self.option_lookups)

        print("\n========================================================")
        print("       HYBRID 5-MIN ROLLING COLLAR BACKTEST RESULTS     ")
        print("========================================================")
        print(f"Intraday Source File:     {self.intraday_path}")
        print(f"Tested Rally Roll Hurdle: {int(self.rally_threshold_pct * 100)}% (above current put strike)")
        print(f"Total Weeks Evaluated:    {len(df)}")
        print(f"Full Cycles Completed:    {len(completed_cycles)} (Called Away at 15:55)")
        print(f"Mid-Cycle Puts Rolled:    {rolls_triggered} rally rolls, {expiry_rolls} expiry rolls")
        print(f"Cycle Win Rate:           {win_rate:.2f}% ({total_wins} Wins / {total_losses} Losses)")
        print("--------------------------------------------------------")
        print(f"Initial Capital:          ${self.initial_capital:,.2f}")
        print(f"Final Trading Capital:    ${self.trading_balance:,.2f} (Active Margin)")
        print(f"Final Cash Vault:         ${self.cash_vault:,.2f} (Untouchable Sweeps)")
        print(f"FINAL NET WORTH (MTM):    ${final_worth:,.2f}")
        print(f"TOTAL SYSTEM ROI:         {total_roi:.2f}%  (CAGR {cagr:.2f}% over {span_days} days)")
        print(f"Max Drawdown:             {max_dd * 100:.2f}%   Weekly Sharpe (ann.): {sharpe:.2f}")
        print(f"SOXL Buy&Hold Same Span:  {bench_roi:.2f}% (Friday close to Friday close)")
        print("--------------------------------------------------------")
        print(f"Option Pricing Quality:   {self.option_lookups:,} lookups, "
              f"{self.fallback_pricings:,} fallback-model pricings ({fallback_rate * 100:.1f}%)")
        if fallback_rate > 0.05 and self.options_cache:
            print("WARNING: >5% of option prices came from the Black-Scholes fallback, "
                  "not market data. Treat results with suspicion.")
        if not self.options_cache:
            print("WARNING: NO options data loaded - ALL option prices are synthetic. "
                  "Results reflect the pricing model, not the market.")
        if self.skipped_entries:
            print(f"NOTE: {self.skipped_entries} entry attempts skipped (insufficient capital / bad pricing).")
        if self.skipped_rolls:
            print(f"NOTE: {self.skipped_rolls} put rolls skipped for insufficient cash.")
        if self.negative_balance_events:
            print(f"WARNING: trading balance went negative {self.negative_balance_events} times (margin!).")
        print("========================================================\n")

    def export_logs(self):
        if not self.trade_logs:
            return
        output_file = f"SOXL_Hybrid_Collar_Log_{int(self.rally_threshold_pct * 100)}pct.csv"
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
