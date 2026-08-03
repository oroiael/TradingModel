# Project status — where we are, what worked, what is next

**This is the one document to read to know where the project stands.** It is a
status and planning document only. It explains *what has been done and whether
it worked*; it contains no instructions.

The instructions live in exactly one place: **[`live/RUNBOOK.md`](live/RUNBOOK.md)**
— what to type, in what order, on the Windows 11 machine.

Last reviewed: **2026-08-02** (QA/QC pass, §4). Everything below was re-run from
a clean checkout during that review; every PASS in §2 is a command that was
executed, not a claim carried forward from an earlier document.

---

## 1. Where we are, in one table

| Phase | What it is | Status |
|---|---|---|
| Research | Find and validate the strategy | ✅ **complete** — locked 2026-07-28, `STRATEGY_SPEC.md` §0.1 |
| Re-tests (V16–V18) | Re-sweep the churn parameters on 1-minute data | ✅ **complete** — nothing adopted, strategy unchanged |
| Phase 1 | Clean-room backtest parity harness | ✅ **complete and PASSING** |
| Phase 2 · Stage 1 | Live state machine proven equal to the backtest | ✅ **complete and PASSING** |
| Phase 2 · Stages 2–4 | Broker adapter, store, orders, timetable, entrypoint | ✅ **code complete, 144 tests green** — but **has never connected to IBKR** |
| Phase 2 · Stage 4 acceptance | One live session, transmit OFF | 🟡 **attempted 2026-08-03 — found four defects, blocked on market data.** See §4.6 |
| Phase 2 · Stage 5 | Go live on paper, ≥4 weeks | ⬜ not started |
| Phase 2 · Stage 6 | `report.py` — daily shadow parity | ⬜ **not built** |
| Phase 2 · Stage 7 | `risk.py`, `watchdog.py`, alerting, service supervision | ⬜ **not built** |
| Phase 3 | Live money at reduced size | ⬜ not started |

**The step we are on: Phase 2, Stage 4 acceptance — one dry run.** Everything
needed for it exists and is tested. It is a launch, not a code change.

**The single most important sentence in this document:** no line of code in
`band_lab/live/` has ever exchanged a packet with IBKR. Every green test in §2
is green against `FakeIB`, an in-memory double. That is a real and useful
result — it eliminates coding error as an explanation for a live shortfall —
but it is not evidence that the engine works against a broker.

---

## 2. What was done, and whether it worked

Every row was re-run on 2026-08-02. The command is the evidence; run it and it
either exits 0 or it does not.

| # | Work | Result | How it was verified |
|---|---|---|---|
| 1 | Strategy research, V1–V15 | ✅ locked | `STRATEGY_SPEC.md` §0.1 — 12 variables, each with its own test programme |
| 2 | Phase 1 clean-room rebuild | ✅ **PASS** | `pytest band_lab/phase1` → **59 passed** |
| 3 | Phase 1 parity vs research engine | ✅ **PASS** | `band_lab/phase1/parity.py` → **exit 0**; all **16** published §8 numbers reproduce exactly |
| 4 | Live state machine equivalence | ✅ **PASS** | `band_lab/live/replay.py` → **exit 0**; SOXL 779=779 ON-days, SOXS 793=793, max daily P&L difference **0.0**, 5,118 trades with 0 outcome differences |
| 5 | Live engine unit + integration tests | ✅ **PASS** | `pytest band_lab/live` → **144 passed** (137 before this review, +7 added in §4) |
| 6 | 1-minute fill-resolution study | ✅ complete | `live/PHASE2_PARITY.md` S10–S12 — **the most consequential finding in the project**, see §3 |
| 7 | V16 / V17 / V18 re-tests | ✅ complete, **nothing adopted** | `v2_dev/` — ~1,040 parameter cells across V1, V3, V7, V10 |
| 8 | Stage 4 acceptance (transmit-OFF session) | ⬜ **NOT DONE** | — |

### What #6 changed, because it governs how the paper run is read

