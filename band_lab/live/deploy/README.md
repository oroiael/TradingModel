# Containerised IB Gateway for the live engine

Runs IB Gateway headless so the engine does not need a desktop TWS. Paper
today; the live cutover is a mode change plus an acknowledged port, noted at
the bottom.

```bash
cp .env.example .env          # paper TWS_USERID / TWS_PASSWORD
docker compose up -d          # gateway only, engine runs on the host
docker compose logs -f ib-gateway
```

Then point the engine at it:

```bash
cd band_lab/live
python run.py --config deploy/config.host.json
```

## Which port, and why it is not the one you expect

The Gateway binds **`127.0.0.1:4002`** (paper) *inside* its own container.
That address is not reachable from anywhere else, so the image runs `socat` to
republish it on **`0.0.0.0:4004`**. Everything outside the container talks to
the socat port.

| Engine runs… | connects to | config file |
|---|---|---|
| on the host | `127.0.0.1:4002` (published → container 4004) | `config.host.json` |
| as a sibling container | `ib-gateway:4004` (socat, over the `trader` network) | `config.container.json` |

Live is the same shape one port down: Gateway `4001`, socat `4003`.

Verified from the image's `scripts/common.sh`, which sets `API_PORT=4002;
SOCAT_PORT=4004` for paper and `4001/4003` for live.

This is why `config.py` grew `LIVE_PORTS` / `PAPER_PORTS`. The old guard read
`(7496, 4001)`, so a live container-networked session on **4003 would have
walked straight past the `allow_live_account` acknowledgement** — the single
check standing between Phase 2 and real money. Both sets are now covered and
`test_every_live_port_is_refused_including_the_socat_ones` holds the line.

## Pinning

`image:` names a **digest**, not a tag:

```
ghcr.io/gnzsnz/ib-gateway:stable@sha256:91165c07…
```

A tag like `:stable` is a moving pointer. `docker compose pull` follows it
wherever it went, so the same file can give you a different Gateway and a
different IBC on a morning you were not planning to debug anything. A digest
is the content hash of one exact image: it either resolves to those bytes or
fails loudly.

That matters more here than it usually would. **IBC — the component that drives
the login dialogs — was retired on 2026-09-01 and its repository archived.**
The automation under this image has no upstream maintainer left. It works; it
is also frozen, and the failure mode of an unplanned upgrade is the Gateway
failing to log in at 09:30.

To move deliberately, resolve the new digest, change the line, and watch one
full session before trusting it:

```bash
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:gnzsnz/ib-gateway:pull&service=ghcr.io" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json" \
     https://ghcr.io/v2/gnzsnz/ib-gateway/manifests/stable | grep -i docker-content-digest
```

Current pin resolved 2026-09-17 → IB Gateway 10.45.1j, IBC 3.24.2.

## Settings that are load-bearing

| Setting | Why |
|---|---|
| `TWS_ACCEPT_INCOMING=accept` | The engine no longer connects from `127.0.0.1`, so it is not a trusted IP and TWS raises "Accept incoming connection attempt?". The image default `manual` leaves that dialog unanswered on a headless container and the connection hangs. |
| `READ_ONLY_API=no` | RUNBOOK §4.1. The engine places orders. |
| `BYPASS_WARNING=yes` | Order-precaution dialogs would otherwise block a fill with nobody there to click. |
| `AUTO_RESTART_TIME=11:00 PM` | RUNBOOK §4.3. IBC restarts **without re-authentication**, which is the thing that makes unattended running possible. The engine reconnects itself (§6.2). |
| `TIME_ZONE=America/New_York` | The §5 timetable and the 11:00 arm are ET. |
| `TWS_SETTINGS_PATH` + volume | Otherwise the Gateway reconfigures itself every restart. |

The paper-account "this is not a brokerage account" dialog needs **no**
handling: the image's IBC template hardcodes
`AcceptNonBrokerageAccountWarning=yes`. Until that dialog is accepted TWS
refuses API connections, so it would have been a silent hang — it is simply
already done.

## Market data

Paper sees live data only if the live account shares its subscriptions
(RUNBOOK §4.4). One caveat this deployment makes more likely: if you are logged
into the **live** account anywhere else while this paper Gateway runs, IBKR
error **10197** applies — *"the user is logged into the paper account and live
account simultaneously… preference would be given to the live account"* — and
the paper side quietly loses its feed.

The engine handles this: 10197 is in `broker.py`'s `NO_LIVE_DATA_ERRORS`, and
because a competing login is a property of the *session* rather than of a
contract it registers against the `"*"` wildcard — so **every** sleeve stands
down, not just whichever symbol was in flight when IBKR sent the message. The
log names the remedy (log the other session out) instead of reporting it as a
dead order, and the 11:00 refusal names 10197 rather than blaming a
subscription.

## Going live later

1. `TRADING_MODE: live` and real credentials.
2. Port becomes `4001` (host) or `4003` (container) — `config.py` refuses both
   unless `allow_live_account` is set, deliberately.
3. Live login **does** raise IBKR Mobile 2FA. IBC cannot answer it for you; it
   can only re-offer the prompt. Either someone taps the phone at each cold
   start, or you ask IBKR to relax 2FA for Gateway logins and accept the loss
   of their account-compromise guarantees. Decide that on purpose.
