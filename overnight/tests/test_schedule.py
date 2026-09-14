"""The two jobs, and every guard that must stop them.

Written against the rule that matters most: **no refusal may ever leave the
account with a larger position than it had.** Each test below names the real
failure it is standing in for.
"""
import datetime as dt
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import schedule
import state as state_mod
from config import OvernightConfig
from constants import COVER_SYMBOL, PRIMARY_SYMBOL
from fake_broker import (FakeBroker, Q, calm_then, quotes_for, ramp,
                         stormy_recently)
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def cfg(tmp, **kw):
    c = OvernightConfig(
        state_path=os.path.join(tmp, "state.json"),
        ledger_path=os.path.join(tmp, "ledger.csv"),
        db_path=os.path.join(tmp, "x.db"), **kw)
    c.validate()
    return c


def at(h, m, s=0, day=(2026, 9, 14)):
    return dt.datetime(*day, h, m, s, tzinfo=NY)


def broker(**kw):
    kw.setdefault("sessions", {PRIMARY_SYMBOL: calm_then(400),
                               COVER_SYMBOL: calm_then(400, seed=5)})
    kw.setdefault("quotes", quotes_for(kw["sessions"]))
    return FakeBroker(**kw)


# ======================================================== ENTER — the guards

def test_enter_refuses_before_the_window(tmp_path):
    with pytest.raises(schedule.Refused, match="before"):
        schedule.enter(broker(), cfg(str(tmp_path)), asof=at(14, 0))


def test_enter_refuses_PAST_THE_1550_DEADLINE(tmp_path):
    """A late MOC is rejected, not queued. Sending one is worse than nothing."""
    b = broker()
    with pytest.raises(schedule.Refused, match="deadline"):
        schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 51))
    assert b.placed == []


def test_enter_refuses_when_already_holding(tmp_path):
    """Means the morning exit did not happen. Never trade on top of that."""
    b = broker(positions={PRIMARY_SYMBOL: 1144})
    with pytest.raises(schedule.Refused, match="already holding"):
        schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 45))
    assert b.placed == []


def test_enter_refuses_when_an_order_is_already_working(tmp_path):
    b = broker()
    b._working.append(type("W", (), dict(symbol=PRIMARY_SYMBOL, order_id=1))())
    with pytest.raises(schedule.Refused, match="working order"):
        schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 45))
    assert b.placed == []


def test_enter_refuses_below_the_equity_floor(tmp_path):
    """Under $12,228 the $0.35 commission minimum dominates. STRATEGY.md §3.5."""
    b = broker(equity=5_000.0)
    with pytest.raises(schedule.Refused, match="below the"):
        schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 45))
    assert b.placed == []


def test_enter_refuses_on_short_history(tmp_path):
    """A short history is a DIFFERENT threshold, not a noisier one."""
    b = broker(sessions={PRIMARY_SYMBOL: ramp(50), COVER_SYMBOL: ramp(50)})
    with pytest.raises(schedule.Refused, match="sessions, need"):
        schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 45))
    assert b.placed == []


# ======================================================== ENTER — the actions

def test_enter_places_nothing_when_the_decision_is_flat(tmp_path):
    """Both instruments at their most volatile ever -> neither eligible -> flat."""
    b = broker(sessions={PRIMARY_SYMBOL: stormy_recently(400),
                         COVER_SYMBOL: stormy_recently(400, seed=5)})
    c = cfg(str(tmp_path))
    r = schedule.enter(b, c, asof=at(15, 45))
    assert r.acted is False, "a stormy night must not trade"
    assert b.placed == []
    assert state_mod.read_intent(c.state_path).is_flat


def test_enter_takes_the_COVER_leg_when_only_the_cover_is_calm(tmp_path):
    """The 23% of nights that are the whole reason XLU is in this strategy."""
    sessions = {PRIMARY_SYMBOL: stormy_recently(400),
                COVER_SYMBOL: calm_then(400, seed=5)}
    b = broker(sessions=sessions, quotes=quotes_for(sessions))
    c = cfg(str(tmp_path))
    r = schedule.enter(b, c, asof=at(15, 45))
    assert r.acted
    assert b.placed[0]["symbol"] == COVER_SYMBOL
    px = sessions[COVER_SYMBOL][-1].close
    assert b.placed[0]["qty"] == int(140_000 * c.cover_multiple // px)


def test_enter_prefers_the_PRIMARY_when_both_are_calm(tmp_path):
    b = broker(sessions={PRIMARY_SYMBOL: calm_then(400),
                         COVER_SYMBOL: calm_then(400, seed=5)})
    r = schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 45))
    assert r.acted and b.placed[0]["symbol"] == PRIMARY_SYMBOL


