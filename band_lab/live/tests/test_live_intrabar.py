"""
Tests for the dual-granularity replay.

The load-bearing one is `test_degenerate_case_reproduces_the_5min_replay`: fed
the 5-minute bars as both the decision stream and the fill stream, this module
must be indistinguishable from `replay.py`. Without that, a 1-minute result
could differ for reasons that have nothing to do with resolution.
"""

from __future__ import annotations

import pandas as pd
import pytest

from intrabar import (
    TARGET_DELAY,
    aggregate,
    replay_session_intrabar,
    replay_symbol_intrabar,
)
from replay import backtest_config, load_sessions, replay_symbol
from sleeve import START_IDX, Bar, SleeveConfig, SleeveStateMachine


# ------------------------------------------------------------- aggregation
def test_aggregate_builds_ohlc_correctly():
    fine = [Bar(0, 10.0, 11.0, 9.5, 10.5, 100),
            Bar(1, 10.5, 12.0, 10.0, 11.5, 200),
            Bar(2, 11.5, 11.8, 8.0, 9.0, 300),
            Bar(3, 9.0, 9.5, 8.5, 9.2, 50),
            Bar(4, 9.2, 9.9, 9.1, 9.8, 60),
            Bar(5, 9.8, 10.0, 9.7, 9.9, 70)]
    out = aggregate(fine, 5)
    assert len(out) == 2
    assert out[0] == Bar(0, 10.0, 12.0, 8.0, 9.8, 710)
    assert out[1] == Bar(1, 9.8, 10.0, 9.7, 9.9, 70)


def test_aggregate_indexes_by_decision_bar():
    fine = [Bar(j, 10.0, 10.0, 10.0, 10.0, 1) for j in range(0, 20)]
    assert [b.idx for b in aggregate(fine, 5)] == [0, 1, 2, 3]


# --------------------------------------------------------------- degenerate
def _cfg():
    return SleeveConfig(symbol="SOXL", sleeve_capital=75_000.0,
                        tick_rounding=False, whole_shares=False,
                        sizing_basis="limit")


def _armed(sm):
    sm.begin_session("D", atr5=10.0, is_half_day=False, late_open=False)
    sm.apply_morning_filter(or30=3.0, thr80=5.0, pos10=0.5)
    return sm


def test_one_to_one_fill_bars_behave_like_the_plain_replay():
    """per_decision_bar=1 means the fill stream *is* the decision stream.

    Also a miniature of S10: the target exit on the second bar is followed by a
    re-entry in that same bar, at that bar's open.
    """
    bars = [Bar(i, 100.0, 100.0, 100.0, 100.0) for i in range(START_IDX)]
    bars.append(Bar(START_IDX, 100.0, 100.0, 98.0, 99.0))     # touches 99 limit
    bars.append(Bar(START_IDX + 1, 99.0, 101.0, 99.0, 100.0))  # hits the target
    sm = _armed(SleeveStateMachine(_cfg()))
    replay_session_intrabar(bars, bars, sm, 1)

    assert sm.trades[0].outcome == "target"
    assert sm.trades[0].entry_px == pytest.approx(99.0)
    assert sm.trades[0].exit_px == pytest.approx(99.99)
    # the same-bar re-entry, priced at the bar open
    assert sm.fills == 2
    assert sm.trades[1].entry_bar == START_IDX + 1 == sm.trades[0].exit_bar
    assert sm.trades[1].entry_px == pytest.approx(99.0)
    assert sm.trades[1].outcome == "flatten"


def test_target_delay_fill_bar_allows_a_faster_exit():
    """At finer resolution the target need not wait a full decision bar."""
    dbars = [Bar(i, 100.0, 100.0, 100.0, 100.0) for i in range(START_IDX)]
    dbars.append(Bar(START_IDX, 100.0, 101.0, 98.0, 100.5))
    fine = [Bar(j, 100.0, 100.0, 100.0, 100.0) for j in range(START_IDX * 5)]
    fine += [Bar(START_IDX * 5, 100.0, 100.0, 98.0, 99.0),      # entry at 99
             Bar(START_IDX * 5 + 1, 99.0, 101.0, 99.0, 100.5)]  # target 99.99

    for delay, expect_fills in (("decision_bar", 0), ("fill_bar", 1)):
        sm = _armed(SleeveStateMachine(_cfg()))
        replay_session_intrabar(dbars, fine, sm, 5, target_delay=delay)
        closed = [t for t in sm.trades if t.outcome == "target"]
        assert len(closed) == expect_fills, delay


