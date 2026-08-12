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
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime
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
    #: The session `fired` belongs to. Design rule 4 is "one intervention per
    #: session"; without a date to compare against it silently became one per
    #: *process*, and `run()` loops across days.
    fired_on: Optional[date] = None
    _said: list = field(default_factory=list)
    _arming_said: bool = False

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = Store(self.cfg.db_path)
        if self.broker is None:
            self.broker = IBBroker(
                host=self.cfg.host, port=self.cfg.port,
                client_id=self.cfg.watchdog_client_id,      # §6.2 — never the engine's
                exchange=self.cfg.exchange, primary=self.cfg.primary,
                dry_run=not self.cfg.watchdog_transmit, on_event=self.say)

    @property
    def armed(self) -> bool:
        """Will an intervention actually reach the market?"""
        return bool(self.cfg.watchdog_transmit)

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
    def _heartbeat(self) -> Optional[dict]:
        """The engine's last proof of life, or None if it never wrote one."""
        try:
            with open(self.cfg.heartbeat_file) as fh:
                return json.load(fh)
        except Exception:                                   # noqa: BLE001
            return None

    def warn_if_the_engine_is_only_rehearsing(self) -> None:
        """Said once, because it contradicts what the runbook promises.

        `DEPLOYMENT.md` §12.1 tells an operator that during a dry run "nothing
        reaches the market". That covers the engine. This process is armed by
        default and will send real market orders against real exposure, which
        is the point of it — but discovering that from a fill is exactly the
        §4.1 failure again, where three documents described `readonly` as
        something it was not.

        The engine's mode cannot be inferred from this side: `--dry-run` is a
        flag on `run.py`, not a value in the shared config file. So it is read
        from the heartbeat the engine writes. An older engine that does not
        record it leaves this silent rather than guessing.
        """
        if self._arming_said or not self.armed:
            return
        if (self._heartbeat() or {}).get("transmit") is not False:
            return
        self._arming_said = True
        self.say("warn",
                 "the engine is running with transmit OFF while this watchdog "
                 "is ARMED — if the account is exposed past "
                 f"{self.hard_flat:%H:%M} it will send real market orders. That "
                 "is deliberate (exposure is real whether or not the engine is "
                 "rehearsing), but it is not what DEPLOYMENT.md §12.1 promises "
                 "about a dry run. Pass --no-transmit to rehearse both.")

    def heartbeat_age(self, now: Optional[datetime] = None) -> Optional[float]:
        """Seconds since the engine last wrote. None if it never has.

        The file's own timestamp is preferred over its mtime — a copied or
        restored file can have a fresh mtime and stale contents, and trusting
        mtime alone would read that as a living engine.
        """
        now = now or datetime.now(NY)
        beat = self._heartbeat()
        if beat is None:
            return None
        try:
            stamp = datetime.fromisoformat(beat["ts"])
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

    def _flatten_in_flight(self, symbol: str) -> float:
        """Shares already committed to a working market order for `symbol`.

        Any MKT order resting on this contract is closing something — the
        watchdog's own from a previous pass, or an engine flatten that outlived
        the global cancel. Either way, a second one sells the same shares twice.

        Nothing else the engine rests is counted here. A bracket leg is what the
        global cancel is aimed at, and if it survives, that is §6.7 — a problem
        this method cannot fix and must not paper over by refusing to flatten.
        """
        return sum(w.remaining for w in self.broker.working_orders(symbol)
                   if w.order_type == "MKT")

    @staticmethod
    def in_session(now: datetime) -> bool:
        return (now.weekday() < 5
                and SESSION_OPEN <= now.time() <= SESSION_CLOSE)

    # -------------------------------------------------------------- deciding
    def _roll_session(self, now: datetime) -> None:
        """A new trading day re-arms the watchdog.

        Design rule 4 is **one intervention per session** — it exists so that a
        disagreement with the engine inside a single day cannot become a loop of
        duelling orders. `fired` was never cleared, so it delivered one
        intervention per *process* instead, and `run()` loops indefinitely. A
        watchdog that acted on Monday would watch Tuesday through Friday unable
        to act, and say nothing about it: the silent failure it exists to
        prevent, relocated into the watchdog itself.

        Compared with `>` rather than `!=` on purpose. A clock correction that
        steps backwards must not re-arm it inside a session it has already acted
        in — staying dormant is the safe direction of that error.
        """
        today = now.astimezone(NY).date()
        if self.fired and self.fired_on is not None and today > self.fired_on:
            self.say("info", f"new session {today} — re-arming after the "
                             f"intervention on {self.fired_on}")
            self.fired, self.fired_on = False, None

    def verdict(self, now: Optional[datetime] = None) -> tuple[bool, str]:
        """(should_intervene, why). Places no orders and cancels nothing.

        Not quite pure: it clears `fired` when the session date has moved on,
        because every path that asks "should I act?" must get an answer based on
        today rather than on a day that ended. That is the only state it writes.
        """
        now = now or datetime.now(NY)
        self._roll_session(now)
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
    def intervene(self, why: str, attempts: int = 5, settle: float = 3.0,
                  now: Optional[datetime] = None) -> bool:
        """Cancel everything, then sell to flat. The only thing it can do.

        **Never stacks.** This loop used to re-send a full-size market order on
        every pass, which is the defect `OrderManager.ensure_flat` was rewritten
        to remove: three sells of 1,680 against one long 1,680 is a short 3,360,
        and §11 prohibits an inverted position outright. It is strictly worse
        than the failure to flatten it is trying to fix, and a market order that
        has not filled in three seconds is usually still working, not lost.

        Until `broker.wait` replaced `time.sleep` the risk was masked rather than
        absent: the event loop never ran between passes, so `exposure()` returned
        the same frozen snapshot every time and the position never appeared to
        shrink. Now that the watchdog can actually see, it has to look.
        """
        self.say("critical", f"INTERVENING — {why}")
        # Stamped with the session it belongs to, so `_roll_session` can tell
        # "already acted today" from "acted at some point since this process
        # started" — which is the whole of defect F6.
        self.fired = True
        self.fired_on = (now or datetime.now(NY)).astimezone(NY).date()
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
                    # Reading what is already working is part of the decision,
                    # so it sits inside the guard: if the book cannot be read,
                    # sending blind is the one outcome worth avoiding. The pass
                    # is skipped loudly and the next one tries again.
                    working = self._flatten_in_flight(symbol)
                    if working > 0:
                        self.say("info",
                                 f"{symbol} flatten already working for "
                                 f"{working:.0f} — waiting, not re-sending")
                        continue
                    self.broker.place_market(
                        symbol, "SELL" if pos > 0 else "BUY", abs(pos), ref)
                    self.say("critical",
                             f"{symbol} watchdog flatten "
                             f"{'SELL' if pos > 0 else 'BUY'} {abs(pos):.0f}")
                except Exception as exc:                    # noqa: BLE001
                    self.say("error", f"{symbol} flatten failed: {exc!r}")
            if settle > 0:
                self.broker.wait(settle)

        positions, working = self.exposure()
        if positions:
            if not self.armed:
                # Not a failure: nothing was sent because nothing was meant to
                # be. Saying HUMAN INTERVENTION REQUIRED here would train the
                # operator to discount the one message that must never be
                # discounted.
                self.say("warn",
                         f"rehearsal (--no-transmit): would have flattened "
                         f"{positions}; the orders above were logged, not sent")
                return False
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
        self.warn_if_the_engine_is_only_rehearsing()
        act, why = self.verdict(now)
        if act:
            self.intervene(why, now=now)
            return "intervened"
        return why

    def run(self, interval: float = 30.0, quiet_every: int = 20) -> None:
        """§6.2 — check every 30 seconds, for as long as the session lasts."""
        self.say("info" if self.armed else "warn",
                 f"watching | port {self.cfg.port} "
                 f"clientId={self.cfg.watchdog_client_id} | "
                 f"stale>{self.stale_seconds:.0f}s or past "
                 f"{self.hard_flat:%H:%M} while exposed | "
                 + ("ARMED — an intervention sends real market orders"
                    if self.armed else
                    "NOT ARMED (--no-transmit) — it will decide and log, and "
                    "send nothing. Nothing will be closed for you."))
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
            # The watchdog's whole job is sensing, and every sensor it has
            # (`position`, `working_orders`) is a local read. Sleeping deaf for
            # 30s at a time meant `exposure()` returned the snapshot taken at
            # connect and never changed: a watchdog that started flat would
            # never see a position appear.
            self.broker.wait(interval)


def main() -> int:
    ap = argparse.ArgumentParser(description="band_lab flatten watchdog (§6.2)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--once", action="store_true",
                    help="run a single check and exit (cron, or a smoke test)")
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--stale", type=float, default=STALE_SECONDS)
    ap.add_argument("--no-transmit", action="store_true",
                    help="decide and log, but send nothing — for rehearsing "
                         "alongside `run.py --dry-run`. NOTHING WILL BE CLOSED "
                         "FOR YOU: the default is armed, because exposure is "
                         "real whether or not the engine is rehearsing.")
    args = ap.parse_args()

    cfg = EngineConfig.load(args.config)
    if args.no_transmit:
        cfg.watchdog_transmit = False
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
