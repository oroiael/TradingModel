# QA/QC Report — `hybrid_collar_backtester.py`

**Date:** 2026-07-11
**Verdict:** The script runs and follows the broad shape of the intended strategy (Monday 09:35 entry / weekly call writing, Friday 15:55 evaluation, rally-triggered put rolls, 10% profit sweep to vault). **However, its P&L and cash accounting are materially wrong — results are inflated — and most option prices in a real run will come from a crude synthetic pricer, not your ThetaData file.** Backtest output in its current form should not be used to judge the strategy.

Two of the critical findings were verified empirically with reproducible synthetic-data tests (see `qa/` directory):

- **Flat-price test:** SOXL pinned at exactly $100 for 4 weeks. A collar cycle at a constant price should earn only call premium minus put decay. The engine reported **+5.80% ROI vs. a true flow-based +2.80%** — exactly $750/cycle of phantom profit (the initial call credit double-counted).
- **Rally-then-sideways test:** price jumps +15% after entry, then goes nowhere. The engine rolled the put from strike 115 **to the same strike 115 every Friday, seven weeks in a row**, paying ~$750–800/week in roll costs, because the rally baseline never resets.

---

## 1. Critical bugs (results are wrong)

### 1.1 Initial call credit is double-counted (lines 199, 207, 223, 267)
`net_cost_per_share = price + put_debit - call_credit` already nets the entry call credit into `total_invested`. But `realized_call_gains` is *also* seeded with that same credit (line 223), and cycle P&L is `total_rev - total_invested + realized_call_gains` (line 267). The entry credit is therefore counted twice. **Verified: exactly `call_credit × contracts × 100` ($750 in the test) of phantom profit per completed cycle.**

### 1.2 Weekly call credits are double-counted in cash on profitable exits (lines 235–236 vs. 273)
Each Monday write credits the premium to `trading_balance` immediately (line 236) *and* accumulates it in `realized_call_gains`. On a profitable called-away exit, the balance is credited `total_invested + reinvest_amt`, where `reinvest_amt` derives from a P&L that includes `realized_call_gains` — so every weekly credit collected during the cycle hits the cash ledger a second time. Total cash credited at close works out to `total_rev + realized_call_gains` instead of `total_rev`. Note the losing branch (line 276) credits only `total_rev`, i.e., the two branches are mutually inconsistent — the losing branch is the correct one.

### 1.3 Put roll costs are missing from cycle P&L (lines 253–254 vs. 267)
Roll cost is deducted from cash (line 254) but `total_invested` is never updated and the P&L formula never subtracts accumulated roll costs. Reported `Cycle_PnL`, the win/loss classification, and the vault sweep amount are all computed on P&L that ignores every dollar spent rolling the put.

### 1.4 Rally-roll baseline never resets (lines 246–251)
`run_up_pct` is always measured from the original `entry_price`. Once price is ≥ hurdle above entry, **every subsequent Friday triggers a roll**, including "rolls" to the identical strike, each paying a fresh 7-day extension. Verified: 7 consecutive 115→115 rolls, ~$5,600 of pure churn in 7 weeks. The trigger should compare against the *current put strike* (e.g., roll when `price ≥ put_strike × (1 + hurdle)`), and same-strike rolls should be skipped.

### 1.5 Put expiration is never enforced
`put_exp` only ever moves forward (+7d per roll). If a position is held past the put's expiration without rally rolls, `put_dte = max(1, (put_exp - date).days)` clamps negative DTE to 1 and the fallback pricer keeps valuing an expired option. The position stays "protected" — and is later *sold for value* at cycle close — via a phantom put.

### 1.6 Stale-call bugs around market holidays (lines 173, 183, 262)
- **Holiday Monday, open position:** the weekly call is only written when `day_name == 'Monday'`. On a holiday Monday no call is written, yet Friday still evaluates `price >= pos['call_strike']` against the *previous week's already-expired* call, potentially "assigning" shares on an option that no longer exists.
- **Holiday Friday (e.g., Good Friday):** the call is never evaluated at all; if it finished ITM, assignment silently vanishes and Monday overwrites the strike.

