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

from broker import FakeIB, NotLiveDataError, SessionHours, is_working
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


def test_a_failed_flatten_does_not_book_a_fabricated_trade(tmp_path):
    """`sm.flatten(price=0.0)` reported a real open position as -4018 bp.

    It was called unconditionally on a comment asserting "not in a position
    now" — false exactly when `ensure_flat` fails. Booking an exit at zero
    prices the trade at `qty * (0 - entry) / capital`, which looks like a
    catastrophic loss and buries the actual fault: shares about to be carried
    overnight, which §1 forbids above everything else.
    """
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX + 1):
        eng.on_bar("SOXL", b)
    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    ib.fill(entry.order_id, price=100.0)
    eng.poll(START_IDX + 1)
    assert eng.sleeves["SOXL"].sm.in_position

    ib.fill = lambda *a, **k: None            # the flatten cannot settle
    flat = eng.flatten_all(settle=0)
    assert flat["SOXL"] is False
    sm = eng.sleeves["SOXL"].sm
    assert sm.in_position, "the position is real and still open — say so"
    assert not sm.trades, "no trade may be booked at a price nothing traded at"
    assert sm.pnl == 0.0, "and the day's P&L must not be fabricated"


# ----------------------------- the flatten deadline (2026-08-10, fix #4)
@pytest.mark.parametrize("hhmm,expected", [
    ("15:55", 5 * 60 - 20),      # on time: five minutes, less the margin
    ("15:58", 2 * 60 - 20),      # late start still gets what is left
    ("15:59:50", 0.0),           # inside the margin — floored, never negative
    ("16:05", 0.0),              # already past the hard deadline
])
def test_hard_flat_budget_counts_down_to_the_1600_deadline(tmp_path, hhmm, expected):
    """§12 puts the flatten at 15:55 and the hard deadline at 16:00.

    On 2026-08-10 the flatten used 23 seconds of those five minutes and carried
    524 shares overnight. The budget is what stops that recurring.
    """
    eng, ib, store, feats = _engine(tmp_path)
    parts = [int(v) for v in hhmm.split(":")] + [0]
    now = datetime(2026, 8, 10, parts[0], parts[1], parts[2], tzinfo=ZoneInfo("America/New_York"))
    assert eng.hard_flat_budget(now) == pytest.approx(expected, abs=0.5)


