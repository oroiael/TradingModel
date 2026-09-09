# Cold start after a reboot — and checking the FAS 1-minute capture

Windows / PowerShell. Copy-paste lines, in order. Every section ends with a
check that either passes or tells you to stop.

Two rules that cause most of the wasted time here:

- **Invoke Python as `python`, never `python3`.** `python3` on Windows resolves
  to the Microsoft Store shim, so `pip install` says "already satisfied" while
  the import still fails. Every IBKR entry point now diagnoses this itself
  (`ibkr_env.py`), but it is faster not to trigger it.
- **Only one machine may be logged into IBKR at a time.** A second TWS, the
  mobile app, or a Client Portal browser tab produces **error 162** and silently
  kills the bar feed.

---

## §0 · Find the repo and the venv

A reboot loses the shell, so start by establishing where you are. The repo has
lived in two places and the venv has two names — `RUNBOOK_WINDOWS.md` documents
`C:\TradingModel` + `.venv-live`; the FAS capture session ran from
`C:\Users\churc\documents\TradingModel` + `env`.

```powershell
# whichever of these exists is your repo
Test-Path C:\TradingModel
Test-Path C:\Users\churc\documents\TradingModel
```

```powershell
cd C:\TradingModel                        # <-- or the Users path, whichever answered True
Get-ChildItem -Directory -Force |
    Where-Object { Test-Path "$($_.FullName)\Scripts\Activate.ps1" } |
    Select-Object Name
```

That prints the venv name — `.venv-live`, `env`, or both. Use it below.

---

## §1 · Python environment

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1          # or:  .\env\Scripts\Activate.ps1
```

The prompt must now start with `(.venv-live)` (or `(env)`). **Prove it is the
interpreter you think it is** — this is the single most common failure:

```powershell
python -c "import sys; print(sys.executable)"
python -c "import pandas, numpy, ib_async, requests, zoneinfo; zoneinfo.ZoneInfo('America/New_York'); print('deps ok')"
```

`sys.executable` must sit **inside** the venv directory. `deps ok` must print.

If anything is missing:

```powershell
pip install -r band_lab\live\requirements.txt
```

That installs pandas, numpy, pytest, ib_async, **requests** (the ThetaData path)
and **tzdata** (Windows ships no IANA database, and every timestamp in this repo
goes through `ZoneInfo("America/New_York")`).

| Symptom | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` — once per user |
| `python` opens the Microsoft Store | Python is not on PATH; reinstall with "Add python.exe to PATH" ticked |
| `ModuleNotFoundError: No module named 'ib_async'` | You ran the wrong interpreter. Run the script again — `ibkr_env.py` prints which Python ran and the command that fixes it |
| `ZoneInfoNotFoundError` | `pip install tzdata` |

Price files are Git LFS. After a fresh clone they are 132-byte pointers, and
`fas_1min_verify.py` refuses to parse one:

```powershell
git lfs pull --include="FAS_5min_6Years.csv,SOXL_1min.csv,SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
Get-ChildItem FAS_5min_6Years.csv, SOXL_1min.csv |
    Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
```

Megabytes, not bytes. `SOXL_1min.csv` is **40.9 MB**.

---

## §2 · TWS / IBKR — needed for the FAS fetch

`fas_1min_fetch.py` defaults to `--source ibkr`, so nothing below §4 works until
this passes.

1. Launch **Trader Workstation** and log in — the login screen's selector must
   say **Paper**.
2. **File → Global Configuration → API → Settings**: Enable ActiveX and Socket
   Clients **ON**, Socket port **7497**, Trusted IPs **127.0.0.1**, Read-Only
   API **OFF**.
3. Log IBKR out everywhere else — the Mac, the phone app, any Client Portal tab.

Smoke test:

```powershell
cd C:\TradingModel
python check_tws.py
```

Expected:

```
connected: True
conId: <SOXL's contract id>
['<your NetLiquidation>']
```

If it hangs or refuses: wrong port (7496 and 4001 are live money), trusted IP
not set, TWS not actually logged into paper, or a precaution dialog is sitting
on screen waiting for a click.

> After a reboot TWS may not have auto-logged in, and its scheduled auto-restart
> (Configuration → Lock and Exit, 23:00) will not have run either. Check the
> window is really up and logged in, not just that the process exists.

---

## §3 · ThetaData terminal — complete restart

Not needed for the FAS 1-minute file (that came from IBKR and is finished). It
*is* needed for the `soxl_options_greeks_*.py` / `tqqq_options_greeks_*.py`
family, `local_fast_fetch.py`, and `fas_1min_fetch.py --source theta`.

