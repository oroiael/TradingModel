# QA/QC Report — `final_hedged_audit.py`

**Date:** 2026-07-12
**Verdict:** The script implements the intended shape of the strategy — a 30–60 DTE, $5-wide, ~20Δ/5Δ SOXL put credit spread (income engine) plus a 1×3 put ratio backspread (PRB hedge), with an intraday strike-touch tripwire, 35% take-profit, 15%-of-balance sizing, and a 10% profit sweep to a cash vault. **However, it does not faithfully account for what that structure would actually make or lose.** Four defects were verified empirically with reproducible synthetic-data tests (see `qa/qa_fha_*.py`); the two worst ones each mis-state a single trade's P&L by **$27,000–$33,000 on a $150,000 account**, always in a direction that flatters the strategy or hides risk. Backtest output in its current form should not be used to judge the strategy or to size real capital.

---

## Resolution (2026-07-12) — fixes implemented

All items in section 4 are now implemented in `final_hedged_audit.py` on this branch, and the four `qa/qa_fha_*.py` harnesses have been flipped from bug demonstrations into **regression tests that assert the fixed behavior** (all passing):

1. **Loss cap removed** — losses are reported in full; a loud warning prints if a realized loss ever exceeds the structural max (possible pre-expiry via vol marks), but the number is never rewritten.
2. **Structural risk sizing** — `structure_max_loss()` evaluates the combined 6-leg expiration payoff at its strike kinks and sizing divides by that. On the test chain this is $1,447.80/contract vs the old $410 → 15 contracts instead of 54.
3. **Tripwire reordered above the quote gate** — it needs only the intraday low, so quote-gap days can no longer disable the stop-loss. Gap days now only skip the TP/EOD-stop *decision* (and are counted/reported).
4. **No silent $0 marks** — `put_value()` marks every leg as real quote → intrinsic (at/after expiry) → Black-Scholes with the day's IV or the entry IV; every mark source is counted and a data-coverage line prints in the summary.
5. **Delta convention normalized at load** (`delta = -abs(delta)` for puts) — both vendor conventions now produce identical backtests.
6. **Full friction** — slippage *and* $0.65/contract commissions on every executed leg, both sides; expired legs settle with no exit friction. The entry filter and structural risk both use round-trip friction.
7. **Daily mark-to-market equity curve** (written to `SOXL_Final_Hedged_Equity_Curve.csv`) — max drawdown is now daily-MTM, and the summary adds CAGR, annualized Sharpe, SOXL buy-and-hold benchmark, and open-at-end trades marked to market in final equity.
8. **Unified crash model** — income stop fills at `max(3× credit, EOD spread cost)`; hedge legs marked at the EOD price using real quotes when present, else vega-shocked model marks. Added the previously missing **EOD value stop** (`STOP-LOSS (EOD)`) so `stop_loss_mult` behaves as named.
9. **Hardened loaders** — required-column validation with explicit errors, duplicate-key detection, percent-vs-decimal IV auto-detection, robust IBKR datetime parsing, and a missing-lows warning.

Deliberately unchanged (flagged, not bugs): the hedge sell leg may still coincide with the income short strike (the structural risk math now prices that correctly; see 1.6 and strategy note 5.2), the sweep/vault mechanics, and the strategy parameters themselves. Sections 1–3 below document the original defects as found.

---

Verified findings as originally measured (the harnesses now assert the fixed behavior; run with `cd qa && python3 qa_fha_<name>_test.py`):

| Test | Finding | Measured effect |
|---|---|---|
| `qa_fha_losscap_test.py` | Losing trades are clamped to an understated "Base Risk" | Engine's own crash model computed **−$55,100**; engine reported **−$22,140**. True structural worst case is **3.4×** the risk figure used for sizing. |
| `qa_fha_tripwire_gap_test.py` | Stop-loss tripwire silently skipped on quote-gap days | Breach day with one missing quote row: booked **+$4,860 EXPIRATION win** instead of the **−$22,140** its own crash model dictates — a $27,000 swing, 0 crashes counted. |
| `qa_fha_zeroquote_slippage_test.py` | Missing hedge quotes valued at **$0.00** on exit; entry slippage never charged | 3 long puts liquidated for nothing (−$6,480 phantom hedge loss); only 6 of 12 round-trip legs pay slippage. |
| `qa_fha_deltasign_test.py` | Hedge selection depends on the delta sign convention of the input file | Identical data, positive-delta convention → **the entire backtest silently produces zero trades**. |

