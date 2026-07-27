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

## 5. Results of §3.1 + §3.2 (run 2026-07-18)

Implemented: 4.5% interest on idle cash (constant, documented), weekly
top-up to the 75% target with matching put-contract additions, and the
drawdown OTM call fallback (strike ≥ spot+10%, min $0.05/sh).

Outcome vs the +53.9% baseline: **+125.9% total ($338,893), CAGR 38.2%,
max DD −24.5% (better than baseline's −28.2%), ann. vol 34.3% (up from
27.7%)**. Calls sold all 131 weeks ($445.9k premium); interest +$9.1k.
The dominant driver was the weekly top-up: dollar-cost averaging the
2024–25 crash pulled average basis down to the market, which organically
re-enabled call selling (opt #2 fired only once). Attribution: calls
+$445.9k, puts −$133.0k, stock −$70.7k (moving-average-basis accounting
offset inside call premium), interest +$9.1k.

**Caveats before trusting it:** (1) top-up buying is path-favorable in a
crash-then-recovery window — in a 2022-style grind-down it buys all the
way down; the hedge scales along (only 3 weeks deeper than −20% DD here)
but the 2020–2023 data extension (§4.4) is the real test. (2) One week
(2025-05-19) had no 120–180 DTE listing at whole-dollar strikes: the put
lapsed for one week until the next Monday's repurchase — a listing-gap
edge case worth a fallback rule later.

## 6. Suggested order of remaining work

1. ~~§3.1 cash deployment~~ DONE (see §5).
2. ~~§3.2 zero-income-week fix~~ DONE (see §5).
3. §3.3 + §3.4 joint grid with frontier report.
4. §3.5 threshold grids on the winner.
5. §3.6 robustness gauntlet; only keep parameters that survive it.

## 7. Put policy decision (2026-07-18, post put-policy lab)

Adopted: **buy the put and HOLD TO EXPIRATION** (roll-up rule retired;
conditional −15% exit kept). Baseline is now +180.5% / −24.5% max DD.
Rolling in either direction, profit-harvesting, and liquidate-everything
exits all tested worse on real quotes (see qa/put_policy_report.txt).

Put-spread strategy implemented (`PUT_SPREAD_SHORT_FRAC`): sell a put at
~65–75% of the long strike, same expiration, real quotes both legs, held
to expiration with net-intrinsic settlement. Results frontier:

| policy     | return  | max DD | hedge net spend |
|------------|---------|--------|-----------------|
| plain put (baseline) | +180.5% | −24.5% | $248k |
| spread_65  | +235.5% | −36.8% | $187k |
| spread_75  | +239.7% | −47.6% | $147k |
| no hedge   | +230.4% | −67.4% | $0 |

spread_75 dominates no-hedge outright (more return, less drawdown).
spread_65 ≈ no-hedge returns at roughly half its drawdown. The choice
between baseline and spread_65 is a genuine risk-appetite decision:
+55 points of return for ~12 points deeper max drawdown. Default remains
the plain put; set PUT_SPREAD_SHORT_FRAC = 0.65 to switch.

## 8. Spread_65 scenario tests (2026-07-18): invest 85%, exit trigger 20%

spread_65 adopted as the working default (+235.5%, −36.8% max DD).
Scenarios on top of it, each change isolated then combined:

| scenario              | return  | CAGR  | max DD | vol   | worst wk |
|-----------------------|---------|-------|--------|-------|----------|
| spread_65 (reference) | +235.5% | 61.7% | −36.8% | 44.9% | −17.0%   |
| + invest 85%          | +262.3% | 66.7% | −42.2% | 50.5% | −18.2%   |
| + exit trigger 20%    | +235.5% | 61.7% | −36.8% | 44.9% | −17.0%   |
| + both                | +262.3% | 66.7% | −42.2% | 50.5% | −18.2%   |

Findings: (1) **invest 85% adds ~27 points of return for ~5.4 points more
max DD** — a clean, roughly proportional risk/return trade. Side effect:
with only 15% cash, 4–5 weeks couldn't immediately afford the hedge
top-up after large put purchases and ran a few contracts under-hedged
until cash replenished (warned per week in the run log). (2) **Raising
the protective-exit trigger from 15% to 20% is a historical no-op**: the
only exit in the window fired on a −20.4% week, beyond both thresholds.
It only matters in future paths where a −15%..−20% move coincides with
the put covering the loss; it neither helped nor hurt here. Neither
scenario changes the repo default pending user decision.

## 9. Spread_65 scenario tests round 2 (2026-07-18): invest 90%, sweep 5%

| scenario               | return  | CAGR  | max DD | vol   | worst wk | side acct | under-hedged wks |
|------------------------|---------|-------|--------|-------|----------|-----------|------------------|
| spread_65 (ref 75%/10%)| +235.5% | 61.7% | −36.8% | 44.9% | −17.0%   | $62,062   | 1  |
| + invest 90%           | +307.7% | 74.7% | −43.1% | 54.0% | −18.8%   | $81,379   | 15 |
| + sweep 5%             | +256.4% | 65.6% | −38.3% | 47.0% | −17.7%   | $33,770   | 1  |
| + both                 | +334.1% | 79.1% | −45.6% | 56.5% | −19.9%   | $44,462   | 13 |

Findings: (1) sweep 5% is a clean compounding win (+21 points for ~1.5
points more DD) — the trade-off is the smaller swept-cash cushion ($34k
vs $62k). (2) invest 90% adds big return (+72 points) BUT the strategy
outruns its own hedge maintenance: with only 10% cash, **13–15 weeks run
under-hedged** because the Monday share top-up consumes the cash before
the put top-up executes. That is a structural flaw at 90%, not just a
risk preference — fixable by reordering the weekly sequence (hedge
top-up BEFORE share top-up), which should be implemented and re-tested
before 90% is considered for adoption. Defaults unchanged (75%/10%).

## 10. Hedge-priority fix + invest-fraction ladder (2026-07-18)

Fix implemented in two parts: (1) weekly share buys are sized so cash can
still hedge every new round lot at real quotes (INVEST_FRACTION becomes a
cap); (2) at put replacement events, shares are sold to fund full
coverage when cash can't (flagged SOLD_TO_FUND_HEDGE per row -- a
documented deviation from spec 2.b.2). Under-hedged weeks: 16 -> 1 (the
un-fixable 2025-05-19 listing-gap week).

