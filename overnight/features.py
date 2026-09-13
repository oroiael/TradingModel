"""Daily bars in, realised volatility and walk-forward thresholds out.

This is the input half of the strategy. It has no broker and no decisions: it
turns a price history into the two numbers `core.py` needs, and nothing else.

Two things here are easy to get wrong and are therefore stated rather than
implied:

**The RV window ends at D-1, not D.** `RV_LAG` exists because an MOC order must
reach NYSE markets by 15:50 ET, so day D's close cannot be an input to the
decision that submits it. `window_end_index` is the only place that arithmetic
lives.

**The threshold is walk-forward, never a constant.** `threshold_at` sees only
the history strictly before the day it is asked about. A fitted number typed
into a config file would be a different strategy — one that knew, in 2023, where
2026's volatility would rank.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
from dataclasses import dataclass
from statistics import stdev
from typing import Optional, Sequence

from constants import (
    ANNUALISATION,
    MIN_HISTORY,
    PERCENTILE,
    RV_LAG,
    RV_WINDOW,
)

ZONE_SUFFIX = " America/New_York"


@dataclass(frozen=True)
class Session:
    """One trading session's open and close. The only bar shape this uses."""

    date: dt.date
    open: float
    close: float


def load_sessions(path: str) -> list[Session]:
    """Read a CSV of bars into one Session per date, ordered.

    Accepts both conventions in this repository: intraday grids stamped
    `YYYYMMDD HH:MM:SS America/New_York` (first bar of the day supplies the
    open, last supplies the close) and daily bars stamped `YYYY-MM-DD`.
    """
    opens: dict[dt.date, float] = {}
    closes: dict[dt.date, float] = {}
    order: list[dt.date] = []
    with open(path) as fh:
        reader = csv.reader(fh)
        next(reader)
        for row in reader:
            stamp = row[0].replace(ZONE_SUFFIX, "")
            try:
                day = dt.datetime.strptime(stamp, "%Y%m%d %H:%M:%S").date()
            except ValueError:
                day = dt.date.fromisoformat(stamp[:10])
            if day not in opens:
                opens[day] = float(row[1])
                order.append(day)
            closes[day] = float(row[4])
    return [Session(d, opens[d], closes[d]) for d in order]


def close_to_close(sessions: Sequence[Session]) -> list[float]:
    """Simple returns between consecutive closes.

    Element k is the return from `sessions[k]`'s close to `sessions[k+1]`'s, so
    the list is one shorter than `sessions`. Every window index below is stated
    against this convention.
    """
    return [sessions[i].close / sessions[i - 1].close - 1
            for i in range(1, len(sessions))]


def window_end_index(decision_index: int, lag: int = RV_LAG) -> int:
    """Exclusive end, in `close_to_close` space, of the window for a decision day.

    The last return in the window is the one ENDING at the close of
    `decision_index - lag`. With lag=1 that is D-1's close, which is the newest
    price known at the 15:50 MOC deadline.
    """
    return decision_index - lag


def realised_vol(
    returns: Sequence[float],
    decision_index: int,
    window: int = RV_WINDOW,
    lag: int = RV_LAG,
) -> Optional[float]:
    """Annualised realised volatility in percent, or None if history is short."""
    end = window_end_index(decision_index, lag)
    start = end - window
    if start < 0 or end > len(returns):
        return None
    return stdev(returns[start:end]) * (ANNUALISATION ** 0.5) * 100.0


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile.

    Matches the research code exactly. `numpy.percentile`'s default ("linear")
    agrees with this, but numpy is not a dependency of the live path and a
    silent disagreement here would move which nights trade.
    """
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def threshold_at(
    history: Sequence[float],
    p: float = PERCENTILE,
    min_history: int = MIN_HISTORY,
) -> Optional[float]:
    """The eligibility cut from prior observations only.

    `history` must contain only values from days strictly before the day being
    decided. Passing the current day's own RV would leak it into its own
    threshold; callers build the history incrementally for that reason.
    """
    if len(history) < min_history:
        return None
    return percentile(history, p)


@dataclass(frozen=True)
class DailyFeature:
    """Everything known about one decision day for one instrument."""

    date: dt.date
    rv: Optional[float]
    threshold: Optional[float]
    next_date: dt.date
    calendar_days: int
    overnight_return: float


def build(sessions: Sequence[Session],
          window: int = RV_WINDOW,
          lag: int = RV_LAG,
          p: float = PERCENTILE,
          min_history: int = MIN_HISTORY) -> "dict[dt.date, DailyFeature]":
    """Walk the history forward, emitting one feature row per decidable day.

    A day is decidable when its RV window fits behind it and a following session
    exists to close the position into. `overnight_return` is the realised
    close-to-next-open move and is for measurement only — it is not, and must
    not become, an input to the decision.
    """
    returns = close_to_close(sessions)
    out: dict[dt.date, DailyFeature] = {}
    history: list[float] = []
    first = window + lag
    for i in range(first, len(sessions) - 1):
        rv = realised_vol(returns, i, window, lag)
        if rv is None:
            continue
        cut = threshold_at(history, p, min_history)
        nxt = sessions[i + 1]
        out[sessions[i].date] = DailyFeature(
            date=sessions[i].date,
            rv=rv,
            threshold=cut,
            next_date=nxt.date,
            calendar_days=(nxt.date - sessions[i].date).days,
            overnight_return=nxt.open / sessions[i].close - 1.0,
        )
        history.append(rv)
    return out
