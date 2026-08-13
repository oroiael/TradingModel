# Phase 2 — Live Engine Build Plan (IBKR TWS paper)

Phase 2 of `band_lab/IMPLEMENTATION_SPEC.md` §9: run the full engine against
an IBKR **paper** account for ≥4 weeks and log every fill.

**The strategy is LOCKED.** Nothing in this plan changes a parameter. Where
§2 of the implementation spec is silent, the gap is resolved here explicitly
(§4) rather than decided silently in code — the discipline Phase 1
established.

Status: **plan, awaiting sign-off to start Stage 1.**

---

## 1. What this run can and cannot establish

Worth stating up front, because it decides how much engineering is
justified before launch.

IBKR's paper account produces fills from a simulator, not from a market. It
does not model queue position, and a resting limit is understood to fill
when the market trades at or through it — which is close to the backtest's
own assumption (`STRATEGY_SPEC.md` A1). **If that is right, paper trading
cannot validate A1**, the assumption `IMPLEMENTATION_SPEC.md` §9 calls the
largest untested item in the project; it will largely confirm the backtest
by construction. This is on the verification list in §6 and is measurable in
week 1: log the quoted bid/ask at every fill and check whether any fill
occurs without the quote reaching the limit.

**What this run does establish:**

| | |
|---|---|
| decision correctness on live data | gate, filter, `thr80` continuity against the historical series, bar alignment, session-high tracking |
| order lifecycle end to end | ratchet modifies, OCA behaviour, partial fills, counters, and the 15:55 flatten actually reaching flat |
| operational survival | the 23:00 TWS restart, reconnects, reconciliation, 24/7 uptime |
| **real quoted spreads at real order events** | the one cost input `phase1/COST_MODEL.md` §7.4 says no further analysis can supply, and where all the SOXS cost uncertainty lives (7.3 bp of range vs SOXL's 2.3) |

So: a plumbing and cost-data run. Fill realism is settled in Phase 3, at
reduced size, with real money.

The engine is also only ON ~52% of sessions, so four weeks yields ~10–11
ON-days per sleeve. Calendar time is the scarce resource here, which argues
against any pre-launch step that does not remove a specific ambiguity from
the evidence.

---

## 2. Configuration (decided 2026-07-31)

| # | Item | Decision |
|---|---|---|
| 1 | Broker process | **TWS**, paper, auto-restart **23:00 ET**. Adapter is port-agnostic so IB Gateway + IBC remains a config change, not a rewrite. |
| 2 | Market data | Live L1 shared to the paper account. Engine asserts non-delayed and refuses to trade otherwise (§4 of the spec). |
| 3 | Capital basis | `capital_basis = min(NetLiquidation, 150_000)`; `sleeve_capital = 0.50 × capital_basis` ⇒ **$75,000 per sleeve**. The $1 order minimum does not bind at this size, so the published cost rows still apply. |
| 4 | Sleeves | **Both** SOXL and SOXS, from day one. |
| 5 | Risk dial | **f = 1.00** (matches every validated figure). |
| 6 | Partial fills | Proposal in §4.1 adopted. |
| 7 | Alerting | email + push + desktop. |
| 8 | Scope | New code in `band_lab/live/`; `band_lab/phase1/` untouched as the reference. |

Still needed, not blocking Stage 1: host OS (selects the desktop notifier
and the service manager — launchd / Task Scheduler / systemd), SMTP
credentials, and the push service (Pushover key or ntfy topic).

---

## 3. Architecture

Single process, single IB connection, two independent sleeve state machines,
plus a separate watchdog process (built during the run, §5).

```
band_lab/live/
  config.py          # runtime config; delegates to phase1/spec_constants.validate_config
  strategy_core.py   # PURE strategy: gate, filter, anchor/ratchet, bracket levels,
                     #   counters, flatten. No IBKR, no I/O, no clock.
  sleeve.py          # SleeveStateMachine: drives strategy_core off (bar, clock, broker event)
  broker.py          # ib_async adapter: connect/reconnect, contracts, trading hours,
                     #   market-data-type assertion, historical bootstrap, bar feed
  orders.py          # OrderManager: deterministic orderRef, ratchet-modify, OCA, flatten,
                     #   rate limit, duplicate guard, reconciliation
  store.py           # SQLite (WAL): bars, decisions, orders, fills, quotes, counters, daily rows
  engine.py          # scheduler / event loop — the §5 timetable
  replay.py          # offline driver: historical bars -> the LIVE state machine
  report.py          # 16:10 reconcile + shadow parity; weekly §8 report
  risk.py            # day-loss breaker, connectivity guard, kill switch   (Stage 7)
  watchdog.py        # separate process: heartbeat -> reqGlobalCancel + flatten (Stage 7)
  tests/
```

**The load-bearing decision:** `strategy_core.py` is the only place strategy
logic exists, and it is proven equivalent to `phase1/spec_engine.py` by
replaying the historical bars through the live state machine (Stage 1).
Without that proof, a live shortfall cannot be attributed — a fill-assumption
failure and a mis-coded ratchet produce equally plausible logs, and no amount
of live data separates them.

Second design decision, which removes a whole class of tests: **reconciliation
from the broker is the only way state is ever established**, on every connect.
There is then no distinct "restart path" to test, because every path is the
restart path. This matters because TWS drops the API nightly at 23:00.

---

## 4. Specification gaps resolved here

§2 of the implementation spec does not address these. Each is recorded as a
decision, not an improvement; none changes a §12 constant.

### 4.1 Partial fills (agreed)

On the first execution against an entry order: **immediately cancel the
remaining quantity, bracket the actual filled quantity, and count it as one
fill.** Rationale: preserves "one position at a time" (§2.6), keeps `fills`
bounded at 5 (§2.7), and is the closest live analogue to the backtest's
all-or-nothing model. A partially filled exit leg leaves the OCA sibling
holding the residual quantity — the OrderManager reconciles bracket
quantities against the actual position after every execution.

### 4.2 `account_equity`

NetLiquidation (USD), sampled once by the 06:00 pre-open job and frozen for
the session — §2.4 states sleeve capital does not update intraday.

### 4.3 Sleeve independence under a shared account

With w=0.50 and f=1.00, both sleeves in a position simultaneously deploys the
full basis. A pre-order buying-power check is required, and **neither sleeve
may size beyond its own w share** — otherwise the sleeves become coupled,
which §2 forbids ("Neither sleeve ever reads the other's state"). Leveraged
ETFs carry elevated margin requirements; to be verified against the paper
account, not assumed.

### 4.4 Historical features are stored as percentages only

`range_pct` and `or30` only — never historical prices. This follows §4's
warning directly and the Phase 1 S7 finding: SOXS's back-adjusted series runs
to $1.17M/share and silently zeroes 248 sessions if sizing touches it.

### 4.5 Ordering rules that are easy to get backwards

- The **anchor updates only on completed bars** (§2.5.1) — an intrabar new
  high must not raise the limit until that bar closes.
- The **re-arm after an exit is immediate**, on the exit event, not at the
  next bar close. V2 measures instant re-entry below the standing session
  high at **+47.9 bp of the 65.6 bp total** — this is most of the edge.
- The entry limit **never moves down**, after rounding as well as before.
- All orders `tif=DAY`, `outsideRth=False` — belt and braces on the
  flat-overnight guarantee.

### 4.6 The 15:50–15:55 entry window

Per §2.5 the entry rests until the flatten, and the backtest books such
fills and exits them at 15:55 — so a 15:54 fill is market-flattened a minute
later, paying a crossing spread for almost nothing. It is inside the
validated numbers, so it is kept and measured, not "improved".

### 4.7 15:55 flatten uses MKT, not MOC

§2.8 permits either; MOC has a submission cutoff that makes it
non-deterministic at 15:55 (to be confirmed, §6). Residual quantity is
re-sent until flat, with a critical alert if not flat by 16:00.

---

## 5. Stages

**~4–5 working days to the first live paper order.** Safety systems and
reporting are built during the run, since on a paper account they protect no
capital — but they are all complete before Phase 3.

| Stage | Work | Acceptance |
|---|---|---|
| **0** | Local venv (3.11+), `ib_async`, pandas/numpy/pytest. TWS paper: API on, port, trusted IP 127.0.0.1, Read-Only **off**, auto-restart 23:00, memory raised. `git lfs pull` the two 5-min CSVs. | `python3 band_lab/phase1/parity.py` exits 0 locally. |
| **1** | `strategy_core.py`, `sleeve.py`, `replay.py`. | Replaying the historical bars through the **live** state machine reproduces `spec_engine` under `SPEC_LITERAL` exactly: same ON/OFF day set, same fills, same entry/exit prices, same daily P&L. |
| **2** | `broker.py`, `store.py`. Connection lifecycle + reconnect; contract qualification; **live-vs-delayed assertion**; today's session hours from contract details (half-day ⇒ OFF); historical bootstrap; 5-minute bar feed with a periodic cross-check against a historical fetch. | OR30 recomputed from IBKR-fetched bars matches the repo CSV series over an overlap window; `thr80` continuous across the seam. A missed bar understates `session_high`, which is the anchor — gap detection is not optional. |
| **3** | `orders.py`. Deterministic `orderRef` = (date, sleeve, role, sequence); ratchet-modify; OCA on fill; immediate re-arm; flatten; rate limiter; duplicate guard; reconcile-on-connect. | Ratchet invariant asserted in code and test; counters reconstructible from IBKR executions alone. |
| **4** | `engine.py` — the §5 timetable; decision + fill + quote logging. | One live session run with transmit **off**: decisions logged and matching an EOD `spec_engine` replay of the same day's bars. Half a day, not a week. |
| **5** | **Go live on paper.** | First order placed. First ~3 sessions treated as shakedown and excluded from the evidence set. |
| **6** | `report.py` — 16:10 reconcile + daily shadow-parity (live fills vs what the backtest books on the same bars); weekly report vs §8 baselines. | Weekly report matches hand-computed values on a fixture week (§10.16). |
| **7** | `risk.py`, `watchdog.py`, alerting, service supervision, §10.9–12 tests against a `FakeIB`. | All 16 acceptance tests green before Phase 3. |

### Dropped from the first draft of this plan, deliberately

- **A standalone observe-only week.** It costs ~a fifth of the run's ON-days
  to buy what the day-one shadow comparison gives anyway.
- **The FakeIB crash/disconnect matrix as a prerequisite.** Real disconnects
  will occur nightly; the reconcile-only design (§3) removes most of the
  surface. Built in Stage 7, before real money.
- **Watchdog and the −8.5% day-loss breaker as prerequisites.** They protect
  capital that is not at risk here. Stage 7.

---

## 6. To verify against IBKR documentation before Stage 2

Outbound access to `interactivebrokers.github.io` is blocked from the build
environment, so these are open questions rather than guesses. In a system
whose first design priority is "fail to flat", they get confirmed, not
assumed.

> **Update 2026-08-12.** The official docs are now committed at
> `TWS API/TWS Documentation - Copy Paste from Online.pdf` and were searched
> for §6.1. They settle the *mechanism* for asking the question and nothing
> about the answer:
>
> | | |
> |---|---|
> | `reqAllOpenOrders` (p84) | "Requests **all current open orders in associated accounts** at the current moment." The cross-client request — what a probe must use |
> | `reqOpenOrders` (p86) | "Requests all open orders **placed by this specific API client** (identified by the API client id)." The wrong one: a separate probe client would read its own empty book and report "no stop" |
>
> **Order persistence across a client disconnect is not documented.** Every
> mention of disconnection (pp. 21, 22, 46, 80, 93) is about connectivity
> errors or `eDisconnect`'s socket semantics; none addresses whether a resting
> order outlives the client that placed it. §6.1 therefore cannot be closed by
> citation and needs an experiment.
>
> `verify_stp.py` is that experiment, and `RUNBOOK.md` §7.5 is the procedure.
> It snapshots the broker from a separate API client before and after the
> engine is killed and writes a JSON verdict, so the answer lands in the repo
> instead of in somebody's memory of what TWS looked like.

1. **Stop orders on US stocks** — IB-simulated vs native, default trigger
   method, and whether they survive a TWS restart and an API client
   disconnect. Most safety-critical: §6.1 requires a broker-side stop that
   outlives the engine.
2. **TWS auto-restart** — behaviour at 23:00, whether a weekly manual
   re-login is still required, API order retention across the restart, and
   the "auto-cancel orders on API disconnect" setting.
3. **OCA semantics** — `ocaType` 1/2/3 on partial fills; whether groups
   survive a disconnect.
4. **Historical data** — duration limits and pacing for 5-minute bars
   (drives bootstrap chunking).
5. **`reqRealTimeBars`** — whether a bar is emitted every 5s with no trades;
   RTH behaviour.
6. **MOC cutoff** for US stocks (§4.7).
7. **Paper fill simulation** — the §1 question.

---

## 7. Baselines this run is measured against

From `IMPLEMENTATION_SPEC.md` §8 (measured, machine-checked by
`phase1/parity.py`):

| metric | SOXL | SOXS |
|---|---|---|
| fills per ON day | 3.17 | 3.36 |
| ON-day rate | 52.1% | 53.1% |
| exit mix — target / stop / 15:55 flatten | 71.3 / 9.9 / 18.8% | 71.8 / 9.3 / 18.9% |
| net bp per ON day | 61.9 | 48.1 |
| worst day | −8.00% | −8.00% |

> **AMENDED 2026-08 — these are upper bounds.** `PHASE2_PARITY.md` S11
> re-ran the locked config on 1-minute fill data: **SOXL 42.5 bp/ON-day
> (64% of the 5-minute figure) and SOXS 34.2 (54%)**. Plan on **~40 net
> bp/ON-day for SOXL and ~30 for SOXS**; a paper run at 20–40 bp is
> consistent with the evidence and is not, on its own, a broken engine.
> The 4-week / ~10–11 ON-day sample size below applies with even more force
> against the wider uncertainty.

**The live system does not start at parity with these, and should not be
expected to.** `phase1/PHASE1_PARITY.md` §4: adopting the spec's four
residual rules is worth **+0.3 bp/ON-day on SOXL and +3.5 on SOXS** against
the validated series, and the unmodelled tick grid is a further ~+3–4 bp of
unbanked conservatism on SOXL. Those are the comparison baselines — not zero.

Wide variance applies to every bp figure; a single week proves nothing.
Investigate structural breaks (>20% for a month on fill counts or ON-rates),
not noise.

---

## 8. Non-goals for Phase 2

Everything in `IMPLEMENTATION_SPEC.md` §11, plus: no dynamic capital rule
(V14 measured it; the spec adopts static w=0.50), no parameter changes, and
no modification of `band_lab/phase1/`, which stays as the reference the live
engine is proven against.
