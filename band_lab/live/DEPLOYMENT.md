# Deployment — IBKR TWS paper (macOS §§1–8, Windows §13)

Setup and runbook for the Phase 2 engine. Build stages are in
[PHASE2_PLAN.md](PHASE2_PLAN.md); Stage 1's result is in
[PHASE2_PARITY.md](PHASE2_PARITY.md).

> **What exists today: Stages 1–4, runnable.** Strategy core, sleeve state
> machine, broker adapter, SQLite store, OrderManager, the §5 timetable, and
> `run.py` — the service entrypoint that drives a whole day end to end. 130
> tests, all green against a `FakeIB` double. **No code here has ever
> connected to IBKR.** Stage 5 is a launch, not a code drop: §12 is the
> go-live procedure, and §12.1 is the next action.
> Stages 6 (reporting) and 7 (watchdog, day-loss breaker) are built *during*
> the paper run, per PHASE2_PLAN.md §5 — they protect capital that is not at
> risk on paper, but they are prerequisites for Phase 3.

---

## 1. Machine prerequisites

A Mac that stays powered and online 09:30–16:00 ET every weekday. The
strategy is not latency-sensitive (5-minute granularity) but it *is*
uptime-sensitive inside the session.

```bash
# Homebrew, if not already present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python@3.12 git-lfs
git lfs install
```

Python 3.11+ is required (`zoneinfo`, modern dataclasses). Check with
`python3 --version`.

## 2. Repository and data

The 5-minute history is git-lfs and arrives as a pointer file on a fresh
clone. Everything in Stage 1 needs the real files.

```bash
cd ~/TradingModel                 # wherever the repo lives
git checkout claude/band-lab-trading-strategy-plan-6zxt67
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"

# sanity: these must be ~7.7MB and ~8.7MB, not 132 bytes
ls -lh SOXL_5min_6Years.csv SOXS_5min_6Years.csv
```

## 3. Python environment

```bash
cd ~/TradingModel
python3 -m venv .venv-live
source .venv-live/bin/activate
pip install -U pip
pip install -r band_lab/live/requirements.txt
```

Use a **separate** venv from the repo's existing `env/` — that one holds only
numpy and scipy for the research scripts and should not be disturbed.

## 4. Verify the install

Four commands. All four must pass before Stage 2 work begins; they are also
the regression gate to re-run after any change.

```bash
cd ~/TradingModel
source .venv-live/bin/activate

python3 -m pytest band_lab/phase1 -q      # expect: 59 passed
python3 band_lab/phase1/parity.py         # expect: exit 0, all sections green
python3 band_lab/live/replay.py           # expect: STAGE 1 EQUIVALENCE: PASS
python3 -m pytest band_lab/live -q        # expect: 58 passed
```

`echo $?` after `parity.py` and `replay.py` — both return 0 when green and
non-zero when not, so they can be wired into a pre-flight check later.

## 5. The Stage 1 diagnostics

Two standing reports, both documented in [PHASE2_PARITY.md](PHASE2_PARITY.md):

```bash
python3 band_lab/live/replay.py --sizing        # S9  sizing basis (§2.4)
python3 band_lab/live/replay.py --fill-models   # S10 same-bar re-entry exposure
```

`--fill-models` is the one to read before deciding how much capital this
deserves. It takes ~2 minutes.

---

## 6. TWS paper configuration

Do this before Stage 2. Settings are under **File → Global Configuration**
(TWS names shift slightly between versions; where a label differs, the
intent is what matters).

**API → Settings**

| Setting | Value | Why |
|---|---|---|
| Enable ActiveX and Socket Clients | **on** | the API connection itself |
| Socket port | **7497** | TWS paper default (live is 7496; Gateway is 4002/4001) |
| Trusted IPs | **127.0.0.1** | engine runs on the same Mac |
| Read-Only API | **off** | the engine must place orders |
| Download open orders on connection | **on** | required by reconcile-on-connect (`PHASE2_PLAN.md` §3) |
| Create API message log file | **on** | Phase 2 wants the audit trail |
| Master API client ID | leave unset for now | Stage 3 decides; the watchdog needs its own client ID |

**API → Precautions**

The engine sends plain limit, stop and market orders in ordinary sizes.
Order-precaution dialogs cannot be answered by a headless process, so the
relevant "Bypass … for API orders" boxes need to be ticked — but tick them
deliberately, one at a time, rather than enabling everything. This is the
one area where a wrong setting turns a rejected order into a silent hang, so
Stage 2 will log every rejection explicitly.

**Configuration → Lock and Exit**

| Setting | Value |
|---|---|
| Auto restart | **23:00** (per your decision) |
| Never lock Trader Workstation | on, or set the auto-lock well outside RTH |

**Market data**

