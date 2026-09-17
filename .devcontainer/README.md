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

There are workarounds — running headless IB Gateway with IBC inside the
container, or reverse-tunnelling back to your Mac — but the first puts your
IBKR credentials in a cloud container, and the second needs your Mac online
anyway, which defeats the point. **Recommended split: live trading and data
fetching stay on the machine running TWS; backtests move to the Codespace.**

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