def test_hard_flat_budget_is_never_negative(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    late = datetime(2026, 8, 10, 23, 0, tzinfo=ZoneInfo("America/New_York"))
    assert eng.hard_flat_budget(late) == 0.0


def test_flatten_shares_the_budget_between_sleeves_that_still_hold(tmp_path):
    """One stuck sleeve must not spend the other's deadline.

    `flatten_all` runs sleeves sequentially, so an un-shared budget would let
    the first burn all five minutes and leave the second with none — turning
    one overnight position into two.
    """
    eng, ib, store, feats = _engine(tmp_path, symbols=("SOXL", "SOXS"))
    day = datetime(2026, 8, 10, 6, 0, tzinfo=ZoneInfo("America/New_York"))
    eng.pre_open(day, feats)

    seen = {}
    for sym, rt in eng.sleeves.items():
        rt.om.ensure_flat = (lambda s: (lambda **kw: seen.__setitem__(s, kw.get("budget")) or True))(sym)
    eng.flatten_all(budget=100.0)

    # Neither sleeve holds anything, so `max(1, holding)` keeps the share finite
    # and both are offered time rather than the first taking it all.
    assert set(seen) == {"SOXL", "SOXS"}
    assert all(v is not None and v > 0 for v in seen.values()), seen


def test_flatten_gives_a_holding_sleeve_a_real_share(tmp_path):
    eng, ib, store, feats = _engine(tmp_path, symbols=("SOXL", "SOXS"))
    day = datetime(2026, 8, 10, 6, 0, tzinfo=ZoneInfo("America/New_York"))
    eng.pre_open(day, feats)
    ib.positions["SOXL"] = 500.0
    ib.positions["SOXS"] = 500.0

    seen = {}
    for sym, rt in eng.sleeves.items():
        rt.om.ensure_flat = (lambda s: (lambda **kw: seen.__setitem__(s, kw.get("budget")) or True))(sym)
    eng.flatten_all(budget=100.0)

    # Two sleeves holding: each is offered about half, not all-then-nothing.
    assert seen["SOXL"] == pytest.approx(50.0, abs=5.0), seen
    assert seen["SOXS"] > 0, seen


def test_hard_flat_budget_is_capped_at_the_1555_to_1600_window(tmp_path):
    """Found by review: a disconnect path calling `flatten_all` at 09:00 would
    otherwise be handed seven hours, and `ensure_flat` would spend them."""
    eng, ib, store, feats = _engine(tmp_path)
    morning = datetime(2026, 8, 10, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    assert eng.hard_flat_budget(morning) == pytest.approx(300.0)   # 15:55 -> 16:00


def test_flatten_without_a_clock_does_not_invent_a_deadline(tmp_path):
    """Found by a 6x slowdown in the suite, not by a failing assertion.

    `flatten_all` used to read `datetime.now()` itself, so the same call
    returned a 0-second budget after 16:00 and a 300-second one in the morning.
    The suite passed either way; it just took five minutes longer before lunch.
    A test that is only fast by time of day is not a passing test.
    """
    import time as _t
    eng, ib, store, feats = _engine(tmp_path)
    day = datetime(2026, 8, 10, 6, 0, tzinfo=ZoneInfo("America/New_York"))
    eng.pre_open(day, feats)
    ib.positions["SOXL"] = 100.0          # never settles: the worst case

    t0 = _t.time()
    eng.flatten_all(settle=0)             # no clock given -> no deadline
    assert _t.time() - t0 < 30, "flatten_all invented a wall-clock budget"


def test_flatten_honours_a_clock_when_it_is_given(tmp_path):
    """The other half: with a clock, the §12 deadline is in force."""
    eng, ib, store, feats = _engine(tmp_path, symbols=("SOXL",))
    day = datetime(2026, 8, 10, 6, 0, tzinfo=ZoneInfo("America/New_York"))
    eng.pre_open(day, feats)
    seen = {}
    eng.sleeves["SOXL"].om.ensure_flat = lambda **kw: seen.update(kw) or True
    eng.flatten_all(now=datetime(2026, 8, 10, 15, 55,
                                 tzinfo=ZoneInfo("America/New_York")))
    assert seen.get("budget") == pytest.approx(5 * 60 - 20, abs=1.0)


# ------------------ completing the bar record (fix: bar 76/77 truncation)
def test_the_session_record_is_completed_after_the_flatten(tmp_path):
    """`run_session` stops at 15:55, so bars 76 and 77 are never recorded.

    `report.py`'s shadow replays what was stored and `replay_session`
    force-flattens at the last bar it is given, so the comparison closed its
    final trade a bar early. On 2026-08-10 that understated the SOXS shadow by
    68 bp and read as live outperformance.
    """
    eng, ib, store, feats = _engine(tmp_path)
    day = datetime(2026, 8, 10, 6, 0, tzinfo=ZoneInfo("America/New_York"))
    eng.pre_open(day, feats)
    ib.bars["SOXL"] = _session_bars(high=100.0, n=FLATTEN_IDX + 1)   # 0..77

    # what the live loop managed to record
    for b in ib.bars["SOXL"][:76]:
        store.bar("SOXL", eng.session, b.idx, b.open, b.high, b.low, b.close, b.volume)
    recorded = store.session_bars("SOXL", eng.session)
    assert max(r["bar_idx"] for r in recorded) == 75

    eng.record_session_tail(day)

    recorded = store.session_bars("SOXL", eng.session)
    assert max(r["bar_idx"] for r in recorded) == FLATTEN_IDX
    from sleeve import LAST_HOLDING_IDX
    assert LAST_HOLDING_IDX in {r["bar_idx"] for r in recorded}


def test_completing_the_record_is_idempotent(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    day = datetime(2026, 8, 10, 6, 0, tzinfo=ZoneInfo("America/New_York"))
    eng.pre_open(day, feats)
    ib.bars["SOXL"] = _session_bars(high=100.0, n=FLATTEN_IDX + 1)
    eng.record_session_tail(day)
    first = len(store.session_bars("SOXL", eng.session))
    eng.record_session_tail(day)
    assert len(store.session_bars("SOXL", eng.session)) == first


def test_a_failed_tail_fetch_never_blocks_the_reconcile(tmp_path):
    """The record is evidence, not control."""
    eng, ib, store, feats = _engine(tmp_path)
    day = datetime(2026, 8, 10, 6, 0, tzinfo=ZoneInfo("America/New_York"))
    eng.pre_open(day, feats)
    def boom(*a, **kw):
        raise RuntimeError("no data")
    ib.historical_bars = boom
    assert eng.record_session_tail(day) == {"SOXL": 0}      # no raise
    eng.reconcile()                                          # still works


# ------------------- §2.5's activation is a clock event (fix: 11:05 arming)
def _at_1100(day=None):
    d = day or DAY
    return d.replace(hour=11, minute=0, second=0, microsecond=0)


def _observed_to_1100(eng, symbol="SOXL"):
    """Everything the engine knows at 11:00: bars 0..17, filter applied."""
    for b in _session_bars(n=START_IDX):
        eng.on_bar(symbol, b)


def test_the_limit_is_armed_at_1100_not_when_bar_18_completes(tmp_path):
    """The engine armed five minutes late, every session.

    The feed only reports *completed* bars, so the bar labelled 11:00 arrived
    at 11:05 and the limit went live after that bar had already traded. The
    backtest opens bar 18 and then lets it trade against the resting limit —
    `sleeve.on_bar_open` says so in as many words. Measured on the reference
    engine at start_idx 19 instead of 18: SOXL 65.93 -> 62.02 bp/ON-day,
    SOXS 61.18 -> 57.72.
    """
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    _observed_to_1100(eng)
    assert not [o for o in ib.orders.values() if o.action == "BUY"]

    assert eng.activate_due(_at_1100()) == ["SOXL"]
    buys = [o for o in ib.orders.values() if o.action == "BUY"]
    assert buys, "the limit must be resting before bar 18 trades"
    assert buys[0].limit_px == pytest.approx(99.0)


def test_the_clock_activation_does_not_fire_early(tmp_path):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    _observed_to_1100(eng)
    assert eng.activate_due(_at_1100().replace(hour=10, minute=59)) == []
    assert not [o for o in ib.orders.values() if o.action == "BUY"]


def test_the_clock_activation_refuses_an_incomplete_bar_record(tmp_path):
    """A gapped session understates the session high, which is the one input
    the whole strategy ratchets from."""
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX):
        if b.idx == 12:
            continue                      # a bar the feed never delivered
        eng.on_bar("SOXL", b)
    assert eng.activate_due(_at_1100()) == []
    assert not [o for o in ib.orders.values() if o.action == "BUY"]


def test_the_clock_activation_does_not_double_arm(tmp_path):
    """`on_bar` still activates when bar 18 lands; it must be a no-op by then."""
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    _observed_to_1100(eng)
    eng.activate_due(_at_1100())
    before = len([o for o in ib.orders.values() if o.action == "BUY"])

    eng.on_bar("SOXL", Bar(START_IDX, 100.0, 100.0, 100.0, 100.0, 1.0))
    after = len([o for o in ib.orders.values() if o.action == "BUY"])
    assert after == before, "bar 18 armed a second entry order"


def test_the_clock_activation_still_refuses_delayed_data(tmp_path):
    """§2's refusal must not be bypassed by moving the trigger to the clock."""
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    _observed_to_1100(eng)
    def boom(symbol=None):
        raise NotLiveDataError("delayed")
    ib.assert_live_data = boom
    assert eng.activate_due(_at_1100()) == []
    assert eng.sleeves["SOXL"].dormant
    assert not [o for o in ib.orders.values() if o.action == "BUY"]


def test_a_stood_down_sleeve_is_not_armed_by_the_clock(tmp_path):
    # §2.3: a wide opening range with the 10:00 print low in it.
    eng, ib, store, feats = _engine(tmp_path, or30=1.0)
    eng.pre_open(DAY, feats)
    for i in range(START_IDX):
        eng.on_bar("SOXL", Bar(i, 100.0, 108.0, 100.0, 100.5, 1.0))
    assert eng.sleeves["SOXL"].dormant
    assert eng.activate_due(_at_1100()) == []


# --------------------------------- the cold start is a restart path too (F2)
def test_a_cold_start_never_places_a_second_entry(tmp_path):
    """§3 says every path is the restart path. The first one was not.

    `Runner.pre_open` connects before `engine.sleeves` exists, so `on_connect`
    iterated an empty dict and reconciled nothing, and `pre_open` then built
    fresh state machines without asking the broker anything. Only a *re*connect
    ever reconciled. A process that armed at 11:00 and died therefore came back
    believing it had never armed, replayed the session from the feed, and put a
    second live buy limit behind one that could still fill.
    """
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX + 1):
        eng.on_bar("SOXL", b)
    resting = [o for o in ib.orders.values() if o.action == "BUY"]
    assert len(resting) == 1, "the dead process armed exactly once"

    # The replacement process: same broker, same database, nothing in memory.
    eng2 = Engine(ib, store, symbols=("SOXL",), on_event=lambda l, m: None)
    eng2.pre_open(DAY, feats)
    assert eng2.sleeves["SOXL"].om.entry_id == resting[0].order_id, \
        "pre-open must establish state from the broker, not from memory"

    for b in _session_bars(n=START_IDX + 1):
        eng2.on_bar("SOXL", b)

    live = [o for o in ib.orders.values()
            if o.action == "BUY" and o.status not in ("Cancelled", "Filled")]
    assert len(live) == 1, f"one sleeve, one resting entry — found {len(live)}"


def test_pre_open_reconciles_even_when_the_market_is_closed(tmp_path):
    """A position left by a dead process is just as real on a holiday.

    The gate and the market-closed check both stand the sleeve down before
    anything else looks at the broker, so a holiday is precisely the day a
    forgotten position would go unnoticed.
    """
    ib = FakeIB(symbols=("SOXL",))
    store = Store(str(tmp_path / "closed.db"))
    said = []
    eng = Engine(ib, store, symbols=("SOXL",),
                 on_event=lambda lvl, msg: said.append((lvl, msg)))
    o = DAY.replace(hour=9, minute=30)
    ib.hours["SOXL"] = SessionHours(o, o.replace(hour=13), is_half_day=True)
    ib.positions["SOXL"] = 500.0        # left behind by a process that died

    eng.pre_open(DAY, {"SOXL": _history()})

    assert eng.sleeves["SOXL"].dormant, "a half day still gates the sleeve off"
    # Asserted on what pre_open itself did — calling reconcile() from the test
    # would write the same row and pass whether or not the engine ever looked.
    rows = store.rows("SELECT state FROM counters WHERE symbol='SOXL'")
    assert rows, "pre-open must reconcile even when the sleeve stands down"
    assert any(lvl == "warn" and "500" in msg for lvl, msg in said), \
        "and must say so — a holiday is the day nobody else would look"


# ------------------- a close the engine did not order (2026-08-10 shape, F3)
def _in_position(tmp_path, entry_px=90.0):
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX + 1):
        eng.on_bar("SOXL", b)
    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    ib.fill(entry.order_id, price=entry_px)
    eng.poll(START_IDX + 1)
    assert eng.sleeves["SOXL"].sm.in_position
    return eng, ib, store


