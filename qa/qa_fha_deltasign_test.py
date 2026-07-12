"""QA regression 4: the delta sign convention of the input file no longer
changes the backtest.

Original bug: income legs used `abs(delta)` but the hedge sell leg matched
signed -0.20, so a vendor file with positive put deltas made 'closest to
-0.20' resolve to the deepest-OTM strike in the chain -- below which no buy
strikes exist -- and the entire backtest silently produced zero trades.

Scenario: two runs on byte-identical market data except for the sign of the
delta column.

Fixed behavior verified here: deltas are normalized at load (puts negative),
so both runs enter the identical trade (income 90/85, hedge sell 90, buy
3x80) with identical P&L. Also checks the expiration exit: legs settle
(intrinsic/quote), so only the 6 entry legs pay slippage/commission.
"""
from fha_common import D0, entry_chain, put_row, run_engine

E = "2024-02-02"


def build(sign):
    rows = entry_chain(E, sign=sign)
    rows += [
        put_row(D0, E, 70, 0.50, sign * 0.01),
        put_row(D0, E, 60, 0.30, sign * 0.005),
    ]
    # unrelated quote so expiration day exists as a trading day
    rows += [put_row(E, "2024-03-18", 50, 0.05, sign * 0.50, spot=100.0)]
    return rows


res_neg = run_engine(build(-1.0), {D0: 99.0, E: 99.0})
res_pos = run_engine(build(+1.0), {D0: 99.0, E: 99.0})

for label, res in [("negative deltas", res_neg), ("positive deltas", res_pos)]:
    assert len(res) == 1, f"{label}: expected 1 closed trade, got {len(res)}"
    t = res.iloc[0]
    print(f"{label:>16}: income {t['Inc. Short Strike']}/{t['Inc. Long Strike']}  "
          f"hedge sell {t['Hdg. Sell Strike']}, buy 3x {t['Hdg. Buy Strike']}  "
          f"P&L {t['Total Net PnL ($)']:>10,.2f}  ({t['Reason']})")

neg, pos = res_neg.iloc[0], res_pos.iloc[0]
for col in ["Inc. Short Strike", "Inc. Long Strike", "Hdg. Sell Strike",
            "Hdg. Buy Strike", "Contracts", "Total Net PnL ($)",
            "Slippage Paid ($)", "Commissions ($)", "Reason"]:
    assert neg[col] == pos[col], (col, neg[col], pos[col])

assert neg["Hdg. Sell Strike"] == "$90.00" and neg["Hdg. Buy Strike"] == "$80.00"
assert neg["Reason"] == "EXPIRATION"

# expiration settles all legs: only the 6 entry legs pay friction
contracts = int(neg["Contracts"])
assert abs(neg["Slippage Paid ($)"] - 0.05 * 6 * 100 * contracts) < 0.01
assert abs(neg["Commissions ($)"] - 0.65 * 6 * contracts) < 0.01

print("\nPASS: both delta conventions produce the identical backtest; "
      "expired legs settle without exit friction.")
