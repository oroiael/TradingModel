# Runbook — macOS · the development machine, and the backup trader

**Instructions only.** What to type, in what order, and what you should see.
The reasoning lives in [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) and the
documents it maps; the normative rules live in
[`../IMPLEMENTATION_SPEC.md`](../IMPLEMENTATION_SPEC.md).

This machine is for **coding, research and verification**, and is the **backup
trading environment** if the Windows box is unavailable. The Windows box is the
primary — see [`RUNBOOK_WINDOWS.md`](RUNBOOK_WINDOWS.md).

Three rules while working through this:

1. **Do the sections in order.** Each one assumes the previous one passed.
2. **Stop at the first step that does not behave as described.** Do not work
   around it. Every check here exists because something went silently wrong
   underneath it at least once.
3. 🔴 **Only one machine may be logged into IBKR at a time.** A second TWS, the
   mobile app, or even a Client Portal browser tab produces **error 162** and
   silently kills the bar feed on the other machine. **Never open TWS here while
   the Windows box is trading.** Full failover procedure in
   [§G](#g--failover--taking-over-trading-from-the-windows-box).

All times are **America/New_York (ET)**.
**The paper port is 7497** — everywhere in this document, without exception.
7496 and 4001 are live-money ports and `EngineConfig.validate()` refuses them.

Shell is **bash/zsh**. Substitute your repo location for **`~/TradingModel`**
throughout. Python is invoked as **`python3`**.

| Section | Use it when |
|---|---|
| [§A](#a--what-this-machine-is-for) | Deciding whether you are on the right box |
| [§B](#b--where-am-i-run-this-first) | You are not sure what is installed |
| [§C](#c--one-time-machine-setup) | Filling the gaps §B found |
| [§D](#d--verify-the-install--the-regression-gate) | Before any code change lands, and before any session |
| [§E](#e--execute-every-stage-in-order) | Running every file in the project, stage by stage |
| [§F](#f--the-coding-loop) | Day-to-day development |
| [§G](#g--failover--taking-over-trading-from-the-windows-box) | 🔴 The Windows box is down and the market opens |
| [§H](#h--the-in-session-checks) | This machine is trading |
| [§I](#i--close-out-and-evidence) | 15:55–16:10 |
| [§J](#j--stopping-restarting-emergency) | Something needs to stop |
| [§K](#k--troubleshooting) | Something errored |
| [§L](#l--command-index--every-runnable-file) | You want the one command for one file |

---

# §A · What this machine is for

| | macOS (this box) | Windows 11 |
|---|---|---|
| Role | **Coding, research, verification. Backup trader** | Primary trading environment |
| Runs the test suites | **Yes, constantly** | Yes, as the pre-session gate |
| Runs the research + parity harnesses | **Yes — this is the machine for it** | Occasionally |
| Runs `run.py --dry-run` | Yes, freely | Yes |
| Runs `run.py --transmit` | **Only during a failover** (§G) | **Yes — this is the machine** |
| TWS open | **Only during a failover** | During the session, exclusively |

Everything that is a *decision* rather than a command — the TWS settings, the
timeline, the in-session checks, the troubleshooting — is identical on both
machines. Only the shell syntax, the paths and the power management differ.

---

# §B · Where am I? Run this first

```bash
cd ~/TradingModel || cd ~/Documents/TradingModel || echo "FIND THE REPO FIRST"
pwd
python3 --version                                   # need 3.11+
git rev-parse --short HEAD                          # which commit
git log --oneline -1
git lfs version                                     # must not error
ls -lh SOXL_5min_6Years.csv SOXS_5min_6Years.csv    # must be MB, not 132B
ls -lh SOXL_1min.csv SOXS_1min.csv                  # only for the S10/S11 study
ls -d .venv-live 2>/dev/null || echo "NO VENV"
```

That one block answers every setup question at once. Anything that errors or
looks wrong is a step in §C; anything already fine is a step to skip.

You need commit **`014e9b4`** or later. **Without it, `--dry-run` places real
orders** — `readonly` in `ib_async` never stopped `placeOrder`, and the guard
that makes a dry run actually dry did not exist until 2026-08-02.

---

# §C · One-time machine setup

### C.1 Fill the gaps

```bash
# only what §B said was missing
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12 git-lfs
git lfs install
```

### C.2 Code and data

```bash
cd ~/TradingModel
git checkout main && git pull
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv,SOXL_1min.csv,SOXS_1min.csv"
ls -lh SOXL_5min_6Years.csv SOXS_5min_6Years.csv SOXL_1min.csv SOXS_1min.csv
```

**The 5-minute CSVs must be ~7.4 MB and ~8.3 MB.** At 132 bytes they are still
Git LFS pointers and nothing downstream works. The two 1-minute files are needed
only for the S10/S11 study (§E.4) and the `v2_dev` re-tests (§E.2).

Everything in the repo root is LFS-tracked by default (`.gitattributes`:
`*.csv filter=lfs`), so the same applies to any other price file a research
script asks for — `SOXX_5min_6Years.csv`, `SPXL_5min_6Years.csv`,
`FAS_5min_6Years.csv`. Pull them the same way when a script needs one.

### C.3 The Python environment

```bash
cd ~/TradingModel
python3 -m venv .venv-live
source .venv-live/bin/activate
pip install -U pip
pip install -r band_lab/live/requirements.txt
```

That installs `pandas`, `numpy`, `pytest`, `ib_async`, `requests` and `tzdata`.
The prompt should now start with `(.venv-live)`. **Every command in this
document assumes the venv is active.**

### C.4 Stop the Mac sleeping

Only needed when this machine is trading (§G), but harmless to set now:

```bash
sudo pmset -c sleep 0 disksleep 0 displaysleep 10
pmset -g custom          # verify
```

Locking the screen is fine — the process keeps running. **Closing the Terminal
window kills it**, and so does logging out.

### C.5 TWS — install now, log in only when trading

Install Trader Workstation from interactivebrokers.com. **Do not log in while
the Windows box is trading** (rule 3). When you do, the settings are identical
to the Windows box; on macOS they are under **TWS → Settings**, or
**File → Global Configuration** on older builds:

| Setting | Value |
|---|---|
| Enable ActiveX and Socket Clients | **ON** |
| Socket port | **7497** |
| Trusted IPs | **127.0.0.1** |
| Read-Only API | **OFF** |
| Download open orders on connection | **ON** |
| Create API message log file | **ON** |
| Master API client ID | leave blank |
| API → Precautions | tick every "Bypass … for API orders" box |
| Configuration → Lock and Exit → Auto restart | **23:00** |
| Never lock Trader Workstation | ON |

Market data entitlement is **account-level, not machine-level**, so the
subscription already shared to the paper account carries over to this machine
with nothing to re-buy. What does *not* carry over is the one-connection limit —
see rule 3.

### C.6 Keep session logs out of git

The launch commands below write to `~/TradingModel/logs/`. That directory is
gitignored — leave it that way. Session logs carry account balances, share
counts and fill prices.

---

# §D · Verify the install — the regression gate

**Run this whole block before any change lands, and before any session.**

```bash
cd ~/TradingModel
source .venv-live/bin/activate

python3 -m pytest band_lab/phase1 -q
python3 band_lab/phase1/parity.py  ; echo "exit=$?"
python3 band_lab/live/replay.py    ; echo "exit=$?"
python3 -m pytest band_lab/live -q
```

Expected, exactly:

| Command | Must show | Time |
|---|---|---|
| `pytest band_lab/phase1` | `59 passed` — a fixed invariant | ~1 min |
| `parity.py` | a table ending in the §8 numbers, then `exit=0` | ~2 min |
| `replay.py` | `STAGE 1 EQUIVALENCE: PASS`, then `exit=0` | ~1 min |
| `pytest band_lab/live` | all pass, **0 failures** | ~1 min |

**Do not memorise the live count — `0 failures` is the gate.** For orientation
only: `PROJECT_STATUS.md` recorded **173** at the 2026-08-06 review (59 + 173 =
the 232 it quotes), and `watchdog.py` added 12 the next day. The number grows
with every fix; the commit hash is the real version check.

Anything other than the above — a failure, a different phase1 count, a non-zero
exit — is a stop.

---

# §E · Execute every stage, in order

Everything the project can run, grouped by the stage it belongs to. **This is
the machine to run §E.1–§E.4 on** — they are offline, CPU-bound and need no
broker. §E.5 and §E.6 need TWS and therefore the failover rule.

All commands assume:

```bash
cd ~/TradingModel
source .venv-live/bin/activate
```

| Stage | What it is | Status | Section |
|---|---|---|---|
| Research | Find and validate the strategy | ✅ complete, locked 2026-07-28 | §E.1 |
| Re-tests V16–V18 | Re-sweep churn parameters on 1-minute data | ✅ complete, **nothing adopted** | §E.2 |
| Phase 1 | Clean-room backtest parity harness | ✅ complete, passing | §E.3 |
| Phase 2 · Stage 1 | Live state machine == the backtest | ✅ complete, passing | §E.4 |
| Phase 2 · Stages 2–4 | Broker, store, orders, timetable, entrypoint | ✅ code complete | §E.5 |
| Phase 2 · Stage 5 | Paper run, ≥4 weeks | 🟡 **underway on Windows** | §E.6 |
| Phase 2 · Stages 6–7 | `report.py`, `risk.py`, alerting | ⬜ **not built** | §E.7 |

## E.1 Research — the original 5-minute programme

Outputs land in `band_lab/out/`. Needs the two 5-minute CSVs only. Run in this
order; the later scripts import helpers from the earlier ones.

```bash
# the three README scripts, in order
python3 band_lab/band_analysis.py        # band stats, excursions, the failing control fade
python3 band_lab/churn_harvest.py        # dip-buy harvester grid (params x filters)
python3 band_lab/regime_gate.py          # the ATR5 volatility gate on the best configs
```

Then the twelve variable programmes, V1–V15. Each one is the evidence behind one
locked constant in `IMPLEMENTATION_SPEC.md` §12, and each has a matching
`V*_TESTS.md` next to it:

```bash
python3 band_lab/v1v3_adaptive_tests.py      # V1 dip %, V3 target %
python3 band_lab/v2_anchor_tests.py          # V2 the ratchet anchor
python3 band_lab/v5_start_time_tests.py      # V5 start time
python3 band_lab/v5_corrected_rerun.py       # V5 corrected — defines sim_trades_fixed, used by V9+
python3 band_lab/v6_eod_exit_tests.py        # V6 the 15:55 exit
python3 band_lab/v8_direction_tests.py       # V8 SOXS as a second sleeve   [needs SOXS_5min_6Years.csv]
python3 band_lab/v9_filter_tests.py          # V9 the 10:00 morning filter
python3 band_lab/v10_gate_tests.py           # V10 the ATR5 gate level      [needs SOXX_5min_6Years.csv]
python3 band_lab/v11_sizing_tests.py         # V11 sizing and 3x margin
python3 band_lab/v13_streak_tests.py         # V13 the 2-stop breaker
python3 band_lab/v14_pair_protocol.py        # V14 the pair protocol — prespecified adoption bar
python3 band_lab/v15_weekly_sweep.py         # V15 weekly stability
```

And the supporting studies:

```bash
python3 band_lab/cap_sweep.py                # capital-cap sensitivity
python3 band_lab/sizing_verification.py      # sizing arithmetic, independently
python3 band_lab/etf_scaling_test.py         # does it transfer to FAS?      [needs FAS_5min_6Years.csv]
python3 band_lab/spxl_scaling_test.py        # ... and SPXL?                 [needs SPXL_5min_6Years.csv]
python3 band_lab/transfer_test.py            # cross-symbol transfer
python3 band_lab/put_overlay_test.py         # a put overlay on the sleeve
python3 band_lab/walk_forward_and_combo.py   # walk-forward + the combined $150K backtest
```

> These are one-off. Nothing in the trading path reads `band_lab/out/`.

## E.2 Re-tests V16–V18 — the v2.0-dev line

**Nothing in `v2_dev/` is approved for trading.** It re-swept ~1,040 parameter
cells on the 1-minute data and adopted nothing; the strategy is unchanged. The
discipline it operates under is in `v2_dev/README.md` and is worth reading
before adding to it: the adoption bar is written down *before* the test runs, a
fixed small number of variables per programme, walk-forward not full-sample, and
**one engine** — the research harness drives `band_lab/live/sleeve.py` rather
than forking it.

Needs **`SOXL_1min.csv` and `SOXS_1min.csv`** (§C.2). Outputs go to
`band_lab/v2_dev/out/`.

```bash
python3 band_lab/v2_dev/churn_joint_test.py --quick   # V16 joint dip/target, coarse grid
python3 band_lab/v2_dev/churn_joint_test.py           # V16 full grid + walk-forward
python3 band_lab/v2_dev/trade_cap_test.py             # V17 the 5-trade cap
python3 band_lab/v2_dev/vol_gate_test.py              # V18 the ATR5 gate, re-measured
```

Each accepts `--out <dir>` if you want the CSVs somewhere else.

## E.3 Phase 1 — the clean-room parity harness

`band_lab/phase1/` is the reference implementation. **It must not be modified.**

```bash
python3 -m pytest band_lab/phase1 -q          # 59 passed — a fixed invariant
python3 band_lab/phase1/parity.py             # all 16 published §8 numbers, exit 0   (~2 min)
python3 band_lab/phase1/parity.py --skip-delta   # faster; skips the delta table
python3 band_lab/phase1/cost_model.py         # commission + slippage tables by account size
```

`parity.py --tol <float>` changes the comparison tolerance; the default `1e-12`
is what the published claim rests on. Do not loosen it to make it pass.

## E.4 Phase 2 · Stage 1 — the live state machine, offline

`replay.py` drives the *live* sleeve state machine over the full 6-year history
and compares it to the phase1 engine, decision by decision. **This is the gate
that catches a strategy change hidden inside a refactor** — run it after every
change to `strategy_core.py`, `sleeve.py` or anything they touch.

```bash
python3 band_lab/live/replay.py                  # STAGE 1 EQUIVALENCE: PASS, exit 0   (~1 min)
python3 band_lab/live/replay.py --sizing         # the S9 sizing-basis difference
python3 band_lab/live/replay.py --fill-models    # the S10 same-bar re-entry sensitivity
```

The 1-minute fill-resolution study — **the most consequential finding in the
project** (`PHASE2_PARITY.md` S10–S12):

```bash
for S in SOXL SOXS; do
  python3 band_lab/live/intrabar.py --symbol $S --check --start 2022-01-01   # data sanity first
  python3 band_lab/live/intrabar.py --symbol $S --start 2022-01-01
done
```

Expect **42.5 bp/ON-day on SOXL and 34.2 on SOXS**, against 66.8 / 63.0 at
5-minute resolution. **That is why you plan on ~40 bp and ~30 bp, not §8's
61.9 / 48.1.** `--path` points at a different CSV, `--force` overrides the
split-adjustment heuristic.

Rebuilding the 1-minute CSVs is a separate job, needs TWS running (so: the
failover rule), and is paced at ~11 s per session per symbol — hours. You should
not need it; the files are in LFS:

```bash
python3 band_lab/live/fetch_1min.py --symbol SOXL --start 2022-01-01 --port 7497
```

## E.5 Phase 2 · Stages 2–4 — the engine against a broker

```bash
python3 -m pytest band_lab/live -q            # 0 failures — offline, run it freely
python3 band_lab/live/diagnose.py             # needs TWS — VERDICT: READY
python3 band_lab/live/run.py --dry-run        # needs TWS — a whole session, transmit OFF
```

**`diagnose.py`** is read-only: it connects on its own client id, performs every
call the engine performs, prints what came back, and places no orders. It exists
because `run.py` is deliberately quiet — it prints decisions, not plumbing — so
**a silent feed and a working feed look identical**.

| Question it answers | Why it matters |
|---|---|
| Does `reqHistoricalData` return bars, and is **bar 0 the 09:30 bar**? | `Bar.idx` is minutes since 09:30 ET. A timezone mismatch shifts the whole grid, so bar 5 (the 10:00 filter) and bar 18 (the 11:00 arming) never come up. The engine consumes every bar and decides nothing, with no error. This actually happened — TWS was set to `America/Los_Angeles` and idx came out −36 |
| Is the feed **live**, per contract? | §4 forbids trading on delayed data |

A healthy result ends in `VERDICT: READY`. If it says **NOT READY**, do not start
`run.py`.

**The dry run** is the right first session on *this* machine — it has never
traded, and §5 of the original runbook keeps the dry run precisely for "a first
session on any new machine". Every order line must carry **`DRY RUN — not
sent:`**; that prefix is the guarantee:

```bash
mkdir -p logs
caffeinate -dims python3 -u band_lab/live/run.py --dry-run 2>&1 | tee "logs/$(date +%Y%m%d)-dryrun.log"
```

> **Forward slashes, and keep the launch line unbroken.** `band_lab\live\run.py`
> is a Windows path; in a POSIX shell the backslashes are escape characters and
> it collapses to `band_labliverun.py`. A stray `\` before the pipe breaks it the
> same way. Copy the line whole rather than retyping it.

`caffeinate -dims` holds sleep off for exactly as long as the engine runs, and
releases it when the engine exits. `-u` is deliberately absent from the
`caffeinate` flags — it expires after five seconds without `-t` and would do
nothing useful here. The `-u` on `python3` is a different flag entirely:
unbuffered output, so the log file stays current.

## E.6 Phase 2 · Stage 5 — the paper run

**On this machine only during a failover.** Full procedure in
[§G](#g--failover--taking-over-trading-from-the-windows-box).

```bash
python3 band_lab/live/watchdog.py --once      # one check, prints a verdict, changes nothing
python3 band_lab/live/watchdog.py             # terminal 2, all session
python3 band_lab/live/run.py --transmit       # terminal 1, all session
```

## E.7 Stages 6–7 — not built, nothing to run

| File | Stage | State |
|---|---|---|
| `report.py` | 6 — daily shadow parity, weekly §8 report | ⬜ **does not exist.** Highest-priority remaining work, and **the highest-value thing to build on this machine**: without it the paper run produces fills nobody diffs against the backtest, which is the entire reason to launch |
| `risk.py` | 7 — the −8.5% day-loss breaker, *enforced* | ⬜ **does not exist.** `Engine.day_loss_breached()` measures the condition and `run.py` breaks the session loop on it; nothing enforces a dormant-until-cleared state |
| Alerting | 7 | ⬜ **does not exist** in any form. When it is built, it must not go through public `ntfy.sh` — that would carry positions and P&L in clear text through a third party |
| Service supervision | 7 | ⬜ **does not exist.** The engine is a foreground process started by hand. `launchd` is the macOS answer, but only after Stage 7 |
| `watchdog.py` | 7 | ✅ built 2026-08-07 — §E.6 |

---

# §F · The coding loop

The order that catches the most, fastest:

```bash
cd ~/TradingModel
source .venv-live/bin/activate

# 1. the fast unit gate while you work — seconds
python3 -m pytest band_lab/live -q -k "not slow"

# 2. the full suites before you commit
python3 -m pytest band_lab/phase1 -q      # 59 passed, always
python3 -m pytest band_lab/live -q        # 0 failures

# 3. the equivalence gate — the one that catches a strategy change in a refactor
python3 band_lab/live/replay.py  ; echo "exit=$?"

# 4. only if you touched phase1 or a §12 constant
python3 band_lab/phase1/parity.py ; echo "exit=$?"
```

Both suites define a `slow` marker (`-m slow` selects them, `-k "not slow"`
skips): phase1's slow test runs the full 6-year parity backtest (~40 s), live's
replays the full history (~60 s).

Three things that will bite:

| | |
|---|---|
| **`EQUIVALENCE: FAIL`** | Not a flaky test. The sleeve's decisions changed. Diff before going any further |
| **`band_lab/phase1/` is frozen** | It is the reference implementation. If a change requires editing it, the change is wrong until proven otherwise |
| **`spec_constants.validate_config` will reject you** | Every strategy number lives in `IMPLEMENTATION_SPEC.md` §12. `config.py` may only carry *deployment* choices — host, port, paths. If a value could change a fill, it is in the wrong file, and the engine refuses to start |

`pytest` collects nothing? Run from the repo root — `conftest.py` sets
`sys.path` relative to itself.

---

# §G · Failover — taking over trading from the Windows box

🔴 **The single hard rule: the Windows box must be fully logged out of IBKR
before this machine logs in.** IBKR serves market data to one location at a
time. A second session produces error 162 here, historical requests fail, the
feature top-up returns nothing, and the engine refuses to start. If the Windows
box is *hung* rather than cleanly shut down, its TWS may still hold the
connection — confirm from Client Portal (then **close that tab too**; on
2026-08-03 the Client Portal tab was itself the competing session).

## G.1 The failover checklist

- [ ] **Windows box:** TWS quit, or the machine off. Not just the engine killed
- [ ] **Everywhere:** IBKR mobile app closed, Client Portal tabs closed
- [ ] **This box:** `git pull`, commit `014e9b4` or later
- [ ] **This box:** the four §D commands, 0 failures
- [ ] **This box:** TWS logged into **paper**, port 7497, §C.5 settings applied
- [ ] **This box:** `diagnose.py` → `VERDICT: READY`
- [ ] **This box:** `pmset` applied (§C.4), and you will not close the Terminal
- [ ] **Positions:** check TWS for anything the Windows box left open before you
      start the engine. It reconciles from the broker on connect, but you want
      to know what it is about to inherit

## G.2 The sequence

```bash
# --- prepare -------------------------------------------------------------
cd ~/TradingModel
git checkout main && git pull
git log --oneline -1                      # 014e9b4 or later
source .venv-live/bin/activate
pip install -r band_lab/live/requirements.txt
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
ls -lh SOXL_5min_6Years.csv SOXS_5min_6Years.csv     # 7.4M / 8.3M

# --- the gate ------------------------------------------------------------
python3 -m pytest band_lab/phase1 -q
python3 band_lab/phase1/parity.py  ; echo "exit=$?"
python3 band_lab/live/replay.py    ; echo "exit=$?"
python3 -m pytest band_lab/live -q

# --- pre-flight ----------------------------------------------------------
sudo pmset -c sleep 0 disksleep 0 displaysleep 10
python3 band_lab/live/diagnose.py         # VERDICT: READY, or stop
```

**Terminal 2 — the watchdog, started before the engine.** It is the only thing
that makes the flatten guarantee independent of the engine being correct:

```bash
cd ~/TradingModel
source .venv-live/bin/activate
python3 band_lab/live/watchdog.py --once          # confirm it can reach TWS
mkdir -p logs
caffeinate -dims python3 -u band_lab/live/watchdog.py 2>&1 | tee "logs/$(date +%Y%m%d)-watchdog.log"
```

**Terminal 1 — the engine:**

```bash
cd ~/TradingModel
source .venv-live/bin/activate
mkdir -p logs
caffeinate -dims python3 -u band_lab/live/run.py --transmit 2>&1 | tee "logs/$(date +%Y%m%d)-live.log"
```

For a rehearsal with no orders, swap `--transmit` for `--dry-run`. The two flags
together are refused rather than resolved by precedence.

The banner must read:

```
========================================================================
*** TRANSMIT ON — ORDERS WILL REACH THE MARKET ***
    port 7497 (PAPER)   clientId=11
    SOXL,SOXS at f=1.0 w=0.5 cap=$150,000
    First order is possible only after the 11:00 bar (§2.3).
========================================================================
```

**If it says `DRY RUN` instead, `--transmit` did not take.** If the port is not
7497, stop immediately.

Other flags: `--poll <seconds>` overrides the 20 s bar poll, `--heartbeat
<seconds>` the 900 s status line (0 disables it — do not, the watchdog reads it),
`--config <path.json>` loads a JSON config.

## G.3 The watchdog, in detail

It sits silent until one of two things is true:

| Trigger | Covers |
|---|---|
| No engine heartbeat for **>2 minutes** during RTH | crash, hang, killed terminal, **slept Mac** |
| Past **15:58** and still holding a position or a working order | an engine that is alive, heartbeating, and wrong — which is what happened on 2026-08-05, -06 and -07 |

Then it does exactly one thing: `reqGlobalCancel`, then market orders to flat.
It cannot open a position — it has no code path that places a limit or a stop.

```
11:01:02 [watchdog info    ] watching | port 7497 clientId=12 | stale>120s or past 15:58 while exposed
11:11:04 [watchdog info    ] ok — engine alive (18s), 1 position(s)
```

> **It uses clientId 12**, never the engine's 11. If you change `client_id` in a
> config file, change `watchdog_client_id` too — two processes on one id will
> fight.

If it ever prints `HUMAN INTERVENTION REQUIRED`, it tried five times and failed
— go to TWS immediately.

## G.4 The timeline

**No order can exist before the 11:00 bar.** §2.3: *"No orders may be placed
before 11:00 under any circumstance."* Enforced in three places — the state
machine only activates at `bar_idx >= 18`, the engine only calls
`assert_live_data` at that same point, and no intent is emitted before it.

| Time (ET) | What happens | Needs you? |
|---|---|---|
| 08:00–08:30 | §G.2 prepare + gate; TWS logged into paper | ✅ |
| 08:30 | `diagnose.py` → `VERDICT: READY` | ✅ |
| 08:45 | start `watchdog.py` (terminal 2) | ✅ |
| by 09:25 | start `run.py` (terminal 1); pre-open: connect, features, gate, capital | ✅ **watch this** |
| 09:25–09:30 | polls; the feed correctly returns **nothing** before the open | no |
| 09:30–10:00 | records bars 0–5 | no |
| 10:00 | morning filter fires on bar 5 | ✅ Check 5 |
| 10:00–11:00 | observes; tracks `session_high`. **Still cannot order** | no |
| **~11:05** | **first arming** — bar 18 covers 11:00–11:05 and is only delivered once it closes, so the limit goes live at ~11:05–11:06, priced off bars 0–17 | ✅ **be back** |
| 11:05–15:55 | ratchet, fills, brackets, re-arm | ✅ |
| 15:55 | flatten | ✅ verify in TWS |
| 15:58 | watchdog's hard deadline — it intervenes if still exposed | ✅ |
| 16:10 | `EOD reconcile: AGREES`; save the evidence | ✅ |
| 23:00 | TWS auto-restarts; the engine reconnects by itself | no |

An 08:00 start with an absence from 09:00 to 11:00 is **structurally** safe, not
safe by luck: the window you miss is the one in which the engine is forbidden
from acting. If it dies while you are away, it dies flat.

**The live-vs-backtest gap this creates runs one direction only.** The
backtest's limit rests from 11:00 and can fill during bar 18; live, you are not
in the market for those five minutes. Live will miss fills the backtest books,
never the reverse.

## G.5 Handing trading back to Windows

1. Confirm this machine is **flat** in TWS — no position, no working order.
2. `Ctrl+C` both terminals. `Ctrl+C` stops the process; **it does not flatten**.
3. **Quit TWS on this machine.** Not just disconnect — quit it.
4. Copy the day's evidence off (§I.2) and commit nothing from `logs/` or
   `band_lab/live/out/` — both are gitignored, keep it that way.
5. Only then start TWS on the Windows box.

---

# §H · The in-session checks

Identical on both machines. **Write down what you actually see.**

### ✅ Check 1 — the feature top-up reached the broker

```
09:24:11 [info    ] SOXL: 524 sessions in window | +8 from broker | csv holds 1510 | last session 2026-07-31
```

**Pass:** `+N from broker` with **N > 0**, and `last session` reading the most
recent trading day.

**Fail:** an explicit `[error]` saying the top-up added no sessions. The CSVs
stop at 2026-07-21 (SOXL) and 2026-07-24 (SOXS), so this means the gate is being
computed from stale data. `features.check` now refuses the run outright past 5
days of staleness. **Stop and investigate** — usually error 162 (§K).

> `sessions in window` (524) is the trimmed `thr80` window and `csv holds` is the
> whole file — they are not meant to sum.

### ✅ Check 2 — equity, sleeve capital, and the right port

```
09:24:03 [info    ] pre-open 20260810 | SOXL,SOXS @ 127.0.0.1:7497 clientId=11 | f=1.0 w=0.5 cap=150,000 | TRANSMIT ON
09:24:20 [info    ] equity=150,000 basis=150,000 sleeve_capital=75,000
```

**Pass:** the address ends **`:7497`**; the mode is what you intended; `equity=`
matches the paper balance; `sleeve_capital=` is half the capped basis. The engine
computes `sleeve_capital = 0.50 × min(NetLiquidation, 150,000)` and
`shares = floor(sleeve_capital / price)`.

**Fail:** a `sleeve_capital` under a few hundred dollars means the sleeve sizes
to 0 shares and silently never trades. Under $230 NetLiq, it never trades at all.

### ✅ Check 3 — the gate is ON for both sleeves

No `GATE OFF` line should appear. **Fail:** if the reason is `atr5` and the value
looks like last week's, the top-up failed — see Check 1. If it is
`market_closed`, TWS thinks today is a holiday.

### ✅ Check 4 — no bars before 09:30, and no repeats

Between starting the engine and 09:30, **no bar-related output at all**. The
first bars follow the 09:35 close. **Fail:** bar activity before 09:30, or bar
indices that jump backwards — prior-session bars being read as today's.

### ✅ Check 5 — the 10:00 filter fires once

```
10:00:22 [info    ] SOXL STAND DOWN: or30>=thr80 and pos10<2/3
```

**Pass:** at most one filter line per sleeve, at ~10:00 and not before.

### ✅ Check 6 — 11:00 arming

At ~11:05, for each sleeve still ON, a resting BUY LMT appears in TWS and in the
log. On a dry run the line must read **`DRY RUN — not sent:`**.

**🔴 STOP IMMEDIATELY** if you are in a dry run and an order appears *without*
that prefix, or appears in TWS at all.

**Fail (soft):** `NotLiveDataError` → market data is delayed.

### ✅ Check 7 — the bracket covers the whole position

**This is defect 8, the most serious found so far.** On 2026-08-06 IBKR filled
541 shares as 300 + 210 + 31; the bracket was sized from the first execution, so
**241 shares carried no stop and no target** while the state machine believed it
held 300. The fix sizes the protective legs from `broker.position()` after every
entry execution.

**Verify it on real fills:** after any entry, the SELL STP quantity in TWS must
equal the position quantity. Every time.

### ✅ Check 8 — no `BAR GAP` errors, all session

```
11:03:01 [error   ] SOXL BAR GAP: 18 -> 21; session_high may be understated
```

**Pass:** zero occurrences. A missed bar understates `session_high`, the anchor
everything ratchets from.

### The three open assumptions

`PHASE2_PLAN.md` §6. **No exit has ever filled against IBKR.**

- **§6.1 (most important) — does the protective stop outlive the engine?** After
  the first bracket is on: confirm SELL LMT **and** SELL STP in TWS, `Ctrl+C` the
  engine, **check the stop is still there**. If it vanishes, that is a
  stop-everything finding. Restart afterwards — it reconciles from the broker and
  resumes; confirm it does not open a duplicate position.
- **§6.3 — does OCA cancel the sibling?** When a target fills, the sibling stop
  must go to `Cancelled` by itself. If both legs execute, the sleeve ends up
  **short**, which the strategy forbids absolutely.
- **§6.2 — does the 23:00 TWS restart reconcile cleanly?** Leave it overnight;
  confirm `fills` and `stop_outs` did not double-count.

### What a normal result looks like

**Plan on ~40 bp/ON-day for SOXL and ~30 for SOXS.** A run at 20–40 bp is
consistent with the evidence and is **not** a sign the engine is broken — §E.4
is why. The engine is ON ~52% of sessions, so four weeks gives ~10–11 ON-days
per sleeve. **A single week proves nothing.** The first ~3 sessions are shakedown
and are excluded from the evidence set.

---

# §I · Close-out and evidence

## I.1 15:55–16:10

```
15:55:02 [info    ] 15:55 flatten
15:55:07 [info    ] all sleeves flat
15:55:09 [info    ] SOXL EOD fills=2 stops=0 pnl=38.4bp agrees=True

EOD reconcile: AGREES
```

**Pass:** `EOD reconcile: AGREES`, no `critical` line anywhere in the session,
and — **with your own eyes, in TWS** — no position and no working order. The log
line saying flat is not the check; three consecutive sessions in August 2026
printed a flatten that did not flatten.

## I.2 Save the evidence

```bash
cd ~/TradingModel
cp band_lab/live/out/live.db ~/Desktop/live-$(date +%Y%m%d).db
```

The logs are already at `logs/$(date +%Y%m%d)-live.log` and
`logs/$(date +%Y%m%d)-watchdog.log`.

## I.3 Inspect what the engine actually decided

Until `report.py` exists (Stage 6), this is the instrument:

```bash
python3 -c "
import sqlite3
c = sqlite3.connect('band_lab/live/out/live.db')
c.row_factory = sqlite3.Row
for r in c.execute('SELECT * FROM daily ORDER BY session DESC LIMIT 4'):
    print(dict(r))
"
```

One row per sleeve per session, newest first: `gate_ok`, `gate_reason`,
`filter_ok`, `filter_reason`, `atr5`, `or30`, `thr80`, `pos10`,
`account_equity`, `sleeve_capital`, `fills`, `stop_outs`, `realised_pnl`,
`flat_at_close`.

Other tables: `bars`, `decisions`, `orders`, `fills`, `quotes`, `counters`,
`events`.

The two S10/S11 questions to answer from `fills` and `quotes`: did any fill
occur without the quote reaching the limit, and on same-bar re-entries is the
achieved price at or worse than the price just sold?

## I.4 The go/no-go after a dry run

Any "no" is a no-go for transmitting.

- [ ] Did all four §D verification commands pass in the morning?
- [ ] Did the feature top-up show `+N from broker` with N > 0 (Check 1)?
- [ ] Was the gate ON for both sleeves (Check 3)?
- [ ] Were there zero bars before 09:30 and no index repeats (Check 4)?
- [ ] Did every order line carry `DRY RUN — not sent` (Check 6)?
- [ ] Were there zero `BAR GAP` errors and zero `critical` lines (Check 8)?

Then compare the day's decisions against a replay of the same bars:

```bash
python3 band_lab/live/replay.py   ; echo "exit=$?"
```

---

# §J · Stopping, restarting, emergency

## Stopping safely

`Ctrl+C` in the engine window stops the process. **It does not flatten.** If a
position is open when you stop it:

1. Restart the engine — it reconciles and resumes; or
2. Flatten manually in TWS and cancel all working orders.

**Never leave a position open overnight.** It is design priority #1 and the
whole strategy is only safe because of it.

## Keeping the process alive on macOS

| | |
|---|---|
| Locking the screen | Fine — the process keeps running |
| **Closing the Terminal window** | **Kills it** |
| **Logging out** | **Kills it** |
| Sleep | Kills it — `caffeinate -dims` on the launch line prevents it, and §C.4's `pmset` is the belt to that braces |

## Restarting after a crash

Just restart it. State is established by reconciling with the broker, never from
memory, so starting at 13:00 after a crash produces the same state as having run
since 09:30. **Check TWS for orphaned orders first.**

## Can it be left unattended?

| Mode | Answer |
|---|---|
| `--dry-run` | **Yes.** `IBBroker` refuses to transmit at the adapter. The worst outcome is losing a day's observations |
| `--transmit` | **No.** No alerting, no service supervision, §6.1 unverified, no `report.py` |

`watchdog.py` closes the flatten hole specifically, and only that one.
`IMPLEMENTATION_SPEC.md` §7 requires attended operation for the first 3–6 months
regardless. Be at the machine from 11:00 to 16:00.

## Emergency — flatten everything now

In TWS: right-click the position → **Close Position**, then **Trade → Cancel All
Orders**. Do this **in TWS**, not through the engine.

---

# §K · Troubleshooting

| Symptom | Cause / fix |
|---|---|
| **Error 162** "Trading TWS session is connected from a **different IP address**" | 🔴 The most likely failure on this machine. The same IBKR login is active somewhere else — **the Windows box**, Client Portal in a browser, the mobile app, a second TWS. IBKR serves market data to one location at a time. **Log out everywhere else, then restart the engine.** Not an entitlement problem |
| **Error 10089** "requires additional subscription for API… Delayed market data is available" | The account has no live L1 entitlement for API use. Entitlement is account-level, so if the Windows box has it, this box has it — check for 162 first. Otherwise: Client Portal → Settings → Market Data Subscriptions, then share to paper |
| `feature history is insufficient or stale — refusing to start` | The broker top-up returned nothing (usually error 162), so ATR5/thr80 would come from the CSV's last session. §2.2 forbids trading on stale data. Fix the top-up and re-run — do **not** work around it |
| `+0 from broker` in the pre-open line | Same cause. Features are stale to 2026-07-21. Do not trade the session |
| `replay.py` fails loading CSVs, or a research script does | LFS files are still pointers — `git lfs pull --include="..."` (§C.2) |
| `command not found: band_labliverun.py` or similar | You used Windows backslashes in a POSIX shell. Forward slashes, and copy the launch line whole |
| `pytest` collects nothing | Run from `~/TradingModel`; `conftest.py` sets `sys.path` relative to itself |
| `ModuleNotFoundError: pandas` / `ib_async` / `requests` | The venv is not active, or §C.3 was skipped. `source .venv-live/bin/activate` |
| The Mac slept mid-session | `caffeinate -dims` was not on the launch line. §C.4 + the launch line, both |
| Connection refused | Port 7497 vs 7496; trusted IP 127.0.0.1; TWS actually logged into **paper** |
| `NotLiveDataError` | Market data is delayed |
| Orders do nothing | Read-Only API is ON, or a precaution dialog is waiting on screen in TWS (§C.5) |
| Bar indices are negative | TWS is set to a non-ET timezone. `Bar.idx` is minutes since 09:30 ET; `America/Los_Angeles` gives idx −36 and the engine decides nothing, silently. `diagnose.py` catches it |
| `EQUIVALENCE: FAIL` after a code change | The gate doing its job. The sleeve's decisions changed — diff before going further |
| `ConfigError: port 7496 is a LIVE-money port` | Correct behaviour. Phase 2 is paper only |
| `ConfigError` naming a §12 constant | `spec_constants.validate_config` rejecting a strategy change made in a deployment file. Put it in §12 or do not make it |
| `BAR GAP` errors | A poll missed a bar; `session_high` may be understated. Record the indices |
| Watchdog prints `HUMAN INTERVENTION REQUIRED` | It tried five times to flatten and failed. **Go to TWS now** |
| Watchdog and engine fight over orders | Both are on the same client id. Engine is 11, watchdog 12 (`watchdog_client_id`) |
| Engine crashed mid-session | Restart it — it reconciles from the broker, not from memory. Check TWS for orphaned orders first |

---

# §L · Command index — every runnable file

Prefix every line with:

```bash
cd ~/TradingModel && source .venv-live/bin/activate
```

| Stage | File | Command | Expected |
|---|---|---|---|
| Research | `band_analysis.py` | `python3 band_lab/band_analysis.py` | `band_lab/out/report.txt` + tables |
| Research | `churn_harvest.py` | `python3 band_lab/churn_harvest.py` | `out/churn_grid.csv` |
| Research | `regime_gate.py` | `python3 band_lab/regime_gate.py` | gated results |
| Research | `v1v3_adaptive_tests.py` | `python3 band_lab/v1v3_adaptive_tests.py` | `out/v1v3_results.csv` |
| Research | `v2_anchor_tests.py` | `python3 band_lab/v2_anchor_tests.py` | `out/v2_*.csv` |
| Research | `v5_start_time_tests.py` | `python3 band_lab/v5_start_time_tests.py` | `out/v5_results.csv` |
| Research | `v5_corrected_rerun.py` | `python3 band_lab/v5_corrected_rerun.py` | `out/v5_corrected_results.csv` |
| Research | `v6_eod_exit_tests.py` | `python3 band_lab/v6_eod_exit_tests.py` | `out/v6_results.csv` |
| Research | `v8_direction_tests.py` | `python3 band_lab/v8_direction_tests.py` | `out/v8_results.csv` |
| Research | `v9_filter_tests.py` | `python3 band_lab/v9_filter_tests.py` | `out/v9_results.csv` |
| Research | `v10_gate_tests.py` | `python3 band_lab/v10_gate_tests.py` | `out/v10_results.csv` |
| Research | `v11_sizing_tests.py` | `python3 band_lab/v11_sizing_tests.py` | `out/v11_results.csv` |
| Research | `v13_streak_tests.py` | `python3 band_lab/v13_streak_tests.py` | `out/v13_results.csv` |
| Research | `v14_pair_protocol.py` | `python3 band_lab/v14_pair_protocol.py` | pair protocol tables |
| Research | `v15_weekly_sweep.py` | `python3 band_lab/v15_weekly_sweep.py` | `out/v15_*.csv` |
| Research | `cap_sweep.py` | `python3 band_lab/cap_sweep.py` | `out/cap_sweep.csv` |
| Research | `sizing_verification.py` | `python3 band_lab/sizing_verification.py` | `out/sizing_verification.csv` |
| Research | `etf_scaling_test.py` | `python3 band_lab/etf_scaling_test.py` | `out/etf_scaling_*.csv` |
| Research | `spxl_scaling_test.py` | `python3 band_lab/spxl_scaling_test.py` | `out/spxl_scaling.csv` |
| Research | `transfer_test.py` | `python3 band_lab/transfer_test.py` | `out/transfer_test.csv` |
| Research | `put_overlay_test.py` | `python3 band_lab/put_overlay_test.py` | `out/put_overlay_curves.csv` |
| Research | `walk_forward_and_combo.py` | `python3 band_lab/walk_forward_and_combo.py` | `out/wf_*.csv`, `out/combo_*.csv` |
| V16 | `v2_dev/churn_joint_test.py` | `python3 band_lab/v2_dev/churn_joint_test.py [--quick]` | `v2_dev/out/v16_*.csv` |
| V17 | `v2_dev/trade_cap_test.py` | `python3 band_lab/v2_dev/trade_cap_test.py` | `v2_dev/out/v17_*.csv` |
| V18 | `v2_dev/vol_gate_test.py` | `python3 band_lab/v2_dev/vol_gate_test.py` | `v2_dev/out/v18_*.csv` |
| Phase 1 | `phase1/` suite | `python3 -m pytest band_lab/phase1 -q` | **59 passed** |
| Phase 1 | `phase1/parity.py` | `python3 band_lab/phase1/parity.py` | 16 §8 numbers, **exit 0** |
| Phase 1 | `phase1/cost_model.py` | `python3 band_lab/phase1/cost_model.py` | cost tables |
| P2 S1 | `live/replay.py` | `python3 band_lab/live/replay.py` | `STAGE 1 EQUIVALENCE: PASS`, **exit 0** |
| P2 S1 | `live/replay.py --sizing` | `python3 band_lab/live/replay.py --sizing` | the S9 report |
| P2 S1 | `live/replay.py --fill-models` | `python3 band_lab/live/replay.py --fill-models` | the S10 report |
| P2 S1 | `live/intrabar.py` | `python3 band_lab/live/intrabar.py --symbol SOXL --start 2022-01-01` | 42.5 bp SOXL / 34.2 SOXS |
| P2 S1 | `live/fetch_1min.py` | `python3 band_lab/live/fetch_1min.py --symbol SOXL --start 2022-01-01 --port 7497` | rebuilds the 1-min CSV; needs TWS; hours |
| P2 S2–4 | `live/` suite | `python3 -m pytest band_lab/live -q` | **0 failures** |
| P2 S2–4 | `live/diagnose.py` | `python3 band_lab/live/diagnose.py` | `VERDICT: READY` — needs TWS |
| P2 S2–4 | `live/run.py` dry | `python3 band_lab/live/run.py --dry-run` | every order `DRY RUN — not sent:` |
| P2 S5 | `live/watchdog.py` check | `python3 band_lab/live/watchdog.py --once` | one verdict, changes nothing |
| P2 S5 | `live/watchdog.py` | `python3 band_lab/live/watchdog.py` | terminal 2, all session |
| P2 S5 | `live/run.py` live | `python3 band_lab/live/run.py --transmit` | `*** TRANSMIT ON ***`, port 7497 — **failover only** |
| P2 S6 | `live/report.py` | — | ⬜ **not built** — the highest-value thing to build here |
| P2 S7 | `live/risk.py` | — | ⬜ **not built** |