def test_a_watchdog_flatten_is_booked_at_the_price_it_filled(tmp_path):
    """The watchdog's refs are `WATCHDOG-<date>-<time>-<symbol>`.

    `parse_ref` cannot decode one — `int("SOXL")` raises — so the execution was
    logged as a fill and routed nowhere. `exit_qty` stayed 0, the sleeve went on
    believing it held 757 shares it no longer had, and 15:55 booked the trade at
    a price nobody traded at: -9084 bp against a real +101.
    """
    eng, ib, store = _in_position(tmp_path, entry_px=90.0)
    held = abs(ib.position("SOXL"))

    oid = ib.place_market("SOXL", "SELL", held, "WATCHDOG-20260803-155830-SOXL")
    ib.fill(oid, price=91.0)

    eng.flatten_all(bar_idx=FLATTEN_IDX, settle=0)

    sm = eng.sleeves["SOXL"].sm
    assert len(sm.trades) == 1
    t = sm.trades[-1]
    assert t.exit_px == pytest.approx(91.0), "the price it actually filled at"
    assert t.outcome == "external", "not a target, a stop, or our own flatten"
    assert t.ret > 0, "a +1.00 move on a long is not a loss"


def test_an_external_close_stands_the_sleeve_down(tmp_path):
    """It must not re-arm into the position that was just taken off it.

    Every actor that closes a position behind the engine's back — the watchdog,
    a hand in TWS, a liquidation — is trying to reduce exposure. Re-arming is
    the exact opposite, and it would let the engine undo a watchdog
    intervention that fired for a reason.
    """
    eng, ib, store = _in_position(tmp_path, entry_px=90.0)
    oid = ib.place_market("SOXL", "SELL", abs(ib.position("SOXL")),
                          "WATCHDOG-20260803-155830-SOXL")
    ib.fill(oid, price=91.0)

    eng.poll(START_IDX + 2)                    # mid-session, not at the close

    sm = eng.sleeves["SOXL"].sm
    assert not sm.in_position
    assert sm.state.value == "closed"
    assert not [o for o in ib.orders.values()
                if o.action == "BUY" and o.status == "Submitted"], \
        "no new entry may rest after someone else flattened the sleeve"


