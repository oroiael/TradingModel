# Runbook — Windows 11 · the primary trading machine

**Instructions only.** What to type, in what order, and what you should see.
The reasoning lives in [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) and the
documents it maps; the normative rules live in
[`../IMPLEMENTATION_SPEC.md`](../IMPLEMENTATION_SPEC.md).

This machine **runs the paper account**. The Mac is for coding and for taking
over if this box is unavailable — see [`RUNBOOK_MACOS.md`](RUNBOOK_MACOS.md).

Three rules while working through this:

1. **Do the sections in order.** Each one assumes the previous one passed.
2. **Stop at the first step that does not behave as described.** Do not work
   around it. Every check here exists because something went silently wrong
   underneath it at least once.
3. **Only one machine may be logged into IBKR at a time.** A second TWS, the
   mobile app, or even a Client Portal browser tab produces **error 162** here
   and silently kills the bar feed. Before you start, the Mac must be logged
   out of IBKR entirely.

All times are **America/New_York (ET)**.
**The paper port is 7497** — everywhere in this document, without exception.
7496 and 4001 are live-money ports and `EngineConfig.validate()` refuses them.

Shell is **PowerShell**. The repo lives at **`C:\TradingModel`**. Python is
invoked as **`python`** (not `python3`).

| Section | Use it when |
|---|---|
| [§A](#a--what-this-machine-is-for) | Deciding whether you are on the right box |
| [§B](#b--one-time-machine-setup) | The box is new, or something in §C fails |
| [§C](#c--the-fast-path--an-already-set-up-box) | The box is already set up and today is a trading day |
| [§D](#d--verify-the-install--the-regression-gate) | Every session, before anything else |
| [§E](#e--tws-paper-configuration--one-time-verify-every-session) | One-time TWS setup, and the per-session verification |
| [§F](#f--execute-every-stage-in-order) | Running every file in the project, stage by stage |
| [§G](#g--the-daily-session-minute-by-minute) | The trading day itself |
| [§H](#h--the-in-session-checks) | Watching the engine while it runs |
| [§I](#i--close-out-and-evidence) | 15:55–16:10 |
| [§J](#j--stopping-restarting-emergency) | Something needs to stop |
| [§K](#k--troubleshooting) | Something errored |
| [§L](#l--command-index--every-runnable-file) | You want the one command for one file |

---

# §A · What this machine is for

| | Windows 11 (this box) | macOS |
|---|---|---|
| Role | **Primary trading environment** | Coding, research, backup trading |
| Runs `run.py --transmit` | **Yes — this is the machine** | Only when this box is down |
| Runs `watchdog.py` | **Yes, every session** | Only when it is trading |
| Runs the test suites | Yes, as the pre-session gate | Yes, constantly |
| Logged into IBKR | **During the session, exclusively** | Logged out while this box trades |

The engine is **attended**: `IMPLEMENTATION_SPEC.md` §7 requires a human at the
machine for the first 3–6 months, and there is no alerting of any kind — no
push, no email, no desktop notification. The console window and `watchdog.py`
are the entire monitoring stack.

---

# §B · One-time machine setup

Skip to [§C](#c--the-fast-path--an-already-set-up-box) if `python --version`,
`git --version` and `git lfs version` all already answer.

### B.1 Install the tooling

Open **PowerShell as Administrator**:

```powershell
winget install --id Python.Python.3.12 -e
winget install --id Git.Git -e
winget install --id GitHub.GitLFS -e
```

Close that window. Open a **normal** PowerShell window and verify:

```powershell
python --version     # must be 3.11 or higher
git --version
git lfs version
```

> If `python` opens the Microsoft Store instead of running, Python is not on
> PATH. Re-run the installer and tick **"Add python.exe to PATH"**.

Initialise LFS once per machine:

```powershell
git lfs install
```

Allow the venv activation script to run, once per user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### B.2 Get the code and the data

```powershell
cd C:\
git clone https://github.com/oroiael/TradingModel.git
cd C:\TradingModel
git checkout main
git pull
git log --oneline -1
```

You need commit **`014e9b4`** or later. **Without it, `--dry-run` places real
orders** — `readonly` in `ib_async` never stopped `placeOrder`, and the guard
that makes a dry run actually dry did not exist until 2026-08-02.

> Do **not** use the branch name printed in `DEPLOYMENT.md` §2. It was merged
> and deleted; `main` is current.

The price files are stored in Git LFS and arrive as 132-byte pointer files
otherwise. Nothing downstream works until they are real:

```powershell
cd C:\TradingModel
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv,SOXL_1min.csv,SOXS_1min.csv"
```

**Check — this must show megabytes, not bytes:**

```powershell
Get-ChildItem SOXL_5min_6Years.csv, SOXS_5min_6Years.csv, SOXL_1min.csv, SOXS_1min.csv |
    Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
```

```
Name                     MB
----                     --
SOXL_5min_6Years.csv    7.4
SOXS_5min_6Years.csv    8.3
SOXL_1min.csv           ...
SOXS_1min.csv           ...
```

If any of them reads `0`, the LFS pull did not work. Stop and fix it. The two
5-minute files are required for **everything**; the two 1-minute files are
required only for the S10/S11 study (§F.4) and the `v2_dev` re-tests (§F.2).

### B.3 Build the Python environment

```powershell
cd C:\TradingModel
python -m venv .venv-live
.\.venv-live\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r band_lab\live\requirements.txt
```

That installs `pandas`, `numpy`, `pytest`, `ib_async`, `requests` and
**`tzdata`**. The last one matters on Windows specifically: Windows ships no
IANA time-zone database, and every timestamp in the engine goes through
`ZoneInfo("America/New_York")`.

The prompt should now start with `(.venv-live)`. **Every command in this
document assumes the venv is active.**

### B.4 Stop the machine sleeping

PowerShell **as Administrator**:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 10
```

Then **Settings → Windows Update → Advanced options** — set active hours to
cover 09:00–17:00 so it does not reboot mid-session.

- **`Win+L` (lock) is fine — the engine keeps running.**
- **Signing out kills it.** So does closing the PowerShell window, and so does
  sleep.

### B.5 Keep session logs out of git

The launch commands below write to `C:\TradingModel\logs\`. That directory is
gitignored — leave it that way. Session logs carry account balances, share
counts and fill prices.

---

# §C · The fast path — an already-set-up box

Python, TWS and the repo are already installed. Four things still have to
happen before the session.

### C.1 🔴 `git pull` — mandatory, every session

```powershell
cd C:\TradingModel
git checkout main
git pull
git log --oneline -1
```

Commit **`014e9b4`** or later. See §B.2 for why this one is not optional.

### C.2 Confirm the price files are real, not LFS pointers

Even on a working clone these arrive as 132-byte pointers unless someone ran
`git lfs pull`:

```powershell
cd C:\TradingModel
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
Get-ChildItem SOXL_5min_6Years.csv, SOXS_5min_6Years.csv |
    Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
```

Must read **7.4 MB** and **8.3 MB**. If either says `0`, stop and fix it.

### C.3 Reinstall requirements — the file changes

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
pip install -r band_lab\live\requirements.txt
```

### C.4 Run the §D gate

Not a formality — it is what proves the pull landed cleanly.

---

# §D · Verify the install — the regression gate

**Run this whole block every time before a trading session**, not just once.

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1

python -m pytest band_lab\phase1 -q
python band_lab\phase1\parity.py  ; echo "exit=$LASTEXITCODE"
python band_lab\live\replay.py    ; echo "exit=$LASTEXITCODE"
python -m pytest band_lab\live -q
```

Expected, exactly:

| Command | Must show | Time |
|---|---|---|
| `pytest band_lab\phase1` | `59 passed` — a fixed invariant | ~1 min |
| `parity.py` | a table ending in the §8 numbers, then `exit=0` | ~2 min |
| `replay.py` | `STAGE 1 EQUIVALENCE: PASS`, then `exit=0` | ~1 min |
| `pytest band_lab\live` | all pass, **0 failures** | ~1 min |

**Do not memorise the live count — `0 failures` is the gate.** For orientation
only: `PROJECT_STATUS.md` recorded **173** at the 2026-08-06 review (59 + 173 =
the 232 it quotes), and `watchdog.py` added 12 the next day. The number grows
with every fix; the commit hash in §C.1 is the real version check.

Anything other than the above — a failure, a different phase1 count, a non-zero
exit — is a stop.

---

# §E · TWS paper configuration — one-time, verify every session

Install **Trader Workstation** from interactivebrokers.com and log in to the
**paper** account. The login screen has a Live/Paper selector — it must say
**Paper**.

### E.1 API settings

**File → Global Configuration → API → Settings**

| Setting | Value |
|---|---|
| Enable ActiveX and Socket Clients | **ON** |
| Socket port | **7497** |
| Trusted IPs | **127.0.0.1** |
| Read-Only API | **OFF** |
| Download open orders on connection | **ON** |
| Create API message log file | **ON** |
| Master API client ID | leave blank |

> Port 7497 is TWS paper. **7496 is live money** — the engine refuses to start
> on it unless explicitly overridden, and for Phase 2 you never override it.

### E.2 Precautions

**API → Precautions** — tick the "Bypass … for API orders" boxes one at a time,
deliberately. A precaution dialog cannot be answered by a headless process; an
un-bypassed one turns a rejected order into a silent hang.

### E.3 Restart schedule

**Configuration → Lock and Exit**

| Setting | Value |
|---|---|
| Auto restart | **23:00** |
| Never lock Trader Workstation | ON |

### E.4 Market data — the engine refuses to trade without this

Paper accounts see live data only if the live account's subscriptions are
shared to them: **Client Portal → Settings → Account Settings → Paper Trading
Account → share market data**. The subscription needed is **live US equity L1
covering NYSE Arca** — both ETFs are Arca-listed.

**Check:** in TWS, add SOXL to a watchlist. The bid/ask must tick during market
hours without a delayed-data banner.

This gates two separate things: the engine refuses to arm at 11:00 on delayed
data, *and* the historical top-up in §E.6 is itself a market-data request that
fails without it.

> **Close the Client Portal tab when you are done.** On 2026-08-03 the browser
> tab used to *buy* the subscription was itself the competing IBKR session that
> produced error 162 and killed the top-up.

### E.5 Confirm the account can trade the size

In TWS: **Account → Account Window**. Note **NetLiquidation**,
**Available Funds** and **Buying Power** before the session, so a rejection is
diagnosable rather than a surprise.

The engine computes `sleeve_capital = 0.50 × min(NetLiquidation, 150,000)` and
`shares = floor(sleeve_capital / price)`.

| | |
|---|---|
| `capital_basis` | `min(NetLiq, 150,000)` = **$150,000** at the planned balance |
| `sleeve_capital` | 0.50 × 150,000 = **$75,000 per sleeve** |
| shares at SOXL ≈ $115 | **652** |
| both sleeves long at once | **$150,000 of stock on $150,000 equity** |

That is exactly the size the published cost rows assume. It also puts the
account at **100% deployed** when both sleeves are long simultaneously —
`PHASE2_PLAN.md` §4.3, still open:

- **PDT is satisfied.** $150,000 ≫ the $25,000 floor.
- **Reg T initial margin** is 50% on ordinary stock, but **3x ETFs carry
  elevated requirements** — brokers cap day-trading buying power near 1.33×
  because of 75% maintenance. 1.0× should fit, with little room to spare.
- **A dry run cannot test this.** No orders are sent, so no buying-power check
  is exercised.

For reference, if the balance ever ends up wrong:

| NetLiquidation | Per sleeve | Shares at SOXL ≈ $115 |
|---|---:|---:|
| $150,000 (planned) | $75,000 | 652 |
| $50,000 | $25,000 | 217 |
| $1,000 | $500 | 4 |
| under $230 | under $115 | **0 — the sleeve never trades** |

### E.6 Historical data — nothing to update by hand

**The engine fetches it itself, every morning, as part of the run.**

| | |
|---|---|
| **Backbone** | The repo's 5-minute CSVs. They stop at **2026-07-21** (SOXL) and **2026-07-24** (SOXS) and are never rewritten |
| **Top-up** | At pre-open the engine measures the gap to today and makes **one** paced `reqHistoricalData` call per symbol for the missing 5-minute bars |
| **Today's bars** | Polled live from IBKR every 30 seconds through the session |

A failed top-up is now an explicit `[error]` and `features.check` refuses the
run outright past 5 days of staleness — which is another reason §C.1's
`git pull` matters. Watch it as **§H Check 1**.

> `band_lab/live/fetch_1min.py` is the fetcher for the 1-minute *study*, not for
> this. The CSV backbone is deliberately frozen — it is the exact series every
> published number came from.

---

# §F · Execute every stage, in order

Everything the project can run, grouped by the stage it belongs to. **Only §F.5
and §F.6 are part of a trading day.** §F.1–§F.4 reproduce the research and the
parity evidence; run them once on a new machine, or when you want to confirm a
published number by hand.

All commands assume:

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
```

| Stage | What it is | Status | Section |
|---|---|---|---|
| Research | Find and validate the strategy | ✅ complete, locked 2026-07-28 | §F.1 |
| Re-tests V16–V18 | Re-sweep churn parameters on 1-minute data | ✅ complete, **nothing adopted** | §F.2 |
| Phase 1 | Clean-room backtest parity harness | ✅ complete, passing | §F.3 |
| Phase 2 · Stage 1 | Live state machine == the backtest | ✅ complete, passing | §F.4 |
| Phase 2 · Stages 2–4 | Broker, store, orders, timetable, entrypoint | ✅ code complete | §F.5 |
| Phase 2 · Stage 5 | Paper run, ≥4 weeks | 🟡 **underway** | §F.6 |
| Phase 2 · Stages 6–7 | `report.py`, `risk.py`, alerting | ⬜ **not built** | §F.7 |

## F.1 Research — the original 5-minute programme

Outputs land in `band_lab\out\`. Needs the two 5-minute CSVs only. Run in this
order; the later scripts import helpers from the earlier ones.

```powershell
# the three README scripts, in order
python band_lab\band_analysis.py        # band stats, excursions, the failing control fade
python band_lab\churn_harvest.py        # dip-buy harvester grid (params x filters)
python band_lab\regime_gate.py          # the ATR5 volatility gate on the best configs
```

Then the twelve variable programmes, V1–V15. Each one is the evidence behind one
locked constant in `IMPLEMENTATION_SPEC.md` §12, and each has a matching
`V*_TESTS.md` next to it:

```powershell
python band_lab\v1v3_adaptive_tests.py      # V1 dip %, V3 target %
python band_lab\v2_anchor_tests.py          # V2 the ratchet anchor
python band_lab\v5_start_time_tests.py      # V5 start time
python band_lab\v5_corrected_rerun.py       # V5 corrected — defines sim_trades_fixed, used by V9+
python band_lab\v6_eod_exit_tests.py        # V6 the 15:55 exit
python band_lab\v8_direction_tests.py       # V8 SOXS as a second sleeve   [needs SOXS_5min_6Years.csv]
python band_lab\v9_filter_tests.py          # V9 the 10:00 morning filter
python band_lab\v10_gate_tests.py           # V10 the ATR5 gate level      [needs SOXX_5min_6Years.csv]
python band_lab\v11_sizing_tests.py         # V11 sizing and 3x margin
python band_lab\v13_streak_tests.py         # V13 the 2-stop breaker
python band_lab\v14_pair_protocol.py        # V14 the pair protocol — prespecified adoption bar
python band_lab\v15_weekly_sweep.py         # V15 weekly stability
```

And the supporting studies:

```powershell
python band_lab\cap_sweep.py                # capital-cap sensitivity
python band_lab\sizing_verification.py      # sizing arithmetic, independently
python band_lab\etf_scaling_test.py         # does it transfer to FAS?      [needs FAS_5min_6Years.csv]
python band_lab\spxl_scaling_test.py        # ... and SPXL?                 [needs SPXL_5min_6Years.csv]
python band_lab\transfer_test.py            # cross-symbol transfer
python band_lab\put_overlay_test.py         # a put overlay on the sleeve
python band_lab\walk_forward_and_combo.py   # walk-forward + the combined $150K backtest
```

> These are one-off. Nothing in the trading path reads `band_lab\out\`.

## F.2 Re-tests V16–V18 — the v2.0-dev line

**Nothing in `v2_dev\` is approved for trading.** It re-swept ~1,040 parameter
cells on the 1-minute data and adopted nothing; the strategy is unchanged.

Needs **`SOXL_1min.csv` and `SOXS_1min.csv`** (§B.2). Outputs go to
`band_lab\v2_dev\out\`.

```powershell
python band_lab\v2_dev\churn_joint_test.py --quick   # V16 joint dip/target, coarse grid
python band_lab\v2_dev\churn_joint_test.py           # V16 full grid + walk-forward
python band_lab\v2_dev\trade_cap_test.py             # V17 the 5-trade cap
python band_lab\v2_dev\vol_gate_test.py              # V18 the ATR5 gate, re-measured
```

Each accepts `--out <dir>` if you want the CSVs somewhere else.

## F.3 Phase 1 — the clean-room parity harness

`band_lab\phase1\` is the reference implementation. **It must not be modified.**

```powershell
python -m pytest band_lab\phase1 -q          # 59 passed — a fixed invariant
python band_lab\phase1\parity.py             # all 16 published §8 numbers, exit 0   (~2 min)
python band_lab\phase1\parity.py --skip-delta   # faster; skips the delta table
python band_lab\phase1\cost_model.py         # commission + slippage tables by account size
```

`parity.py --tol <float>` changes the comparison tolerance; the default `1e-12`
is what the published claim rests on. Do not loosen it to make it pass.

## F.4 Phase 2 · Stage 1 — the live state machine, offline

`replay.py` drives the *live* sleeve state machine over the full 6-year history
and compares it to the phase1 engine, decision by decision.

```powershell
python band_lab\live\replay.py                  # STAGE 1 EQUIVALENCE: PASS, exit 0   (~1 min)
python band_lab\live\replay.py --sizing         # the S9 sizing-basis difference
python band_lab\live\replay.py --fill-models    # the S10 same-bar re-entry sensitivity
```

The 1-minute fill-resolution study — **the most consequential finding in the
project** (`PHASE2_PARITY.md` S10–S12). Needs the 1-minute CSVs:

```powershell
python band_lab\live\intrabar.py --symbol SOXL --check --start 2022-01-01   # data sanity first
python band_lab\live\intrabar.py --symbol SOXL --start 2022-01-01
python band_lab\live\intrabar.py --symbol SOXS --check --start 2022-01-01
python band_lab\live\intrabar.py --symbol SOXS --start 2022-01-01
```

Expect **42.5 bp/ON-day on SOXL and 34.2 on SOXS**, against 66.8 / 63.0 at
5-minute resolution. **This is why you plan on ~40 bp and ~30 bp, not §8's
61.9 / 48.1.**

Rebuilding the 1-minute CSVs is a separate job and needs TWS running. It is
paced at ~11 s per session per symbol, so it takes hours — you should not need
it, the files are in LFS:

```powershell
python band_lab\live\fetch_1min.py --symbol SOXL --start 2022-01-01 --port 7497
```

## F.5 Phase 2 · Stages 2–4 — the engine against a broker

```powershell
python -m pytest band_lab\live -q            # 0 failures — the gate, §D
python band_lab\live\diagnose.py             # pre-flight — VERDICT: READY
python band_lab\live\run.py --dry-run        # a whole session, transmit OFF
```

**`diagnose.py`** is read-only: it connects on its own client id, performs every
call the engine performs, prints what came back, and places no orders. It exists
because `run.py` is deliberately quiet — it prints decisions, not plumbing — so
**a silent feed and a working feed look identical**.

| Question it answers | Why it matters |
|---|---|
| Does `reqHistoricalData` return bars, and is **bar 0 the 09:30 bar**? | `Bar.idx` is minutes since 09:30. A timezone mismatch shifts the whole grid, so bar 5 (the 10:00 filter) and bar 18 (the 11:00 arming) never come up. The engine consumes every bar and decides nothing, with no error. This actually happened — TWS was set to `America/Los_Angeles` and idx came out −36 |
| Is the feed **live**, per contract? | §4 forbids trading on delayed data |

A healthy result:

```
[ ok ] connected on port 7497 — PAPER
[ ok ] NetLiquidation $155,803 -> sleeve_capital $75,000
[ ok ] SOXL / SOXS qualified, session 09:30-16:00
[ ok ] bar 0 is the 09:30 bar — indices are aligned
[ ok ] engine would consume 78 bars (idx 0..77)
[ ok ] live market data confirmed
VERDICT: READY
```

If it says **NOT READY**, do not start `run.py`.

**The dry run** is not today's path — the 2026-08-03 dry runs found five defects
but never reached the 11:00 arming, and `diagnose.py` now covers the pre-open
half they were checking. Use `--dry-run` for a first session on a *new* machine,
after a change to the order path, or for a no-consequence rehearsal:

```powershell
mkdir logs -Force
python -u band_lab\live\run.py --dry-run 2>&1 |
    Tee-Object -FilePath "logs\$(Get-Date -f yyyyMMdd)-dryrun.log"
```

Every order line must carry the prefix **`DRY RUN — not sent:`**. That prefix is
the guarantee. If an order appears in TWS without it, `Ctrl+C` immediately and
cancel it by hand.

## F.6 Phase 2 · Stage 5 — the paper run (where we are)

Two processes, two terminals, **watchdog first**. Full sequence in
[§G](#g--the-daily-session-minute-by-minute).

```powershell
python band_lab\live\watchdog.py --once      # one check, prints a verdict, changes nothing
python band_lab\live\watchdog.py             # terminal 2, all session
python band_lab\live\run.py --transmit       # terminal 1, all session
```

## F.7 Stages 6–7 — not built, nothing to run

| File | Stage | State |
|---|---|---|
| `report.py` | 6 — daily shadow parity, weekly §8 report | ⬜ **does not exist.** Highest-priority remaining work: without it the paper run produces fills nobody diffs against the backtest |
| `risk.py` | 7 — the −8.5% day-loss breaker, *enforced* | ⬜ **does not exist.** `Engine.day_loss_breached()` measures the condition and `run.py` breaks the session loop on it; nothing enforces a dormant-until-cleared state |
| Alerting | 7 | ⬜ **does not exist** in any form |
| Service supervision | 7 | ⬜ **does not exist.** The engine is a foreground process started by hand |
| `watchdog.py` | 7 | ✅ built 2026-08-07 — §F.6 |

Until Stage 6 exists, the day's decisions come out of SQLite by hand — see
[§I.3](#i3-inspect-what-the-engine-actually-decided).

---

# §G · The daily session, minute by minute

## G.0 The timeline

**No order can exist before the 11:00 bar.** §2.3: *"No orders may be placed
before 11:00 under any circumstance."* It is enforced in three places — the
state machine only activates at `bar_idx >= 18`, the engine only calls
`assert_live_data` at that same point, and no intent is emitted before it.

| Time (ET) | What happens | Needs you? |
|---|---|---|
| 08:00–08:30 | §C fast path, §D gate, TWS logged into paper | ✅ |
| 08:30 | `diagnose.py` → `VERDICT: READY` | ✅ |
| 08:45 | start `watchdog.py` (terminal 2) | ✅ |
| by 09:25 | start `run.py` (terminal 1); pre-open runs: connect, features, gate, capital | ✅ **watch this** |
| 09:25–09:30 | polls; the feed correctly returns **nothing** before the open | no |
| 09:30–10:00 | records bars 0–5 | no |
| 10:00 | morning filter fires on bar 5 | ✅ Check 5 |
| 10:00–11:00 | observes; tracks `session_high`. **Still cannot order** | no |
| **~11:05** | **first arming** — see G.0.1 | ✅ **be back** |
| 11:05–15:55 | ratchet, fills, brackets, re-arm | ✅ |
| 15:55 | flatten | ✅ verify in TWS |
| 15:58 | watchdog's hard deadline — it intervenes if still exposed | ✅ |
| 16:10 | `EOD reconcile: AGREES`; save the evidence | ✅ |
| 23:00 | TWS auto-restarts; the engine reconnects by itself | no |

An 08:00 start with an absence from 09:00 to 11:00 is **structurally** safe, not
safe by luck: the window you miss is the one in which the engine is forbidden
from acting. If it dies while you are away, it dies flat.

### G.0.1 Why "~11:05" and not 11:00

Bar 18 covers 11:00–11:05 and is only delivered once it *closes*. The engine
arms on receipt, so the limit goes live around 11:05–11:06, priced off bars
0–17 — the same anchor the backtest uses at 11:00 — and is then immediately
ratcheted if bar 18 printed a new high.

The backtest's limit rests from 11:00 and can fill during bar 18; live, you are
not in the market for those five minutes. **The gap runs one direction only:
live will miss fills the backtest books, never the reverse.**

## G.1 08:00 — prepare

```powershell
cd C:\TradingModel
git checkout main
git pull
git log --oneline -1                # must be 014e9b4 or later
.\.venv-live\Scripts\Activate.ps1
pip install -r band_lab\live\requirements.txt

git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
Get-ChildItem SOXL_5min_6Years.csv, SOXS_5min_6Years.csv |
    Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
```

Then the §D gate, all four commands, **0 failures**.

Start TWS, log in to the **paper** account, confirm the Live/Paper selector says
Paper and the API port is **7497**. Leave it running. Confirm no other IBKR
session anywhere — including the Mac and any Client Portal browser tab.

## G.2 08:30 — pre-flight

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
python band_lab\live\diagnose.py
```

`VERDICT: READY` or stop. It costs 20 seconds and it is the difference between
finding error 162 at 08:30 and finding it at 11:00.

## G.3 08:45 — terminal 2: the watchdog

**Start it before the engine.** It is the only thing that makes the flatten
guarantee independent of the engine being correct.

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
python band_lab\live\watchdog.py --once      # confirm it can reach TWS

mkdir logs -Force
python -u band_lab\live\watchdog.py 2>&1 |
    Tee-Object -FilePath "logs\$(Get-Date -f yyyyMMdd)-watchdog.log"
```

It sits silent until one of two things is true:

| Trigger | Covers |
|---|---|
| No engine heartbeat for **>2 minutes** during RTH | crash, hang, killed terminal, slept machine |
| Past **15:58** and still holding a position or a working order | an engine that is alive, heartbeating, and wrong — which is what happened on 2026-08-05, -06 and -07 |

Then it does exactly one thing: `reqGlobalCancel`, then market orders to flat.
It cannot open a position — it has no code path that places a limit or a stop.

Normal output:

```
11:01:02 [watchdog info    ] watching | port 7497 clientId=12 | stale>120s or past 15:58 while exposed
11:11:04 [watchdog info    ] ok — engine alive (18s), 1 position(s)
```

Earning its keep:

```
15:58:01 [watchdog critical] INTERVENING — past 15:58 and still exposed ({'SOXS': 1680.0}, 3 working) — §1 forbids holding overnight
15:58:01 [watchdog info    ] global cancel sent
15:58:01 [watchdog critical] SOXS watchdog flatten SELL 1680
15:58:04 [watchdog info    ] FLAT after 1 flatten pass(es)
```

> **It uses clientId 12**, never the engine's 11. If you change `client_id` in a
> config file, change `watchdog_client_id` too — two processes on one id will
> fight.

If it ever prints `HUMAN INTERVENTION REQUIRED`, it tried five times and failed
— go to TWS immediately.

## G.4 by 09:25 — terminal 1: the engine

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1

mkdir logs -Force
python -u band_lab\live\run.py --transmit 2>&1 |
    Tee-Object -FilePath "logs\$(Get-Date -f yyyyMMdd)-live.log"
```

`-u` forces unbuffered output so the log file stays current while the session
runs. Leave this window open and untouched for the whole session. It prints as
it goes; it needs no input.

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

> `--transmit` and `--dry-run` together are refused rather than resolved by
> precedence. A config file also works — `--config path.json` with
> `"transmit": true` — but the flag is preferred because the intent is visible
> in the command line and in the log.

Other flags: `--poll <seconds>` overrides the 30 s bar poll, `--heartbeat
<seconds>` the 900 s status line (0 disables it — do not, the watchdog reads it).

---

# §H · The in-session checks

Watch for these in order. Each has a pass condition. **Write down what you
actually see** — that record is the point of the session.

### ✅ Check 1 — the feature top-up reached the broker

```
09:24:11 [info    ] SOXL: 524 sessions in window | +8 from broker | csv holds 1510 | last session 2026-07-31
09:24:18 [info    ] SOXS: 524 sessions in window | +5 from broker | csv holds 1508 | last session 2026-07-31
```

**Pass:** `+N from broker` with **N > 0**, and `last session` reading the most
recent trading day.

**Fail:** an explicit error —

```
[error   ] SOXL: the broker top-up added no sessions — ATR5 and thr80 are being
           computed from history ending 2026-07-21. Verify before trusting the gate.
```

The CSVs stop at 2026-07-21 (SOXL) and 2026-07-24 (SOXS), so this means the gate
is being computed from stale data. **Stop the run and investigate.** Usually
error 162 — see §K.

> `sessions in window` (524) is the trimmed `thr80` window and `csv holds` is the
> whole file — they are not meant to sum. Only `from broker` and `last session`
> matter here.

### ✅ Check 2 — equity, sleeve capital, and the right port

```
09:24:03 [info    ] pre-open 20260810 | SOXL,SOXS @ 127.0.0.1:7497 clientId=11 | f=1.0 w=0.5 cap=150,000 | TRANSMIT ON
09:24:20 [info    ] equity=150,000 basis=150,000 sleeve_capital=75,000
```

**Pass:** all four of —

- the address ends **`:7497`** (paper). If it says 7496 or 4001, kill it now
- the mode is what you intended
- `equity=` matches the paper balance
- `sleeve_capital=` is half the capped basis

**Fail:** a `sleeve_capital` under a few hundred dollars means the sleeve sizes
to 0 shares and silently never trades.

### ✅ Check 3 — the gate is ON for both sleeves

No `GATE OFF` line should appear.

**Fail:** `SOXL GATE OFF: ...`. If the reason is `atr5` and the value looks like
last week's, the top-up failed — see Check 1. If it is `market_closed`, TWS
thinks today is a holiday.

### ✅ Check 4 — no bars before 09:30, and no repeats

Between starting the engine and 09:30, **no bar-related output should appear at
all**. The first bars follow the 09:35 close.

**Fail:** bar activity before 09:30, or bar indices that jump backwards. That
would mean prior-session bars are being read as today's — the defect fixed on
2026-08-02.

### ✅ Check 5 — the 10:00 filter fires once

Shortly after 10:00, either nothing (the day is ON) or:

```
10:00:22 [info    ] SOXL STAND DOWN: or30>=thr80 and pos10<2/3
```

**Pass:** at most one filter line per sleeve, at ~10:00 and not before.

### ✅ Check 6 — 11:00 arming

At ~11:05, for each sleeve still ON, a resting BUY LMT appears in TWS and in the
log. On a dry run the line must read **`DRY RUN — not sent:`**.

**🔴 STOP IMMEDIATELY** if you are in a dry run and an order appears *without*
that prefix, or appears in TWS at all. `Ctrl+C`, check TWS for working orders,
cancel anything you find.

**Fail (soft):** `NotLiveDataError` → market data is delayed. Fix §E.4.

### ✅ Check 7 — the bracket covers the whole position

**This is defect 8, the most serious found so far.** On 2026-08-06 IBKR filled
541 shares as 300 + 210 + 31; the bracket was sized from the first execution, so
**241 shares carried no stop and no target** while the state machine believed it
held 300.

The fix sizes the protective legs from `broker.position()` after every entry
execution. **Verify it on real fills:** after any entry, the SELL STP quantity
in TWS must equal the position quantity. Check it every time.

### ✅ Check 8 — no `BAR GAP` errors, all session

```
11:03:01 [error   ] SOXL BAR GAP: 18 -> 21; session_high may be understated
```

**Pass:** zero occurrences. A missed bar understates `session_high`, which is
the anchor everything ratchets from.

**Fail:** any occurrence. Note the time and the indices.

### The three open assumptions — check these deliberately

`PHASE2_PLAN.md` §6. No amount of offline work settles them; **no exit has ever
filled against IBKR.**

#### §6.1 — does the protective stop outlive the engine? *(most important)*

After the first entry fills and its bracket is placed:

1. Confirm in TWS that both a **SELL LMT** and a **SELL STP** are working.
2. Press `Ctrl+C` in the engine window to kill the process.
3. **Look at TWS. The SELL STP must still be there.**

If the stop disappears when the engine dies, the system has no protection
against an adverse move while it is down. **That is a stop-everything finding.**
Record it and do not run unattended until it is resolved.

Restart afterwards — it reconciles from the broker on connect and resumes:

```powershell
python -u band_lab\live\run.py --transmit 2>&1 |
    Tee-Object -FilePath "logs\$(Get-Date -f yyyyMMdd)-live.log" -Append
```

Confirm it does not open a duplicate position.

#### §6.3 — does OCA cancel the sibling?

When a target fills, the sibling stop must go to `Cancelled` in TWS by itself.
If both legs can execute, the sleeve ends up **short** — which the strategy
forbids absolutely.

#### §6.2 — does the 23:00 TWS restart reconcile cleanly?

Leave everything running overnight. Next morning, confirm the engine reconnected
and that `fills` and `stop_outs` for the prior day did not double-count.

### What a normal result looks like

**Plan on ~40 bp/ON-day for SOXL and ~30 for SOXS.** A run at 20–40 bp is
consistent with the evidence and is **not** a sign the engine is broken — see
§F.4 for why §8's 61.9 / 48.1 are an upper bound.

The engine is ON ~52% of sessions, so four weeks gives only ~10–11 ON-days per
sleeve. **A single week proves nothing.** Investigate structural breaks — fill
counts or ON-day rates off by >20% for a month — not noise. The first ~3
sessions are shakedown and are excluded from the evidence set.

---

# §I · Close-out and evidence

## I.1 15:55–16:10

```
15:55:02 [info    ] 15:55 flatten
15:55:07 [info    ] all sleeves flat
15:55:09 [info    ] SOXL EOD fills=2 stops=0 pnl=38.4bp agrees=True
15:55:10 [info    ] SOXS EOD fills=0 stops=0 pnl=0.0bp agrees=True

EOD reconcile: AGREES
```

**Pass:** `EOD reconcile: AGREES`, no `critical` line anywhere in the session,
and — **with your own eyes, in TWS** — no position and no working order. The log
line saying flat is not the check; three consecutive sessions in August 2026
printed a flatten that did not flatten. That is what the watchdog is for, and it
is also why you look.

## I.2 Save the evidence

```powershell
cd C:\TradingModel
$d = Get-Date -f yyyyMMdd
Copy-Item band_lab\live\out\live.db "$env:USERPROFILE\Desktop\live-$d.db"
```

The log is already at `logs\<yyyyMMdd>-live.log` and
`logs\<yyyyMMdd>-watchdog.log`.

## I.3 Inspect what the engine actually decided

Until `report.py` exists (Stage 6), this is the instrument:

```powershell
python -c "import sqlite3;c=sqlite3.connect(r'band_lab\live\out\live.db');c.row_factory=sqlite3.Row;print(*[dict(r) for r in c.execute('SELECT * FROM daily ORDER BY session DESC LIMIT 4')],sep='\n')"
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

```powershell
python band_lab\live\replay.py   ; echo "exit=$LASTEXITCODE"
```

If anything is unexplained, repeat the dry run. Calendar time is cheap; a wrong
first order is not.

---

# §J · Stopping, restarting, emergency

## Stopping safely

`Ctrl+C` in the engine window stops the process. **It does not flatten.** If a
position is open when you stop it:

1. Restart the engine — it reconciles and resumes; or
2. Flatten manually in TWS and cancel all working orders.

**Never leave a position open overnight.** It is design priority #1 and the
whole strategy is only safe because of it.

## Restarting after a crash

Just restart it. State is established by reconciling with the broker, never from
memory, so starting at 13:00 after a crash produces the same state as having run
since 09:30. **Check TWS for orphaned orders first.**

## Can it be left unattended?

| Mode | Answer |
|---|---|
| `--dry-run` | **Yes.** `IBBroker` refuses to transmit at the adapter. The worst outcome is losing a day's observations |
| `--transmit` | **No.** Four specific things are missing, below |

| Missing | Consequence unattended |
|---|---|
| Alerting | None exists — no push, email or desktop. The console is the only monitor |
| Service supervision | Process dies → the day ends silently, possibly with a position open |
| §6.1 unverified | Whether the protective stop survives the engine dying is *still an open question* |
| `report.py` | No daily diff against the backtest, so a slow drift is invisible |

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
| **Error 10089** "requires additional subscription for API… Delayed market data is available" | The account has **no live L1 entitlement for API use**. §4 makes delayed data a refusal-to-trade condition, so the sleeve stands down at 11:00. Subscribe in Client Portal → Settings → Market Data Subscriptions, then share to paper (§E.4) |
| **Error 162** "Trading TWS session is connected from a **different IP address**" | The same IBKR login is active somewhere else — **the Mac**, Client Portal in a browser, the mobile app, or a second TWS. IBKR serves market data to one location at a time. **Log out everywhere else, then restart the engine.** Not an entitlement problem. This includes the Client Portal tab you used to buy the subscription |
| `feature history is insufficient or stale — refusing to start` | The broker top-up returned nothing (usually error 162), so ATR5/thr80 would come from the CSV's last session. §2.2 forbids trading on stale data. Fix the top-up and re-run — do **not** work around it |
| `+0 from broker` in the pre-open line | Same cause. Features are stale to 2026-07-21. Do not trade the session |
| `replay.py` fails loading CSVs | LFS files are still pointers — re-run §C.2's `git lfs pull` |
| `pytest band_lab\live` collects nothing | Run from `C:\TradingModel`; `conftest.py` sets `sys.path` |
| `ZoneInfoNotFoundError` | `pip install tzdata` — Windows ships no IANA database. §B.3 |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, once |
| `python` opens the Microsoft Store | Python is not on PATH — reinstall with "Add python.exe to PATH" |
| Connection refused | Port 7497 vs 7496; trusted IP 127.0.0.1; TWS actually logged into **paper** |
| `NotLiveDataError` | Market data is delayed — §E.4 |
| Orders do nothing | Read-Only API is ON, or a precaution dialog is waiting on screen in TWS (§E.2) |
| Bar indices are negative | TWS is set to a non-ET timezone. `Bar.idx` is minutes since 09:30 ET; `America/Los_Angeles` gives idx −36 and the engine decides nothing, silently. `diagnose.py` catches it |
| `EQUIVALENCE: FAIL` after a code change | The gate doing its job. The sleeve's decisions changed — diff before going further |
| `BAR GAP` errors | A poll missed a bar; `session_high` may be understated. Record the indices |
| Watchdog prints `HUMAN INTERVENTION REQUIRED` | It tried five times to flatten and failed. **Go to TWS now** |
| Watchdog and engine fight over orders | Both are on the same client id. Engine is 11, watchdog 12 (`watchdog_client_id`) |
| Engine crashed mid-session | Restart it — it reconciles from the broker, not from memory. Check TWS for orphaned orders first |

---

# §L · Command index — every runnable file

Prefix every line with:

```powershell
cd C:\TradingModel ; .\.venv-live\Scripts\Activate.ps1
```

| Stage | File | Command | Expected |
|---|---|---|---|
| Research | `band_analysis.py` | `python band_lab\band_analysis.py` | `band_lab\out\report.txt` + tables |
| Research | `churn_harvest.py` | `python band_lab\churn_harvest.py` | `out\churn_grid.csv` |
| Research | `regime_gate.py` | `python band_lab\regime_gate.py` | gated results |
| Research | `v1v3_adaptive_tests.py` | `python band_lab\v1v3_adaptive_tests.py` | `out\v1v3_results.csv` |
| Research | `v2_anchor_tests.py` | `python band_lab\v2_anchor_tests.py` | `out\v2_*.csv` |
| Research | `v5_start_time_tests.py` | `python band_lab\v5_start_time_tests.py` | `out\v5_results.csv` |
| Research | `v5_corrected_rerun.py` | `python band_lab\v5_corrected_rerun.py` | `out\v5_corrected_results.csv` |
| Research | `v6_eod_exit_tests.py` | `python band_lab\v6_eod_exit_tests.py` | `out\v6_results.csv` |
| Research | `v8_direction_tests.py` | `python band_lab\v8_direction_tests.py` | `out\v8_results.csv` |
| Research | `v9_filter_tests.py` | `python band_lab\v9_filter_tests.py` | `out\v9_results.csv` |
| Research | `v10_gate_tests.py` | `python band_lab\v10_gate_tests.py` | `out\v10_results.csv` |
| Research | `v11_sizing_tests.py` | `python band_lab\v11_sizing_tests.py` | `out\v11_results.csv` |
| Research | `v13_streak_tests.py` | `python band_lab\v13_streak_tests.py` | `out\v13_results.csv` |
| Research | `v14_pair_protocol.py` | `python band_lab\v14_pair_protocol.py` | pair protocol tables |
| Research | `v15_weekly_sweep.py` | `python band_lab\v15_weekly_sweep.py` | `out\v15_*.csv` |
| Research | `cap_sweep.py` | `python band_lab\cap_sweep.py` | `out\cap_sweep.csv` |
| Research | `sizing_verification.py` | `python band_lab\sizing_verification.py` | `out\sizing_verification.csv` |
| Research | `etf_scaling_test.py` | `python band_lab\etf_scaling_test.py` | `out\etf_scaling_*.csv` |
| Research | `spxl_scaling_test.py` | `python band_lab\spxl_scaling_test.py` | `out\spxl_scaling.csv` |
| Research | `transfer_test.py` | `python band_lab\transfer_test.py` | `out\transfer_test.csv` |
| Research | `put_overlay_test.py` | `python band_lab\put_overlay_test.py` | `out\put_overlay_curves.csv` |
| Research | `walk_forward_and_combo.py` | `python band_lab\walk_forward_and_combo.py` | `out\wf_*.csv`, `out\combo_*.csv` |
| V16 | `v2_dev\churn_joint_test.py` | `python band_lab\v2_dev\churn_joint_test.py [--quick]` | `v2_dev\out\v16_*.csv` |
| V17 | `v2_dev\trade_cap_test.py` | `python band_lab\v2_dev\trade_cap_test.py` | `v2_dev\out\v17_*.csv` |
| V18 | `v2_dev\vol_gate_test.py` | `python band_lab\v2_dev\vol_gate_test.py` | `v2_dev\out\v18_*.csv` |
| Phase 1 | `phase1\` suite | `python -m pytest band_lab\phase1 -q` | **59 passed** |
| Phase 1 | `phase1\parity.py` | `python band_lab\phase1\parity.py` | 16 §8 numbers, **exit 0** |
| Phase 1 | `phase1\cost_model.py` | `python band_lab\phase1\cost_model.py` | cost tables |
| P2 S1 | `live\replay.py` | `python band_lab\live\replay.py` | `STAGE 1 EQUIVALENCE: PASS`, **exit 0** |
| P2 S1 | `live\replay.py --sizing` | `python band_lab\live\replay.py --sizing` | the S9 report |
| P2 S1 | `live\replay.py --fill-models` | `python band_lab\live\replay.py --fill-models` | the S10 report |
| P2 S1 | `live\intrabar.py` | `python band_lab\live\intrabar.py --symbol SOXL --start 2022-01-01` | 42.5 bp SOXL / 34.2 SOXS |
| P2 S1 | `live\fetch_1min.py` | `python band_lab\live\fetch_1min.py --symbol SOXL --start 2022-01-01 --port 7497` | rebuilds the 1-min CSV; needs TWS; hours |
| P2 S2–4 | `live\` suite | `python -m pytest band_lab\live -q` | **0 failures** |
| P2 S2–4 | `live\diagnose.py` | `python band_lab\live\diagnose.py` | `VERDICT: READY` |
| P2 S2–4 | `live\run.py` dry | `python band_lab\live\run.py --dry-run` | every order `DRY RUN — not sent:` |
| P2 S5 | `live\watchdog.py` check | `python band_lab\live\watchdog.py --once` | one verdict, changes nothing |
| P2 S5 | `live\watchdog.py` | `python band_lab\live\watchdog.py` | terminal 2, all session |
| P2 S5 | `live\run.py` live | `python band_lab\live\run.py --transmit` | `*** TRANSMIT ON ***`, port 7497 |
| P2 S6 | `live\report.py` | — | ⬜ **not built** |
| P2 S7 | `live\risk.py` | — | ⬜ **not built** |
