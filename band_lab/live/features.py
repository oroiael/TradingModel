"""
Feature bootstrap — the ATR5 / thr80 history the 06:00 job needs.

`Engine.pre_open` takes a `FeatureHistory` per sleeve; this builds it.
`IMPLEMENTATION_SPEC.md` §7 requires >=520 sessions per symbol, because thr80
is the 80th percentile of OR30 over the prior 504 sessions and refuses to
produce a number below 120 observations.

Two design decisions:

**The repository CSVs are the backbone, IBKR is the top-up.** Re-fetching two
years of 5-minute bars every morning would be ~30 paced requests per symbol
for data that has not changed. The validated 5-minute files already carry six
years; the broker is asked only for sessions after the file ends. That also
means the live engine's features come from the identical series every
published number was produced from, which is what makes the daily
shadow-parity report meaningful.

**Only percentages are ever retained** (§4.4, and the Phase 1 S7 finding):
`FeatureHistory` stores `range_pct` and `or30` and nothing else. SOXS's
back-adjusted series runs to $1.17M/share, and any code path that lets a
historical *price* reach the sizing arithmetic silently zeroes 248 sessions.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from strategy_core import Bar, FeatureHistory, session_stats  # noqa: E402
from spec_constants import OR_PCTL_MINOBS, OR_PCTL_WINDOW      # noqa: E402

#: §7 — enough history for thr80's 504-session window plus slack.
SESSIONS_REQUIRED = 520


class InsufficientHistory(RuntimeError):
    """Fewer sessions than thr80 needs. §2.2 stands the sleeve down anyway,
    but failing loudly at 06:00 is better than a silent OFF day."""


@dataclass
class Bootstrap:
    symbol: str
    history: FeatureHistory
    sessions: int
    last_session: Optional[datetime]
    from_csv: int
    from_broker: int

    @property
    def sufficient(self) -> bool:
        return self.sessions >= OR_PCTL_MINOBS


def _group_by_session(bars: list[Bar], day) -> list[tuple]:
    return [(day, bars)] if bars else []


def build(symbol: str, root: str, broker=None, today: Optional[datetime] = None,
          store=None, required: int = SESSIONS_REQUIRED) -> Bootstrap:
    """CSV backbone + broker top-up -> a FeatureHistory ready for 06:00.

    `broker` may be None (offline / dry run), in which case the history stops
    at the CSV's last session and `sufficient` still reports honestly.
    """
    from replay import load_sessions          # local: keeps import light

    sessions = load_sessions(symbol, root)
    from_csv = len(sessions)
    last = sessions[-1][0] if sessions else None
    from_broker = 0

    if broker is not None and last is not None:
        today = today or datetime.now()
        gap_days = (today.date() - last.date()).days
        if gap_days > 1:
            # One paced request covers the gap. 5-minute bars for a few weeks
            # sit well inside any plausible duration limit — §6.4 is still an
            # open question, so the request is deliberately small, not clever.
            duration = f"{min(max(gap_days + 3, 5), 60)} D"
            for day, bars in broker.historical_sessions(symbol, today,
                                                        duration, "5 mins"):
                if day is None or day <= last.date():
                    continue                       # already in the CSV
                sessions.append((day, bars))
                from_broker += 1

    history = FeatureHistory()
    for _, bars in sessions[-max(required, OR_PCTL_WINDOW + 20):]:
        history.append(session_stats(bars))       # percentages only (§4.4)

    n = len(history)
    if store is not None:
        store.event("info", "features",
                    f"{symbol}: {n} sessions "
                    f"({from_csv} csv + {from_broker} broker), "
                    f"atr5={history.atr5():.2f} thr80={history.thr80():.2f}")
    return Bootstrap(symbol, history, n, sessions[-1][0] if sessions else None,
                     from_csv, from_broker)


#: How far back the newest feature session may sit before the history is stale.
#: A normal Tuesday is 1 day; a Monday is 3; a Monday holiday makes Tuesday 4.
#: 5 clears every ordinary US market calendar gap and nothing more.
MAX_FEATURE_AGE_DAYS = 5


def _as_date(value):
    return value.date() if hasattr(value, "date") else value


def check(bootstraps: dict, on_event=None, today=None) -> bool:
    """Pre-flight: enough history to produce thr80, and recent enough to mean it.

    §2.2 stands a sleeve down when "historical data required for ATR5/thr80 is
    unavailable **or stale**", and §4 requires a pre-trade check that "the last
    daily bar is the prior session". Only the first half was implemented: a
    broker top-up that returned nothing left the engine computing ATR5 from
    whatever the CSV happened to end on, silently.

    That is not hypothetical. On 2026-08-03 IBKR error 162 killed both top-up
    requests and the engine carried on with features ending 2026-07-21 — thirteen
    days and one volatility regime out of date. It was after the close, so
    nothing came of it; during a session it would have gated and armed on stale
    inputs.

    Staleness is now fatal to the run rather than a log line. Refusing costs a
    trading day; trading a gate computed from the wrong fortnight does not
    announce itself at all.
    """
    ok = True

    def say(level, msg):
        if on_event:
            on_event(level, msg)

    for symbol, b in bootstraps.items():
        if not b.sufficient:
            ok = False
            say("critical", f"{symbol}: only {b.sessions} sessions, thr80 needs "
                            f"{OR_PCTL_MINOBS} — sleeve will stand down every day")
        if b.last_session is None:
            ok = False
            say("critical", f"{symbol}: no sessions at all")
            continue
        if today is None:
            continue                              # caller opted out of the check
        age = (_as_date(today) - _as_date(b.last_session)).days
        if age > MAX_FEATURE_AGE_DAYS:
            ok = False
            say("critical",
                f"{symbol}: newest feature session is {_as_date(b.last_session)}, "
                f"{age} days before {_as_date(today)} — ATR5 and thr80 would be "
                f"computed from stale history. §2.2 forbids trading on it. "
                f"Fix the broker top-up (IBKR 162 means a second session holds "
                f"the market-data connection) and re-run.")
    return ok
