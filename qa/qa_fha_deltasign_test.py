"""QA harness 4: the hedge-leg selection depends on the SIGN convention of
the delta column, while the income-leg selection does not.

Income legs use `daily_puts['delta'].abs()` (convention-agnostic), but the
hedge sell leg minimizes `(delta - (-0.20)).abs()` on the SIGNED delta.
Options vendors ship put deltas either negative (OPRA/ORATS style) or as
positive magnitudes.

With positive put deltas, the value closest to -0.20 is simply the SMALLEST
delta in the chain -- i.e. the deepest-OTM (lowest) strike listed. The
hedge-buy legs must then be at strikes BELOW that, of which there are none,
so `prb_buy_cands` is always empty and NO TRADE CAN EVER BE ENTERED.

Scenario: two runs on byte-identical market data except for the sign of the
delta column. Same prices, same strikes, same everything.

Expected (buggy) result:
  negative deltas -> 1 trade, hedge sells the 20d 90-put, buys 3x 80-puts
  positive deltas -> ZERO trades in the entire backtest, silently
The engine neither validates nor normalizes the input convention, and a
positive-delta vendor file produces an empty (or, with unusual chains, a
nonsensically hedged) backtest with no warning.
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

print(f"negative deltas: {len(res_neg)} closed trade(s)")
if len(res_neg):
    t = res_neg.iloc[0]
    print(f"                 income {t['Inc. Short Strike']}/{t['Inc. Long Strike']}  "
          f"hedge sell {t['Hdg. Sell Strike']}, buy 3x {t['Hdg. Buy Strike']}")
print(f"positive deltas: {len(res_pos)} closed trade(s)")

assert len(res_neg) == 1, f"expected 1 trade with negative deltas, got {len(res_neg)}"
t = res_neg.iloc[0]
assert t["Inc. Short Strike"] == "$90.00" and t["Inc. Long Strike"] == "$85.00"
assert t["Hdg. Sell Strike"] == "$90.00" and t["Hdg. Buy Strike"] == "$80.00"

# with positive deltas the hedge sell collapses to the lowest strike in the
# chain (closest to -0.20), no buy strikes exist below it, and the engine
# silently enters nothing at all
assert len(res_pos) == 0, (
    f"expected 0 trades with positive deltas, got {len(res_pos)}")

print("\nCONFIRMED: identical market data, opposite delta sign convention "
      "-> 1 hedged trade vs an entirely empty backtest. The delta "
      "convention is never validated or normalized.")
