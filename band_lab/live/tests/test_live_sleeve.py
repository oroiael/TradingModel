"""
Stage 1 — acceptance tests for the live state machine.

These are the live-engine counterparts of `IMPLEMENTATION_SPEC.md` §10 items
4, 5, 6, 7, 8 and 14, asserted against the object that will actually run
against IBKR rather than against a backtest of it.
"""

from __future__ import annotations

import pytest

from sleeve import (
    START_IDX,
    Bar,
    IntentKind,
    SleeveConfig,
    SleeveState,
    SleeveStateMachine,
)

CAPITAL = 75_000.0
ORDER_KINDS = (IntentKind.PLACE_ENTRY, IntentKind.MODIFY_ENTRY,
               IntentKind.PLACE_BRACKET, IntentKind.FLATTEN)


def cfg(**kw) -> SleeveConfig:
    base = dict(symbol="SOXL", sleeve_capital=CAPITAL,
                tick_rounding=False, whole_shares=False, sizing_basis="limit")
    base.update(kw)
    return SleeveConfig(**base)


def bar(idx, o=100.0, h=None, l=None, c=None):
    return Bar(idx, o, h if h is not None else o, l if l is not None else o,
               c if c is not None else o)


def armed(config=None, highs=None):
    """A sleeve that has passed gate + filter and reached 11:00."""
    sm = SleeveStateMachine(config or cfg())
    sm.begin_session("D", atr5=10.0, is_half_day=False, late_open=False)
    sm.apply_morning_filter(or30=3.0, thr80=5.0, pos10=0.5)
    highs = highs or [100.0] * START_IDX
    for i, h in enumerate(highs):
        sm.on_bar_open(i)
        sm.on_bar_close(bar(i, h=h))
    sm.on_bar_open(START_IDX)
    return sm


# --------------------------------------------------------------- §10.14/2.2
def test_gate_off_day_produces_no_orders():
    sm = SleeveStateMachine(cfg())
    sm.begin_session("D", atr5=5.9, is_half_day=False, late_open=False)
    assert sm.state is SleeveState.GATE_OFF
    for i in range(80):
        sm.on_bar_open(i)
        sm.on_bar_close(bar(i, h=100.0 + i))
    assert sm.working_entry is None
    assert not [x for x in sm.drain_intents() if x.kind in ORDER_KINDS]


def test_stand_down_day_produces_no_orders():
    sm = SleeveStateMachine(cfg())
    sm.begin_session("D", atr5=10.0, is_half_day=False, late_open=False)
    sm.apply_morning_filter(or30=9.0, thr80=5.0, pos10=0.1)
    assert sm.state is SleeveState.STOOD_DOWN
    for i in range(80):
        sm.on_bar_open(i)
        sm.on_bar_close(bar(i, h=100.0 + i))
    assert not [x for x in sm.drain_intents() if x.kind in ORDER_KINDS]


# ------------------------------------------------------------------- §10.5
def test_no_order_intent_before_1100():
    sm = SleeveStateMachine(cfg())
    sm.begin_session("D", atr5=10.0, is_half_day=False, late_open=False)
    sm.apply_morning_filter(or30=3.0, thr80=5.0, pos10=0.5)
    for i in range(START_IDX):
        sm.on_bar_open(i)
        sm.on_bar_close(bar(i, h=100.0 + i))
        assert not [x for x in sm.drain_intents() if x.kind in ORDER_KINDS]
        assert sm.working_entry is None
    sm.on_bar_open(START_IDX)
    placed = [x for x in sm.drain_intents() if x.kind is IntentKind.PLACE_ENTRY]
    assert len(placed) == 1 and placed[0].bar_idx == START_IDX


def test_the_1100_limit_is_priced_off_the_morning_high():
    sm = armed(highs=[100.0 + i for i in range(START_IDX)])   # high 117 at bar 17
    assert sm.anchor == pytest.approx(117.0)
    assert sm.working_entry.limit_px == pytest.approx(117.0 * 0.99)


# ------------------------------------------------------------------- §10.4
def test_anchor_never_decreases_and_the_limit_never_moves_down():
    sm = armed()
    seen = [sm.working_entry.limit_px]
    for i, h in enumerate([101, 103, 102, 99, 105, 104], start=START_IDX):
        sm.on_bar_open(i)
        sm.on_bar_close(bar(i, h=float(h)))
        seen.append(sm.working_entry.limit_px)
    assert sm.anchor == pytest.approx(105.0)
    assert seen == sorted(seen)
    assert sm.working_entry.limit_px == pytest.approx(105.0 * 0.99)


