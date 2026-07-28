# Implementation Specification — Automated IBKR Trading System

**Status: the strategy is LOCKED. This document is a build specification,
not a research document. Do not re-derive, re-optimise, or "improve" any
parameter below — every one has been individually tested and the evidence
is in `STRATEGY_SPEC.md` and `MASTER_STRATEGY_DOCUMENT.md`. Changing a
number invalidates the validation.**

This document is written to be handed directly to an engineer as a
complete build prompt. It is self-contained: an implementer needs nothing
but this file, IBKR credentials, and the acceptance tests in §10.

**Amendment log.** Every parameter in §12 is unchanged since the strategy
was locked. The changes below are corrections to *descriptions* that did
not match the engine the numbers came from — found by the Phase 1
clean-room build (§9), which is what that phase exists to do. Each is
evidenced in `band_lab/phase1/PHASE1_PARITY.md`.

| date | § | change |
|---|---|---|
| 2026-07 | 2.1 | `thr80` recompute cadence: monthly → **daily**, matching the validated engine |
| 2026-07 | 2.6 | added the **anti-lookahead backtest convention** (no target fill on the entry bar) — previously stated only in `STRATEGY_SPEC.md` |
| 2026-07 | 8 | monitoring baselines replaced with **measured per-sleeve values**; two were wrong |
| 2026-07 | 9 | Phase 1 marked complete; the residual as-built vs validated gap recorded |

---

## 1. What you are building

A headless, always-on service that trades two ETF sleeves (SOXL and
SOXS) intraday on Interactive Brokers, independently and in parallel,
according to fixed rules, and that is **flat in cash every night without
exception**.

Design priority order — when these conflict, higher wins:

1. **Never hold a position overnight.** This is not a preference. SOXS
   lost ~100% of its value over the backtest period; the strategy is only
   safe because it never carries exposure through a close.
2. **Never exceed the daily loss structure.** Two stop-outs ends a
   sleeve's day. No exceptions, no discretion, no "one more trade."
3. **Fail to flat.** Every failure mode — disconnect, crash, bad data,
   unknown state — resolves to *no position and no working orders*.
4. **Correctness over latency.** The strategy operates on 5-minute
   granularity. Nothing here is latency-sensitive.
5. **Observability.** Every decision must be logged with the inputs that
   produced it, sufficient to reconstruct why the system did what it did.

---

## 2. The exact trading rules (normative)

Each sleeve runs the identical algorithm on **its own** price data. The
sleeves share only the account and the capital split. Neither sleeve ever
reads the other's state, prices, or signals.

### 2.1 Definitions

- `session` = US equities regular trading hours, 09:30–16:00 America/New_York.
- `bar` = 5-minute bar of the sleeve's symbol, RTH only. Bar index 0 is
  the 09:30 bar. Bar 18 is the 11:00 bar.
- `daily_range_pct(d)` = (High(d) − Low(d)) / Open(d) × 100, session values.
- `ATR5(d)` = mean of `daily_range_pct` over the **5 completed sessions
  before d**. Uses no data from day d.
- `OR30(d)` = (High − Low of 09:30–10:00 on day d) / Open(09:30) × 100.
- `OR_high`, `OR_low` = high and low of the 09:30–10:00 window.
- `pos10(d)` = (close of the 10:00 bar − OR_low) / (OR_high − OR_low).
  If OR_high == OR_low, use 0.5.
- `thr80(d)` = the 80th percentile of `OR30` over the **prior 504
  sessions** of that symbol, using only sessions strictly before d.
  Recomputed **every session**, pre-open, from the 504 sessions ending at
  d−1. Requires ≥120 prior observations; if fewer, the sleeve does not
  trade.

  > **Amended 2026-07 (Phase 1).** This clause previously specified a
  > monthly recompute held constant within the calendar month. The
  > research engine that produced every validated number in
  > `MASTER_STRATEGY_DOCUMENT.md` recomputes the threshold daily, so the
  > monthly wording described a system that was never measured. The
  > cadence is amended to daily to match the validated series exactly.
  >
  > This is a documentation correction, not a strategy change, and does
  > not require re-validation: V9 §T5 swept the refresh cadence and found
  > it immaterial (monthly/quarterly/annual all within 61–65 bp, Sharpe
  > 3.03–3.21), and the Phase 1 measurement puts daily at 65.6 bp inside
  > that band. The desk rule recorded in `V9_FILTER_TESTS.md` decision 4
  > ("monthly, confirmed robust") stands as the historical record of what
  > was tested; it is superseded here for what is to be *built*. See
  > `band_lab/phase1/PHASE1_PARITY.md` §3 S1.
