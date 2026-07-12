"""QA harness 1: the 'Base Risk' loss cap fabricates P&L on crash exits.

Scenario: standard entry on 2024-01-02 (DTE 31). On 2024-01-31 (2 DTE left)
SOXL prints an intraday low of 81, breaching the 90 short strike -> the
engine's CRASH (TRIPWIRE) path fires.

The engine's own crash model produces (per contract):
  income leg : 1.50 - 3*1.50                    = -3.00
  hedge legs : 3*BS(81,80) - BS(81,90) at 52% IV, 2 DTE  (deeply negative:
               with 2 days left the 3 long 80-puts are still OTM while the
               short 90-put is ~$9 ITM)
  total      : ~ -$1,022 per contract

But line 149-150 then clamps every losing trade to -'Base Risk' = -$410,
where Base Risk covers ONLY the income spread (width - credit). The hedge's
own loss trough simply vanishes from the books.

Expected (buggy) result: engine reports exactly -Base Risk * contracts,
~2.5x smaller than the loss its own model computed. It also shows the true
expiration payoff of the combined 6-leg structure at S=80 is -$1,410 per
contract, i.e. actual worst-case risk is ~3.4x 'Base Risk' -- so the 15%
position sizing is really risking ~50% of the account per trade.
"""
import pandas as pd

from fha_common import D0, entry_chain, put_row, run_engine

from final_hedged_audit import black_scholes_put

E = "2024-02-02"          # DTE 31 from D0
CRASH = "2024-01-31"      # 2 DTE remaining

rows = entry_chain(E)
# quotes for the income legs on the crash day (needed to get past the
# missing-quote gate; the tripwire branch itself never reads them)
rows += [
    put_row(CRASH, E, 90, 9.20, -0.95, iv=0.90, spot=82.0),
    put_row(CRASH, E, 85, 4.60, -0.85, iv=0.90, spot=82.0),
]

res = run_engine(rows, {D0: 99.0, CRASH: 81.0})

assert len(res) == 1, f"expected 1 closed trade, got {len(res)}"
trade = res.iloc[0]
assert trade["Reason"] == "CRASH (TRIPWIRE)", trade["Reason"]
contracts = int(trade["Contracts"])

# ---- independently recompute what the engine's OWN crash model produced ----
net_credit_realized = 1.50 - 0.30 - 6 * 0.05          # 0.90
base_risk = (5.0 - net_credit_realized) * 100          # $410 / contract

t = max(1, (pd.Timestamp(E) - pd.Timestamp(CRASH)).days) / 365.0
shocked_iv = 0.40 * 1.30
hedge_value = 3 * black_scholes_put(81.0, 80.0, t, 0.05, shocked_iv) \
    - black_scholes_put(81.0, 90.0, t, 0.05, shocked_iv)
income_pnl = 1.50 - 1.50 * 3.0                         # -3.00
model_pnl_per_contract = (income_pnl + (hedge_value - 0.30) - 0.30) * 100

reported = trade["Total Net PnL ($)"]
capped = -base_risk * contracts

print(f"contracts                        : {contracts}")
print(f"engine's own crash-model P&L     : {model_pnl_per_contract:>12,.2f} /contract")
print(f"'Base Risk' cap                  : {-base_risk:>12,.2f} /contract")
print(f"engine REPORTED                  : {reported:>12,.2f} total")
print(f"engine's model actually computed : {model_pnl_per_contract * contracts:>12,.2f} total")
print(f"loss silently erased by the cap  : "
      f"{model_pnl_per_contract * contracts - capped:>12,.2f}")

assert model_pnl_per_contract < -base_risk, "scenario should exceed the cap"
assert abs(reported - capped) < 0.01, (
    f"expected clamped {capped:,.2f}, engine reported {reported:,.2f}")

# ---- structural max risk vs 'Base Risk' (expiration payoff at S = 80) ----
s = 80.0
inc = 1.50 - (max(0, 90 - s) - max(0, 85 - s))                # -3.50
hdg = (3 * max(0, 80 - s) - max(0, 90 - s)) - 0.30            # -10.30
true_worst = (inc + hdg - 0.30) * 100                          # -1,410
print(f"\nexpiration payoff at S=80        : {true_worst:>12,.2f} /contract "
      f"({abs(true_worst) / base_risk:.1f}x the 'Base Risk' used for sizing)")

print("\nCONFIRMED: losses beyond the income-spread width are silently "
      "clamped, and position sizing uses a max-risk figure ~3.4x too small.")
