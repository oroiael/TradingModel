"""
Stage 7 — the watchdog (§6.2).

The acceptance test §10.12 asks for "watchdog kills a hung engine and flattens
independently". These drive that against `FakeIB`, plus the trigger §6.2 does
not name and which is the one that actually fired in the field: an engine that
is alive, heartbeating, and still holding a position after the flatten deadline.
"""

from __future__ import annotations

import json
from datetime import datetime, time as dtime, timedelta
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


def test_a_new_session_re_arms_the_watchdog(tmp_path):
    """Design rule 4 is one intervention per *session*, not per process.

    `run()` loops indefinitely across days. A watchdog that acted on Friday and
    never re-armed would watch the whole of the following week unable to act,
    and say nothing about it — the silent failure it exists to prevent, moved
    inside the watchdog itself.
    """
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})
    assert wd.verdict(MIDDAY)[0] is True

    wd.intervene("first", settle=0, now=MIDDAY)
    assert wd.fired_on == MIDDAY.date()
    assert wd.verdict(MIDDAY)[0] is False, "the rest of the day stays dormant"

    monday = MIDDAY + timedelta(days=3)          # 2026-08-10, still exposed
    assert wd.verdict(monday)[0] is True, "a new session re-arms it"
    assert any("re-arming" in m for _, m in wd._said)


def test_a_backwards_clock_does_not_re_arm(tmp_path):
    """An NTP correction must not hand it a second intervention in one day.

    Dormant is the safe direction of this error: the cost is a watchdog that
    waits, the cost of the other is duelling orders with a live engine.
    """
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})
    wd.intervene("first", settle=0, now=MIDDAY)
    assert wd.verdict(MIDDAY - timedelta(days=1))[0] is False


def test_intervention_never_stacks_duplicate_market_orders(tmp_path):
    """The defect `ensure_flat` was rewritten to remove, still live here.

    Nothing fills in this test, so every pass sees the same 1,680 long. The old
    loop sent a full-size market order each time: four passes against one long
    1,680 is a short 5,040. §11 prohibits an inverted position outright, and it
    is strictly worse than the failure to flatten it is trying to fix.
    """
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})

    assert wd.intervene("stuck", attempts=4, settle=0) is False
    mkt = [o for o in ib.orders.values() if o.order_type == "MKT"]
    assert len(mkt) == 1, f"one flatten for one position, not {len(mkt)}"
    assert mkt[0].qty == 1680
    assert any("already working" in m for _, m in wd._said)


def test_it_re_sends_once_the_previous_flatten_is_gone(tmp_path):
    """The guard must not wedge it — a dead flatten leaves shares exposed.

    Waiting on an order that is still working is right; waiting on one that TWS
    cancelled would leave the position open with nothing trying to close it,
    which is the failure the watchdog exists to prevent.
    """
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})

    def kill_working_then_wait(seconds):
        for o in ib.orders.values():
            if o.order_type == "MKT" and o.status == "Submitted":
                o.status = "Cancelled"          # TWS took it; nothing is working
    ib.wait = kill_working_then_wait

    assert wd.intervene("stuck", attempts=3, settle=1) is False
    mkt = [o for o in ib.orders.values() if o.order_type == "MKT"]
    assert len(mkt) == 3, "each pass must re-send once the last one died"


def test_the_watchdog_never_opens_a_position(tmp_path):
    """It has exactly one power. Flat is the only state it can create."""
    import inspect
    import watchdog
    src = inspect.getsource(watchdog)
    assert "place_limit" not in src, "the watchdog may not place a limit order"
    assert "place_stop" not in src, "nor a stop"


# ------------------------------------------------ arming is explicit (F8)
def test_armed_by_default_and_the_broker_agrees(tmp_path):
    """Exposure is real whether or not the *engine* is rehearsing.

    A position left by a previous session still has to be closed by 16:00, so
    the default is armed. What must never happen is discovering that from a
    fill.
    """
    cfg = EngineConfig(db_path=str(tmp_path / "w.db"))
    wd = Watchdog(cfg, store=Store(str(tmp_path / "w.db")))
    assert wd.armed is True
    assert wd.broker.dry_run is False


def test_no_transmit_really_sends_nothing(tmp_path):
    cfg = EngineConfig(db_path=str(tmp_path / "w.db"), watchdog_transmit=False)
    wd = Watchdog(cfg, store=Store(str(tmp_path / "w.db")))
    assert wd.armed is False
    assert wd.broker.dry_run is True, \
        "readonly is what stops IBBroker transmitting (§4.1)"


