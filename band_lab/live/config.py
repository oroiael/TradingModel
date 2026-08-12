"""
Runtime configuration for the live engine.

`PHASE2_PLAN.md` §3 lists this module and says it "delegates to
phase1/spec_constants.validate_config". That delegation is the point: every
strategy number lives in §12 and this file may only carry *deployment* choices
— host, port, paths, alerting. If a value here could change a fill, it is in
the wrong file.

`EngineConfig.validate()` is called before the engine connects, so a
misconfigured deployment fails at startup rather than at 11:00 with an order
in flight (§6.8 requires a hard startup failure).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from spec_constants import (  # noqa: E402
    DIP_PCT, F_SIZE, GATE_ATR5_MIN, MAX_FILLS, MAX_STOPS, START_TIME,
    STOP_PCT, TARGET_PCT, W_PER_SLEEVE, ConfigError, validate_config,
)

#: §2 of the plan — capital basis is capped so the published cost rows apply.
CAPITAL_CAP = 150_000.0

#: IBKR's documented historical-data pacing, quoted from the TWS API reference
#: (`TWS API/TWS Documentation - Copy Paste from Online.pdf`, Historical Data
#: Limitations): *"Making more than 60 requests within any ten minute period"*,
#: and again under `reqRealTimeBars`: *"no more than 60 API queries in more than
#: 600 seconds"*.
PACING_MAX_REQUESTS = 60
PACING_WINDOW_SECONDS = 600.0

#: Held back from the pacing budget for the historical requests that are not the
#: bar feed: the feature top-up at pre-open (one per symbol), the session-tail
#: fetch at the close (one per symbol), a re-poll after a reconnect, and
#: `diagnose.py` if an operator runs it alongside a live session. Any of those
#: can land inside the same ten-minute window as the feed.
PACING_RESERVE = 12

#: The watchdog treats a heartbeat older than `watchdog.STALE_SECONDS` (120s)
#: as a dead engine. `run.py` touches the heartbeat once per poll, so a poll
#: interval anywhere near that threshold makes the watchdog fire on a healthy
#: session. Four polls of margin is the floor.
HEARTBEAT_POLLS_BEFORE_STALE = 4
WATCHDOG_STALE_SECONDS = 120.0


@dataclass
class EngineConfig:
    # ---- deployment (safe to change) -------------------------------------
    symbols: tuple = ("SOXL", "SOXS")
    host: str = "127.0.0.1"
    port: int = 7497                    # 7497 TWS paper, 7496 TWS live
    client_id: int = 11
    exchange: str = "SMART"
    primary: str = "ARCA"
    db_path: str = os.path.join(_HERE, "out", "live.db")
    capital_cap: float = CAPITAL_CAP
    #: One `reqHistoricalData` per symbol per poll. At 20.0 with two sleeves
    #: this was exactly 60 requests per 600 seconds — IBKR's documented ceiling,
    #: with nothing left for the pre-open top-up or the EOD tail fetch, and only
    #: five seconds clear of the separate "identical requests within 15 seconds"
    #: rule. 30.0 spends 40 of the 60. The strategy is defined on 5-minute
    #: closes, so the cost is that a bar, the 11:00 arm and the re-arm after an
    #: exit are each seen up to ten seconds later than before.
    bar_poll_seconds: float = 30.0
    #: Status line every N seconds so silence is distinguishable from death.
    heartbeat_seconds: float = 900.0
    #: Touched every poll; `watchdog.py` reads its mtime as proof of life.
    heartbeat_file: str = os.path.join(_HERE, "out", "heartbeat.json")
    #: The watchdog connects with its own client id (§6.2).
    watchdog_client_id: int = 12
    #: The watchdog sends orders even when `transmit` is False, and defaults to
    #: doing so on purpose: exposure on the account is real whether or not the
    #: *engine* is rehearsing, and a position left over from a previous session
    #: still has to be closed by 16:00. It is separate from `transmit` rather
    #: than derived from it so the choice is visible, because it contradicts
    #: what `DEPLOYMENT.md` §12.1 promises about a dry run — the same class of
    #: surprise as §4.1's `readonly`, which three documents described wrongly.
    #: Set False (or pass `--no-transmit`) to rehearse both processes together.
    watchdog_transmit: bool = True
    #: Stage 4 acceptance runs a whole session with this True: decisions are
    #: computed and logged, nothing reaches the market.
    transmit: bool = False
    #: Refuse to start against a live-money port unless explicitly acknowledged.
    allow_live_account: bool = False

    # ---- strategy (must equal §12) ---------------------------------------
    f: float = F_SIZE
    w: float = W_PER_SLEEVE
    gate_atr5_min: float = GATE_ATR5_MIN
    dip_pct: float = DIP_PCT
    target_pct: float = TARGET_PCT
    stop_pct: float = STOP_PCT
    max_fills: int = MAX_FILLS
    max_stops: int = MAX_STOPS
    start_time: str = START_TIME
    allow_short: bool = False
    allow_overnight: bool = False

    # ------------------------------------------------------------- checks
    def validate(self) -> None:
        """§6.8 — reject anything that is a strategy change in disguise."""
        validate_config(self)                     # the §12 gate itself
        if self.port in (7496, 4001) and not self.allow_live_account:
            raise ConfigError(
                f"port {self.port} is a LIVE-money port; Phase 2 is paper only. "
                "Set allow_live_account=True only when Phase 3 is signed off.")
        if not self.symbols:
            raise ConfigError("no symbols configured")
        if self.bar_poll_seconds <= 0:
            raise ConfigError("bar_poll_seconds must be positive")
        # §6.8 wants a hard startup failure rather than a discovery at 11:00.
        # A pacing violation does not announce itself as one: it arrives as
        # error 162, "Historical market data Service error message", which is
        # generic enough that on 2026-08-03 it was read as connection
        # contention and the engine carried on with a fortnight-old feature
        # history. Adding a third sleeve at 30s would breach this silently.
        # The poll interval is squeezed from both sides, and neither bound was
        # written down anywhere before. Too fast breaches IBKR's pacing; too
        # slow starves the heartbeat the watchdog reads as proof of life.
        floor = (len(self.symbols) * PACING_WINDOW_SECONDS
                 / (PACING_MAX_REQUESTS - PACING_RESERVE))
        ceiling = WATCHDOG_STALE_SECONDS / HEARTBEAT_POLLS_BEFORE_STALE
        if floor > ceiling:
            raise ConfigError(
                f"{len(self.symbols)} symbols cannot be polled safely at any "
                f"interval: pacing needs at least {floor:.0f}s and the "
                f"watchdog's {WATCHDOG_STALE_SECONDS:.0f}s staleness threshold "
                f"allows at most {ceiling:.0f}s. Fewer symbols, or raise "
                f"watchdog.STALE_SECONDS and this together — deliberately, "
                f"because it also slows every detection of a dead engine.")
        if not floor <= self.bar_poll_seconds <= ceiling:
            per_window = len(self.symbols) * (PACING_WINDOW_SECONDS
                                              / self.bar_poll_seconds)
            raise ConfigError(
                f"bar_poll_seconds={self.bar_poll_seconds:g} is outside the "
                f"workable {floor:.0f}-{ceiling:.0f}s window for "
                f"{len(self.symbols)} symbol(s). It would send "
                f"{per_window:.0f} historical requests per "
                f"{PACING_WINDOW_SECONDS:.0f}s against IBKR's documented limit "
                f"of {PACING_MAX_REQUESTS} (less {PACING_RESERVE} reserved), or "
                f"leave fewer than {HEARTBEAT_POLLS_BEFORE_STALE} heartbeats "
                f"before the watchdog calls a healthy engine dead. §6.8 wants "
                f"this to fail at startup rather than at 11:00: a pacing "
                f"violation arrives as error 162, 'Historical market data "
                f"Service error message', which on 2026-08-03 was read as "
                f"connection contention while the engine traded on a "
                f"fortnight-old feature history.")
        if self.heartbeat_seconds < 0:
            raise ConfigError("heartbeat_seconds must be >= 0 (0 disables)")

    # ---------------------------------------------------------------- I/O
    @classmethod
    def load(cls, path: Optional[str] = None) -> "EngineConfig":
        """Load from JSON, falling back to the defaults (which are §12)."""
        if not path or not os.path.exists(path):
            cfg = cls()
        else:
            with open(path) as fh:
                cfg = cls(**{**asdict(cls()), **json.load(fh)})
        cfg.validate()
        return cfg

    def summary(self) -> str:
        mode = "TRANSMIT ON" if self.transmit else "transmit OFF (dry run)"
        return (f"{','.join(self.symbols)} @ {self.host}:{self.port} "
                f"clientId={self.client_id} | f={self.f} w={self.w} "
                f"cap={self.capital_cap:,.0f} | {mode}")
