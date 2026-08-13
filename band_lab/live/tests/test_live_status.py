"""
Stage 7 — tests for the phone-sized status snapshot.

The thing this must not do is reassure. A snapshot that renders cleanly while
the engine is dead, or that omits an open position after 16:00, is worse than
no snapshot at all — it is the console window's one job, done wrong, on a
device you are trusting instead of looking.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import status
from status import render
from store import Store

NY = ZoneInfo("America/New_York")
SESSION = "20260812"
CAPITAL = 74_471.0


def utc(hh: int, mm: int, day: str = "2026-08-12") -> str:
    return f"{day}T{hh + 4:02d}:{mm:02d}:00.000+00:00"


def at(hh: int, mm: int) -> datetime:
    return datetime(2026, 8, 12, hh, mm, tzinfo=NY)


@pytest.fixture
def store(tmp_path) -> Store:
    s = Store(str(tmp_path / "t.db"))
    yield s
    s.close()


def write_daily(store, symbol="SOXL", *, gate=1, filter_ok=1):
    store.daily(SESSION, symbol, gate_ok=gate, gate_reason="gate_on",
                filter_ok=filter_ok, filter_reason="filter_on", atr5=8.35,
                or30=3.44, thr80=5.64, pos10=0.62, sleeve_capital=CAPITAL,
                account_equity=148_942.0)


def write_fill(store, exec_id, role, side, qty, price, hh, mm, symbol="SOXL"):
    store._ins("fills", ts=utc(hh, mm), symbol=symbol, session=SESSION,
               exec_id=exec_id, order_ref=f"{SESSION}-{symbol}-{role}-1",
               role=role, side=side, qty=qty, price=price)


def beat(tmp_path, minutes_ago=0.0, transmit=True, now=None):
    now = now or at(12, 0)
    path = str(tmp_path / "heartbeat.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"ts": (now - timedelta(minutes=minutes_ago)).isoformat(),
                   "session": SESSION, "pid": 4242, "transmit": transmit,
                   "sleeves": {"SOXL": "ARMED"}}, fh)
    return path


# --------------------------------------------------------------- the engine
def test_a_missing_heartbeat_is_stated_not_skipped(store, tmp_path):
    write_daily(store)
    out = render(store, SESSION, str(tmp_path / "nothing.json"), now=at(12, 0))
    assert "no heartbeat file" in out


def test_a_stale_heartbeat_is_flagged(store, tmp_path):
    """§6.2's threshold, restated for a human. `watchdog.py` acts on it; this
    only says so — two processes acting on one condition is how you get two
    flattens."""
    write_daily(store)
    out = render(store, SESSION, beat(tmp_path, minutes_ago=5), now=at(12, 0))
    assert "STALE" in out


def test_a_fresh_heartbeat_reads_alive(store, tmp_path):
    write_daily(store)
    out = render(store, SESSION, beat(tmp_path, minutes_ago=0.2), now=at(12, 0))
    assert "alive" in out and "STALE" not in out


def test_a_rehearsal_says_so(store, tmp_path):
    """Reading a transmit-OFF day as a real one is how you conclude the
    strategy made no money when it never placed an order."""
    write_daily(store)
    out = render(store, SESSION, beat(tmp_path, transmit=False), now=at(12, 0))
    assert "transmit OFF" in out


# --------------------------------------------------------------- the sleeves
def test_a_stood_down_sleeve_says_why(store, tmp_path):
    store.daily(SESSION, "SOXS", gate_ok=1, gate_reason="gate_on", filter_ok=0,
                filter_reason="stand_down_wide_or_weak_pos10",
                sleeve_capital=CAPITAL)
    out = render(store, SESSION, beat(tmp_path), now=at(12, 0))
    assert "stood down" in out and "stand_down_wide_or_weak_pos10" in out


def test_closed_round_trips_are_listed_with_their_outcome(store, tmp_path):
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 509, 144.34, 11, 0)
    write_fill(store, "x1", "T", "SLD", 509, 145.78, 11, 10)
    out = render(store, SESSION, beat(tmp_path), now=at(12, 0))
    assert "144.34 → 145.78" in out
    assert "target" in out
    assert "+99.8 bp" in out


def test_an_open_position_is_reported_as_held_not_as_a_trade(store, tmp_path):
    """Booking an unclosed position as a round trip is defect §4.7's
    -4018 bp — a fabricated number that looks like a catastrophe and buries
    the real fault, which is that shares are still out there."""
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 510, 145.82, 11, 40)
    out = render(store, SESSION, beat(tmp_path), now=at(12, 0))
    assert "HOLDING" in out and "145.82" in out
    assert "0 round trip(s)" in out


def test_not_flat_after_the_hard_deadline_is_the_loudest_thing_on_the_page(
        store, tmp_path):
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 510, 145.82, 11, 40)
    out = render(store, SESSION, beat(tmp_path, now=at(16, 5)), now=at(16, 5))
    assert "NOT FLAT" in out and "SOXL" in out


def test_flat_after_the_deadline_says_so(store, tmp_path):
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 509, 144.34, 11, 0)
    write_fill(store, "x1", "T", "SLD", 509, 145.78, 15, 56)
    out = render(store, SESSION, beat(tmp_path, now=at(16, 5)), now=at(16, 5))
    assert "flat past" in out and "NOT FLAT" not in out


def test_the_flat_verdict_is_not_claimed_before_the_deadline(store, tmp_path):
    """At noon, holding a position is the strategy working."""
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 510, 145.82, 11, 40)
    out = render(store, SESSION, beat(tmp_path), now=at(12, 0))
    assert "NOT FLAT" not in out and "flat past" not in out


# ----------------------------------------------------------------- events
def test_a_critical_event_is_surfaced(store, tmp_path):
    write_daily(store)
    store.event("critical", "engine", "SOXL STILL HOLDS 510 SHARES",
                session=SESSION, symbol="SOXL")
    out = render(store, SESSION, beat(tmp_path), now=at(12, 0))
    assert "CRITICAL" in out and "STILL HOLDS" in out


def test_warnings_do_not_masquerade_as_criticals(store, tmp_path):
    write_daily(store)
    store.event("warn", "orders", "bracket replaced", session=SESSION)
    out = render(store, SESSION, beat(tmp_path), now=at(12, 0))
    assert "warnings and errors" in out
    assert "CRITICAL" not in out


# ------------------------------------------------------------------ privacy
def test_no_dollars_omits_cash_and_size_but_keeps_the_decision(store, tmp_path):
    """`PROJECT_STATUS.md` §5F: alerting must not carry positions and P&L in
    clear text through a third party. This is the version worth defaulting to
    on a phone — it still answers "is it working?"."""
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 509, 144.34, 11, 0)
    write_fill(store, "x1", "T", "SLD", 509, 145.78, 11, 10)
    full = render(store, SESSION, beat(tmp_path), now=at(12, 0), dollars=True)
    thin = render(store, SESSION, beat(tmp_path), now=at(12, 0), dollars=False)

    assert "74,471" in full and "74,471" not in thin      # sleeve capital
    assert "+99.8 bp" in full and "+99.8 bp" in thin      # the decision stays
    assert "target" in thin


def test_no_dollars_hides_the_share_count_of_an_open_position(store, tmp_path):
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 510, 145.82, 11, 40)
    thin = render(store, SESSION, beat(tmp_path), now=at(12, 0), dollars=False)
    assert "HOLDING" in thin and "510 sh" not in thin


# ------------------------------------------------------------- degenerate
def test_an_empty_database_renders_rather_than_raising(store, tmp_path):
    """The engine has not started yet is an ordinary state at 08:00, not an
    error, and a monitor that traceback's on it will not be trusted at 15:55."""
    out = render(store, None, str(tmp_path / "none.json"), now=at(8, 0))
    assert "no session" in out.lower()