def test_an_unexplained_close_is_never_booked_at_zero(tmp_path):
    """The half the earlier fix left open.

    `sm.flatten` books whenever the sleeve is in a position and is only ever
    handed 0.0, so guarding on `not flat` covered a real open position and
    missed its mirror image: broker flat, sleeve still holding, and no
    execution to explain the difference. Here the position simply vanishes.
    """
    eng, ib, store = _in_position(tmp_path, entry_px=90.0)
    ib.positions["SOXL"] = 0.0                 # gone, with no execution at all

    eng.flatten_all(bar_idx=FLATTEN_IDX, settle=0)

    sm = eng.sleeves["SOXL"].sm
    assert not sm.trades, "no trade may be booked at a price nothing traded at"
    assert sm.pnl == 0.0


# ------------------------- a dormant sleeve stops being able to trade (F12)
def test_a_gated_off_day_cancels_an_entry_left_by_a_dead_process(tmp_path):
    """`sleeve.py` has always documented DORMANT as cancel-all; it only logged.

    Latent until `pre_open` began reconciling before the gate. Now a gate-OFF
    morning can start holding a resting buy limit from a process that died
    yesterday — and left alone it fills in the afternoon, into a sleeve that
    decided at 06:00 not to trade and is watching nothing.
    """
    ib = FakeIB(symbols=("SOXL",))
    ib.connect()
    stale = ib.place_limit("SOXL", "BUY", 500, 99.0, "20260803-SOXL-E-1")
    store = Store(str(tmp_path / "d.db"))
    eng = Engine(ib, store, symbols=("SOXL",), on_event=lambda l, m: None)

    eng.pre_open(DAY, {"SOXL": _history(range_pct=2.0)})     # ATR5 too low

    assert eng.sleeves["SOXL"].dormant
    assert not is_working(ib.orders[stale].status), \
        "a sleeve that will not trade must not leave a live entry behind"


