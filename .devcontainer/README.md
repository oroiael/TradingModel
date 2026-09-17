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
scripts/fetch-data.sh --root       # pull the CSVs your run reads
python band_lab/phase1/run.py      # then run as usual
```

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

This repo tracks **~6.3 GB across 853 CSVs** in Git LFS:

| Group | Files | Size |
| --- | --- | --- |
| top level | 66 | 1.22 GB |
| `raw_data/` | 753 | 4.74 GB |
| `soxl_raw_data/` | 3 | 313 MB |

LFS bandwidth is metered monthly, and **every fresh Codespace re-downloads
whatever it pulls**. This is the constraint most likely to bite you — check
your allowance at github.com/settings/billing before making a habit of
rebuilding.

`post-create.sh` therefore sets `--skip-smudge` and pulls **nothing** by
default. Fetch per run:

```bash
scripts/fetch-data.sh --list       # groups and sizes
scripts/fetch-data.sh --root       # 1.2 GB
scripts/fetch-data.sh SOXL_1min.csv SOXS_1min.csv
scripts/fetch-data.sh --all        # 6.3 GB, prompts first
```

Two further levers, both deliberately **not** applied here because they change
behaviour for every clone, not just Codespaces:

- **`.lfsconfig` with `lfs.fetchexclude = "*"`** would make skip-smudge the
  repo-wide default. Clean for a repo this size, but your next fresh clone on
  any machine would also arrive empty. Your call.
- **Prebuilds** (repo Settings → Codespaces) bake the container *and* the LFS
  content into an image, so a new Codespace starts warm. Costs storage,
  removes the repeated transfer.

Keeping one Codespace alive rather than recreating it avoids the problem
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
