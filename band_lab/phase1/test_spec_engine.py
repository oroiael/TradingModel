"""
Phase 1 — acceptance tests for the clean-room engine.

Covers the correctness and risk items of IMPLEMENTATION_SPEC.md §10 that
are in scope for a backtest harness:

    §10.1  clean-room parity with the research engine   -> test_parity_*
    §10.2  gate arithmetic (ATR5 by hand)               -> test_atr5_*
    §10.3  filter arithmetic, all four combinations     -> test_filter_*
    §10.4  anchor never decreases within a session      -> test_anchor_*
    §10.5  no order with timestamp < 11:00              -> test_no_order_before_1100
    §10.6  bracket live within one event loop of fill   -> test_bracket_live_on_entry_bar
    §10.7  no entry after the 2nd stop-out              -> test_stop_breaker
    §10.8  no entry after the 5th fill                  -> test_fill_cap
    §10.13 config with f = 1.5 rejected at startup      -> test_config_*
    §10.14 gate-OFF day produces zero orders            -> test_gate_off_no_orders

§10.9–12, 15–16 exercise the live IBKR engine (flatten verification,
crash/restart reconciliation, disconnect, watchdog, replay, weekly report)
and belong to Phase 2; they are not simulable here and are deliberately
absent rather than faked.

Run:  python3 -m pytest band_lab/phase1 -v
      python3 -m pytest band_lab/phase1 -v -m "not slow"   (skip the 30s parity run)
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BAND_LAB = os.path.dirname(HERE)
ROOT = os.path.dirname(BAND_LAB)
for p in (HERE, BAND_LAB, os.path.join(ROOT, "cycle_lab")):
    if p not in sys.path:
        sys.path.insert(0, p)

import dataclasses as dc

from spec_constants import (
    ConfigError, GATE_ATR5_MIN, MAX_FILLS, MAX_STOPS, POS10_TOP_THIRD,
    bar_index, bar_time, round_to_tick,
)
from spec_engine import (
    RESEARCH_COMPAT, SPEC_LITERAL, EngineConfig, Session, build_sessions,
    daily_features, filter_on, gate_on, simulate_session, run_sleeve,
)

DAY = pd.Timestamp("2024-06-03")
FULL_DAY_BARS = 78          # 09:30 .. 15:55 starts
START_I = bar_index("11:00")


# ------------------------------------------------------------- fixtures
def make_session(ohlc: list[tuple], date=DAY, first_idx: int = 0) -> Session:
    """Build a Session from a list of (open, high, low, close) tuples."""
    a = np.asarray(ohlc, dtype=float)
    return Session(date=date, idx=np.arange(first_idx, first_idx + len(a)),
                   o=a[:, 0], h=a[:, 1], l=a[:, 2], c=a[:, 3],
                   v=np.ones(len(a)))


def flat_day(price: float = 100.0, n: int = FULL_DAY_BARS) -> list[tuple]:
    return [(price, price, price, price)] * n


def bars_to_frame(sessions: list[list[tuple]], dates: list[pd.Timestamp]
                  ) -> pd.DataFrame:
    rows = []
    for date, ohlc in zip(dates, sessions):
        for i, (o, h, l, c) in enumerate(ohlc):
            rows.append({"dt": date + pd.Timedelta(minutes=5 * i + 570),
                         "date": date, "Open": o, "High": h, "Low": l,
                         "Close": c, "Volume": 1.0})
    return pd.DataFrame(rows)


CFG = SPEC_LITERAL                       # the spec as amended 2026-07
MONTHLY = dc.replace(CFG, thr80_refresh="monthly")   # the rejected S1 reading


# ================================================== §10.13 config validation
def test_config_rejects_f_above_one():
    with pytest.raises(ConfigError, match="leverage"):
        EngineConfig(f=1.5)


def test_config_rejects_f_at_zero():
    with pytest.raises(ConfigError):
        EngineConfig(f=0.0)


def test_config_accepts_the_validated_f_range():
    for f in (0.05, 0.5, 1.0):
        assert EngineConfig(f=f).f == f


def test_config_rejects_w_outside_plateau():
    for w in (0.3, 0.9):
        with pytest.raises(ConfigError, match="plateau"):
            EngineConfig(w=w)


@pytest.mark.parametrize("kw", [
    dict(gate_atr5_min=5.0), dict(dip_pct=0.02), dict(target_pct=0.015),
    dict(stop_pct=0.03), dict(max_fills=6), dict(max_stops=3),
    dict(start_time="10:30"),
])
def test_config_rejects_strategy_parameter_changes(kw):
    with pytest.raises(ConfigError, match="strategy change"):
        EngineConfig(**kw)


def test_config_rejects_shorting_and_overnight():
    with pytest.raises(ConfigError, match="short"):
        EngineConfig(allow_short=True)
    with pytest.raises(ConfigError, match="overnight"):
        EngineConfig(allow_overnight=True)


# ======================================================== §2.1 bar indexing
def test_bar_index_matches_spec_examples():
    # §2.1: "Bar index 0 is the 09:30 bar. Bar 18 is the 11:00 bar."
    assert bar_index("09:30") == 0
    assert bar_index("11:00") == 18
    assert bar_time(0) == "09:30" and bar_time(18) == "11:00"
    assert bar_index("15:55") == 77


def test_round_to_tick():
    assert round_to_tick(13.3339) == pytest.approx(13.33)
    assert round_to_tick(13.3350) == pytest.approx(13.34)
    assert round_to_tick(158.4149) == pytest.approx(158.41)


# ================================================ §10.2 gate arithmetic (ATR5)
def test_atr5_matches_hand_computation_over_five_sessions():
    """Five prior sessions with ranges 5,6,7,8,9 % -> ATR5 on day 6 = 7.0."""
    dates = pd.bdate_range("2024-01-02", periods=6)
    sessions, hand = [], [5.0, 6.0, 7.0, 8.0, 9.0, 4.0]
    for pct in hand:
        o = 100.0
        hi, lo = o * (1 + pct / 200), o * (1 - pct / 200)   # range = pct% of open
        sessions.append([(o, hi, lo, o)] + flat_day(o, FULL_DAY_BARS - 1))
    d = daily_features(build_sessions(bars_to_frame(sessions, dates), CFG), CFG)
    assert d["range_pct"].round(6).tolist() == pytest.approx(hand, abs=1e-9)
    # ATR5 uses only the 5 completed sessions BEFORE d, and no data from d.
    assert np.isnan(d["atr5"].iloc[4])                       # only 4 priors
    assert d["atr5"].iloc[5] == pytest.approx(np.mean(hand[:5]))   # 7.0
    assert d["atr5"].iloc[5] == pytest.approx(7.0)


def test_gate_uses_only_prior_sessions():
    """Changing day d's own range must not move day d's ATR5."""
    dates = pd.bdate_range("2024-01-02", periods=6)
    base = [[(100.0, 103.0, 97.0, 100.0)] + flat_day(100.0, 77) for _ in range(6)]
    d1 = daily_features(build_sessions(bars_to_frame(base, dates), CFG), CFG)
    bumped = [list(s) for s in base]
    bumped[5][0] = (100.0, 180.0, 20.0, 100.0)
    d2 = daily_features(build_sessions(bars_to_frame(bumped, dates), CFG), CFG)
    assert d1["atr5"].iloc[5] == pytest.approx(d2["atr5"].iloc[5])


@pytest.mark.parametrize("atr5,expected", [
    (5.99, False), (6.0, True), (6.01, True), (float("nan"), False)])
def test_gate_threshold(atr5, expected):
    row = pd.Series({"atr5": atr5, "is_half_day": False, "late_open": False})
    assert gate_on(row, CFG)[0] is expected


def test_gate_rejects_scheduled_half_day():
    row = pd.Series({"atr5": 12.0, "is_half_day": True, "late_open": False})
    ok, why = gate_on(row, CFG)
    assert ok is False and why == "scheduled_half_day"
    # ...but the research-compat reading trades it
    assert gate_on(row, RESEARCH_COMPAT)[0] is True


# ============================================== §10.3 filter arithmetic (4 cells)
@pytest.mark.parametrize("or30,pos10,expected,label", [
    (4.0, 0.90, True,  "narrow OR, strong pos10 -> proceed"),
    (4.0, 0.10, True,  "narrow OR, weak pos10   -> proceed"),
    (6.0, 0.90, True,  "wide OR,   strong pos10 -> proceed (violent up-morning)"),
    (6.0, 0.10, False, "wide OR,   weak pos10   -> STAND DOWN"),
])
def test_filter_all_four_combinations(or30, pos10, expected, label):
    row = pd.Series({"or30": or30, "pos10": pos10, "thr80": 5.0})
    assert filter_on(row, CFG)[0] is expected, label


def test_filter_boundary_is_inclusive_at_two_thirds():
    # §2.3 stands down only if pos10 < 2/3, so exactly 2/3 proceeds.
    wide = {"or30": 6.0, "thr80": 5.0}
    assert filter_on(pd.Series({**wide, "pos10": POS10_TOP_THIRD}), CFG)[0] is True
    assert filter_on(pd.Series({**wide, "pos10": POS10_TOP_THIRD - 1e-9}), CFG)[0] is False
    # and only if OR30 >= thr80, so exactly at the threshold can stand down
    assert filter_on(pd.Series({"or30": 5.0, "thr80": 5.0, "pos10": 0.1}), CFG)[0] is False
    assert filter_on(pd.Series({"or30": 4.999, "thr80": 5.0, "pos10": 0.1}), CFG)[0] is True


def test_filter_stands_down_when_history_is_insufficient():
    # §2.1: "Requires >=120 prior observations; if fewer, the sleeve does not trade."
    row = pd.Series({"or30": 4.0, "pos10": 0.9, "thr80": float("nan")})
    ok, why = filter_on(row, CFG)
    assert ok is False and why == "thr80_insufficient_history"


def test_thr80_requires_120_observations_and_uses_only_prior_sessions():
    n = 200
    dates = pd.bdate_range("2022-01-03", periods=n)
    rng = np.random.default_rng(0)
    sessions = []
    for r in rng.uniform(2.0, 10.0, n):
        o = 100.0
        sessions.append([(o, o * (1 + r / 200), o * (1 - r / 200), o)]
                        + flat_day(o, FULL_DAY_BARS - 1))
    # §2.1 (as amended): the threshold appears the moment the 120th prior
    # observation exists, and is refreshed every session thereafter.
    daily = daily_features(build_sessions(bars_to_frame(sessions, dates), CFG), CFG)
    assert daily["thr80"].iloc[:120].isna().all()
    assert daily["thr80"].iloc[120:].notna().all()
    # The rejected monthly reading instead waits for the FIRST SESSION OF THE
    # MONTH on or after that point, leaving the sleeve dark in between.
    monthly = daily_features(build_sessions(bars_to_frame(sessions, dates),
                                            MONTHLY), MONTHLY)
    assert monthly["thr80"].iloc[:120].isna().all()
    first_valid = monthly["thr80"].notna().idxmax()
    assert first_valid > monthly.index[120]
    assert first_valid == monthly.index[
        monthly.index.to_period("M") == first_valid.to_period("M")][0]
    assert monthly["thr80"].loc[first_valid:].notna().all()


def test_thr80_refreshes_every_session():
    """§2.1 as amended 2026-07 — daily, not held constant within the month.

    This is the cadence the validated series was produced with; see
    PHASE1_PARITY.md §3 S1.
    """
    n = 400
    dates = pd.bdate_range("2022-01-03", periods=n)
    rng = np.random.default_rng(1)
    sessions = []
    for r in rng.uniform(2.0, 10.0, n):
        o = 100.0
        sessions.append([(o, o * (1 + r / 200), o * (1 - r / 200), o)]
                        + flat_day(o, FULL_DAY_BARS - 1))
    frame = bars_to_frame(sessions, dates)
    daily = daily_features(build_sessions(frame, CFG), CFG)["thr80"].dropna()
    monthly = daily_features(build_sessions(frame, MONTHLY),
                             MONTHLY)["thr80"].dropna()
    # the spec cadence moves within a month...
    assert daily.groupby(daily.index.to_period("M")).nunique().max() > 1
    # ...and the rejected reading holds exactly one value per calendar month
    assert (monthly.groupby(monthly.index.to_period("M")).nunique() == 1).all()
    # the engine default is the spec cadence, not the rejected one
    assert SPEC_LITERAL.thr80_refresh == "daily"
    assert RESEARCH_COMPAT.thr80_refresh == "daily"


def test_backtest_does_not_model_the_tick_grid_by_default():
    """RESOLVED 2026-07: the live engine rounds to the cent grid (§2.5/§2.6);
    the backtest does not, and the difference is held as unbanked
    conservatism rather than booked as edge. See PHASE1_PARITY.md §3 S5."""
    assert SPEC_LITERAL.tick_rounding is False
    assert RESEARCH_COMPAT.tick_rounding is False
    bars = flat_day(100.0, START_I) + [(100.0, 100.0, 98.0, 99.0)]
    bars += flat_day(99.0, FULL_DAY_BARS - len(bars))
    # 99.0 is already on the grid; use an anchor that is not
    bars = [(100.004, 100.004, 100.004, 100.004)] * START_I + bars[START_I:]
    plain = simulate_session(make_session(bars), CFG)
    rounded = simulate_session(make_session(bars), dc.replace(CFG, tick_rounding=True))
    assert plain.anchor_updates[0][2] == pytest.approx(100.004 * 0.99)
    assert rounded.anchor_updates[0][2] == pytest.approx(99.00)


# =========================================================== §2.1 OR / pos10
def test_or30_and_pos10_from_the_0930_to_1000_window_only():
    """OR window is the six bars 09:30..09:55; pos10 is the 10:00 print."""
    ohlc = [(100.0, 102.0, 99.0, 101.0),      # 09:30
            (101.0, 103.0, 100.0, 102.0),     # 09:35
            (102.0, 104.0, 101.0, 103.0),     # 09:40  <- OR high 104
            (103.0, 103.5, 98.0, 99.0),       # 09:45  <- OR low  98
            (99.0, 100.0, 98.5, 99.5),        # 09:50
            (99.5, 101.0, 99.0, 100.5)]       # 09:55  close at 10:00 = 100.5
    ohlc += [(500.0, 900.0, 10.0, 500.0)] * (FULL_DAY_BARS - 6)   # must be ignored
    d = daily_features(build_sessions(bars_to_frame([ohlc], [DAY]), CFG), CFG)
    assert d["or_high"].iloc[0] == pytest.approx(104.0)
    assert d["or_low"].iloc[0] == pytest.approx(98.0)
    assert d["or30"].iloc[0] == pytest.approx((104.0 - 98.0) / 100.0 * 100)
    assert d["pos10"].iloc[0] == pytest.approx((100.5 - 98.0) / (104.0 - 98.0))


def test_pos10_is_one_half_when_the_opening_range_is_degenerate():
    # §2.1: "If OR_high == OR_low, use 0.5."
    d = daily_features(build_sessions(bars_to_frame([flat_day()], [DAY]), CFG), CFG)
    assert d["pos10"].iloc[0] == pytest.approx(0.5)
    assert d["or30"].iloc[0] == pytest.approx(0.0)


# =============================== §10.4 anchor monotonicity / §10.5 no early order
def test_anchor_never_decreases_across_a_rising_then_falling_high():
    """§2.5.3: the limit price never moves down."""
    bars = flat_day(100.0, START_I)                     # 09:30..10:55 flat
    rise = [(100.0 + k, 101.0 + k, 99.5 + k, 100.0 + k) for k in range(10)]
    fall = [(109.0 - k, 110.0 - k, 108.0 - k, 109.0 - k) for k in range(10)]
    bars += rise + fall
    bars += flat_day(99.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), dc.replace(CFG, tick_rounding=False))
    anchors = [a for _, a, _ in r.anchor_updates]
    limits = [lp for _, _, lp in r.anchor_updates]
    assert anchors == sorted(anchors), "anchor decreased within the session"
    assert limits == sorted(limits), "resting limit moved down"
    assert max(anchors) == pytest.approx(110.0)         # peak of the rise
    assert all(lp == pytest.approx(a * 0.99) for a, lp in zip(anchors, limits))


def test_anchor_at_activation_excludes_the_forming_bar():
    """§2.5.1: the anchor uses completed bars only, so bar 18's own high
    cannot set the limit that bar 18 trades against."""
    bars = flat_day(100.0, START_I)
    bars[START_I - 1] = (100.0, 100.0, 100.0, 100.0)
    bars.append((100.0, 200.0, 98.0, 120.0))            # bar 18: huge high
    bars += flat_day(120.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    first_bar, first_anchor, first_limit = r.anchor_updates[0]
    assert first_bar == START_I
    assert first_anchor == pytest.approx(100.0)         # NOT 200.0
    assert first_limit == pytest.approx(99.0)
    # bar 18's low of 98 is below 99 -> it fills at 99, not at 200*0.99
    assert r.trades[0].entry_bar == START_I
    assert r.trades[0].entry_px == pytest.approx(99.0)


def test_no_order_before_1100():
    """§10.5 / §2.3: no order may be placed before 11:00 under any circumstance.

    The morning dips 10% below the session high — deep enough to fill a
    resting 0.99x limit several times over — and the afternoon never trades
    below it. A correct engine books nothing at all.
    """
    bars = flat_day(100.0, START_I)
    bars[5] = (100.0, 100.0, 90.0, 100.0)               # 09:55: a 10% dip
    bars[9] = (100.0, 100.0, 92.0, 100.0)               # 10:15: another
    bars += flat_day(100.0, FULL_DAY_BARS - START_I)    # afternoon flat at 100
    r = simulate_session(make_session(bars), CFG)
    assert r.fills == 0, "a pre-11:00 dip must not produce an order"
    assert r.trades == []
    assert all(b >= START_I for b, _, _ in r.anchor_updates)


def test_the_morning_high_still_anchors_the_afternoon_limit():
    """The morning is observation only, but it *builds* the anchor (§2.3)."""
    bars = flat_day(100.0, START_I)
    bars[5] = (100.0, 120.0, 100.0, 100.0)              # morning high of 120
    bars += [(100.0, 100.0, 98.0, 99.0)]                # 11:00 dips to 98
    bars += flat_day(99.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    assert r.anchor_updates[0] == (START_I, pytest.approx(120.0), pytest.approx(118.8))
    assert r.trades[0].entry_bar == START_I
    assert r.trades[0].entry_px == pytest.approx(100.0), "gapped through -> fills at open"


def test_gate_off_no_orders():
    """§10.14: a day where the gate is OFF produces zero orders."""
    dates = pd.bdate_range("2024-01-02", periods=6)
    quiet = [[(100.0, 100.5, 99.5, 100.0)] + flat_day(100.0, 77) for _ in range(5)]
    volatile = [(100.0, 100.0, 100.0, 100.0)] * START_I + \
               [(100.0, 130.0, 70.0, 100.0)] * (FULL_DAY_BARS - START_I)
    frame = bars_to_frame(quiet + [volatile], dates)
    sessions = build_sessions(frame, CFG)
    d = daily_features(sessions, CFG)
    assert d["atr5"].iloc[5] < GATE_ATR5_MIN
    ok, why = gate_on(d.iloc[5], CFG)
    assert ok is False and why == "atr5_below_gate"


# ================================================ §10.6 bracket live on the fill
def test_bracket_live_on_entry_bar():
    """§2.6: the OCA is placed the instant the entry fills, so the protective
    stop can fire on the entry bar itself."""
    bars = flat_day(100.0, START_I)
    bars.append((100.0, 100.0, 90.0, 91.0))             # dips to 99 then to 90
    bars += flat_day(91.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    t = r.trades[0]
    assert t.entry_bar == t.exit_bar == START_I
    assert t.outcome == "stop"
    assert t.entry_px == pytest.approx(99.0)
    assert t.exit_px == pytest.approx(99.0 * 0.96)
    assert t.ret == pytest.approx(-0.04)


def test_target_may_not_fill_on_the_entry_bar():
    """The research convention (STRATEGY_SPEC §2.5 step 4): a target fill is
    booked no earlier than the bar after entry. Intrabar ordering is unknowable."""
    bars = flat_day(100.0, START_I)
    bars.append((100.0, 105.0, 98.9, 104.0))            # entry at 99 AND +1% high
    bars.append((104.0, 104.0, 104.0, 104.0))
    bars += flat_day(104.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    assert r.trades[0].entry_bar == START_I
    assert r.trades[0].exit_bar == START_I + 1
    assert r.trades[0].outcome == "target"
    # the permissive reading books it on the entry bar instead
    r2 = simulate_session(make_session(bars), dc.replace(CFG, target_on_entry_bar=True))
    assert r2.trades[0].exit_bar == START_I


def test_gap_through_levels_fills_at_the_open():
    """A limit/stop gapped through fills at the open, not at the level."""
    bars = flat_day(100.0, START_I)
    bars.append((95.0, 95.0, 94.0, 95.0))               # opens below the 99 limit
    bars.append((80.0, 80.0, 79.0, 80.0))               # gaps below the 91.2 stop
    bars += flat_day(80.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    t = r.trades[0]
    assert t.entry_px == pytest.approx(95.0), "buy limit gapped through -> fill at open"
    assert t.exit_px == pytest.approx(80.0), "sell stop gapped through -> fill at open"
    assert t.ret == pytest.approx(80.0 / 95.0 - 1)
    assert t.ret < -0.04, "a gap-through stop loses more than the 4% level"


# ==================================================== §10.7/§10.8 the breakers
def _stop_cycle(price: float) -> list[tuple]:
    """One bar that fills the resting limit at 0.99*price and stops out."""
    return [(price, price, price * 0.95, price * 0.951)]


def test_stop_breaker():
    """§10.7 / §2.7: after the 2nd stop-out, no further entry that session."""
    bars = flat_day(100.0, START_I)
    for _ in range(5):                                   # five stop-out chances
        bars += [(100.0, 100.0, 94.0, 100.0), (100.0, 100.0, 100.0, 100.0)]
    bars += flat_day(100.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    assert r.stop_outs == MAX_STOPS == 2
    assert r.fills == 2, "a third entry was placed after the breaker tripped"
    assert r.pnl == pytest.approx(-2 * 0.04)
    assert all(t.outcome == "stop" for t in r.trades)


def test_fill_cap():
    """§10.8 / §2.7: after the 5th fill, no further entry that session."""
    bars = flat_day(100.0, START_I)
    for _ in range(8):                                   # eight round-trip chances
        bars += [(100.0, 100.0, 98.5, 99.0),             # fill at 99.0
                 (99.0, 100.5, 99.0, 100.0)]             # target 99.99 hit
    bars += flat_day(100.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    assert r.fills == MAX_FILLS == 5
    assert r.stop_outs == 0
    assert len(r.trades) == 5
    assert all(t.outcome == "target" for t in r.trades)
    # every exit is at least the +1% target (a gap-up open fills better)
    assert all(t.ret >= 0.01 - 1e-12 for t in r.trades)
    assert r.pnl == pytest.approx(sum(t.ret for t in r.trades))
    # the cap, not the market, is what stopped it: bars after the 5th exit
    # still trade below the resting limit and must produce no 6th entry.
    last_exit = r.trades[-1].exit_bar
    limit = max(lp for _, _, lp in r.anchor_updates)
    assert any(bars[i][2] <= limit for i in range(last_exit + 1, FULL_DAY_BARS))


def test_worst_structural_day_is_minus_eight_percent():
    """§2.7: the breaker converts the worst possible day to a structural -8%."""
    bars = flat_day(100.0, START_I)
    for _ in range(5):
        bars += [(100.0, 100.0, 94.0, 100.0), (100.0, 100.0, 100.0, 100.0)]
    bars += flat_day(100.0, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    assert r.pnl == pytest.approx(-0.08)


# ============================================================= §2.8 the flatten
def test_open_position_is_flattened_at_1555():
    """§2.8: nothing is carried overnight; the position closes at 15:55."""
    bars = flat_day(100.0, START_I)
    bars.append((100.0, 100.0, 98.0, 98.5))              # entry at 99
    bars += [(98.5, 98.6, 98.4, 98.5)] * (FULL_DAY_BARS - len(bars) - 1)
    bars.append((98.5, 98.6, 98.4, 97.0))                # the 15:55 bar
    assert len(bars) == FULL_DAY_BARS
    r = simulate_session(make_session(bars), CFG)
    t = r.trades[-1]
    assert t.outcome == "flatten"
    assert t.exit_bar == bar_index("15:50"), "spec flattens at 15:55 = close of the 15:50 bar"
    assert t.exit_px == pytest.approx(98.5)
    # the research reading rides the last bar to the 16:00 close instead
    r2 = simulate_session(make_session(bars), dc.replace(CFG, eod_mode="session_close"))
    assert r2.trades[-1].exit_bar == bar_index("15:55")
    assert r2.trades[-1].exit_px == pytest.approx(97.0)


def test_no_position_survives_the_session():
    bars = flat_day(100.0, START_I) + [(100.0, 100.0, 98.0, 98.5)]
    bars += flat_day(98.5, FULL_DAY_BARS - len(bars))
    r = simulate_session(make_session(bars), CFG)
    assert all(t.exit_bar >= t.entry_bar for t in r.trades)
    assert len(r.trades) == r.fills, "every fill must be closed by the end of the session"


# ======================================================= §10.1 clean-room parity
@pytest.mark.slow
@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_parity_with_research_engine(symbol):
    """§10.1 / §9 Phase 1 — the acceptance test.

    The clean-room engine, run under the research engine's reading of the
    ambiguous clauses, must reproduce its daily P&L series exactly.
    """
    csv = os.path.join(ROOT, f"{symbol}_5min_6Years.csv")
    if not os.path.exists(csv) or os.path.getsize(csv) < 10_000:
        pytest.skip(f"{symbol} 5-minute history unavailable (git lfs pull)")
    from parity import research_series, compare
    ref = research_series()[symbol]
    _, got, _ = run_sleeve(symbol, RESEARCH_COMPAT)
    c = compare(ref, got, tol=1e-12)
    assert c["days_only_in_research"] == 0
    assert c["days_only_in_cleanroom"] == 0
    assert c["common_days"] > 700
    assert c["max_abs_diff"] < 1e-12, f"worst daily divergence {c['max_abs_diff']:g}"


@pytest.mark.slow
def test_v14_tables_rebuild_identically():
    """§9 Phase 1: reproduce band_lab/out/v14_*.csv from the clean-room series."""
    for sym in ("SOXL", "SOXS"):
        csv = os.path.join(ROOT, f"{sym}_5min_6Years.csv")
        if not os.path.exists(csv) or os.path.getsize(csv) < 10_000:
            pytest.skip("5-minute history unavailable (git lfs pull)")
    from parity import rebuild_v14, diff_tables, cleanroom_series
    series, _, _ = cleanroom_series(RESEARCH_COMPAT)
    d = diff_tables(rebuild_v14(series))
    assert (d["status"] == "IDENTICAL").all(), d.to_string(index=False)