Whole-hedge ladder, spread_65 + sweep 5%:

| invest cap | return  | CAGR  | max DD | forced hedge-fund sales |
|-----------|---------|-------|--------|--------------------------|
| 75%       | +256.4% | 65.6% | −38.3% | 0 sh    |
| 85%       | +283.5% | 70.5% | −41.8% | 76 sh   |
| 88%       | +281.4% | 70.1% | −44.0% | 345 sh  |
| 90%       | +286.6% | 71.0% | −44.6% | 778 sh  |
| **95%**   | **+200.0%** | 54.7% | **−56.1%** | 1,617 sh |

Finding: returns plateau at 85-90% and COLLAPSE at 95%, which is
strictly dominated (less return, more risk than every other rung). At
95% the cash buffer that powers the strategy's own edge -- weekly
dip-buying top-ups and interest -- is starved, and the hedge must be
maintained by repeatedly selling shares at lows. The earlier +334% at
"90%" (section 9) was inflated by its broken hedge; the honest
whole-hedge 90% number is +286.6%. Practical maximum: ~90%.
Default currently 95% per user direction; recommendation is 90%.

## 11. ROBUSTNESS TEST on 2022-2023 data (2026-07-27) — CHANGES CONCLUSIONS

New files on main (SOXL_Options_2022/2023.csv, SOXL_5min_6Years.csv)
supplied the missing bear-market regime. Data verified: every Monday has
a <=7 DTE weekly, every day has 120+ DTE listings, whole strikes near
spot on all 501 days, no crossed quotes; the 6-year 5-min file is
byte-identical to the 3-year file on all 754 shared days. 2022 pre-split
adjusted strikes (37.67 = 113/3) are correctly excluded by the
whole-number rule. Loader and STOCK_CSV extended: window is now
2022-01-03 -> 2026-07-02 (235 weeks, 1,516,524 option rows).

### Full-window results (235 weeks) vs the old 131-week window

| config          | 2024-26 return | FULL return | FULL CAGR | FULL maxDD |
|-----------------|----------------|-------------|-----------|------------|
| plain put 75/10 | +180.5%        | +122.1%     | 19.3%     | −43.0%     |
| spread65 75/10  | +235.5%        | +165.2%     | 24.1%     | −56.9%     |
| spread65 85/5   | +283.5%        | +194.3%     | 27.0%     | −61.9%     |
| spread65 90/5   | +286.6%        | +190.1%     | 26.6%     | −63.2%     |
| spread65 95/5   | +200.0%        | +118.1%     | 18.8%     | −64.0%     |
| no hedge        | +230.4%        | +121.0%     | 19.2%     | −75.7%     |

