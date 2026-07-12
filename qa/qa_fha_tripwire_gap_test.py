"""QA harness 2: the intraday crash tripwire is silently skipped on any day
the income legs have no EOD quote.

In run_audit(), the missing-quote gate (lines 100-102) runs BEFORE the
tripwire check (line 109) and `continue`s past it -- even though the
tripwire needs only the intraday low, not option quotes.

Scenario: standard entry on 2024-01-02. On 2024-01-16 SOXL prints an
intraday low of 89, breaching the 90 short strike -- but that day's option
rows for strikes 90/85 are missing from the file (a single unrelated quote
keeps the date alive as a trading day). Price recovers and the trade runs
to expiration OTM.

Expected (buggy) result: zero CRASH (TRIPWIRE) exits; the trade books a
full EXPIRATION win (+$4,860), when the engine's own crash model, had it
run that day, books the capped max loss (-$22,140). A single missing quote
row swings the result by ~$27,000 and disables the strategy's core risk
control.
"""
import pandas as pd

from fha_common import D0, entry_chain, put_row, run_engine

from final_hedged_audit import black_scholes_put

E = "2024-02-02"
GAP_CRASH = "2024-01-16"   # low breaches short strike; income quotes absent

rows = entry_chain(E)
# unrelated far-OTM quote: makes GAP_CRASH a trading day (DTE 10 -> no entry)
rows += [put_row(GAP_CRASH, "2024-01-26", 50, 0.05, -0.01, spot=88.0)]
# unrelated quote on expiration day so it is a trading day (DTE 45; the
# single row can't form a $5-wide spread, so no new entry either)
rows += [put_row(E, "2024-03-18", 50, 0.05, -0.50, spot=100.0)]

res = run_engine(rows, {D0: 99.0, GAP_CRASH: 89.0, E: 99.0})

assert len(res) == 1, f"expected 1 closed trade, got {len(res)}"
trade = res.iloc[0]
contracts = int(trade["Contracts"])
tripwires = (res["Reason"] == "CRASH (TRIPWIRE)").sum()

# what the tripwire SHOULD have booked on 2024-01-16 (engine's own model)
t = max(1, (pd.Timestamp(E) - pd.Timestamp(GAP_CRASH)).days) / 365.0
shocked_iv = 0.40 * 1.30
hedge_value = 3 * black_scholes_put(89.0, 80.0, t, 0.05, shocked_iv) \
    - black_scholes_put(89.0, 90.0, t, 0.05, shocked_iv)
crash_pnl = (1.50 - 4.50 + (hedge_value - 0.30) - 0.30) * 100
base_risk = (5.0 - 0.90) * 100
crash_pnl_capped = max(crash_pnl, -base_risk) * contracts

print(f"intraday low on {GAP_CRASH}      : 89.00  (short strike = 90.00 -> breach)")
print(f"tripwire exits recorded          : {tripwires}")
print(f"exit reason recorded             : {trade['Reason']}")
print(f"P&L engine booked                : {trade['Total Net PnL ($)']:>12,.2f}")
print(f"P&L its crash model would book   : {crash_pnl_capped:>12,.2f}")
print(f"swing from one missing quote row : "
      f"{trade['Total Net PnL ($)'] - crash_pnl_capped:>12,.2f}")

assert tripwires == 0, "bug no longer reproduces: tripwire fired"
assert trade["Reason"] == "EXPIRATION"
assert trade["Total Net PnL ($)"] > 0

print("\nCONFIRMED: a quote gap on the breach day silently disables the "
      "stop-loss tripwire; the trade sails through to a full win.")
