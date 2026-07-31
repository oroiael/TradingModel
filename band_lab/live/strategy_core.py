"""
Stage 1 — the pure strategy core.

Every strategy decision the live engine makes is computed here, and nowhere
else. This module has no IBKR, no I/O, no clock and no global state: it is a
pile of functions over numbers, so that `replay.py` can drive it with
historical bars and `sleeve.py` can drive it with live ones, and the two are
provably the same thing.

The §-references are to `band_lab/IMPLEMENTATION_SPEC.md`. The §12 constants
are imported from `band_lab/phase1/spec_constants.py` rather than
re-transcribed — that file is the single source of truth and re-typing the
numbers here would create a second one.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from typing import Sequence

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_PHASE1 = os.path.join(os.path.dirname(_HERE), "phase1")
if _PHASE1 not in sys.path:
    sys.path.insert(0, _PHASE1)

from spec_constants import (  # noqa: E402
    ATR_LOOKBACK,
    DIP_PCT,
    FLATTEN_TIME,
    GATE_ATR5_MIN,
    OR_PCTL,
    OR_PCTL_MINOBS,
    OR_PCTL_WINDOW,
    OR_WINDOW,
    POS10_TOP_THIRD,
    STOP_PCT,
    TARGET_PCT,
    TICK_SIZE,
    bar_index,
    round_to_tick,
)

OR_START_IDX = bar_index(OR_WINDOW[0])      # 0  — the 09:30 bar
OR_END_IDX = bar_index(OR_WINDOW[1])        # 6  — the 10:00 bar (exclusive)
FLATTEN_IDX = bar_index(FLATTEN_TIME)       # 77 — the bar labelled 15:55


# --------------------------------------------------------------------- bars
@dataclass(frozen=True)
class Bar:
    """One 5-minute RTH bar. `idx` is the §2.1 bar index: 0 is the 09:30 bar."""

    idx: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


# ----------------------------------------------------------------- features
@dataclass(frozen=True)
class SessionStats:
    """§2.1 quantities derived from one completed session's bars.

    Only percentages survive into history (`range_pct`, `or30`) — §4 forbids
    using historical price *levels* for anything, and Phase 1 §3.2 S7 shows
    what happens when that rule is broken on SOXS.
    """

    session_open: float
    high: float
    low: float
    close: float
    range_pct: float
    or_high: float
    or_low: float
    close10: float
    or30: float
    pos10: float
    first_bar_idx: int
    last_bar_idx: int
    n_bars: int
    is_half_day: bool
    late_open: bool


def session_stats(bars: Sequence[Bar]) -> SessionStats:
    """§2.1 definitions over one session. `bars` must be one session, ordered."""
    if not bars:
        raise ValueError("session_stats requires at least one bar")
    window = [b for b in bars if OR_START_IDX <= b.idx < OR_END_IDX]
    if window:
        or_high = max(b.high for b in window)
        or_low = min(b.low for b in window)
        # §2.1: pos10 uses the close at 10:00 — the last bar of the opening-range
        # window (the bar labelled 09:55), not the bar labelled 10:00.
        close10 = window[-1].close
    else:
        or_high = or_low = close10 = float("nan")
    span = or_high - or_low
    session_open = bars[0].open
    return SessionStats(
        session_open=session_open,
        high=max(b.high for b in bars),
        low=min(b.low for b in bars),
        close=bars[-1].close,
        range_pct=(max(b.high for b in bars) - min(b.low for b in bars))
        / session_open * 100.0,
        or_high=or_high,
        or_low=or_low,
        close10=close10,
        or30=span / session_open * 100.0,
        # §2.1: "If OR_high == OR_low, use 0.5."
        pos10=(close10 - or_low) / span if span > 0 else 0.5,
        first_bar_idx=bars[0].idx,
        last_bar_idx=bars[-1].idx,
        n_bars=len(bars),
        # §2.2 a scheduled half-day closes before the 15:55 flatten
        is_half_day=bars[-1].idx < FLATTEN_IDX,
        # §4 the session must have opened at 09:30 for the bar clock to mean
        # what §2.1 says it means
        late_open=bars[0].idx > 0,
    )


class FeatureHistory:
    """Rolling per-symbol history behind ATR5 and thr80.

    Live this is fed one row per completed session from SQLite; in replay it is
    fed from the historical bars. Both use *this* code, which is why the
    equivalence test is meaningful.
    """

    def __init__(self) -> None:
        self._range_pct: list[float] = []
        self._or30: list[float] = []

    def __len__(self) -> int:
        return len(self._range_pct)

    def append(self, stats: SessionStats) -> None:
        self._range_pct.append(stats.range_pct)
        self._or30.append(stats.or30)

    def atr5(self) -> float:
        """§2.1 — mean daily_range_pct over the 5 completed sessions before d.

        NaN when fewer than 5 prior sessions exist; §2.2 then refuses the day.
        """
        if len(self._range_pct) < ATR_LOOKBACK:
            return float("nan")
        return float(np.mean(self._range_pct[-ATR_LOOKBACK:]))

    def thr80(self) -> float:
        """§2.1 — 80th percentile of OR30 over the prior 504 sessions.

        Recomputed every session (amended 2026-07; see §2.1 and Phase 1 S1).
        Requires >= 120 prior observations, else NaN and the sleeve stands down.
        """
        if len(self._or30) < OR_PCTL_MINOBS:
            return float("nan")
        window = self._or30[-OR_PCTL_WINDOW:]
        return float(np.quantile(np.asarray(window, dtype=float), OR_PCTL))


# ---------------------------------------------------------------- decisions
@dataclass(frozen=True)
class Decision:
    ok: bool
    reason: str


def gate_decision(atr5: float, is_half_day: bool, late_open: bool,
                  gate_atr5_min: float = GATE_ATR5_MIN) -> Decision:
    """§2.2 daily gate, evaluated before the open.

    Reason strings match `phase1/spec_engine.gate_on` so the two can be diffed
    day by day rather than only on P&L.
    """
    if not np.isfinite(atr5):
        return Decision(False, "atr5_unavailable")
    if atr5 < gate_atr5_min:
        return Decision(False, "atr5_below_gate")
    if is_half_day:
        return Decision(False, "scheduled_half_day")
    if late_open:
        return Decision(False, "incomplete_session_data")
    return Decision(True, "gate_on")


def filter_decision(or30: float, thr80: float, pos10: float) -> Decision:
    """§2.3 morning filter, evaluated once at 10:00.

    Stand down only if the opening range is wide *and* price is not in the top
    third of it — violent up-mornings are traded (V9).
    """
    if not np.isfinite(thr80):
        return Decision(False, "thr80_insufficient_history")
    if not np.isfinite(or30) or not np.isfinite(pos10):
        return Decision(False, "or30_unavailable")
    if or30 >= thr80 and pos10 < POS10_TOP_THIRD:
        return Decision(False, "stand_down_wide_or_weak_pos10")
    return Decision(True, "filter_on")


# ------------------------------------------------------------ price and size
def entry_limit_price(anchor: float, tick_rounding: bool = True,
                      tick: float = TICK_SIZE, dip_pct: float = DIP_PCT) -> float:
    """§2.5 — the resting BUY LIMIT sits `dip_pct` below the session-high anchor."""
    px = anchor * (1.0 - dip_pct)
    return round_to_tick(px, tick) if tick_rounding else px


def target_price(entry_px: float, tick_rounding: bool = True,
                 tick: float = TICK_SIZE, target_pct: float = TARGET_PCT) -> float:
    """§2.6 — the OCA profit target."""
    px = entry_px * (1.0 + target_pct)
    return round_to_tick(px, tick) if tick_rounding else px


def stop_price(entry_px: float, tick_rounding: bool = True,
               tick: float = TICK_SIZE, stop_pct: float = STOP_PCT) -> float:
    """§2.6 — the OCA protective stop. Absolute 4%, never scaled (V4)."""
    px = entry_px * (1.0 - stop_pct)
    return round_to_tick(px, tick) if tick_rounding else px


def order_quantity(f: float, sleeve_capital: float, price: float,
                   whole_shares: bool = True) -> float:
    """§2.4 — `floor(f x sleeve_capital / price)`.

    `whole_shares=False` is the idealised fractional limit the backtest uses;
    live it is always True (Phase 1 §3.2 S7).
    """
    if price <= 0:
        return 0.0
    raw = f * sleeve_capital / price
    return float(math.floor(raw)) if whole_shares else float(raw)
