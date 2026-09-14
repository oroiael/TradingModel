"""Partial fills, from the first live night.

2026-09-14: `enter` ordered 1,390 SOXL market-on-close and 629 filled, across
four executions at an average of 101.2649. That is 45.3% of the intended size —
0.447x equity, not 1.00x.

Nothing about that is dangerous: under-sized is the safe direction, and `exit`
sizes from `broker.position()` so it sells exactly what is there. What IS
dangerous is reporting it as a 1.00x night, because `running_totals` compounds
`net_pct` and the error would never come back out of the inception-to-date
figures.
"""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run as run_mod
import schedule
import state as state_mod
from config import OvernightConfig
from constants import PRIMARY_COST_BPS, PRIMARY_SYMBOL
from fake_broker import FakeBroker, W, calm_then, quotes_for
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

#: The real numbers from the night this file is about.
ORDERED, FILLED = 1390, 629
ENTRY, EQUITY = 101.2649, 142_492.0


class E:
    def __init__(self, side, qty, price):
        self.side, self.qty, self.price = side, qty, price
        self.time = dt.datetime(2026, 9, 15, 9, 30)
        self.exec_id = f"{side}{qty}{price}"


def cfg(tmp):
    c = OvernightConfig(state_path=os.path.join(tmp, "state.json"),
                        ledger_path=os.path.join(tmp, "ledger.csv"),
                        db_path=os.path.join(tmp, "x.db"))
    c.validate()
    return c


def broker(**kw):
    sessions = {PRIMARY_SYMBOL: calm_then(400), "XLU": calm_then(400, seed=5)}
    kw.setdefault("sessions", sessions)
    kw.setdefault("quotes", quotes_for(sessions))
    return FakeBroker(**kw)


def partial_intent(c, filled=FILLED, ordered=ORDERED):
    i = state_mod.Intent(
        decision_date="2026-09-14", leg=PRIMARY_SYMBOL, multiple=1.0,
        shares=ordered, order_id=8, order_ref="ON-20260914-SOXL-ENTER",
        equity_at_entry=EQUITY, reference_price=102.51, transmitted=True,
        filled_shares=filled, fill_price=ENTRY)
    state_mod.write_intent(c.state_path, i)
    return i


def report(tmp, exit_px, sold=FILLED):
    c = cfg(tmp)
    partial_intent(c)
    b = broker(equity=EQUITY)
    b.executions = lambda s: [E("SLD", sold, exit_px)] if s == PRIMARY_SYMBOL else []
    rc = run_mod.job_report(b, c, _Store())
    return rc, state_mod.read_ledger(c.ledger_path)[0]


class _Store:
    def event(self, *a, **k): pass


# ================================================= the row tells the truth

def test_the_ledger_records_the_size_that_actually_traded(tmp_path):
    _, row = report(str(tmp_path), 103.0)
    assert int(row["shares"]) == FILLED
    assert int(row["intended_shares"]) == ORDERED
    assert float(row["fill_rate_pct"]) == pytest.approx(45.25, abs=0.01)


def test_the_multiple_is_the_real_one_not_the_intended_one(tmp_path):
    _, row = report(str(tmp_path), 103.0)
    assert float(row["multiple_intended"]) == 1.0
    assert float(row["multiple_actual"]) == pytest.approx(
        FILLED * ENTRY / EQUITY, abs=1e-4)
    assert float(row["multiple_actual"]) < 0.46, "0.447x, not 1.00x"


def test_pnl_is_dollars_that_actually_moved(tmp_path):
    exit_px = 103.0
    _, row = report(str(tmp_path), exit_px)
    notional = FILLED * ENTRY
    expect = FILLED * (exit_px - ENTRY) - notional * 2 * PRIMARY_COST_BPS / 1e4
    assert float(row["pnl_dollars"]) == pytest.approx(expect, abs=0.02)


def test_scaling_by_the_INTENDED_multiple_would_overstate_by_more_than_double(tmp_path):
    """The bug this file exists to prevent, stated as a number."""
    exit_px = 103.0
    _, row = report(str(tmp_path), exit_px)
    gross = exit_px / ENTRY - 1.0
    naive = 1.0 * gross * EQUITY                 # what the old code produced
    assert naive / float(row["pnl_dollars"]) > 2.0


def test_net_pct_is_against_equity_so_running_totals_compound_correctly(tmp_path):
    _, row = report(str(tmp_path), 103.0)
    assert float(row["net_pct"]) == pytest.approx(
        float(row["pnl_dollars"]) / EQUITY * 100.0, abs=1e-3)