The 5-minute backtest priced roughly half its own edge at levels that had
already traded inside the same bar. Re-measured on 1-minute fills:

| | published (`IMPLEMENTATION_SPEC.md` §8) | 1-minute measurement | plan on |
|---|---:|---:|---:|
| SOXL | 61.9 net bp/ON-day | 42.5 gross | **~40 bp** |
| SOXS | 48.1 net bp/ON-day | 34.2 gross | **~30 bp** |

**A paper run at 20–40 bp/ON-day is the expected result, not a broken engine.**
The residual error runs one direction only (sub-minute sequencing is still
unresolved), so real fills should land *below* the 1-minute figures.

No §12 constant changed. Three re-test programmes tried and adopted nothing.

---

## 3. What is not done, and what each gap costs

| Gap | Consequence | When it must exist |
|---|---|---|
| **Nothing has talked to IBKR** | Every §6 assumption in `PHASE2_PLAN.md` is unverified — most importantly §6.1, that a `STP` order is broker-side and survives the engine dying | Stage 4 dry run |
| **`report.py` does not exist** (Stage 6) | There is no instrument to answer the S10/S11 question. Without it the paper run produces fills nobody diffs against the backtest, which is the *entire reason to launch* | Week 1 of the paper run |
| **`risk.py` does not exist** (Stage 7) | `Engine.day_loss_breached()` measures the −8.5% condition and `run.py` breaks the session loop on it, but nothing enforces a dormant-until-cleared state | Before Phase 3 |
| **`watchdog.py` does not exist** (Stage 7) | If the engine hangs while holding a position, nothing independent flattens it. On paper this risks no money; on real money it is the difference between −4% and unbounded | Before Phase 3 |
| **No alerting** | `run.py` prints to the console and writes SQLite. There is no push, email or desktop notification of any kind, despite three documents describing them | Before unattended operation |
| **No service supervision** | The engine is a foreground process started by hand. A reboot or a crash ends the trading day silently | Before unattended operation |
| **Paper account not confirmed** | `sleeve_capital = 0.50 × min(NetLiquidation, 150_000)`. If the paper account's NetLiquidation is small, `floor(f × sleeve_capital / price)` rounds to **0 shares** and the sleeve silently never trades | Before Monday |

### Acceptance tests (`IMPLEMENTATION_SPEC.md` §10), actual state

| Items | Status |
|---|---|
| 1–8, 13, 14 | ✅ pass in `band_lab/phase1` |
| 9 (15:55 flatten reaches flat) | ✅ covered against `FakeIB`, ⬜ never against IBKR |
| 10 (crash/restart reconcile) | 🟡 partially — reconnect idempotency and ratchet recovery are tested; the four named crash points are not |
| 11 (disconnect → flatten), 12 (watchdog) | ⬜ open — Stage 7 |
| 15 (session decision log), 16 (weekly report) | ⬜ open — Stage 6 |

The spec's own §10 table still shows 9 and 10 as fully open; that is now
understated. It remains true that none of 9–12 has run against a real broker.

---

## 4. QA/QC findings from the 2026-08-02 review

Two defects, both in code, both fixed here. Neither touches a §12 constant, and
`replay.py` still reports exact equivalence after both.

### 4.1 🔴 `--dry-run` would have placed real orders — **fixed**

`run.py --dry-run` sets `transmit=False`, which the runner passes to
`IBBroker(readonly=True)`. Three documents state this means "nothing reaches the
market". It did not.

`readonly` in `ib_async` is a **client-side flag only** — it skips two startup
requests (`reqOpenOrders`, `reqCompletedOrders`) and has no effect on
`placeOrder`. `OrderManager` never passed `transmit` down to the broker either;
every call used the default `transmit=True`. The only thing that would have
stopped an order was TWS's own *Read-Only API* checkbox — which `DEPLOYMENT.md`
§6 correctly tells you to switch **off**.

Following the documents exactly would therefore have sent live paper orders
during the session that exists to send none.

