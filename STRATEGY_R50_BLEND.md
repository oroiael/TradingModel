# The R:50% Blend — Full Strategy Specification & Backtest

**Strategy name:** Regime-Switched Blend, "R:50% Active above trend / 0% below"
**Engine:** `r_blend_backtest.py` · **Full weekly per-leg table:** `r_blend_ledger.csv` (131 weeks × 63 columns) · **Stats:** `qa/r_blend_report.txt`
**Window:** 2024-01-02 → 2026-07-02, $150,000 start, real EOD quotes, 20%-of-spread fills, $0.65/contract.

## 1. Executive summary

One account runs two sleeves. A **DEFENSE sleeve** (the hardened R2 income
engine) runs every week of the year. An **ACTIVE sleeve** (trend calls plus a
re-struck straddle) exists **only while SOXL is above its 100-day moving
average** and is closed entirely below it. One weekly boolean drives the
allocation.

| headline (integrated backtest, QA-reconciled) | |
|---|---|
| End wealth | **$528,150 (+252%, 64.8% CAGR)** |
| Max drawdown | **−25.2%** — the shallowest of any high-return strategy tested in this project |
| MAR (CAGR/maxDD) | 2.58 |
| Worst / best single week | −11.6% / +17.2% |
| 2025 crash (Feb–May) | **+16.7%** while SOXL fell ~75% |
| 2026 crash (June) | −16.9% (vs −28.6% buy-hold, −37.7% pure Active) |
| Weeks with realized Defense income | 65 of 131; sweep account ends at $55,468 |
| IBKR portfolio-margin utilization | avg 17.7%, max 29.6% — never near a margin call |
| Regime flips in 2.5 years | 8 (low churn) |

For reference: pure Defense ended $477k at −27.6% DD; pure Active $1.53M at
−54.6% DD; buy-and-hold $764k at −75.2% DD.

## 2. Why this strategy exists — the evidence chain

Every design choice traces to a measured fact from this repo's labs:

1. **SOXL options are cheap at the back, fair-to-rich only in the front week**
   (pricing lab S2: 90–180-day ATM implied vol under-priced subsequently
   realized vol by 22–29 points; weekly IV roughly fair). → *Own long-dated
   options; never be net short movement.*
2. **Every net-short-movement structure lost money** across ~200 tested
   permutations (naked puts/calls/strangles/straddles S6, put diagonals R1,
   iron condors R3). → *The short side of this strategy is one small,
   covered, weekly call — nothing else.*
3. **Deep-ITM calls beat owning shares** (R2: long-call-only $796k vs
   buy-hold $764k with 27 points less drawdown; put-call parity F5 shows
   synthetic longs priced ~2–3%/yr below fair carry). → *All long exposure is
   via 75Δ calls, never stock.*
4. **The weekly short call earns its keep only in chop; it destroys value in
   recoveries and melt-ups** (hedge campaign F-lever: skipping it below trend
   added +$165k). → *D2 is gated by trend and by post-crash weeks.*
5. **Exposure sizing beats timing signals for drawdown control; put wings pay
   in fast crashes; monetizing them recycles crash gains** (hedge campaign:
   invest-50% cut DD to −30% keeping fast recovery; wing +16% in crash25;
   TP at 2–3x best). → *Defense = 50% deployment + 0.5-ratio 90-day wing
   with 3x take-profit.*
6. **Trend information is real but only at long lookbacks** (active lab:
   100d SMA MAR 2.46 vs 20d SMA 0.53 — short lookbacks churn). → *The 100-day
   SMA is the regime switch.*
7. **The two books earn in different regimes but are +0.69 correlated**
   (blend lab), so the best combination is not "hold both always" but
   "hold Active only in its winning regime" — the R:50/0 policy won the
   24-policy allocation tournament.

## 3. The regime signal — what, why, and its known weakness

**Definition.** `SMA100` = simple average of the last 100 daily SOXL closes
(from the 5-minute file's 15:55 bars). **RISK-ON** if the first-trading-day
close of the week ≥ SMA100; else **RISK-OFF**. Evaluated once per week; acted
on at that evening's prices (live: Monday's session).

