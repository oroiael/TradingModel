"""Fetch daily bars for the whole screen universe, from TWS, once.

    python overnight\\..\\retreat_lab\\fetch_universe.py          # from the repo root:
    python retreat_lab/fetch_universe.py

Writes one CSV per symbol to `retreat_lab/out/universe/<SYM>.csv` in the same
shape as the other daily files here, so `tail_screen.py` reads them unchanged.

## Three things this has to get right

**Pacing.** IBKR throttles historical data requests, and a violation returns
error 162 rather than data. The commonly-cited limit is 60 requests per rolling
10 minutes. **That number is NOT verified here** — IBKR's documentation is
unreachable from this environment and `TWS API/` carries the message tables but
not the pacing rules — so the default gap is a conservative 11 seconds, giving
~55 per 10 minutes. 235 symbols is therefore about 45 minutes. Lower `--pace`
only if you have seen it work.

**Resumability.** A 45-minute job that dies at symbol 180 must not start over.
Anything already on disk is skipped, so re-running continues where it stopped.
Delete a file to refetch just that symbol.

**Never colliding with the live engine.** Its own client id (22, not the
engine's 21), `dry_run=True` so the order path is inert, and it refuses to start
inside the enter or exit windows — a 45-minute read loop overlapping the 15:45
MOC is not a risk worth taking for a research fetch.

Symbols that will not qualify (delisted, renamed, wrong venue) are logged and
skipped. A screen that aborts on the first bad ticker in 235 is useless.

**Which port.** 7497 is desktop TWS in paper mode, which is the default and the
recommended host for this job: that machine already runs TWS and already holds
the market-data entitlements. 4002 is the containerised Gateway from
`band_lab/live/deploy/`, for running this inside a Codespace. Do not point this
at a Gateway that is logged into the SAME paper account as a desktop TWS you
are relying on — see `.devcontainer/README.md` on IBKR 10197.

Usage:  python3 retreat_lab/fetch_universe.py [--pace 11] [--duration "5 Y"]
                                              [--host 127.0.0.1] [--port 7497]
                                              [--force]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_ROOT, "overnight")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from universe import symbols, group_of                       # noqa: E402

OUT = os.path.join(_ROOT, "retreat_lab", "out", "universe")


def busy_now(now: dt.time) -> str:
    """Refuse during the two windows where the live engine places orders."""
    if dt.time(15, 25) <= now < dt.time(16, 10):
        return "the 15:45 MOC window (and the 16:05 confirm)"
    if dt.time(8, 55) <= now < dt.time(9, 50):
        return "the 09:15 MOO window (and the 09:35 watchdog)"
    return ""


def write(symbol: str, bars) -> int:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{symbol}.csv")
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        for b in bars:
            w.writerow([b.date.isoformat(), b.open, b.high, b.low, b.close,
                        b.volume])
    os.replace(tmp, path)
    return len(bars)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="fetch the screen universe")
    ap.add_argument("--pace", type=float, default=11.0,
                    help="seconds between requests (default 11 ~ 55/10min)")
    ap.add_argument("--duration", default="5 Y")
    ap.add_argument("--host", default="127.0.0.1",
                    help="TWS/Gateway host (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=7497,
                    help="7497 desktop TWS paper (default), 4002 the "
                         "containerised Gateway in a Codespace")
    ap.add_argument("--client-id", type=int, default=22, dest="client_id")
    ap.add_argument("--force", action="store_true",
                    help="refetch symbols already on disk")
    ap.add_argument("--only", default="", help="comma-separated subset")
    ap.add_argument("--anyway", action="store_true",
                    help="run even inside a trading window")
    args = ap.parse_args(argv)

    from broker_ext import AuctionBroker                      # noqa: PLC0415

    now = dt.datetime.now().time()
    blocked = busy_now(now)
    if blocked and not args.anyway:
        print(f"REFUSED: {now.strftime('%H:%M')} is inside {blocked}. This is a "
              f"45-minute read loop and the engine is about to trade. Run it "
              f"later, or pass --anyway if you know the engine is idle.")
        return 2

    wanted = [s.strip().upper() for s in args.only.split(",") if s.strip()] \
        or symbols()
    os.makedirs(OUT, exist_ok=True)
    todo = [s for s in wanted
            if args.force or not os.path.exists(os.path.join(OUT, f"{s}.csv"))]

    print(f"universe {len(wanted)} symbols, {len(wanted)-len(todo)} already on "
          f"disk, {len(todo)} to fetch")
    if not todo:
        print("nothing to do")
        return 0
    print(f"pace {args.pace:.0f}s → about {len(todo)*args.pace/60:.0f} minutes\n")

    # `primary=""` matters: the engine qualifies against ARCA, which is right
    # for SOXL and XLU and wrong for most of a 235-name universe. SMART with no
    # primary lets IBKR resolve the listing itself.
    broker = AuctionBroker(host=args.host, port=args.port,
                           client_id=args.client_id, exchange="SMART",
                           primary="", dry_run=True,
                           on_event=lambda l, m: None)
    ok = skipped = 0
    started = time.time()
    try:
        try:
            broker.connect()
        except Exception as exc:                              # noqa: BLE001
            alt = 4002 if args.port == 7497 else 7497
            print(f"could not reach {args.host}:{args.port} — {str(exc)[:70]}\n"
                  f"  7497 is desktop TWS (paper); 4002 is the containerised\n"
                  f"  Gateway that `band_lab/live/deploy/docker-compose.yml`\n"
                  f"  publishes. Try --port {alt}.")
            return 3
        for i, sym in enumerate(todo, 1):
            try:
                bars = broker.daily_sessions(sym, None, args.duration)
                if len(bars) < 200:
                    print(f"  [{i:>3}/{len(todo)}] {sym:<7} only {len(bars)} "
                          f"bars — skipped")
                    skipped += 1
                else:
                    n = write(sym, bars)
                    ok += 1
                    print(f"  [{i:>3}/{len(todo)}] {sym:<7} {n:>5} bars "
                          f"{bars[0].date} → {bars[-1].date}  ({group_of(sym)})")
            except Exception as exc:                          # noqa: BLE001
                print(f"  [{i:>3}/{len(todo)}] {sym:<7} FAILED: "
                      f"{str(exc)[:70]} — skipped")
                skipped += 1
            if i < len(todo):
                time.sleep(args.pace)
    except KeyboardInterrupt:
        print("\n  interrupted — rerun to continue where this stopped")
    finally:
        try:
            broker.disconnect()
        except Exception:                                     # noqa: BLE001
            pass

    print(f"\n  {ok} fetched, {skipped} skipped, "
          f"{(time.time()-started)/60:.0f} minutes")
    print(f"  wrote {OUT}")
    print(f"  now run:  python retreat_lab/tail_screen.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
