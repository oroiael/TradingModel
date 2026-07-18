# SOXL Weekly-Income Strategy — Evaluation & Optimization Roadmap

*Written 2026-07-18, against commit history through the 120–180 DTE
optimal-put-scan run (+53.9%). All numbers below come from
`soxl_weekly_backtest_results.csv` (131 weeks, 2024-01-02 → 2026-07-02,
100% real-quote executions).*

---

## 1. Reinvestment mechanics — exact current behavior

The 75% rule is applied **at position entry events only** (initial entry and
re-entry after assignment/exit): the code buys shares up to 75% of total
investable capital (cash + share value) whenever fewer than 100 shares are
held. Realized gains minus the 10% sweep stay in the cash ledger and are
picked up by the *next* entry event — there were 19 such events in 131
weeks. There is **no weekly top-up**: between assignments, call premium and
other realized cash accumulates idle. Measured consequence: while holding
shares, cash averaged **52.6% of the trading balance** (p90: 69.7%) — partly
because the 2024–25 drawdown shrank the share sleeve, but structurally
because nothing redeploys cash until an assignment resets the position.
Cash also earns 0% in the model. Both are addressable (see §3.1).

## 2. Evaluation of the trade as it stands

| Metric | Value |
|---|---|
| Total return (incl. side account) | +53.9% ($230,778) |
| CAGR | 18.7% |
| Max drawdown (weekly closes) | −28.2% |
| Annualized weekly vol | 27.7% |
| Worst / best week | −12.4% / +15.1% |
| Weeks with call income | 78 / 131 (median $610, mean $2,304) |
| Realized P&L attribution | calls +$179.7k, puts −$58.6k, stock ≈ $0 |

What the numbers say:

* **The put does its job.** SOXL itself fell ~86% peak-to-trough inside the
  window; the strategy's max drawdown was −28.2%. The hedge cost −$58.6k
  realized — that is the insurance bill for cutting an −86% drawdown to −28%.
* **The call leg is the income engine and it works — except when it
  doesn't.** All net income is call premium. But 53 of 131 weeks sold
  nothing because no strike existed near the deep-underwater basis: the
  strategy produced **zero income during the exact stretch the user wants
  weekly income most**.
* **Stock realized ≈ $0 by design** (basis-anchored strikes); equity gains
  arrive as unrealized appreciation on the invested sleeve.
* **Idle cash is the silent drag** (§1). At ~50% cash for long stretches,
  even T-bill yield (~4–5% over this window) would have added roughly
  $10–15k, and redeployment more.

## 3. Optimization tests, ranked by expected value per unit of added risk

### 3.1 Deploy idle cash (no strategy risk — do first)
(a) credit T-bill interest on cash balances (needs a rate series or an
agreed constant); (b) add a weekly top-up: buy shares whenever share value
< 75% of balance, not only at re-entries. Round lots are not required to
hold shares — extra shares add covered-call capacity every time they cross
a 100 multiple. Test both separately; expected impact $10–30k with
unchanged strategy logic.

### 3.2 Fix the 53 zero-income weeks (moderate risk, likely largest lever)
Today: no strike near basis listed → skip. Key insight from the data: with
a near-ATM put on, **assignment below basis is not an unhedged loss** — the
put gains offset the stock loss below its strike. Tests:
* sell the nearest listed strike ≥ max(put strike, spot) during
  basis-unlisted weeks (income floor protected by the put);
* cap it: only when premium ≥ some minimum ($/contract) to avoid selling
  pennies;
* compare against the original spec's price-anchored strikes *analyzed
  jointly with the put* — the early −68% price-anchored run predates the
  put-aware framing and the real-quote data.
Even $300–600/week over 53 weeks is $15–30k plus compounding.

### 3.3 Put moneyness × coverage grid (the explicit risk dial)
The current hedge is full-size and ATM — maximum protection, maximum cost.
Grid-test with real quotes: strike at 100/95/90/85% of spot × coverage
100/75/50% of shares × the existing 120–180 tenor scan. Report each cell as
(CAGR, max DD, hedge cost) and pick from the frontier. This is the
cleanest "more return for slightly more risk" experiment; e.g. a 90%-strike
full-coverage put keeps tail protection while cutting premium materially.

### 3.4 Invest fraction 75% → 85/90/100%
With a put under the position, a higher equity fraction is defensible.
Same frontier treatment as 3.3; combines with 3.1(b).

### 3.5 Assignment-avoidance and threshold grids (cheap to run)
* Roll the weekly call (buy back Friday, resell next Monday higher) instead
  of taking assignment when the close is marginally above strike — avoids
  selling into momentum; measure vs current.
* Grid the roll-up trigger (10/15/20/25%) and protective-exit (10/15/20%) —
  note the 15% exit never fired in the final configuration; verify it isn't
  dead weight or, worse, path-lucky.
* Sweep policy: 10% vs 0% (max compounding) vs a fixed-dollar weekly
  income draw — the last matches the stated "income flowing weekly"
  objective better than a percentage of irregular realized gains.

### 3.6 Robustness before believing any of it
* Sub-period stability: re-run winners on 2024, 2025, 2026 separately —
  a parameter that only wins in the 2026 melt-up is curve-fit.
* Execution sensitivity: re-run at 0% / 20% / 50%-of-spread executions.
* Entry-day sensitivity: Monday vs Tuesday/Wednesday entries.

## 4. Data / indicators to request

1. **Intraday option quotes** (even a single 10:00 ET snapshot per day):
   current option data is end-of-day while trades execute Monday morning —
   the one remaining pricing bias in the backtest.
2. **A short-rate series** (3M T-bill or Fed funds, daily) for cash yield
   in 3.1 — or approve a documented constant.
3. **SOXL distribution history**: SOXL pays quarterly distributions; they
   are currently not modeled (understates long-stock returns slightly).
4. **2020–2023 extension of all three files** (5-min bars + raw option
   exports): the current window is essentially one crash-and-recovery arc;
   the 2022 bear market would test the put leg against a slow grind-down,
   which is its hardest regime.
5. Optional, for regime filters: daily VIX and SOX/SOXX index levels to
   gate call-selling aggressiveness and put tenor by volatility regime.

## 5. Suggested order of work

1. §3.1 cash deployment (pure win) → rerun baseline.
2. §3.2 zero-income-week fix (biggest single lever).
3. §3.3 + §3.4 joint grid with frontier report.
4. §3.5 threshold grids on the winner.
5. §3.6 robustness gauntlet; only keep parameters that survive it.