**Why an SMA at all?** It is the only signal in our data that tested as both
informative and robust: it powers the F-lever (fact 4), the active lab's best
run (fact 6), and the winning allocation policy (fact 7). IV-based gates were
tested and rejected — the term structure is inverted 67% of all days, so it
carries almost no timing information (pricing lab S3).

**Why 100 days?** Tested against 20, 30, 50 SMAs and 10/20/40-day breakouts.
On a 115%-vol 3x ETF, short lookbacks whipsaw: the 20d version of the same
active strategy ended at $415k with a −94% drawdown vs $1.7M at −66% for the
100d. 100 days ≈ half a year of trading — long enough that only regime-scale
moves flip it (8 flips in 131 weeks), short enough to exit the 2024-25 bear
near its start (RISK-OFF from 2024-07-29, re-entering 2025-06-09 after the
bottom).

**Its known weakness — stated plainly:** the SMA lags peaks. In June 2026
SOXL crashed from $300 while the SMA100 was still far below price, so the
strategy stayed RISK-ON through the first −28% week. That single episode is
this strategy's entire max drawdown (−25.2%, peak 2026-06-15). The wing, the
straddle put, the call-skip and the 50% sizing are what kept it to −25%
instead of the −55 to −75% the unhedged books took. No trend signal fixes
crash-from-peak; only the always-on hedges do.

**Signal-concentration caveat:** the same family of signal appears three
times (allocation SMA100, Active direction SMA100, Defense call-skip SMA50).
This is deliberate simplicity, but it means one indicator family carries a
lot of weight — a reason for out-of-sample validation before live capital.

## 4. Architecture

```
                        ONE IBKR ACCOUNT ($150k start)
                                    |
             Monday EOD: is SOXL close >= 100-day SMA ?
                    |                               |
                RISK-ON                         RISK-OFF
          50% ACTIVE + 50% DEFENSE         100% DEFENSE (active legs closed)
                    |                               |
   ACTIVE sleeve (of its 50%):          DEFENSE sleeve (of its equity):
   A1 75d call ~150 DTE   (50%)         D1 75d call ~150 DTE        (50%)
   A2 ATM call ~120 DTE \ (25%,         D2 short weekly 15-20d call (1:1 D1,
   A3 ATM put  ~120 DTE / re-struck        gated by 50d SMA & drop rule)
                          at 25% moves) D3 25d put ~90 DTE (0.5 per D1,
                                           3x take-profit)
                                        D4 idle cash at T-bill yield (4%)
   max loss = premium held              sweep: 25% of positive weekly
   (all legs long)                      realized Defense P&L -> side account
```

## 5. Leg-by-leg specification

Execution rule for every option trade (project standard):
**sell** = bid + 0.20×(ask−bid); **buy** = ask − 0.20×(ask−bid); quotes with
bid = 0 or ask < bid are rejected and the next nearest liquid strike is used.
Whole-dollar strikes preferred. All entries/rolls happen on the week's first
trading day (backtest: EOD; live: Monday ~10:00 per the original project
convention).

### D1 — Defense long call (the income engine's chassis)
- **What:** CALL, delta nearest **0.75**, expiry nearest **150 DTE** within
  120–180.
- **Why:** stock replacement — carries the upside at ~⅓ the capital of
  shares with loss capped at premium (facts 1, 3).
- **Size:** contracts = (50% × Defense sleeve equity) ÷ (spot × 100) — i.e.
  share-equivalent notional, NOT premium-maximized. Resized weekly toward
  target with a 10% dead-band.
- **Exit/roll:** when DTE ≤ 45, sell and re-buy fresh 150 DTE at 0.75Δ
  (≈ every 15 weeks; 131-week backtest did it 7 times plus resizes).
- **Ledger example (week 1, 2024-01-02):** bought 13 × K$23 calls exp
  2024-05-17 at $7.89 (quote bid 7.65/ask 7.95, Δ0.76, 136 DTE) = $10,257.
