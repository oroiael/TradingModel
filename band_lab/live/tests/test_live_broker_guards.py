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
    def __init__(self, mdt_after_probe=1, quote=None):
        self.marketDataType = 1
        self._answer = mdt_after_probe
        # Opt-in: the delayed-data tests rely on a ticker with no quote in it,
        # because `assert_live_data` breaks out of its probe as soon as one
        # appears and would then never read the marketDataType they are about.
        if quote is not None:
            self.bid, self.ask, self.last = quote
            self.bidSize = self.askSize = 100.0


class _StubIB:
    """Just enough of ib_async.IB to reach the guard under test."""

    def __init__(self, bars=(), mdt=1, quote=None):
        self.mkt_data_requests = []
        self._quote = quote
        self._connected = True
        self.placed = []
        self.cancelled = []
        self.global_cancels = 0
        self._bars = list(bars)
        self._mdt = mdt
        self.market_data_type_requested = None
        self.mkt_data_cancelled = []

    def isConnected(self):
        return self._connected

    def disconnect(self):
        self._connected = False

    def reqMarketDataType(self, n):
        self.market_data_type_requested = n

    def reqMktData(self, contract, *a, **kw):
        self.mkt_data_requests.append(contract)
        self._ticker = _StubTicker(quote=self._quote)
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


def _broker(readonly, bars=(), mdt=1, quote=None):
    b = IBBroker(readonly=readonly)
    b._ib = _StubIB(bars, mdt, quote)
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


# ------------------------------- IBKR errors are recorded, and classified (F26)
def test_the_warning_set_matches_ib_async():
    """Transcribed, then asserted — the same discipline as DONE_STATES.

    The split decides whether an order is still working. A code in the set
    leaves it alive with `ValidationError`; anything else makes `wrapper.error`
    set the trade `Cancelled` while IBKR may still be filling it.
    """
    import inspect

    import ib_async.wrapper as W
    from broker import IB_WARNING_CODES, is_warning

    src = " ".join(inspect.getsource(W.Wrapper.error).split())
    listed = "frozenset({" + ", ".join(str(c) for c in sorted(IB_WARNING_CODES)) + "})"
    assert listed in src, "ib_async's warning set has moved; retranscribe it"
    assert "2100 <= errorCode < 2200" in src

    assert is_warning(2102), "modify-before-processed leaves the order working"
    assert not is_warning(103), "duplicate order id does not"
    assert not is_warning(202), "202 is an order-delete error, deliberately"


def _broker_recording():
    """The stub broker from above, with its event stream captured."""
    said = []
    b = _broker(readonly=True, mdt=1)
    b._on_event = lambda lvl, msg: said.append((lvl, msg))
    return b, said


def test_every_ibkr_error_is_recorded_not_just_market_data():
    """On 2026-08-10 error 103 arrived and this engine recorded nothing.

    `_on_ib_error` returned early for anything outside NO_LIVE_DATA_ERRORS, so
    the one code that mattered was dropped, `ib_async` marked the trade
    Cancelled, and IBKR went on to fill 1,703 shares. The session had to be
    reconstructed from TWS's own log afterwards.
    """
    b, said = _broker_recording()
    b._on_ib_error(7, 103, "Duplicate order ID", SimpleNamespace(symbol="SOXS"))

    assert said, "an order-rejecting error must reach the log"
    level, msg = said[-1]
    assert level == "error"
    assert "103" in msg and "SOXS" in msg
    assert "Cancelled" in msg, "say what ib_async has just done to the trade"


def test_a_warning_code_is_not_reported_as_a_dead_order():
    """2102 leaves the order working, and the log must not imply otherwise."""
    b, said = _broker_recording()
    b._on_ib_error(7, 2102, "Unable to modify this order as it is still being "
                            "processed", SimpleNamespace(symbol="SOXL"))
    level, msg = said[-1]
    assert level == "warn" and "Cancelled" not in msg


def test_connection_chatter_is_not_logged():
    """TWS repeats "farm connection is OK" constantly; it is not a condition."""
    b, said = _broker_recording()
    for code in (2104, 2106, 2158):
        b._on_ib_error(-1, code, "Market data farm connection is OK")
    assert not said


def test_a_market_data_error_still_stands_the_sleeve_down():
    """The pre-existing behaviour must survive the widened logging."""
    b, said = _broker_recording()
    b._on_ib_error(9, 10089, "API data requires subscription",
                   SimpleNamespace(symbol="SOXL"))
    assert "SOXL" in b._no_live_data
    with pytest.raises(NotLiveDataError):
        b.assert_live_data("SOXL")


# ------------------------------ one market-data line per symbol, not per read
def test_repeated_quotes_use_one_subscription():
    """`reqMktData` takes a fresh reqId every call and orphans the last one.

    `wrapper.startTicker` reuses the `Ticker` object but overwrites
    `ticker2ReqId`, so the data keeps arriving and nothing looks wrong while
    TWS accumulates subscriptions `cancelMktData` can no longer reach. Against
    a concurrent-line limit of about 100, and a `_record_fill` that reads a
    quote on every execution, that is a session-length leak.
    """
    b = _broker(readonly=True, quote=(10.0, 10.02, 10.01))
    for _ in range(12):
        q = b.quote("SOXL")
    assert q.bid == pytest.approx(10.0) and q.ask == pytest.approx(10.02)
    assert len(b._ib.mkt_data_requests) == 1, \
        f"12 reads opened {len(b._ib.mkt_data_requests)} subscriptions"


def test_two_symbols_get_one_subscription_each():
    b = _broker(readonly=True, quote=(10.0, 10.02, 10.01))
    for _ in range(4):
        b.quote("SOXL")
        b.quote("SOXS")
    assert len(b._ib.mkt_data_requests) == 2


