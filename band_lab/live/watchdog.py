"""
Stage 7 — the watchdog. `IMPLEMENTATION_SPEC.md` §6.2.

    python3 band_lab/live/watchdog.py            # alongside run.py, all session
    python3 band_lab/live/watchdog.py --once     # one check, for cron or a test

A separate process whose only job is to make sure the account ends the day flat
even when the engine cannot. It does nothing at all until one of two conditions
is true, and then it does exactly one thing: cancel everything and sell to flat.

**Why it exists, concretely.** Over 2026-08-05..07 the engine failed to flatten
three sessions running — first by stacking duplicate market orders, then by
racing its own bracket cancels. Each time the position was rescued by a human
reading a log. §6.2 has specified this process since before the engine was
written; the paper run is what made the case unarguable.

Two triggers, deliberately different in kind:

* **The engine stopped heartbeating** (§6.2's own rule: >2 minutes during RTH).
  Covers a crash, a hang, a killed terminal, a slept machine.
* **The hard flatten deadline passed** and something is still open. Covers the
  case §6.2 does not: an engine that is alive, heartbeating, and *wrong* — which
  is precisely what happened on all three of those closes.

Design rules it follows, all from §6:

1. **Its own client id.** Never shares the engine's connection.
2. **Read-only until it acts.** No orders, no cancels, no state, until a trigger
   fires.
3. **It only ever flattens.** It cannot open a position, and it never decides
   anything about strategy.
4. **One intervention per session.** After acting it stays dormant, so a
   disagreement with the engine cannot become a loop of duelling orders.
5. **Loud.** Every decision is printed and persisted, including the ones where
   it decided to do nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from broker import Broker, BrokerError, IBBroker    # noqa: E402
from config import EngineConfig                     # noqa: E402
from store import Store                             # noqa: E402

NY = ZoneInfo("America/New_York")

#: §6.2 — "if the heartbeat stops for >2 minutes during RTH".
STALE_SECONDS = 120.0
#: The engine flattens at 15:55 (§2.8) and must be flat by 16:00. The watchdog
#: gives it three minutes of that budget before taking over, so a slow-but-
#: working flatten is never interrupted mid-fill.
HARD_FLAT = dtime(15, 58)
SESSION_OPEN, SESSION_CLOSE = dtime(9, 30), dtime(16, 0)


@dataclass
class Watchdog:
    cfg: EngineConfig
    broker: Optional[Broker] = None
    store: Optional[Store] = None
    stale_seconds: float = STALE_SECONDS
    hard_flat: dtime = HARD_FLAT
    fired: bool = False
    _said: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = Store(self.cfg.db_path)
        if self.broker is None:
            self.broker = IBBroker(
                host=self.cfg.host, port=self.cfg.port,
                client_id=self.cfg.watchdog_client_id,      # §6.2 — never the engine's
                exchange=self.cfg.exchange, primary=self.cfg.primary,
                readonly=False, on_event=self.say)

    # ------------------------------------------------------------------ log
    def say(self, level: str, msg: str) -> None:
        stamp = datetime.now(NY).strftime("%H:%M:%S")
        print(f"{stamp} [watchdog {level:8}] {msg}", flush=True)
        self._said.append((level, msg))
        try:
            self.store.event(level, "watchdog", msg)
        except Exception:                                   # noqa: BLE001
            pass                        # logging must never stop a flatten

    # ------------------------------------------------------------- sensing
    def heartbeat_age(self, now: Optional[datetime] = None) -> Optional[float]:
        """Seconds since the engine last wrote. None if it never has.

        The file's own timestamp is preferred over its mtime — a copied or
        restored file can have a fresh mtime and stale contents, and trusting
        mtime alone would read that as a living engine.
        """
        now = now or datetime.now(NY)
        path = self.cfg.heartbeat_file
        try:
            with open(path) as fh:
                stamp = datetime.fromisoformat(json.load(fh)["ts"])
        except Exception:                                   # noqa: BLE001
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=NY)
        return (now - stamp).total_seconds()

    def exposure(self) -> tuple[dict, int]:
        """What is actually at risk: positions, and orders that could create one."""
        positions, working = {}, 0
        for symbol in self.cfg.symbols:
            pos = self.broker.position(symbol)
            if abs(pos) > 1e-9:
                positions[symbol] = pos
            working += len(self.broker.working_orders(symbol))
        return positions, working

    @staticmethod
    def in_session(now: datetime) -> bool:
        return (now.weekday() < 5
                and SESSION_OPEN <= now.time() <= SESSION_CLOSE)

    # -------------------------------------------------------------- deciding
    def verdict(self, now: Optional[datetime] = None) -> tuple[bool, str]:
        """(should_intervene, why). Pure — takes no action."""
        now = now or datetime.now(NY)
        if self.fired:
            return False, "already intervened this session"
        if not self.in_session(now):
            return False, "outside RTH"

        positions, working = self.exposure()
        if not positions and not working:
            # Nothing to protect. A stale heartbeat on a flat account is the
            # engine having finished, not the engine having died, and firing
            # reqGlobalCancel at it would be pure risk with nothing to gain.
            return False, "flat and no working orders"

        if now.time() >= self.hard_flat:
            return True, (f"past {self.hard_flat:%H:%M} and still exposed "
                          f"({positions or 'no position'}, {working} working) — "
                          f"§1 forbids holding overnight")

        age = self.heartbeat_age(now)
        if age is None:
            return True, ("no engine heartbeat file at all, and the account is "
                          "exposed")
        if age > self.stale_seconds:
            return True, (f"engine heartbeat {age:.0f}s old (>{self.stale_seconds:.0f}) "
                          f"while exposed")
        return False, f"engine alive ({age:.0f}s), {len(positions)} position(s)"

    # --------------------------------------------------------------- acting
    def intervene(self, why: str, attempts: int = 5, settle: float = 3.0) -> bool:
        """Cancel everything, then sell to flat. The only thing it can do."""
        self.say("critical", f"INTERVENING — {why}")
        self.fired = True
        try:
            self.broker.cancel_all()                        # §6.7 reqGlobalCancel
            self.say("info", "global cancel sent")
        except Exception as exc:                            # noqa: BLE001
            self.say("error", f"global cancel failed: {exc!r}")

        for i in range(attempts):
            positions, _ = self.exposure()
            if not positions:
                self.say("info", f"FLAT after {i} flatten pass(es)")
                return True
            for symbol, pos in positions.items():
                ref = f"WATCHDOG-{datetime.now(NY):%Y%m%d-%H%M%S}-{symbol}"
                try:
                    self.broker.place_market(
                        symbol, "SELL" if pos > 0 else "BUY", abs(pos), ref)
                    self.say("critical",
                             f"{symbol} watchdog flatten "
                             f"{'SELL' if pos > 0 else 'BUY'} {abs(pos):.0f}")
                except Exception as exc:                    # noqa: BLE001
                    self.say("error", f"{symbol} flatten failed: {exc!r}")
            if settle > 0:
                time.sleep(settle)

        positions, working = self.exposure()
        if positions:
            self.say("critical",
                     f"WATCHDOG COULD NOT FLATTEN {positions} "
                     f"({working} orders working) — HUMAN INTERVENTION REQUIRED")
            return False
        self.say("info", "FLAT")
        return True

    # ---------------------------------------------------------------- loop
    def check(self, now: Optional[datetime] = None) -> str:
        now = now or datetime.now(NY)
        try:
            if not self.broker.connected:
                self.broker.connect()
        except BrokerError as exc:
            self.say("error", f"cannot reach the broker: {exc!r}")
            return "no-broker"
        act, why = self.verdict(now)
        if act:
            self.intervene(why)
            return "intervened"
        return why

    def run(self, interval: float = 30.0, quiet_every: int = 20) -> None:
        """§6.2 — check every 30 seconds, for as long as the session lasts."""
        self.say("info", f"watching | port {self.cfg.port} "
                         f"clientId={self.cfg.watchdog_client_id} | "
                         f"stale>{self.stale_seconds:.0f}s or past "
                         f"{self.hard_flat:%H:%M} while exposed")
        ticks = 0
        while True:
            now = datetime.now(NY)
            if now.time() > SESSION_CLOSE and self.in_session(now) is False:
                verdict = self.check(now)
                if verdict == "intervened":
                    ticks = 0
            else:
                verdict = self.check(now)
            ticks += 1
            if ticks % quiet_every == 0:        # a periodic "still here"
                self.say("info", f"ok — {verdict}")
            time.sleep(interval)


def main() -> int:
    ap = argparse.ArgumentParser(description="band_lab flatten watchdog (§6.2)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--once", action="store_true",
                    help="run a single check and exit (cron, or a smoke test)")
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--stale", type=float, default=STALE_SECONDS)
    args = ap.parse_args()

    cfg = EngineConfig.load(args.config)
    wd = Watchdog(cfg, stale_seconds=args.stale)
    try:
        if args.once:
            print(f"verdict: {wd.check()}")
            return 0
        wd.run(interval=args.interval)
    except KeyboardInterrupt:
        wd.say("info", "stopped by hand")
    finally:
        try:
            wd.broker.disconnect()
        except Exception:                                   # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
