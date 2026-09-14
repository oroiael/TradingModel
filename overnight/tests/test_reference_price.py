"""Sizing off a quote you only get to read once.

The multiple is defined against equity, so `floor(equity * multiple / price)`
puts the notional at exactly `equity * multiple` AT THE PRICE USED. A price that
is not the current market is therefore not a rounding error — it is the wrong
position size, sent into an auction that after 15:50 can be neither cancelled
nor reduced.

The case these are written around is real. At 21:29 on 2026-09-13 the pre-flight
read $111.56 for SOXL against Friday's $121.82 close and sized 1,277 shares
where 1,149 was the intent: 9% over, with nothing on screen saying the price was
8% from anything the strategy knew.
"""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import schedule
from config import OvernightConfig
from constants import COVER_SYMBOL, PRIMARY_SYMBOL
from fake_broker import FakeBroker, Q, calm_then, quotes_for
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
CLOSE = 121.82                       # SOXL's real 2026-09-11 close


def cfg(tmp, **kw):
    c = OvernightConfig(state_path=os.path.join(tmp, "state.json"),
                        ledger_path=os.path.join(tmp, "ledger.csv"),
                        db_path=os.path.join(tmp, "x.db"), **kw)
    c.validate()
    return c


def sig(close=CLOSE):
    return schedule.LegSignal(50.0, 80.0, dt.date(2026, 9, 11), close)


def price(quote, tmp, rehearsing=False, close=CLOSE, **kw):
    b = FakeBroker(quotes={PRIMARY_SYMBOL: quote})
    return schedule._reference_price(b, PRIMARY_SYMBOL, sig(close),
                                     cfg(tmp, **kw), rehearsing)


# ============================================== which field becomes the price

def test_a_tight_book_gives_the_midpoint(tmp_path):
    assert price(Q(121.80, 121.84, 121.83), str(tmp_path)) == pytest.approx(121.82)


def test_a_wide_book_falls_back_to_last(tmp_path):
    """Measured normal is 0.008% on SOXL. At 4% the midpoint is not a price."""
    got = price(Q(119.0, 124.0, 121.90), str(tmp_path))
    assert got == pytest.approx(121.90), "should be `last`, not the 121.50 mid"


def test_a_one_sided_book_falls_back_to_last(tmp_path):
    assert price(Q(0.0, 121.84, 121.79), str(tmp_path)) == pytest.approx(121.79)


def test_no_quote_at_all_refuses_a_real_run(tmp_path):
    with pytest.raises(schedule.Refused, match="no usable price"):
        price(Q(), str(tmp_path))


def test_no_quote_at_all_falls_back_to_the_close_when_rehearsing(tmp_path):
    assert price(Q(), str(tmp_path), rehearsing=True) == pytest.approx(CLOSE)


# ====================================== the band, and what it is measured from

def test_a_price_far_from_the_close_refuses_a_real_run(tmp_path):
    """Not a view about how far SOXL can move — a quote that is not a price."""
    with pytest.raises(schedule.Refused, match="beyond the 30% band"):
        price(Q(60.0, 60.02, 60.01), str(tmp_path))


def test_the_same_price_only_warns_in_a_rehearsal(tmp_path):
    """A rehearsal exists to SHOW you this, so it must not stop at it."""
    assert price(Q(60.0, 60.02, 60.01), str(tmp_path),
                 rehearsing=True) == pytest.approx(60.01)


def test_a_real_2365pct_move_is_allowed_through(tmp_path):
    """The worst 15:45 move on a traded night in six years, 2025-01-27.
    A band that refuses this refuses real trades."""
    px = CLOSE * (1 - 0.2365)
    assert price(Q(px - 0.01, px + 0.01, px), str(tmp_path)) == pytest.approx(px, rel=1e-4)


def test_the_band_cannot_be_configured_below_what_really_happens():
    with pytest.raises(ValueError, match="refuses real trades"):
        OvernightConfig(max_price_deviation=1.5).validate()


def test_the_sunday_case_is_inside_the_band_and_still_reported(tmp_path, capsys):
    """$111.56 vs $121.82 is 8.4% — a real move for SOXL, so it is NOT refused.
    The fix for it is that the log now says so, every single time."""
    got = price(Q(111.54, 111.58, 111.56), str(tmp_path))
    assert got == pytest.approx(111.56)
    out = capsys.readouterr().out
    assert "-8.42% from the 2026-09-11 close" in out
    assert "121.8200" in out


# ================================================ provenance reaches the log

def test_the_quote_is_always_described(tmp_path, capsys):
    price(Q(121.80, 121.84, 121.83), str(tmp_path))
    out = capsys.readouterr().out
    assert "SOXL quote:" in out and "spread" in out and "age" in out


def test_delayed_data_is_named_in_the_log(tmp_path, capsys):
    b = FakeBroker(quotes={PRIMARY_SYMBOL: Q(121.80, 121.84, 121.83)})
    b.market_data_type = 3
    schedule._reference_price(b, PRIMARY_SYMBOL, sig(), cfg(str(tmp_path)), False)
    assert "DELAYED" in capsys.readouterr().out


def test_a_broker_without_quote_detail_still_works(tmp_path):
    """band_lab's plain `quote()` must keep working — the adapter is optional."""
    class Plain:
        def quote(self, symbol):
            return Q(121.80, 121.84, 121.83)
    got = schedule._reference_price(Plain(), PRIMARY_SYMBOL, sig(),
                                    cfg(str(tmp_path)), False)
    assert got == pytest.approx(121.82)


# ========================================= and the whole job, end to end

def test_enter_refuses_rather_than_oversizing_on_a_bad_quote(tmp_path):
    """The failure this whole file is about: too LOW a price buys too MANY
    shares, and the MOC cannot be reduced after 15:50."""
    sessions = {PRIMARY_SYMBOL: calm_then(400), COVER_SYMBOL: calm_then(400, seed=5)}
    good = quotes_for(sessions)
    broken = dict(good)
    broken[PRIMARY_SYMBOL] = Q(1.00, 1.02, 1.01)          # a quote, not a price
    b = FakeBroker(sessions=sessions, quotes=broken)
    with pytest.raises(schedule.Refused, match="beyond the"):
        schedule.enter(b, cfg(str(tmp_path)),
                       asof=dt.datetime(2026, 9, 14, 15, 45, tzinfo=NY))
    assert b.placed == [], "a refusal must never leave an order behind"
