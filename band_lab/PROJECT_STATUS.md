# Project status — where we are, what worked, what is next

**This is the one document to read to know where the project stands.** It is a
status and planning document only. It explains *what has been done and whether
it worked*; it contains no instructions.

The instructions live in exactly one place: **[`live/RUNBOOK.md`](live/RUNBOOK.md)**
— what to type, in what order. §0M is macOS, §0 is Windows.

Last reviewed: **2026-08-06** — QA/QC pass (§4.1–4.5), the first live IBKR
sessions (§4.6), and the first transmitting session (§4.7). Every PASS in §2 is
a command that was executed, not a claim carried forward.

---

## 1. Where we are, in one table

| Phase | What it is | Status |
|---|---|---|
| Research | Find and validate the strategy | ✅ **complete** — locked 2026-07-28, `STRATEGY_SPEC.md` §0.1 |
| Re-tests (V16–V18) | Re-sweep the churn parameters on 1-minute data | ✅ **complete** — nothing adopted, strategy unchanged |
| Phase 1 | Clean-room backtest parity harness | ✅ **complete and PASSING** |
| Phase 2 · Stage 1 | Live state machine proven equal to the backtest | ✅ **complete and PASSING** |
| Phase 2 · Stages 2–4 | Broker adapter, store, orders, timetable, entrypoint | ✅ **code complete, 265 tests green**; trading against IBKR paper since 2026-08-06 |
| Phase 2 · Stage 4 acceptance | One live session, transmit OFF | 🟡 **superseded** — the dry runs never reached 11:00 and `diagnose.py` now covers what they checked. See §4.6 |
| Phase 2 · Stage 5 | Go live on paper, ≥4 weeks | 🟡 **underway — first real orders placed 2026-08-06.** Three more defects found, all fixed. See §4.7 |
| Phase 2 · Stage 6 | `report.py` — daily shadow parity | ✅ **built 2026-08-07** — 12 tests, incl. §10.16's hand-computed fixture |
| Phase 2 · Stage 7 | `risk.py`, alerting, service supervision | 🟡 **`watchdog.py` built 2026-08-07** (§6.2, 12 tests); `risk.py` and alerting still open |
| Phase 3 | Live money at reduced size | ⬜ not started |

**The step we are on: the paper run — two transmitting sessions so far, both
shakedown.** 2026-08-06 and 2026-08-07. Attended, paper account, f=1.00 and
w=0.50 per sleeve. `PHASE2_PLAN.md` Stage 5 excludes the first ~3 sessions, and
both of these carry evidence-quality flags besides, so **the usable evidence
about the strategy is still zero ON-days.**

Stage 6 (`report.py`) and the watchdog were both built on 2026-08-07, out of
plan order, because three consecutive failed closes made them the binding
constraint rather than a Phase 3 prerequisite.

**The single most important sentence in this document:** eight defects have been
found in five live sessions, and every one of them was invisible to a test suite
that is now 232 green — because all eight lived in `IBBroker`, the feature
bootstrap, or the order path against a real broker, which a `FakeIB` suite
cannot reach by construction. The most serious, found on the first transmitting
session, left **241 of 541 shares with no protective stop**.