- `session_high(t)` = highest traded price of the sleeve's symbol between
  09:30 and time t on the current day, inclusive of all completed bars
  before t. See §2.5 for the precise update rule.
- `E` = actual fill price of an entry.

### 2.2 Daily gate (evaluated before the open)

Trade this sleeve today only if `ATR5 ≥ 6.0`.

Additionally do not trade if: the session is a scheduled half-day
(early close); the exchange is closed; or historical data required for
ATR5/thr80 is unavailable or stale.

### 2.3 Morning filter (evaluated once, at 10:00)

Stand down for the day if **both**:
- `OR30 ≥ thr80`, and
- `pos10 < 2/3`

Otherwise proceed. (In words: a violently wide opening range only
disqualifies the day if price is *not* in the top third of that range at
10:00. Violent up-mornings are traded.)

No orders may be placed before 11:00 under any circumstance.

### 2.4 Position sizing

- `sleeve_capital` = `account_equity × w`, where **w = 0.50** for each of
  SOXL and SOXS.
- `order_qty` = `floor(f × sleeve_capital / limit_price)`, where **f =
  1.00** by default (see §2.9 for the risk dial).
- Whole shares only. If `order_qty < 1`, the sleeve does not trade.
- `sleeve_capital` is recomputed **once daily, pre-open**, from settled
  account equity. It does **not** update intraday.

### 2.5 Entry — the ratcheting resting limit

From 11:00 until the flatten time, whenever the sleeve is flat and both
counters permit:

1. Compute `anchor` = `session_high` using **only completed bars**
   (09:30 through the most recently closed bar). The currently forming
   bar is excluded.
2. Maintain a resting **BUY LIMIT** at `round_to_tick(anchor × 0.99)`.
3. On each new completed bar, recompute `anchor`. If it has risen, modify
   the order upward. **The limit price never moves down**, and the order
   is never cancelled and re-placed at a lower price.

There is no native IBKR order type for this — it is application logic.
Do **not** use IBKR's trailing-buy order, which trails the *low* and is a
different trade.

### 2.6 Exit — OCA bracket, placed immediately on fill

The instant an entry fills at price `E`, place a one-cancels-all group:

- **SELL LIMIT** at `round_to_tick(E × 1.01)` — the profit target
- **SELL STOP** at `round_to_tick(E × 0.96)` — stop-market, accept slippage

While a position is open, no entry order rests. One position at a time
per sleeve.

**Backtest convention (normative for any simulator, added 2026-07).** A
bar-granularity backtest must **not** book a target fill on the entry bar
itself. Within a bar the true price path is unknowable, so:

- on the entry bar, only the **stop** may fire (the adverse case);
- the **target** may fill from the next bar onward;
- within any bar, the stop is checked **before** the target.

This is not a strategy rule — live, the OCA is genuinely resting from the
moment of fill and may occasionally do better. It is an anti-lookahead
rule, and it is load-bearing: violating it is the exact bug documented in
`v5_corrected_rerun.py`, where a single bar with ≥1% range could set a
trigger 1% below its own high and instantly "win" off that same high.
Every validated number in this project post-dates that fix. Any
re-implementation that omits this paragraph will silently reproduce the
bug.

### 2.7 Counters and the circuit breaker

Per sleeve, reset at each session start:

- `fills` — incremented on every entry fill. **Maximum 5.**
- `stop_outs` — incremented whenever an exit occurs via the stop leg.
  **Maximum 2.**

