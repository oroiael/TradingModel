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
    needs_split_adjustment,
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


# ------------------------------------------------------- split-basis detect
def _frame(pre_close, post_close):
    """Minimal 1-minute frame straddling SOXL's 2021-03-02 split."""
    return pd.DataFrame({
        "date": [pd.Timestamp("2021-02-16"), pd.Timestamp("2021-03-03")],
        "Close": [pre_close, post_close]})


def test_detects_raw_series_needs_adjusting():
    """Raw SOXL sits ~15x higher before the split — divide it."""
    assert needs_split_adjustment(_frame(710.0, 42.0), "SOXL") is True


def test_detects_already_adjusted_series():
    """An adjusted series sits in the same range either side — leave it alone.

    This is the S12 case: dividing it a second time misprices every pre-split
    session by 15x, and the 5-minute parity gate then reports ~44.
    """
    assert needs_split_adjustment(_frame(47.34, 42.0), "SOXL") is False


def test_symbol_without_splits_is_never_adjusted():
    """SOXS has no SPLIT_ADJUSTMENTS entry; its 5-minute file is back-adjusted."""
    assert needs_split_adjustment(_frame(64800.0, 42.0), "SOXS") is False


def test_falls_back_to_the_documented_convention_without_both_sides():
    """No post-split rows means no ratio to measure; assume the raw convention
    `fetch_1min.py` documents rather than guessing."""
    df = pd.DataFrame({"date": [pd.Timestamp("2021-02-16")], "Close": [710.0]})
    assert needs_split_adjustment(df, "SOXL") is True


# --------------------------------------------------------------- CLI wiring
def test_cli_failure_branch_does_not_crash(monkeypatch):
    """Regression: a merge once dropped --force from the parser while leaving
    `args.force` in main(), so any failing check raised AttributeError instead
    of reporting the failure. Cheap to assert, and it fails loudly."""
    import intrabar

    monkeypatch.setattr(intrabar, "parity_check", lambda *a, **k: 1)
    monkeypatch.setattr("sys.argv", ["intrabar.py", "--symbol", "SOXL"])
    assert intrabar.main() == 1


def test_cli_check_only_returns_the_check_result(monkeypatch):
    import intrabar

    monkeypatch.setattr(intrabar, "parity_check", lambda *a, **k: 0)
    monkeypatch.setattr(intrabar, "resolution_report",
                        lambda *a, **k: pytest.fail("must not run under --check"))
    monkeypatch.setattr("sys.argv", ["intrabar.py", "--symbol", "SOXL", "--check"])
    assert intrabar.main() == 0


@pytest.mark.slow
@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_parity_check_runs_on_the_real_files(symbol):
    """Regression: the same merge left `split_adjust` referenced in
    parity_check and resolution_report after the parameter was removed, so
    both raised NameError on any real invocation."""
    from intrabar import parity_check

    assert parity_check(symbol, start=pd.Timestamp("2026-06-01")) in (0, 1)
