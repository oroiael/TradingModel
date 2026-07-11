"""QA harness: run HybridCollarBacktester on synthetic flat-price data and
compare its internal ledger against an independently computed true cash ledger.

Scenario: SOXL pinned at exactly $100.00 for every 5-min bar, 4 full Mon-Fri
weeks. Price == ATM strike every Friday => called away every week.
With a perfectly flat price, true P&L per cycle = call premium collected
minus put time-decay. Any divergence between the engine's net worth and the
flow-based ledger is an accounting bug.

Expected (buggy) result: engine over-credits every completed cycle by
`initial_call_credit * contracts * 100` (see QA report finding 1.1/1.2).
"""
import sys, os, tempfile
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from hybrid_collar_backtester import HybridCollarBacktester

WORKDIR = tempfile.mkdtemp(prefix="collar_qa_")

# ---- build 4 weeks of flat 5-min bars (Mon 2024-01-08 .. Fri 2024-02-02) ----
rows = []
d = pd.Timestamp("2024-01-08")
while d <= pd.Timestamp("2024-02-02"):
    if d.dayofweek < 5:
        t = d + pd.Timedelta(hours=9, minutes=30)
        end = d + pd.Timedelta(hours=16)
        while t <= end:
            rows.append({"Datetime": t.strftime("%Y-%m-%d %H:%M:%S"), "close": 100.0})
            t += pd.Timedelta(minutes=5)
    d += pd.Timedelta(days=1)
intraday_path = os.path.join(WORKDIR, "flat_5min.csv")
pd.DataFrame(rows).to_csv(intraday_path, index=False)

# no options csv on purpose -> engine falls back to synthetic pricer for everything


class Instrumented(HybridCollarBacktester):
    """Shadow ledger: recompute the CORRECT cash delta for every event using the
    engine's own pricing function, then compare with what the engine did."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.true_cash = self.initial_capital  # flow-based ledger (trading + vault combined)
        self.events = []

    def execute_initial_entry(self, date, price):
        before = self.trading_balance + self.cash_vault
        super().execute_initial_entry(date, price)
        after = self.trading_balance + self.cash_vault
        if self.open_position is not None:
            true_delta = -self.open_position['total_invested']  # buy shares+put, sell call, netted
            self.true_cash += true_delta
            self.events.append(("ENTRY", date.date(), after - before, true_delta))

    def write_weekly_call(self, date, price):
        before = self.trading_balance + self.cash_vault
        super().write_weekly_call(date, price)
        after = self.trading_balance + self.cash_vault
        true_delta = after - before  # +credit; engine is correct here
        self.true_cash += true_delta
        self.events.append(("WRITE_CALL", date.date(), after - before, true_delta))

    def evaluate_friday_close(self, date, price):
        pos = self.open_position
        contracts, shares = pos['contracts'], pos['shares']
        put_dte = max(1, (pos['put_exp'] - date).days)
        current_put_val = self.get_option_price(date, pos['put_exp'], 'P', pos['put_strike'], price, put_dte)
        run_up = (price - pos['entry_price']) / pos['entry_price']
        true_delta = 0.0
        if run_up >= self.rally_threshold_pct:
            new_exp = pos['put_exp'] + pd.Timedelta(days=7)
            new_strike = round(price * 2) / 2.0
            new_debit = self.get_option_price(date, new_exp, 'P', new_strike, price, put_dte + 7)
            true_delta -= (new_debit - current_put_val) * contracts * 100
        if price >= pos['call_strike']:
            true_delta += shares * pos['call_strike'] + contracts * 100 * current_put_val

        before = self.trading_balance + self.cash_vault
        super().evaluate_friday_close(date, price)
        after = self.trading_balance + self.cash_vault
        self.true_cash += true_delta
        self.events.append(("FRIDAY", date.date(), after - before, true_delta))


if __name__ == "__main__":
    os.chdir(WORKDIR)  # keep the engine's CSV log out of the repo
    eng = Instrumented(options_path=os.path.join(WORKDIR, "no_such_file.csv"),
                       intraday_path=intraday_path,
                       initial_capital=100000.0, rally_threshold_pct=0.10)
    eng.run_simulation()

    print(f"{'event':<12}{'date':<14}{'engine cash delta':>20}{'true cash delta':>20}{'error':>14}")
    for ev, dt, got, want in eng.events:
        print(f"{ev:<12}{str(dt):<14}{got:>20,.2f}{want:>20,.2f}{got - want:>14,.2f}")

    engine_worth = eng.trading_balance + eng.cash_vault
    print(f"\nEngine final net worth : {engine_worth:>12,.2f}")
    print(f"True flow-based worth  : {eng.true_cash:>12,.2f}")
    print(f"OVERSTATEMENT          : {engine_worth - eng.true_cash:>12,.2f}  "
          f"({(engine_worth - eng.true_cash) / 100000 * 100:.2f}% of capital in 4 weeks)")