Read that as the argument for the attended requirement and against waiving any
gate, not as an argument that the engine is unsound. Each defect was found in
the cheapest possible place: paper money, watched, with nothing at risk.

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
| 5 | Live engine unit + integration tests | ✅ **PASS** | `pytest band_lab/live` → **173 passed** (137 before this review; +36 added by §4's fixes) |
| 6 | 1-minute fill-resolution study | ✅ complete | `live/PHASE2_PARITY.md` S10–S12 — **the most consequential finding in the project**, see §3 |
| 7 | V16 / V17 / V18 re-tests | ✅ complete, **nothing adopted** | `v2_dev/` — ~1,040 parameter cells across V1, V3, V7, V10 |
| 8 | IBKR pre-flight, both sleeves | ✅ **READY** (2026-08-03 17:19 ET) | `band_lab/live/diagnose.py` — connection, capital, contracts, hours, 78 bars at idx 0..77, live data confirmed |
| 9 | Stage 4 acceptance (transmit-OFF session) | ⬜ superseded — never reached 11:00 | — |
| 10 | **First transmitting session** | ✅ **2026-08-06** — gate, 10:00 filter, 11:00 arming, entry fill, OCA bracket all observed live | §4.7 |

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
| **No exit has ever filled against IBKR** | Entry, bracket and ratchet are proven live; no target or stop has executed, and the 15:55 flatten has never run against a real position. All three `PHASE2_PLAN.md` §6 assumptions remain open — above all §6.1, that a `STP` is broker-side and survives the engine dying | next sessions |
| ~~`report.py` does not exist~~ | ✅ Built 2026-08-07. Diffs live fills against the same bars replayed through the same rules, answers both §12.3 questions, and leads with evidence-quality flags because most sessions so far have not been usable evidence | done |
| **`risk.py` does not exist** (Stage 7) | `Engine.day_loss_breached()` measures the −8.5% condition and `run.py` breaks the session loop on it, but nothing enforces a dormant-until-cleared state | Before Phase 3 |
| ~~`watchdog.py` does not exist~~ | ✅ Built 2026-08-07 after three consecutive sessions where the engine failed to flatten. Fires on a stale heartbeat (§6.2) **or** on still being exposed past 15:58 — the second trigger is the one that would have caught all three | done |
| **No alerting** | `run.py` prints to the console and writes SQLite. There is no push, email or desktop notification of any kind, despite three documents describing them | Before unattended operation |
| **No service supervision** | The engine is a foreground process started by hand. A reboot or a crash ends the trading day silently | Before unattended operation |
| ~~Paper account not confirmed~~ | ✅ Resolved: NetLiquidation **$155,803** → `sleeve_capital` **$75,000**, the size the published cost rows assume | done 2026-08-03 |

### Acceptance tests (`IMPLEMENTATION_SPEC.md` §10), actual state

| Items | Status |
|---|---|
| 1–8, 13, 14 | ✅ pass in `band_lab/phase1` |
| 9 (15:55 flatten reaches flat) | ✅ covered against `FakeIB`, ⬜ never against IBKR |
| 10 (crash/restart reconcile) | 🟡 partially — reconnect idempotency and ratchet recovery are tested; the four named crash points are not |
| 11 (disconnect → flatten) | ⬜ open — Stage 7 |
| 12 (watchdog flattens independently) | ✅ covered against `FakeIB` by `watchdog.py`, ⬜ never fired against IBKR |
| 15 (session decision log), 16 (weekly report) | ✅ covered by `report.py`, ⬜ never run on a clean session |

The spec's own §10 table still shows 9 and 10 as fully open; that is now
understated against `FakeIB`. It remains true that **none of 9–12 has completed
against a real broker** — the 2026-08-06 session proved the entry half of the
order path only.

---

## 4. QA/QC findings — the review, and five live sessions

**Eight defects, all in code, all fixed.** Two came from reading the code
(§4.1–4.2), three from first contact with IBKR (§4.6), and three from the first
transmitting session (§4.7). **None touches a §12 constant**, and `replay.py`
reports exact equivalence after all eight — every one was in live plumbing, not
in strategy arithmetic.

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

**A fifth, found the same evening.** With error 162 back (the Client Portal tab
used to *buy* the market-data subscription was itself the competing session), the
top-up returned nothing and the engine **logged the problem and carried on**,
computing ATR5 and thr80 from a CSV ending 2026-07-21. §2.2 forbids trading on
stale data and §4 requires checking the last daily bar is the prior session;
only the "unavailable" half was implemented. `features.check` now refuses the
run outright at more than 5 days of age.

The three runner tests that broke when that guard went in were the same bug in
miniature — every one drove `FakeIB` with no broker sessions against a fixture
dated 2026-08-03, so all of them had been silently two weeks stale.

**Resolved 2026-08-03 17:19 ET — `diagnose.py` returns `VERDICT: READY`:**

```
[ ok ] connected on port 7497 — PAPER
[ ok ] NetLiquidation $155,803 -> sleeve_capital $75,000
[ ok ] SOXL / SOXS qualified, session 09:30-16:00
[ ok ] bar 0 is the 09:30 bar — indices are aligned
[ ok ] engine would consume 78 bars (idx 0..77)
[ ok ] live market data confirmed
```

Both operational blockers cleared: the L1 subscription is live and shared to
paper, and no competing IBKR session holds the market-data connection. **Stage 4
is not yet met — the engine has still never reached the 11:00 arming** — but
nothing known now stands between it and a clean session.

**What this says about the test suite.** All five defects were invisible to a
green suite, because every one lived in `IBBroker` or the feature bootstrap —
the parts a `FakeIB` suite by construction cannot exercise. That is not an argument against
the suite (it caught the strategy logic, which is what it was for); it is an
argument that `diagnose.py` and the dry-run gate are load-bearing, and that
**Stage 4's acceptance must not be waived.**

### 4.7 The 2026-08-06 session — first real orders

The engine transmitted for the first time. **Three more defects, all fixed**;
none of them was reachable without live orders.

| | Defect | Consequence |
|---|---|---|
| 6 | `diagnose.py` called a pre-market run a failure | Zero bars for *today* is correct before 09:35 — it is the date filter doing its job. Run at 07:48 the pre-flight said `NOT READY` on the one line behaving properly, and the runbook says stop at the first thing that misbehaves |
| 7 | The live-data guard refused on **silence** | TWS does not reliably send a `marketDataType` callback when it is already serving what was asked for, so silence is the ordinary case. At 11:05 it stood a healthy sleeve down on a confirmed-good subscription and ended the session. Refusal is now reserved for positive evidence — the error codes, which fired correctly on 2026-08-03 when the feed really was delayed |
| **8** | **One order settled in several executions was read as several entries** | **The most serious defect in the project so far.** IBKR filled 541 shares as 300 + 210 + 31. The bracket was sized from the first execution, so **241 shares carried no stop and no target**, while the state machine believed it held 300 — a target or stop fill would have sold 300, left 241 long, and re-armed as though flat |

Defect 8 is the one to remember. §4.1 of `PHASE2_PLAN.md` anticipated partial
fills and specified "cancel the remainder, bracket what filled" — but the cancel
races the remainder executing, and on the first live entry it lost that race.
The fix stops trusting any single execution: the protective legs are now sized
from `broker.position()` after every entry execution, which is the only quantity
that cannot be wrong, and re-armed until they cover it.

Defects 6 and 7 are the same lesson from opposite directions: **a safety check
that fires on healthy days is not a safety feature.** Both refused on the
absence of evidence rather than on evidence, and both cost a session.

**What the session did prove**, none of it previously observed live:

- the gate passing both sleeves on live ATR5;
- the **10:00 morning filter firing on time**, standing SOXS down for the
  documented reason (`stand_down_wide_or_weak_pos10`);
- the 11:00 activation, the resting buy limit, and the ratchet;
- **a real entry fill, and a real OCA bracket placed against it.**

**What it did not prove**, and what the next sessions are for:

- the exit path — no target or stop has ever filled;
- the 15:55 flatten against a real position;
- all three `PHASE2_PLAN.md` §6 assumptions, still open, §6.1 above all.

One reading note for the evidence set: the entry armed at 138.60 off a 09:30
session high and filled at 133.54, because the engine was restarted at 12:26
into a market already 4.6% below that high. Correct by the rules, and not
representative — a continuous run would have entered hours earlier and higher.

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

### A2. ✅ RESOLVED 2026-08-03 — market data

Was: IBKR error **10089** on both sleeves, delayed data only. Subscribed and
shared to paper the same evening; `diagnose.py` returns `VERDICT: READY`.

- [x] Subscribe to **live US equity L1 covering NYSE Arca** (the error names
      `ARCA/TOP/ALL`; both ETFs are Arca-listed). Client Portal → Settings →
      User Settings → **Market Data Subscriptions**. Take non-professional
      status if eligible — it is materially cheaper
- [x] **Share it to the paper account** — a separate toggle under Settings →
      Account Settings → Paper Trading Account. Subscribing alone is not enough
- [x] Re-run `python band_lab/live/diagnose.py` until it says **`VERDICT: READY`**

**Run `diagnose.py` before every session anyway.** Error 162 recurred twice on
2026-08-03 — the second time because the Client Portal tab used to buy the
subscription was itself a competing session. It costs 20 seconds and it is the
difference between finding that at 08:30 and finding it at 11:00.

### B. ✅ Done — dry runs and first transmitting session

- [x] Machine, TWS, market data, pre-flight `VERDICT: READY`
- [x] Dry runs 2026-08-03 (five defects found)
- [x] **First transmit-ON session 2026-08-06** — first real orders placed
- [x] Defects 6, 7, 8 found and fixed

### C. 🔜 The next session — what to watch, in order

- [ ] **The exit path.** No target or stop has ever filled. Watch for
      `EXIT TARGET` / `EXIT STOP` with a `ret=` figure
- [ ] **§6.1 — the safety-critical one.** Once a bracket is on: confirm SELL LMT
      and SELL STP in TWS, kill the engine, **check the stop is still there**.
      If it vanishes, stop and report — nothing runs unattended until it is
      resolved
- [ ] **§6.3** — a target fill must cancel its sibling stop by itself
- [ ] **A bracket that covers the whole position.** After any entry, the stop's
      quantity in TWS must equal the position. This is defect 8's fix under
      observation on real fills for the first time
- [ ] **The 15:55 flatten** against a real position — verify flat in TWS with
      your own eyes, not just the log line
- [ ] **§6.2** — leave it overnight; confirm the 23:00 TWS restart reconciles
      without double-counting

### E. Week 1 of the paper run

- [x] **Build `report.py`** (Stage 6) — done 2026-08-07
- [ ] Answer the two S10/S11 questions from the `fills` and `quotes` tables:
      did any fill occur without the quote reaching the limit, and on same-bar
      re-entries is the achieved price at or worse than the price just sold
- [ ] Make feature staleness an automatic refusal (§4.4 item 1)

### F. Before Phase 3 (real money) — none of these is optional

- [ ] `risk.py` — the −8.5% day-loss breaker, enforced not just measured
- [x] `watchdog.py` — separate process, heartbeat → `reqGlobalCancel` + flatten
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
