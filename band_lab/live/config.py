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
    bar_poll_seconds: float = 20.0
    #: Status line every N seconds so silence is distinguishable from death.
    heartbeat_seconds: float = 900.0
    #: Touched every poll; `watchdog.py` reads its mtime as proof of life.
    heartbeat_file: str = os.path.join(_HERE, "out", "heartbeat.json")
    #: The watchdog connects with its own client id (§6.2).
    watchdog_client_id: int = 12
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
