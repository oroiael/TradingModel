"""
Stage 1 — acceptance tests for the pure strategy core.

These re-check the §2.1-§2.4 arithmetic against hand-computed fixtures. They
are the live-engine counterparts of `phase1/test_spec_engine.py` items §10.2
and §10.3; the equivalence suite then proves the two agree on real data.
"""

from __future__ import annotations

import math

import pytest

from spec_constants import GATE_ATR5_MIN, POS10_TOP_THIRD, round_to_tick
from strategy_core import (
    Bar,
    FeatureHistory,
    entry_limit_price,
    filter_decision,
    gate_decision,
    order_quantity,
    session_stats,
    stop_price,
    target_price,
)


def flat_bars(n=78, start=0, base=100.0):
    return [Bar(start + i, base, base, base, base, 1.0) for i in range(n)]


# ------------------------------------------------------------ session stats
def test_or30_uses_only_the_0930_to_1000_window():
    bars = flat_bars()
    # bars 0..5 are 09:30..09:55 — the opening-range window
    bars[2] = Bar(2, 100.0, 106.0, 100.0, 100.0, 1.0)
    bars[4] = Bar(4, 100.0, 100.0, 96.0, 99.0, 1.0)
    # bar 6 (10:00) must not affect OR30
    bars[6] = Bar(6, 100.0, 130.0, 70.0, 100.0, 1.0)
    st = session_stats(bars)
    assert st.or_high == 106.0 and st.or_low == 96.0
    assert st.or30 == pytest.approx(10.0)


def test_pos10_is_the_close_of_the_0955_bar():
    bars = flat_bars()
    bars[0] = Bar(0, 100.0, 110.0, 90.0, 100.0, 1.0)
    bars[5] = Bar(5, 100.0, 100.0, 100.0, 105.0, 1.0)   # the 09:55 bar closes at 10:00
    bars[6] = Bar(6, 100.0, 100.0, 100.0, 91.0, 1.0)    # the 10:00 bar is too late
    st = session_stats(bars)
    assert st.close10 == 105.0
    assert st.pos10 == pytest.approx(0.75)


def test_pos10_is_one_half_when_the_opening_range_is_degenerate():
    assert session_stats(flat_bars()).pos10 == 0.5


def test_half_day_and_late_open_flags():
    assert session_stats(flat_bars(n=78)).is_half_day is False
    # a 13:00 close: last bar index 41 < 77
    assert session_stats(flat_bars(n=42)).is_half_day is True
    assert session_stats(flat_bars()).late_open is False
    assert session_stats(flat_bars(start=3)).late_open is True


def test_range_pct_is_measured_off_the_session_open():
    bars = flat_bars()
    bars[10] = Bar(10, 100.0, 112.0, 100.0, 100.0, 1.0)
    bars[20] = Bar(20, 100.0, 100.0, 94.0, 100.0, 1.0)
    assert session_stats(bars).range_pct == pytest.approx(18.0)


# ---------------------------------------------------------------- features
def _hist(range_pcts, or30s=None):
    h = FeatureHistory()
    or30s = or30s or [1.0] * len(range_pcts)
    for r, o in zip(range_pcts, or30s):
        bars = flat_bars()
        bars[0] = Bar(0, 100.0, 100.0 + r, 100.0, 100.0, 1.0)
        st = session_stats(bars)
        h._range_pct.append(r)      # direct: the arithmetic under test is the mean
        h._or30.append(o)
    return h


def test_atr5_is_the_mean_of_the_five_prior_sessions():
    h = _hist([4.0, 5.0, 6.0, 7.0, 8.0])
    assert h.atr5() == pytest.approx(6.0)
    h._range_pct.append(20.0)       # a sixth session drops the first
    assert h.atr5() == pytest.approx((5 + 6 + 7 + 8 + 20) / 5)


def test_atr5_is_nan_before_five_sessions():
    assert math.isnan(_hist([6.0] * 4).atr5())


def test_thr80_requires_120_observations():
    assert math.isnan(_hist([6.0] * 119, [3.0] * 119).thr80())
    assert not math.isnan(_hist([6.0] * 120, [3.0] * 120).thr80())


def test_thr80_is_the_80th_percentile_of_the_trailing_504():
    or30s = [float(i) for i in range(1, 505)]
    h = _hist([6.0] * 504, or30s)
    assert h.thr80() == pytest.approx(403.4)          # linear interpolation
    # a 505th observation must drop the oldest: the window becomes 2..504 plus
    # the new value, so the 80th percentile moves up by exactly one rank
    h._or30.append(1000.0)
    assert h.thr80() == pytest.approx(404.4)


# --------------------------------------------------------------- decisions
@pytest.mark.parametrize("atr5,expected", [
    (GATE_ATR5_MIN - 0.01, False), (GATE_ATR5_MIN, True), (10.0, True)])
def test_gate_threshold_is_inclusive(atr5, expected):
    assert gate_decision(atr5, False, False).ok is expected


def test_gate_refuses_half_days_and_late_opens():
    assert gate_decision(10.0, True, False).reason == "scheduled_half_day"
    assert gate_decision(10.0, False, True).reason == "incomplete_session_data"
    assert gate_decision(float("nan"), False, False).reason == "atr5_unavailable"


@pytest.mark.parametrize("or30,pos10,expected", [
    (3.0, 0.2, True),    # narrow open, weak position   -> trade
    (3.0, 0.9, True),    # narrow open, strong position -> trade
    (9.0, 0.9, True),    # wide open, top third         -> trade (V9)
    (9.0, 0.2, False),   # wide open, weak position     -> stand down
])
def test_filter_all_four_combinations(or30, pos10, expected):
    assert filter_decision(or30, 5.0, pos10).ok is expected


def test_filter_boundary_is_inclusive_at_two_thirds():
    assert filter_decision(9.0, 5.0, POS10_TOP_THIRD).ok is True
    assert filter_decision(9.0, 5.0, POS10_TOP_THIRD - 1e-9).ok is False


def test_filter_stands_down_without_enough_history():
    assert filter_decision(3.0, float("nan"), 0.5).reason == "thr80_insufficient_history"


# ------------------------------------------------------------ price and size
def test_levels_match_the_spec_constants():
    assert entry_limit_price(100.0, tick_rounding=False) == pytest.approx(99.0)
    assert target_price(100.0, tick_rounding=False) == pytest.approx(101.0)
    assert stop_price(100.0, tick_rounding=False) == pytest.approx(96.0)


def test_levels_round_to_the_cent_grid_when_live():
    assert entry_limit_price(158.437, tick_rounding=True) == pytest.approx(
        round_to_tick(158.437 * 0.99), abs=1e-12)
    assert entry_limit_price(158.437, True) * 100 == pytest.approx(
        round(158.437 * 0.99 * 100), abs=1e-9)


def test_order_quantity_floors_to_whole_shares_live():
    assert order_quantity(1.0, 75_000.0, 158.41) == 473.0
    assert order_quantity(1.0, 75_000.0, 158.41, whole_shares=False) == pytest.approx(
        75_000.0 / 158.41)
    # §2.4: below one share the sleeve does not trade
    assert order_quantity(1.0, 100.0, 158.41) == 0.0
