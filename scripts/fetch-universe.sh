#!/usr/bin/env bash
# Fetch the 235-symbol screen universe from inside a Codespace.
#
# Brings the paper IB Gateway up, waits for it to accept API connections, runs
# retreat_lab/fetch_universe.py against it, and TAKES THE GATEWAY BACK DOWN.
#
# The teardown is the point, not politeness. IBKR allows one session per
# username; docker-compose.yml sets EXISTING_SESSION_DETECTED_ACTION=primary,
# so while this Gateway is up it OWNS the account and any desktop TWS logged
# into the same username is dropped. If that desktop is running the overnight
# engine it silently misses the 15:45 MOC, the 16:05 confirm, the 09:15 MOO or
# the 09:35 watchdog. Leaving the Gateway running after a research fetch is how
# that happens by accident.
#
#   scripts/fetch-universe.sh                 # up, fetch, down
#   scripts/fetch-universe.sh --keep-gateway  # leave it up (you own the risk)
#   scripts/fetch-universe.sh --only SPY,TLT  # anything else goes to the fetcher
#
# Credentials come from TWS_USERID / TWS_PASSWORD. In a Codespace set them as
# Codespaces secrets (github.com/settings/codespaces) so they arrive as
# environment variables and never touch a file.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY="$ROOT/band_lab/live/deploy"
KEEP=0
ARGS=()
for a in "$@"; do
  if [ "$a" = "--keep-gateway" ]; then KEEP=1; else ARGS+=("$a"); fi
done

command -v docker >/dev/null || {
  echo "docker not found. This script is for a Codespace with the"
  echo "docker-in-docker feature (see .devcontainer/devcontainer.json)."
  echo "On a box already running desktop TWS, skip this and run:"
  echo "    python3 retreat_lab/fetch_universe.py"
  exit 1; }

: "${TWS_USERID:?set TWS_USERID (Codespaces secret, or export it)}"
: "${TWS_PASSWORD:?set TWS_PASSWORD (Codespaces secret, or export it)}"

down() {
  [ "$KEEP" = "1" ] && { echo "--keep-gateway: leaving it up. It holds the IBKR session."; return; }
  echo "==> stopping the Gateway (releasing the IBKR session)"
  docker compose -f "$DEPLOY/docker-compose.yml" down --timeout 30 || true
}
trap down EXIT

echo "==> starting paper IB Gateway"
docker compose -f "$DEPLOY/docker-compose.yml" up -d ib-gateway

# The compose healthcheck allows 180s for cold login + IBC's dialog handling.
echo "==> waiting for it to accept API connections (up to 5 min)"
for i in $(seq 1 60); do
  state=$(docker inspect -f '{{.State.Health.Status}}' bandlab-ib-gateway-1 2>/dev/null || echo starting)
  [ "$state" = "healthy" ] && { echo "    healthy after ~$((i*5))s"; break; }
  if [ "$i" = "60" ]; then
    echo "    NOT healthy after 5 min. Gateway logs:"
    docker compose -f "$DEPLOY/docker-compose.yml" logs --tail 40 ib-gateway
    exit 1
  fi
  sleep 5
done

echo "==> fetching (resumable: re-run to continue where it stops)"
python3 "$ROOT/retreat_lab/fetch_universe.py" --port 4002 "${ARGS[@]+"${ARGS[@]}"}"
