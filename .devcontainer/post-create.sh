#!/usr/bin/env bash
# Runs once, after the Codespace container is created.
#
# Deliberately does NOT pull Git LFS content. The data in this repo is ~6.3 GB
# and LFS bandwidth is metered monthly, so fetching all of it on every rebuild
# is the fastest way to burn a quota. Fetch what a given run needs instead:
#     scripts/fetch-data.sh --list
set -euo pipefail

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "Installing Python dependencies (requirements.txt)"
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
echo "done: $(python -c 'import pandas, numpy; print("pandas", pandas.__version__, "| numpy", numpy.__version__)')"

say "Git LFS status"
git lfs install --local --skip-smudge >/dev/null 2>&1 || true

# A pointer file starts with the LFS spec URL and is ~130 bytes. Sample a file
# we know is LFS-tracked rather than guessing from `git lfs ls-files`, which
# reports what is tracked, not what is actually present on disk.
probe="SOXL_1min.csv"
if [ -f "$probe" ] && head -c 60 "$probe" 2>/dev/null | grep -q "git-lfs.github.com"; then
    cat <<'MSG'
LFS content is NOT downloaded — the CSVs on disk are pointer files.

This is expected and intentional: pulling all 853 files would transfer ~6.3 GB
against your monthly LFS bandwidth quota. Fetch only what you need:

    scripts/fetch-data.sh --list              # what is available
    scripts/fetch-data.sh SOXL_1min.csv       # one file
    scripts/fetch-data.sh --band-lab          # a lab's inputs
    scripts/fetch-data.sh --all               # everything (~6.3 GB)
MSG
else
    echo "LFS content appears to be present on disk."
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

say "Ready."
