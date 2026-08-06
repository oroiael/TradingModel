"""
Stage 4 tests — the §5 daily timetable, against FakeIB.

The engine owns time. These tests drive it through a synthetic session and
check the things that are only observable at the timetable level: the gate's
hard interlock, the 10:00 filter, the 11:00 activation, bar-gap detection,
the 15:55 flatten, the 16:00 flat check and the 16:10 reconcile.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from broker import FakeIB, NotLiveDataError, SessionHours
from engine import Engine, FILTER_IDX, FLATTEN_IDX, START_IDX
from store import Store
from strategy_core import Bar, FeatureHistory, SessionStats, session_stats

NY = ZoneInfo("America/New_York")
DAY = datetime(2026, 8, 3, tzinfo=NY)


def _prior_session(range_pct: float, or30: float) -> SessionStats:
    """A completed session with the requested ATR5/thr80 inputs.

    Built from bars through `session_stats` rather than by constructing a
    SessionStats directly, so the history the tests feed the engine is produced
    by exactly the code the live engine uses.
    """
    o = 100.0
    or_hi = o + or30 / 100.0 * o
    hi = o + range_pct / 100.0 * o
    bars = [Bar(0, o, or_hi, o, or_hi, 1.0)]
    bars += [Bar(i, or_hi, or_hi, o, or_hi, 1.0) for i in range(1, 6)]
    bars += [Bar(i, or_hi, hi if i == 6 else or_hi, o, or_hi, 1.0)
             for i in range(6, FLATTEN_IDX + 1)]
    return session_stats(bars)


def _history(range_pct=10.0, or30=3.0, n=130) -> FeatureHistory:
    """Enough completed sessions for ATR5 and thr80 to be defined."""
    h = FeatureHistory()
    stats = _prior_session(range_pct, or30)
    for _ in range(n):
        h.append(stats)
    return h


def _engine(tmp_path, range_pct=10.0, or30=3.0, equity=150_000.0,
            symbols=("SOXL",)):
    ib = FakeIB(equity=equity)
    store = Store(str(tmp_path / "e.db"))
    eng = Engine(ib, store, symbols=symbols, on_event=lambda l, m: None)
    feats = {s: _history(range_pct, or30) for s in symbols}
    return eng, ib, store, feats


def _session_bars(high=100.0, n=None):
    n = FLATTEN_IDX + 1 if n is None else n
    return [Bar(i, high, high, high, high, 1000.0) for i in range(n)]


# ------------------------------------------------------------------ 06:00
def test_pre_open_sets_sleeve_capital_from_capped_basis(tmp_path):
    """§2 — capital_basis = min(NetLiquidation, 150k); sleeve = 0.50 x basis."""
    eng, ib, store, feats = _engine(tmp_path, equity=400_000.0)
    eng.pre_open(DAY, feats)
    assert eng.sleeve_capital == pytest.approx(75_000.0)


def test_pre_open_uses_real_equity_below_the_cap(tmp_path):
    eng, ib, store, feats = _engine(tmp_path, equity=80_000.0)
    eng.pre_open(DAY, feats)
    assert eng.sleeve_capital == pytest.approx(40_000.0)


def test_gate_off_makes_the_sleeve_dormant_for_the_day(tmp_path):
    """ATR5 below 6% -> gate OFF -> hard interlock, no orders all day."""
    eng, ib, store, feats = _engine(tmp_path, range_pct=2.0)
    eng.pre_open(DAY, feats)
    assert eng.sleeves["SOXL"].dormant
    for b in _session_bars():
        eng.on_bar("SOXL", b)
    assert not [o for o in ib.orders.values() if o.action == "BUY"], \
        "a gated-off sleeve must never place an order"


def test_half_day_is_gated_off(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    o = DAY.replace(hour=9, minute=30)
    ib.hours["SOXL"] = SessionHours(o, o.replace(hour=13), is_half_day=True)
    eng.pre_open(DAY, feats)
    assert eng.sleeves["SOXL"].dormant


# ------------------------------------------------------------------ 10:00
def test_morning_filter_stands_the_sleeve_down(tmp_path):
    """§2.3 — OR30 in the top quintile and 10:00 not in the top third."""
    eng, ib, store, feats = _engine(tmp_path, or30=1.0)
    eng.pre_open(DAY, feats)
    bars = [Bar(i, 100.0, 108.0, 100.0, 100.5, 1.0) for i in range(FILTER_IDX + 1)]
    for b in bars:
        eng.on_bar("SOXL", b)
    assert eng.sleeves["SOXL"].dormant
    assert eng.sleeves["SOXL"].dormant_reason


def test_filter_runs_exactly_once(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=FILTER_IDX + 1):
        eng.on_bar("SOXL", b)
    assert eng.sleeves["SOXL"].filtered
    before = eng.sleeves["SOXL"].dormant
    eng.apply_morning_filter("SOXL", _session_bars(n=FILTER_IDX + 1))
    assert eng.sleeves["SOXL"].dormant is before


# ------------------------------------------------------------------ 11:00
def test_no_orders_before_1100_then_armed_at_1100(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX):
        eng.on_bar("SOXL", b)
    assert not [o for o in ib.orders.values() if o.action == "BUY"], \
        "§5: 09:30-11:00 is observe-only"

    eng.on_bar("SOXL", Bar(START_IDX, 100.0, 100.0, 100.0, 100.0, 1.0))
    buys = [o for o in ib.orders.values() if o.action == "BUY"]
    assert buys, "the resting limit must be working at 11:00"
    assert buys[0].limit_px == pytest.approx(99.0)


def test_activation_refuses_delayed_market_data(tmp_path):
    """§2 — the engine must not arm on a delayed feed."""
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    ib.market_data_type = 3          # delayed
    for b in _session_bars(n=START_IDX):
        eng.on_bar("SOXL", b)
    eng.on_bar("SOXL", Bar(START_IDX, 100.0, 100.0, 100.0, 100.0, 1.0))
    rt = eng.sleeves["SOXL"]
    assert rt.dormant and rt.dormant_reason == "not_live_data"
    assert not rt.activated, "a delayed feed must never arm"
    assert not ib.working_orders("SOXL"), "and must place no order"


def test_one_sleeve_losing_its_feed_does_not_end_the_session(tmp_path):
    """Entitlements are per contract.

    On 2026-08-06 a NotLiveDataError on SOXL propagated out of `on_bar`, broke
    the runner's session loop and flattened both sleeves. It is contained now.
    """
    eng, ib, store, feats = _engine(tmp_path, symbols=("SOXL", "SOXS"))
    eng.pre_open(DAY, feats)

    real = ib.assert_live_data
    def only_soxl_is_delayed(symbol=None):
        if symbol == "SOXL":
            raise NotLiveDataError("SOXL: delayed")
        return real(symbol)
    ib.assert_live_data = only_soxl_is_delayed

    for b in _session_bars(n=START_IDX + 1):
        eng.on_bar("SOXL", b)
        eng.on_bar("SOXS", b)

    assert eng.sleeves["SOXL"].dormant, "the affected sleeve stands down"
    assert not eng.sleeves["SOXS"].dormant, "the healthy sleeve keeps trading"
    assert eng.sleeves["SOXS"].activated


def test_bar_gap_is_reported(tmp_path):
    """A missed bar understates session_high, which is the anchor."""
    seen = []
    eng, ib, store, feats = _engine(tmp_path)
    eng.on_event = lambda lvl, msg: seen.append((lvl, msg))
    eng.pre_open(DAY, feats)
    eng.on_bar("SOXL", Bar(0, 100.0, 100.0, 100.0, 100.0, 1.0))
    eng.on_bar("SOXL", Bar(3, 100.0, 100.0, 100.0, 100.0, 1.0))
    assert any(lvl == "error" and "BAR GAP" in msg for lvl, msg in seen)


def test_limit_ratchets_up_with_the_session_high(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX):
        eng.on_bar("SOXL", b)
    eng.on_bar("SOXL", Bar(START_IDX, 100.0, 100.0, 100.0, 100.0, 1.0))
    first = eng.sleeves["SOXL"].om.entry_limit
    eng.on_bar("SOXL", Bar(START_IDX + 1, 100.0, 120.0, 100.0, 120.0, 1.0))
    assert eng.sleeves["SOXL"].om.entry_limit > first


# ------------------------------------------------------------ 15:55/16:00
def test_flatten_cancels_working_orders(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX + 1):
        eng.on_bar("SOXL", b)
    assert [o for o in ib.orders.values() if o.status == "Submitted"]
    eng.flatten_all()
    assert not [o for o in ib.orders.values() if o.status == "Submitted"]


def test_verify_flat_detects_a_residual_position(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    ib.positions["SOXL"] = 5.0
    assert eng.verify_flat() is False
    ib.positions["SOXL"] = 0.0
    assert eng.verify_flat() is True


def test_flatten_closes_a_real_position(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX + 1):
        eng.on_bar("SOXL", b)
    om = eng.sleeves["SOXL"].om
    ib.fill(om.entry_id, price=99.0)
    eng.poll(START_IDX)
    assert ib.position("SOXL") > 0

    real = ib.place_market
    ib.place_market = lambda s, a, q, r: (lambda oid: (ib.fill(oid, price=99.5), oid)[1])(real(s, a, q, r))
    assert eng.flatten_all()["SOXL"] is True
    assert eng.verify_flat() is True


# ------------------------------------------------------------------ 16:10
def test_reconcile_writes_the_daily_row(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX + 1):
        eng.on_bar("SOXL", b)
    eng.reconcile()
    rows = store.rows("SELECT * FROM daily WHERE session=? AND symbol=?",
                      ("20260803", "SOXL"))
    assert len(rows) == 1
    assert rows[0]["gate_ok"] == 1


def test_on_connect_reconciles_every_time(tmp_path):
    """§3 — every path is the restart path."""
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    out = eng.on_connect()
    assert set(out) == {"SOXL"}
    assert "agrees" in out["SOXL"]


def test_day_loss_breaker_condition(tmp_path):
    """§12 DAY_LOSS_KILL = -8.5% of sleeve capital."""
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    assert eng.day_loss_breached() is False
    from sleeve import Trade
    eng.sleeves["SOXL"].sm.trades.append(
        Trade(entry_bar=20, exit_bar=21, entry_px=100.0, exit_px=96.0,
              qty=1.0, ret=-0.09, outcome="stop"))
    assert eng.day_loss_breached() is True


def test_bars_are_persisted(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=6):
        eng.on_bar("SOXL", b)
    assert len(store.session_bars("SOXL", "20260803")) == 6