def test_a_rehearsal_does_not_cry_wolf(tmp_path):
    """`HUMAN INTERVENTION REQUIRED` has to keep meaning something.

    Nothing was sent because nothing was meant to be sent, so reporting a
    failure to flatten would train the operator to discount the one message
    that must never be discounted.
    """
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})
    wd.cfg.watchdog_transmit = False

    assert wd.intervene("rehearsal", attempts=2, settle=0) is False
    assert not any(lvl == "critical" and "HUMAN INTERVENTION" in m
                   for lvl, m in wd._said)
    assert any("rehearsal" in m for _, m in wd._said)


def test_it_says_so_when_the_engine_is_rehearsing_and_it_is_not(tmp_path):
    """The §4.1 shape again: a document promising nothing reaches the market.

    `--dry-run` is a flag on run.py, not a value in the shared config, so the
    only way this side can know is the heartbeat the engine writes.
    """
    hb = tmp_path / "heartbeat.json"
    hb.write_text(json.dumps({"ts": MIDDAY.isoformat(), "session": "20260807",
                              "transmit": False}))
    cfg = EngineConfig(db_path=str(tmp_path / "w.db"), heartbeat_file=str(hb))
    ib = FakeIB(symbols=cfg.symbols)
    ib.connect()
    wd = Watchdog(cfg, broker=ib, store=Store(str(tmp_path / "w.db")))

    wd.warn_if_the_engine_is_only_rehearsing()
    assert any(lvl == "warn" and "transmit OFF" in m for lvl, m in wd._said)

    n = len(wd._said)
    wd.warn_if_the_engine_is_only_rehearsing()
    assert len(wd._said) == n, "said once, not every 30 seconds"


def test_it_stays_quiet_when_there_is_nothing_to_warn_about(tmp_path):
    """A transmitting engine, and an older one that records no mode at all."""
    for payload in ({"ts": MIDDAY.isoformat(), "transmit": True},
                    {"ts": MIDDAY.isoformat()}):
        hb = tmp_path / "hb.json"
        hb.write_text(json.dumps(payload))
        cfg = EngineConfig(db_path=str(tmp_path / "w.db"), heartbeat_file=str(hb))
        ib = FakeIB(symbols=cfg.symbols)
        ib.connect()
        wd = Watchdog(cfg, broker=ib, store=Store(str(tmp_path / "w.db")))
        wd.warn_if_the_engine_is_only_rehearsing()
        assert not wd._said, f"nothing to say for {payload}"


def test_the_engine_records_its_mode_in_the_heartbeat(tmp_path):
    """The warning above is only possible if run.py actually writes it."""
    import inspect
    import run
    assert '"transmit"' in inspect.getsource(run.Runner.touch_heartbeat)


# ------------------------- the session is the exchange's, not a constant (F16)
def test_a_holiday_is_not_an_ordinary_tuesday(tmp_path):
    """The static 09:30-16:00 window treats a weekday holiday as a session.

    The engine's `session_hours` already answers this properly — it raises
    `MarketClosedError` — and the watchdog can ask the same question.
    """
    from broker import MarketClosedError

    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})
    def closed(symbol, day):
        raise MarketClosedError(f"{symbol}: no regular session")
    ib.session_hours = closed

    assert wd.in_session(MIDDAY) is False
    assert wd.verdict(MIDDAY)[0] is False


def test_a_half_day_pulls_the_deadline_in(tmp_path):
    """15:58 is two minutes before an ordinary close, and useless at 13:00.

    A half day is precisely when the engine is gated off and least likely to be
    watched, so a deadline that never arrives is the worst case for it.
    """
    from broker import SessionHours

    wd, ib = _wd(tmp_path, heartbeat_age=5, positions={"SOXS": 1680})
    o = MIDDAY.replace(hour=9, minute=30)
    ib.hours["SOXL"] = ib.hours["SOXS"] = SessionHours(
        o, o.replace(hour=13, minute=0), is_half_day=True)

    assert wd.hard_flat_at(MIDDAY) == dtime(12, 58)
    late = MIDDAY.replace(hour=12, minute=59)
    assert wd.verdict(late)[0] is True, "past the real deadline, still exposed"


def test_an_ordinary_day_keeps_the_configured_deadline(tmp_path):
    wd, ib = _wd(tmp_path, heartbeat_age=5, positions={"SOXS": 1680})
    assert wd.hard_flat_at(MIDDAY) == dtime(15, 58)


def test_the_broker_falling_over_leaves_the_watchdog_awake(tmp_path):
    """Blind is worse than approximate: fall back to the static window."""
    wd, ib = _wd(tmp_path, heartbeat_age=600, positions={"SOXS": 1680})
    def boom(symbol, day):
        raise RuntimeError("TWS busy")
    ib.session_hours = boom

    assert wd.in_session(MIDDAY) is True
    assert wd.verdict(MIDDAY)[0] is True