**Why `java -jar ThetaTerminalv3.jar` did nothing.** Four causes, in the order
they bite. Work down the list — each step below ends in a check.

| # | Cause | Tell |
|---|---|---|
| 1 | Java missing, or older than 21 | `'java' is not recognized`, or `UnsupportedClassVersionError` |
| 2 | Not in the jar's directory | `Unable to access jarfile ThetaTerminalv3.jar` |
| 3 | **No `creds.txt` beside the jar** | it starts, then exits or refuses every request. **`.env` is not read by the terminal** — that file is for the Python scripts only |
| 4 | Right terminal, wrong port assumed after | it *is* running; your health check was pointed at 25520 |

### 3.1 Java 21 or greater

v3 will not run on anything older.

```powershell
java -version
```

Needs `21` or higher. If it is missing or older:

```powershell
winget install --id EclipseAdoptium.Temurin.21.JDK -e
```

Close that PowerShell window, open a new one, and check `java -version` again —
PATH is only picked up by a new shell.

### 3.2 Find or download the jar

```powershell
Get-ChildItem -Path C:\ -Filter "ThetaTerminal*.jar" -Recurse -ErrorAction SilentlyContinue |
    Select-Object FullName, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
```

If nothing comes back, download `ThetaTerminalv3.jar` from the download link on
ThetaData's Getting Started page (<https://docs.thetadata.us/Articles/Getting-Started/Getting-Started.html>)
and put it in a folder of its own:

```powershell
New-Item -ItemType Directory -Force -Path C:\ThetaTerminal
```

The jar is self-updating, so you download it once.

### 3.3 `creds.txt` — the step that most likely stopped you

v3 takes credentials from a plain text file **in the same directory as the
jar**: **email on line one, password on line two, nothing else**.

```powershell
cd C:\ThetaTerminal
notepad creds.txt
```

The values are the ones already in `C:\TradingModel\.env`:

```powershell
Get-Content C:\TradingModel\.env
```

Paste the value after `THETADATA_USERNAME=` as line 1 and the value after
`THETADATA_PASSWORD=` as line 2 — **the keys themselves must not appear in the
file**. Save, then confirm it is exactly two lines:

```powershell
Get-Content C:\ThetaTerminal\creds.txt | Measure-Object -Line
```

If Notepad's encoding causes trouble, rewrite it as plain ASCII (both values are
ASCII):

```powershell
Set-Content -Path C:\ThetaTerminal\creds.txt -Encoding ascii -Value @(
    (Get-Content C:\TradingModel\.env | Where-Object { $_ -like 'THETADATA_USERNAME=*' }) -replace '^[^=]+=','',
    (Get-Content C:\TradingModel\.env | Where-Object { $_ -like 'THETADATA_PASSWORD=*' }) -replace '^[^=]+=',''
)
Get-Content C:\ThetaTerminal\creds.txt | Measure-Object -Line
```

> `creds.txt` is a password in plaintext on disk. Keep it in the terminal's own
> folder, **not** in the repo — `.gitignore` does not cover `C:\ThetaTerminal`,
> and there is no rule stopping you committing it if it sits next to the code.

### 3.4 Start it

Its own PowerShell window, and **leave that window open** — it is a foreground
server, so closing the window or signing out kills it:

```powershell
cd C:\ThetaTerminal
java -jar ThetaTerminalv3.jar
```

Two variants worth knowing:

```powershell
java -jar ThetaTerminalv3.jar --creds-file=creds.txt    # creds file elsewhere
java -Xms2G -Xmx8G -jar ThetaTerminalv3.jar             # more heap for big pulls
```

**Read what it prints on startup.** It reports whether the login succeeded and
which port it bound. That printed port is the authority — everything below
assumes it said 25503.

### 3.5 Verify, from a *different* window

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 25503 | Select-Object TcpTestSucceeded
```

Then ask it for actual data:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" "http://127.0.0.1:25503/v3/stock/history/ohlc?symbol=SOXL&start_date=20260701&end_date=20260701&interval=1m"
```

| Result | Means |
|---|---|
| `200` | working |
| `401` / `403` | credentials wrong, or the subscription does not cover **stock** data (options-only plans fail exactly here) |
| nothing / connection refused | the terminal is not up, or bound to a different port |

Finally, the repo's own probe — it prints the raw payload and says which route
the terminal answers on:

```powershell
cd C:\TradingModel
python fas_1min_fetch.py --symbol FAS --source theta --probe
```

### 3.6 The port and route were wrong in this repo — now fixed