- **Backtest P&L: +$191,259 realized — the largest earner in the book.**

### D2 — Defense weekly short call (the income tap)
- **What:** sell CALL, delta nearest **0.175** (the 15–20Δ band), expiring
  this week (3–7 DTE), exactly 1 contract per D1 contract (never naked).
- **Why:** converts chop into weekly cash; front-week is the only tenor
  where selling isn't structurally underpaid (fact 1).
- **Triggers that SKIP the sale (48 of 131 weeks):**
  - spot < **50-day SMA** ("don't cap the V-recovery" — fact 4), or
  - last week fell more than **10%** (post-crash bounce weeks).
- **Exit:** none — held to Friday, cash-settled at intrinsic vs the
  expiry-day close. If it finishes in the money, the loss is intrinsic −
  credit; D1 gains more than D2 loses on the way up (Δ0.75 vs Δ0.175).
- **Ledger example (week 1):** sold 13 × K$30 calls exp 2024-01-05 at
  $0.152 (quote bid 0.15/ask 0.16, Δ0.16, 3 DTE); expired worthless Friday
  (close $25.94), **+$197.60 kept**.
- **Backtest P&L: −$15,848 realized** — a small net cost over this window
  (it earns in chop, gives some back in melt-ups) in exchange for 65
  income weeks and $55k swept. This is the honest price of weekly cash.

### D3 — Defense put wing (the crash airbag)
- **What:** buy PUT, delta nearest **0.25**, expiry nearest **90 DTE**,
  **0.5 contracts per D1 contract**.
- **Why:** 90-day puts sit where implied vol is most under-priced (fact 1);
  half-ratio was the best cost/protection point in the 27-variant wing sweep.
- **Exit/roll triggers:**
  - **Take-profit:** the moment its sale price ≥ **3× cost**, sell it and
    immediately re-buy a fresh 25Δ/90-DTE put. This monetizes crashes near
    the bottom. Fired once: **2025-04-07, sold at $16.13 vs ~$5.3 cost,
    +$14,940 realized in the worst week of the crash**, then re-armed.
  - **Time:** roll at ≤ 21 DTE (typically costs cents — expired wings sold
    at $0.01–0.95 in the ledger).
- **Backtest P&L: −$12,703 realized** — ~0.9%/yr of average equity; that is
  the insurance premium, and it bought +16.7% during the 2025 collapse.

### D4 — Cash & sweep (the ballast)
- Idle cash accrues **4% APY** (T-bill assumption — the one number not from
  the data files; +$15,764 over the window). Every week, **25% of positive
  realized Defense P&L** moves to a separate sweep account ($55,468 by the
  end). The sweep is the strategy's "paycheck" ledger.

### A1 — Active trend call (the regime rider)
- **What:** identical instrument to D1 (75Δ, ~150 DTE call) but sized at
  50% × **Active** sleeve equity, and it **only exists in RISK-ON**.
- **Why:** when the trend is up on a 3x ETF, the dominant P&L source is
  simply being long with convexity (active lab: trend-100 was the single
  best signal tested).
- **Exit:** closed at the sale price the first week the regime flips
  RISK-OFF; rolled at ≤45 DTE otherwise.
- **Backtest P&L: +$136,108 realized across 85 RISK-ON weeks.**

### A2/A3 — Active straddle (the swing harvester)
- **What:** buy CALL + PUT at the **same whole strike nearest spot**,
  expiry nearest **120 DTE**, 25% of Active sleeve equity split evenly.
  RISK-ON only.
- **Why:** direction-free convexity on the cheapest part of the vol surface;
  profits from a wild swing in EITHER direction (fact 1 + user requirement).
- **The re-strike trigger (the active "trading in and out"):** whenever spot
  closes ≥ **25% away from the straddle strike**, sell both legs and re-buy
  a fresh ATM pair. Each re-strike converts the winning leg's paper gain
  into cash and resets the position. Fired **11 times** (e.g. 2026-04-13,
  -04-27, -05-11, -06-15 during the melt-up — each one banked call-side
  gains on the way to $300). Also rolled at ≤45 DTE.