---

## 1. Critical bugs (results are wrong)

### 1.1 The "Base Risk" loss cap fabricates P&L (lines 149–150, 231)
`Base Risk = (income width − net credit) × 100` covers **only the income spread**. But the closed trade's P&L includes the hedge, and the 1×3 backspread has its own loss trough: between the hedge-buy and hedge-sell strikes near expiration, the short 20Δ put is deep ITM while the 3 long puts expire worthless — per contract that adds up to `(K_sell − K_buy) + hedge debit` of additional loss (with the test's 90/80 strikes: **$1,410 vs the claimed $410**, per contract). Lines 149–150 then clamp every losing trade to −Base Risk "as a safeguard". This is not a safeguard — it deletes real, modeled losses from the ledger. **Verified: a near-expiry crash the engine itself priced at −$1,020/contract was booked at −$410/contract; $32,960 of loss on one trade silently erased.**

Consequences compound: (a) reported ROI, win-rate on magnitude, and max drawdown are all fictions in any crash month; (b) **position sizing** (`alloc_pct / Base Risk`) believes it risks 15% of the balance per trade when the structure's true worst case is ~3.4× that — five concurrent trades can put well over 100% of the account at risk while the report shows a maximum possible loss of 15% each.

### 1.2 The intraday tripwire — the strategy's core risk control — is skipped whenever quotes are missing (lines 100–102 vs 109)
The missing-quote gate `continue`s before the tripwire check, even though the tripwire needs only the underlying's intraday low (from the IBKR file), not option quotes. Real EOD options files routinely have gap days (low volume, vendor holes, far-OTM strikes not printed). **Verified: a day whose low breached the short strike but whose income-leg quotes were absent produced no stop-out; the trade sailed to a full-profit "EXPIRATION" exit and the crash counter stayed at 0 — a $27,000 swing from one missing row.** Move the tripwire check above the quote gate.

### 1.3 Missing hedge quotes are valued at $0.00 on every normal exit (lines 133–134)
`options_cache.get(key, 0)` defaults absent hedge legs to zero. At expiration the income legs get an intrinsic-value fallback (lines 97–99) but the hedge legs never do — an ITM hedge at expiry with no EOD row is settled at $0. On take-profit exits a missing far-OTM quote liquidates 3 long puts for nothing. **Verified: −$1.20/contract phantom hedge loss where the true residual value was positive.** The error can cut either way (a missing *sell*-leg quote flatters the trade), so it adds noise *and* bias with zero instrumentation. Use intrinsic fallback at expiry, carry-last-known or Black-Scholes marks otherwise, and count cache misses.

### 1.4 Hedge selection breaks on positive-delta data files (line 216 vs 196–197)
Income legs use `delta.abs()` (convention-agnostic); the hedge sell leg minimizes distance to **signed** −0.20. Vendors ship put deltas both ways. With positive deltas the "closest to −0.20" is simply the smallest delta in the chain — the lowest listed strike — below which no buy strikes exist, so `prb_buy_cands` is always empty. **Verified: identical data, positive convention → the whole backtest silently runs zero trades.** Normalize once at load (`delta = -delta.abs()` for puts) and assert the convention.

### 1.5 Entry slippage never reaches the P&L (line 228 vs 143–146)
Entry slippage (6 legs × $0.05) is subtracted inside `net_credit_realized`, but that number is only used for the entry filter and sizing; the stored `Entry Net Credit` is the raw mid. At close, `total_legs_to_close = 6` charges only the exit side. A round trip of this structure is **12 executions**; every trade is overstated by $0.30/contract-set (≈$1,620 per 54-contract trade). Conversely, legs that *expire* shouldn't pay exit slippage at all — charge slippage per leg actually executed, on both sides.

### 1.6 The hedge sell leg is (almost always) the same contract as the income short put
Both target ~20Δ in the same expiration, so `prb_sell` resolves to the income short strike — confirmed in every test run (hedge sell = income short = $90). The real position is therefore **short 2× the 20Δ put**, long 1× 15Δ-ish put, long 3× far-OTM puts. Three consequences the script ignores:
- The "hedge" doubles short exposure exactly at the tripwire strike; the loss trough in 1.1 is structural, not incidental.
- Margin: the second short put is only part-covered by wide-strike longs; real buying power per contract will far exceed "Base Risk", so the computed contract counts (54–300) may be un-fundable. No margin model exists.
- If this netting is *intended* (an embedded broken-wing structure), it should be stated and risk computed on the combined payoff. If not, exclude the income short strike from `prb_sell_cands`.

