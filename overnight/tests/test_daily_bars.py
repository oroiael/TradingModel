"""The daily-bar request, and why it is not band_lab's.

This file exists because the first live pre-flight died here:

    FAILED: bar size '1 day' has no index grid; known: ['1 min', '5 mins']

band_lab's `historical_sessions` indexes every bar by minutes since 09:30 and
refuses a size it has no grid for. That refusal is CORRECT — it guards a real
defect where `startswith("5")` gave "15 mins" a 1-minute grid — so the fix was a
separate daily path, not a wider lookup table. These tests pin both halves: the
new path works, and the old guard still bites.
"""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import broker_ext
import features
import schedule
from broker_ext import AuctionBroker, DailyBar
from config import OvernightConfig
from constants import COVER_SYMBOL, PRIMARY_SYMBOL
from fake_broker import calm_then


class FakeIB:
    """Records every `reqHistoricalData` call and replays a scripted answer."""

    def __init__(self, *answers):
        self.calls: list[dict] = []
        self.answers = list(answers)

    def reqHistoricalData(self, contract, **kw):
        self.calls.append(dict(contract=contract, **kw))
        return self.answers.pop(0) if self.answers else []


class RawBar:
    """What ib_async hands back for a daily bar: `date` is a bare `date`.

    Verified in this repository, not recalled — `band_lab/live/broker.py:178`
    carries the comment "parseIBDatetime returns a bare date for a daily bar"
    and the branch that was added to handle it.
    """

    def __init__(self, date, o, c):
        self.date, self.open, self.high = date, o, max(o, c)
        self.low, self.close, self.volume = min(o, c), c, 1000


def make_broker(ib):
    b = AuctionBroker(host="x", port=7497, client_id=99, dry_run=True)
    b._require = lambda: ib
    b.contract = lambda symbol: f"contract:{symbol}"
    return b


RAW = [RawBar(dt.date(2026, 9, 9), 100.0, 101.0),
       RawBar(dt.date(2026, 9, 10), 101.0, 99.5),
       RawBar(dt.date(2026, 9, 11), 99.5, 102.25)]


# ================================================ the request IBKR actually gets

def test_daily_sessions_asks_for_daily_bars():
    ib = FakeIB(RAW)
    make_broker(ib).daily_sessions("SOXL", None, "4 Y")
    kw = ib.calls[0]
    assert kw["barSizeSetting"] == "1 day"
    assert kw["durationStr"] == "4 Y"


def test_it_asks_for_the_series_the_research_was_built_on():
    """TRADES, not ADJUSTED_LAST. The threshold is a percentile of this
    instrument's own RV history, so the wrong basis is a different strategy."""
    ib = FakeIB(RAW)
    make_broker(ib).daily_sessions("SOXL", None, "4 Y")
    kw = ib.calls[0]
    assert kw["whatToShow"] == "TRADES" == broker_ext.DAILY_WHAT_TO_SHOW
    assert kw["useRTH"] is True
    assert kw["formatDate"] == 1
    assert kw["keepUpToDate"] is False


def test_a_bare_date_from_ibkr_parses():
    """`formatDate=1` yields a bare `date` for a daily bar, which is not what
    the intraday path's timestamp handling expects."""
    got = make_broker(FakeIB(RAW)).daily_sessions("SOXL", None, "4 Y")
    assert [b.date for b in got] == [dt.date(2026, 9, 9), dt.date(2026, 9, 10),
                                     dt.date(2026, 9, 11)]
    assert got[-1].close == 102.25
    assert all(isinstance(b, DailyBar) for b in got)


def test_bars_come_back_oldest_first_whatever_order_ibkr_sent():
    got = make_broker(FakeIB(list(reversed(RAW)))).daily_sessions("X", None, "4 Y")
    assert [b.date for b in got] == sorted(b.date for b in got)


def test_an_empty_stamped_request_retries_open_ended():
    """Whether IBKR accepts an out-of-hours endDateTime is an OPEN QUESTION —
    a Sunday-evening pre-flight is exactly when it would bite."""
    ib = FakeIB([], RAW)
    end = dt.datetime(2026, 9, 13, 20, 31)
    got = make_broker(ib).daily_sessions("SOXL", end, "4 Y")
    assert len(ib.calls) == 2
    assert ib.calls[0]["endDateTime"] == "20260913 20:31:00 US/Eastern"
    assert ib.calls[1]["endDateTime"] == ""
    assert len(got) == 3