def test_a_rising_high_emits_exactly_one_modify():
    sm = armed()
    sm.drain_intents()
    sm.on_bar_open(START_IDX)
    sm.on_bar_close(bar(START_IDX, h=110.0))
    kinds = [x.kind for x in sm.drain_intents()]
    assert kinds == [IntentKind.MODIFY_ENTRY]
    sm.on_bar_open(START_IDX + 1)
    sm.on_bar_close(bar(START_IDX + 1, h=109.0))       # lower high: no modify
    assert sm.drain_intents() == []


# ------------------------------------------------------------------- §10.6
def test_bracket_is_emitted_on_the_entry_fill():
    sm = armed()
    sm.drain_intents()
    sm.on_entry_fill(99.0, START_IDX)
    intents = sm.drain_intents()
    assert [x.kind for x in intents] == [IntentKind.PLACE_BRACKET]
    assert intents[0].target_px == pytest.approx(99.0 * 1.01)
    assert intents[0].stop_px == pytest.approx(99.0 * 0.96)
    assert sm.working_entry is None          # no entry rests while in position


def test_entry_quantity_is_sized_off_the_limit_price():
    sm = armed()
    assert sm.working_entry.qty == pytest.approx(CAPITAL / (100.0 * 0.99))
    sm.on_entry_fill(90.0, START_IDX)        # a gap-through fill
    # §2.4 sizes off the limit, so the quantity does not change with the fill
    assert sm.trades == []
    sm.on_exit_fill(90.0, START_IDX + 1, "target")
    assert sm.trades[0].qty == pytest.approx(CAPITAL / (100.0 * 0.99))


def test_fill_priced_sizing_is_available_for_backtest_parity():
    sm = armed(cfg(sizing_basis="fill"))
    sm.on_entry_fill(90.0, START_IDX)
    sm.on_exit_fill(90.0, START_IDX + 1, "target")
    assert sm.trades[0].qty == pytest.approx(CAPITAL / 90.0)


# ------------------------------------------------------------------- §10.7
def test_second_stop_out_ends_the_day():
    sm = armed()
    for n in range(2):
        sm.on_entry_fill(99.0, START_IDX + n)
        sm.on_exit_fill(99.0 * 0.96, START_IDX + n, "stop")
    assert sm.stop_outs == 2
    assert sm.state is SleeveState.DONE
    assert sm.working_entry is None
    assert [x.reason for x in sm.drain_intents() if x.kind is IntentKind.DORMANT] \
        == ["counters_exhausted"]
    # and nothing re-arms it
    for i in range(START_IDX + 2, 70):
        sm.on_bar_open(i)
        sm.on_bar_close(bar(i, h=200.0))
    assert sm.working_entry is None


# ------------------------------------------------- V19 day profit stop (dev)
def test_the_default_has_no_upward_truncation():
    """§12 truncates a day downward twice and upward never. Production keeps it
    that way: the live engine builds `SleeveConfig` without the field at all."""
    assert cfg().day_profit_stop is None
    sm = armed()
    for n in range(5):
        sm.on_entry_fill(99.0, START_IDX + n)
        sm.on_exit_fill(99.0 * 1.01, START_IDX + n + 1, "target")
    assert sm.pnl == pytest.approx(0.05)      # five winners, never cut short
    assert [x.reason for x in sm.drain_intents()
            if x.kind is IntentKind.DORMANT] == ["counters_exhausted"]


def test_one_target_ends_the_day_at_a_one_percent_stop():
    """V19's central mechanism: a target pays exactly `f x target_pct`, so a
    +1% threshold and a +0.5% threshold are the same rule — stop after the
    first winner. There is no day that lands between them."""
    sm = armed(cfg(day_profit_stop=0.01))
    sm.on_entry_fill(99.0, START_IDX)
    sm.on_exit_fill(99.0 * 1.01, START_IDX + 1, "target")
    assert sm.pnl == pytest.approx(0.01)
    assert sm.state is SleeveState.DONE
    assert sm.working_entry is None
    assert [x.reason for x in sm.drain_intents()
            if x.kind is IntentKind.DORMANT] == ["day_profit_stop"]


def test_the_epsilon_catches_a_target_that_floats_a_hair_under():
    """`f x target_pct` lands on 0.009999999999999998 about as often as on 0.01.
    Without the epsilon, "stop at +1%" would mean "after one winner" or "after
    two" depending on rounding noise in the entry price — a 100 bp/day swing
    decided by nothing."""
    sm = armed(cfg(day_profit_stop=0.01))
    sm.pnl = 0.01 - 1e-12
    assert sm.day_profit_reached