### 1.7 Open trades at the end of the backtest vanish
Final ROI/net-worth come from the last *closed* trade's row. Up to 5 open trades — up to 75% of the balance at risk — are neither marked-to-market nor mentioned in the summary.

---

## 2. Math / model accuracy issues

1. **Crash exit is best-case on both engines simultaneously (lines 111–124).** Income exits at exactly 3× credit regardless of gap size (a limit-fill assumption in a flash crash), while the hedge is marked with the underlying at the **exact intraday low** with IV shocked 1.30× — i.e., you buy back the spread at your stop price *and* liquidate the long puts at the day's most favorable print. Both assumptions err in the strategy's favor; crash-day P&L is systematically optimistic. Use the EOD price (or a fill between touch and close) for both engines consistently.
2. **The "3× credit stop" only exists inside the strike-touch path.** A vol spike that marks the spread beyond 3× credit while price stays above the short strike never stops out — the trade can only exit at TP or expiration. Add an EOD value stop if 3× is the intended rule.
3. **Vega shock uses entry IV × fixed 1.30.** Crash-day IV is in the file (when present) — use it; a fixed 30% pop understates 2020/2022-style events on SOXL and overstates minor touches. The 0.80 IV fallback (lines 237–238) is hard-coded and never logged; percent-vs-decimal IV scale is never validated (an IV of "80" instead of "0.80" silently produces garbage Black-Scholes values).
4. **Drawdown is measured only at close events on realized cash (lines 163–166).** No daily mark-to-market equity curve exists, so intramonth drawdowns while 5 trades are open are invisible; "Max Drawdown 14.76%" style outputs materially understate risk. This also means no CAGR, Sharpe/Sortino, exposure, or benchmark (SOXL buy-and-hold / unhedged-spread A-B) can be computed — final ROI has no time axis.
5. **Same-day decide-and-fill on EOD closes.** TP is detected on the close and filled at that same close; entry credits use possibly stale/crossed EOD `close` prints. Acceptable EOD-backtest simplifications, but $0.05/leg slippage is thin for SOXL options (spreads on far-OTM legs are frequently $0.05–0.20 wide on their own) and there are **no commissions** (≈$0.65–1.30/contract × 12 legs matters at 54–300 contracts).
6. **Sweep quirk:** at ≥300 contracts, 100% of profit is swept (line 156) — a discontinuity in compounding; vault cash earns 0% forever and is never redeployed after drawdowns. Fine if intended; state it in the output.
7. **Fixed 5% risk-free rate** across a multi-year window; minor next to the above.

---

## 3. Robustness / code-quality issues

1. **KeyErrors on plausible files:** no `type`/`right` column, or no `delta` column → hard crash with no message (lines 29, 196). Missing `underlying_price` → `daily_prices = {}` → the entire run silently prints "No trades executed."
2. **Duplicate `(Date, Expiration, strike)` rows silently overwrite** each other in `options_cache`/`iv_cache` (`.to_dict()` keeps the last row) — dual-listed roots or vendor dupes go unnoticed.
3. **IBKR loader fragility (lines 49–53):** first column containing "date"/"time" wins; `str[:8]` + `%Y%m%d` assumes `"YYYYMMDD hh:mm:ss"` — an ISO-formatted export (`2024-01-02 09:30`) throws or mis-parses; `low` matched by substring could hit e.g. a `below_vwap` column. Validate and fail loudly.
4. **No data-coverage instrumentation:** nothing reports cache hit rates, quote-gap days, IV fallback usage, or dates where IBKR lows are missing (line 89 silently substitutes the EOD price, which weakens the tripwire on exactly the days it matters).
5. **One entry max per day with no de-duplication:** the same strikes/expiration can be stacked up to 5× across consecutive days — concentration the summary never shows.
6. `warnings.filterwarnings('ignore')` hides pandas issues; output CSV is written to the CWD unconditionally; `time` is imported but unused.

---

## 4. Recommended fixes, in order of impact on result validity

