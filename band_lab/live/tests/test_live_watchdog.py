"""
Stage 7 — the watchdog (§6.2).

The acceptance test §10.12 asks for "watchdog kills a hung engine and flattens
independently". These drive that against `FakeIB`, plus the trigger §6.2 does
not name and which is the one that actually fired in the field: an engine that
is alive, heartbeating, and still holding a position after the flatten deadline.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from broker import FakeIB
from config import EngineConfig
from store import Store
from watchdog import Watchdog

NY = ZoneInfo("America/New_York")
MIDDAY = datetime(2026, 8, 7, 13, 0, tzinfo=NY)          # a Friday, mid-session
LATE = datetime(2026, 8, 7, 15, 59, tzinfo=NY)           # past the hard deadline
WEEKEND = datetime(2026, 8, 8, 13, 0, tzinfo=NY)         # Saturday


def _wd(tmp_path, heartbeat_age=None, positions=None, working=0):
    hb = tmp_path / "heartbeat.json"
    if heartbeat_age is not None:
        stamp = MIDDAY - timedelta(seconds=heartbeat_age)
        hb.write_text(json.dumps({"ts": stamp.isoformat(), "session": "20260807"}))
    cfg = EngineConfig(db_path=str(tmp_path / "w.db"),
                       heartbeat_file=str(hb))
    ib = FakeIB(symbols=cfg.symbols)
    ib.connect()
    for symbol, qty in (positions or {}).items():
        ib.positions[symbol] = qty
    for _ in range(working):
        ib._add("SOXS", "SELL", 100, "LMT", "x", limit_px=50.0)
    return Watchdog(cfg, broker=ib, store=Store(str(tmp_path / "w.db"))), ib


# ------------------------------------------------------------- stays asleep
def test_silent_when_the_engine_is_alive(tmp_path):
    wd, ib = _wd(tmp_path, heartbeat_age=10, positions={"SOXS": 1680})
    act, why = wd.verdict(MIDDAY)
    assert act is False and "alive" in why
    assert not ib.orders, "a healthy session must not be touched"


def test_silent_when_flat_even_with_no_heartbeat(tmp_path):
    """A stale heartbeat on a flat account is a finished engine, not a dead one.

    Firing `reqGlobalCancel` at that is pure risk with nothing to protect.
    """
    wd, ib = _wd(tmp_path, heartbeat_age=None, positions=None)
    act, why = wd.verdict(MIDDAY)
    assert act is False and "flat" in why


def test_silent_outside_rth(tmp_path):
    wd, ib = _wd(tmp_path, heartbeat_age=99_999, positions={"SOXS": 1680})
    act, why = wd.verdict(WEEKEND)
    assert act is False and "RTH" in why


def test_only_intervenes_once(tmp_path):
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})
    assert wd.verdict(MIDDAY)[0] is True
    wd.fired = True
    assert wd.verdict(MIDDAY)[0] is False, \
        "duelling orders with the engine is worse than either alone"


# ------------------------------------------------------------------- fires
def test_fires_when_the_engine_stops_heartbeating(tmp_path):
    """§6.2 — heartbeat stopped for more than two minutes during RTH."""
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})
    act, why = wd.verdict(MIDDAY)
    assert act is True and "heartbeat" in why


def test_fires_when_the_heartbeat_file_never_existed(tmp_path):
    wd, ib = _wd(tmp_path, heartbeat_age=None, positions={"SOXS": 1680})
    act, why = wd.verdict(MIDDAY)
    assert act is True and "no engine heartbeat" in why


def test_fires_past_the_deadline_even_with_a_healthy_engine(tmp_path):
    """The trigger §6.2 does not name, and the one that mattered in the field.

    2026-08-05, -06 and -07 all ended with the engine alive, heartbeating, and
    still holding a position after 15:55. A liveness check alone would have
    watched all three happen.
    """
    wd, ib = _wd(tmp_path, heartbeat_age=5, positions={"SOXS": 1680})
    act, why = wd.verdict(LATE)
    assert act is True and "forbids holding overnight" in why


def test_fires_on_working_orders_alone_past_the_deadline(tmp_path):
    """A resting buy limit into the close can still open a position."""
    wd, ib = _wd(tmp_path, heartbeat_age=5, positions=None, working=1)
    act, why = wd.verdict(LATE)
    assert act is True


# ------------------------------------------------------------- flattening
def test_intervention_cancels_everything_then_sells_to_flat(tmp_path):
    """§10.12 — the watchdog flattens independently of the engine."""
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680}, working=2)

    real_place = ib.place_market
    def place_and_fill(symbol, action, qty, order_ref):
        oid = real_place(symbol, action, qty, order_ref)
        ib.fill(oid, price=42.0)
        return oid
    ib.place_market = place_and_fill

    assert wd.intervene("test", settle=0) is True
    assert ib.global_cancels == 1, "everything is cancelled before anything is sold"
    assert abs(ib.position("SOXS")) < 1e-9
    assert wd.fired is True


def test_a_short_is_flattened_by_buying(tmp_path):
    """The 2026-08-05 failure mode left a short. Flat means flat either way."""
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXL": -1082})
    real_place = ib.place_market
    def place_and_fill(symbol, action, qty, order_ref):
        oid = real_place(symbol, action, qty, order_ref)
        ib.fill(oid, price=137.0)
        return oid
    ib.place_market = place_and_fill

    assert wd.intervene("short", settle=0) is True
    sent = [o for o in ib.orders.values() if o.order_type == "MKT"]
    assert sent and sent[0].action == "BUY", "cover a short, do not sell more"
    assert abs(ib.position("SOXL")) < 1e-9


def test_it_shouts_when_it_cannot_flatten(tmp_path):
    """Failing silently is the one outcome that must be impossible."""
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})
    assert wd.intervene("stuck", attempts=2, settle=0) is False   # nothing fills
    assert any(lvl == "critical" and "HUMAN INTERVENTION REQUIRED" in m
               for lvl, m in wd._said)


def test_the_watchdog_never_opens_a_position(tmp_path):
    """It has exactly one power. Flat is the only state it can create."""
    import inspect
    import watchdog
    src = inspect.getsource(watchdog)
    assert "place_limit" not in src, "the watchdog may not place a limit order"
    assert "place_stop" not in src, "nor a stop"
