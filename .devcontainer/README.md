# Running TradingModel in a GitHub Codespace

A Codespace runs this repo on GitHub's machines, not your Mac. Your laptop can
be closed and the run continues. That works well for the backtesting half of
this project and not at all for the live half. This document says which is
which, and why.

## What runs in a Codespace

Everything that computes over the CSVs: the backtest engines, the grid
optimizers (`massive_grid_optimizer.py`, `the_titan_grid.py`,
`hedge_optimizer_grid.py`), `band_lab`, `retreat_lab`, `vol_anatomy`,
`ccp_lab`, `cc_lp_lab`, and the `qa/` suite. Also the HTTP-based data sources
(`yfinance`).

```bash
scripts/fetch-data.sh --root     # the 66 top-level CSVs, 1.2 GB
python collar_backtester.py      # reads Master_Backtest_Data_SOXL.csv
```

Pull before you run. Without the data these scripts do not fail cleanly — they
read the 130-byte LFS pointer as if it were a CSV and die in the parser.

## What does not

Anything that connects to a process on `localhost`. In a container `localhost`
is the container, and neither of these is in it:

| Blocked | Why |
| --- | --- |
| `band_lab/live/` (the whole live engine) | `config.py:63` → `127.0.0.1:7497` |
| `stream_market_data.py`, `check_tws.py`, `fetch_1min.py`, `diagnose.py` | TWS / IB Gateway on 7497/7496/4001/4002 |
| `soxl_ibkr_historical*.py`, `ibkr_intraday_fetcher*.py`, `TQQQ_ibkr_historical_3yr.py` | same, via the older `ibapi` client |
| `soxl_options_greeks_*.py`, `soxl_historical_greeks*.py` | the `thetadata` client needs the local ThetaData Terminal |

**Superseded in part.** `band_lab/live/deploy/docker-compose.yml` now runs a
paper IB Gateway as a container, and `devcontainer.json` enables
docker-in-docker so it can run here. The table above is still right about
`localhost` — it is the Gateway container that changes the answer, not the
network. With it up, `127.0.0.1:4002` inside the Codespace reaches a real TWS
socket and the clients above connect.

**Recommended split is unchanged: live trading and data fetching stay on the
machine running TWS; analysis moves to the Codespace.** The Gateway makes the
IBKR path *possible* from here, not advisable. Two reasons, and the second is
the serious one.

1. Your IBKR password ends up in a cloud container's environment.
2. **IBKR allows one session per username.** Log the container Gateway into
   the same paper account as your desktop TWS and they fight over it. This
   compose file sets `EXISTING_SESSION_DETECTED_ACTION: primary`, so the
   container is the one that wins — it takes the session and your desktop TWS
   is dropped. If that desktop is running the `overnight/` engine, it silently
   misses the 15:45 MOC, the 16:05 confirm, the 09:15 MOO or the 09:35
   watchdog. Related: IBKR **10197**, "no market data during competing
   session", which this project's notes record as demoting **the whole
   account**, not one symbol — see `.claude/skills/ibkr-semantics/SKILL.md`.

   If you need the Gateway here anyway, use a **second IBKR paper username**.
   Failing that, only bring it up while desktop TWS is closed, and stop it
   before 15:25 ET.

## Running the cover-leg screen from here

`retreat_lab/cover_search.py` scores 235 candidate instruments against SOXL.
It is a two-stage pipeline and only the first stage needs a broker:

```bash
# Stage 1 — needs TWS/Gateway. ~45 min for 235 symbols at the default pacing.
python3 retreat_lab/fetch_universe.py                 # desktop TWS, port 7497
python3 retreat_lab/fetch_universe.py --port 4002     # container Gateway

# Stage 2 — pure compute, no broker, no LFS data beyond the SOXL series.
scripts/fetch-data.sh SOXL_1min.csv
python3 retreat_lab/cover_search.py 20
```

### Running both stages here, with no TWS box

```bash
scripts/fetch-universe.sh              # Gateway up, fetch, Gateway down
git add retreat_lab/out/universe/ && git commit -m "universe: refresh" && git push
python3 retreat_lab/cover_search.py 20
```

`scripts/fetch-universe.sh` starts the paper Gateway, waits for it to accept
API connections, runs the fetch against port 4002, and **takes the Gateway
back down**. The teardown is the safety feature: while that container is up it
owns the IBKR session, so leaving it running is how a desktop TWS gets dropped
by accident. `--keep-gateway` opts out if you want it to stay.

