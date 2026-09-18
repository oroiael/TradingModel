#!/usr/bin/env bash
# Prove this container can actually run the project: dependencies, data, and
# all three test suites. Run it right after a Codespace is created.
#
#   scripts/verify-codespace.sh              # everything (~3 min)
#   scripts/verify-codespace.sh --no-fetch   # assume the data is already here
#
# It does NOT touch IBKR. That is a separate check and needs a Gateway —
# band_lab/live/deploy/README.md has it.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

FETCH=1
[ "${1:-}" = "--no-fetch" ] && FETCH=0

pass=0; fail=0
step() { printf '\n\033[1m── %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail+1)); }

# The data the suites actually read. Deliberately not "everything": this is
# ~59 MB of the repo's 6.3 GB, and .lfsconfig means a fresh clone has none of
# it. Established by running each suite against pointer files and reading which
# path it died on, not by guessing from the .gitattributes list.
DATA=(SOXL_5min_6Years.csv SOXS_5min_6Years.csv SOXL_1min.csv)

step "Interpreter and dependencies"
py=$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')
if python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,12) else 1)'; then
    ok "python $py (3.12+, matches .devcontainer)"
else
    bad "python $py — the container pins 3.12; thetadata needs >=3.12"
fi
for m in pandas numpy scipy matplotlib pytest ib_async; do
    v=$(python3 -c "import $m,sys; print(getattr($m,'__version__','?'))" 2>/dev/null) \
        && ok "$m $v" || bad "$m not importable — pip install -r requirements.txt"
done
# The cap exists so a container rebuild cannot silently change backtest results.
python3 -c 'import pandas; import sys; sys.exit(0 if pandas.__version__ < "3" else 1)' \
    && ok "pandas is <3.0 as requirements.txt pins" \
    || bad "pandas 3.x installed — requirements.txt caps it below 3.0"

step "Market data"
command -v git-lfs >/dev/null && ok "git-lfs present" || bad "git-lfs missing"
if [ "$FETCH" = 1 ]; then
    ./scripts/fetch-data.sh "${DATA[@]}" >/dev/null 2>&1 || true
fi
for f in "${DATA[@]}"; do
    if head -c 60 "$f" 2>/dev/null | grep -q "git-lfs.github.com"; then
        bad "$f is still an LFS pointer — scripts/fetch-data.sh ${f}"
    elif [ -s "$f" ]; then
        ok "$f ($(du -h "$f" | cut -f1))"
    else
        bad "$f missing"
    fi
done

step "Test suites"
run_suite() {
    local name="$1" dir="$2"
    local out; out=$(cd "$dir" && python3 -m pytest -q 2>&1 | tail -1)
    if printf '%s' "$out" | grep -qE "^[0-9]+ passed"; then
        ok "$name — $out"
    else
        bad "$name — $out"
    fi
}
run_suite "band_lab/phase1" band_lab/phase1
run_suite "band_lab/live  " band_lab/live
run_suite "overnight      " overnight

step "IBKR semantics reference"
if python3 .claude/skills/ibkr-semantics/scripts/verify_claims.py >/dev/null 2>&1; then
    ok "all claims in SKILL.md still hold against the installed ib_async"
else
    bad "verify_claims.py reports drift — run it directly for the list"
fi

printf '\n\033[1m%d ok, %d failed\033[0m\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then
    printf 'This container can run the project. IBKR is a separate check:\n'
    printf '  band_lab/live/deploy/README.md — "Testing the IBKR connection"\n'
fi
exit $(( fail > 0 ))