def test_a_dormant_sleeve_keeps_the_bracket_on_a_real_position(tmp_path):
    """Cancel-all taken literally would strip the only protection there is.

    §6.1's guarantee is a stop resting for whatever is held. The reconcile that
    surfaces the entry above surfaces the bracket too, and they must not be
    treated the same way.
    """
    ib = FakeIB(symbols=("SOXL",))
    ib.connect()
    ib.positions["SOXL"] = 500.0
    tgt = ib.place_limit("SOXL", "SELL", 500, 101.0, "20260803-SOXL-T-2",
                         oca_group="g")
    stp = ib.place_stop("SOXL", "SELL", 500, 95.0, "20260803-SOXL-S-3",
                        oca_group="g")
    store = Store(str(tmp_path / "d2.db"))
    said = []
    eng = Engine(ib, store, symbols=("SOXL",),
                 on_event=lambda lvl, msg: said.append((lvl, msg)))

    eng.pre_open(DAY, {"SOXL": _history(range_pct=2.0)})     # gate OFF

    assert eng.sleeves["SOXL"].dormant
    assert is_working(ib.orders[tgt].status) and is_working(ib.orders[stp].status)
    assert any("keeping the bracket" in m for _, m in said)


def test_a_dormant_flat_sleeve_does_not_leave_orphan_sell_orders(tmp_path):
    """Flat, so the two legs have nothing to sell. They are just exposure."""
    ib = FakeIB(symbols=("SOXL",))
    ib.connect()
    tgt = ib.place_limit("SOXL", "SELL", 500, 101.0, "20260803-SOXL-T-2",
                         oca_group="g")
    stp = ib.place_stop("SOXL", "SELL", 500, 95.0, "20260803-SOXL-S-3",
                        oca_group="g")
    store = Store(str(tmp_path / "d3.db"))
    eng = Engine(ib, store, symbols=("SOXL",), on_event=lambda l, m: None)

    eng.pre_open(DAY, {"SOXL": _history(range_pct=2.0)})

    assert not is_working(ib.orders[tgt].status)
    assert not is_working(ib.orders[stp].status)