Set `TWS_USERID` and `TWS_PASSWORD` as **Codespaces secrets**
(github.com/settings/codespaces), not in `.env` — they arrive as environment
variables and the script reads them from there, so no file holds them.

`devcontainer.json` sets `IB_PORT=4002`, so a bare
`python3 retreat_lab/fetch_universe.py` finds the Gateway here while the same
command on a TWS box still goes to 7497.

**The one decision this forces.** IBKR allows one session per username. If a
desktop TWS is still running the `overnight/` engine on the account you put in
`TWS_USERID`, this Gateway takes the session from it. Either:

- **use a second IBKR paper username** for the Gateway — clean, no scheduling,
  and what to do if the engine keeps running anywhere; or
- **run the fetch only when that desktop TWS is closed.** `fetch_universe.py`
  already refuses inside the trading windows, but that guard does not know
  about the Gateway, so the wrapper's teardown is what keeps the window short.

The market-data entitlements are the account's, not the machine's, so a
Codespace fetch sees exactly what the Windows box would.

### What still cannot move off a local machine

The **live engine** is not a Codespace workload, whatever the machine size. It
has to hold 15:45 and 16:05 one day and 09:15 and 09:35 the next; a Codespace
idles out at 30 minutes and is capped at 4 hours. Research fetching moves here
cleanly. Retiring the trading box entirely means moving the engine to an
always-on host, which is what `band_lab/live/deploy/` was built for — the same
compose file, on a small cloud VM rather than in a Codespace.

The tracked universe is the other half of not depending on one machine:
`retreat_lab/out/universe/` is committed (plain git, ~14 MB, deliberately not
LFS), so the 45-minute fetch and its IBKR pacing budget survive the Codespace
being deleted.

Two things to expect from stage 1:

- **It outlives the idle timeout.** 235 symbols at 11 s pacing is ~45 minutes;
  Codespaces stops at 30 minutes idle by default. Raise it to 4 hours in
  Codespaces settings. If it does get cut off, just re-run — the script skips
  anything already on disk and continues.
- **A partial universe is normal.** The 235 names span 18 groups including
  currency, crypto and rates, and historical data for those needs entitlements
  this account may not hold. Symbols that fail are logged and skipped rather
  than aborting the run. Read the skip list before treating the screen as
  complete.

Those clients are still installed (`ib_async` is in `requirements.txt`) so the
modules import and the offline tests pass. It is connecting that fails, not
importing. `band_lab/live/ibkr_env.py` explains the distinction.

## The LFS bandwidth question

This repo tracks **~6.3 GB across 822 CSVs** in Git LFS:

| Group | Files | Size | Fetch with |
| --- | --- | --- | --- |
| top level | 66 | 1.22 GB | `--root` |
| `raw_data/` | 753 | 4.74 GB | `--raw-data` |
| `soxl_raw_data/` | 3 | 313 MB | `--soxl-raw` |

LFS bandwidth is metered monthly, and a default clone materializes all of it —
on every fresh Codespace. So **`.lfsconfig` sets `lfs.fetchexclude = "*"`**: a
clone or a new Codespace arrives holding pointer files and costs no bandwidth,
and you pull the group a run actually reads.

```bash
scripts/fetch-data.sh --list       # groups, sizes, and what is already present
scripts/fetch-data.sh --root       # 1.2 GB
scripts/fetch-data.sh SOXL_1min.csv SOXS_1min.csv
scripts/fetch-data.sh --all        # 6.3 GB, prompts first
```

### The `-X ""` gotcha

This bites anyone running git-lfs by hand, so it is worth stating plainly.
`fetchexclude` is applied **in addition to** `--include`, not overridden by it:
a file is fetched only if it matches the include **and** misses the exclude.
With `*` excluded, that means:

```bash
git lfs pull -I "SOXL_1min.csv"          # fetches NOTHING, silently
git lfs pull -I "SOXL_1min.csv" -X ""    # correct
```

Verified against git-lfs 3.4.1. `scripts/fetch-data.sh` passes `-X ""` for you,
which is the main reason to use it rather than calling git-lfs directly.

A second, related trap: a leading slash anchors a pattern to the repo root.
Without it, `*.csv` matches at any depth — `-I "*.csv"` pulls all 822 files,
`-I "/*.csv"` pulls the 66 at top level.

