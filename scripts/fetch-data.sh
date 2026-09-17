#!/usr/bin/env bash
# Fetch Git LFS data selectively.
#
# This repo tracks ~6.3 GB of market data across 853 CSVs. LFS bandwidth is
# metered monthly, so pulling everything on every fresh clone or Codespace
# rebuild is usually a waste. Pull the group a run actually reads.
#
#   scripts/fetch-data.sh --list                 what is available, and how big
#   scripts/fetch-data.sh --root                 1.2 GB  top-level CSVs (66)
#   scripts/fetch-data.sh --raw-data             4.7 GB  raw_data/ (753)
#   scripts/fetch-data.sh --soxl-raw             0.3 GB  soxl_raw_data/ (3)
#   scripts/fetch-data.sh --all                  6.3 GB  everything
#   scripts/fetch-data.sh SOXL_1min.csv ...      named paths
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

usage() { sed -n '2,13p' "$0" | sed 's/^# \?//'; }

# Files under a pathspec that are genuinely LFS-tracked. Reads the pointer
# itself rather than trusting .gitattributes, which carves out ~30 CSVs from
# the LFS filter with `-filter -diff -merge`. Note the root group uses a
# :(glob) pathspec: a bare `*.csv` pathspec matches at ANY depth in git, which
# would silently scoop up all 1154 CSVs instead of the 80 at top level.
lfs_files() {
    git ls-files -z -- "$@" \
        | xargs -0 -I{} sh -c 'head -c 60 "{}" 2>/dev/null | grep -q "git-lfs.github.com" && printf "%s\n" "{}"; exit 0' 2>/dev/null
}

# Sum the `size` line of each pointer. Correct whether or not content is local.
sum_size() {
    while IFS= read -r f; do sed -n '3s/size //p' "$f"; done \
        | awk '{s+=$1} END {if (s>=1073741824) printf "%.2f GB", s/1073741824; else if (s>0) printf "%.1f MB", s/1048576; else printf "-"}'
}

# Pull an explicit newline-separated file list, passed to LFS as one
# comma-joined --include. Exact by construction: no pattern to misinterpret.
pull_list() {
    local list; list="$(cat)"
    [ -z "$list" ] && { echo "Nothing to fetch."; return 0; }
    local n; n="$(printf '%s\n' "$list" | wc -l | tr -d ' ')"
    echo "Fetching $n file(s)..."
    git lfs pull --include="$(printf '%s\n' "$list" | paste -sd, -)"
    echo "Done."
}

row() { printf '%-16s %-7s %s\n' "$1" "$2" "$3"; }

[ $# -eq 0 ] && { usage; exit 1; }

ROOT_SPEC=':(glob)*.csv'

case "${1:-}" in
    -h|--help) usage ;;
    --list)
        row GROUP FILES SIZE
        r="$(lfs_files "$ROOT_SPEC")"
        row --root "$(printf '%s\n' "$r" | grep -c . || true)" "$(printf '%s\n' "$r" | sum_size)"
        for pair in "raw_data:--raw-data" "soxl_raw_data:--soxl-raw"; do
            g="${pair%%:*}"; flag="${pair##*:}"
            f="$(lfs_files "$g/")"
            row "$flag" "$(printf '%s\n' "$f" | grep -c . || true)" "$(printf '%s\n' "$f" | sum_size)"
        done
        echo
        if head -c 60 SOXL_1min.csv 2>/dev/null | grep -q "git-lfs.github.com"; then
            echo "On disk: pointers only — nothing downloaded yet."
        else
            echo "On disk: at least some LFS content is present."
        fi
        ;;
    --root)      lfs_files "$ROOT_SPEC"   | pull_list ;;
    --raw-data)  lfs_files raw_data/      | pull_list ;;
    --soxl-raw)  lfs_files soxl_raw_data/ | pull_list ;;
    --all)
        echo "This transfers ~6.3 GB against your monthly LFS bandwidth quota."
        read -r -p "Continue? [y/N] " reply
        [[ "$reply" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
        git lfs pull
        echo "Done."
        ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    *)  printf '%s\n' "$@" | pull_list ;;
esac