**Fix:** `IBBroker` now refuses to transmit while `readonly` is set. Orders are
logged as `DRY RUN — not sent: …` and given negative synthetic ids; modify and
cancel become no-ops on those ids. The whole engine path still runs, so the dry
run still produces the decision log it is for. Four new tests in
`live/tests/test_live_broker_guards.py`.

### 4.2 🔴 The bar feed could not tell today's bars from yesterday's — **fixed**

`Bar.idx` is a clock offset from 09:30 and carries no date. `BarFeed.poll`
called `historical_bars(symbol, now, "1 D", "5 mins")` and `IBBroker` discarded
the date the bars came with. If IBKR's `1 D` window reaches into the prior
session — which for a request made inside RTH is `PHASE2_PLAN.md` §6.4, an
explicitly open question — that session's 11:00–16:00 bars arrive as *today's*
afternoon once the feed sorts by index.

Started before 09:30, the feed would have consumed a whole prior session in one
poll: the morning filter evaluated on yesterday's opening range, the 11:00 limit
armed off yesterday's session high, and today's real bars then discarded as
already-seen.

**Fix:** `IBBroker.historical_bars` now returns one calendar session — the day
the request's `end` falls on. Before the open it correctly returns nothing.
`historical_sessions`, which the feature bootstrap needs, still spans days.
Three new tests.

### 4.3 🟠 Documentation defects — corrected

| Where | Problem |
|---|---|
| `DEPLOYMENT.md` §4, §12.1 | Told you to expect **58** and **115** tests; the suite has **144** |
| `DEPLOYMENT.md` §2 | `git checkout claude/band-lab-trading-strategy-plan-6zxt67` — that branch was merged and deleted; the command fails |
| `DEPLOYMENT.md` §9 | Describes a `config.local.toml`; `EngineConfig.load()` reads **JSON** and `config.local.toml` is never opened by any code |
| `DEPLOYMENT.md` §9 | Gives the database path as `live/state/engine.db`; the code default is `live/out/live.db` |
| `DEPLOYMENT.md` §10 | The runbook table promises a "push alert" at 10:00 and 15:55. No alerting of any kind is built |
| `DEPLOYMENT.md` (whole file) | Written for macOS — Homebrew, `pmset`, `launchd`, `osascript`. The paper run is on Windows 11 |
| `live/README.md`, `PHASE2_PARITY.md` | Stale test counts |

### 4.4 🟠 Open items that are judgement calls, not defects

1. **Feature staleness is never checked.** `IMPLEMENTATION_SPEC.md` §4 requires
   "last daily bar is the prior session" as a pre-trade sanity check.
   `features.check()` only verifies there are ≥120 sessions. If the broker
   top-up silently returns nothing, the engine computes ATR5 from data ending
   **2026-07-21** and trades on it without complaint. The runbook makes this a
   manual check; it should become an automatic refusal.
2. **The pre-open log line does not add up.** It prints
   `524 sessions (1510 csv + 8 broker)` — `sessions` is the trimmed 524-session
   window while `csv` is the untrimmed file count. Harmless, but it is the line
   you are asked to verify at 06:00, so it should read cleanly.
3. **`live/out/` was not gitignored.** The live SQLite database — order and fill
   history — would have shown up as an untracked file inviting a commit. Added
   to `.gitignore`.
4. **Buying power under both sleeves is still unverified.** `PHASE2_PLAN.md`
   §4.3 flagged this and it remains open: at `w=0.50, f=1.00` both sleeves in a
   position simultaneously deploy the full capital basis, and 3x ETFs carry
   elevated margin requirements.

### 4.6 The 2026-08-03 dry run — what the first contact with IBKR found

Three sessions were attempted against TWS paper. **No order was ever
transmitted** and no capital was at risk. The engine never reached the 11:00
arming, so Stage 4's acceptance is *not* met — but the day did the job a dry run
exists to do.

**Two further defects, on top of §4.1 and §4.2, neither catchable by the suite:**