# ------------- one sleeve's entitlement is not the whole session's (F22)
def test_standing_down_one_sleeve_leaves_the_other_trading(tmp_path):
    """Entitlements are per contract, and the error now says which.

    `NotLiveDataError` carries the symbol so a caller that catches it outside
    the per-sleeve guards can still contain it. Parsing it out of the message
    is the alternative, and the message is prose.
    """
    eng, ib, store, feats = _engine(tmp_path, symbols=("SOXL", "SOXS"))
    eng.pre_open(DAY, feats)

    stood = eng.stand_down("SOXL", "not_live_data", "SOXL: delayed")

    assert stood == ["SOXL"]
    assert eng.sleeves["SOXL"].dormant
    assert not eng.sleeves["SOXS"].dormant


def test_an_unattributed_failure_stands_every_sleeve_down(tmp_path):
    """§4 forbids trading on delayed data, and an error naming no symbol
    could be either sleeve. Refusing both is the safe reading."""
    eng, ib, store, feats = _engine(tmp_path, symbols=("SOXL", "SOXS"))
    eng.pre_open(DAY, feats)

    stood = eng.stand_down(None, "not_live_data", "account: no subscription")

    assert sorted(stood) == ["SOXL", "SOXS"]
    assert all(rt.dormant for rt in eng.sleeves.values())


def test_standing_down_takes_the_resting_entry_off_the_market(tmp_path):
    """The gap the two `not_live_data` paths had.

    Both set `rt.dormant` directly, which skipped `_dormant` — so a sleeve that
    lost its feed while armed went dormant with its buy limit still resting at
    IBKR, free to fill into a sleeve that had stopped watching.
    """
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    for b in _session_bars(n=START_IDX + 1):
        eng.on_bar("SOXL", b)
    entry = [o for o in ib.orders.values() if o.action == "BUY"][0]
    assert is_working(entry.status), "armed, with a live buy limit"

    eng.stand_down("SOXL", "not_live_data", "SOXL: delayed")

    assert not is_working(entry.status), \
        "a sleeve that stops watching must not leave an order that can fill"


def test_a_second_stand_down_is_quiet(tmp_path):
    """It runs from a loop handler, so it must not shout every 30 seconds."""
    eng, ib, store, feats = _engine(tmp_path)
    eng.pre_open(DAY, feats)
    assert eng.stand_down("SOXL", "not_live_data") == ["SOXL"]
    assert eng.stand_down("SOXL", "not_live_data") == []


# ------------------- a ref must identify exactly one order (F24)
def test_reconcile_reports_a_ref_that_covers_two_orders(tmp_path):
    """Deterministic refs are what make §2.7's counters reconstructible.

    `reconcile` counts entries as a *set* of refs, so a collision under-counts
    the breaker without saying so. This is the detector for the sequence
    recovery regressing.
    """
    eng, ib, store, feats = _engine(tmp_path)
    said = []
    eng.on_event = lambda lvl, msg: said.append((lvl, msg))
    eng.pre_open(DAY, feats)

    store.order("SOXL", eng.session, "20260803-SOXL-E-1", "E", "BUY", "LMT",
                "placed", order_id=1)
    store.order("SOXL", eng.session, "20260803-SOXL-E-1", "E", "BUY", "LMT",
                "placed", order_id=2)

    eng.reconcile()

    assert any(lvl == "critical" and "no longer unique" in msg
               for lvl, msg in said)


def test_the_ordinary_event_log_is_not_a_collision(tmp_path):
    """One ref legitimately has many rows — placed, modified, cancelled."""
    eng, ib, store, feats = _engine(tmp_path)
    said = []
    eng.on_event = lambda lvl, msg: said.append((lvl, msg))
    eng.pre_open(DAY, feats)

    for event in ("placed", "modified", "cancelled"):
        store.order("SOXL", eng.session, "20260803-SOXL-E-1", "E", "BUY",
                    "LMT", event, order_id=1)

    eng.reconcile()

    assert not [m for lvl, m in said if "no longer unique" in m]


