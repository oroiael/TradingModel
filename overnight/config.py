"""Deployment settings, and the guards that make a wrong one fail loudly.

Follows `band_lab/live/config.py`: a frozen-ish dataclass with a `validate()`
that refuses anything which is a strategy change in disguise. The strategy
numbers themselves live in `constants.py` and are not repeated here — what is
here is *where* and *how much*, not *what*.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

from constants import (
    COVER_MULTIPLE_LIVE,
    COVER_SYMBOL,
    MIN_HISTORY,
    PRIMARY_MULTIPLE,
    PRIMARY_SYMBOL,
    RV_LAG,
    RV_WINDOW,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
TIMEZONE = "America/New_York"


def _t(h: int, m: int, s: int = 0) -> dt.time:
    return dt.time(h, m, s)


@dataclass
class OvernightConfig:
    # ---- connection -------------------------------------------------------
    host: str = "127.0.0.1"
    #: 7497 TWS paper, 7496 TWS live, 4002 Gateway paper, 4001 Gateway live.
    port: int = 7497
    #: Its own id, distinct from band_lab's engine (11) and watchdog (12), so
    #: the two systems can never adopt each other's orders.
    client_id: int = 21
    #: IBKR account id. Required when the login reports more than one, because
    #: every account read otherwise sums across all of them.
    account: str = ""
    exchange: str = "SMART"
    primary_exchange: str = "ARCA"

    # ---- safety -----------------------------------------------------------
    #: False rehearses: decisions computed and logged, nothing sent. `readonly`
    #: in ib_async does NOT stop orders — the adapter enforces this.
    transmit: bool = False
    #: Refuse to start against a live-money port unless explicitly acknowledged.
    allow_live_account: bool = False
    #: Run a job OUTSIDE its clock window, for a pre-flight of the data path.
    #:
    #: The 15:50 and 09:29:30 guards exist for one reason: an auction order
    #: arriving after them is *rejected*, and after 15:50 an MOC can be neither
    #: cancelled nor reduced. Neither statement says anything about a run that
    #: places nothing. So this is allowed only with `transmit` off, and
    #: `validate()` below refuses the combination rather than trusting a caller.
    rehearse_now: bool = False
    #: Refuse to size a leg larger than this, whatever equity says. A backstop
    #: against a bad net_liquidation read, not a strategy parameter.
    max_notional: float = 1_000_000.0
    #: Refuse to trade at all below this equity: under it the $0.35 commission
    #: minimum dominates and the measurements are contaminated. STRATEGY.md §3.5.
    #: The paper account holds $140,000, so this is a floor, not a constraint.
    min_equity: float = 12_228.0

    # ---- sizing -----------------------------------------------------------
    primary_multiple: float = PRIMARY_MULTIPLE
    cover_multiple: float = COVER_MULTIPLE_LIVE

    # ---- the two windows, all ET ------------------------------------------
    #: Earliest the enter job will act. Before this, imbalance information is
    #: thin and there is no reason to be early.
    enter_open: dt.time = field(default_factory=lambda: _t(15, 30))
    #: Target. Five minutes of margin before the deadline.
    enter_target: dt.time = field(default_factory=lambda: _t(15, 45))
    #: HARD. `IBKR Order types.md:13` — MOC must be received by 15:50 ET, and
    #: `:14` — it cannot be cancelled or reduced after. Past this the job must
    #: not place anything, because a late MOC is rejected, not queued.
    enter_deadline: dt.time = field(default_factory=lambda: _t(15, 50))

    exit_open: dt.time = field(default_factory=lambda: _t(9, 0))
    exit_target: dt.time = field(default_factory=lambda: _t(9, 15))
    #: HARD, with 25 seconds of margin. `NYSE Arca Auction.md` — new MOO orders
    #: are rejected from 09:29:55, cancels from 09:29.
    exit_deadline: dt.time = field(default_factory=lambda: _t(9, 29, 30))
    #: The auction has printed by here; a position still open is the one
    #: unrecoverable state and must alert.
    exit_confirm_by: dt.time = field(default_factory=lambda: _t(9, 35))

    # ---- data -------------------------------------------------------------
    #: Daily history to request.
    #:
    #: Not a sample-size question — 3 years is 751 observations and plenty. It
    #: is that the walk-forward threshold is a percentile of ALL prior RV, so a
    #: shorter history is a DIFFERENT cut. Measured on SOXL: the p60 is 103.67%
    #: on 3 years against 107.50% on the full history, which flips 5.1% of
    #: decisions and takes max drawdown from -28.9% to -35.2% for the same
    #: return. 4 years lands on 107.49% — the shortest history that reproduces
    #: the backtest — so that is what is fetched.
    history_duration: str = "4 Y"
    #: Refuse to decide on less than this many sessions.
    min_sessions: int = RV_WINDOW + RV_LAG + MIN_HISTORY + 20

    # ---- paths ------------------------------------------------------------
    db_path: str = os.path.join(_HERE, "out", "overnight.db")
    state_path: str = os.path.join(_HERE, "out", "state.json")
    ledger_path: str = os.path.join(_HERE, "out", "ledger.csv")

    @property
    def symbols(self) -> "tuple[str, str]":
        return (PRIMARY_SYMBOL, COVER_SYMBOL)

    def validate(self) -> None:
        if self.rehearse_now and self.transmit:
            raise ValueError(
                "rehearse_now and transmit are mutually exclusive. rehearse_now "
                "removes the 15:50/09:29:30 auction guards, which is only safe "
                "because nothing is sent. Pick one.")
        if self.port in (7496, 4001) and not self.allow_live_account:
            raise ValueError(
                f"port {self.port} is a LIVE-money port. Set allow_live_account "
                f"explicitly if that is really intended.")
        if not (0.0 < self.primary_multiple <= 1.0):
            raise ValueError(f"primary_multiple {self.primary_multiple} outside (0, 1]")
        if not (0.0 < self.cover_multiple < 3.0):
            raise ValueError(
                f"cover_multiple {self.cover_multiple} must be in (0, 3.0) — at "
                f"exactly 3.0 the account sits ON a 3:1 cap, where any adverse "
                f"overnight move puts it over. Deploy 2.5.")
        if self.enter_target >= self.enter_deadline:
            raise ValueError("enter_target must be before enter_deadline")
        if self.exit_target >= self.exit_deadline:
            raise ValueError("exit_target must be before exit_deadline")
        if self.min_sessions < RV_WINDOW + RV_LAG + MIN_HISTORY:
            raise ValueError("min_sessions cannot be below the burn-in requirement")

    def summary(self) -> str:
        mode = ("TRANSMIT" if self.transmit
                else "rehearse OUT OF HOURS (nothing sent)" if self.rehearse_now
                else "rehearse (nothing sent)")
        return (f"{self.host}:{self.port} cid={self.client_id} "
                f"acct={self.account or '(single)'} | {mode} | "
                f"{PRIMARY_SYMBOL} {self.primary_multiple:.2f}x / "
                f"{COVER_SYMBOL} {self.cover_multiple:.2f}x")

    @classmethod
    def load(cls, path: Optional[str] = None) -> "OvernightConfig":
        cfg = cls()
        if path and os.path.exists(path):
            with open(path) as fh:
                raw = json.load(fh)
            for k, v in raw.items():
                if not hasattr(cfg, k):
                    raise ValueError(f"unknown config key: {k}")
                cur = getattr(cfg, k)
                setattr(cfg, k, dt.time.fromisoformat(v) if isinstance(cur, dt.time) else v)
        cfg.validate()
        return cfg

    def to_json(self) -> str:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, dt.time):
                d[k] = v.isoformat()
        return json.dumps(d, indent=2)