| | Defect | Consequence |
|---|---|---|
| §4.1 | `--dry-run` transmitted | would have placed real orders |
| §4.2 | feed was date-blind | would have armed off yesterday's session high |
| **new** | **`assert_live_data` was a no-op** | read `ib._ccr_probe_ticker`, an attribute nothing ever set, so the `is None` branch returned on every real connection. §4's "refuse to trade on delayed data" **was not implemented**. The account was in fact on delayed data |
| **new** | **bar timestamps were not zone-normalised** | **TWS on this machine is configured for `America/Los_Angeles`.** The 09:30 ET bar arrived as `06:30`, giving `Bar.idx` = **−36**. Bar 5 (the 10:00 filter) and bar 18 (the 11:00 arming) never came up. The engine consumed every bar of the session and decided nothing, raising no error |

The second is the one to remember. A whole session ran, every bar was ingested,
and the output was **silence** — no exception, no warning, nothing in the logs to
distinguish it from a working feed. `IMPLEMENTATION_SPEC.md` §1's fifth design
priority is observability, and this is the gap it was written about.

**Confirmed fixed** by `live/diagnose.py` on the same machine: both sleeves now
report `bar 0 is the 09:30 bar`, 54 bars, idx 0..53.

**Two operational findings, not defects:**

1. **IBKR error 162** — "Trading TWS session is connected from a different IP
   address" killed every historical request in the first attempt. Cause: a
   second session was logged into the same IBKR user. IBKR serves market data to
   one location at a time. Resolved by logging out elsewhere.
2. **The blocker: IBKR error 10089 on both sleeves** — the account has **no live
   L1 entitlement for API use**; TWS offers delayed data instead. §4 makes that
   a refusal-to-trade condition, so the sleeves correctly stand down. **Phase 2
   cannot start until this is subscribed and shared to the paper account.**

**What this says about the test suite.** All four defects were invisible to 157
green tests, because every one of them lives in `IBBroker` — the single class a
`FakeIB` suite by construction cannot exercise. That is not an argument against
the suite (it caught the strategy logic, which is what it was for); it is an
argument that `diagnose.py` and the dry-run gate are load-bearing, and that
**Stage 4's acceptance must not be waived.**

### 4.5 On the strategy itself — no errors found, one observation

I did not re-test anything, as instructed. Reading for high-level and
common-sense errors, the research documents are internally consistent, the
1-minute finding is handled with unusual honesty (the harsh result was adopted
and propagated to every document that quotes a number), and the V16–V18
programmes did the hard thing — prespecifying an adoption bar and then rejecting
their own winners. Three specific things I checked and found correct: the
anti-lookahead convention in §2.6 is load-bearing and correctly stated; the
"never use historical prices for sizing" rule is real and the SOXS back-adjusted
series genuinely would zero 248 sessions; and running both sleeves long is
coherent rather than a contradiction, because the pair's diversification is
measured, not assumed.

**One observation about timing, not about the strategy.** The gate for Monday
2026-08-03 reads, from IBKR daily bars for the five sessions 2026-07-27 → 07-31:

| | ATR5 for Monday | gate (`ATR5 ≥ 6.0`) |
|---|---:|---|
| SOXL | **≈ 15.8%** | ON |
| SOXS | **≈ 17.5%** | ON |

That is roughly **2.6× the gate threshold** and far above the 6.7% median day
range in the research sample — SOXL ran a −42% drawdown and a +25% bounce inside
six sessions. Both sleeves will be ON, and the first live session lands in one of
the most volatile regimes in the dataset.

This is not an argument against launching — the money is paper, the strategy's
edge is documented to *live* in high-volatility days (`README.md` §4), and the
worst day is structurally capped at −8%. But two things follow: the first few
sessions are not a representative sample of anything, and this is exactly the
regime where the −4% stop and the 2-stop breaker get exercised, which makes it a
good test of the order path and a bad one for reading bp.

---

## 5. ✅ Next-steps checklist

Instructions for every item are in [`live/RUNBOOK.md`](live/RUNBOOK.md), section
by section. This is the ledger; that is the manual.

