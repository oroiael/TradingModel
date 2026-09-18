#!/usr/bin/env bash
# Runs once, after the Codespace container is created.
#
# Does NOT pull Git LFS content, and does not need to suppress it either:
# .lfsconfig sets `lfs.fetchexclude = "*"` repo-wide, so the clone that already
# happened before this script ran cost no LFS bandwidth and left pointer files
# on disk. This only reports the state and points at the fetch helper.
set -euo pipefail

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "Installing Python dependencies (requirements.txt)"
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
echo "done: $(python -c 'import pandas, numpy; print("pandas", pandas.__version__, "| numpy", numpy.__version__)')"

say "Git LFS status"
# Column 2 of `git lfs ls-files` is the download state: * present, - pointer.
total="$(git lfs ls-files 2>/dev/null | grep -c . || true)"
have="$(git lfs ls-files 2>/dev/null | awk '$2=="*"' | grep -c . || true)"
echo "${have} of ${total} LFS objects present locally."

if [ "$have" -lt "$total" ]; then
    cat <<'MSG'

Most CSVs on disk are pointer files, which is intentional: .lfsconfig excludes
LFS content from fetch so a clone costs no bandwidth. Pull what a run needs:

    scripts/fetch-data.sh --list              # groups, sizes, what is present
    scripts/fetch-data.sh --root              # 1.2 GB  top-level CSVs
    scripts/fetch-data.sh --raw-data          # 4.7 GB  raw_data/
    scripts/fetch-data.sh SOXL_1min.csv       # named files
    scripts/fetch-data.sh --all               # everything (~6.3 GB)

Running git-lfs by hand needs -X "" to clear that repo-level exclude:
    git lfs pull -I "SOXL_1min.csv" -X ""
MSG
fi

say "What runs here, and what does not"
cat <<'MSG'
RUNS: the backtesters, the grid optimizers, band_lab, retreat_lab, vol_anatomy,
      ccp_lab, the qa/ suite — anything computing over the LFS CSVs.

DOES NOT RUN: anything connecting to 127.0.0.1:7497/7496/4001/4002 (TWS or
      IB Gateway) or to the ThetaData Terminal. In a container localhost is the
      container, and neither process is in it. That covers band_lab/live/,
      stream_market_data.py, check_tws.py, fetch_1min.py and the
      soxl_ibkr_historical* / ibkr_intraday_fetcher* fetchers.
      Keep those on the machine running TWS. See .devcontainer/README.md.
MSG

say "Verify this container"
cat <<'MSG'
One command checks dependencies, fetches the ~59 MB the suites read, and runs
all three of them (719 tests):

    scripts/verify-codespace.sh

The IBKR connection is a separate check and needs a Gateway:
band_lab/live/deploy/README.md — "Testing the IBKR connection".
MSG

say "Ready."
