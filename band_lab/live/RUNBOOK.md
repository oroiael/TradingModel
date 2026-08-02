# Runbook — Windows 11, IBKR TWS paper

**Instructions only.** What to type, in what order, and what you should see.
No explanation of why — that is in
[`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) and the documents it maps.

Two rules while working through this:

1. **Do the sections in order.** Each one assumes the previous one passed.
2. **Stop at the first step that does not behave as described.** Do not work
   around it. Every check here exists because something can go silently wrong
   underneath it.

Conventions: `C:\TradingModel` is used as the repo location — substitute yours.
All times are **America/New_York (ET)**. Commands are PowerShell.

---

# §1 · Install the machine — one time

Skip this section if `python --version`, `git --version` and `git lfs version`
all already answer.

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

---

# §2 · Get the code and the data — one time

```powershell
cd C:\
git clone https://github.com/oroiael/TradingModel.git
cd C:\TradingModel
git checkout main
git pull
```

> Do **not** use the branch name printed in `DEPLOYMENT.md` §2. It was merged
> and deleted; `main` is current.

Pull the two 5-minute price files. They are stored in Git LFS and arrive as
132-byte pointer files otherwise, and nothing downstream works:

```powershell
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
```

**Check — this must show megabytes, not bytes:**

```powershell
Get-ChildItem SOXL_5min_6Years.csv, SOXS_5min_6Years.csv |
    Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
```

```
Name                     MB
----                     --
SOXL_5min_6Years.csv    7.4
SOXS_5min_6Years.csv    8.3
```

If either reads `0` MB, the LFS pull did not work. Stop and fix it.

Create the Python environment:

```powershell
cd C:\TradingModel
python -m venv .venv-live
.\.venv-live\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r band_lab\live\requirements.txt
```

> If PowerShell refuses to run `Activate.ps1`, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

# §3 · Verify the install — four commands, all must pass

**Run this whole block every time before a trading session**, not just once.
It is the regression gate.

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1

python -m pytest band_lab\phase1 -q
python band_lab\phase1\parity.py  ; echo "exit=$LASTEXITCODE"
python band_lab\live\replay.py    ; echo "exit=$LASTEXITCODE"
python -m pytest band_lab\live -q
```

Expected, exactly:

| Command | Must show |
|---|---|
| `pytest band_lab\phase1` | `59 passed` |
| `parity.py` | a table ending in the §8 numbers, then `exit=0` |
| `replay.py` | `STAGE 1 EQUIVALENCE: PASS`, then `exit=0` |
| `pytest band_lab\live` | `144 passed` |

`parity.py` takes ~2 minutes and `replay.py` ~1 minute. Anything other than the
above — a failure, a different count, a non-zero exit — is a stop.

---

# §4 · Configure TWS paper — one time

Install **Trader Workstation** from interactivebrokers.com and log in to the
**paper** account (the login screen has a Live/Paper selector — it must say
Paper).

### 4.1 API settings

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

### 4.2 Precautions

**API → Precautions** — tick the "Bypass … for API orders" boxes one at a time,
deliberately. A precaution dialog cannot be answered by a headless process; an
un-bypassed one turns a rejected order into a silent hang.

### 4.3 Restart schedule

**Configuration → Lock and Exit**

| Setting | Value |
|---|---|
| Auto restart | **23:00** |
| Never lock Trader Workstation | ON |

### 4.4 Market data — the engine refuses to trade without this

Paper accounts see live data only if the live account's subscriptions are shared
to them: **Client Portal → Settings → Account Settings → Paper Trading Account →
share market data**.

**Check:** in TWS, add SOXL to a watchlist. The bid/ask must tick during market
hours without a delayed-data banner. If it shows delayed data, the engine will
stand down at 11:00 and the session is wasted.

### 4.5 Confirm the account can actually trade the size

In TWS: **Account → Account Window**. Note **NetLiquidation**.

The engine computes `sleeve_capital = 0.50 × min(NetLiquidation, 150,000)` and
`shares = floor(sleeve_capital / price)`.

| NetLiquidation | Per sleeve | Shares at SOXL ≈ $115 |
|---|---:|---:|
| $1,000,000 (IBKR paper default) | $75,000 | 652 |
| $150,000 | $75,000 | 652 |
| $50,000 | $25,000 | 217 |
| $1,000 | $500 | 4 |
| $250 | $125 | **1** |
| under $230 | under $115 | **0 — the sleeve never trades** |

If NetLiquidation is small, reset the paper account's balance in Client Portal
before Monday. The published cost figures assume $75,000 per sleeve.

### 4.6 Stop the machine sleeping

PowerShell **as Administrator**:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 10
```

Also: **Settings → Windows Update → Advanced options** — set active hours to
cover 09:00–17:00 so it does not reboot mid-session.

---

# §5 · Monday 2026-08-03 — the dry run

**Transmit is OFF. Nothing reaches the market.** This is Stage 4's acceptance
and it must be clean before any order is ever sent.

## 5.1 — 08:30 ET, before the open

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
git pull
```

Run the four verification commands from **§3**. All four must pass.

Start TWS and log in to the paper account. Leave it running and logged in.

## 5.2 — by 09:25 ET, start the engine

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
python band_lab\live\run.py --dry-run
```

Leave this window open and untouched for the whole session. It prints as it
goes; it does not need input.

You should see immediately:

```
========================================================================
DRY RUN — transmit is OFF. Decisions are computed and logged;
the broker adapter is read-only. Nothing reaches the market.
========================================================================
09:24:03 [info    ] pre-open 20260803 | SOXL,SOXS @ 127.0.0.1:7497 clientId=11 | f=1.0 w=0.5 cap=150,000 | transmit OFF (dry run)
09:24:04 [info    ] connected 127.0.0.1:7497 clientId=11
```

## 5.3 — the seven checks

Watch for these in order. Each has a pass condition. **Write down what you
actually see** — the whole point of the day is this record.

### ✅ Check 1 — the feature top-up reached the broker

```
09:24:11 [info    ] SOXL: 524 sessions in window | +8 from broker | csv holds 1510 | last session 2026-07-31
09:24:18 [info    ] SOXS: 524 sessions in window | +5 from broker | csv holds 1508 | last session 2026-07-31
```

**Pass:** `+N from broker` with **N > 0**, and `last session` reading the most
recent trading day — **2026-07-31** on Monday morning. Expect N = **8** for SOXL
and **5** for SOXS.

**Fail:** the engine prints an explicit error:

```
[error   ] SOXL: the broker top-up added no sessions — ATR5 and thr80 are being
           computed from history ending 2026-07-21. Verify before trusting the gate.
```

The price files stop at 2026-07-21 (SOXL) and 2026-07-24 (SOXS), so this means
the gate is being computed from week-old data. **Stop the run and investigate.**

> `sessions in window` (524) is the trimmed `thr80` window and `csv holds` is the
> whole file — they are not meant to sum. Only `from broker` and `last session`
> matter here.

### ✅ Check 2 — equity and sleeve capital

```
09:24:20 [info    ] equity=1,000,000 basis=150,000 sleeve_capital=75,000
```

**Pass:** `sleeve_capital` matches §4.5 for your account. **Fail:** a
sleeve_capital under a few hundred dollars — the sleeve will size to 0 shares.

### ✅ Check 3 — the gate is ON for both sleeves

No `GATE OFF` line should appear. From IBKR daily bars for 2026-07-27 → 07-31,
ATR5 into Monday is ≈ **15.8%** (SOXL) and ≈ **17.5%** (SOXS), against a
threshold of 6.0%.

**Fail:** `SOXL GATE OFF: ...`. If the reason is `atr5` and the value is near
12–13%, the top-up failed — see Check 1. If it is `market_closed`, TWS thinks
today is a holiday.

### ✅ Check 4 — no bars before 09:30, and no repeats

Between starting the engine and 09:30, **no bar-related output should appear at
all**. The first bars follow the 09:35 close.

**Fail:** bar activity before 09:30, or bar indices that jump backwards. That
would mean prior-session bars are being read as today's. This is the defect
fixed on 2026-08-02 and Monday is its first test on live data — check it
deliberately.

### ✅ Check 5 — the 10:00 filter fires once

Shortly after 10:00, either nothing (the day is ON) or:

```
10:00:22 [info    ] SOXL STAND DOWN: or30>=thr80 and pos10<2/3
```

**Pass:** at most one filter line per sleeve, at ~10:00 and not before.

### ✅ Check 6 — 11:00 arming

At ~11:00, for each sleeve still ON:

```
11:00:14 [info    ] DRY RUN — not sent: BUY LMT 652 SOXL @ 114.27 (20260803-SOXL-ENTRY-1)
```

**Pass:** the line says **`DRY RUN — not sent`**. That is the guarantee that
nothing reached the market.

**🔴 STOP IMMEDIATELY** if you see an order placed *without* that prefix, or if
any order appears in TWS. Kill the window with `Ctrl+C`, check TWS for working
orders, and cancel anything you find.

**Fail (soft):** `NotLiveDataError` → market data is delayed. Fix §4.4.

### ✅ Check 7 — no `BAR GAP` errors, all session

Search the whole session's output for `BAR GAP`:

```
11:03:01 [error   ] SOXL BAR GAP: 18 -> 21; session_high may be understated
```

**Pass:** zero occurrences. A missed bar understates `session_high`, which is
the anchor everything ratchets from, and the polled feed is the only place it
can be silently lost.

**Fail:** any occurrence. Note the time and the indices.

## 5.4 — 15:55 to 16:10, the close

```
15:55:02 [info    ] 15:55 flatten
15:55:07 [info    ] all sleeves flat
15:55:09 [info    ] SOXL EOD fills=0 stops=0 pnl=0.0bp agrees=True
15:55:10 [info    ] SOXS EOD fills=0 stops=0 pnl=0.0bp agrees=True

EOD reconcile: AGREES
```

`fills=0` is correct — nothing was transmitted. **Pass:** `EOD reconcile: AGREES`
and no `critical` line anywhere in the session.

## 5.5 — save the evidence

```powershell
cd C:\TradingModel
Copy-Item band_lab\live\out\live.db "$env:USERPROFILE\Desktop\live-20260803-dryrun.db"
```

---

# §6 · Monday evening — the go/no-go

Answer these six. **Any "no" is a no-go for transmitting on Tuesday.**

- [ ] Did all four §3 verification commands pass in the morning?
- [ ] Did the feature top-up show `+N broker` with N > 0 (Check 1)?
- [ ] Was the gate ON for both sleeves (Check 3)?
- [ ] Were there zero bars before 09:30 and no index repeats (Check 4)?
- [ ] Did every order line carry `DRY RUN — not sent` (Check 6)?
- [ ] Were there zero `BAR GAP` errors and zero `critical` lines (Check 7)?

Then compare the day's decisions against a replay of the same bars:

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
python band_lab\live\replay.py   ; echo "exit=$LASTEXITCODE"
```

Inspect what the engine actually decided:

```powershell
python -c "import sqlite3; c=sqlite3.connect(r'band_lab\live\out\live.db'); [print(dict(r)) for r in c.execute('SELECT * FROM daily WHERE session=\"20260803\"').fetchall()]"
```

If everything is clean, Tuesday is the first transmit-ON session (**§7**).
If anything is unexplained, repeat the dry run on Tuesday. Calendar time is
cheap here; a wrong first order is not.

---

# §7 · The first transmit-ON session

Only after §6 is all "yes".

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
```

Create `band_lab\live\config.local.json` — **JSON, not TOML**, despite what
`DEPLOYMENT.md` §9 says:

```json
{
  "transmit": true,
  "port": 7497,
  "client_id": 11,
  "db_path": "band_lab/live/out/live.db"
}
```

> Strategy numbers are deliberately absent. `validate_config` rejects any
> attempt to put one here — that is §6.8 of the spec in executable form.

Run the §3 verification block, then:

```powershell
python band_lab\live\run.py --config band_lab\live\config.local.json
```

The banner must now read `TRANSMIT ON` and the DRY RUN block must **not**
appear.

## 7.1 — three things to check deliberately on the first session

These are `PHASE2_PLAN.md` §6 assumptions that no amount of offline work can
settle. Check them on purpose; do not wait to notice them.

### §6.1 — does the protective stop outlive the engine? **(most important)**

After the first entry fills and its bracket is placed:

1. Confirm in TWS that both a **SELL LMT** and a **SELL STP** are working.
2. Press `Ctrl+C` in the engine window to kill the process.
3. **Look at TWS. The SELL STP must still be there.**

If the stop disappears when the engine dies, the system has no protection
against an adverse move while it is down. **That is a stop-everything finding.**
Record it and do not run unattended until it is resolved.

Restart the engine afterwards:

```powershell
python band_lab\live\run.py --config band_lab\live\config.local.json
```

It reconciles from the broker on connect and resumes. Confirm it does not open a
duplicate position.

### §6.3 — does OCA cancel the sibling?

When a target fills, the sibling stop must go to `Cancelled` in TWS by itself.
If both legs can execute, the sleeve ends up short — which the strategy forbids
absolutely.

### §6.2 — does the 23:00 TWS restart reconcile cleanly?

Leave everything running overnight. On Tuesday morning check the engine
reconnected and that `fills` and `stop_outs` for Monday did not double-count.

## 7.2 — what a normal result looks like

**Plan on ~40 bp/ON-day for SOXL and ~30 for SOXS.** A run at 20–40 bp is
consistent with the evidence and is **not** a sign the engine is broken.

The engine is ON ~52% of sessions, so four weeks gives only ~10–11 ON-days per
sleeve. **A single week proves nothing.** Investigate structural breaks — fill
counts or ON-day rates off by >20% for a month — not noise.

The first ~3 sessions are shakedown and are excluded from the evidence set.

---

# §8 · Daily operation

| Time (ET) | Action |
|---|---|
| 08:30 | TWS logged into paper; run the §3 verification block |
| 09:25 | Start `run.py`; leave the window open |
| 09:35 | Check 1–4 (top-up, capital, gate, no early bars) |
| 10:00 | Check 5 — the filter decision |
| 11:00 | Check 6 — arming |
| 15:55 | Confirm `all sleeves flat` |
| 16:10 | Confirm `EOD reconcile: AGREES`; save the day's notes |
| 23:00 | TWS auto-restarts; engine reconnects by itself |

> There is **no alerting** — no push, no email, no desktop notification, in any
> form. Watching the console window is the only monitoring that exists today.
> That is Stage 7 work and it is listed in `PROJECT_STATUS.md` §5F.

## Stopping safely

`Ctrl+C` in the engine window stops the process. It does **not** flatten. If a
position is open when you stop it:

1. Restart the engine — it reconciles and resumes; or
2. Flatten manually in TWS and cancel all working orders.

**Never leave a position open overnight.** It is design priority #1 and the
whole strategy is only safe because of it.

## Emergency — flatten everything now

In TWS: right-click the position → **Close Position**, then **Trade → Cancel All
Orders**. Do this in TWS, not through the engine.

---

# §9 · Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `replay.py` fails loading CSVs | LFS files are still pointers — re-run §2's `git lfs pull` |
| `pytest band_lab\live` collects nothing | Run from `C:\TradingModel`; `conftest.py` sets `sys.path` |
| `ZoneInfoNotFoundError` | `pip install tzdata` — Windows ships no IANA database |
| Connection refused | Port 7497 vs 7496; trusted IP 127.0.0.1; TWS actually logged into **paper** |
| `NotLiveDataError` | Market data is delayed — §4.4 |
| Orders do nothing | Read-Only API is ON, or a precaution dialog is waiting on screen in TWS |
| `EQUIVALENCE: FAIL` after a code change | The gate doing its job. The sleeve's decisions changed — diff before going further |
| `+ 0 broker` in the pre-open line | The top-up fetch failed; features are stale to 2026-07-21. Do not trade the session |
| `BAR GAP` errors | A poll missed a bar; `session_high` may be understated. Record the indices |
| Engine crashed mid-session | Restart it — it reconciles from the broker, not from memory. Check TWS for orphaned orders first |