def test_disconnect_releases_the_subscriptions():
    b = _broker(readonly=True, quote=(10.0, 10.02, 10.01))
    b.quote("SOXL")
    assert b._tickers
    b.disconnect()
    assert b._ib.mkt_data_cancelled, "leaving them for TWS to reap is not tidy"
    assert not b._tickers


def test_the_live_data_probe_does_not_leave_a_dead_ticker_behind():
    """`cancelMktData` is looked up by contract, so it cancels ours too.

    Without dropping the cache here, `quote` would go on reading a `Ticker`
    that TWS has stopped updating — reporting a frozen book as a live one,
    which is worse than no quote at all because it looks fine.
    """
    b = _broker(readonly=True, mdt=1, quote=(10.0, 10.02, 10.01))
    b.quote("SOXL")
    assert "SOXL" in b._tickers

    b.assert_live_data("SOXL")               # opens a probe, then cancels it
    assert "SOXL" not in b._tickers, "the probe cancelled what we were holding"

    before = len(b._ib.mkt_data_requests)
    b.quote("SOXL")
    assert len(b._ib.mkt_data_requests) == before + 1, "so it re-subscribes"


# ------------------- the double must model the states the broker reports (F10)
@pytest.mark.parametrize("status", sorted(
    {"PendingSubmit", "ApiPending", "PreSubmitted", "Submitted",
     "ValidationError", "ApiUpdate", "PendingCancel"}))
def test_fake_modifies_every_state_the_real_broker_would(status):
    """`IBBroker.modify_limit` scans `openTrades()` and does not look further.

    `IB.placeOrder`-as-modify asserts only that the status is not a DoneState,
    so all seven of these are modified without complaint against a real TWS.
    `FakeIB` accepted two of them, which left the engine's behaviour against
    the other five — `PendingCancel` above all — untestable.
    """
    from broker import BrokerError

    ib = FakeIB()
    ib.connect()
    oid = ib.place_limit("SOXL", "BUY", 100, 99.0, "20260803-SOXL-E-1")
    ib.orders[oid].status = status

    ib.modify_limit(oid, 99.5, 100)              # must not raise
    assert ib.orders[oid].limit_px == pytest.approx(99.5)


@pytest.mark.parametrize("status", sorted({"Filled", "Cancelled",
                                           "ApiCancelled", "Inactive"}))
def test_fake_refuses_to_modify_a_done_order(status):
    from broker import BrokerError

    ib = FakeIB()
    ib.connect()
    oid = ib.place_limit("SOXL", "BUY", 100, 99.0, "20260803-SOXL-E-1")
    ib.orders[oid].status = status
    with pytest.raises(BrokerError):
        ib.modify_limit(oid, 99.5, 100)


def test_an_unknown_id_raises_the_same_error_as_the_real_broker():
    """It raised `KeyError`, so `_modify_entry`'s `except BrokerError` — the
    branch that leaves the resting order alone — was never exercised."""
    from broker import BrokerError

    ib = FakeIB()
    ib.connect()
    with pytest.raises(BrokerError):
        ib.modify_limit(4242, 99.5, 100)


def test_a_ghost_cannot_be_modified_or_cancelled():
    """`openTrades()` does not return it, so neither path can reach it."""
    from broker import BrokerError

    ib = FakeIB()
    ib.connect()
    oid = ib.place_limit("SOXL", "BUY", 100, 99.0, "20260803-SOXL-E-1")
    ib.hide(oid)

    with pytest.raises(BrokerError):
        ib.modify_limit(oid, 99.5, 100)
    ib.cancel(oid)
    assert ib.orders[oid].status == "Submitted", "a cancel cannot reach it either"


def test_oca_cancels_a_sibling_in_any_working_state():
    """`ocaType=1` is CANCEL_WITH_BLOCK — it does not poll for two states.

    The sweep listed `Submitted`/`PreSubmitted`, so a stop still sitting in
    `PendingSubmit` when its target filled stayed working in the double while a
    real broker would have taken it.
    """
    ib = FakeIB()
    ib.connect()
    tgt = ib.place_limit("SOXL", "SELL", 100, 101.0, "20260803-SOXL-T-2",
                         oca_group="g1")
    stp = ib.place_stop("SOXL", "SELL", 100, 95.0, "20260803-SOXL-S-3",
                        oca_group="g1")
    ib.orders[stp].status = "PendingSubmit"      # not yet acknowledged

    ib.fill(tgt, price=101.0)
    assert ib.orders[stp].status == "Cancelled"


def test_no_module_hand_writes_a_status_list():
    """The rule the skill states, enforced rather than remembered.

    "Use `broker.is_working(status)`. Never hand-write a status list — that is
    the exact mistake, and it recurred inside a test double written to catch
    it." It then recurred a third time, in two places. A single comparison
    against one named state is fine and deliberate; a *collection* of them is
    someone re-deriving `is_working` by hand.
    """
    import ast
    import os

    from broker import ACTIVE_STATES, DONE_STATES

    known = set(ACTIVE_STATES) | set(DONE_STATES) | {"PendingCancel"}
    live = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    for name in ("broker.py", "orders.py", "engine.py", "watchdog.py"):
        tree = ast.parse(open(os.path.join(live, name)).read(), filename=name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for cmp_node in node.comparators:
                if not isinstance(cmp_node, (ast.Tuple, ast.List, ast.Set)):
                    continue
                names = {e.value for e in cmp_node.elts
                         if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                if len(names) >= 2 and names <= known:
                    offenders.append(f"{name}:{node.lineno} {sorted(names)}")

    assert not offenders, (
        "these re-derive `is_working` by hand and will drift from "
        f"`openTrades()`: {offenders}")
