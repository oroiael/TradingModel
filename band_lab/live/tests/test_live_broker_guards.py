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

from broker import IBBroker, NotLiveDataError, bar_time_et

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


def test_silence_is_not_taken_for_live():
    """ib_async defaults `marketDataType` to 1, so no callback reads as live.

    Unknown has to refuse, or the guard is decorative on exactly the path it
    exists to catch.
    """
    b = _broker(readonly=True, mdt=None)     # TWS never answers
    b._ib._ticker = _StubTicker()
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