def test_enter_sizes_and_sends_a_moc(tmp_path):
    b = broker()
    c = cfg(str(tmp_path))
    r = schedule.enter(b, c, asof=at(15, 45))
    if not r.acted:
        pytest.skip("fixture produced a flat night")
    o = b.placed[0]
    assert o["kind"] == "MOC" and o["action"] == "BUY"
    px = b.quote(o["symbol"]).last
    mult = c.primary_multiple if o["symbol"] == PRIMARY_SYMBOL else c.cover_multiple
    assert o["qty"] == int(140_000 * mult // px)
    assert o["qty"] * px <= 140_000 * mult          # rounded DOWN, never over


def test_enter_writes_an_intent_that_records_the_signal(tmp_path):
    b = broker()
    c = cfg(str(tmp_path))
    schedule.enter(b, c, asof=at(15, 45))
    i = state_mod.read_intent(c.state_path)
    assert i is not None
    assert i.decision_date == "2026-09-14"
    assert i.primary_rv is not None and i.primary_threshold is not None


def test_enter_reports_when_an_order_is_never_acknowledged(tmp_path):
    """Silence is the failure mode. It must be named, and NOT retried."""
    b = broker(ack_after=999)
    r = schedule.enter(b, cfg(str(tmp_path)), asof=at(15, 45))
    if not r.acted:
        pytest.skip("fixture produced a flat night")
    assert "NOT ACKNOWLEDGED" in r.detail
    assert len(b.placed) == 1, "a missing acknowledgement must never re-place"


def test_rehearsal_sends_a_synthetic_id_and_marks_intent_untransmitted(tmp_path):
    b = broker(transmit=False)
    c = cfg(str(tmp_path))
    r = schedule.enter(b, c, asof=at(15, 45))
    if not r.acted:
        pytest.skip("fixture produced a flat night")
    assert state_mod.read_intent(c.state_path).transmitted is False


# ========================================================= EXIT — the guards

def test_exit_refuses_before_its_window(tmp_path):
    with pytest.raises(schedule.Refused, match="before"):
        schedule.exit_(broker(), cfg(str(tmp_path)), asof=at(8, 30))


def test_exit_refuses_PAST_THE_MOO_DEADLINE(tmp_path):
    """Arca rejects new MOO orders from 09:29:55. Past the guard, alert loudly."""
    b = broker(positions={PRIMARY_SYMBOL: 1144})
    with pytest.raises(schedule.Refused, match="held through the session"):
        schedule.exit_(b, cfg(str(tmp_path)), asof=at(9, 45))
    assert b.placed == []


def test_exit_refuses_to_act_on_a_short_position(tmp_path):
    """This strategy never shorts; a negative position means something is wrong."""
    b = broker(positions={PRIMARY_SYMBOL: -100})
    with pytest.raises(schedule.Refused, match="short"):
        schedule.exit_(b, cfg(str(tmp_path)), asof=at(9, 15))
    assert b.placed == []


# ========================================================= EXIT — the actions

def test_exit_does_nothing_when_flat(tmp_path):
    b = broker()
    r = schedule.exit_(b, cfg(str(tmp_path)), asof=at(9, 15))
    assert r.acted is False and b.placed == []


def test_exit_SELLS_WHAT_THE_BROKER_HOLDS_not_what_state_says(tmp_path):
    """The rule band_lab learned the hard way. State is a record, not authority.

    Here the state file claims 500 shares and the account holds 1,144. Selling
    500 would leave 644 held through the session.
    """
    c = cfg(str(tmp_path))
    state_mod.write_intent(c.state_path, state_mod.Intent(
        decision_date="2026-09-13", leg=PRIMARY_SYMBOL, multiple=1.0, shares=500,
        order_id=1, order_ref="x", equity_at_entry=140_000.0, reference_price=122.0))
    b = broker(positions={PRIMARY_SYMBOL: 1144})
    r = schedule.exit_(b, c, asof=at(9, 15))
    assert r.acted
    assert b.placed[0]["qty"] == 1144          # the broker's number, not 500
    assert b.placed[0]["kind"] == "MOO"
    assert b.placed[0]["action"] == "SELL"


def test_exit_works_with_no_state_file_at_all(tmp_path):
    """A lost state file must not strand a position."""
    b = broker(positions={COVER_SYMBOL: 8258})
    r = schedule.exit_(b, cfg(str(tmp_path)), asof=at(9, 15))
    assert r.acted and b.placed[0]["qty"] == 8258


def test_exit_sells_both_legs_if_somehow_both_are_held(tmp_path):
    """Should be impossible by construction; if it happens, flatten everything."""
    b = broker(positions={PRIMARY_SYMBOL: 100, COVER_SYMBOL: 200})
    r = schedule.exit_(b, cfg(str(tmp_path)), asof=at(9, 15))
    assert {p["symbol"] for p in b.placed} == {PRIMARY_SYMBOL, COVER_SYMBOL}


def test_exit_warns_when_the_moc_evidently_did_not_fill(tmp_path):
    c = cfg(str(tmp_path))
    state_mod.write_intent(c.state_path, state_mod.Intent(
        decision_date="2026-09-13", leg=PRIMARY_SYMBOL, multiple=1.0, shares=1144,
        order_id=1, order_ref="x", equity_at_entry=140_000.0, reference_price=122.0))
    b = broker()                                   # account is flat
    seen = []
    r = schedule.exit_(b, c, asof=at(9, 15), events=lambda l, m: seen.append((l, m)))
    assert r.acted is False
    assert any("may not have filled" in m for _, m in seen)


# ====================================================== CONFIRM — the fill job

class E:
    def __init__(self, side, qty, price):
        self.side, self.qty, self.price = side, qty, price
        self.exec_id = f"{side}{qty}{price}"


def with_execs(b, symbol, rows):
    b.executions = lambda s, _r=rows, _sym=symbol: list(_r) if s == _sym else []
    return b


def _intent(c, leg=PRIMARY_SYMBOL, shares=1144):
    i = state_mod.Intent(decision_date="2026-09-14", leg=leg, multiple=1.0,
                         shares=shares, order_id=1, order_ref="x",
                         equity_at_entry=140_000.0, reference_price=122.28)
    state_mod.write_intent(c.state_path, i)
    return i


def test_confirm_records_the_vwap_across_several_executions(tmp_path):
    """One order is not one fill. IBKR settles in as many as the book requires."""
    c = cfg(str(tmp_path)); _intent(c)
    b = with_execs(broker(positions={PRIMARY_SYMBOL: 1144}), PRIMARY_SYMBOL,
                   [E("BOT", 644, 122.00), E("BOT", 500, 122.50)])
    r = schedule.confirm(b, c, asof=at(16, 5))
    assert r.acted
    i = state_mod.read_intent(c.state_path)
    assert i.filled_shares == 1144
    assert i.fill_price == pytest.approx((644*122.00 + 500*122.50)/1144, abs=1e-4)
    assert i.entry_confirmed


def test_confirm_ignores_sells(tmp_path):
    c = cfg(str(tmp_path)); _intent(c)
    b = with_execs(broker(positions={PRIMARY_SYMBOL: 1144}), PRIMARY_SYMBOL,
                   [E("BOT", 1144, 122.00), E("SLD", 1144, 123.00)])
    schedule.confirm(b, c, asof=at(16, 5))
    assert state_mod.read_intent(c.state_path).fill_price == pytest.approx(122.00)


def test_confirm_reports_a_missing_fill_loudly(tmp_path):
    """A MOC that did not fill means the account is flat tonight. Must be named."""
    c = cfg(str(tmp_path)); _intent(c)
    b = with_execs(broker(), PRIMARY_SYMBOL, [])
    seen = []
    r = schedule.confirm(b, c, asof=at(16, 5), events=lambda l, m: seen.append((l, m)))
    assert r.acted is False
    assert any(l == "error" and "NO fill" in m for l, m in seen)


def test_confirm_warns_on_a_partial(tmp_path):
    c = cfg(str(tmp_path)); _intent(c, shares=1144)
    b = with_execs(broker(positions={PRIMARY_SYMBOL: 900}), PRIMARY_SYMBOL,
                   [E("BOT", 900, 122.00)])
    seen = []
    schedule.confirm(b, c, asof=at(16, 5), events=lambda l, m: seen.append((l, m)))
    assert any("partial" in m for _, m in seen)


def test_confirm_is_a_noop_on_a_flat_night(tmp_path):
    c = cfg(str(tmp_path))
    state_mod.write_intent(c.state_path, state_mod.Intent(
        decision_date="2026-09-14", leg="FLAT", multiple=0.0, shares=0,
        order_id=0, order_ref="", equity_at_entry=140_000.0, reference_price=0.0))
    r = schedule.confirm(broker(), c, asof=at(16, 5))
    assert r.acted is False