- **Backtest P&L: calls +$117,847, puts −$52,088 → net +$65,759.** The put
  side is expected to bleed in an up-trending regime; it's the half that
  pays when a crash begins while still RISK-ON (June 2026: the straddle puts
  and D3 wing are why the worst week was −11.6% and not −20%+).

## 6. The weekly operating procedure (exactly what the engine does)

**Monday (first trading day), evening prices — in this order:**
1. Accrue cash interest; mark every leg to the day's quotes.
2. **Compute the regime boolean:** close ≥ SMA100 → RISK-ON else RISK-OFF.
3. Set sleeve targets: Active = 50% of total equity if RISK-ON else 0;
   Defense = the rest.
4. **Active sleeve:** if RISK-OFF, close A1/A2/A3 (sell at the 20% rule).
   If RISK-ON: manage A1 (buy if absent / roll if ≤45 DTE / resize to
   target); manage the straddle (re-strike if 25% moved, roll if stale,
   buy ATM pair if absent).
5. **Defense sleeve:** manage D1 (same rules as A1 on its own target);
   manage D3 (take-profit check first, then time roll, then buy if absent);
   sell D2 unless a skip trigger is active.
6. Record the portfolio-margin scan (±45% TIMS-style stress).

**Friday (expiry):** D2 settles at intrinsic vs the closing price. Nothing
else expires — every other leg is rolled ≥ 3 weeks before expiry by rule.

**Between Mondays:** nothing, in the backtest (EOD data limit). Live in
IBKR, the same triggers can be evaluated on streaming quotes — the 3x wing
take-profit and the 25% re-strike would fire mid-week at better prices, and
a crash-day regime exit wouldn't wait for Monday. The backtest is therefore
the *slow* version of this strategy.

## 7. Trigger reference card

| # | trigger | threshold | checked | action |
|---|---|---|---|---|
| T1 | Regime switch | close ≥/< SMA100 | weekly, Mon EOD | open/close entire Active sleeve; reweight to 50/50 or 0/100 |
| T2 | Long-call roll (D1, A1) | DTE ≤ 45 | weekly | sell, re-buy 150 DTE 75Δ |
| T3 | Long-call resize | drift > 10% from target contracts | weekly | trim/top-up to sleeve target |
| T4 | Short-call skip (D2) | spot < SMA50 **or** last week < −10% | weekly, before selling | don't sell this week's call |
| T5 | Short-call settle | Friday close vs strike | Fri | cash-settle intrinsic |
| T6 | Wing take-profit (D3) | sale price ≥ 3× cost | weekly (live: continuous) | sell wing, realize, re-buy fresh |
| T7 | Wing time roll (D3) | DTE ≤ 21 | weekly | sell, re-buy 90 DTE 25Δ |
| T8 | Straddle re-strike (A2/A3) | \|spot/strike − 1\| ≥ 25% | weekly (live: continuous) | close pair, re-buy ATM |
| T9 | Straddle time roll | DTE ≤ 45 | weekly | close pair, re-buy ATM 120 DTE |
| T10 | Income sweep | weekly Defense realized > 0 | Fri | move 25% to sweep account |

## 8. Backtest results in full

**Wealth path:** $150,000 → $528,150 (+ $55,468 already in the sweep
account is included in that figure). QA: every cash flow reconciles —
start + Σrealized + interest − commissions = final cash + sweep to the cent.

| year | return | regime mix | notes |
|---|---|---|---|
| 2024 | +11.9% | mostly RISK-ON, two flips | chop; short calls + straddle re-strikes carry it |
| 2025 | +73.8% | RISK-OFF Jan→Jun | **+16.7% through the crash** (wing 3x monetization, no active longs, calls skipped); re-entered RISK-ON 2025-06-09 into the recovery |
| 2026 (H1) | +81.1% | RISK-ON melt-up, brief Apr flip | straddle re-strikes bank the run to $300; June crash costs −16.9% |

