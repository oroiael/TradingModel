# Launch — one page

**Account:** IBKR **paper**, ~$142,000, portfolio margin. **Port 7497.**
Once installed, this runs itself. You should not be typing anything at 15:45.

---

## Install once, tonight

PowerShell, in the repo. If it fails with access denied, re-run PowerShell as
Administrator.

```powershell
git pull
powershell -ExecutionPolicy Bypass -File overnight\win\install_tasks.ps1 -Mode Live
```

`-Mode` has no default — `Live` sends real orders, `Rehearse` sends none on the
same schedule. Say which one you meant.

Undo at any time:

```powershell
powershell -ExecutionPolicy Bypass -File overnight\win\uninstall_tasks.ps1
```

### What that installs

Seven weekday tasks under `\Overnight\` in Task Scheduler, all logging to
`overnight\out\<job>.log`.

| ET | job | what it does |
|---|---|---|
| 09:15 | `exit` | sells **market-on-open** |
| 09:35 | `watchdog` | flattens at market if the exit did not |
| 09:45 | `report` | writes the P&L row |
| 12:30 | `watchdog` | midday safety net |
| 15:35 | `watchdog` | clears anything stuck, before entering |
| 15:45 | `enter` | buys SOXL or XLU **market-on-close** |
| 16:05 | `confirm` | records the fill — unreadable tomorrow |

Missed runs are allowed to start late, because every job refuses on its own
clock: a late `enter` will not send an MOC past 15:50, a late `exit` will not
send an MOO past 09:29:30, and the watchdog picks up whatever that leaves.
**Late is safe here. Silent is not.**

### What it still needs from you

TWS or Gateway **running and logged in**, this user **logged on**, and the
machine **awake**. Tasks cannot run without a session, and the engine cannot
trade without TWS. If the machine sleeps through 15:45, nothing happens — which
is a missed trade, not a loss. If it sleeps through 09:15 **while holding**,
that is the one case that costs money, and the 12:30 and 15:35 watchdogs are
what catch it on wake.

---

## Optional: prove it before it matters

```powershell
python overnight\run.py --job enter --rehearse-now
```

Connects, fetches four years of daily bars, cross-checks them against the
committed research files, computes the signal, sizes the order, sends nothing.
Refuses to run with `--transmit`.

Four lines are worth reading in the output:

**`code:`** — the commit running. Not what you pulled, and nothing below it is
testing what you think. `+local-edits` means your tree is modified.

**`worst close mismatch`** — the live feed against the research dailies. Last
run: **0.000% across 1,003 dates**, both symbols, which settles that the feed is
the same price series the threshold was fitted on.

**`rv ... vs cut ...`** — as of Friday 2026-09-11:

| | RV20 | p60 cut | |
|---|---|---|---|
| **SOXL** | 98.68% | 106.27% | eligible by 7.6pp |
| **XLU** | 13.82% | 16.81% | eligible by 3.0pp |

**Expect SOXL at 1.00×.** SOXL is eligible so it wins; XLU is only the fallback.
A different *leg* means stop and read why.

**`sizing off ... % from the ... close`** — the share count is equity ÷ this
price, so this price being real is the whole ballgame. At 15:45 expect a drift
of a percent or two. Out of hours it can be far larger and that is not
necessarily wrong: the Sunday pre-flight read $111.56 against Friday's $121.82.
**Do not read a rehearsal's share count as tomorrow's.**

---

## What to expect

One of three outcomes at 15:45, all correct:

| | |
|---|---|
| **SOXL** | ~$142,000, roughly 1,170 shares near $121. ~65% of nights |
| **XLU** | ~$356,000 at 2.5× on margin. ~23% of nights |
| **FLAT** | no order at all. ~12% of nights |

Overnight P&L on a traded night is typically **±1–3%** — call it ±$1,400 to
±$4,300 — mean about **+0.38%**. A bad night is **−5% or worse**; the worst in
the backtest was −15.5%, about −$22,000.

Backtested at this configuration (2023→2026, 895 sessions): +1,233% total,
106.7%/yr, max drawdown −28.9%, 58% of nights positive.
**Do not expect that live** — it is the best of a long search. `STRATEGY.md` §4.3.

---

## Where the numbers are

- `overnight\out\ledger.csv` — one row per completed trade, inception to date
- `overnight\out\*.log` — one per job, appended every run
- `overnight\out\state.json` — tonight's intent
- `overnight\out\overnight.db` — event log

Task Scheduler's own view:

```powershell
Get-ScheduledTask -TaskPath '\Overnight\' | Format-Table TaskName,State
Get-ScheduledTaskInfo -TaskPath '\Overnight\' -TaskName 'Overnight-enter'
```

There is **no phone reporting yet**. Checking from your phone means a remote
desktop to this machine, or reading the CSV some other way. That is the next
thing to build.

---

## If something goes wrong

**The state that matters is holding a position after 09:30.** The watchdog now
covers that on a schedule, at market, and it will not stack orders or sell
twice. If it cannot clear a position it prints `STILL HOLDING` and
`Sell it in TWS by hand` — that is not advisory.

Everything else fails safe. A refusal prints `REFUSED:` and leaves the account
flat or unchanged. A job that refuses has not lost anything except a night.

What the watchdog will **not** do: run while the machine is off, act outside
09:31–15:40, touch anything other than SOXL and XLU, or buy to cover a short.
