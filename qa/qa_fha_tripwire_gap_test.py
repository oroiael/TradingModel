"""QA regression 2: the intraday crash tripwire fires even on days when the
income legs have no EOD quote.

Original bug: the missing-quote gate ran BEFORE the tripwire check and
`continue`d past it, so a single absent quote row on the breach day
disabled the stop-loss entirely (measured: +$4,860 'EXPIRATION' win booked
instead of the modeled crash loss -- a ~$27,000 swing).

Scenario: standard entry on 2024-01-02. On 2024-01-16 SOXL prints an
intraday low of 89, breaching the 90 short strike -- and that day's option
rows for strikes 90/85 are missing from the file (one unrelated quote keeps
the date alive as a trading day).

Fixed behavior verified here: the tripwire (which needs only the intraday
low) fires on the breach day; the income stop fills at 3x credit (no quotes
to slip against) and the hedge is model-marked at the EOD price with the
vega-shocked entry IV.
"""
import pandas as pd

from fha_common import D0, entry_chain, put_row, run_engine

from final_hedged_audit import black_scholes_put

E = "2024-02-02"
GAP_CRASH = "2024-01-16"   # low breaches short strike; income quotes absent

rows = entry_chain(E)
# unrelated far-OTM quote: makes GAP_CRASH a trading day (DTE 10 -> no entry)
rows += [put_row(GAP_CRASH, "2024-01-26", 50, 0.05, -0.01, spot=88.0)]
# unrelated quote on what would have been expiration day
rows += [put_row(E, "2024-03-18", 50, 0.05, -0.50, spot=100.0)]

res = run_engine(rows, {D0: 99.0, GAP_CRASH: 89.0, E: 99.0})

assert len(res) == 1, f"expected 1 closed trade, got {len(res)}"
trade = res.iloc[0]
contracts = int(trade["Contracts"])

# independent recomputation of the crash exit on the gap day
friction_rt = 2 * 6 * (0.05 + 0.65 / 100.0)
income_pnl = 1.50 - 1.50 * 3.0                      # no quotes -> 3x stop fill
t = max(1, (pd.Timestamp(E) - pd.Timestamp(GAP_CRASH)).days) / 365.0
shocked = 0.40 * 1.30
hedge_val = 3 * black_scholes_put(88.0, 80.0, t, 0.05, shocked) \
    - black_scholes_put(88.0, 90.0, t, 0.05, shocked)
want_pnl = (income_pnl + (hedge_val - 0.30) - friction_rt) * 100 * contracts

print(f"intraday low on {GAP_CRASH}      : 89.00 (short strike 90.00 -> breach; quotes absent)")
print(f"exit reason recorded             : {trade['Reason']}")
print(f"exit date recorded               : {trade['Exit Date']}")
print(f"engine reported P&L              : {trade['Total Net PnL ($)']:>12,.2f}")
print(f"independent recomputation        : {want_pnl:>12,.2f}")

assert trade["Reason"] == "CRASH (TRIPWIRE)", trade["Reason"]
assert trade["Exit Date"] == GAP_CRASH, trade["Exit Date"]
assert (res["Reason"] == "CRASH (TRIPWIRE)").sum() == 1
assert abs(trade["Total Net PnL ($)"] - want_pnl) < 1.0, (
    f"expected {want_pnl:,.2f}, got {trade['Total Net PnL ($)']:,.2f}")

print("\nPASS: a quote gap on the breach day no longer disables the "
      "stop-loss tripwire.")