def test_a_populated_request_does_not_retry():
    ib = FakeIB(RAW, RAW)
    make_broker(ib).daily_sessions("SOXL", dt.datetime(2026, 9, 13, 20, 31), "4 Y")
    assert len(ib.calls) == 1


# ============================================= the guard we did NOT weaken

def test_bandlabs_intraday_guard_still_refuses_a_daily_bar_size():
    """If someone ever 'fixes' this by adding '1 day' to `_BAR_STEP_MINUTES`,
    every daily bar silently lands at index 0 and this test is the alarm."""
    import bandlab
    broker_mod = bandlab.load("broker")
    assert "1 day" not in broker_mod._BAR_STEP_MINUTES
    ib = FakeIB(RAW)
    b = make_broker(ib)
    with pytest.raises(broker_mod.BrokerError, match="no index grid"):
        b._dated_bars("SOXL", None, "4 Y", "1 day")


def test_the_schedule_uses_the_daily_path_not_the_intraday_one(tmp_path):
    """A broker with only band_lab's method must fail loudly, not fall back."""
    class OnlyIntraday:
        def historical_sessions(self, *a, **kw):
            raise AssertionError("daily bars must not go through this")

    cfg = OvernightConfig(db_path=str(tmp_path / "x.db"))
    with pytest.raises(AttributeError, match="daily_sessions"):
        schedule.daily_features(OnlyIntraday(), "SOXL", cfg,
                                dt.datetime(2026, 9, 14, 15, 45))


# ====================================== the basis check, which measures the rest

def write_csv(path, sessions, scale_before=None, factor=1.0):
    with open(path, "w", newline="") as fh:
        fh.write("Date,Open,High,Low,Close,Volume\n")
        for s in sessions:
            k = factor if (scale_before and s.date < scale_before) else 1.0
            fh.write(f"{s.date},{s.open*k},{s.close*k},{s.open*k},"
                     f"{s.close*k},100\n")


def test_matching_series_reports_a_tiny_mismatch(tmp_path):
    sessions = [features.Session(b.date, b.open, b.close) for b in calm_then(200)]
    ref = str(tmp_path / "ref.csv")
    write_csv(ref, sessions)
    worst = schedule.cross_check_basis("SOXL", sessions, ref)
    assert worst == pytest.approx(0.0, abs=1e-9)


def test_a_dividend_adjusted_series_is_caught(tmp_path):
    """ADJUSTED_LAST back-adjusts the OLD prices and leaves recent ones alone —
    which is precisely the shape this scales in."""
    sessions = [features.Session(b.date, b.open, b.close) for b in calm_then(200)]
    ref = str(tmp_path / "ref.csv")
    write_csv(ref, sessions, scale_before=sessions[-20].date, factor=0.97)
    worst = schedule.cross_check_basis("SOXL", sessions, ref)
    assert worst == pytest.approx(0.03 / 0.97, rel=1e-6)
    assert worst > 0.002, "must exceed the tolerance, or the check is decorative"


def test_a_missing_reference_is_not_an_error(tmp_path):
    """A stale or absent research file is not a reason to stop trading."""
    sessions = [features.Session(b.date, b.open, b.close) for b in calm_then(50)]
    assert schedule.cross_check_basis("SOXL", sessions, str(tmp_path / "no.csv")) is None


def test_non_overlapping_dates_report_unverified(tmp_path):
    sessions = [features.Session(b.date, b.open, b.close) for b in calm_then(50)]
    other = [features.Session(s.date + dt.timedelta(days=4000), s.open, s.close)
             for s in sessions]
    ref = str(tmp_path / "ref.csv")
    write_csv(ref, other)
    assert schedule.cross_check_basis("SOXL", sessions, ref) is None


def test_the_shipped_reference_files_exist_and_overlap():
    """The config points at real files; if one moves, say so here not at 15:45."""
    cfg = OvernightConfig()
    for symbol in (PRIMARY_SYMBOL, COVER_SYMBOL):
        path = cfg.reference_csv[symbol]
        assert os.path.exists(path), f"{symbol}: {path} is missing"
        assert features.load_sessions(path), f"{symbol}: {path} is empty"
