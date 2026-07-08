import pandas as pd
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')


class SOXLVolatilityHarvester:
    def __init__(self, data_path):
        print(f"Loading Master Dataset from: {data_path}...")
        self.df = pd.read_csv(data_path, low_memory=False)

        date_col = 'date' if 'date' in self.df.columns else 'trade_date'
        self.df['Date'] = pd.to_datetime(self.df[date_col])
        self.df['Expiration'] = pd.to_datetime(self.df['expiration'])
        self.df['DTE'] = (self.df['Expiration'] - self.df['Date']).dt.days

        # Create a quick lookup for daily underlying prices
        if 'underlying_price' in self.df.columns:
            self.daily_prices = self.df.groupby('Date')['underlying_price'].first().to_dict()
        else:
            self.daily_prices = {}

        # Trades expiring after the last date in the dataset cannot be settled
        # and must be excluded, not scored at whatever the final price happens to be.
        self.last_data_date = self.df['Date'].max()

        # Real fills happen at bid/ask, not at the close print. Use quotes when
        # the dataset has them; otherwise fall back to close plus a slippage haircut.
        self.has_quotes = 'bid' in self.df.columns and 'ask' in self.df.columns

        print(f"Engine Ready: {len(self.df)} clean records loaded "
              f"(data through {self.last_data_date.date()}, "
              f"{'bid/ask quotes' if self.has_quotes else 'close prices + slippage'} for fills).")

    def run_production_backtest(self, dte_range=(20, 45), width_range=(2.5, 5.0),
                                min_credit=0.50, short_delta_target=0.20,
                                long_delta_target=0.05, delta_tolerance=0.05,
                                slippage_pct=0.05, commission_per_leg=0.65):
        print(f"\n--- 1. BUILDING TRADE SETUPS ---")

        type_col = 'type' if 'type' in self.df.columns else 'right' if 'right' in self.df.columns else None
        if type_col is None:
            raise ValueError("Dataset needs a 'type' or 'right' column to identify puts.")

        puts = self.df[self.df[type_col].str.upper().isin(['P', 'PUT'])].copy()
        puts = puts.dropna(subset=['delta', 'close', 'strike'])
        puts = puts[puts['DTE'].between(*dte_range)]

        trades = []
        skipped_unsettleable = 0

        for date, day_chain in puts.groupby('Date'):
            # Both legs of a vertical spread MUST share an expiration, so
            # candidate spreads are built one expiration at a time.
            best = None
            for expiration, chain in day_chain.groupby('Expiration'):
                short_err = (chain['delta'].abs() - short_delta_target).abs()
                shorts = chain[short_err <= delta_tolerance]
                if shorts.empty:
                    continue
                short_put = shorts.loc[(shorts['delta'].abs() - short_delta_target).abs().idxmin()]

                longs = chain[(chain['delta'].abs() - long_delta_target).abs() <= delta_tolerance]
                longs = longs[(short_put['strike'] - longs['strike']).between(*width_range)]
                if longs.empty:
                    continue
                long_put = longs.loc[(longs['delta'].abs() - long_delta_target).abs().idxmin()]

                # Sell the short leg at the bid, buy the long leg at the ask.
                if self.has_quotes and pd.notna(short_put['bid']) and pd.notna(long_put['ask']):
                    short_fill = short_put['bid']
                    long_fill = long_put['ask']
                else:
                    short_fill = short_put['close'] * (1 - slippage_pct)
                    long_fill = long_put['close'] * (1 + slippage_pct)

                net_credit = (short_fill - long_fill) * 100
                if net_credit < (min_credit * 100):
                    continue

                width = short_put['strike'] - long_put['strike']
                max_risk = (width * 100) - net_credit
                if max_risk <= 0:
                    continue

                delta_err = abs(abs(short_put['delta']) - short_delta_target)
                if best is None or delta_err < best['_delta_err']:
                    best = {
                        'Entry Date': date,
                        'Expiration': expiration,
                        'DTE': short_put['DTE'],
                        'Short Strike': short_put['strike'],
                        'Short Delta': abs(short_put['delta']),
                        'Long Strike': long_put['strike'],
                        'Net Credit': net_credit,
                        'Max Risk': max_risk,
                        'Fees': commission_per_leg * 2,
                        '_delta_err': delta_err,
                    }

            if best is None:
                continue
            if best['Expiration'] > self.last_data_date:
                skipped_unsettleable += 1
                continue
            del best['_delta_err']
            trades.append(best)

        if skipped_unsettleable:
            print(f"Excluded {skipped_unsettleable} setups expiring after the dataset ends "
                  f"({self.last_data_date.date()}) — they cannot be settled honestly.")

        if not trades:
            return None

        print(f"Built {len(trades)} spread setups.")
        return pd.DataFrame(trades)

    def simulate_outcomes(self, trades_df):
        print(f"\n--- 2. SIMULATING TRADE OUTCOMES (PnL) ---")
        if not self.daily_prices:
            print("Error: 'underlying_price' column missing. Cannot simulate outcomes.")
            return

        price_dates = sorted(self.daily_prices)
        results = []
        for _, trade in trades_df.iterrows():
            exp_date = trade['Expiration']

            # Settle at the last underlying close on or before expiration,
            # but only if it is close enough to expiration to be meaningful.
            available_dates = [d for d in price_dates if d <= exp_date]
            if not available_dates:
                continue
            exit_date = available_dates[-1]
            if (exp_date - exit_date).days > 5:
                continue

            settlement_price = self.daily_prices[exit_date]

            # Put Credit Spread Logic at Expiration:
            # If SOXL ends ABOVE short strike, we keep the full credit.
            if settlement_price >= trade['Short Strike']:
                payoff = trade['Net Credit']
                result = "WIN"
            # If SOXL ends BELOW long strike, we take the max loss.
            elif settlement_price <= trade['Long Strike']:
                payoff = -trade['Max Risk']
                result = "MAX LOSS"
            # If it ends between the strikes, partial loss/win
            else:
                intrinsic_value = (trade['Short Strike'] - settlement_price) * 100
                payoff = trade['Net Credit'] - intrinsic_value
                result = "PARTIAL"

            results.append({
                'Entry Date': trade['Entry Date'],
                'Expiration': exp_date,
                'Exit Date': exit_date,
                'Short Strike': trade['Short Strike'],
                'Long Strike': trade['Long Strike'],
                'Settlement Price': round(settlement_price, 2),
                'Result': result,
                'Max Risk': trade['Max Risk'],
                'PnL ($)': round(payoff - trade['Fees'], 2),
            })

        pnl_df = pd.DataFrame(results)
        if pnl_df.empty:
            print("No trades could be settled within the dataset.")
            return

        pnl_df = pnl_df.sort_values('Exit Date').reset_index(drop=True)

        wins = int((pnl_df['PnL ($)'] > 0).sum())
        losses = len(pnl_df) - wins
        win_rate = (wins / len(pnl_df)) * 100
        total_pnl = pnl_df['PnL ($)'].sum()

        # Equity curve and drawdown, marked at trade exit dates.
        equity = pnl_df['PnL ($)'].cumsum()
        max_drawdown = (equity - equity.cummax()).min()

        # Concurrent exposure: entering daily means many spreads are open at
        # once, so the raw PnL sum is meaningless without the margin it tied up.
        peak_open = 0
        peak_margin = 0.0
        for d in price_dates:
            open_mask = (pnl_df['Entry Date'] <= d) & (pnl_df['Exit Date'] >= d)
            open_count = int(open_mask.sum())
            open_risk = pnl_df.loc[open_mask, 'Max Risk'].sum()
            peak_open = max(peak_open, open_count)
            peak_margin = max(peak_margin, open_risk)

        print(f"Total Trades Evaluated: {len(pnl_df)}")
        print(f"Total Wins:   {wins}")
        print(f"Total Losses: {losses}")
        print(f"Historical Win Rate: {win_rate:.2f}%")
        print("-" * 40)
        print(f"TOTAL SYSTEM PnL (1 Contract, net of fees): ${total_pnl:,.2f}")
        print(f"Average PnL per Trade:                      ${pnl_df['PnL ($)'].mean():.2f}")
        print("-" * 40)
        print(f"Max Drawdown (closed-trade equity): ${max_drawdown:,.2f}")
        print(f"Peak Concurrent Open Spreads:       {peak_open}")
        print(f"Peak Margin at Risk:                ${peak_margin:,.2f}")
        if peak_margin > 0:
            print(f"Total PnL / Peak Margin:            {total_pnl / peak_margin * 100:.2f}%")
        print("-" * 40)

        return pnl_df


if __name__ == "__main__":
    env = SOXLVolatilityHarvester("SOXL_Master_Cleaned.csv")
    report = env.run_production_backtest()

    if report is not None:
        env.simulate_outcomes(report)
    else:
        print("No valid trade setups found.")