Paper accounts see live data only if the live account's subscriptions are
shared to it (Client Portal → Settings → Account Settings → Paper Trading
Account → share market data). §4 of the implementation spec makes delayed
data a refusal-to-trade condition, and Stage 2 asserts it at startup rather
than trusting the setting.

**Still to confirm against IBKR documentation** (blocked from my build
environment — `PHASE2_PLAN.md` §6): whether a weekly manual re-login is
still required alongside the 23:00 auto-restart, whether API orders and
IB-held stops survive that restart, and the "auto-cancel orders on API
disconnect" behaviour. These decide how much the watchdog has to do.

## 7. Keeping the Mac awake (macOS; Windows is §13.5)

macOS sleeping mid-session is the most likely cause of a missed bar or an
unmanaged position.

```bash
# on AC power: never sleep the system or the disk; the display may sleep
sudo pmset -c sleep 0 disksleep 0 displaysleep 10 womp 1

# verify
pmset -g custom
```

Also:

- **System Settings → Users & Groups → Automatic login: on**, so the machine
  comes back by itself after a power cut. Note this requires FileVault to be
  **off** — a real security trade-off on a machine holding broker
  credentials. If FileVault stays on, a reboot needs a human, and the
  watchdog's flatten path becomes correspondingly more important.
- **System Settings → General → Software Update**: turn off automatic
  install of macOS updates (they reboot the machine).
- Keep the engine and TWS out of App Nap by running the engine from a
  `launchd` job (Stage 7) rather than from a Terminal window that may be
  backgrounded.
- Belt and braces while attended: `caffeinate -dimsu -w $(pgrep -f engine.py)`.

## 8. ntfy alerting

```bash
brew install ntfy                     # CLI, optional
# pick a long random topic — on ntfy.sh the topic name is the ONLY secret
python3 -c "import secrets; print('bandlab-' + secrets.token_hex(8))"

# test it (replace with your topic)
curl -d "band_lab test alert" https://ntfy.sh/bandlab-xxxxxxxxxxxxxxxx
```

Install the ntfy app on the phone and Mac and subscribe to that topic.

**Privacy note, worth a decision:** alerts will carry positions, fills and
P&L. On the public `ntfy.sh` server anyone who guesses or learns the topic
can read them, and messages pass through a third party in clear text. A
random topic is adequate for paper trading; before Phase 3 goes live with
real money, either self-host ntfy or switch to authenticated topics with
access control.

Alert channels for Phase 2 (email + push + desktop, per your decision):

| channel | mechanism | Stage |
|---|---|---|
| push | ntfy topic above | 4 |
| email | SMTP — credentials needed (app password if Gmail) | 4 |
| desktop | macOS notification via `osascript`/`terminal-notifier` | 4 |

## 9. Configuration file (Stage 2)

The engine will read `band_lab/live/config.local.toml`, which is gitignored
and never committed:

```toml
[broker]
host = "127.0.0.1"
port = 7497                # TWS paper
client_id = 11             # engine; the watchdog uses its own
account = "DU1234567"

[capital]
notional_cap = 150000.0    # capital_basis = min(NetLiquidation, this)
w_per_sleeve = 0.50        # -> $75,000 per sleeve
f = 1.00

[sleeves]
symbols = ["SOXL", "SOXS"]

[alerts]
ntfy_topic = "bandlab-xxxxxxxxxxxxxxxx"
email_to = "you@example.com"
smtp_host = "smtp.gmail.com"
desktop = true

[paths]
db = "band_lab/live/state/engine.db"
logs = "band_lab/live/state/logs"
```

Every strategy parameter is deliberately **absent** — those live in
`phase1/spec_constants.py` and `validate_config` rejects any attempt to
override them (§6.8, §12).

## 10. Daily runbook (Stage 5 onward)

| Time (ET) | What happens |
|---|---|
| 06:00 | pre-open job: refresh daily bars, ATR5, thr80, gate, sleeve capital |
| 09:30 | begin recording bars — no orders |
| 10:00 | morning filter; push alert with the ON/STAND-DOWN decision |
| 11:00 | activate: resting buy limit goes live |
| 15:55 | flatten; push alert confirming flat |
| 16:10 | reconcile against IBKR executions; daily shadow-parity report |
| 23:00 | TWS auto-restart; engine reconnects and reconciles |

## 11. Troubleshooting

| Symptom | Check |
|---|---|
| `replay.py` fails to load CSVs | `git lfs pull` — the files are 132-byte pointers otherwise |
| `pytest band_lab/live` collects nothing | run from the repo root; `conftest.py` sets `sys.path` |
| equivalence FAILS after a code change | that is the gate doing its job — the sleeve's decisions changed; diff before going further |
| TWS API refuses the connection | port 7497 vs 7496, trusted IP, and whether TWS is actually logged in to the **paper** account |
| orders silently do nothing | Read-Only API is on, or an order-precaution dialog is waiting on screen |