### A. Before Monday's open — Windows 11 machine (RUNBOOK §0, §3, §4)

Confirmed 2026-08-02: Python, TWS and the repo are **already installed**, and
the paper account will hold **$150,000** on port **7497**. RUNBOOK §1–§2 are
therefore skippable; these are not.

- [ ] 🔴 **`git pull` on the Windows box — commit `014e9b4` or later.** Without
      it `--dry-run` transmits real orders (§4.1). Nothing else on this list
      matters if this is missed
- [ ] `git lfs pull` and confirm the CSVs are 7.4 MB / 8.3 MB, not 132 bytes
- [ ] `pip install -r band_lab/live/requirements.txt` — the file changed
- [ ] **Verify the install: 4 commands, all must pass** — 59 phase1 tests,
      `parity.py` exit 0, `replay.py` exit 0, **144** live tests (not 137)
- [ ] Verify the TWS API settings: port **7497**, Read-Only API **off**,
      trusted IP 127.0.0.1, download open orders **on**, auto-restart 23:00
- [ ] **Confirm market data is live, not delayed.** This gates two things: the
      engine refuses to arm at 11:00 on delayed data, *and* the historical
      top-up in §B is a market-data request that fails without it
- [ ] Note **Available Funds** and **Buying Power** in TWS. At $150K both
      sleeves deploy 100% of equity, and 3x ETFs carry elevated margin
      requirements — `PHASE2_PLAN.md` §4.3, still open and **not testable by
      the dry run** since no orders are sent
- [ ] Stop the machine sleeping (RUNBOOK §4.7)

> **Historical data needs no manual step.** The engine tops up from the CSV
> backbone (which ends 2026-07-21 / 2026-07-24) via one paced IBKR request per
> symbol at pre-open, and polls today's bars live. RUNBOOK §4.6.

### A2. 🔴 THE BLOCKER — market data (nothing else can proceed)

Confirmed 2026-08-03 by `diagnose.py`: IBKR error **10089** on both SOXL and
SOXS. The account is entitled to delayed data only, and §4 forbids trading on it.

- [ ] Subscribe to **live US equity L1 covering NYSE Arca** (the error names
      `ARCA/TOP/ALL`; both ETFs are Arca-listed). Client Portal → Settings →
      User Settings → **Market Data Subscriptions**. Take non-professional
      status if eligible — it is materially cheaper
- [ ] **Share it to the paper account** — a separate toggle under Settings →
      Account Settings → Paper Trading Account. Subscribing alone is not enough
- [ ] **Check the live account can pay the fee.** It held **$86.78** on
      2026-08-03. Market data is billed monthly to the live account, and an
      unfundable subscription does not activate
- [ ] Re-run `python band_lab/live/diagnose.py` until it says **`VERDICT: READY`**

Do not schedule another session until that verdict is green. The engine will
stand down at 11:00 regardless, and the day will teach nothing.

### B. Monday 2026-08-03 — the dry run (RUNBOOK §5)

Transmit **OFF** all day. Nothing reaches the market.

- [ ] Start `run.py --dry-run` before 09:25 ET
- [ ] **06:00-equivalent check:** the pre-open line shows `+N broker` with
      **N > 0** — SOXL should top up **8** sessions, SOXS **5**. If N = 0 the
      features are stale to 2026-07-21 and the run is not valid
- [ ] Gate prints ON for both sleeves with ATR5 ≈ 15.8 (SOXL) / 17.5 (SOXS)
- [ ] 10:00 — filter decision is printed and written to `daily.filter_reason`
- [ ] 11:00 — the limit *would* arm; `DRY RUN — not sent:` lines appear
- [ ] **No `BAR GAP` errors all session** — a missed bar understates
      `session_high`, which is the anchor everything ratchets from
- [ ] **No bar arrives before 09:30 and no bar index repeats** — this is the
      §4.2 fix under observation on real data for the first time
- [ ] 15:55 / 16:00 — flatten and verify-flat paths run clean
- [ ] Session ends `EOD reconcile: AGREES`