def test_a_session_with_no_daily_row_yet_does_not_raise(store, tmp_path):
    store.event("info", "run", "starting", session=SESSION)
    store.daily(SESSION, "SOXL", gate_ok=1, sleeve_capital=CAPITAL)
    out = render(store, SESSION, beat(tmp_path), now=at(9, 40))
    assert "SOXL" in out


def test_render_never_writes_to_the_database(store, tmp_path):
    """`store.py` makes the broker the only source of state. A monitor that
    could feed back into a decision would break that, so this asserts the
    file itself is untouched."""
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 509, 144.34, 11, 0)
    before = os.path.getsize(store.path)
    for _ in range(3):
        render(store, SESSION, beat(tmp_path), now=at(12, 0))
    assert os.path.getsize(store.path) == before


def test_importing_status_never_reaches_the_broker():
    """`report.py` states this about itself and it is load-bearing for both:
    a tool you run against a *live* session must not be able to reach the
    account it is watching.

    Asserted on the real import graph in a clean interpreter, not on the source
    text — the obvious `"ib_async" not in src` version passes or fails on
    whether a docstring mentions the word, and would go green on a module that
    imported the broker three hops down. Run in a subprocess because the rest
    of the suite imports `broker` and `sys.modules` is process-wide.
    """
    code = (
        "import sys; sys.path.insert(0, %r); import status; "
        "print('broker' in sys.modules, 'ib_async' in sys.modules)"
        % os.path.dirname(os.path.abspath(status.__file__)))
    res = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "False False"
