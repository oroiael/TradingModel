"""The out-of-hours pre-flight, and the two data-path invariants it exposed.

`--rehearse-now` exists so the whole signal path — connect, fetch, RV, cut,
decide, size — can be run at any hour of the day against the real broker before
it matters. Everything here is about making that safe and making it honest:

  * safe: it is allowed ONLY when nothing can be sent, checked twice.
  * honest: the numbers it prints must be the numbers tomorrow's 15:45 run
    computes, or the rehearsal is theatre. The last two sections pin that.
"""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import features
import schedule
import state as state_mod
from config import OvernightConfig
from constants import COVER_SYMBOL, PRIMARY_SYMBOL
from fake_broker import FakeBroker, Q, calm_then, quotes_for
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def cfg(tmp, **kw):
    c = OvernightConfig(
        state_path=os.path.join(tmp, "state.json"),
        ledger_path=os.path.join(tmp, "ledger.csv"),
        db_path=os.path.join(tmp, "x.db"), **kw)
    c.validate()
    return c


def broker(**kw):
    kw.setdefault("sessions", {PRIMARY_SYMBOL: calm_then(400),
                               COVER_SYMBOL: calm_then(400, seed=5)})
    kw.setdefault("quotes", quotes_for(kw["sessions"]))
    kw.setdefault("transmit", False)
    return FakeBroker(**kw)


def at(h, m, s=0, day=(2026, 9, 14)):
    return dt.datetime(*day, h, m, s, tzinfo=NY)


# ===================================== the bypass may never reach a live order

def test_config_refuses_rehearse_now_with_transmit():
    c = OvernightConfig(rehearse_now=True, transmit=True)
    with pytest.raises(ValueError, match="mutually exclusive"):
        c.validate()


def test_schedule_refuses_the_combination_even_if_validate_was_skipped(tmp_path):
    """The second lock. `validate()` is a call someone can forget to make."""
    c = cfg(str(tmp_path))
    c.rehearse_now = True
    c.transmit = True                      # bypassing validate() deliberately
    b = broker(transmit=True)
    with pytest.raises(schedule.Refused, match="transmit is on"):
        schedule.enter(b, c, asof=at(20, 10))
    assert b.placed == []


def test_cli_refuses_the_combination():
    import run
    with pytest.raises(SystemExit):
        run.main(["--job", "enter", "--rehearse-now", "--transmit"])


def test_the_1550_guard_is_untouched_without_the_flag(tmp_path):
    """The behaviour that protects the account must not have moved."""
    b = broker()
    with pytest.raises(schedule.Refused, match="deadline"):
        schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 51))
    assert b.placed == []


# ============================================== the pre-flight actually works

def test_enter_runs_at_2010_when_rehearsing(tmp_path):
    """20:10 ET — the hour the operator actually has to test in."""
    b = broker()
    c = cfg(str(tmp_path), rehearse_now=True)
    r = schedule.enter(b, c, asof=at(20, 10))
    assert r.acted, "the pre-flight must reach the sizing step"
    assert b.placed[0]["kind"] == "MOC"
    i = state_mod.read_intent(c.state_path)
    assert i.transmitted is False, "a rehearsal must never claim a live order"


def test_exit_runs_out_of_hours_when_rehearsing(tmp_path):
    b = broker(positions={PRIMARY_SYMBOL: 500})
    c = cfg(str(tmp_path), rehearse_now=True)
    r = schedule.exit_(b, c, asof=at(20, 10))
    assert r.acted and b.placed[0]["kind"] == "MOO"


def test_rehearsal_sizes_off_the_close_when_there_is_no_quote(tmp_path):
    """Out of hours `quote()` returns zeros — refusing there would stop the
    pre-flight at the one step it exists to check."""
    sessions = {PRIMARY_SYMBOL: calm_then(400), COVER_SYMBOL: calm_then(400, seed=5)}
    b = broker(sessions=sessions, quotes={PRIMARY_SYMBOL: Q(), COVER_SYMBOL: Q()})
    c = cfg(str(tmp_path), rehearse_now=True)
    r = schedule.enter(b, c, asof=at(20, 10))
    assert r.acted
    leg = b.placed[0]["symbol"]
    close = sessions[leg][-1].close
    mult = c.primary_multiple if leg == PRIMARY_SYMBOL else c.cover_multiple
    assert b.placed[0]["qty"] == int(140_000 * mult // close)


def test_a_REAL_run_still_refuses_without_a_quote(tmp_path):
    """The fallback is for rehearsals only. At 15:45 a missing quote is a fault."""
    b = broker(quotes={PRIMARY_SYMBOL: Q(), COVER_SYMBOL: Q()})
    with pytest.raises(schedule.Refused, match="no usable price"):
        schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 45))
    assert b.placed == []


# ================================== invariant 1: day D's close is never an input

def test_the_decision_days_own_bar_is_dropped(tmp_path):
    """`reqHistoricalData` returns a PARTIAL bar for the day its endDateTime
    falls inside, and a complete one after 16:00. Either would put day D's close
    into the window RV_LAG exists to keep it out of — silently, because a
    partial bar looks like any other bar."""
    full = calm_then(400)
    asof = dt.datetime(full[-1].date.year, full[-1].date.month, full[-1].date.day,
                       15, 45, tzinfo=NY)
    b = broker(sessions={PRIMARY_SYMBOL: full, COVER_SYMBOL: full})
    kept = schedule.daily_features(b, PRIMARY_SYMBOL, cfg(str(tmp_path)), asof)
    assert kept[-1].date == full[-2].date
    assert all(s.date < asof.date() for s in kept)


def test_dropping_it_changes_the_rv(tmp_path):
    """If the drop were a no-op this test would be worthless, so prove it bites."""
    full = calm_then(400)
    asof = dt.datetime(full[-1].date.year, full[-1].date.month, full[-1].date.day,
                       15, 45, tzinfo=NY)
    b = broker(sessions={PRIMARY_SYMBOL: full, COVER_SYMBOL: full})
    c = cfg(str(tmp_path))
    with_drop = schedule.todays_signals(b, c, asof)[PRIMARY_SYMBOL].rv
    naive = features.realised_vol(features.close_to_close(full), len(full))
    assert with_drop != pytest.approx(naive), \
        "the partial-bar filter must actually move the number it guards"


# =============================== invariant 2: today's cut == the research's cut

def test_todays_signal_equals_what_build_computes_for_that_day(tmp_path):
    """The live path and the research path must agree on the SAME day.

    `features.build` emits a row only for days that have a FOLLOWING session,
    because it also measures the realised overnight return — so its newest row
    is D-2. Taking the threshold history from it would decide today against a
    cut one observation short of the backtest's. This pins the live path to
    `build`'s answer for a day where `build` has one.
    """
    full = calm_then(400)
    feats = features.build(full)
    day = max(feats)                          # the newest day build can decide
    idx = next(i for i, s in enumerate(full) if s.date == day)

    asof = dt.datetime(day.year, day.month, day.day, 15, 45, tzinfo=NY)
    b = broker(sessions={PRIMARY_SYMBOL: full, COVER_SYMBOL: full})
    sig = schedule.todays_signals(b, cfg(str(tmp_path)), asof)[PRIMARY_SYMBOL]

    assert sig.last_date == full[idx - 1].date
    assert sig.rv == pytest.approx(feats[day].rv, abs=1e-12)
    assert sig.threshold == pytest.approx(feats[day].threshold, abs=1e-12)
