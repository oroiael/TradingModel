"""QA harness 3: on TAKE-PROFIT / EXPIRATION exits, any hedge leg with a
missing quote is valued at $0.00 (options_cache.get(..., 0)), and entry
slippage is never charged.

Scenario: standard entry on 2024-01-02. On 2024-01-10 the income spread has
decayed (short 0.90, long 0.10 -> cost 0.80 <= 65% of the 1.50 credit), so
the engine takes profit. The strike-80 hedge-buy quote is absent that day,
so the engine marks all 3 long hedge puts at $0.00 -- a 23-DTE put 20%% OTM
on a 3x levered ETF is certainly not worth zero.

Expected (buggy) results:
  * Net Hedge PnL = (3*0 - 0.90) - 0.30 = -1.20/contract: the engine
    liquidates 3 long puts for nothing because a row is missing.
  * Slippage Paid = 6 legs * $0.05 = $0.30/contract, though a round trip of
    the 6-leg structure is 12 executions; the $0.30 of entry slippage that
    was subtracted inside `net_credit_realized` for filtering/sizing never
    reaches the P&L.
"""
from fha_common import D0, entry_chain, put_row, run_engine

E = "2024-02-02"
TP = "2024-01-10"   # DTE 23 -> outside (30, 60), so no new entry that day

rows = entry_chain(E)
rows += [
    put_row(TP, E, 90, 0.90, -0.15, spot=100.0),
    put_row(TP, E, 85, 0.10, -0.02, spot=100.0),
    # NOTE: no (TP, E, 80) row -> hedge-buy legs will be marked at $0.00
]

res = run_engine(rows, {D0: 99.0, TP: 99.0})

assert len(res) == 1, f"expected 1 closed trade, got {len(res)}"
trade = res.iloc[0]
contracts = int(trade["Contracts"])
assert trade["Reason"] == "TAKE-PROFIT", trade["Reason"]

hedge_marked_at_zero = round((3 * 0.0 - 0.90 - 0.30) * 100 * contracts, 2)
slippage_6_legs = round(0.05 * 6 * 100 * contracts, 2)
slippage_12_legs = round(0.05 * 12 * 100 * contracts, 2)

print(f"contracts                    : {contracts}")
print(f"Net Hedge PnL reported       : {trade['Net Hedge PnL ($)']:>12,.2f}")
print(f"  = 3 long 80-puts sold for $0.00 each (quote row missing) minus")
print(f"    the short 90-put at 0.90 and the 0.30 entry cost")
print(f"Slippage charged             : {trade['Slippage Paid ($)']:>12,.2f} (6 legs, exit only)")
print(f"Slippage for the round trip  : {slippage_12_legs:>12,.2f} (12 executions)")

assert abs(trade["Net Hedge PnL ($)"] - hedge_marked_at_zero) < 0.01, (
    f"expected {hedge_marked_at_zero}, got {trade['Net Hedge PnL ($)']}")
assert abs(trade["Slippage Paid ($)"] - slippage_6_legs) < 0.01

print("\nCONFIRMED: missing hedge quotes are silently valued at $0.00 on "
      "exit, and only half the round-trip slippage is ever charged.")
