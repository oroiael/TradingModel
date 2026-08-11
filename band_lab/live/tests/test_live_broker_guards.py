"""
Two adapter guarantees that no other test could have caught, because every
other test runs against `FakeIB` and these are properties of `IBBroker`.

Both were found by QA review before the first paper session, and both would
have failed silently — the first by placing real orders during what the
runbook calls a dry run, the second by trading yesterday's bars as today's.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from broker import FakeIB, IBBroker, NotLiveDataError, bar_time_et

NY = ZoneInfo("America/New_York")


# ------------------------------------------------------- bar timestamps -> ET
@pytest.mark.parametrize("raw", [
    datetime(2026, 8, 3, 9, 30),                                    # naive
    datetime(2026, 8, 3, 9, 30, tzinfo=NY),                         # aware, ET
    datetime(2026, 8, 3, 13, 30, tzinfo=timezone.utc),              # aware, UTC
    datetime(2026, 8, 3, 15, 30, tzinfo=ZoneInfo("Europe/Amsterdam")),
    "20260803  09:30:00",                                           # string form
])
def test_every_ibkr_timestamp_form_lands_on_bar_zero(raw):
    """`Bar.idx` is minutes since 09:30 ET, so the zone is load-bearing.

    `ib_async.util.parseIBDatetime` returns any of these depending on the TWS
    version and its configured timezone. Read naively, the UTC form puts the
    09:30 bar at index 48 and the session decides nothing all day, silently.
    """
    et = bar_time_et(raw)
    assert (et.hour * 60 + et.minute - 570) // 5 == 0
    assert et.tzinfo is None, "compared against naive CSV timestamps downstream"


class _StubTicker:
    def __init__(self, mdt_after_probe=1):
        self.marketDataType = 1
        self._answer = mdt_after_probe


class _StubIB:
    """Just enough of ib_async.IB to reach the guard under test."""

    def __init__(self, bars=(), mdt=1):
        self.placed = []
        self.cancelled = []
        self.global_cancels = 0
        self._bars = list(bars)
        self._mdt = mdt
        self.market_data_type_requested = None
        self.mkt_data_cancelled = []

    def isConnected(self):
        return True

    def reqMarketDataType(self, n):
        self.market_data_type_requested = n

    def reqMktData(self, contract, *a, **kw):
        self._ticker = _StubTicker()
        return self._ticker

    def cancelMktData(self, contract):
        self.mkt_data_cancelled.append(contract)

    def sleep(self, _s):
        # Stand in for TWS answering the marketDataType callback.
        if self._mdt is not None:
            self._ticker.marketDataType = self._mdt

    def placeOrder(self, contract, order):
        self.placed.append(order)
        return SimpleNamespace(order=SimpleNamespace(orderId=99))

    def openTrades(self):
        return []

    def cancelOrder(self, order):
        self.cancelled.append(order)

    def reqGlobalCancel(self):
        self.global_cancels += 1

    def reqHistoricalData(self, *a, **kw):
        return self._bars


def _broker(readonly, bars=(), mdt=1):
    b = IBBroker(readonly=readonly)
    b._ib = _StubIB(bars, mdt)
    b._contracts["SOXL"] = object()          # skip qualifyContracts
    b._contracts["SOXS"] = object()
    return b


# ------------------------------------------------------- delayed data refusal
def test_live_data_assertion_passes_on_live():
    b = _broker(readonly=True, mdt=1)
    b.assert_live_data("SOXL")               # must not raise
    assert b._ib.market_data_type_requested == 1
    assert b._ib.mkt_data_cancelled, "the probe subscription is released again"


@pytest.mark.parametrize("mdt", [2, 3, 4])
def test_live_data_assertion_refuses_a_downgrade(mdt):
    """3 = delayed. Arming a limit off 15-minute-old prices is the failure."""
    b = _broker(readonly=True, mdt=mdt)
    with pytest.raises(NotLiveDataError):
        b.assert_live_data("SOXL")


def test_live_data_assertion_refuses_on_a_subscription_error():
    """The signal that actually fired in the field, 2026-08-03.

    TWS emitted 10089 ("requires additional subscription... Delayed market data
    is available") four times while the engine armed regardless, because the
    old guard read an attribute nothing ever set.
    """
    b = _broker(readonly=True, mdt=1)
    contract = SimpleNamespace(symbol="SOXL")
    b._on_ib_error(10, 10089, "Requested market data requires additional "
                              "subscription for API.", contract)
    with pytest.raises(NotLiveDataError):
        b.assert_live_data("SOXL")


def test_a_subscription_error_on_one_sleeve_does_not_condemn_the_other():
    """Entitlements are per contract."""
    b = _broker(readonly=True, mdt=1)
    b._on_ib_error(10, 10089, "no subscription", SimpleNamespace(symbol="SOXL"))
    with pytest.raises(NotLiveDataError):
        b.assert_live_data("SOXL")
    b.assert_live_data("SOXS")               # must not raise


def test_silence_proceeds_with_a_warning_rather_than_refusing():
    """Measured 2026-08-06: TWS often sends no `marketDataType` at all.

    The guard first shipped refusing on silence, on "unknown should fail safe".
    That stood a healthy sleeve down at 11:05 on a confirmed-good subscription
    and cost the session — silence is the ordinary case, so refusing on it fires
    mostly on good days. Refusal is now reserved for positive evidence, and the
    error-code path below is what carries §4.
    """
    warned = []
    b = _broker(readonly=True, mdt=None)     # TWS never answers
    b._ib._ticker = _StubTicker()
    b._on_event = lambda level, msg: warned.append((level, msg))
    b.assert_live_data("SOXL")               # must NOT raise
    assert any(l == "warn" for l, _ in warned), "but it must say so, loudly"


def test_positive_evidence_still_refuses_after_the_loosening():
    """The loosening must not have hollowed the guard out."""
    b = _broker(readonly=True, mdt=3)        # TWS says delayed
    with pytest.raises(NotLiveDataError):
        b.assert_live_data("SOXL")

    b = _broker(readonly=True, mdt=None)     # silent, but an error arrived
    b._ib._ticker = _StubTicker()
    b._on_ib_error(9, 10089, "no subscription", SimpleNamespace(symbol="SOXL"))
    with pytest.raises(NotLiveDataError):
        b.assert_live_data("SOXL")


def test_unrelated_errors_are_ignored():
    """162 is the session/IP conflict — a different fault, not a data downgrade."""
    b = _broker(readonly=True, mdt=1)
    b._on_ib_error(21, 162, "Trading TWS session is connected from a different "
                            "IP address", SimpleNamespace(symbol="SOXL"))
    b.assert_live_data("SOXL")               # must not raise


# ------------------------------------------------------- dry run == no orders
def test_readonly_broker_transmits_nothing():
    """`--dry-run` must reach the market with nothing.

    ib_async's own `readonly` flag only skips two startup requests; it does not
    stop `placeOrder`. Without this guard, Stage 4's acceptance run places live
    paper orders — the opposite of what it is for.
    """
    b = _broker(readonly=True)
    ids = [
        b.place_limit("SOXL", "BUY", 100, 50.0, "ref-entry"),
        b.place_stop("SOXL", "SELL", 100, 48.0, "ref-stop"),
        b.place_market("SOXL", "SELL", 100, "ref-flat"),
    ]
    assert b._ib.placed == [], "a dry run must not send an order"
    assert all(i < 0 for i in ids), "synthetic ids are negative and unmistakable"
    assert len(set(ids)) == 3, "each dry order still gets a distinct id"


def test_readonly_broker_swallows_modify_and_cancel():
    """The ratchet modifies and the 15:55 cancel run on the same dry ids."""
    b = _broker(readonly=True)
    oid = b.place_limit("SOXL", "BUY", 100, 50.0, "ref-entry")
    b.modify_limit(oid, 50.5, 100)          # must not raise, must not send
    b.cancel(oid)
    b.cancel_all()
    assert b._ib.placed == []
    assert b._ib.cancelled == []
    assert b._ib.global_cancels == 0


def test_transmitting_broker_still_places_orders():
    """The guard is on `readonly` only — the real run is unchanged."""
    b = _broker(readonly=False)
    assert b.place_limit("SOXL", "BUY", 100, 50.0, "ref-entry") == 99
    assert len(b._ib.placed) == 1
    o = b._ib.placed[0]
    assert (o.orderType, o.lmtPrice, o.tif, o.outsideRth) == ("LMT", 50.0, "DAY", False)


def test_a_negative_order_id_is_never_sent_even_when_transmitting():
    """Belt and braces: a dry id leaking into a live session cancels nothing."""
    b = _broker(readonly=False)
    b.modify_limit(-1, 50.0, 100)           # must not raise
    b.cancel(-1)
    assert b._ib.placed == [] and b._ib.cancelled == []


# ------------------------------------------------- one session's bars, not two
def _raw(day: str, hhmm: str):
    return SimpleNamespace(date=datetime.strptime(f"{day} {hhmm}", "%Y%m%d %H%M"),
                           open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)


def test_historical_bars_returns_only_the_requested_session():
    """`Bar.idx` is a clock offset with no date; two sessions collapse into one.

    A window that reaches back into the prior session would deliver its
    11:00-16:00 bars as *today's* afternoon after the feed sorts by idx.
    """
    bars = [_raw("20260731", "1400"), _raw("20260731", "1500"),
            _raw("20260803", "0930"), _raw("20260803", "0935")]
    b = _broker(readonly=True, bars=bars)
    out = b.historical_bars("SOXL", datetime(2026, 8, 3, 9, 40, tzinfo=NY),
                            "1 D", "5 mins")
    assert [x.idx for x in out] == [0, 1], "only 2026-08-03's two bars"


def test_historical_bars_before_the_open_is_empty():
    """06:00 pre-open: the prior session's bars are not today's."""
    b = _broker(readonly=True, bars=[_raw("20260731", "1400")])
    out = b.historical_bars("SOXL", datetime(2026, 8, 3, 6, 0, tzinfo=NY),
                            "1 D", "5 mins")
    assert out == [], "no session yet means no bars, not yesterday's"


def test_historical_sessions_still_spans_days():
    """The feature bootstrap needs the multi-day view and keeps it."""
    bars = [_raw("20260731", "0930"), _raw("20260803", "0930")]
    b = _broker(readonly=True, bars=bars)
    days = b.historical_sessions("SOXL", datetime(2026, 8, 3, 6, 0, tzinfo=NY),
                                 "5 D", "5 mins")
    assert [d for d, _ in days] == [date(2026, 7, 31), date(2026, 8, 3)]


# ------------------- the double must model the states the broker reports
def test_fake_and_real_agree_on_what_counts_as_working():
    """The divergence that made a green suite meaningless.

    `IBBroker.working_orders` reports whatever `IB.openTrades()` returns, which
    `ib_async` defines as every trade whose status is not a `DoneState` —
    `PendingCancel` included. `FakeIB` filtered to `Submitted`/`PreSubmitted`,
    so the state that carried 524 shares overnight on 2026-08-10 could not be
    represented in a test at all.
    """
    from broker import ACTIVE_STATES, DONE_STATES, is_working

    # Transcribed from the installed ib_async, and asserted against it so a
    # package upgrade that moves a state cannot pass silently.
    from ib_async.order import OrderStatus
    assert DONE_STATES == set(OrderStatus.DoneStates)
    assert ACTIVE_STATES == set(OrderStatus.ActiveStates)

    # PendingCancel is in neither set, and is therefore still working.
    assert OrderStatus.PendingCancel not in DONE_STATES
    assert OrderStatus.PendingCancel not in ACTIVE_STATES
    assert is_working(OrderStatus.PendingCancel)


def test_fake_reports_a_pending_cancel_as_working():
    ib = FakeIB()
    ib.connect()
    ib.stall_cancels = True
    oid = ib.place_limit("SOXL", "BUY", 100, 99.0, "20260803-SOXL-E-1")
    assert [w.order_id for w in ib.working_orders("SOXL")] == [oid]

    ib.cancel(oid)
    still = ib.working_orders("SOXL")
    assert [w.order_id for w in still] == [oid], \
        "a cancel TWS has not confirmed still holds the shares"
    assert still[0].status == "PendingCancel"

    assert ib.confirm_cancels("SOXL") == 1
    assert ib.working_orders("SOXL") == []


def test_a_confirmed_cancel_is_the_default():
    """The ordinary case stays one step, so the happy path stays fast."""
    ib = FakeIB()
    ib.connect()
    oid = ib.place_limit("SOXL", "BUY", 100, 99.0, "20260803-SOXL-E-1")
    ib.cancel(oid)
    assert ib.working_orders("SOXL") == []


def test_global_cancel_clears_a_stalled_cancel():
    """§6.7's escape hatch, against the state it exists for.

    NOT verified against IBKR: whether a real `reqGlobalCancel` frees an OCA leg
    stuck in PendingCancel is the open question this models optimistically.
    """
    ib = FakeIB()
    ib.connect()
    ib.stall_cancels = True
    oid = ib.place_limit("SOXL", "SELL", 100, 99.0, "20260803-SOXL-T-1")
    ib.cancel(oid)
    assert ib.working_orders("SOXL")
    ib.cancel_all()
    assert ib.working_orders("SOXL") == []


# ------------------------------------------------ waiting without going deaf
def test_ibbroker_wait_runs_the_event_loop():
    """`wait` must pump ib_async's loop, or every poll reads frozen state.

    `ib_async` is single-threaded asyncio with no background reader, and
    `positions()`, `openTrades()`, `fills()` and `accountValues()` are plain
    reads of dictionaries the loop fills in. `IB.sleep` runs the loop;
    `time.sleep` stops it. Three loops depend on the difference — `ensure_flat`,
    `_clear_working` and `watchdog.check` — and under `time.sleep` none of them
    can observe the change they are waiting for.
    """
    slept = []
    broker = IBBroker()
    broker._ib = SimpleNamespace(sleep=slept.append)

    broker.wait(0.25)

    assert slept == [0.25], "wait must delegate to IB.sleep, not time.sleep"


def test_wait_works_while_disconnected():
    """`run_session` sleeps between polls whether or not the reconnect took.

    Routing this through `_require` would raise exactly when the engine is
    already struggling, turning a recoverable outage into a hot loop.
    """
    broker = IBBroker()
    assert broker._ib is None
    broker.wait(0.0)                     # must not raise


def test_a_failing_ib_sleep_still_waits():
    """A pause is never allowed to be what fails a flatten."""
    broker = IBBroker()

    def boom(_seconds):
        raise RuntimeError("event loop is already running")

    broker._ib = SimpleNamespace(sleep=boom)
    broker.wait(0.0)                     # falls back, does not propagate


def test_no_trading_module_sleeps_deaf():
    """The regression guard for the whole class of defect.

    Parsed rather than grepped, so a mention of `time.sleep` in a comment or a
    docstring — of which there are now several, deliberately — cannot fail this,
    and a real call cannot hide behind one.

    `broker.py` is excluded because it *defines* the fallback: `Broker.wait` is
    `time.sleep` (right for `FakeIB`, which has no loop to pump) and
    `IBBroker.wait` falls back to it when there is no connection.
    """
    import ast
    import os

    live = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    for name in ("orders.py", "run.py", "watchdog.py", "engine.py", "feed.py"):
        tree = ast.parse(open(os.path.join(live, name)).read(), filename=name)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "sleep"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "time"):
                offenders.append(f"{name}:{node.lineno}")

    assert not offenders, (
        "these block ib_async's event loop, so every broker read taken "
        f"afterwards is stale: {offenders}. Use `self.broker.wait(...)`.")