When `fills >= 5` **or** `stop_outs >= 2`, the sleeve is done for the
day: cancel all working orders, place no more entries. If a position is
open at that moment it still runs to its bracket or the flatten.

This breaker is load-bearing — it is what converts the worst possible day
to a structural −8% (two 4% stops). It admits no discretion.

### 2.8 End of day — mandatory flatten

At **15:55** America/New_York:
1. Cancel all working orders for the sleeve.
2. If a position exists, close it with a market order (or MOC if the
   venue/timing supports it deterministically).
3. Verify flat by 16:00. If not flat, raise a **critical** alert and
   retry aggressively.

Nothing is ever carried overnight.

### 2.9 The risk dial (configuration, not logic)

`f` is a configuration value in [0.05, 1.00], default 1.00. Lower values
reduce return and drawdown near-proportionally. **`f > 1.00` must be
rejected by config validation** — leverage was tested and rejected.

`w` is configurable per sleeve, default 0.50 each, valid range
[0.375, 0.75] per the validated plateau. The two weights need not sum to
1.0; uncommitted capital simply sits in cash.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Supervisor (systemd / Docker restart=always)            │
│  ├─ IB Gateway + IBC        (auto-login, daily re-auth)  │
│  ├─ Strategy Engine         (the service you build)      │
│  │    ├─ MarketDataFeed     (5-min bars, both symbols)   │
│  │    ├─ SleeveStateMachine × 2   (SOXL, SOXS)           │
│  │    ├─ OrderManager       (idempotent, reconciling)    │
│  │    ├─ RiskGovernor       (hard limits, kill switch)   │
│  │    └─ StatePersistence   (SQLite, write-ahead)        │
│  ├─ Watchdog                (separate process, see §6)   │
│  └─ Notifier                (push/email on events)       │
└──────────────────────────────────────────────────────────┘
```

**Language/stack:** Python 3.11+, `ib_async` (maintained fork of
ib_insync) or the official `ibapi`. `ib_async` is recommended — its
event model fits this design and it handles reconnection cleanly.
SQLite for state (no server to fail). No external message broker
required.

**Hosting:** a small always-on VPS in a US-East region, or an
always-on local machine with reliable power and network. The strategy is
not latency-sensitive; it *is* uptime-sensitive between 09:30 and 16:00 ET.

**Why IB Gateway over TWS:** headless, lighter, designed for
unattended operation. IBC handles the daily restart/re-auth that IBKR
forces.

---

## 4. Data requirements

- **Live bars:** 5-minute RTH bars for SOXL and SOXS. Use
  `reqRealTimeBars` (5-second) aggregated locally to 5 minutes, or
  `reqHistoricalData` with `keepUpToDate=True`. Aggregating 5-second bars
  locally is preferred: it gives a deterministic bar-close event and
  avoids IBKR's historical-bar revisions.
- **Historical daily bars:** ≥520 sessions per symbol for ATR5 and the
  thr80 percentile. Fetch once at startup, refresh daily pre-open, cache
  in SQLite.
- **Market data subscription:** a paid IBKR US equities L1 subscription
  is required. Delayed data is **not acceptable** — the entry anchor and
  filter depend on live prices. The system must detect delayed-data mode
  and refuse to trade.
- **Sanity checks before trading each day:** last daily bar is the prior
  session; no NaNs; prices within a plausible band of the prior close
  (reject >50% moves as bad ticks pending manual review); both symbols
  present.

Note on adjusted history: SOXL and SOXS have both had splits. When
computing ATR5 and OR30 percentiles from historical data, use IBKR's
adjusted series consistently. Percentage-based measures are
split-invariant; **absolute price levels from history must never be used
for sizing or order pricing** — always use live prices. (A prior analysis
error came from exactly this: back-adjusted SOXS history implies prices
of ~$51,000, which are not tradeable.)

---

## 5. Daily state machine

Run per sleeve, independently. All times America/New_York.

| Time | Action |
|---|---|
| 06:00 | Pre-open job: refresh daily bars; compute ATR5; recompute thr80 from the 504 sessions ending yesterday; evaluate the gate; compute `sleeve_capital` from account equity; persist the decision. If gate OFF → sleeve dormant, hard interlock prevents any order today. |
| 09:30 | If gate ON: begin recording bars. **No orders.** |
| 10:00 | On close of the 10:00 bar: compute OR30 and pos10; apply the morning filter; persist ON / STAND-DOWN. If stand down → sleeve dormant for the day. |
| 10:00–11:00 | Observe only. Continue tracking `session_high`. |
| 11:00 | Activate: compute anchor from completed bars, place the resting buy limit. |
| 11:00–15:55 | On each bar close: update anchor and ratchet the limit up if needed. On fill: place the OCA bracket, increment `fills`. On exit: increment `stop_outs` if stopped, re-arm if counters permit, else cancel and go dormant. |
| 15:55 | Flatten: cancel all, market-close any position. |
| 16:00 | Verify flat. Alert if not. |
| 16:10 | Reconcile: compare internal fill records against IBKR executions; write the daily row; append to the live-vs-backtest monitoring series. |

**Restart safety:** the engine must be able to crash and restart at any
point in this timeline and resume correctly, by reading persisted state
plus querying IBKR for actual positions and open orders. On restart it
**reconciles reality first**, then resumes — it never assumes its
in-memory view is correct.

---

## 6. Safety systems (mandatory)

1. **Broker-side protective stop always resting.** Never rely on the
   engine to notice a stop level. The stop is a live order at IBKR from
   the moment of fill.
2. **Watchdog process.** A separate, minimal process that verifies the
   engine heartbeats every 30 seconds. If the heartbeat stops for >2
   minutes during RTH, the watchdog independently connects to IBKR,
   cancels all orders, and flattens all positions.
3. **Connectivity guard.** If the API connection or market data drops for
   >60 seconds while a position is open, flatten via whatever path is
   available and go dormant for the day.
4. **Daily loss circuit breaker.** If a sleeve's realised day loss exceeds
   **−8.5%** of its sleeve capital (beyond the structural worst case),
   flatten immediately, go dormant, and require manual re-enable. This
   should never fire; if it does, something is wrong with the logic or
   the fills.
5. **Order-rate limiter.** Cap modifications at a sane rate (e.g. ≤1
   modify per symbol per 5 seconds) to avoid IBKR pacing violations.
6. **Duplicate-order guard.** Every order carries a deterministic client
   ID derived from (date, sleeve, sequence). Reject any attempt to place
   a second entry while one is working or a position is open.
7. **Global kill switch.** A single command/file/endpoint that cancels
   everything, flattens everything, and holds the system dormant until
   explicitly cleared.
8. **Config validation at startup.** Reject `f > 1.0`, `w` outside
   [0.375, 0.75], any gate/filter/level parameter differing from §2, and
   any attempt to enable shorting or overnight holding.

---

## 7. Attended vs unattended operation

**Attended mode** (required for the first 3–6 months): the engine runs
the full state machine but sends a notification at the 10:00 decision and
at the 15:55 flatten confirmation. A human can hit the kill switch at any
time. Nothing waits on human input — approval is not required for the
system to act, but a human is watching.

**Unattended mode** adds: IBC-managed auto-restart and daily re-auth; the
watchdog of §6.2 running as a separate service; alerting on every state
transition and every anomaly; and a weekly automated report (§8).

The strategy is unusually well suited to unattended operation because the
worst case of "do nothing" is being flat in cash.

---

## 8. Logging, monitoring, and the live-vs-backtest check

Persist for every session, per sleeve: gate inputs (ATR5, threshold) and
decision; filter inputs (OR30, thr80, pos10) and decision; every anchor
update; every order placed/modified/cancelled with timestamps and prices;
every fill with price, quantity, and commission; counters; the flatten
result; and end-of-day P&L.

**Weekly automated comparison against backtest expectations:**

All figures below are **measured** on the research engine over the
2020-07 → 2026 sample by the Phase 1 harness, not estimated. Regenerate
with `python3 band_lab/phase1/parity.py` (section D); the raw table is
`band_lab/phase1/out/monitoring_expectations.csv`.

| metric | SOXL | SOXS |
|---|---|---|
| fills per ON day | 3.17 | 3.36 |
| ON-day rate | 52.1% of sessions | 53.1% |
| exit mix — target | 71.3% | 71.8% |
| exit mix — stop | 9.9% | 9.3% |
| exit mix — 15:55 flatten | 18.8% | 18.9% |
| gross bp per ON day | 65.6 | 57.7 |
| net bp per ON day | 61.9 | 48.1 |
| worst day | −8.00% | −8.00% |

Wide variance applies to every bp figure; a single week proves nothing.

> **Corrected 2026-07 (Phase 1).** This table previously read "target-hit
> share of exits ≈ 75–80%" and "net bp per ON day ≈ 50". Neither matched
> the engine it was meant to describe: the target share is ≈71% (≈88% if
> the 15:55 flatten is excluded, which the old wording did not say), and
> net bp differs enough between the sleeves that a single blended figure
> is not usable as a monitoring baseline. Since this section is what a
> live system gets judged against, and the rule below is to investigate
> deviations >20%, the wrong baselines would have made a correctly
> functioning system look like a 5% miss on day one.

Investigate **structural** breaks, not noise: a month where fill counts
or ON-rates deviate >20% from expectation means the market or the
execution has changed, not luck. A single bad week is expected — see
§6.3 of the master document for the weekly distribution.

---

## 9. Build phases and deliverables

**Phase 1 — Backtest parity harness. ✅ COMPLETE (2026-07).**
Re-implement the rules of §2 from this document alone, run them over the
historical 5-minute CSVs in the repository, and reproduce
`band_lab/out/v14_*.csv`. **Acceptance: daily P&L series matches the
research engine to within floating-point tolerance.**

Delivered in `band_lab/phase1/`; findings in `PHASE1_PARITY.md`. Parity
holds exactly — 787 SOXL and 801 SOXS ON-days, no day-set difference,
worst daily divergence 4.2e-16 — and all four `v14_*.csv` rebuild
identically from the clean-room series. Re-run with
`python3 band_lab/phase1/parity.py` (exit 0 == parity holds); it doubles
as a regression gate. Acceptance tests §10.1–8, 10.13 and 10.14 live in
`band_lab/phase1/test_spec_engine.py`.

The clean-room check did its job: it found eight clauses of §2 that an
implementer cannot resolve from this document's words. Six were
corrected in place (§2.1 cadence, §2.6 backtest convention, §8
baselines). Three known, deliberate differences remain between the
as-specified system and the engine that produced the validated numbers —
in each case the spec is right and the research engine simply never
implemented the rule:

| | rule | research engine | cost of adopting the spec |
|---|---|---|---|
| §2.2 | scheduled half-days OFF | trades them | −8 ON-days/sleeve; +0.4 bp SOXL, +1.2 bp SOXS |
| §2.8 | flatten at 15:55 | holds to the 16:00 close | 0 ON-days; −0.1 bp SOXL, +2.3 bp SOXS |
| §2.1 | bars addressed by clock time | addressed by file position | 0.0 bp both sleeves |

Adopting all three is worth **+0.3 bp/ON-day on SOXL and +3.5 on SOXS**
against the validated series. That is the gap the live system starts
with, and it is the number to carry into the Phase 3 comparison — not
zero.

One modelling decision was taken and should not be re-opened without
evidence: **the backtest does not model the $0.01 tick grid**, though the
live engine necessarily rounds to it (§2.5, §2.6). Modelling it is worth
+4.3 bp/ON-day on SOXL — 6.6% of the sleeve's edge, robust to rounding
direction and not a split-adjustment artifact. It is held as **unbanked
conservatism**: assume it is not there, and let Phase 2's real fills
settle it.

**Phase 2 — Paper trading.** Full engine against IBKR paper account, ≥4
weeks. Log every fill. Compare realised fills against what the backtest
assumed — this is the largest untested assumption in the entire project
and paper trading is the first real evidence about it.

**Phase 3 — Live at reduced size.** 10–20% of intended capital, 4–8
weeks. Verify commissions and slippage against the modelled 3.7 bp/day
(SOXL) and 9.6 bp/day (SOXS).

**Phase 4 — Scale.** Only if live bp/ON-day sits within the conservative
band from §6.2 of the master document. Any structural shortfall means
back to research, not "give it more time."

---

## 10. Acceptance tests

The system is not done until all pass.

**Correctness**
1. Clean-room parity with the research engine (Phase 1 above).
2. Gate arithmetic: given a fixture of 5 daily bars, ATR5 matches by hand.
3. Filter arithmetic: fixtures for OR30 above/below threshold × pos10
   above/below 2/3 — all four combinations produce the documented decision.
4. Anchor never decreases within a session, across a synthetic bar
   sequence with a rising-then-falling high.
5. No order is ever created with timestamp < 11:00.
6. Bracket is placed within one event loop of the entry fill.

**Risk**
7. After the 2nd stop-out, no further entry order is placed that session.
8. After the 5th fill, no further entry order is placed that session.
9. At 15:55 with an open position, the position is closed and all orders
   cancelled; assert flat before 16:00.
10. Simulated engine crash at each of: pre-open, 10:05, mid-position,
    15:54 — on restart the system reconciles with IBKR and reaches a
    correct state, and never opens a duplicate position.
11. Simulated API disconnect while in a position → flatten path executes.
12. Watchdog kills a hung engine and flattens independently.
13. Config with `f = 1.5` is rejected at startup.
14. A day where the gate is OFF produces zero orders under all conditions.

**Operational**
15. Full session replay from recorded market data produces a complete,
    auditable decision log.
16. Weekly report generates and matches hand-computed values on a
    fixture week.

---

## 11. Explicit non-goals — do not build these

- No shorting, in any form, including via inverse instruments beyond the
  SOXS sleeve as specified. (Mirror-signal shorting was tested and lost
  money under honest fills.)
- No overnight positions, no pre-market or after-hours trading.
- No options, no leverage, no margin beyond settlement convenience.
- No pyramiding or scaling into positions — withdrawn after testing.
- No de-risking after losing days — tested and rejected; post-loss days
  are the strategy's best days.
- No adaptive/volatility-scaled entry or target levels — tested and
  rejected.
- No profit-sweep logic in the trading engine. If capital is withdrawn,
  it is done outside the system, between sessions.
- No parameter optimisation, auto-tuning, or machine learning of any
  kind. The parameters are fixed by validation and must be changed only
  by a deliberate, documented, re-validated decision.
- No additional instruments. SPXL, FAS and TQQQ were evaluated; none is
  adopted (§9 of the master document).

---

## 12. Reference constants (single source of truth)

```python
SLEEVES        = ["SOXL", "SOXS"]
W_PER_SLEEVE   = 0.50          # capital weight, valid [0.375, 0.75]
F_SIZE         = 1.00          # risk dial, valid (0, 1.00]; >1.0 rejected
GATE_ATR5_MIN  = 6.0           # percent
ATR_LOOKBACK   = 5             # sessions
OR_WINDOW      = ("09:30", "10:00")
OR_PCTL        = 0.80          # trailing threshold percentile
OR_PCTL_WINDOW = 504           # sessions
OR_PCTL_MINOBS = 120
POS10_TOP_THIRD= 2.0 / 3.0
START_TIME     = "11:00"
DIP_PCT        = 0.01          # entry = anchor * (1 - DIP_PCT)
TARGET_PCT     = 0.01          # exit  = E * (1 + TARGET_PCT)
STOP_PCT       = 0.04          # exit  = E * (1 - STOP_PCT), ABSOLUTE
MAX_FILLS      = 5
MAX_STOPS      = 2
FLATTEN_TIME   = "15:55"
HARD_FLAT_BY   = "16:00"
DAY_LOSS_KILL  = -0.085        # fraction of sleeve capital
TIMEZONE       = "America/New_York"
```

Any deviation from these values is a strategy change, not a
configuration change, and requires re-validation through the protocol
described in `MASTER_STRATEGY_DOCUMENT.md` §5.