**Drawdown anatomy:** max −25.2%, peak 2026-06-15 → trough at data end
(the June-2026 crash is still open when data stops 2026-07-02). The
2024-25 bear — which was the max-DD episode for *every* earlier strategy —
cost this blend only ~−15% peak-to-trough because the regime switch had the
account in Defense-only mode for most of it. Worst three weeks are all
June 2026 (−$73.8k, −$48.2k, −$33.4k from a $610k peak).

**Realized P&L attribution (per leg):** D1 +$191k · A1 +$136k ·
A2 straddle-calls +$118k · A3 straddle-puts −$52k · D2 short calls −$16k ·
D3 wing −$13k · interest +$16k · commissions −$2.2k. The two 75Δ call legs
are the engine; the short call and both hedge legs are small net costs that
bought the −25% drawdown profile and 65 income weeks.

**Margin:** TIMS-style ±45% scan each week: average utilization 17.7% of
equity, maximum 29.6%. Everything is cash-funded (long premium + covered
short); the account never approaches Reg-T limits either. PM account
optional but preferred.

## 9. Important honesty note: NAV simulation vs this integrated backtest

`blend_lab.py` projected this policy at ~$1.03M using the two sleeves'
standalone NAV return streams. The integrated engine — the number to trust —
ends at $528k. The gap is real and instructive: the standalone Active book's
RISK-ON returns partly came from positions it had *carried through*
RISK-OFF periods (straddles struck at crash-bottom prices, etc.). A sleeve
that is switched off cannot carry those positions, so applying its return
stream to a switched allocation overstates results. The integrated backtest
opens Active fresh at each RISK-ON flip and pays the real re-entry spreads.
Both artifacts are kept in the repo deliberately: the comparison is a
caution against portfolio math done on strategy return streams.

## 10. Known weaknesses, caveats, and open data requests

1. **In-sample.** One 2.5-year window containing two crashes and one
   melt-up. The 100d-SMA family is used three times. **2021–2023 SOXL
   option chains remain the gating request before live capital.**
2. **Crash-from-peak lag** (§3): −25% drawdowns can and will happen again;
   the hedges bound it, the signal does not prevent it.
3. **EOD quotes only:** entries, re-strikes, take-profits and regime exits
   all execute at end-of-day; live automation on streaming data should do
   modestly better, but that claim is unverified (intraday option data
   requested).
4. **4% cash APY is an assumption**, not from the data files (T-bill series
   requested). Setting it to 0 lowers the end result by ~$16–20k.
5. Dividends, early assignment on D2 (American exercise around ex-dates),
   and borrow fees are not modeled; the whole-strike and liquidity rules
   follow the project spec.

## 11. IBKR automation sketch

One weekly cron + one Friday settlement check + optional intraday hooks:
- Monday 10:00 ET: compute SMA100/SMA50 from daily bars (or IBKR
  historical), evaluate T1–T4, submit the leg adjustments as individual
  limit orders at the 20%-rule prices (legs are independent here — no combo
  needed except optionally pairing the straddle).
- Streaming hooks (optional, improves on backtest): T6 wing take-profit and
  T8 re-strike as live conditional orders; a fast-crash regime exit.
- State persisted to disk; reconcile against `reqPositions()` on restart
  (per the Active-Version spec already in this repo).

## 12. Reproduce

```bash
git lfs pull && pip install pandas numpy scipy
python3 r_blend_backtest.py     # ~1 min: ledger + report
```
`r_blend_ledger.csv` columns: week/spot/SMA/regime/sleeve targets, then per
leg (`D1_longcall_*`, `D2_shortcall_*`, `D3_putwing_*`, `A1_trendcall_*`,
`A2_stcall_*`, `A3_stput_*`): action, strike, expiry, contracts, fill price,
quote audit note, realized P&L; then weekly cash/sweep/equity/wealth and the
portfolio-margin scan.
