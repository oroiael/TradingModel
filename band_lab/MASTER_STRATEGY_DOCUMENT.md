# SOXL Intraday Churn Harvester — Master Strategy Document

Version 1.0 — 2026-07-28. Prepared for third-party validation and live
implementation. Repository: `oroiael/TradingModel`, directory `band_lab/`
(research programs, results, and this document), `cycle_lab/` (data
loaders and the demoted satellite strategy).

---

## 1. Executive summary

The strategy trades SOXL (3x leveraged semiconductor ETF) long-only,
intraday-only, on roughly half of all trading days — the days when the
semiconductor sector's volatility regime is elevated. It buys 1%
pullbacks below the session high, takes +1% profits, stops at −4%, quits
after 2 stop-outs or 5 trades, and is always flat by the close.

Backtested on 6 years of 5-minute bars (2020-07 → 2026-07):
**65.6 bp per traded day gross, Sharpe 3.09, worst single day −8.0%**,
with every one of its 12 rule parameters individually audited through
prespecified test programs, walk-forward validation, and mechanism
requirements. A conservative live expectation, after an out-of-sample
haircut and IBKR Pro Fixed costs, is **~49 bp per traded day** — at
$150,000 flat sizing roughly **+$1,900/week on average, with a heavily
skewed distribution** (median week ≈ +$200, 5th-percentile week ≈
−$9,000, ~1 week in 4 has no trading at all).

The single most important research finding (Section 3): the strategy's
edge is NOT "dip buying" per se. Removing only the instant-re-entry
behavior costs 48 of the 66 bp — the engine is *staying long below the
session high in +1% increments on high-volatility days*, with the 2-stop
breaker as the escape hatch.

## 2. The instrument and the opportunity

