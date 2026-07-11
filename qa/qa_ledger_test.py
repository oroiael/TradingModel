"""QA regression test: ledger correctness of HybridCollarBacktester.

Scenario: SOXL pinned at exactly $100.00 for every 5-min bar, 4 full Mon-Fri
weeks, no options file (Black-Scholes fallback pricing throughout, which is
deterministic). Price == ATM strike every Friday => called away every week.

Assertions:
  1. Ledger identity: trading_balance + cash_vault ==
     initial_capital + sum(flow_log) to the penny, at end of run.
  2. Independent re-derivation: a hand-rolled simulation of the same 4 cycles
     (entry cost, assignment proceeds, commissions, spread, sweep) reproduces
     the engine's final trading balance and vault exactly.

The original engine failed (2) by +$750 per completed cycle (initial call
credit double-counted) - see QA_REPORT_hybrid_collar_backtester.md, 1.1/1.2.
"""
import os
import sys
import tempfile

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


def expected_final_state(engine_params):
    """Independently re-derive the 4 flat cycles from strategy rules alone,
    using a pricing-only engine instance (empty cache => deterministic BS)."""
    px = HybridCollarBacktester(**engine_params)  # never loads data; pricing helpers only
    bal, vault = px.initial_capital, 0.0
    S = 100.0
    for mon in pd.to_datetime(["2024-01-08", "2024-01-15", "2024-01-22", "2024-01-29"]):
        fri = mon + pd.Timedelta(days=4)
        put_exp = mon + pd.Timedelta(days=px.put_target_dte)

        call_credit = px.sell_px(px.get_option_close(mon, fri, 'C', S, S))
        put_debit = px.buy_px(px.get_option_close(mon, put_exp, 'P', S, S))
        net_cost = S + put_debit - call_credit
        shares = int(bal * px.allocation_pct / net_cost) // 100 * 100
        contracts = shares // 100
        entry_cost = (shares * net_cost + shares * px.stock_commission_per_share
                      + 2 * contracts * px.commission_per_contract)

        put_fri = px.sell_px(px.get_option_close(fri, put_exp, 'P', S, S))
        proceeds = (shares * S - shares * px.stock_commission_per_share
                    + contracts * 100 * put_fri - contracts * px.commission_per_contract)

        cycle_pnl = proceeds - entry_cost
        bal += cycle_pnl
        sweep = cycle_pnl * px.profit_sweep_pct if cycle_pnl > 0 else 0.0
        bal -= sweep
        vault += sweep
    return bal, vault


if __name__ == "__main__":
    os.chdir(WORKDIR)  # keep the engine's CSV log out of the repo
    params = dict(options_path=os.path.join(WORKDIR, "no_such_file.csv"),
                  intraday_path=intraday_path,
                  initial_capital=100000.0, rally_threshold_pct=0.10,
                  require_options_data=False)
    eng = HybridCollarBacktester(**params)
    eng.run_simulation()

    # 1. ledger identity
    flows = sum(a for _, a in eng.flow_log)
    lhs = eng.trading_balance + eng.cash_vault
    rhs = eng.initial_capital + flows
    print(f"Ledger identity: balance+vault={lhs:,.2f}  initial+flows={rhs:,.2f}  error={lhs - rhs:,.4f}")
    assert abs(lhs - rhs) < 0.01, "LEDGER IDENTITY BROKEN: cash created or destroyed outside flow_log"

    # 2. independent re-derivation of all 4 cycles
    exp_bal, exp_vault = expected_final_state(params)
    print(f"Trading balance: engine={eng.trading_balance:,.2f}  expected={exp_bal:,.2f}  "
          f"error={eng.trading_balance - exp_bal:,.4f}")
    print(f"Cash vault:      engine={eng.cash_vault:,.2f}  expected={exp_vault:,.2f}  "
          f"error={eng.cash_vault - exp_vault:,.4f}")
    assert abs(eng.trading_balance - exp_bal) < 0.01, "P&L DOUBLE-COUNTING REGRESSION (trading balance)"
    assert abs(eng.cash_vault - exp_vault) < 0.01, "P&L DOUBLE-COUNTING REGRESSION (vault sweep)"

    n_cycles = sum(1 for r in eng.trade_logs if "CALLED AWAY" in r['Status'])
    assert n_cycles == 4, f"expected 4 completed cycles, got {n_cycles}"
    print("\nPASS: ledger identity holds and engine matches independent re-derivation to the penny.")