1. **Delete the loss cap** (lines 149–150). If you want a sanity guard, log a loud warning when a trade's loss exceeds the structural max and fail the run — never rewrite the number.
2. **Size on true structural risk:** compute the combined 6-leg expiration payoff over a price grid and use its minimum (plus a stress margin for pre-expiry marks) as max risk per contract. With the test chain that changes per-contract risk from $410 to ~$1,410 and cuts sizing ~3.4×.
3. **Reorder the tripwire above the missing-quote gate** — it needs only the daily low.
4. **Never value a leg at a silent $0:** intrinsic fallback at/after expiry for all legs; before expiry, carry-forward last mark or Black-Scholes with that day's ATM IV; count and report every fallback.
5. **Normalize the delta convention at load and assert it** (all put deltas ≤ 0 after normalization); also exclude the income short strike from hedge-sell candidates or explicitly model the netted position.
6. **Charge slippage and commissions per executed leg on both sides;** skip expired legs.
7. **Build a daily mark-to-market equity curve** (income + hedge legs marked daily) and report CAGR, max daily-MTM drawdown, Sharpe/Sortino, exposure, and include open trades at the end of the run. Add SOXL buy-and-hold and the **unhedged spread** as benchmarks — you cannot tell whether the PRB earns its keep without the A/B.
8. **Unify the crash model:** one consistent fill assumption (EOD or low) for both engines; crash-day IV from the file when present.
9. **Harden loaders:** schema validation with explicit errors, duplicate-key detection, IV-scale check, IBKR datetime parsing via `pd.to_datetime` on the full string, and a data-coverage report printed before the run.

---

## 5. Strategy-level observations and ideas (after the engine is fixed)

These are suggestions to *test*, not assertions — the current engine cannot answer them yet:

1. **Prove the hedge earns its keep.** The PRB costs ~0.30–0.50 against ~1.50 of credit (20–35% of gross income) and, as structured, deepens the loss trough in moderate (−10–20%) selloffs while only paying off in deep crashes. Run hedged vs unhedged vs "long 3 far-OTM puts only, no hedge-sell leg" over 2020–2022-inclusive data before concluding the 1×3 is the right shape.
2. **Don't sell the hedge put at the income short strike.** If the double-short at 20Δ isn't deliberate, finance the long puts with a further-OTM sell, or drop the sell leg and accept a small debit. Alternatively **calendarize the hedge**: buy the 3 long puts in a longer-dated expiry — far better gap protection per dollar of theta bleed, and it survives the income spread's expiration.
3. **Regime filters.** SOXL sells 20Δ puts best when vol is rich and trend isn't broken. Test (a) an IV-rank floor (only enter above, say, the 30th percentile so credit-to-width stays attractive — also make `min_credit` a % of width rather than a fixed $0.85), and (b) a trend filter (no new entries below the 200-day MA or after an N% drawdown from the 3-month high). SOXL bear legs are long and serially correlated; entry throttling is likely worth more than the hedge.
4. **Exit management.** 35% TP on 30–60 DTE structures leaves a long gamma-risk tail; the standard research result on short premium is that time-based exits dominate — test closing at 21 DTE regardless, and a 50% TP variant. Also add the EOD 3× value stop (see 2.2) so the stop rule matches its description.
5. **Diversify entries.** Enforce minimum spacing in expiration/strike between concurrent trades (currently 5 near-identical positions can stack in one week, making "5 trades" one big trade with one gap risk).
6. **Portfolio-level stress sizing.** Size each entry so a −30% SOXL day (it has happened) across *all* open positions, marked with a real vol shock, loses no more than a chosen fraction of the account — per-trade width-based sizing understates correlated risk in a single-underlying book.
7. **Idle cash and the vault.** Pay T-bill yield on unencumbered cash and test a rule that redeploys vault capital after an X% drawdown — as written, the vault is a one-way valve that drags compounded returns while still being counted in ROI.

---

*Reproduction: `cd qa && python3 qa_fha_losscap_test.py && python3 qa_fha_tripwire_gap_test.py && python3 qa_fha_zeroquote_slippage_test.py && python3 qa_fha_deltasign_test.py` (requires only `pandas`). Each script builds its own synthetic option/intraday CSVs in a temp directory, runs `FinalAuditSimulator` unmodified, and asserts the FIXED behavior (they originally asserted the bugs; see the Resolution section and git history).*
