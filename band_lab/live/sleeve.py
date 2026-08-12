"""
Stage 1 — the per-sleeve state machine.

One instance per symbol. It owns the §2.5-§2.8 lifecycle for a single trading
day and knows nothing about IBKR, wall clocks, files or the other sleeve
(§2: "Neither sleeve ever reads the other's state, prices, or signals").

It never performs an action. It emits `Intent`s, which `replay.py` executes
against historical bars and the Stage 3 OrderManager will execute against
IBKR. That is what makes the live path and the backtest path the same code.

Strategy constants come from `phase1/spec_constants.py` via `strategy_core`
and are deliberately *not* configurable here: `SleeveConfig` carries only
capital, sizing and the two backtest-compatibility switches.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from strategy_core import (  # noqa: E402
    Bar,
    Decision,
    FLATTEN_IDX,
    entry_limit_price,
    filter_decision,
    gate_decision,
    order_quantity,
    stop_price,
    target_price,
)
from spec_constants import (  # noqa: E402
    DIP_PCT,
    F_SIZE,
    GATE_ATR5_MIN,
    MAX_FILLS,
    MAX_STOPS,
    START_TIME,
    STOP_PCT,
    TARGET_PCT,
    TICK_SIZE,
    bar_index,
)

START_IDX = bar_index(START_TIME)            # 18 — the 11:00 bar
# §2.8: flat at 15:55, so the last bar that may hold a position is the one that
# closes at 15:55 — the bar labelled 15:50.
LAST_HOLDING_IDX = FLATTEN_IDX - 1           # 76


class SleeveState(str, Enum):
    PREOPEN = "preopen"
    GATE_OFF = "gate_off"            # §2.2 refused the day
    OBSERVING = "observing"          # gate ON, before the 10:00 filter
    STOOD_DOWN = "stood_down"        # §2.3 refused the day
    WAITING = "waiting"              # filter ON, before 11:00
    ARMED = "armed"                  # entry limit resting
    IN_POSITION = "in_position"
    DONE = "done"                    # counters exhausted, flat for the day
    CLOSED = "closed"                # session over


DORMANT_STATES = (SleeveState.GATE_OFF, SleeveState.STOOD_DOWN,
                  SleeveState.DONE, SleeveState.CLOSED)

#: Exits after which the sleeve does **not** re-arm.
#:
#: "flatten" is §2.8's 15:55 close. "external" is a position closed by
#: something that is not this engine — the watchdog, a hand in TWS, a
#: liquidation — and it is terminal for the same reason but a stronger one:
#: re-arming would put the sleeve straight back into the position that was just
#: taken off it, which is the opposite of what every one of those actors
#: intended. `replay.py` produces only "stop", "target" and "flatten", so this
#: is live-only and the Stage 1 equivalence proof is untouched.
TERMINAL_OUTCOMES = ("flatten", "external")


# ------------------------------------------------------------------ intents
class IntentKind(str, Enum):
    PLACE_ENTRY = "place_entry"
    MODIFY_ENTRY = "modify_entry"
    CANCEL_ENTRY = "cancel_entry"
    PLACE_BRACKET = "place_bracket"
    CANCEL_BRACKET = "cancel_bracket"
    FLATTEN = "flatten"
    DORMANT = "dormant"


@dataclass(frozen=True)
class Intent:
    kind: IntentKind
    bar_idx: int
    limit_px: float = 0.0
    qty: float = 0.0
    target_px: float = 0.0
    stop_px: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class EntryOrder:
    limit_px: float
    qty: float


@dataclass(frozen=True)
class Bracket:
    qty: float
    target_px: float
    stop_px: float


@dataclass(frozen=True)
class Trade:
    entry_bar: int
    exit_bar: int
    entry_px: float
    exit_px: float
    qty: float
    ret: float
    outcome: str                      # "target" | "stop" | "flatten"
    limit_px: float = 0.0             # the resting limit the entry filled against


# ------------------------------------------------------------------- config
@dataclass(frozen=True)
class SleeveConfig:
    symbol: str
    sleeve_capital: float
    f: float = F_SIZE
    # Live always rounds to the cent grid and buys whole shares. The backtest
    # models neither (Phase 1 §3.2 S5/S7); turning both off reproduces it.
    tick_rounding: bool = True
    whole_shares: bool = True
    tick_size: float = TICK_SIZE
    # §2.4 sizes off `limit_price`. The research engine sizes off the *fill*
    # price, which differs only when a gap fills through the limit. "limit" is
    # the spec, "fill" reproduces the validated series — see PHASE2_PARITY.md S9.
    sizing_basis: str = "limit"
    max_fills: int = MAX_FILLS
    max_stops: int = MAX_STOPS
    start_idx: int = START_IDX
    last_holding_idx: int = LAST_HOLDING_IDX
    # V1/V3/V4 levels. These default to the locked §12 values and MUST stay
    # there for anything on the production path — `spec_constants.validate_config`
    # rejects a live engine that moves them. They are settable only so the
    # v2_dev research harness can sweep them without forking the engine, which
    # would reintroduce the "two harnesses" problem PHASE2_PARITY.md warns about.
    dip_pct: float = DIP_PCT              # V1
    target_pct: float = TARGET_PCT        # V3
    stop_pct: float = STOP_PCT            # V4
    gate_atr5_min: float = GATE_ATR5_MIN  # V10 cutoff

    def __post_init__(self):
        if self.sizing_basis not in ("limit", "fill"):
            raise ValueError(f"bad sizing_basis={self.sizing_basis!r}")
        for name in ("dip_pct", "target_pct", "stop_pct"):
            if not 0.0 < getattr(self, name) < 1.0:
                raise ValueError(f"bad {name}={getattr(self, name)!r}")


# ------------------------------------------------------------ state machine
class SleeveStateMachine:
    """§2.5-§2.8 for one symbol, one session."""

    def __init__(self, cfg: SleeveConfig) -> None:
        self.cfg = cfg
        self.date: Any = None
        self.state = SleeveState.PREOPEN
        self.gate: Optional[Decision] = None
        self.filter: Optional[Decision] = None

        self.fills = 0
        self.stop_outs = 0
        self.pnl = 0.0
        self.trades: list[Trade] = []
        self.anchor_updates: list[tuple[int, float, float]] = []

        self._anchor = float("nan")
        self._limit_px = float("nan")
        self._entry: Optional[EntryOrder] = None
        self._bracket: Optional[Bracket] = None
        self._entry_px = 0.0
        self._entry_limit_px = 0.0
        self._entry_bar = -1
        self._qty = 0.0
        self._last_bar_idx = -1
        self._intents: list[Intent] = []

    # ----------------------------------------------------------- properties
    @property
    def in_position(self) -> bool:
        return self.state is SleeveState.IN_POSITION

    @property
    def working_entry(self) -> Optional[EntryOrder]:
        """The resting BUY LIMIT, or None when nothing may rest (§2.6, §2.7)."""
        return self._entry if self.state is SleeveState.ARMED else None

    @property
    def bracket(self) -> Optional[Bracket]:
        return self._bracket if self.in_position else None

    @property
    def entry_bar(self) -> int:
        return self._entry_bar

    @property
    def anchor(self) -> float:
        return self._anchor

    @property
    def limit_price(self) -> float:
        return self._limit_px

    @property
    def trading_today(self) -> bool:
        return self.state not in (SleeveState.PREOPEN, SleeveState.GATE_OFF,
                                  SleeveState.STOOD_DOWN)

    def drain_intents(self) -> list[Intent]:
        out, self._intents = self._intents, []
        return out

    def _emit(self, kind: IntentKind, **kw) -> None:
        self._intents.append(Intent(kind=kind, bar_idx=self._last_bar_idx, **kw))

    # --------------------------------------------------------------- §2.2/3
    def begin_session(self, date: Any, atr5: float, is_half_day: bool,
                      late_open: bool) -> Decision:
        """06:00 pre-open job. A gate-OFF sleeve can place no order today."""
        self.date = date
        self.gate = gate_decision(atr5, is_half_day, late_open,
                                  self.cfg.gate_atr5_min)
        self.state = SleeveState.OBSERVING if self.gate.ok else SleeveState.GATE_OFF
        if not self.gate.ok:
            self._emit(IntentKind.DORMANT, reason=self.gate.reason)
        return self.gate

    def apply_morning_filter(self, or30: float, thr80: float,
                             pos10: float) -> Decision:
        """10:00, on the close of the 09:55 bar. Evaluated once."""
        if self.state is not SleeveState.OBSERVING:
            raise RuntimeError(f"morning filter in state {self.state}")
        self.filter = filter_decision(or30, thr80, pos10)
        self.state = SleeveState.WAITING if self.filter.ok else SleeveState.STOOD_DOWN
        if not self.filter.ok:
            self._emit(IntentKind.DORMANT, reason=self.filter.reason)
        return self.filter

    # ----------------------------------------------------------------- §2.5
    def on_bar_open(self, bar_idx: int) -> None:
        """Called as each bar begins — live, this is the 11:00 timer.

        Activation is a *clock* event, not a bar-close event: at 11:00 the limit
        goes live priced off the bars completed before it. Keeping it here (and
        not in `on_bar_close`) also keeps the anchor honest when a session has
        missing bars, where "the bar before 11:00" and "the last completed bar"
        are not the same thing.
        """
        self._last_bar_idx = bar_idx
        if self.state is SleeveState.WAITING and bar_idx >= self.cfg.start_idx:
            self._activate(bar_idx)

    def on_bar_close(self, bar: Bar) -> None:
        """Fold this bar's high into the anchor and ratchet the limit up.

        The anchor uses *completed bars only* — the forming bar is excluded —
        so a new high inside the current bar cannot raise the limit until that
        bar closes. The limit that goes live at 11:00 is therefore priced off
        bars 0..17.
        """
        self._last_bar_idx = bar.idx
        if not self.trading_today:
            return

        rising = math.isnan(self._anchor) or bar.high > self._anchor
        if rising:
            self._anchor = float(bar.high)

        if rising and self.state in (SleeveState.ARMED, SleeveState.IN_POSITION):
            new_limit = self._limit_from_anchor()
            # §2.5.3: the limit price never moves down.
            if not (new_limit > self._limit_px):
                return
            self._limit_px = new_limit
            self.anchor_updates.append((bar.idx, self._anchor, self._limit_px))
            if self.state is SleeveState.ARMED:
                self._entry = EntryOrder(self._limit_px, self._size(self._limit_px))
                self._emit(IntentKind.MODIFY_ENTRY, limit_px=self._entry.limit_px,
                           qty=self._entry.qty)

    def _limit_from_anchor(self) -> float:
        return entry_limit_price(self._anchor, self.cfg.tick_rounding,
                                 self.cfg.tick_size, self.cfg.dip_pct)

    def _size(self, price: float) -> float:
        return order_quantity(self.cfg.f, self.cfg.sleeve_capital, price,
                              self.cfg.whole_shares)

    def _activate(self, bar_idx: int) -> None:
        """11:00 — the first moment an order may exist (§2.3, §10.5)."""
        if math.isnan(self._anchor):
            self.state = SleeveState.DONE
            self._emit(IntentKind.DORMANT, reason="no_completed_bars_before_start")
            return
        self._limit_px = self._limit_from_anchor()
        self.anchor_updates.append((bar_idx, self._anchor, self._limit_px))
        self._arm(IntentKind.PLACE_ENTRY)

    def _arm(self, kind: IntentKind) -> None:
        """Place (or re-place) the resting entry, or go dormant if it cannot be."""
        if self.fills >= self.cfg.max_fills or self.stop_outs >= self.cfg.max_stops:
            # §2.7 the breaker admits no discretion. Going dormant cancels
            # everything working; the OrderManager treats DORMANT as cancel-all.
            self.state = SleeveState.DONE
            self._entry = None
            self._emit(IntentKind.DORMANT, reason="counters_exhausted")
            return
        qty = self._size(self._limit_px)
        if qty <= 0:                      # §2.4 whole shares only
            self.state = SleeveState.DONE
            self._emit(IntentKind.DORMANT, reason="order_qty_below_one_share")
            return
        self._entry = EntryOrder(self._limit_px, qty)
        self.state = SleeveState.ARMED
        self._emit(kind, limit_px=self._entry.limit_px, qty=qty)

    # ----------------------------------------------------------------- §2.6
    def on_entry_fill(self, price: float, bar_idx: int,
                      qty: Optional[float] = None) -> None:
        """An entry filled at `price`. The OCA bracket goes on immediately."""
        if self.state is not SleeveState.ARMED:
            raise RuntimeError(f"entry fill in state {self.state}")
        if qty is None:
            qty = (self._size(price) if self.cfg.sizing_basis == "fill"
                   else self._entry.qty)
        self._entry_limit_px = self._entry.limit_px
        self._entry = None
        self._entry_px = float(price)
        self._entry_bar = int(bar_idx)
        self._qty = float(qty)
        self.fills += 1
        self.state = SleeveState.IN_POSITION
        self._last_bar_idx = bar_idx
        self._bracket = Bracket(
            qty=self._qty,
            target_px=target_price(self._entry_px, self.cfg.tick_rounding,
                                   self.cfg.tick_size, self.cfg.target_pct),
            stop_px=stop_price(self._entry_px, self.cfg.tick_rounding,
                               self.cfg.tick_size, self.cfg.stop_pct),
        )
        self._emit(IntentKind.PLACE_BRACKET, qty=self._qty,
                   target_px=self._bracket.target_px,
                   stop_px=self._bracket.stop_px)

    def amend_entry(self, price: float, qty: float) -> None:
        """Correct `E` and the size once a fill has finished settling.

        §2.6 prices the bracket off `E` and §2.4's return is computed on the
        quantity held, but IBKR settles one order in as many executions as the
        book requires — so neither is knowable from the first of them. Live on
        2026-08-06 a 541-share entry booked its quantity as 100 and reported a
        +1% target as **+18.1 bp instead of +96.5**.

        A simulated fill is atomic, so `replay.py` never calls this and the
        equivalence proof is untouched. It exists for the live path alone.
        """
        if not self.in_position:
            return
        self._entry_px = float(price)
        self._qty = float(qty)

    def on_exit_fill(self, price: float, bar_idx: int, outcome: str) -> Trade:
        """A bracket leg (or the 15:55 flatten) filled. Book it and re-arm."""
        if not self.in_position:
            raise RuntimeError(f"exit fill in state {self.state}")
        self._last_bar_idx = bar_idx
        ret = self._qty * (price - self._entry_px) / self.cfg.sleeve_capital
        trade = Trade(self._entry_bar, int(bar_idx), self._entry_px, float(price),
                      self._qty, ret, outcome, self._entry_limit_px)
        self.trades.append(trade)
        self.pnl += ret
        if outcome == "stop":
            self.stop_outs += 1
        self._bracket = None
        self._qty = 0.0
        if outcome in TERMINAL_OUTCOMES or bar_idx > self.cfg.last_holding_idx:
            self.state = SleeveState.CLOSED
            self._entry = None
            return trade
        # §2.5/V2: re-arm on the exit event, not at the next bar close. Instant
        # re-entry below the standing session high is +47.9 bp of the 65.6.
        self._arm(IntentKind.PLACE_ENTRY)
        return trade

    # ----------------------------------------------------------------- §2.8
    def flatten(self, price: float, bar_idx: int) -> Optional[Trade]:
        """15:55 — cancel everything, close any position. No exceptions."""
        self._last_bar_idx = bar_idx
        trade = None
        if self.in_position:
            self._emit(IntentKind.CANCEL_BRACKET)
            self._emit(IntentKind.FLATTEN, qty=self._qty, reason="eod_flatten")
            trade = self.on_exit_fill(price, bar_idx, "flatten")
        elif self.state is SleeveState.ARMED:
            self._emit(IntentKind.CANCEL_ENTRY)
        self._entry = None
        self.state = SleeveState.CLOSED
        return trade