@pytest.mark.parametrize("delay", TARGET_DELAY)
def test_target_delay_values_are_accepted(delay):
    bars = [Bar(i, 100.0, 100.0, 100.0, 100.0) for i in range(START_IDX + 2)]
    sm = _armed(SleeveStateMachine(_cfg()))
    replay_session_intrabar(bars, bars, sm, 1, target_delay=delay)


def test_bad_switches_are_rejected():
    bars = [Bar(0, 1.0, 1.0, 1.0, 1.0)]
    sm = _armed(SleeveStateMachine(_cfg()))
    with pytest.raises(ValueError):
        replay_session_intrabar(bars, bars, sm, 1, fill_model="nope")
    with pytest.raises(ValueError):
        replay_session_intrabar(bars, bars, sm, 1, target_delay="nope")


# --------------------------------------------------------------------- slow
@pytest.mark.slow
@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_degenerate_case_reproduces_the_5min_replay(symbol):
    """Fed 5-minute bars as both streams, this must equal `replay.py` exactly.

    This is what licenses reading a 1-minute run as a resolution effect rather
    than as an unrelated difference between two harnesses.
    """
    sessions = load_sessions(symbol)
    _, ref_on, ref_tr = replay_symbol(symbol, backtest_config(symbol),
                                      sessions=sessions)
    on, tr = replay_symbol_intrabar(symbol, sessions, 1)

    assert list(on.index) == list(ref_on.index)
    assert float((on - ref_on).abs().max()) < 1e-12
    assert len(tr) == len(ref_tr)
    for col in ("entry_px", "exit_px", "qty", "ret"):
        assert float((tr[col] - ref_tr[col]).abs().max()) < 1e-9, col
    assert (tr["outcome"].to_numpy() == ref_tr["outcome"].to_numpy()).all()


# ------------------------------------------------------------- price scales
def test_mismatched_price_scales_raise_rather_than_produce_a_table():
    """A split-adjustment mismatch must be fatal, not silently plausible.

    Regression for the 2026-07 fetch: IBKR's 1-minute data is already
    split-adjusted, the repo's 5-minute CSV is not, and adjusting the former
    again put the fill stream at 1/15 the decision scale. Entries then filled
    at the low scale while the 15:55 flatten booked at the high one, which
    reads as an enormous edge instead of as an error.
    """
    from intrabar import PriceScaleError

    dbars = [Bar(i, 45.0, 45.0, 45.0, 45.0) for i in range(START_IDX + 2)]
    fine = [Bar(j, 3.0, 3.0, 3.0, 3.0) for j in range((START_IDX + 2) * 5)]
    sm = _armed(SleeveStateMachine(_cfg()))
    with pytest.raises(PriceScaleError, match="split"):
        replay_session_intrabar(dbars, fine, sm, 5)


def test_matching_price_scales_pass_the_guard():
    dbars = [Bar(i, 45.0, 45.2, 44.8, 45.0) for i in range(START_IDX + 2)]
    fine = [Bar(j, 45.0, 45.1, 44.9, 45.0) for j in range((START_IDX + 2) * 5)]
    sm = _armed(SleeveStateMachine(_cfg()))
    replay_session_intrabar(dbars, fine, sm, 5)     # must not raise


def test_one_minute_loader_does_not_split_adjust_by_default(tmp_path):
    """IBKR data arrives adjusted; the 5-minute repo files do not."""
    from intrabar import load_1min_sessions

    path = tmp_path / "SOXL_1min.csv"
    rows = ["Date,Open,High,Low,Close,Volume"]
    for m in range(3):
        rows.append(f"20210216 09:{30 + m}:00 America/New_York,45.0,45.0,45.0,45.0,10")
    path.write_text("\n".join(rows) + "\n")

    plain = load_1min_sessions("SOXL", root=str(tmp_path), path=str(path))
    assert plain[0][1][0].close == pytest.approx(45.0)

    adjusted = load_1min_sessions("SOXL", root=str(tmp_path), path=str(path),
                                  split_adjust=True)
    assert adjusted[0][1][0].close == pytest.approx(3.0)