# ---------------------------------------------- ref hygiene at reconcile
def test_a_blank_order_ref_is_reported_as_its_own_fault(tmp_path):
    """2026-08-13 printed `order refs are no longer unique:  covers 4 orders`
    — a CRITICAL naming nothing, because the colliding ref was the empty
    string. An absent ref and two real refs colliding are different faults with
    different fixes, and rendering the first as the second wastes the one
    message a human is guaranteed to read.
    """
    eng, ib, store, feats = _engine(tmp_path)
    eng.session = "20260813"
    for oid in (1, 2, 3, 4):
        store.order("SOXL", "20260813", "", "T", "SELL", "LMT", "cancelled",
                    order_id=oid)
    seen = []
    eng.on_event = lambda level, msg: seen.append((level, msg))
    eng.reconcile()

    crit = [m for lvl, m in seen if lvl == "critical"]
    assert any("no ref at all" in m for m in crit), crit
    assert not any("no longer unique" in m for m in crit), \
        "a blank ref is not a collision between two real refs"


def test_two_real_refs_colliding_still_reports_a_collision(tmp_path):
    """The check's original purpose, unchanged: `reconcile` counts entries as a
    set of refs, so one ref covering two orders silently under-counts §2.7."""
    eng, ib, store, feats = _engine(tmp_path)
    eng.session = "20260813"
    for oid in (1, 2):
        store.order("SOXL", "20260813", "20260813-SOXL-E-1", "E", "BUY", "LMT",
                    "placed", order_id=oid)
    seen = []
    eng.on_event = lambda level, msg: seen.append((level, msg))
    eng.reconcile()

    crit = [m for lvl, m in seen if lvl == "critical"]
    assert any("no longer unique" in m and "20260813-SOXL-E-1" in m
               for m in crit), crit


# --------------------------------------------- the decision, with its numbers
def test_a_gate_off_line_carries_the_value_and_the_margin(tmp_path):
    """"GATE OFF: atr5_below_gate" reads the same at 5.98 and at 3.10.

    On 2026-08-17 a *contaminated* ATR5 flipped this line with nothing on
    screen to show it had moved, and on 2026-08-18 a legitimately quiet day
    produced the identical text. The operator's next question is always "by how
    much", and it cost a database query to answer.
    """
    eng, ib, store, feats = _engine(tmp_path, range_pct=3.0)   # well under 6.0
    seen = []
    eng.on_event = lambda level, msg: seen.append(msg)
    eng.pre_open(DAY, feats)

    (line,) = [m for m in seen if "GATE OFF" in m]
    assert "atr5_below_gate" in line
    assert "atr5=3.00" in line and "needs 6.00" in line


def test_a_gate_on_line_says_so_with_the_value(tmp_path):
    eng, ib, store, feats = _engine(tmp_path, range_pct=10.0)
    seen = []
    eng.on_event = lambda level, msg: seen.append(msg)
    eng.pre_open(DAY, feats)

    (line,) = [m for m in seen if "gate ON" in m]
    assert "atr5=10.00" in line and "needs 6.00" in line
    assert not [m for m in seen if "GATE OFF" in m]


def test_the_stand_down_line_carries_both_halves_of_v9(tmp_path):
    """V9 is "skip OR30 above the trailing 80th pct *unless* the 10:00 print is
    in the top third". Both comparisons have to be on screen or a near-miss on
    the rule looks identical to a routine stand-down — 2026-08-13 stood SOXS
    down at pos10=0.021 while SOXL traded on pos10=0.981, same morning."""
    eng, ib, store, feats = _engine(tmp_path, range_pct=10.0, or30=1.0)
    eng.pre_open(DAY, feats)
    seen = []
    eng.on_event = lambda level, msg: seen.append(msg)
    # a wide opening range with a weak 10:00 print -> stand down
    bars = [Bar(i, 100.0, 110.0, 90.0, 91.0) for i in range(FILTER_IDX + 1)]
    eng.apply_morning_filter("SOXL", bars)

    (line,) = [m for m in seen if "STAND DOWN" in m]
    assert "or30=" in line and "thr80=" in line and "pos10=" in line