### C. Monday evening — go/no-go (RUNBOOK §6)

- [ ] Compare the day's decisions against an EOD replay of the same bars
- [ ] Decide transmit ON for Tuesday. **Any unexplained item in B is a no-go**

### D. First transmit-ON session (RUNBOOK §7)

- [ ] Deliberately check the three `PHASE2_PLAN.md` §6 assumptions the first
      session answers — **§6.1 the stop survives killing the engine** (the most
      safety-critical item in the system), §6.3 OCA cancels the sibling,
      §6.2 the 23:00 restart reconciles without double-counting
- [ ] First ~3 sessions are shakedown and are excluded from the evidence set

### E. Week 1 of the paper run

- [ ] **Build `report.py`** (Stage 6). This is the highest-priority remaining
      work — without it the run generates fills nobody compares to the backtest
- [ ] Answer the two S10/S11 questions from the `fills` and `quotes` tables:
      did any fill occur without the quote reaching the limit, and on same-bar
      re-entries is the achieved price at or worse than the price just sold
- [ ] Make feature staleness an automatic refusal (§4.4 item 1)

### F. Before Phase 3 (real money) — none of these is optional

- [ ] `risk.py` — the −8.5% day-loss breaker, enforced not just measured
- [ ] `watchdog.py` — separate process, heartbeat → `reqGlobalCancel` + flatten
- [ ] Alerting (push / email / desktop) and service supervision
- [ ] Acceptance tests §10.11, §10.12, §10.15, §10.16 green
- [ ] Resolve the remaining `PHASE2_PLAN.md` §6 questions against IBKR docs
- [ ] Move alerting off public `ntfy.sh` — it would carry positions and P&L in
      clear text through a third party

---

## 6. Map of the documents — what each one is for

The complaint that prompted this review was that it is hard to tell which
document to read. This is the answer.

### Read these to *do* something

| Document | Use it when |
|---|---|
| **`PROJECT_STATUS.md`** (this file) | You want to know where the project is |
| **[`live/RUNBOOK.md`](live/RUNBOOK.md)** | You are at the keyboard and need to launch or operate the engine |

### Read these to *understand* something

| Document | What it holds |
|---|---|
| [`IMPLEMENTATION_SPEC.md`](IMPLEMENTATION_SPEC.md) | **Normative.** The exact rules (§2), the constants (§12), the acceptance tests (§10). If two documents disagree, this one wins |
| [`STRATEGY_SPEC.md`](STRATEGY_SPEC.md) | Why each of the 12 variables holds its value, and the evidence |
| [`MASTER_STRATEGY_DOCUMENT.md`](MASTER_STRATEGY_DOCUMENT.md) | The long-form narrative: mechanism, results, drawdowns, what could go wrong |
| [`README.md`](README.md) | The original 5-minute research — where the strategy came from |
| [`live/PHASE2_PLAN.md`](live/PHASE2_PLAN.md) | The build plan: stages, resolved spec gaps (§4), open IBKR questions (§6) |
| [`live/PHASE2_PARITY.md`](live/PHASE2_PARITY.md) | **The one to read before deciding how much capital this deserves.** S10–S12, the 1-minute study |
| [`live/DEPLOYMENT.md`](live/DEPLOYMENT.md) | macOS setup notes and background on TWS configuration. Superseded by `RUNBOOK.md` for the Windows machine |
| [`phase1/PHASE1_PARITY.md`](phase1/PHASE1_PARITY.md) | The eight spec ambiguities the clean-room build found, and how each was resolved |
| [`phase1/COST_MODEL.md`](phase1/COST_MODEL.md) | Commission and slippage arithmetic, by account size |
| [`v2_dev/`](v2_dev/) | The development line. **Nothing here is approved for trading** |

### Currently one directory, one job

`band_lab/phase1/` is the reference implementation and must not be modified.
`band_lab/live/` is the engine. `band_lab/v2_dev/` is research. The top level of
`band_lab/` is the original research plus the specifications.
