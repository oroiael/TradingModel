#!/usr/bin/env bash
# Fetch Git LFS data selectively.
#
# This repo tracks ~6.3 GB of market data across 822 CSVs, and .lfsconfig sets
# `lfs.fetchexclude = "*"` so a clone or a new Codespace costs no bandwidth and
# arrives holding pointer files. Use this to pull the group a run actually reads.
#
#   scripts/fetch-data.sh --list                 groups, sizes, what is on disk
#   scripts/fetch-data.sh --root                 1.2 GB  top-level CSVs (66)
#   scripts/fetch-data.sh --raw-data             4.7 GB  raw_data/ (753)
#   scripts/fetch-data.sh --soxl-raw             0.3 GB  soxl_raw_data/ (3)
#   scripts/fetch-data.sh --all                  6.3 GB  everything
#   scripts/fetch-data.sh SOXL_1min.csv ...      named paths
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

command -v git-lfs >/dev/null || { echo "git-lfs is not installed." >&2; exit 1; }

usage() { sed -n '2,14p' "$0" | sed 's/^# \?//'; }

# Pattern notes, both verified against git-lfs 3.4.1:
#   - A leading slash anchors to the repo root. Without it, `*.csv` matches at
#     ANY depth and scoops up all 822 CSVs instead of the 66 at top level.
#   - `-X ""` is load-bearing. git-lfs applies .lfsconfig's fetchexclude IN
#     ADDITION to -I rather than letting -I override it, so a file is fetched
#     only if it matches the include AND misses the exclude. Without -X "" every
#     pull here silently fetches nothing and leaves pointers on disk.
ROOT='/*.csv'

# `git lfs ls-files` is authoritative about what is LFS-tracked and, via its
# second column (* present, - pointer), what has actually been downloaded.
# Reading the working tree instead would miscount: a file already fetched no
# longer looks like a pointer, and would drop out of the listing.
rows() { git lfs ls-files -I "$1" 2>/dev/null; }

# Exact bytes, read from the pointers held in git's object store rather than
# from the working tree or from `ls-files -s`. Two reasons: a file that has
# already been downloaded no longer looks like a pointer on disk, and
# `ls-files -s` prints a rounded DECIMAL string ("9.6 KB") that compounds into
# a several-percent error once summed over 822 files. One `cat-file --batch`
# handles the whole repo in well under a second.
group_bytes() {
    git lfs ls-files -n -I "$1" 2>/dev/null \
        | sed 's|^|HEAD:|' \
        | git cat-file --batch 2>/dev/null \
        | awk '/^size [0-9]+$/ {s+=$2} END {print s+0}'
}

fmt_bytes() {
    awk -v b="$1" 'BEGIN {
        if (b>=1073741824) printf "%.2f GB", b/1073741824;
        else if (b>0)      printf "%.1f MB", b/1048576;
        else               printf "-"}'
}

report() {
    local label="$1" pat="$2" r n got
    r="$(rows "$pat")"
    n="$(printf '%s' "$r" | grep -c . || true)"
    got="$(printf '%s' "$r" | awk '$2=="*"' | grep -c . || true)"
    printf '%-14s %7s %10s   %s\n' "$label" "$n" "$(fmt_bytes "$(group_bytes "$pat")")" "$got downloaded"
}

pull() {
    echo "Fetching: $1"
    git lfs pull --include="$1" --exclude=""
    echo "Done."
}

[ $# -eq 0 ] && { usage; exit 1; }

case "${1:-}" in
    -h|--help) usage ;;
    --list)
        printf '%-14s %7s %10s   %s\n' GROUP FILES SIZE STATE
        report --root       "$ROOT"
        report --raw-data   'raw_data/*'
        report --soxl-raw   'soxl_raw_data/*'
        echo
        report TOTAL '*'
        ;;
    --root)      pull "$ROOT" ;;
    --raw-data)  pull 'raw_data/*' ;;
    --soxl-raw)  pull 'soxl_raw_data/*' ;;
    --all)
        echo "This transfers ~6.3 GB against your monthly LFS bandwidth quota."
        read -r -p "Continue? [y/N] " reply
        [[ "$reply" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
        pull '*'
        ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    *)  pull "$(IFS=,; echo "$*")" ;;
esac