SOXL moves in a wide intraday band: median daily range **6.7% of the
open** (IQR 4.9–9.1%), containing on average **15 completed ≥1% swings
per day** — there has not been a single 0-swing day in six years. The
band is built early (68% of the day's final range is set by 10:30) and
its width is predictable (day range ≈ 1.9 × the opening 30-min range,
correlation 0.62). Volatility clusters violently: P(high-vol day |
high-vol yesterday) = 38% vs a 17% base rate, with bursts up to 11
straight sessions. The strategy is a systematic harvester of that churn,
switched on only when the churn is rich enough to pay (trailing 5-day
range ≥ 6%) and switched off on the one morning type with measured
negative edge (violent *down*-opens).

## 3. What the trade actually is (mechanism)

The naive description — "buy 1% dips, sell +1% pops" — understates what
the audit found. The final mechanism picture, each element measured:

1. **Exposure below the high** (V2 program): the entry anchor is the
   session high, which never decays. After any exit, if price still sits
   ≥1% below that high, the strategy re-enters essentially immediately.
   These re-entries — 1–4% below the anchor — are the BEST trades in the
   book (31–33 bp/trade vs 12.8 bp for "true" fresh 1% dips). Removing
   instant re-entry collapses the edge from 65.6 to 17.7 bp/day.
   **The willingness to stay exposed below a standing high is ~73% of
   the edge.**
2. **The +1% cadence** (V1/V3): SOXL's harvestable reversion operates at
   a ~1% grain regardless of how wide the day is — adaptive levels were
   tested and rejected (the optimum does not migrate across band
   regimes).
3. **The volatility gate** (V10): edge by trailing-vol quartile is
   −9/+30/+20/+51 bp/day. Quiet tape = no edge. The gate is sector vol,
   not instrument vol (a SOXX-derived gate selects 777 of 787 identical
   days).
4. **The morning filter** (V9): violent down-opens (top-quintile opening
   range with the 10:00 print in the lower ⅔ of it) are the one cohort
   with negative edge (−66 bp/day); violent UP-opens are among the best
   days (+89 bp/day) and are traded.
5. **The 2-stop breaker** (V11): after two stop-outs, the measured
   rest-of-day expectation is negative (−20 bp); after one it is positive
   (+23 bp). Quitting at exactly two both adds return and converts the
   worst day from −11.4% to a structural −8.0% (2 × −4%).
6. **Flat overnight** (V6): holding stalled positions overnight would add
   17–26 bp/day and was rejected deliberately: the sample contains −21.6%
   and −19.8% overnight gaps, and the sleeve's design role is zero gap
   exposure. This is the insurance premium, paid knowingly, priced
   precisely.

## 4. The locked rules

> **Gate (pre-open):** trade today only if ATR5 ≥ 6.0%, where ATR5 =
> 5-session trailing mean of (High−Low)/Open. Skip scheduled half-days.
> **Filter (10:00):** compute OR30 = (09:30–10:00 High−Low)/Open. If
> OR30 ≥ its trailing-2yr 80th percentile (≈5.4% currently, recomputed
> monthly) AND the 10:00 print is below the top third of that range →
> stand down for the day.
> **Trading window:** 11:00 → close. Maintain a resting buy limit at
> 0.99 × session high (ratchets up only). On fill at E: OCA bracket —
> sell limit 1.01×E, sell stop 0.96×E. After any exit, re-arm.
> **Counters:** stop for the day after 5 entries or 2 stop-outs,
> whichever first. **15:55–16:00: flatten, no exceptions.**
> **Sizing:** flat fraction f of sleeve equity per trade. f=1.0 =
> growth setting; half-capital accounts should use the per-unit pyramid
> variant instead of flat f=0.5 (V11/V8). Never above f=1.0.

Recorded alternatives (tested, documented, not default): gate at 5.5%
(better calendar compounding, −0.24 Sharpe), SOXX-derived gate (validated
fallback input), 25% SOXS overlay (drawdown dial, costs ~6 bp/day),
mid-morning filter re-admission (flagged for next annual review).

## 5. Variables: how each was tested and what happened

Method used throughout: (1) a written test plan per variable with all
parameters prespecified BEFORE running; (2) measurement-first
("conditional stat before the rule"); (3) plateau verdicts — a winner
needs neighbor support, never a lone spike; (4) yearly walk-forward with
selection on prior data only, adoption bar OOS ≥4 of 5 years; (5) a
mechanism requirement — wins must be explainable by WHICH days/trades
they fix, or they are treated as curve-fit and rejected.

| var | parameter | final | program outcome |
|---|---|---|---|
| V1 | dip depth | 1% fixed | swept 1–3%; adaptive (×band) rejected — optimum does not migrate |
| V2 | entry anchor | session high | windowed/VWAP/prior-close/reset all rejected monotonically; instant re-entry priced at +47.9 bp/day |
| V3 | target | +1% fixed | swept 1–2%; adaptive rejected on mechanism + OOS |
| V4 | stop | −4% **absolute** | swept 2/3/4 twice; scaled stop broke the worst-day guarantee (−20%) — absolute matters, not ratio |
| V5 | start time | 11:00 | swept 09:35–13:00 on corrected engine; plateau 10:30–11:30; 09:35 spike exposed the engine bug and was rejected by plateau rule |
| V6 | EOD exit | flat at close | overnight holds win +17–26 bp/day and were REJECTED on role (gap tail −20%+); premium priced |
| V7 | trade cap | 5 | swept 1–10; Sharpe peaks at 5 |
| V8 | direction | long only | mirror short −17.7 bp under honest fills; SSR binds 16.6% of gated days; pyramid variant adopted for half-capital |
| V9 | day filter | direction-aware OR30 | boundary plateau-confirmed; direction split (+89 up / −66 down) found the true mechanism; adopted, WF 5/5 |
| V10 | vol gate | ATR5 ≥ 6, 5d, cliff | every knob confirmed; U-shape anomaly closed as era-noise; ATR10 "win" exposed as matched-rate artifact |
| V11 | sizing | flat f + 2-stop breaker | six-test program; breaker adopted (better return AND tail); leverage rejected (bootstrap P(−30% DD/yr)=46% at f=1) |
| V12 | role | intraday core, cycle satellite | walk-forward: core retains ~83% of edge OOS; satellite failed OOS (3.3% CAGR) until SMA100 kill-switch (27% OOS CAGR) |

Errors found and fixed along the way (disclosed deliberately): a
**same-bar lookahead bug** in the original simulator (entry trigger set
by the current bar's own high could be "filled" by that same high) —
found when a 09:35-start cell printed Sharpe 5.7, fixed by making the
trigger a true resting limit (prior bars only) with next-bar-earliest
target fills; the fix *raised* the honest 10:30 baseline (the bug cut
both ways midday) and destroyed the morning mirage. Additionally, four
attractive in-sample results were rejected by protocol: the 09:35 start,
the ATR10 lookback (matched-rate artifact), the adaptive target cell,
and the frictionless two-sided book (Sharpe 4.05 → 1.56 under tradable
fills).

## 6. Backtest results and expected performance ($150,000 start)

### 6.1 Headline series (locked core, 2020-07 → 2026-07)

- ON days: 787 of 1,510 (52%); ~3.2 fills per ON day.
- Gross: **65.6 bp/ON-day, Sharpe 3.09** (ON-day basis), ON-day win rate
  63.7%, median ON-day +77 bp, worst day −8.0% (structural).
- Max drawdown on the calendar equity curve: −36.5%.
- Note: 2020 H2 contributes ~zero because the filter requires ~6 months
  of threshold history before it can trade.

### 6.2 The honesty chain (what to actually expect)

Full-sample gross is an upper bound. The discount chain:
1. **Out-of-sample haircut.** The original core retained ~83% of its
   in-sample edge under yearly walk-forward. Each later refinement
   passed its own walk-forward, but successively adopted refinements
   accumulate selection bias no per-program test fully removes.
2. **Costs.** IBKR Pro Fixed ≈ 0.9 bp/round-trip commission at $150K
   size; with spread costs on stops and EOD flattens, all-in drag ≈ 4–7
   bp/ON-day.
3. **Fill realism.** Entries/targets assume resting limits fill at the
   touch on 5-min bars. Unverified below the 5-min grain (top remaining
   risk — see §7).

**Conservative planning scenario** (gross × 0.83, minus 5 bp/day costs):
**49.4 bp/ON-day**.

### 6.3 Weekly expectations at $150,000 (flat sizing, no compounding)

From the 315-week backtest distribution:

| metric | gross | conservative |
|---|---:|---:|
| mean week | +$2,458 | +$1,853 |
| median week | +$440 | +$215 |
| P25 / P75 | $0 / +$6,465 | ≈$0 / ≈+$5,300 |
| 5th percentile week | −$10,643 | −$9,103 |
| worst week in sample | −$23,701 | ≈−$20,000 |
| best week in sample | +$27,477 | ≈+$22,500 |
| weeks with any trading | 77% | 77% |
| positive weeks (of trading weeks) | 69% | ~67% |

Read this table honestly: **the strategy earns in lumps.** A typical
week is roughly flat-to-slightly-positive; the annual result is carried
by the high-volatility burst weeks. Annual gross P&L at flat $150K
varied from +$74K (2025, 2026-H1) to +$216K (2022) — the strategy's
year is decided by how much vol the market delivers, which the gate can
select for but not create.

### 6.4 Compounded projections (and why to distrust them)

Reinvesting fully, the gross series compounds $150K → $16.5M over the
6-year sample (118%/yr); the conservative series → $5.3M (81%/yr).
**These numbers should be treated as arithmetic, not expectations.**
No allowance is made for: capacity/impact above ~$1M positions, fill
degradation as size grows, regime shift (a low-vol era turns the
strategy off — correct behavior, zero return), or the residual
optimism in any strategy validated on the data that shaped it. The
defensible planning claim is the per-ON-day range (≈50–65 bp gross-to-
net) and the weekly distribution above — compounding is then a choice,
not a promise.

### 6.5 Drawdown: the three numbers and how they relate

These are distinct metrics — do not conflate them:

| metric | value | definition |
|---|---:|---|
| worst single day | **−8.0%** | structural cap: 2 stop-outs × −4%, breaker halts the day |
| worst 10 consecutive ON-days | −29.3% | capped days CHAIN — a drawdown is a sequence, not one day |
| max drawdown, compounded equity (f=1.0) | **−36.5%** | peak 2025-11-12 → trough 2026-03-26 (92 sessions), recovered 2026-05-06 |
| same episode at FLAT $150K sizing | −$63.9K (−42.6% of start) | flat sizing looks worse in % of starting capital because positions don't shrink during the streak |
| bootstrap P(−30% DD within a year) at f=1.0 | 46% | the realized −36.5% is expected texture, not an outlier |

(Historical note for readers of earlier round documents: a −22.9% max-DD
figure appears in the round-3 combined-backtest table — that was the
ORIGINAL day-sleeve configuration (10:30 start, plain filter, no
breaker, pre-bug-fix engine, 2022-start window) and is superseded; the
current locked core's number is the −36.5% above.)

Anyone uncomfortable with a −36.5% realized / −30%-per-year-near-coin-flip
profile must run the half-capital per-unit pyramid variant (V11/V8) or
the 25% SOXS overlay dial — not full size.

## 7. Double-check: verified, unverified, and items for third-party review

**Verified in this work:**
- No-lookahead audit of every input: gate uses prior-day data (shifted);
  filter threshold uses shifted rolling quantiles; the 10:00 direction
  check precedes the 11:00 start; the engine's trigger uses prior bars
  only and targets fill next-bar-earliest; split adjustment (2021 15:1)
  verified against the discontinuity scan; SOXS/SOXX files verified
  back-adjusted/clean.
- Commission arithmetic confirmed against the published IBKR Pro Fixed
  schedule (uploaded to the repo owner 2026-07-28).
- Every adopted rule carries a yearly walk-forward OOS table in its
  results doc.

**Known limitations / unverified assumptions (the honest list):**
1. **Sub-5-minute fill sequencing** (A1/A2): stop-before-target within a
   bar is assumed (conservative), and limit fills at the touch are
   assumed (optimistic). 1-minute or tick data would settle both. This
   is the highest-priority item for the validator.
2. **Cumulative selection bias**: 12 sequential audit programs each ran
   walk-forwards, but the sequence itself was steered by results. The
   clean test is forward: paper trading against the backtest's daily
   expectations.
3. **Single instrument, single regime history**: 6 years, one ETF, a
   sample whose last 18 months were extraordinarily volatile. FAS/SPXL/
   TQQQ 5-min files exist in the repo for a transfer test that was NOT
   run (recommended to the validator).
4. **Costs are estimated, not simulated**: the 4–7 bp/day drag is
   arithmetic, not a fill-by-fill cost model.
5. **The V9 direction refinement and V5 start move were adopted from
   full-sample evidence with WF support** — their incremental ~+10 bp
   over the original 10:30/orq5 core is the least-seasoned part of the
   edge estimate. The conservative scenario effectively assumes much of
   it away.

**Suggested third-party validation checklist:**
(a) re-run every `band_lab/v*_tests.py` script from raw CSVs and diff
against `band_lab/out/*.csv`; (b) independently re-implement the locked
rules from §4 alone (clean-room) and compare daily P&L series; (c)
obtain 1-minute data for 2022 and 2026 and re-test fills; (d) run the
transfer test on TQQQ/FAS/SPXL; (e) audit the no-lookahead claims in
`v2_anchor_tests.py` (the canonical current-core implementation);
(f) 3–6 months of paper trading with fills logged against the §6.3
distribution before capital.

## 8. Automation architecture (IBKR) — attended and unattended

No code yet — this is the system design.

### 8.1 Platform components

- **Broker interface:** IB Gateway (headless) or TWS, managed by IBC
  (auto-login/restart). API via the official Python API or `ib_async`.
  Client Portal API is an alternative but the socket API's native
  bracket/OCA and pegged orders fit this strategy better.
- **Market data:** IBKR US equities L1 subscription (a few $/mo;
  waived-tier data is delayed — not acceptable). The strategy needs only
  SOXL 5-second/5-minute bars (`reqRealTimeBars` aggregated, or
  `reqHistoricalData` keep-up-to-date) and daily history for the gate.
- **Host:** a small VPS (or always-on local machine) in a US-East region
  for latency symmetry; the strategy is not latency-sensitive (5-min
  granularity) but IS uptime-sensitive between 09:30–16:00 ET.
- **State store:** a small local DB (SQLite is sufficient) persisting:
  daily gate/filter decisions, session high, open order IDs, position,
  counters (fills, stop-outs), and every fill — so a process restart
  mid-day recovers exact state instead of re-deciding.

### 8.2 Daily state machine

1. **06:00 ET — pre-open job:** pull last 5 completed daily bars,
   compute ATR5, write gate decision. Recompute the monthly OR30
   threshold on the first session of each month. If gate OFF → the
   engine stays dormant; nothing can place an order (hard interlock).
2. **09:30–10:00 — observe:** build OR30 from live bars.
3. **10:00 — filter decision:** OR30 vs threshold + top-third direction
   check; write ON/STAND-DOWN. Track session high continuously.
4. **11:00 — activate:** place the resting buy limit at 0.99 × session
   high, sized floor(f × equity / price). On every new session high,
   modify the order upward (never downward). This ratchet is the one
   behavior IBKR has no native order type for — it is ~20 lines of
   event-driven logic on the 5-min bar close.
5. **On fill:** immediately place the OCA pair (limit +1%, stop −4%,
   stop-market). Increment fill counter. Suspend the entry limit while
   the position is open.
6. **On exit:** log; increment stop counter if stopped; if counters
   allow (fills < 5, stops < 2), recompute session high and re-place the
   entry limit; else cancel everything and go dormant.
7. **15:55 — flatten:** cancel all orders; if a position exists, market
   (or MOC) sell. Verify flat by 16:00; alert loudly if not.
8. **16:10 — reconcile:** compare internal fills vs IBKR execution
   report; write the daily row (P&L, fills, counters, gate/filter
   state); append to the live-vs-backtest monitoring series.

### 8.3 Attended vs unattended

- **Attended mode** (recommended first 3–6 months): the engine runs the
  full state machine but a human confirms two things daily — the 10:00
  stand-down decision and the 15:55 flat state — via a dashboard or even
  a two-line phone notification with an approve/abort action. Human can
  hit a global KILL (cancel all, flatten, dormant) at any time.
- **Unattended mode** adds: IBC-managed auto-restart and daily Gateway
  re-auth; a connectivity watchdog (if the API session or market data
  drops >60s while in a position → flatten via a redundant path);
  process-level "dead-man" — a second tiny process whose only job is to
  verify the main engine heartbeats and flatten if it doesn't;
  broker-side protective stop always resting (never rely on
  software-only stops); daily-loss circuit breaker (if day P&L <
  −8.5% of sleeve — beyond the structural worst day — flatten and
  dormant pending human review); notifications (push/SMS/email) on
  every fill, every state transition, and every anomaly.
- **Fail-safe philosophy:** every failure mode resolves to FLAT. The
  strategy's whole design (no overnight, resting stops, hard counters)
  is unusually compatible with unattended operation because the
  worst-case of "do nothing" is being flat in cash.

### 8.4 Rollout plan

1. Paper account: run the full engine 4+ weeks; diff fills vs backtest
   assumptions (the #1 unverified item in §7).
2. Live at 10–20% size ($15–30K): 4–8 weeks; verify cost/slippage
   arithmetic against real executions.
3. Scale to target size only if live bp/ON-day sits within the §6.3
   conservative band; any structural shortfall (fill rates, filter
   frequencies off by >20%) → back to research, not to hope.

---

## Appendix A — Trading desk runbook (manual operation)

*(Identical to STRATEGY_SPEC.md §2.5; reproduced for standalone use.)*

**Account:** IBKR Pro, Fixed pricing, margin-type account (for same-day
proceeds re-use, not leverage), equity > $25K (PDT). No short/options
permissions required. Nothing held overnight.

**Pre-open:** ATR5 = 5-day mean of (H−L)/O. ≥6.0% → ON, else OFF.
Half-days OFF.
**10:00:** OR30 = (H−L)/O of 09:30–10:00. If OR30 ≥ trailing 80th
percentile (≈5.4%, recompute monthly): stand down UNLESS the 10:00 print
is in the top third of the opening range. No trading before 11:00 ever.
**11:00:** resting BUY LIMIT at 0.99 × session high, floor(f×equity/px)
shares; raise the limit on every new session high (never lower).
**On fill at E:** OCA pair — SELL LIMIT 1.01×E + SELL STOP 0.96×E
(stop-market). Entry limit stays pulled while in a position.
**Counters:** max 5 entries; hard stop after the 2nd stop-out — cancel
everything, done for the day. No discretion.
**After any exit:** recompute session high, re-place entry limit,
re-arm.
**15:55:** replace bracket with market/MOC sell. Flat by 16:00 always.
**Sizing:** f=1.0 growth; half-capital → per-unit pyramid (2 units f/2,
second unit 1% deeper, own brackets); never above f=1.0.
**Costs (verified vs IBKR schedule):** $0.005/sh, $1 min/order, ~0.35 bp
regulatory on sells ⇒ ≈0.9 bp/round trip at $150K; expected all-in drag
4–7 bp/ON-day.
**Prohibitions (each closed by a test):** no pre-11:00 entries; no
trading on stand-down or gate-off days; no shorts (incl. SOXS); no
overnight positions; no third stop; no "one more trade"; no leverage;
never scale the stop.
**Monitoring:** log every fill; weekly compare fills/day (≈3–3.5),
target-hit share (≈75–80%), net bp/ON-day (≈50s, wide variance).
Structural breaks (counts off >20% for a month) → halt and investigate.
Yearly: re-run the walk-forward with new data before re-committing.

## Appendix B — Final scripts (in the repository)

**Canonical current-core reference (corrected engine + all adopted
rules):**
- `band_lab/v2_anchor_tests.py` — most recent full implementation of the
  locked core (its "session" path) + V2 program.
- `band_lab/v5_corrected_rerun.py` — the corrected reference engine
  (`sim_trades_fixed`) and the bug-fix validation run.

**Variable audit programs (corrected engine):**
- `band_lab/v6_eod_exit_tests.py` — V6 EOD-exit program.
- `band_lab/v9_filter_tests.py` — V9 filter program (direction-aware
  filter adoption).
- `band_lab/v10_gate_tests.py` — V10 gate program.
- `band_lab/v1v3_adaptive_tests.py` — V1/V3 adaptive-levels program.

**Variable audit programs (pre-fix engine; verdicts re-verified or
conservative, flagged in STRATEGY_SPEC header):**
- `band_lab/cap_sweep.py` — V7 trade-cap sweep.
- `band_lab/v11_sizing_tests.py` — V11 sizing program (breaker adopted;
  re-verified on corrected engine in v5_corrected_rerun).
- `band_lab/v8_direction_tests.py` — V8 direction program (rejections;
  conservative under the optimistic engine).
- `band_lab/v5_start_time_tests.py` — V5 first pass (superseded by
  v5_corrected_rerun; retained as the bug-discovery record).

**Foundation research:**
- `band_lab/band_analysis.py` — daily-band/excursion study + failed
  OR-fade control.
- `band_lab/churn_harvest.py` — original harvester grid (pre-fix
  engine; historical).
- `band_lab/regime_gate.py` — original vol-gate discovery.
- `band_lab/walk_forward_and_combo.py` — day/cycle walk-forwards +
  two-sleeve combined backtest.

**Satellite (cycle strategy, demoted; optional):**
- `cycle_lab/one_pct_cycle_lab.py` — data loaders (split adjustment) +
  original cycle engine + options-based rounds 1–2.
- `cycle_lab/grid_sweep.py`, `cycle_lab/compound_engine.py`,
  `cycle_lab/kill_switch.py` — cycle grids, $150K compounding engine,
  SMA100 kill-switch validation.

**Documents:** `band_lab/STRATEGY_SPEC.md` (spec + status board + desk
runbook), `band_lab/V*_TESTS.md` (per-variable plans + results),
`band_lab/README.md`, `cycle_lab/README.md`, this document.

## Appendix C — Data inventory

- `SOXL_5min_6Years.csv` — primary series, IBKR 5-min RTH bars,
  2020-07-16 → 2026-07-21, unadjusted (2021-03-02 15:1 split adjusted
  in-code; verified by discontinuity scan).
- `SOXS_5min_6Years.csv` — inverse ETF, back-adjusted (V8 program).
- `SOXX_5min_6Years.csv` — sector index proxy (V10 input test).
- `FAS_5min_6Years.csv`, `SPXL_5min_*.csv`, TQQQ files — available for
  the recommended (not yet run) transfer test.
- `SOXL_Options_*.csv` — EOD option chains (used only by the demoted
  cycle strategy rounds).
- All large files via Git LFS; results CSVs in `band_lab/out/` and
  `cycle_lab/out/` are plain text for diffability.
