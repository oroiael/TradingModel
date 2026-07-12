"""QA regression 1: losses are reported in full (no 'Base Risk' clamp) and
position sizing uses the true structural risk of the 6-leg position.

Original bug: lines 149-150 clamped every losing trade to -(income width -
credit), erasing the 1x3 backspread's loss trough (measured: a crash the
engine's own model priced at -$1,020/contract was booked at -$410), and
sizing divided by that same understated figure (54 contracts instead of 15).

Scenario: standard entry on 2024-01-02 (DTE 31). On 2024-01-31 (2 DTE left)
SOXL prints an intraday low of 81, breaching the 90 short strike -> the
CRASH (TRIPWIRE) path fires with the 3 long 80-puts still OTM.

Fixed behavior verified here:
  * contracts are sized on the combined worst-case payoff (~$1,447.80/ct,
    the S=80 trough), not the $410 income-spread width -> 15 contracts;
  * the reported loss matches an independent recomputation of the engine's
    crash model and is NOT clamped at -$410/contract;
  * the income stop fills at max(3x credit, EOD spread cost) and the hedge
    is marked at the EOD price (quote if present, else shocked-IV model).
"""
import math

import pandas as pd

from fha_common import D0, entry_chain, put_row, run_engine

from final_hedged_audit import black_scholes_put, structure_max_loss

E = "2024-02-02"          # DTE 31 from D0
CRASH = "2024-01-31"      # 2 DTE remaining

rows = entry_chain(E)
rows += [
    put_row(CRASH, E, 90, 9.20, -0.95, iv=0.90, spot=82.0),
    put_row(CRASH, E, 85, 4.60, -0.85, iv=0.90, spot=82.0),
]

res = run_engine(rows, {D0: 99.0, CRASH: 81.0})

assert len(res) == 1, f"expected 1 closed trade, got {len(res)}"
trade = res.iloc[0]
assert trade["Reason"] == "CRASH (TRIPWIRE)", trade["Reason"]
contracts = int(trade["Contracts"])

# ---- independent recomputation of sizing and crash P&L ----
per_leg = 0.05 + 0.65 / 100.0
friction_rt = 2 * 6 * per_leg                                  # 0.678
max_risk = structure_max_loss(90, 85, 90, 80, 3, 1.50, 0.30, friction_rt) * 100
want_contracts = math.floor(150000 * 0.15 / max_risk)

# income: EOD spread cost 9.20-4.60=4.60 is worse than the 4.50 stop -> 4.60
income_pnl = 1.50 - max(1.50 * 3.0, 9.20 - 4.60)
# hedge: sell leg has a real quote (9.20); buy leg is model-marked at the
# EOD price with the vega-shocked entry IV
t = max(1, (pd.Timestamp(E) - pd.Timestamp(CRASH)).days) / 365.0
hb = black_scholes_put(82.0, 80.0, t, 0.05, 0.40 * 1.30)
hedge_pnl = (3 * hb - 9.20) - 0.30
want_pnl = (income_pnl + hedge_pnl - friction_rt) * 100 * contracts

old_base_risk = (5.0 - 0.90) * 100   # the pre-fix income-only figure

print(f"structural max risk          : {max_risk:>12,.2f} /contract "
      f"(vs old 'Base Risk' {old_base_risk:,.2f})")
print(f"contracts sized              : {contracts} (pre-fix engine: 54)")
print(f"engine reported P&L          : {trade['Total Net PnL ($)']:>12,.2f}")
print(f"independent recomputation    : {want_pnl:>12,.2f}")
print(f"per-contract loss            : {trade['Total Net PnL ($)'] / contracts:>12,.2f} "
      f"(old cap would have clamped at {-old_base_risk:,.2f})")

assert contracts == want_contracts, (contracts, want_contracts)
assert abs(max_risk - trade["Max Risk/Ct ($)"]) < 0.01
assert abs(trade["Total Net PnL ($)"] - want_pnl) < 1.0, (
    f"expected {want_pnl:,.2f}, got {trade['Total Net PnL ($)']:,.2f}")
# the loss must exceed the old income-only cap -> proves the clamp is gone
assert trade["Total Net PnL ($)"] / contracts < -old_base_risk

print("\nPASS: losses are reported uncapped and sizing uses the combined "
      "structure's true worst case.")