### Consequences elsewhere

`.lfsconfig` is committed, so this applies to **every** clone, not just
Codespaces — including your Mac. A fresh clone there will also arrive empty
until you run the fetch script. That is the intended trade for a repo this
size, but it is a behaviour change worth knowing about.

To opt out, delete `.lfsconfig`, or override it locally, which wins over the
committed file:

```bash
git config lfs.fetchexclude ""
```

Existing clones that already hold the data are unaffected — nothing is deleted.

### Prebuilds

Repo Settings → Codespaces → prebuilds bakes the container *and* whatever LFS
content you fetch into an image, so a new Codespace starts warm. Costs storage,
removes the repeated transfer. Worth it if you create Codespaces often.

Keeping one Codespace alive rather than recreating it sidesteps the problem
entirely — a stopped Codespace keeps its disk; only the process dies.

## Verifying the container works

```bash
scripts/verify-codespace.sh
```

Checks the interpreter is 3.12, that every dependency imports, that pandas is
below the 3.0 cap, fetches the data the suites read, then runs all three
suites and the `ibkr-semantics` claim check. Exit 0 means this container can
run the project.

| suite | tests | data it needs |
|---|---|---|
| `band_lab/phase1` | 60 | none |
| `band_lab/live` | 504 | `SOXL_5min_6Years.csv`, `SOXS_5min_6Years.csv` |
| `overnight` | 155 | `SOXL_1min.csv` |

That is ~59 MB of the repo's 6.3 GB. The data set was established by running
each suite against pointer files and reading which path it died on, not by
guessing from `.gitattributes` — and a fresh clone has none of it, because
`.lfsconfig` excludes LFS content from fetch.

`.github/workflows/tests.yml` runs the same three suites on every push, from a
clean checkout on Python 3.12. That is the reproducible version of this check:
the script tells you whether *your* container is good, CI tells you whether the
repo still builds anywhere. Note it sets `lfs: false` on checkout and fetches
explicitly, because `actions/checkout`'s built-in LFS step would transfer
nothing against `fetchexclude = "*"`.

The IBKR connection is **not** covered by either. It needs a Gateway; see
`band_lab/live/deploy/README.md`.

## Python and dependency versions

The container is **Python 3.12**. `band_lab/live/DEPLOYMENT.md` sets the floor
at 3.11+, the repo's own venv is 3.12, and `thetadata` publishes nothing
installable below 3.12 (its 0.x line is fully yanked on PyPI).

`requirements.txt` caps `pandas<3.0` and `numpy<3.0` on purpose. pandas 3.0 is
current on PyPI and changes defaults this repo leans on. Without the cap a
container rebuild would quietly give you a different pandas from your laptop,
and a backtest that disagrees with last week's run is the worst outcome this
project has. Lift it deliberately, with a `qa/` re-run — not by accident.

Machine-bound clients live in `requirements-local.txt` (`thetadata`, and the
vendored `ibapi` from `TWS API/source/pythonclient`). Install that one on the
box running TWS, not in the Codespace.

## Machine size

`devcontainer.json` asks for **4 cores / 16 GB RAM / 64 GB disk**. The disk is
the part that matters: 6.3 GB of data, a 387 MB `.git`, and sweep output do not
sit comfortably on the 32 GB default. If your plan will not grant that machine,
lower `hostRequirements` — 2 cores still runs everything, just slower on the
grid searches.

## Long sweeps

Codespaces idle-timeout defaults to 30 minutes (configurable to 4 hours). The
V33/V35/V37/V39 sweeps and the `overnight/` engine are exactly the runs that
get cut off mid-flight. The disk survives — a stopped Codespace resumes with
files intact — but the process does not. For multi-hour sweeps prefer a plain
cloud VM, or a GitHub Actions job (6 h limit), or run them locally.

## Secrets

`.env` was tracked in this repo until recently and carried real ThetaData
credentials. It is now gitignored, but **removing a file from tracking does not
remove it from history** — anyone with repo access can still read the old
values from earlier commits. Rotate that password.

Going forward: set `THETADATA_USERNAME` and `THETADATA_PASSWORD` as Codespaces
secrets at github.com/settings/codespaces. They arrive as environment
variables, and `load_dotenv()` will not overwrite them. See `.env.example`.