### 1.7 Synthetic expirations guarantee options-cache misses (lines 193–194, 229, 250)
- `put_exp = entry + 180 calendar days` is almost never a listed expiration, so the **largest cost leg of the strategy — the 6-month put — will essentially always be priced by the fallback model, not your ThetaData file.** The same is true for every rolled put (`old_exp + 7d`).
- `call_exp = date + 4 days` works for a Monday, but for the Tuesday/Wednesday fallback entries (line 173) it produces **Saturday/Sunday expirations** — guaranteed cache misses and a "Friday" evaluation against a contract that can't exist.
- Strikes are rounded to $0.50 (`round(price*2)/2`) without checking the chain; SOXL strike increments vary with price level.
- **There is no cache hit/miss instrumentation**, so you cannot tell what fraction of the backtest was real data vs. model guess.

### 1.8 Missing options file only warns, then simulates anyway (lines 105–107)
If `SOXL_Master_Cleaned.csv` is absent (or its columns fail to map), the code prints a warning and the entire backtest silently runs 100% on the synthetic pricer. This should be a hard failure.

**Combined effect of 1.1–1.3:** every profitable cycle inflates net worth by `realized_call_gains` (all call credits collected in the cycle) and reports P&L further overstated by roll costs. Over a multi-year weekly-cycle backtest this compounds into a large fictitious return. The flat-price test showed **+3.0% of capital in phantom gains in 4 weeks alone**.

---

## 2. Math / model accuracy issues

1. **Fallback pricer (lines 155–159)** is a Brenner–Subrahmanyam ATM approximation (`0.4·S·σ·√t`) with an ad-hoc Gaussian moneyness damper whose width is 100% of spot — a 20% OTM option is discounted by barely 2%. It uses a **hard-coded 80% IV in all regimes** (SOXL IV has ranged roughly 50–150%), has no rate/carry term, and is perfectly symmetric (no put skew — SOXL puts trade rich to calls). Whatever it touches is fiction; per 1.7 it touches the put on nearly every event.
2. **No transaction costs anywhere:** no per-contract commissions, no bid/ask spread, no slippage. EOD "close" prints on options are frequently stale or crossed; ATM SOXL weeklies routinely carry spreads of several percent of premium. Selling ~52 calls/year plus long-dated put churn makes this a first-order error, always in the strategy's favor.
3. **Assignment model:** called-away is decided by the 15:55 underlying vs. strike, then shares are sold at strike and the put sold at model value. No early-assignment handling (these are American options on a hard-to-borrow ETF). Acceptable as a stated simplification — but it is not stated.
4. **DTE inconsistency:** the weekly call expires `date + 4` days but is priced with `dte=5` (lines 193/196, 229/230).
5. **Idle cash earns nothing:** 75% of the trading balance never deployed and earning 0% — either intended (say so in output) or add a T-bill yield.
6. **No time-aware metrics:** "TOTAL SYSTEM ROI" has no time axis. There is no mark-to-market equity curve, so no CAGR, max drawdown, Sharpe/Sortino, or benchmark comparison (SOXL buy-and-hold, SOXX). A strategy can't be evaluated on final ROI and cycle win-rate alone — especially when open-position weeks log *unrealized* P&L (line 287) into the same `Cycle_PnL` column as realized cycles.

---

## 3. Robustness / code-quality issues

1. **Silent failure paths:** `load_and_prep_data` `return`s on several errors; `run_simulation` only checks `trading_days`, so an options-load failure is invisible (see 1.8).
2. **`iterrows()` cache build (line 134):** extremely slow for a multi-million-row ThetaData file. Use `dict(zip(...))` over vectorized columns (~100× faster).
3. **`get_intraday_price` has no tolerance:** it takes the closest bar to the target with no cap on distance and no RTH filter. On half-days/partial data a "15:55" evaluation silently executes at whatever bar exists (e.g., 13:00 early close) with no log.
4. **Unix-timestamp fallback (line 76)** assumes seconds; 13-digit millisecond stamps parse to ~year 56,000.
5. **No margin/negative-balance guard:** roll costs and entries can drive `trading_balance` negative with no warning.
6. **Silent no-trade states:** `shares == 0` or `net_cost_per_share <= 0` return without logging — the backtest can quietly stop trading for months.
7. **No validation of option quotes:** zero/NaN `close` values in the chain would be used as-is.
8. **Duplicate contract rows** silently keep the last occurrence (line 136).

---