`fas_1min_fetch.py` had `THETA_BASE = http://127.0.0.1:25520` and probed
`/v2/hist/stock/ohlc` and `/v3/hist/stock/ohlc`. Against a v3 terminal all three
are wrong, which is why a health check could report "no local Theta Terminal"
while the terminal was running fine. Corrected to:

- **port 25503** by default (25504 is ThetaData's staging environment), with
  `--theta-port` and a `THETA_PORT` environment variable to override;
- a route table that tries **`/v3/stock/history/ohlc`** with v3's parameter names
  (`symbol`, `interval=1m`) and falls back to the v2 route with v2's names
  (`root`, `ivl=60000`) — whichever the terminal actually answers.

`fas_1min_selftest.py` now pins that selection against a loopback stub in both
directions (47 tests, all passing). What is still *not* verified from here is the
real payload shape behind the v3 route — ThetaData's docs are unreachable from
the environment this was written in, which is exactly what `--probe` is for.
Run it before any full Theta pull.

The older `soxl_options_greeks_*.py` scripts use the `thetadata` Python package
rather than raw REST, and their comments say port 25503 — consistent with v3.
`local_fast_fetch.py` still hard-codes 25520 and will need the same correction
before it works; it was not touched here.

## §4 · Did the FAS 1-minute capture finish?

**The mechanic that answers this:** `fas_1min_fetch.py` walks **backwards** —
it starts at today and requests one session at a time toward `--start`
(default **2019-12-31**, chosen to line up with `SOXL_1min.csv`). So:

- the **newest** row lands in the first minute of the run and is always there;
- the **oldest** row is the progress bar. Where it stopped is how far it got.

Every chunk is written through `.tmp` + atomic replace, and merged
de-duplicated and sorted, so **an interrupted run always leaves a valid file** —
a reboot costs at most the chunk in flight.

### 4a · Thirty-second check

```powershell
cd C:\TradingModel
Get-ChildItem FAS_1min.csv | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
Get-Content FAS_1min.csv -TotalCount 2
Get-Content FAS_1min.csv -Tail 1
```

Read it like this:

| Line | Means |
|---|---|
| `LastWriteTime` | when the last chunk landed. If it is the moment the box went down, the reboot killed the run |
| line 1 | must be `Date,Open,High,Low,Close,Volume` |
| **line 2** | the **oldest** bar. `20191231 09:30:00 America/New_York` = it reached the target. Anything later = that is where it stopped |
| last line | the newest bar — the day you started the run |
| size | a complete capture is **~40 MB**, matching `SOXL_1min.csv`'s 40.9 MB / 642,510 rows |

Also check for wreckage from the moment of the reboot:

```powershell
Get-ChildItem FAS_1min.csv.tmp -ErrorAction SilentlyContinue
```

If a `.tmp` exists, the process died mid-write. `FAS_1min.csv` itself is still
intact — delete the `.tmp` and carry on:

```powershell
Remove-Item FAS_1min.csv.tmp
```

### 4b · Census — rows, sessions, span, bars per session

```powershell
python -c "import pandas as pd; d=pd.read_csv('FAS_1min.csv'); s=d['Date'].astype(str).str.slice(0,8); print('rows    ',f'{len(d):,}'); print('sessions',f'{s.nunique():,}'); print('span    ',s.min(),'->',s.max()); print('bars/session',{int(n):int(c) for n,c in d.groupby(s).size().value_counts().head(4).items()})"
```

A complete capture from 2019-12-31 to today:

- **~1,690 sessions**, **~650,000 rows** (SOXL's 1,653 sessions / 642,510 rows
  through 2026-07-30 is the anchor — add roughly 21 sessions per month since)
- `bars/session` dominated by **390** (09:30–15:59 inclusive; **16:00 is
  deliberately absent**), plus **210** on early-close half-days
- span `20191231 -> <the day you launched the run>`

Anything materially short of that on the **left** end means it did not finish.

### 4c · The real answer — run the verifier

```powershell
python fas_1min_verify.py --symbol FAS ; echo "exit=$LASTEXITCODE"
```

Six checks. `exit=0` means no blocking failure. The three that answer "did I get
all the data":

- **Check 1 — FORMAT** prints `rows / sessions / <first> -> <last>` and the span
  in years, and warns if the span is under 5.5 years.
- **Check 2 — SESSION GRID** prints the bars-per-session histogram and warns
  about every session that is not 390 or 210. Partial sessions from a killed run
  show up here.
- **Check 5 — CROSS-CHECK** aggregates your 1-minute file to 5 minutes and
  compares it bar-for-bar against `FAS_5min_6Years.csv`. This is the check that
  matters: two independently sourced captures agreeing is much stronger evidence
  than any internal consistency test. It also reports **sessions present in the
  5-minute file but missing from the 1-minute file** — a direct list of holes.

Expected FAS-specific warnings that are **not** defects — from
`FAS_1MIN_CAPTURE.md` and `IBKR_1MIN_CAPTURE_REVIEW.md`:

- **More zero-volume bars than SOXL's 1.26%.** FAS is the thin one: median
  5-minute notional $528K against SPXL's $3.76M. That is the instrument.
- **A volume-ratio warning in check 5**, if the 1-minute file ended up
  split-adjusted while `FAS_5min_6Years.csv` carries raw share counts. The
  *return* comparison in the same check is basis-independent and is the one that
  decides whether the capture is sound.
- **Check 5 covers 2020-07-23 onward only** — that is where
  `FAS_5min_6Years.csv` begins. The 2019-12-31 → 2020-07-22 stretch, which
  spans the COVID crash, is cross-checked against nothing. If check 4 names a
  split in there, record it in `SPLIT_ADJUSTMENTS` in `band_lab/live/replay.py`
  (which currently holds only SOXL) — and check the factor against the
  corporate-action table in `IBKR_1MIN_CAPTURE_REVIEW.md`, which says FAS had
  **no splits** between 2021-09-07 and 2026-09-05.

Sanity-check the verifier itself against the known-good pair any time you doubt
it:

```powershell
python fas_1min_verify.py --symbol SOXL
```

---

## §5 · Push `FAS_1min.csv` up to GitHub

The file is ~40 MB. Line 1 of `.gitattributes` is
`*.csv filter=lfs diff=lfs merge=lfs -text`, so it goes to **Git LFS
automatically** — *provided LFS is initialised on this machine*. If it is not,
git commits a 40 MB blob into the repository permanently, and nothing you do
afterwards removes it from history. Check before committing, not after.

### 5.1 Pre-flight — two lines that decide everything

```powershell
cd C:\TradingModel
git lfs install                          # once per machine; harmless to repeat
git check-attr filter -- FAS_1min.csv
```

The second must print exactly:

```
FAS_1min.csv: filter: lfs
```

If it says `unspecified`, **stop** — the file would go in as a raw blob.

### 5.2 Put it on its own branch

PR #59 is the docs change. A 40 MB data file does not belong in it.

```powershell
git checkout main
git pull
git checkout -b data/fas-1min
```

### 5.3 Stage, confirm LFS took it, then commit

```powershell
git add FAS_1min.csv
git lfs status
```

`FAS_1min.csv` must appear under **"Objects to be committed"** with an `(LFS:
<oid>)` marker. If it is listed as `(Git: ...)` instead, LFS did not take it —
go back to 5.1 rather than pushing.

```powershell
git commit -m "Add FAS 1-minute RTH bars, 2019-12-31 onward"
git push -u origin data/fas-1min
```

The push uploads the LFS object first, then the pointer commit. Expect it to sit
on `Uploading LFS objects: 100% (1/1), 40 MB` for a while on a slow uplink; if it
drops, just run the same push again — LFS resumes rather than restarting.

### 5.4 Confirm what actually landed

```powershell
git lfs ls-files | Select-String FAS_1min
git show HEAD:FAS_1min.csv | Select-Object -First 3
```

The second command should print a **pointer**, not CSV rows:

```
version https://git-lfs.github.com/spec/v1
oid sha256:...
size 42...
```

That is the correct result. The pointer is what lives in the commit; the bytes
live in LFS, and GitHub will label the file "Stored with Git LFS". Anyone
cloning gets it with `git lfs pull` (§1).

### 5.5 If it went in as a raw blob

You will have caught it at 5.3. Undo it **before** pushing:

```powershell
git reset HEAD~1
git lfs install
git add FAS_1min.csv
git lfs status                           # must now say LFS
```

Once pushed, rewriting history is the only remedy — which is the whole reason
§5.1 exists.

### Quota

LFS storage and bandwidth are metered per account, and this repo already holds
`SOXL_1min.csv` (41 MB), `SOXS_1min.csv`, `UVXY_1min.csv` and the 5-minute
files. FAS adds another ~40 MB against the same allowance. `git lfs env` shows
which endpoint and repo it is billing against.

---

## §6 · Resume an unfinished capture

Re-run the identical command. It reads the earliest row already on disk and
keeps walking back from there — nothing already fetched is re-requested.

```powershell
cd C:\TradingModel
.\.venv-live\Scripts\Activate.ps1
python fas_1min_fetch.py --symbol FAS --normalize-splits
```

You should see `resuming backwards from <date>` in the first few lines, matching
line 2 of §4a. It ends with:

```
done: N requests, M rows -> C:\TradingModel\FAS_1min.csv
coverage 2019-12-31 -> 2026-09-08  (target start 2019-12-31)
```

`coverage` reaching the target start is the completion signal.

**How long:** the IBKR path forces an 11-second gap between requests regardless
of `--pause` (60 requests per 10 minutes is IBKR's documented ceiling), at one
session per request — so ~1,690 requests, about **5 hours**. If you started this
late last night and the box rebooted, it almost certainly did not finish.

`--duration "1 W"` cuts that to roughly an hour. IBKR's own client documents
durations "up to one week", but it is untested against live TWS here — run it,
verify the output with §4c, and only then trust it for the rest of the set.

Two things worth knowing before you rerun:

- **`--normalize-splits` only runs after a completed walk.** An interrupted run
  leaves the file un-normalized, which is harmless; the run that finishes
  normalizes the whole file in one pass.
- **The walk only goes backwards.** It will not top up sessions *after* the
  newest row you already have. If days have passed since the run first started,
  fetch the tail into a separate file and merge:

```powershell
python fas_1min_fetch.py --symbol FAS --out FAS_1min_tail.csv --start 2026-09-01
python -c "import pandas as pd; a=pd.read_csv('FAS_1min.csv'); b=pd.read_csv('FAS_1min_tail.csv'); o=pd.concat([a,b]).drop_duplicates(subset='Date',keep='last'); o=o.assign(_k=o['Date'].str.slice(0,17)).sort_values('_k').drop(columns='_k'); o.to_csv('FAS_1min.csv',index=False); print(f'{len(o):,} rows')"
python fas_1min_verify.py --symbol FAS
```

Re-verify after any merge. A tail fetched on a different anchor can introduce a
split-basis seam mid-file — `FAS_1MIN_CAPTURE.md` calls this out as a trap. FAS
has no known split in the window, so the risk is low here, but check 4 of the
verifier is what confirms it rather than assumes it.

If TWS complains the client id is in use (a stale connection from before the
reboot), move it:

```powershell
python fas_1min_fetch.py --symbol FAS --normalize-splits --client-id 94
```

---

## §7 · Make the next run survive the night

Log the run, so "did it finish" is answerable from the transcript instead of
inferred from the file. `logs\` is gitignored — session output carries account
detail, leave it that way:

```powershell
New-Item -ItemType Directory -Force -Path logs | Out-Null
python fas_1min_fetch.py --symbol FAS --normalize-splits *>&1 |
    Tee-Object -FilePath logs\fas_1min_fetch_FAS.log
```

Stop the machine sleeping or rebooting under it — PowerShell **as
Administrator**:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
```

Then **Settings → Windows Update → Advanced options → Active hours** wide enough
to cover the run. `Win+L` is safe — the run keeps going. Signing out, closing
the PowerShell window, and sleep all kill it.

### The rest of the six-symbol set

`IBKR_1MIN_CAPTURE_REVIEW.md` is the reference. In short: TQQQ and MUU are
NASDAQ-listed (handled by the `PRIMARY_EXCHANGE` table), MUU has no history
before 2024-10-10, and TQQQ/MUU/BULZ/TMF have no 5-minute companion file, so
check 5 of the verifier warns and skips for those four.

```powershell
foreach ($s in "TQQQ","FAS","SPXL","MUU","BULZ","TMF") {
    python fas_1min_fetch.py --symbol $s --normalize-splits
    python fas_1min_verify.py --symbol $s
}
```

---

## Appendix · macOS

Same steps, different names — `RUNBOOK_MACOS.md` is the full reference.

```bash
cd ~/TradingModel
source .venv-live/bin/activate
python3 -c "import sys; print(sys.executable)"
pip install -r band_lab/live/requirements.txt

python3 check_tws.py

cd ~/ThetaTerminal                     # creds.txt beside the jar: email, then password
java -jar ThetaTerminalv3.jar          # separate terminal, leave it open — Java 21+
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:25503/v3/stock/history/ohlc?symbol=SOXL&start_date=20260701&end_date=20260701&interval=1m"

cd ~/TradingModel

python3 fas_1min_fetch.py --symbol FAS --normalize-splits
python3 fas_1min_verify.py --symbol FAS ; echo "exit=$?"
```

`python3` is correct on macOS — the `python`-not-`python3` rule is a Windows
PATH problem and does not apply here. The one-machine-logged-into-IBKR rule
does: if this Mac connects to TWS, the Windows box must be logged out.