---

## 12. Stage 5 — going live on paper

This is the procedure. It is a launch, not a code change: everything it runs
already exists and is tested. Work through it in order and stop at the first
step that does not behave as described.

### 12.0 Before anything else

`PHASE2_PLAN.md` §6 lists seven questions that could not be verified against
IBKR's documentation from the build environment (outbound access to
`interactivebrokers.github.io` is blocked, and still was at this build). Each
is marked `ASSUMPTION §6.n` at its use site in `broker.py`. **Three of them
are answered by the first session and should be checked deliberately, not
noticed later:**

| # | assumption in code | how to check on day one |
|---|---|---|
| §6.1 | `place_stop` uses a plain `STP`, assumed to be broker-side and to survive an API disconnect | after a bracket goes on, kill the engine process. The stop must still be visible in TWS. **This is the most safety-critical item in the system** — §6.1 requires a stop that outlives the engine. |
| §6.3 | `ocaType=1` on the bracket | fill a target and confirm the sibling stop cancels, and that the group survives a disconnect |
| §6.2 | TWS auto-restart at 23:00 | confirm the engine reconnects and `on_connect()` reconciles without duplicate counting |

### 12.1 Dry run with transmit off — half a day, not a week

`PHASE2_PLAN.md` Stage 4's acceptance: one live session with orders not
transmitted, decisions logged, then compared against an EOD replay of the same
bars.

```bash
source .venv-live/bin/activate
python3 -m pytest band_lab/live -q          # 115 tests, all must pass
python3 band_lab/live/replay.py             # exit 0
python3 band_lab/phase1/parity.py           # exit 0
```

Then run one real session against TWS with transmit off:

```bash
python3 band_lab/live/run.py --dry-run
```

`--dry-run` forces `transmit=False`, which puts the adapter in `readonly` mode
— decisions are computed, logged to SQLite and printed; nothing reaches the
market. Confirm four things:

| check | where |
|---|---|
| gate fires at 06:00 with the ATR5 you expect | console, and the `daily` table |
| filter fires at 10:00 | `daily.filter_reason` |
| the limit *would* arm at 11:00 at the price `replay.py` says | `decisions` table vs an EOD replay of the same bars |
| **no `BAR GAP` errors all session** | console `[error]` lines, and `feed.missing_before()` |

The bar-gap check is the one to watch. A missed bar understates
`session_high`, which is the anchor everything ratchets from, and the polled
feed is the only place that can silently lose one.

### 12.2 Go live

Only after 12.1 is clean:

1. TWS paper, Read-Only API **off**, auto-restart 23:00, trusted IP 127.0.0.1.
2. `f = 1.00`, `w = 0.50` — §12 values, unchanged.
3. Both sleeves from day one.
4. **First ~3 sessions are shakedown and are excluded from the evidence set**
   (PHASE2_PLAN.md Stage 5).

### 12.3 What the run is actually for

Per `PHASE2_PLAN.md` §1 this is a plumbing and cost-data run, not a fill-realism
run — IBKR's paper simulator fills a resting limit when the market trades
through it, which is close to the backtest's own assumption, so paper largely
confirms the backtest by construction.

**The one exception is `PHASE2_PARITY.md` S10/S11, and it is the reason to
launch.** S10 is a question of *time ordering*, not queue position: a re-entry
order sent after an exit can only fill against prints that occur after it is
sent. If the backtest's re-entry prices are not achievable, paper fills show it
in the fill prices themselves, within days.

Every fill is logged with the quoted bid/ask at that moment (`fills` and
`quotes` tables). Two questions to ask of that data in week one:

1. **Did any fill occur without the quote reaching the limit?** If yes, paper
   cannot validate A1 at all and the §8 baselines stay unfalsified.
2. **On same-bar re-entries, is the achieved price at or worse than the price
   just sold?** S11 predicts a systematic gap here. This is the sharper and
   faster test — sharper than watching aggregate bp, which needs months.

### 12.4 What to expect, so a normal result is not misread

`PHASE2_PARITY.md` S11, measured on 1-minute data:

| | §8 published (upper bound) | 1-minute planning figure |
|---|---:|---:|
| SOXL | 61.9 net bp/ON-day | **~40** |
| SOXS | 48.1 net bp/ON-day | **~30** |

**A paper run at 20–40 bp/ON-day is consistent with the evidence and is not
a sign the engine is broken.** Investigate structural breaks — >20% for a
month on fill counts or ON-day rates — not noise. The engine is ON ~52% of
sessions, so four weeks yields only ~10–11 ON-days per sleeve; a single week
proves nothing.

### 12.5 Still missing before Phase 3 (real money)

Built during the run, per PHASE2_PLAN.md Stage 5-7 — on paper they protect
capital that is not at risk, but **none of them is optional before Phase 3**:

- `report.py` — the 16:10 daily shadow-parity report (Stage 6). This is the
  instrument that answers 12.3, so build it first, in week one.
- `risk.py` — the −8.5% day-loss breaker. `Engine.day_loss_breached()`
  measures the condition today but nothing acts on it.
- `watchdog.py` — separate process, heartbeat → `reqGlobalCancel` + flatten.
- Alerting (email/push/desktop) and service supervision (launchd).

---

## 13. Windows 11

The engine is platform-neutral — no signal handlers, no `fork`, no hardcoded
POSIX paths, and every path built with `os.path.join`. Only the *host*
instructions differ. §§1–8 above are macOS; this section is their Windows
equivalent. §§9–12 apply unchanged.

**The one that bites immediately:** on Windows `python3` usually does not
exist. Every command in this document written as `python3 ...` becomes
`python ...` (or `py -3 ...`). The engine itself does not care.

### 13.1 Prerequisites

```powershell
winget install --id Git.Git -e
winget install --id GitHub.GitLFS -e
winget install --id Python.Python.3.12 -e
git lfs install
```

Open a **new** PowerShell window afterwards so `PATH` picks them up. Verify:

```powershell
python --version      # 3.11 or newer
git lfs version
```

### 13.2 Repository and data

```powershell
cd $HOME\TradingModel
git checkout claude/band-lab-trading-strategy-plan-6zxt67
git pull
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv,SOXL_1min.csv,SOXS_1min.csv"

# sizes must be ~7.7MB, ~8.7MB, ~42.9MB, ~48.2MB — not ~130 bytes
Get-ChildItem SOXL_5min_6Years.csv,SOXS_5min_6Years.csv,SOXL_1min.csv,SOXS_1min.csv |
  Select-Object Name,Length
```

The CSVs are marked `-text` in `.gitattributes`, so Git will not rewrite their
line endings. If a size looks wrong, the pull did not complete — re-run it
rather than proceeding.

### 13.3 Python environment

```powershell
cd $HOME\TradingModel
python -m venv .venv-live
.\.venv-live\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r band_lab\live\requirements.txt
```

If activation is blocked by execution policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

(Scoped to the process — it does not change machine policy.)

### 13.4 Verify the install — all offline, run these first

```powershell
python -m pytest band_lab\phase1 -q     # 59 passed
python band_lab\phase1\parity.py        # exit 0
python band_lab\live\replay.py          # STAGE 1 EQUIVALENCE: PASS
python -m pytest band_lab\live -q       # all passed
```

Check exit codes with `$LASTEXITCODE` (the PowerShell equivalent of `echo $?`).
None of these need TWS, a market, or a network — they are the right thing to
run on a weekend.

### 13.5 Keeping the machine awake

macOS `pmset` becomes `powercfg`. Run in an **elevated** PowerShell:

```powershell
powercfg /change standby-timeout-ac 0     # never sleep on AC
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 15    # the display may sleep
powercfg /query SCHEME_CURRENT            # verify
```

Also:

- **Windows Update** is the biggest unattended-operation risk on this
  platform: it reboots. Set *Active hours* to cover 09:00–17:00 ET at minimum
  (Settings → Windows Update → Advanced options). Windows Pro can defer
  updates further via Group Policy; Home cannot fully prevent them, so expect
  an occasional forced restart and rely on the engine's reconcile-on-connect.
- **Screen lock is fine** — TWS and the engine keep running. What matters is
  that the machine comes *back* after a reboot.
- If you want automatic login after a reboot, note the same trade-off as
  FileVault on macOS: it is incompatible with full-disk encryption (BitLocker)
  requiring a boot PIN. A machine holding broker credentials should probably
  keep BitLocker and accept that a reboot needs a human.

### 13.6 Service supervision (Stage 7, not yet)

`launchd` becomes **Task Scheduler**. When Stage 7 lands, the task wants:
trigger *At startup*, "Run whether user is logged on or not", "Run with
highest privileges", and *Settings → If the task fails, restart every 1
minute*. Not required for the paper run, which can be started by hand.

### 13.7 Alerting

**No notifier is implemented yet** — email/push/desktop is Stage 7 work, so
nothing macOS-specific needs porting. When it lands, the Windows desktop
channel is a PowerShell toast (the `BurntToast` module) rather than
`osascript`; ntfy and SMTP are platform-neutral and unchanged.

### 13.8 TWS

Identical to §6 — same settings, same ports, same paper account. The
installer puts it in `C:\Jts` by default; Global Configuration is in the same
place in the UI. The 23:00 auto-restart setting is unchanged.

> **Unverified on Windows.** These instructions were written without a
> Windows machine to test them on. The PowerShell and `winget` invocations
> follow documented syntax but have not been executed; the Python engine
> itself is exercised by the full test suite on every platform it runs on.
> Report anything that does not behave as written.