## 4. Recommended fixes, in priority order

1. **Rebuild the ledger as pure cash-flow accounting** (fixes 1.1–1.3 by construction): every event applies a signed cash flow to one ledger; cycle P&L = sum of that cycle's flows; net worth = cash + mark-to-market of open positions. Never "add back" `total_invested`, and derive the vault sweep from realized cycle flow only. The `qa/qa_ledger_test.py` harness is a ready-made regression test: engine deltas must equal true deltas to the penny.
2. **Snap to real listed contracts:** from the options file, build a per-quote-date index of available expirations and strikes; select the expiration nearest the target DTE and the strike nearest target. Count cache hits vs. fallback pricings and **print the fallback rate in the summary; abort (or prominently warn) above ~5%.**
3. **Fix the roll trigger:** measure the rally from the current put strike (or last roll price), skip same-strike rolls, and roll to *listed* expirations rather than `+7 days`.
4. **Calendar correctness:** write the weekly call on the first trading day of the week (not literal Monday); evaluate assignment on the call's actual expiration date; enforce put expiration (close or replace); handle early-close days.
5. **Add costs:** ~$0.65/contract commissions and a spread haircut (sell at `close − k·spread/2`, buy at `close + k·spread/2`; if bid/ask exist in the ThetaData file, use them directly).
6. **Add real metrics:** weekly mark-to-market equity curve → CAGR, max drawdown, Sharpe, and side-by-side SOXL buy-and-hold benchmark over the identical window.
7. **Fail loudly:** raise on missing/unmappable options data; log skipped entries, tolerance violations, and negative balances.

---

## 5. Strategy-level observations and recommendations

1. **The collar as specified is nearly market-neutral — that's a design flaw, not a feature.** Both legs are struck ATM at the same strike: long stock + long ATM put + short ATM call is a *conversion* — payoff is locked at the strike regardless of where SOXL goes. At fair prices a conversion earns roughly the risk-free rate minus frictions. Any excess return this backtest shows is coming from the pricing model (per §1.7/§2.1), not from the market. **Open a corridor:** put ~10–20% below spot, call ~5–10% above spot (or delta-targeted, e.g., 25-delta call / 20-delta put), so the position actually participates in upside and the put costs far less.
2. **ATM weekly calls on a 3× levered ETF cap exactly the bursts that justify holding it.** SOXL's returns arrive in violent clusters; an ATM call forfeits all of them for one week's premium. Backtest OTM calls (25–35 delta) against the ATM version — on high-vol underlyings this usually dominates across regimes.
3. **The 180-DTE ATM put is extremely expensive insurance** (~20–25% of spot at 80 IV). Cheaper structures worth testing: 10–20% OTM puts, put debit spreads (finance by selling a far-OTM tail you're willing to own through), or shorter-dated puts pinned to listed monthlies/quarterlies. Also reconsider extending expiration +7d on every roll — pin rolls to the same listed expiry cycle and only roll the strike.
4. **Volatility-regime filter:** sell calls (and size positions) conditional on IV rank — premium selling on SOXL when IV is at the low end of its range is poor compensation; when IV rank is high the same trade is far better paid. The flat-80%-IV assumption hides this entirely.
5. **Consider collaring SOXX instead of SOXL.** SOXL's daily-reset leverage causes volatility drag in choppy markets; hedging costs scale with its ~3× IV. A collar on SOXX (or deep-ITM SOXX LEAPS for leverage) delivers similar exposure with much cheaper insurance. Worth a comparative backtest once the engine is fixed.
6. **Put the idle 75% in T-bills** and consider volatility-targeted sizing of the 25% sleeve (shrink allocation when realized vol spikes) instead of a fixed fraction.
7. **Run parameter sweeps only after fixes:** rally hurdle (10% vs 20%), call moneyness, put moneyness/DTE — on the current engine, sweep results would just rank pricing-model artifacts.

---

## 6. Reproduction

```
pip install pandas numpy
python qa/qa_ledger_test.py   # flat-price ledger audit  -> shows $750/cycle overstatement
python qa/qa_roll_test.py     # rally-then-sideways      -> shows same-strike put roll every Friday
```
Both scripts fabricate their own 5-minute CSVs and run the engine with no options file (exercising the fallback pricer, which is what a real run mostly uses anyway per §1.7).
