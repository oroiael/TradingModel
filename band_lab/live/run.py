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
            readonly=not cfg.transmit, on_event=self._event)
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
    def run_session(self, day: datetime, sleep: float = None) -> None:
        """09:30 -> 15:55. Polls the feed, drives the engine, drains fills."""
        sleep = self.cfg.bar_poll_seconds if sleep is None else sleep
        flatten_at = _at(day, 15, 55)
        while datetime.now(NY) < flatten_at:
            try:
                self._connect()
                for symbol, feed in self.feeds.items():
                    for bar in feed.poll(datetime.now(NY)):
                        self.engine.on_bar(symbol, bar)
                self.engine.poll(max((f.last_idx for f in self.feeds.values()),
                                     default=-1))
                if self.engine.day_loss_breached():
                    self._event("critical", "day-loss condition — flattening early")
                    break
            except NotLiveDataError as exc:
                self._event("critical", f"{exc} — standing down for the session")
                break
            except BrokerError as exc:
                self._event("error", f"broker: {exc}; will reconnect")
            except Exception as exc:                        # noqa: BLE001
                self._event("error", f"session loop: {exc!r}")
            time.sleep(sleep)

    # ------------------------------------------------------ 15:55 / 16:10
    def close_out(self) -> dict:
        self._event("info", "15:55 flatten")
        flat = self.engine.flatten_all()
        for symbol, ok in flat.items():
            if not ok:
                self._event("critical", f"{symbol} did not flatten on the first pass")
        if not self.engine.verify_flat():
            self._event("critical", "NOT FLAT — manual intervention required")
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

    def day(self, day: Optional[datetime] = None, sleep: float = None) -> dict:
        day = day or datetime.now(NY)
        if day.weekday() >= 5:
            # Cheap and local; the broker is still authoritative for holidays,
            # but there is no reason to open a connection on a Sunday.
            self._event("info", f"{day:%Y-%m-%d} is a {day:%A} — market closed, "
                                "nothing to do")
            return {}
        if not self.pre_open(day):
            reasons = {s: rt.dormant_reason for s, rt in self.engine.sleeves.items()}
            if all(r == "market_closed" for r in reasons.values()):
                self._event("info", "market closed today — nothing to do")
            else:
                self._event("info", f"all sleeves dormant — no session to run: {reasons}")
            return self.engine.reconcile()
        self.run_session(day, sleep=sleep)
        return self.close_out()


def main() -> int:
    ap = argparse.ArgumentParser(description="band_lab live engine")
    ap.add_argument("--config", default=None, help="JSON config; defaults are §12")
    ap.add_argument("--dry-run", action="store_true",
                    help="transmit OFF — Stage 4 acceptance mode")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--poll", type=float, default=None)
    args = ap.parse_args()

    cfg = EngineConfig.load(args.config)
    if args.dry_run:
        cfg.transmit = False
    cfg.validate()

    if not cfg.transmit:
        print("=" * 72)
        print("DRY RUN — transmit is OFF. Decisions are computed and logged;")
        print("the broker adapter is read-only. Nothing reaches the market.")
        print("=" * 72)

    runner = Runner(cfg, root=args.root)
    try:
        summary = runner.day(sleep=args.poll)
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