### Year-by-year (return / max DD); SOXL: 2022 −86.6%, 2023 +235.8%,
### 2024 −2.5%, 2025 +51.7%, 2026H1 +235.1%

| config          | 2022          | 2023         | 2024        | 2025        |
|-----------------|---------------|--------------|-------------|-------------|
| plain put 75/10 | −43.0%/−43.0% | +42.5%/−24.2%| +25.8%/−19.5%| +37.7%/−22.6%|
| spread65 75/10  | −52.5%/−56.9% | +65.6%/−25.3%| +27.4%/−25.4%| +61.1%/−34.9%|
| spread65 85/5   | −58.7%/−61.9% | +78.6%/−29.3%| +32.1%/−30.6%| +66.4%/−40.2%|
| no hedge        | −70.3%/−75.7% | +140.4%/−33.8%| +7.7%/−43.1%| +63.1%/−55.6%|

### Conclusions that CHANGED

1. **The spread's weakness is now measured, not hypothesized.** In 2022's
   slow grind SOXL fell through the 65% short strike and stayed there, so
   the spread stopped protecting: −52.5% vs the plain put's −43.0%.
   Every 2024-26 return figure was regime-flattered; all fall ~40%.
2. **Risk-adjusted, the four configs are nearly tied** (CAGR/|maxDD|:
   plain 0.45, spread65 0.42, spread65-85/5 0.44, no-hedge 0.25). The
   spread buys return with drawdown almost 1:1. Only the *unhedged* case
   is clearly inferior — the hedge itself is validated.
3. **95% invested is confirmed dominated in both windows** (+118.1%,
   −64.0% — worse than 75% on both axes). Practical max stays ~85-90%.
4. **Choice is now explicitly regime-dependent**: spread65 wins if
   crashes are V-shaped (2025-style), plain put wins if they grind
   (2022-style). A regime-switched hedge (full put when trend/vol
   signals stress, spread otherwise) is the natural next test — it needs
   the VIX/SOX series in section 4.5.

## 12. SOX regime filter (2026-07-27) — TESTED AND REJECTED

SOX_Daily_6Years.csv confirmed present on main and validated: 1,507 days
(2020-07-24 → 2026-07-24), zero missing days across the backtest window,
no gaps/dupes/bad prices. Independent cross-check: SOXL's daily-return
beta to SOX is **3.01** (design = 3.0) with 0.953 correlation, which
validates the SOXL and SOX files against each other. SOXX (1x) and SOXS
(inverse 3x) also present; SOXS shows the expected −0.91 beta to SOXL
and catastrophic decay (only usable as a short-horizon tactical hedge,
not a carry position).

Regime-switched hedge implemented (`REGIME_RULE`, causal — signals
shifted one day so a decision sees only the prior close): SOX stress →
full plain put, calm → spread65.

| config (invest 75/10) | return  | CAGR  | maxDD  | CAGR/|DD| | 2022   |
|-----------------------|---------|-------|--------|-----------|--------|
| plain put (always)    | +122.1% | 19.3% | −43.0% | 0.45      | −43.0% |
| spread65 (always)     | +165.2% | 24.1% | −56.9% | 0.42      | −52.5% |
| regime ma200          | +101.0% | 16.7% | −54.5% | 0.31      | −56.1% |
| regime rv45           | +134.1% | 20.7% | −54.5% | 0.38      | −56.1% |
| regime either         | +101.0% | 16.7% | −54.5% | 0.31      | −56.1% |

Same ordering at invest 85/5. **Every regime variant is worse than both
static policies on return AND risk-adjusted return.**

Why it fails (visible in the signal table at the 10 purchase dates): the
single most damaging purchase, 2022-01-03, was made with SOX **+17%
above its 200-day average** at 35% realized vol — no stress signal —
and SOX then fell 37.7% over the following six months. The filter
bought the cheap spread exactly when full protection was needed, then
switched to expensive full puts in mid-2022 and late-2022 *after* the
damage, carrying that cost through the recovery. Trend and vol signals
are backward-looking; the hedge decision is forward-looking.

