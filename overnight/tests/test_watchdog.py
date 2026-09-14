"""The job that catches the one unrecoverable state.

Every test below names a way `exit` can leave a position behind, or a way a
flatten can make things worse than the position it was fixing. The second kind
matters as much as the first: band_lab's first flatten turned a long 541 into a
short 1,082 by stacking market orders on top of sells already in flight.
"""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state as state_mod
import watchdog
from config import OvernightConfig
from constants import COVER_SYMBOL, PRIMARY_SYMBOL
from fake_broker import FakeBroker, W, calm_then, quotes_for
from schedule import Refused
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def cfg(tmp, **kw):
    c = OvernightConfig(state_path=os.path.join(tmp, "state.json"),
                        ledger_path=os.path.join(tmp, "ledger.csv"),
                        db_path=os.path.join(tmp, "x.db"), **kw)
    c.validate()
    return c


def at(h, m, s=0):
    return dt.datetime(2026, 9, 15, h, m, s, tzinfo=NY)


def broker(**kw):
    sessions = {PRIMARY_SYMBOL: calm_then(400), COVER_SYMBOL: calm_then(400, seed=5)}
    kw.setdefault("sessions", sessions)
    kw.setdefault("quotes", quotes_for(sessions))
    return FakeBroker(**kw)


class Clock:
    """A clock the test drives, so a time budget can be tested in milliseconds."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def run(b, tmp, when=None, **kw):
    clk = kw.pop("clock", None) or Clock()
    b.wait = lambda s, _c=clk: setattr(_c, "t", _c.t + s)
    return watchdog.flatten(b, cfg(tmp), asof=when or at(9, 40), clock=clk, **kw)


# ============================================================== the windows

def test_it_will_not_act_before_the_auction_has_printed(tmp_path):
    """At 09:15 the MOO has not had its auction. A position is not yet evidence."""
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    with pytest.raises(Refused, match="before 09:31"):
        run(b, str(tmp_path), when=at(9, 15))
    assert b.placed == []


def test_it_will_not_act_into_the_closing_auction(tmp_path):
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    with pytest.raises(Refused, match="past 15:40"):
        run(b, str(tmp_path), when=at(15, 45))
    assert b.placed == []


def test_the_windows_cannot_be_configured_to_race_the_other_jobs():
    with pytest.raises(ValueError, match="after exit_deadline"):
        OvernightConfig(watchdog_open=dt.time(9, 0)).validate()
    with pytest.raises(ValueError, match="before enter_target"):
        OvernightConfig(watchdog_close=dt.time(15, 46)).validate()


# ====================================================== the quiet, common case

def test_a_flat_account_does_nothing_at_all(tmp_path):
    """Four days in five this finds nothing, and must cost nothing."""
    b = broker()
    r = run(b, str(tmp_path))
    assert r.acted is False and b.placed == []


def test_running_it_five_times_a_day_is_free(tmp_path):
    b = broker()
    for hour in (9, 10, 12, 14, 15):
        assert run(b, str(tmp_path), when=at(hour, 35)).acted is False
    assert b.placed == []


# ================================================== the state it exists to fix

def test_a_position_left_after_the_open_is_sold_at_market(tmp_path):
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    b._positions[PRIMARY_SYMBOL] = 1149

    real_place = b.place_market if hasattr(b, "place_market") else None
    r = run(b, str(tmp_path))
    assert r.acted
    o = b.placed[0]
    assert o["kind"] == "MKT" and o["action"] == "SELL"
    assert o["symbol"] == PRIMARY_SYMBOL and o["qty"] == 1149


def test_it_sizes_from_the_broker_not_the_state_file(tmp_path):
    """band_lab's defect 3: sizing from a remembered number left 241 of 541
    shares unprotected."""
    c = cfg(str(tmp_path))
    state_mod.write_intent(c.state_path, state_mod.Intent(
        decision_date="2026-09-14", leg=PRIMARY_SYMBOL, multiple=1.0,
        shares=1149, order_id=1, order_ref="x", equity_at_entry=142_492.0,
        reference_price=121.82))
    b = broker(positions={PRIMARY_SYMBOL: 900})     # only 900 actually filled
    run(b, str(tmp_path))
    assert b.placed[0]["qty"] == 900


def test_it_flattens_the_cover_leg_too(tmp_path):
    b = broker(positions={COVER_SYMBOL: 8258})
    run(b, str(tmp_path))
    assert b.placed[0]["symbol"] == COVER_SYMBOL and b.placed[0]["qty"] == 8258


def test_it_reports_flat_once_the_position_is_gone(tmp_path):
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    orig = b.place_market

    def fill(symbol, action, qty, ref):
        oid = orig(symbol, action, qty, ref)
        b._positions[symbol] = 0.0                  # the sell fills
        return oid

    b.place_market = fill
    r = run(b, str(tmp_path))
    assert "flat" in r.detail and "STILL HOLDING" not in r.detail


# ========================================= making it worse is the other failure

def test_it_does_NOT_stack_a_second_sell_on_a_working_one(tmp_path):
    """Three sells of 541 against one long 541 is a short 1,082. This is the
    single most damaging thing a flatten can do.

    The sell here never clears — band_lab's `PendingCancel` that sat holding
    524 shares while every cancel was acknowledged and none took effect. No
    market order may go out for as long as it is visible.
    """
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    b._working.append(W("ON-x-SOXL-EXIT", 77, PRIMARY_SYMBOL, "SELL", "MOO", 1149))
    b.cancel = lambda oid: None                  # acknowledged, never effected
    r = run(b, str(tmp_path), budget=60.0, settle=6.0)
    assert b.placed == [], "a sell in flight must be waited on, not added to"
    assert "UNSOLD" in r.detail, "and the failure has to be reported, not hidden"


def test_it_never_stacks_on_its_OWN_working_flatten(tmp_path):
    """The order it just sent comes back as a working order. Seeing its own
    sell and treating it as a reason to send another is the same bug."""
    b = broker(positions={PRIMARY_SYMBOL: 1149})     # never fills
    run(b, str(tmp_path), budget=60.0, settle=6.0)
    assert len([p for p in b.placed if p["kind"] == "MKT"]) == 1


def test_it_never_cancels_its_own_flatten(tmp_path):
    """Cancelling its own in-flight order to re-send is stacking in disguise:
    the cancel can fail to land and then both are live."""
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    cancelled = []
    orig = b.cancel
    b.cancel = lambda oid: (cancelled.append(oid), orig(oid))
    run(b, str(tmp_path), budget=60.0, settle=6.0)
    assert cancelled == []


def test_a_stale_sell_is_cancelled_before_going_to_market(tmp_path):
    """An OPG order that missed its auction holds nothing and blocks the fix."""
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    b._working.append(W("ON-x-SOXL-EXIT", 77, PRIMARY_SYMBOL, "SELL", "MOO", 1149))
    cancelled = []
    orig = b.cancel
    b.cancel = lambda oid: (cancelled.append(oid), orig(oid))
    run(b, str(tmp_path), budget=60.0, settle=3.0)
    assert 77 in cancelled, "the stale MOO must be cleared"
    assert any(p["kind"] == "MKT" for p in b.placed), "and then sold at market"


def test_a_foreign_sell_gets_exactly_one_settle_first(tmp_path, capsys):
    """It might be the MOO about to fill. Cancelling it instantly would throw
    away the thing that was going to fix this."""
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    b._working.append(W("ON-x-SOXL-EXIT", 77, PRIMARY_SYMBOL, "SELL", "MOO", 1149))
    run(b, str(tmp_path), budget=60.0, settle=3.0)
    out = capsys.readouterr().out
    assert out.index("giving them") < out.index("cancelling")


def test_it_refuses_to_touch_a_short(tmp_path):
    """Buying to cover would be acting on a state nobody designed."""
    b = broker(positions={PRIMARY_SYMBOL: -500})
    with pytest.raises(Refused, match="never shorts"):
        run(b, str(tmp_path))
    assert b.placed == []


def test_the_time_budget_is_a_deadline_not_an_attempt_count(tmp_path):
    """A five-attempt loop once burned 23 seconds with four minutes still on
    the clock, and the shares went overnight. It must spend what it has."""
    clk = Clock()
    b = broker(positions={PRIMARY_SYMBOL: 1149})     # never fills
    run(b, str(tmp_path), budget=45.0, settle=6.0, clock=clk)
    assert clk.t >= 45.0, "gave up before the budget was spent"


def test_the_send_cap_holds_when_orders_keep_vanishing(tmp_path, capsys):
    """The ghost case: IBKR works an order the client cannot see. A third send
    would sell the position three times over."""
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    b.refresh_orders = lambda: b._working.clear()   # nothing ever shows working
    r = run(b, str(tmp_path), budget=120.0, settle=6.0)
    assert len([p for p in b.placed if p["kind"] == "MKT"]) == watchdog.MAX_SENDS
    assert "Refusing to send a third" in capsys.readouterr().out
    assert "UNSOLD" in r.detail


def test_a_position_it_cannot_clear_is_reported_loudly(tmp_path, capsys):
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    r = run(b, str(tmp_path), budget=12.0, settle=6.0)
    assert "STILL HOLDING" in r.detail
    out = capsys.readouterr().out
    assert "Sell it in TWS by hand" in out


# ============================================================== what it says

def test_it_says_what_it_expected_against_what_it_found(tmp_path, capsys):
    c = cfg(str(tmp_path))
    state_mod.write_intent(c.state_path, state_mod.Intent(
        decision_date="2026-09-14", leg=PRIMARY_SYMBOL, multiple=1.0,
        shares=1149, order_id=1, order_ref="x", equity_at_entry=142_492.0,
        reference_price=121.82, transmitted=True))
    run(broker(), str(tmp_path))
    assert "intent: 1149 SOXL from 2026-09-14" in capsys.readouterr().out


def test_it_marks_a_rehearsal_intent_as_never_sent(tmp_path, capsys):
    c = cfg(str(tmp_path))
    state_mod.write_intent(c.state_path, state_mod.Intent(
        decision_date="2026-09-13", leg=PRIMARY_SYMBOL, multiple=1.0,
        shares=1277, order_id=-1, order_ref="x", equity_at_entry=142_492.0,
        reference_price=111.56, transmitted=False))
    run(broker(), str(tmp_path))
    assert "rehearsal intent (never sent): 1277 SOXL" in capsys.readouterr().out


def test_a_position_with_no_intent_is_still_sold_but_flagged(tmp_path, capsys):
    """A stale state file is recoverable. A 3x position through a session is not."""
    c = cfg(str(tmp_path))
    state_mod.write_intent(c.state_path, state_mod.Intent(
        decision_date="2026-09-14", leg="FLAT", multiple=0.0, shares=0,
        order_id=0, order_ref="", equity_at_entry=142_492.0, reference_price=0.0))
    b = broker(positions={PRIMARY_SYMBOL: 1149})
    run(b, str(tmp_path))
    out = capsys.readouterr().out
    assert "state says last night was FLAT" in out
    assert b.placed and b.placed[0]["action"] == "SELL"
