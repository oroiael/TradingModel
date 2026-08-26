"""
Tests for the account equity path.

Two ways this goes wrong quietly, and both were live risks rather than
hypotheticals:

`daily` holds one row per sleeve per session and both carry the *same*
account equity, so a SUM would double every figure and make the account look
twice its size — plausible enough on screen to go unnoticed.

And drawdown is measured from the running peak, not from the starting
equity. When the account rises before it falls the two differ, which is
exactly the case that made this module necessary: "down 4.6% from the peak"
and "down 0.75% since inception" were both true and were being confused for
each other.
"""

from __future__ import annotations

import os

import pytest

from equity_series import series
from store import Store

# Rises for three sessions, then falls below the start. peak != start, and the
# drawdown from peak is far larger than the loss since inception.
PATH = [("20260806", 143_110.0), ("20260810", 146_500.0),
        ("20260811", 148_942.0), ("20260812", 147_000.0),
        ("20260825", 142_039.0)]


@pytest.fixture()
def store(tmp_path):
    s = Store(os.path.join(str(tmp_path), "live.db"))
    for session, equity in PATH:
        for symbol in ("SOXL", "SOXS"):
            s.conn.execute(
                "INSERT INTO daily (session, symbol, account_equity, "
                "sleeve_capital, ts) VALUES (?,?,?,?,?)",
                (session, symbol, equity, equity / 2, "2026-01-01T00:00:00Z"))
    s.conn.commit()
    return s


def test_the_two_sleeves_are_one_account(store):
    """Both sleeve rows carry the same equity; collapsing must not sum them."""
    rows = series(store)
    assert len(rows) == len(PATH)
    assert [r[0] for r in rows] == [s for s, _ in PATH]
    assert [r[1] for r in rows] == [e for _, e in PATH]


def test_the_peak_is_not_the_starting_equity(store):
    """The case the module exists for: the account rose before it fell."""
    equities = [e for _, e, _ in series(store)]
    start, peak, last = equities[0], max(equities), equities[-1]

    assert peak > start, "fixture must exercise peak != start"
    since_inception = last / start - 1.0
    from_peak = last / peak - 1.0

    assert since_inception == pytest.approx(-0.00748, abs=1e-4)
    assert from_peak == pytest.approx(-0.04634, abs=1e-4)
    # The whole point: quoting one of these as the other is a 6x misstatement.
    assert abs(from_peak) > 5 * abs(since_inception)


def test_sessions_without_equity_are_skipped_not_zeroed(store):
    """A NULL equity must drop the session, never enter the path as 0.0 —
    a zero would read as a total loss and poison every peak after it."""
    store.conn.execute(
        "INSERT INTO daily (session, symbol, account_equity, ts) "
        "VALUES (?,?,?,?)", ("20260901", "SOXL", None, "2026-01-01T00:00:00Z"))
    store.conn.commit()
    rows = series(store)
    assert "20260901" not in [r[0] for r in rows]
    assert all(r[1] > 0 for r in rows)


def test_the_path_is_ordered_by_session(store):
    sessions = [r[0] for r in series(store)]
    assert sessions == sorted(sessions)