Caveat: only 10 hedge decisions exist in 4.5 years, so this is a thin
statistical test — but the failure mechanism is structural, not noise.
Conclusion: keep the hedge choice STATIC. Use the plain put when
drawdown control matters more, spread65 when return matters more.

## 13. Put-role tests (a),(b),(d) and NO-UNDERLYING variants (2026-07-27)

All on the full 235-week window, plain put / invest 85% / sweep 5%.

### (a) protective-exit rule, (b) partial coverage, (d) deep-ITM harvest

| test                      | return  | CAGR  | maxDD  | CAGR/|DD| | put spend |
|---------------------------|---------|-------|--------|-----------|-----------|
| reference (exit on, 100%) | +161.5% | 23.7% | −45.5% | **0.52**  | $315,870  |
| (a) exit OFF              | +161.9% | 23.7% | −45.5% | **0.52**  | $317,175  |
| (a) exit UNCONDITIONAL    | +15.4%  |  3.2% | −51.9% | 0.06      | $862,608  |
| (b) coverage 75%          | +146.0% | 22.0% | −55.1% | 0.40      | $219,966  |
| (b) coverage 50%          | +133.5% | 20.6% | −61.4% | 0.34      | $142,933  |
| (b) coverage 25%          | +159.0% | 23.4% | −67.6% | 0.35      | $78,806   |
| (d) deep-ITM harvest 20%  | +115.2% | 18.5% | −52.9% | 0.35      | $287,699  |
| (d) deep-ITM harvest 30%  | +115.2% | 18.5% | −52.9% | 0.35      | $287,699  |

- **(a) The spec's −15% conditional exit is dead weight**: it fires once in
  4.5 years and turning it off changes nothing (+161.9% vs +161.5%, same
  −45.5% DD). Making it unconditional is catastrophic (40 exits, +15.4%)
  — confirms the earlier whipsaw finding on more data.
- **(b) Partial coverage is strictly worse.** Every reduction cuts return
  AND deepens drawdown (0.52 -> 0.34-0.40 risk-adjusted). The hedge is not
  merely insurance: full coverage is what lets the weekly top-up buy dips
  aggressively. Half-hedging keeps the cost and loses the enabling effect.
- **(d) Deep-ITM harvesting hurts** (−46 points). It fires once; selling a
  deep-ITM put mid-crash surrenders exactly the protection that was about
  to pay. The exercise-vs-sell study was right about the *mechanics* of
  which exit is cheaper, but wrong as a *strategy* trigger.

### No-underlying variants (never hold shares)

| strategy                        | return  | CAGR  | maxDD  | CAGR/|DD| |
|---------------------------------|---------|-------|--------|-----------|
| A) cash-secured weekly puts     | −51.8%  | −14.9%| −66.1% | −0.23     |
| B) PMCC (long call + weeklies)  | +79.4%  | 13.8% | −54.5% | 0.25      |
| C) SOXL buy & hold              | +152.3% | 22.7% | −89.2% | 0.25      |
| D) shares + put (the strategy)  | +161.5% | 23.7% | −45.5% | **0.52**  |
| E) shares, cash when SOX<200dma | +57.7%  | 10.6% | −45.2% | 0.23      |
| E2) shares, cash when SOX rv>45%| +79.7%  | 13.9% | −59.4% | 0.23      |

- **A) Cash-secured weekly puts lose money outright** on a 3x ETF:
  $818k of premium collected against $914k of cash-settled assignment
  losses across 111 assigned weeks of 235. Selling ATM weekly puts takes
  the full downside and forgoes all upside — the worst of both.
- **B) PMCC works but is inferior**: exposure-matched long calls
  (120-180 DTE, cheapest per day) plus weekly shorts return +79.4% at
  −54.5% DD. The long call's time decay replaces the put's premium cost
  without capping the downside as effectively.
- **E/E2) Signal-gated de-risking to cash destroys return** (+57.7% /
  +79.7% vs +161.5%) while barely improving drawdown (−45.2% vs −45.5%).
  70 (resp. 44) weeks in cash sold at lows and bought back higher: the
  same lag failure as section 12, now on the equity leg.
- **Holding shares WITH the put is the best structure tested**, and by a
  wide margin risk-adjusted (0.52 vs 0.23-0.25 for everything else).
  Sizing note: the PMCC must be EXPOSURE-matched (invest x balance /
  spot), not premium-matched -- premium sizing levers it ~6x and blew up
  the first run (corrected before reporting).
