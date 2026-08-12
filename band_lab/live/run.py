"""
The service entrypoint — Stage 4's §5 timetable, driven by a wall clock.

    python3 band_lab/live/run.py --dry-run          # transmit off (Stage 4)
    python3 band_lab/live/run.py --config live.json # a real paper session

`engine.py` owns the timetable's *logic*; this file owns *when*. Splitting
them is what lets the whole timetable be tested against `FakeIB` with no
clock at all — `Engine` is driven by explicit calls in the tests and by this
loop in production.

Restart safety (§5): the loop reconciles from the broker on every connect and
re-fetches the session's bars rather than trusting memory, so starting at
13:00 after a crash produces the same state as having run since 09:30. The
23:00 TWS restart is therefore not a special case.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import features                                            # noqa: E402
from broker import (                                        # noqa: E402
    Broker, BrokerError, IBBroker, MarketClosedError, NotLiveDataError,
)
from config import EngineConfig                            # noqa: E402
from engine import Engine, FLATTEN_IDX, START_IDX          # noqa: E402
from feed import BarFeed                                   # noqa: E402
from store import Store                                    # noqa: E402

NY = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(_HERE))


def _at(day: datetime, hh: int, mm: int) -> datetime:
    return day.replace(hour=hh, minute=mm, second=0, microsecond=0)


class Runner:
    """One trading day, start to finish."""

    def __init__(self, cfg: EngineConfig, broker: Optional[Broker] = None,
                 store: Optional[Store] = None, root: str = ROOT) -> None:
        self.cfg = cfg
        self.root = root
        self.store = store or Store(cfg.db_path)
        self.broker = broker or IBBroker(
            host=cfg.host, port=cfg.port, client_id=cfg.client_id,
            exchange=cfg.exchange, primary=cfg.primary,
            dry_run=not cfg.transmit, on_event=self._event)
        self.engine = Engine(self.broker, self.store, symbols=cfg.symbols,
                             f=cfg.f, w=cfg.w, capital_cap=cfg.capital_cap,
                             on_event=self._event)
        self.feeds = {s: BarFeed(self.broker, s) for s in cfg.symbols}
        self.session = ""

    def _event(self, level: str, msg: str) -> None:
        stamp = datetime.now(NY).strftime("%H:%M:%S")
        print(f"{stamp} [{level:8}] {msg}", flush=True)
        try:
            self.store.event(level, "runner", msg, session=self.session or None)
        except Exception:                                   # noqa: BLE001
            pass                                            # logging must not kill the run

    # ------------------------------------------------------------- 06:00
    def pre_open(self, day: datetime) -> bool:
        self.session = day.strftime("%Y%m%d")
        self._event("info", f"pre-open {self.session} | {self.cfg.summary()}")
        self._connect()

        boots = {}
        for symbol in self.cfg.symbols:
            b = features.build(symbol, self.root, broker=self.broker,
                               today=day, store=self.store)
            boots[symbol] = b
            # `sessions` is the trimmed thr80 window and `from_csv` is the whole
            # file, so these never summed and the line read as a typo. The
            # operator's real question at 06:00 is "did the top-up reach the
            # broker" — a stale CSV computes ATR5 from week-old data and says
            # nothing, so it is called out rather than left to arithmetic.
            last = f"{b.last_session:%Y-%m-%d}" if b.last_session else "none"
            self._event("info",
                        f"{symbol}: {b.sessions} sessions in window | "
                        f"+{b.from_broker} from broker | "
                        f"csv holds {b.from_csv} | last session {last}")
            if b.from_broker == 0:
                self._event("error",
                            f"{symbol}: the broker top-up added no sessions — "
                            f"ATR5 and thr80 are being computed from history "
                            f"ending {last}. Verify before trusting the gate.")
        if not features.check(boots, self._event, today=day):
            self._event("critical", "feature history is insufficient or stale — "
                                    "refusing to start. Nothing was traded.")
            return False

        for f in self.feeds.values():
            f.reset()
        self.engine.pre_open(day, {s: b.history for s, b in boots.items()})
        return any(not rt.dormant for rt in self.engine.sleeves.values())

    # --------------------------------------------------------- the session
    def touch_heartbeat(self) -> None:
        """Proof of life for `watchdog.py`, written every poll.

        A file rather than the SQLite store: the watchdog must be able to tell
        "the engine is alive" without taking a lock on the database the engine
        is writing to, and an mtime is the cheapest possible statement of it.
        """
        path = self.cfg.heartbeat_file
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            payload = {
                "ts": datetime.now(NY).isoformat(),
                "session": self.session,
                "pid": os.getpid(),
                # So the watchdog can notice the one mismatch that matters: an
                # engine rehearsing with transmit off while a watchdog armed to
                # send real orders watches the same account.
                "transmit": bool(self.cfg.transmit),
                "sleeves": {s: ("dormant" if rt.dormant else
                                getattr(rt.sm.state, "name", "?"))
                            for s, rt in self.engine.sleeves.items()},
            }
            tmp = f"{path}.tmp"
            with open(tmp, "w") as fh:
                json.dump(payload, fh)
            os.replace(tmp, path)        # atomic; the watchdog never sees a partial
        except Exception:                                   # noqa: BLE001
            pass                         # a heartbeat must never kill the session

    def heartbeat(self) -> None:
        """Periodic proof of life.

        The engine is silent by design between events, and on a normal day the
        events are hours apart — so silence has two readings, "nothing has
        happened yet" and "this died an hour ago", and the operator cannot tell
        them apart. §1's fifth design priority is observability; this is the
        cheapest possible version of it.
        """
        parts = []
        for symbol, rt in self.engine.sleeves.items():
            if rt.dormant:
                parts.append(f"{symbol} dormant({rt.dormant_reason})")
                continue
            state = getattr(rt.sm.state, "name", str(rt.sm.state))
            bar = self.feeds[symbol].last_idx if symbol in self.feeds else -1
            pos = self.broker.position(symbol)
            bit = (f"{symbol} {state} bar={bar} "
                   f"fills={rt.sm.fills} stops={rt.sm.stop_outs}")
            if abs(pos) > 1e-9:
                bit += f" POS={pos:.0f}"
            parts.append(bit)
        self._event("info", "heartbeat | " + " | ".join(parts or ["no sleeves"]))

    def feeds_to_poll(self):
        """The feeds worth a `reqHistoricalData` on this pass.

        Once every sleeve is dormant no bar can change a decision, and the feed
        becomes pure cost — one historical request per symbol per poll, out of
        the 60-per-600s IBKR documents. The loop itself keeps running, because a
        dormant day can still owe the account a 15:55 flatten: `day` no longer
        returns early when the sleeves are all dormant but the account is not
        flat.
        """
        if self.engine.sleeves and all(rt.dormant
                                       for rt in self.engine.sleeves.values()):
            return ()
        return self.feeds.items()

    def run_session(self, day: datetime, sleep: float = None,
                    heartbeat: float = None) -> None:
        """09:30 -> 15:55. Polls the feed, drives the engine, drains fills."""
        sleep = self.cfg.bar_poll_seconds if sleep is None else sleep
        heartbeat = self.cfg.heartbeat_seconds if heartbeat is None else heartbeat
        flatten_at = _at(day, 15, 55)
        last_beat = time.monotonic()
        while datetime.now(NY) < flatten_at:
            try:
                self._connect()
                for symbol, feed in self.feeds_to_poll():
                    for bar in feed.poll(datetime.now(NY)):
                        try:
                            self.engine.on_bar(symbol, bar)
                        except Exception as exc:            # noqa: BLE001
                            # One bad bar must not discard the rest. `poll`
                            # marks every bar it returns as seen, so an
                            # exception escaping this loop used to drop every
                            # remaining bar permanently — on 2026-08-06 a
                            # failure on bar 0 silently lost bars 1-42 and the
                            # anchor was built from two bars out of 44.
                            self._event("error",
                                        f"{symbol} bar {bar.idx}: {exc!r} — "
                                        f"skipped; later bars still processed")
                # §2.5's activation is a clock event, not a bar event: the
                # feed only reports *completed* bars, so waiting for bar 18
                # armed at 11:05 and cost ~6% of the edge every session.
                self.engine.activate_due(datetime.now(NY))
                self.engine.poll(max((f.last_idx for f in self.feeds.values()),
                                     default=-1))
                self.touch_heartbeat()
                if self.engine.day_loss_breached():
                    self._event("critical", "day-loss condition — flattening early")
                    break
            except NotLiveDataError as exc:
                # Containment lives in `on_bar` and `activate_due`, which stand
                # one sleeve down. Reaching here means some other path raised
                # it, and this handler used to `break` — ending the session for
                # both sleeves over one symbol's entitlement, which is the
                # 2026-08-06 failure the containment was added to prevent.
                #
                # Stand down what the error names, or everything when it names
                # nothing, and keep the loop running. A dormant session costs a
                # heartbeat (`feeds_to_poll` returns empty) and still owes the
                # account its 15:55 flatten.
                self.engine.stand_down(getattr(exc, "symbol", None),
                                       "not_live_data", str(exc))
            except BrokerError as exc:
                self._event("error", f"broker: {exc}; will reconnect")
            except Exception as exc:                        # noqa: BLE001
                self._event("error", f"session loop: {exc!r}")
            if heartbeat > 0 and time.monotonic() - last_beat >= heartbeat:
                last_beat = time.monotonic()
                try:
                    self.heartbeat()
                except Exception as exc:                    # noqa: BLE001
                    self._event("error", f"heartbeat: {exc!r}")
            # The whole poll interval used to be spent with the event loop
            # stopped, so order status, executions and the no-live-data error
            # handler were all delivered up to `sleep` seconds late — in bursts,
            # whenever `reqHistoricalData` happened to pump the loop.
            self.broker.wait(sleep)

    # ------------------------------------------------------ 15:55 / 16:10
    def close_out(self, now: Optional[datetime] = None) -> dict:
        self._event("info", "15:55 flatten")
        # §12's HARD_FLAT_BY is a wall-clock deadline, so the flatten needs the
        # wall clock. The engine does not read it for itself — see flatten_all.
        flat = self.engine.flatten_all(now=now or datetime.now(NY))
        for symbol, ok in flat.items():
            if not ok:
                self._event("critical", f"{symbol} did not flatten on the first pass")
        if not self.engine.verify_flat():
            self._event("critical", "NOT FLAT — manual intervention required")
        # Complete the bar record before the daily row is written: the session
        # loop stops at 15:55, and `report.py`'s shadow is force-flattened early
        # without the last two bars. Evidence only — no decision follows it.
        self.engine.record_session_tail(now or datetime.now(NY))
        return self.engine.reconcile()

    # ------------------------------------------------------------ helpers
    def _connect(self) -> None:
        if self.broker.connected:
            return
        self.broker.connect()
        # §3 — every connect is a restart; reconcile before doing anything else.
        for symbol, summary in self.engine.on_connect().items():
            if not summary.get("agrees", True):
                self._event("error", f"{symbol} reconcile mismatch on connect: {summary}")

    def day(self, day: Optional[datetime] = None, sleep: float = None,
            heartbeat: float = None) -> dict:
        day = day or datetime.now(NY)
        if day.weekday() >= 5:
            # Cheap and local; the broker is still authoritative for holidays,
            # but there is no reason to open a connection on a Sunday.
            self._event("info", f"{day:%Y-%m-%d} is a {day:%A} — market closed, "
                                "nothing to do")
            return {}
        if not self.pre_open(day):
            reasons = {s: rt.dormant_reason for s, rt in self.engine.sleeves.items()}
            closed = all(r == "market_closed" for r in reasons.values())
            self._event("info", "market closed today — nothing to do" if closed
                        else f"all sleeves dormant — no session to run: {reasons}")

            # "No session to run" was taken to mean "nothing to do", and the day
            # returned here — past the 15:55 flatten and past the 16:00 verify.
            # But a dormant sleeve is only a decision not to *open* anything; a
            # position inherited from a process that died is exactly as real on
            # a gated-off day, and §1's first priority does not take the day off
            # with the gate.
            held = {s: self.broker.position(s) for s in self.cfg.symbols}
            held = {s: p for s, p in held.items() if abs(p) > 1e-9}
            if not held:
                return self.engine.reconcile()
            if closed:
                # No RTH to flatten into. Say so as loudly as possible and stop:
                # sending a market order at a closed exchange is not a fix.
                self._event("critical",
                            f"market closed and the account is NOT FLAT: {held}. "
                            f"Nothing can be done from here — close it by hand at "
                            f"the next open.")
                return self.engine.reconcile()
            self._event("critical",
                        f"every sleeve is dormant but the account holds {held}. "
                        f"Staying up to flatten at 15:55 — the gate stops this "
                        f"engine opening a position, not closing one.")
            # Falls through. `run_session` skips the bar feed while every sleeve
            # is dormant, so this costs a heartbeat and nothing else.
        self.heartbeat()
        self.run_session(day, sleep=sleep, heartbeat=heartbeat)
        return self.close_out()


def main() -> int:
    ap = argparse.ArgumentParser(description="band_lab live engine")
    ap.add_argument("--config", default=None, help="JSON config; defaults are §12")
    ap.add_argument("--dry-run", action="store_true",
                    help="transmit OFF — Stage 4 acceptance mode")
    ap.add_argument("--transmit", action="store_true",
                    help="ARM THE ORDER PATH — orders reach the market. Paper only; "
                         "the live-money ports are refused by config validation.")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--poll", type=float, default=None)
    ap.add_argument("--heartbeat", type=float, default=None,
                    help="seconds between status lines (0 disables; default 900)")
    args = ap.parse_args()

    if args.dry_run and args.transmit:
        print("--dry-run and --transmit are contradictory; refusing to guess.")
        return 2

    cfg = EngineConfig.load(args.config)
    if args.transmit:
        cfg.transmit = True
    if args.dry_run:
        cfg.transmit = False
    cfg.validate()                       # §6.8; also refuses live-money ports

    if not cfg.transmit:
        print("=" * 72)
        print("DRY RUN — transmit is OFF. Decisions are computed and logged;")
        print("the broker adapter is read-only. Nothing reaches the market.")
        print("=" * 72)
    else:
        # Loud, and in the log: which account, which port, how big. The failure
        # this guards against is not a wrong click, it is a session that was
        # believed to be a dry run.
        print("=" * 72)
        print("*** TRANSMIT ON — ORDERS WILL REACH THE MARKET ***")
        print(f"    port {cfg.port} "
              f"({'PAPER' if cfg.port in (7497, 4002) else 'CHECK THIS PORT'})"
              f"   clientId={cfg.client_id}")
        print(f"    {','.join(cfg.symbols)} at f={cfg.f} w={cfg.w} "
              f"cap=${cfg.capital_cap:,.0f}")
        print("    First order is possible only after the 11:00 bar (§2.3).")
        print("=" * 72)

    runner = Runner(cfg, root=args.root)
    try:
        summary = runner.day(sleep=args.poll, heartbeat=args.heartbeat)
    finally:
        runner.broker.disconnect()
    if not summary:
        print("\nNo session today (weekend or holiday). Nothing to reconcile.")
        return 0
    ok = all(s.get("agrees", False) for s in summary.values())
    print(f"\nEOD reconcile: {'AGREES' if ok else 'MISMATCH — investigate'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
