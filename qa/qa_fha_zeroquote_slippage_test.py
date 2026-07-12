"""QA regression 3: hedge legs with missing exit quotes are model-marked
(never a silent $0.00), and slippage/commissions are charged on every
executed leg of the round trip.

Original bugs: `options_cache.get(..., 0)` liquidated 3 long puts for
nothing whenever a quote row was absent (measured: -$1.20/contract phantom
hedge loss), and only the 6 exit legs ever paid slippage -- the 6 entry
legs were subtracted for filtering/sizing but never reached the P&L.

Scenario: standard entry on 2024-01-02. On 2024-01-10 the income spread has
decayed (short 0.90, long 0.10 -> cost 0.80 <= 65% of the 1.50 credit) ->
TAKE-PROFIT. The strike-80 hedge-buy quote is absent that day.

Fixed behavior verified here:
  * the 3 long 80-puts are marked with Black-Scholes at the day's spot and
    the entry IV (23 DTE, 20% OTM -> small but nonzero), so Net Hedge PnL
    is better than the old zero-mark by 3 x BS value;
  * Slippage Paid = 12 legs x $0.05 and Commissions = 12 legs x $0.65
    (entry + exit; nothing expires on a TP exit).
"""
import pandas as pd

from fha_common import D0, entry_chain, put_row, run_engine

from final_hedged_audit import black_scholes_put

E = "2024-02-02"
TP = "2024-01-10"   # DTE 23 -> outside (30, 60), so no new entry that day

rows = entry_chain(E)
rows += [
    put_row(TP, E, 90, 0.90, -0.15, spot=100.0),
    put_row(TP, E, 85, 0.10, -0.02, spot=100.0),
    # NOTE: no (TP, E, 80) row -> hedge-buy legs must be model-marked
]

res = run_engine(rows, {D0: 99.0, TP: 99.0})

assert len(res) == 1, f"expected 1 closed trade, got {len(res)}"
trade = res.iloc[0]
contracts = int(trade["Contracts"])
assert trade["Reason"] == "TAKE-PROFIT", trade["Reason"]

t = max(1, (pd.Timestamp(E) - pd.Timestamp(TP)).days) / 365.0
hb = black_scholes_put(100.0, 80.0, t, 0.05, 0.40)   # entry IV, unshocked
want_hedge = round(((3 * hb - 0.90) - 0.30) * 100 * contracts, 2)
zero_mark_hedge = round(((3 * 0.0 - 0.90) - 0.30) * 100 * contracts, 2)
want_slippage = round(0.05 * 12 * 100 * contracts, 2)
want_commissions = round(0.65 * 12 * contracts, 2)

print(f"contracts                    : {contracts}")
print(f"BS mark of missing 80-put    : {hb:.4f} (was $0.0000)")
print(f"Net Hedge PnL reported       : {trade['Net Hedge PnL ($)']:>12,.2f}")
print(f"  (old zero-mark would give  : {zero_mark_hedge:>12,.2f})")
print(f"Slippage charged             : {trade['Slippage Paid ($)']:>12,.2f} (12 legs)")
print(f"Commissions charged          : {trade['Commissions ($)']:>12,.2f} (12 legs)")

assert abs(trade["Net Hedge PnL ($)"] - want_hedge) < 0.5, (
    f"expected {want_hedge}, got {trade['Net Hedge PnL ($)']}")
assert trade["Net Hedge PnL ($)"] > zero_mark_hedge
assert abs(trade["Slippage Paid ($)"] - want_slippage) < 0.01
assert abs(trade["Commissions ($)"] - want_commissions) < 0.01

print("\nPASS: missing hedge quotes are model-marked instead of $0.00, and "
      "the full round trip pays slippage and commissions.")