def test_a_full_fill_still_reads_as_one_times(tmp_path):
    """The common case must not have been broken by fixing the rare one."""
    c = cfg(str(tmp_path))
    shares = int(EQUITY // ENTRY)
    partial_intent(c, filled=shares, ordered=shares)
    b = broker(equity=EQUITY)
    b.executions = lambda s: [E("SLD", shares, 103.0)] if s == PRIMARY_SYMBOL else []
    run_mod.job_report(b, c, _Store())
    row = state_mod.read_ledger(c.ledger_path)[0]
    assert float(row["multiple_actual"]) == pytest.approx(1.0, abs=0.01)
    assert float(row["fill_rate_pct"]) == pytest.approx(100.0, abs=0.01)


def test_the_partial_is_called_out_on_screen(tmp_path, capsys):
    report(str(tmp_path), 103.0)
    out = capsys.readouterr().out
    assert "PARTIAL: 629 of 1390" in out and "0.447x" in out


# ============================ nothing in the morning may open a position

def test_exit_cancels_a_leftover_working_buy(tmp_path):
    """Sell at the open and let the rest of last night's buy fill at tonight's
    close, and you hold something nobody decided on with no exit scheduled."""
    c = cfg(str(tmp_path))
    b = broker(positions={PRIMARY_SYMBOL: FILLED})
    b._working.append(W("ON-20260914-SOXL-ENTER", 8, PRIMARY_SYMBOL, "BUY",
                        "MOC", ORDERED - FILLED))
    cancelled = []
    orig = b.cancel
    b.cancel = lambda oid: (cancelled.append(oid), orig(oid))
    schedule.exit_(b, c, asof=dt.datetime(2026, 9, 15, 9, 15, tzinfo=NY))
    assert cancelled == [8]
    assert b.placed[0]["action"] == "SELL" and b.placed[0]["qty"] == FILLED


def test_it_does_not_cancel_the_sell_it_is_about_to_rely_on(tmp_path):
    c = cfg(str(tmp_path))
    b = broker(positions={PRIMARY_SYMBOL: FILLED})
    b._working.append(W("someone-elses-sell", 9, PRIMARY_SYMBOL, "SELL",
                        "LMT", 100))
    cancelled = []
    orig = b.cancel
    b.cancel = lambda oid: (cancelled.append(oid), orig(oid))
    schedule.exit_(b, c, asof=dt.datetime(2026, 9, 15, 9, 15, tzinfo=NY))
    assert cancelled == [], "only BUYs are in scope here"


def test_cancelling_nothing_is_free(tmp_path):
    b = broker(positions={PRIMARY_SYMBOL: FILLED})
    assert schedule.cancel_working_buys(b, ("SOXL", "XLU")) == 0


def test_a_broker_that_cannot_answer_does_not_stop_the_exit(tmp_path):
    """A diagnostic that fails must never stand the exit down, and must never
    crash AFTER the order is placed — that reports a failure for an order that
    went out, and the obvious response is to run it again."""
    c = cfg(str(tmp_path))
    b = broker(positions={PRIMARY_SYMBOL: FILLED})
    b.refresh_orders = lambda: (_ for _ in ()).throw(RuntimeError("TWS says no"))
    r = schedule.exit_(b, c, asof=dt.datetime(2026, 9, 15, 9, 15, tzinfo=NY))
    assert r.acted and b.placed[0]["action"] == "SELL"
    assert "NOT ACKNOWLEDGED" in r.detail, "silence must be named, not swallowed"


def test_exit_is_safe_to_run_twice(tmp_path):
    """It is re-runnable by hand and by a scheduler that saw a non-zero exit
    code. Two MOO sells against one long position is a short."""
    c = cfg(str(tmp_path))
    b = broker(positions={PRIMARY_SYMBOL: FILLED})
    when = dt.datetime(2026, 9, 15, 9, 15, tzinfo=NY)
    schedule.exit_(b, c, asof=when)
    schedule.exit_(b, c, asof=when)              # the position has not filled yet
    assert len([p for p in b.placed if p["action"] == "SELL"]) == 1


def test_it_still_sells_when_a_working_sell_is_too_small(tmp_path):
    """A 100-share sell does not cover 629. Standing down would leave 529."""
    c = cfg(str(tmp_path))
    b = broker(positions={PRIMARY_SYMBOL: FILLED})
    b._working.append(W("partial", 9, PRIMARY_SYMBOL, "SELL", "LMT", 100))
    schedule.exit_(b, c, asof=dt.datetime(2026, 9, 15, 9, 15, tzinfo=NY))
    assert any(p["action"] == "SELL" and p["qty"] == FILLED for p in b.placed)