def test_a_threshold_above_one_target_needs_two():
    sm = armed(cfg(day_profit_stop=0.015))
    sm.on_entry_fill(99.0, START_IDX)
    sm.on_exit_fill(99.0 * 1.01, START_IDX + 1, "target")
    assert sm.state is SleeveState.ARMED          # +1% is not yet +1.5%
    sm.on_entry_fill(99.0, START_IDX + 2)
    sm.on_exit_fill(99.0 * 1.01, START_IDX + 3, "target")
    assert sm.state is SleeveState.DONE


def test_a_losing_day_never_reaches_the_profit_stop():
    """The finding the sweep turns on: the rule can only fire on a day that is
    already winning, so it does nothing at all to the days that hurt. Worst-day
    was identical at every threshold tested, in both sleeves."""
    sm = armed(cfg(day_profit_stop=0.005))
    sm.on_entry_fill(99.0, START_IDX)
    sm.on_exit_fill(99.0 * 0.96, START_IDX, "stop")
    assert sm.pnl < 0.0
    assert not sm.day_profit_reached
    assert sm.state is SleeveState.ARMED


@pytest.mark.parametrize("bad", [0.0, -0.01])
def test_a_non_positive_profit_stop_is_refused(bad):
    with pytest.raises(ValueError, match="day_profit_stop"):
        cfg(day_profit_stop=bad)


def test_first_stop_out_re_arms():
    sm = armed()
    sm.on_entry_fill(99.0, START_IDX)
    sm.on_exit_fill(99.0 * 0.96, START_IDX, "stop")
    assert sm.stop_outs == 1 and sm.state is SleeveState.ARMED
    assert sm.working_entry is not None


# ------------------------------------------------------------------- §10.8
def test_fifth_fill_ends_the_day():
    sm = armed()
    for n in range(5):
        assert sm.working_entry is not None
        sm.on_entry_fill(99.0, START_IDX + n)
        sm.on_exit_fill(99.0 * 1.01, START_IDX + n + 1, "target")
    assert sm.fills == 5
    assert sm.state is SleeveState.DONE
    assert sm.working_entry is None


# ------------------------------------------------------------- V2 / §2.5
def test_exit_re_arms_immediately_not_at_the_next_bar_close():
    """Instant re-entry below the standing session high is +47.9 bp of the
    65.6 (V2). The re-arm must happen on the exit event."""
    sm = armed()
    sm.on_entry_fill(99.0, START_IDX)
    sm.drain_intents()
    sm.on_exit_fill(99.0 * 1.01, START_IDX + 1, "target")
    kinds = [x.kind for x in sm.drain_intents()]
    assert IntentKind.PLACE_ENTRY in kinds
    assert sm.working_entry.limit_px == pytest.approx(100.0 * 0.99)


def test_the_re_armed_limit_uses_the_high_made_while_in_position():
    sm = armed()
    sm.on_entry_fill(99.0, START_IDX)
    sm.on_bar_open(START_IDX + 1)
    sm.on_bar_close(bar(START_IDX + 1, h=120.0))     # new high while holding
    sm.on_exit_fill(100.0, START_IDX + 2, "target")
    assert sm.working_entry.limit_px == pytest.approx(120.0 * 0.99)


# ------------------------------------------------------------------- §2.4
def test_sub_one_share_sizing_goes_dormant_instead_of_trading():
    sm = armed(cfg(sleeve_capital=50.0, whole_shares=True))
    assert sm.working_entry is None
    assert sm.state is SleeveState.DONE
    assert [x.reason for x in sm.drain_intents()
            if x.kind is IntentKind.DORMANT] == ["order_qty_below_one_share"]


# ------------------------------------------------------------------- §2.8
def test_flatten_closes_the_position_and_cancels_everything():
    sm = armed()
    sm.on_entry_fill(99.0, START_IDX)
    sm.drain_intents()
    trade = sm.flatten(97.0, 76)
    kinds = [x.kind for x in sm.drain_intents()]
    assert IntentKind.CANCEL_BRACKET in kinds and IntentKind.FLATTEN in kinds
    assert trade.outcome == "flatten" and trade.exit_px == 97.0
    assert sm.state is SleeveState.CLOSED and not sm.in_position


def test_flatten_cancels_a_resting_entry_when_flat():
    sm = armed()
    sm.drain_intents()
    assert sm.flatten(100.0, 76) is None
    assert [x.kind for x in sm.drain_intents()] == [IntentKind.CANCEL_ENTRY]
    assert sm.working_entry is None and sm.state is SleeveState.CLOSED


def test_pnl_is_a_fraction_of_sleeve_capital():
    sm = armed()
    sm.on_entry_fill(100.0, START_IDX)
    sm.on_exit_fill(101.0, START_IDX + 1, "target")
    # qty was sized off the 99.0 limit, so the return is qty * 1.0 / capital
    assert sm.pnl == pytest.approx((CAPITAL / 99.0) * 1.0 / CAPITAL)
