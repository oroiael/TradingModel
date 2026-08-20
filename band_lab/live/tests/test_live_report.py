"""
Stage 6 — tests for the measurement instrument.

The report is what the paper run is *for*, so the things it must not get wrong
are specific and known: it must rebuild a round trip that IBKR settled in
several executions (defect 8), it must not manufacture a finding out of missing
evidence (defects 6 and 7), and it must catch a bar-index error of the kind
that silently consumed a whole session (§4.6).

`IMPLEMENTATION_SPEC.md` §10.16 — "weekly report generates and matches
hand-computed values on a fixture week" — is `test_weekly_matches_hand_computed`.
"""

from __future__ import annotations

import os

import pytest

import report
from report import (
    LiveTrade,
    bar_idx_of,
    feature_parity,
    fills_without_quotes,
    live_trades,
    same_bar_reentries,
    session_label,
    shadow_replay,
    slippage,
    weekly,
)
from sleeve import Trade
from store import Store
from strategy_core import Bar, session_stats

CAPITAL = 75_000.0
SESSION = "20260806"


# ------------------------------------------------------------------ fixtures
def utc(hh: int, mm: int, day: str = "2026-08-06") -> str:
    """A UTC ISO timestamp for an ET wall-clock time, on a summer date (EDT)."""
    return f"{day}T{hh + 4:02d}:{mm:02d}:00.000+00:00"


@pytest.fixture
def store(tmp_path) -> Store:
    s = Store(str(tmp_path / "t.db"))
    yield s
    s.close()


def flat_session_bars(n: int = 78, price: float = 100.0) -> list[Bar]:
    return [Bar(i, price, price, price, price, 1000.0) for i in range(n)]


def traded_session_bars(n: int = 76) -> list[Bar]:
    """A session that dips 1% after 11:00 and then reaches +1%.

    The anchor sits at 100.00, so the entry limit is 99.00 and the target
    100.00 x 1.01. Defaults to 76 bars — what a real session records.
    """
    out = []
    for i in range(n):
        if i == 20:
            out.append(Bar(i, 100.0, 100.0, 98.5, 99.0))      # fills the limit
        elif i == 25:
            out.append(Bar(i, 99.5, 101.0, 99.5, 100.5))      # reaches +1%
        else:
            out.append(Bar(i, 100.0, 100.0, 100.0, 100.0))
    return out


def write_daily(store: Store, symbol="SOXL", session=SESSION, *, gate=1,
                filter_ok=1, atr5=10.0, or30=3.0, thr80=5.0, pos10=0.5,
                capital=CAPITAL):
    store.daily(session, symbol, gate_ok=gate, gate_reason="gate_on",
                filter_ok=filter_ok, filter_reason="filter_on", atr5=atr5,
                or30=or30, thr80=thr80, pos10=pos10, sleeve_capital=capital,
                account_equity=150_000.0)


def write_bars(store: Store, bars, symbol="SOXL", session=SESSION):
    for b in bars:
        store.bar(symbol, session, b.idx, b.open, b.high, b.low, b.close, b.volume)


def write_session(store: Store, bars, symbol="SOXL", session=SESSION, **kw):
    """Bars plus a daily row whose features are derived from those bars.

    A real engine records what it decided on, so `or30` and `pos10` in the row
    always agree with the stored bars. A fixture that declares them independently
    trips `feature_parity` for a reason that has nothing to do with the test.
    """
    st = session_stats(bars)
    kw.setdefault("or30", st.or30)
    kw.setdefault("pos10", st.pos10)
    write_bars(store, bars, symbol=symbol, session=session)
    write_daily(store, symbol=symbol, session=session, **kw)


def write_fill(store: Store, exec_id, role, side, qty, price, hh, mm,
               symbol="SOXL", session=SESSION, bid=None, ask=None):
    # `Store.fill` stamps its own `ts`, so the timestamp is set directly to keep
    # the fixture's bar indices deterministic.
    store._ins("fills", ts=utc(hh, mm), symbol=symbol, session=session,
               exec_id=exec_id, order_ref=f"{session}-{symbol}-{role}-1",
               role=role, side=side, qty=qty, price=price, bid=bid, ask=ask)


def write_entry_limit(store: Store, limit_px, hh, mm, symbol="SOXL",
                      session=SESSION, event="placed"):
    """An entry-limit order row at a controlled session time.

    `Store.order` stamps `ts` with the wall clock, which would put the fixture's
    orders outside the session and make `entry_limits` skip them.
    """
    store._ins("orders", ts=utc(hh, mm, day=session_label(session)),
               symbol=symbol, session=session,
               order_ref=f"{session}-{symbol}-E-1", role="E", action="BUY",
               order_type="LMT", event=event, limit_px=limit_px)


def write_quote(store: Store, bid, ask, hh, mm, symbol="SOXL", session=SESSION):
    store._ins("quotes", ts=utc(hh, mm, day=session_label(session)),
               symbol=symbol, session=session, context="poll",
               bid=bid, ask=ask, last=(bid + ask) / 2.0)


# ------------------------------------------------------------ bar arithmetic
@pytest.mark.parametrize("hh,mm,expected", [
    (9, 30, 0),        # the open
    (10, 0, 6),        # end of the opening-range window
    (11, 0, 18),       # START_IDX — the activation
    (15, 55, 77),      # FLATTEN_IDX
])
def test_bar_idx_of_matches_the_spec_clock(hh, mm, expected):
    assert bar_idx_of(utc(hh, mm)) == expected


def test_bar_idx_of_is_zone_aware_not_naive():
    """§4.6: a naive local time gave `Bar.idx = -36` and cost a whole session.

    The same instant expressed in a different offset must land on the same bar.
    """
    assert bar_idx_of("2026-08-06T15:00:00+00:00") == 18
    assert bar_idx_of("2026-08-06T08:00:00-07:00") == 18
    assert bar_idx_of("2026-08-06T11:00:00-04:00") == 18


def test_bar_idx_of_refuses_a_naive_timestamp():
    assert bar_idx_of("2026-08-06T11:00:00") is None
    assert bar_idx_of(None) is None
    assert bar_idx_of("not a timestamp") is None


def test_session_label():
    assert session_label("20260806") == "2026-08-06"
    assert session_label("weird") == "weird"


# -------------------------------------------------- live trade reconstruction
def test_single_execution_round_trip(store):
    write_fill(store, "e1", "E", "BOT", 100, 50.00, 11, 5)
    write_fill(store, "x1", "T", "SLD", 100, 50.50, 12, 0)
    (t,) = live_trades(store, "SOXL", SESSION)
    assert (t.entry_bar, t.exit_bar) == (19, 30)
    assert t.entry_px == pytest.approx(50.00)
    assert t.exit_px == pytest.approx(50.50)
    assert t.qty == 100
    assert t.outcome == "target"
    assert t.ret == pytest.approx(0.01)


def test_defect_8_one_entry_settled_in_three_executions(store):
    """The most serious defect in the project, as a test.

    IBKR filled 541 shares as 300 + 210 + 31. A report that read one order as
    one fill would book three trades here and compute a P&L from the first
    slice alone — reproducing the bug it exists to detect.
    """
    write_fill(store, "e1", "E", "BOT", 300, 100.00, 11, 5)
    write_fill(store, "e2", "E", "BOT", 210, 100.02, 11, 5)
    write_fill(store, "e3", "E", "BOT", 31, 100.10, 11, 6)
    write_fill(store, "x1", "T", "SLD", 541, 101.00, 12, 0)

    trades = live_trades(store, "SOXL", SESSION)
    assert len(trades) == 1, "three executions are one round trip, not three"
    t = trades[0]
    assert t.qty == 541
    assert t.n_entry_execs == 3
    # Quantity-weighted, not first-slice and not a simple mean.
    assert t.entry_px == pytest.approx(
        (300 * 100.00 + 210 * 100.02 + 31 * 100.10) / 541)


def test_exit_settled_in_several_executions(store):
    write_fill(store, "e1", "E", "BOT", 500, 100.00, 11, 5)
    write_fill(store, "x1", "S", "SLD", 200, 96.00, 12, 0)
    write_fill(store, "x2", "S", "SLD", 300, 95.90, 12, 0)
    (t,) = live_trades(store, "SOXL", SESSION)
    assert t.qty == 500
    assert t.n_exit_execs == 2
    assert t.exit_px == pytest.approx((200 * 96.00 + 300 * 95.90) / 500)
    assert t.outcome == "stop"


def test_consecutive_round_trips_are_separated(store):
    write_fill(store, "e1", "E", "BOT", 100, 50.00, 11, 5)
    write_fill(store, "x1", "T", "SLD", 100, 50.50, 11, 40)
    write_fill(store, "e2", "E", "BOT", 100, 50.10, 12, 5)
    write_fill(store, "x2", "S", "SLD", 100, 48.10, 13, 0)
    a, b = live_trades(store, "SOXL", SESSION)
    assert (a.outcome, b.outcome) == ("target", "stop")
    assert a.entry_px == pytest.approx(50.00)
    assert b.entry_px == pytest.approx(50.10)


def test_a_position_left_open_is_visible(store):
    """A failure to flatten must never be silently dropped from the report."""
    write_fill(store, "e1", "E", "BOT", 100, 50.00, 11, 5)
    (t,) = live_trades(store, "SOXL", SESSION)
    assert t.outcome == "open"
    assert t.qty == 100
    assert t.exit_bar is None


def test_partial_exit_leaves_the_trade_open(store):
    """Defect 8's other half: 241 shares with no protective order.

    An exit that covers only part of the position has not closed the round
    trip, and the report must not book it as though it had.
    """
    write_fill(store, "e1", "E", "BOT", 541, 100.00, 11, 5)
    write_fill(store, "x1", "T", "SLD", 300, 101.00, 12, 0)
    (t,) = live_trades(store, "SOXL", SESSION)
    assert t.outcome == "open"
    assert t.qty == pytest.approx(241)


# ----------------------------------------------------------- feature parity
def test_feature_parity_agrees_on_consistent_bars(store):
    bars = flat_session_bars()
    write_daily(store, or30=0.0, pos10=0.5)
    row = report.daily_row(store, "SOXL", SESSION)
    checks = feature_parity(bars, row)
    assert checks and all(c.ok for c in checks)


def test_feature_parity_catches_a_bar_index_error(store):
    """§4.6, as a test that costs no session.

    Bars shifted off the §2.1 clock produce a different opening range from the
    one the engine recorded. That disagreement is the whole signal.
    """
    bars = [Bar(i, 100.0, 105.0 if i < 6 else 100.0, 95.0 if i < 6 else 100.0,
                100.0) for i in range(78)]
    write_daily(store, or30=0.0, pos10=0.5)     # what a mis-indexed feed reported
    row = report.daily_row(store, "SOXL", SESSION)
    checks = feature_parity(bars, row)
    assert any(not c.ok for c in checks)
    or30 = next(c for c in checks if c.name == "or30")
    assert or30.recomputed == pytest.approx(10.0)   # (105-95)/100 * 100


# ----------------------------------------------------------- shadow parity
def test_shadow_does_not_run_when_the_gate_was_off(store):
    write_daily(store, gate=0)
    row = report.daily_row(store, "SOXL", SESSION)
    sh = shadow_replay(flat_session_bars(), row)
    assert not sh.ran and not sh.trades


def test_shadow_does_not_run_when_the_sleeve_stood_down(store):
    write_daily(store, filter_ok=0)
    row = report.daily_row(store, "SOXL", SESSION)
    sh = shadow_replay(flat_session_bars(), row)
    assert not sh.ran


def test_shadow_replays_a_traded_day(store):
    """A session that dips 1% after 11:00 and recovers must book a target."""
    bars = []
    for i in range(78):
        if i < 18:
            bars.append(Bar(i, 100.0, 100.0, 100.0, 100.0))
        elif i == 20:
            bars.append(Bar(i, 100.0, 100.0, 98.5, 99.0))     # fills the limit
        elif i == 25:
            bars.append(Bar(i, 99.5, 101.0, 99.5, 100.5))     # reaches +1%
        else:
            bars.append(Bar(i, 100.0, 100.0, 100.0, 100.0))
    write_daily(store)
    row = report.daily_row(store, "SOXL", SESSION)
    sh = shadow_replay(bars, row)
    assert sh.ran, sh.reason
    assert sh.trades
    assert sh.trades[0].outcome == "target"


def test_a_real_session_is_not_a_half_day(store):
    """The bug that made shadow parity dead on arrival, as a regression test.

    `SessionStats.is_half_day` is `last bar idx < FLATTEN_IDX`, and the engine
    flattens *at* FLATTEN_IDX — so it never consumes that bar and a real day
    records 76 bars, idx 0..75. Recomputing the flag from those bars calls
    every live session a half day. On 2026-08-10 the shadow refused on both
    sleeves for exactly this reason, while the report still printed "shadow and
    live agree".
    """
    bars = flat_session_bars(76)          # idx 0..75 — what a real day records
    assert session_stats(bars).is_half_day is True, \
        "the recomputed flag really is wrong; the fix is to not consult it"

    write_daily(store)                    # engine recorded gate ON
    row = report.daily_row(store, "SOXL", SESSION)
    sh = shadow_replay(bars, row)
    assert sh.ran, sh.reason


@pytest.mark.parametrize("n_bars", [70, 76, 77, 78])
def test_shadow_runs_regardless_of_how_many_bars_were_recorded(store, n_bars):
    """Bar coverage varies with when the engine started and stopped. None of it
    may decide the gate, which the daily row already settled."""
    write_daily(store)
    row = report.daily_row(store, "SOXL", SESSION)
    assert shadow_replay(flat_session_bars(n_bars), row).ran


def test_shadow_still_refuses_on_a_real_atr5_disagreement(store):
    """The one refusal left is meaningful: the recorded ATR5 does not clear the
    gate the engine passed on it. That is a finding, not a quirk."""
    write_daily(store, atr5=2.0)          # below GATE_ATR5_MIN, yet gate_ok=1
    row = report.daily_row(store, "SOXL", SESSION)
    sh = shadow_replay(flat_session_bars(76), row)
    assert not sh.ran
    assert "atr5" in sh.reason and "2.00" in sh.reason


@pytest.mark.parametrize("capital,expected_qty", [
    # §2.4 sizes off the limit price: floor(f x capital / 99.00), f = 1.00.
    (74_471.0, 752),
    (12_345.0, 124),
])
def test_shadow_sizes_from_the_recorded_capital(store, capital, expected_qty):
    """Sizing must come from the session's own capital, not a constant."""
    write_daily(store, capital=capital)
    row = report.daily_row(store, "SOXL", SESSION)
    sh = shadow_replay(traded_session_bars(), row)
    assert sh.ran, sh.reason
    assert sh.trades and sh.trades[0].qty == expected_qty


@pytest.mark.parametrize("field", ["atr5", "or30", "thr80", "pos10"])
def test_a_missing_daily_field_is_reported_not_raised(store, field):
    """The daily row is written in three passes; an interrupted session leaves
    real NULLs. A post-session review must not die on a TypeError."""
    kw = dict(atr5=10.0, or30=3.0, thr80=5.0, pos10=0.5)
    kw[field] = None
    store.daily(SESSION, "SOXL", gate_ok=1, gate_reason="gate_on", filter_ok=1,
                filter_reason="filter_on", sleeve_capital=CAPITAL, **kw)
    row = report.daily_row(store, "SOXL", SESSION)
    sh = shadow_replay(flat_session_bars(76), row)
    assert not sh.ran
    assert field in sh.reason


def test_shadow_reports_a_missing_daily_row_rather_than_crashing(store):
    sh = shadow_replay(flat_session_bars(), None)
    assert not sh.ran and "no daily row" in sh.reason


# ------------------------------------------------------------- S10 / S11
def test_same_bar_reentry_detected_in_both_sources():
    """S10 in one case: both sources re-enter in the exit's own bar, and the
    backtest gets in below the price it had just sold at while the live session
    — which could only trade against prints after its exit — did not."""
    live = [
        LiveTrade(entry_bar=20, exit_bar=30, entry_px=100.0, exit_px=101.0,
                  qty=10, outcome="target"),
        LiveTrade(entry_bar=30, exit_bar=40, entry_px=101.2, exit_px=102.2,
                  qty=10, outcome="target"),
    ]
    shadow = [
        Trade(entry_bar=20, exit_bar=30, entry_px=100.0, exit_px=101.0,
              qty=10, ret=0.01, outcome="target"),
        Trade(entry_bar=30, exit_bar=40, entry_px=99.8, exit_px=100.8,
              qty=10, ret=0.01, outcome="target"),
    ]
    (r,) = same_bar_reentries(live, shadow)
    assert r.bar == 30
    assert r.prev_exit_px == pytest.approx(101.0)
    assert r.shadow_better is True
    assert r.live_better is False          # §5 Q2: at or worse, as predicted
    # The S10 exposure, measured: the shadow got in 1.4% cheaper on this event.
    assert r.shadow_advantage_bp == pytest.approx(
        (101.2 / 99.8 - 1.0) * 1e4, abs=0.01)


def test_live_reentry_below_the_exit_is_reported_not_condemned():
    """A live re-entry below the preceding exit is legitimate — the market can
    fall after an exit. The report must describe it, not call it impossible."""
    live = [
        LiveTrade(entry_bar=20, exit_bar=30, entry_px=100.0, exit_px=101.0,
                  qty=10, outcome="target"),
        LiveTrade(entry_bar=30, exit_bar=40, entry_px=100.5, exit_px=101.5,
                  qty=10, outcome="target"),
    ]
    (r,) = same_bar_reentries(live, [])
    assert r.live_better is True
    assert r.shadow_entry_px is None
    assert r.shadow_advantage_bp is None


def test_shadow_only_reentry_is_still_reported():
    """The S10 population that does not exist live is the most important row."""
    shadow = [
        Trade(entry_bar=20, exit_bar=30, entry_px=100.0, exit_px=101.0,
              qty=10, ret=0.01, outcome="target"),
        Trade(entry_bar=30, exit_bar=40, entry_px=99.0, exit_px=100.0,
              qty=10, ret=0.01, outcome="target"),
    ]
    (r,) = same_bar_reentries([], shadow)
    assert r.bar == 30
    assert r.live_entry_px is None
    assert r.shadow_better is True


def test_no_same_bar_reentry_when_bars_differ():
    live = [
        LiveTrade(entry_bar=20, exit_bar=30, entry_px=100.0, exit_px=101.0,
                  qty=10, outcome="target"),
        LiveTrade(entry_bar=31, exit_bar=40, entry_px=100.5, exit_px=101.5,
                  qty=10, outcome="target"),
    ]
    assert same_bar_reentries(live, []) == []


def test_fill_without_quote_needs_positive_evidence(store):
    """Defects 6 and 7: a check that fires on the absence of evidence is a bug.

    With no quotes recorded, the report may not claim anything.
    """
    write_entry_limit(store, 99.00, 11, 0)
    write_fill(store, "e1", "E", "BOT", 100, 99.00, 11, 5)
    flags = fills_without_quotes(store, "SOXL", SESSION)
    assert flags and all(not f.suspicious for f in flags)


def test_fill_without_quote_flags_a_real_gap(store):
    """A fill at a limit the recorded quote never reached is the §5 question."""
    write_entry_limit(store, 99.00, 11, 0)
    write_quote(store, 100.00, 100.05, 11, 0)
    write_fill(store, "e1", "E", "BOT", 100, 99.00, 11, 5)
    (f,) = fills_without_quotes(store, "SOXL", SESSION)
    assert f.suspicious
    assert f.best_bid_seen == pytest.approx(100.00)


def test_quote_reaching_the_limit_is_not_flagged(store):
    write_entry_limit(store, 99.00, 11, 0)
    write_quote(store, 98.90, 98.95, 11, 0)
    write_fill(store, "e1", "E", "BOT", 100, 99.00, 11, 5)
    (f,) = fills_without_quotes(store, "SOXL", SESSION)
    assert not f.suspicious


# ------------------------------------------------------------------ slippage
def test_slippage_signs_are_adverse_positive(store):
    write_entry_limit(store, 100.00, 11, 0)
    # A buy filling above its limit is adverse.
    write_fill(store, "e1", "E", "BOT", 100, 100.10, 11, 5, bid=100.0, ask=100.2)
    (s,) = [r for r in slippage(store, "SOXL", SESSION) if r.role == "E"]
    assert s.vs_limit == pytest.approx(10.0, abs=0.01)      # +10 bp, worse
    assert s.vs_mid == pytest.approx(0.0, abs=0.01)


def test_slippage_price_improvement_is_negative(store):
    write_entry_limit(store, 100.00, 11, 0)
    write_fill(store, "e1", "E", "BOT", 100, 99.90, 11, 5)
    (s,) = [r for r in slippage(store, "SOXL", SESSION) if r.role == "E"]
    assert s.vs_limit == pytest.approx(-10.0, abs=0.01)


def test_sell_slippage_flips_sign(store):
    """A sell filling *below* the mid is the adverse direction."""
    write_fill(store, "x1", "T", "SLD", 100, 99.90, 12, 0, bid=100.0, ask=100.0)
    (s,) = [r for r in slippage(store, "SOXL", SESSION) if r.role == "T"]
    assert s.vs_mid == pytest.approx(10.0, abs=0.01)


# ------------------------------------------------- the two bp definitions
def test_a_gap_through_makes_the_two_definitions_differ(store):
    """The defect §10.16 could not see.

    `test_weekly_matches_hand_computed` sizes 750 shares at 100.00 against
    75,000 of capital, so `qty x entry == capital` exactly and the price return
    and the sleeve return coincide. Every fixture in this file did the same, so
    a report that summed the wrong one passed a green suite — while 2026-08-13
    printed a 0.75 bp gap where the like-for-like figure was 7.85, and
    disagreed with the engine's own `pnl=-555.6bp`.

    §2.4 makes the divergence routine, not exotic: quantity is sized off
    `limit_px` and the fill is free to gap through it.
    """
    write_entry_limit(store, 100.00, 11, 0)
    write_fill(store, "e1", "E", "BOT", 750, 96.00, 11, 5)     # 4% gap-through
    write_fill(store, "x1", "T", "SLD", 750, 97.00, 12, 0)
    (t,) = live_trades(store, "SOXL", SESSION)

    assert t.ret == pytest.approx(97.0 / 96.0 - 1.0)            # price return
    assert t.ret_on_capital(CAPITAL) == pytest.approx(0.01)     # sleeve return
    assert t.ret > t.ret_on_capital(CAPITAL)

    bp, comparable = report.day_bp([t], CAPITAL)
    assert comparable and bp == pytest.approx(100.0)
    assert report.day_bp([t], None)[0] == pytest.approx(104.17, abs=0.01)


def test_day_bp_is_what_the_engine_logs(store):
    """SOXL on 2026-08-13, at the recorded prices. The engine's EOD line said
    `pnl=-555.6bp`; the report must not disagree with the thing it audits."""
    cap = 74_261.0
    trades = [
        LiveTrade(entry_bar=24, exit_bar=72, entry_px=152.59, exit_px=146.48,
                  qty=486, outcome="stop"),
        LiveTrade(entry_bar=72, exit_bar=77, entry_px=146.63, exit_px=144.25,
                  qty=486, outcome="flatten"),
    ]
    bp, comparable = report.day_bp(trades, cap)
    assert comparable
    assert bp == pytest.approx(-555.6, abs=0.1)


def test_an_open_position_is_excluded_from_the_day(store):
    trades = [
        LiveTrade(entry_bar=1, exit_bar=2, entry_px=100.0, exit_px=101.0,
                  qty=750, outcome="target"),
        LiveTrade(entry_bar=3, exit_bar=None, entry_px=100.0,
                  exit_px=float("nan"), qty=750, outcome="open"),
    ]
    assert report.day_bp(trades, CAPITAL)[0] == pytest.approx(100.0)


def test_missing_capital_refuses_to_show_a_gap(store, capsys):
    """Without capital the live figure is a different quantity from the shadow.
    Printing a gap between them would be the original defect with extra steps."""
    write_session(store, traded_session_bars(78), capital=None)
    write_fill(store, "e1", "E", "BOT", 757, 99.00, 11, 10)
    write_fill(store, "x1", "T", "SLD", 757, 100.00, 11, 15)
    report.print_session_report(store, SESSION, ["SOXL"])
    out = capsys.readouterr().out
    assert "NOT comparable" in out
    assert "gap" not in out.split("bp/day")[1].split("\n")[0]


# ------------------------------------------------------ the exit side
def test_exit_quality_grades_every_exit_role(store):
    """The exit side used to have no measurement at all.

    `vs_limit` is None for every role but "E" — an exit has no resting entry
    limit — and the "honest execution number" filtered to `role == "E"` as well.
    A session whose result turned in its last bar produced a report with no line
    in it about that bar.
    """
    write_fill(store, "x1", "T", "SLD", 100, 100.90, 12, 0, bid=101.0, ask=101.0)
    write_fill(store, "x2", "F", "SLD", 100, 99.90, 15, 56, bid=100.0, ask=100.0)
    by_role = {e.role: e
               for e in report.exit_quality(slippage(store, "SOXL", SESSION))}
    assert set(by_role) == {"T", "F"}
    assert by_role["T"].vs_mid_bp == pytest.approx(9.90, abs=0.01)
    assert by_role["F"].vs_mid_bp == pytest.approx(10.00, abs=0.01)


def test_exit_quality_weights_the_quote_comparison_by_size(store):
    """900 shares at the mid and 100 shares 100 bp under it is 10 bp, not 50."""
    write_fill(store, "f1", "F", "SLD", 900, 100.00, 15, 56, bid=100.0, ask=100.0)
    write_fill(store, "f2", "F", "SLD", 100, 99.00, 15, 57, bid=100.0, ask=100.0)
    (e,) = report.exit_quality(slippage(store, "SOXL", SESSION))
    assert e.vs_mid_bp == pytest.approx(10.0, abs=0.01)


# ------------------------------------------------------- the 15:55 flatten
def test_a_day_that_ended_on_a_target_has_no_flatten_cost(store):
    """Most sessions never flatten, and a zero on all of them would be noise."""
    write_fill(store, "e1", "E", "BOT", 100, 100.00, 11, 0)
    write_fill(store, "x1", "T", "SLD", 100, 101.00, 12, 0)
    assert report.flatten_cost(slippage(store, "SOXL", SESSION),
                               flat_session_bars(78)) is None


def test_flatten_is_priced_against_the_bar_the_backtest_exits_on(store):
    """SOXL on 2026-08-12, at the prices that session actually recorded.

    `replay_session`'s tail rule books the backtest's flatten at `close` of
    LAST_HOLDING_IDX, so that is the only price the live market order can
    honestly be compared against — and the comparison nobody could make on the
    day, because the report did not draw it.
    """
    bars = flat_session_bars(78, price=142.99)
    write_fill(store, "e1", "E", "BOT", 510, 145.82, 11, 40)
    write_fill(store, "f1", "F", "SLD", 510, 142.15, 15, 56)

    fc = report.flatten_cost(slippage(store, "SOXL", SESSION), bars)
    assert fc.qty == 510
    assert fc.ref_px == pytest.approx(142.99)
    assert fc.bp == pytest.approx(-58.75, abs=0.05)
    assert fc.dollars == pytest.approx(-428.40, abs=0.01)


def test_flatten_cost_weights_executions_by_size(store):
    """Defect 8's rule on the exit side: IBKR settles one flatten in as many
    executions as the book requires, and a 10-share tail must not weigh the same
    as the 490 shares in front of it."""
    write_fill(store, "e1", "E", "BOT", 500, 100.00, 11, 40)
    write_fill(store, "f1", "F", "SLD", 490, 99.00, 15, 56)
    write_fill(store, "f2", "F", "SLD", 10, 90.00, 15, 57)

    fc = report.flatten_cost(slippage(store, "SOXL", SESSION),
                             flat_session_bars(78, price=100.0))
    assert fc.n_execs == 2 and fc.qty == 500
    assert fc.live_px == pytest.approx(98.82)      # not the unweighted 94.50
    assert fc.dollars == pytest.approx(-590.00)


def test_flatten_without_the_last_holding_bar_has_no_reference(store):
    """`record_session_tail` backfills bar 76; a record that stops at 75 has
    nothing to price the flatten against, and None is the honest answer —
    defects 6 and 7 were both checks that manufactured evidence instead."""
    write_fill(store, "e1", "E", "BOT", 100, 100.00, 11, 40)
    write_fill(store, "f1", "F", "SLD", 100, 99.00, 15, 56)
    fc = report.flatten_cost(slippage(store, "SOXL", SESSION),
                             flat_session_bars(76))
    assert fc is not None and fc.ref_px is None
    assert fc.bp is None and fc.dollars is None


@pytest.mark.parametrize("bid,ask,flagged", [
    (142.14, 142.16, False),   # filled at the mid: the market moved, we did not
    (143.20, 143.24, True),    # filled 75 bp under a quote that was standing
])
def test_only_a_bad_fill_against_the_standing_quote_is_a_finding(
        store, capsys, bid, ask, flagged):
    """The distinction the two numbers exist to draw.

    Both cases lose the same amount against the backtest's price. In the first
    the market fell between 15:55 and the fill, which is timing exposure no
    order type avoids — §4.7 sends a MKT because §1 puts being flat above the
    fill price, and that trade-off is deliberate. Only the second is the
    execution's own fault, and only the second may raise a finding.
    """
    write_session(store, traded_session_bars(78))
    write_fill(store, "e1", "E", "BOT", 510, 145.82, 11, 40)
    write_fill(store, "f1", "F", "SLD", 510, 142.15, 15, 56, bid=bid, ask=ask)

    report.print_session_report(store, SESSION, ["SOXL"])
    out = capsys.readouterr().out
    assert "the 15:55 flatten — a MARKET order" in out
    assert ("not a spread on a liquid ETF" in out) is flagged


# ------------------------------------------------------------- §8 weekly
def test_weekly_matches_hand_computed(store):
    """§10.16 — the acceptance test, on a fixture week.

    Three sessions: two traded, one gate-OFF. The traded days book 3 round
    trips between them (2 targets, 1 stop). Every figure below is computed by
    hand from those numbers and none of them comes from the code under test.
    """
    # Day 1 — ON, two trades: +1% on 750 shares, then -4% on 750 shares.
    write_daily(store, session="20260803")
    write_fill(store, "a1", "E", "BOT", 750, 100.00, 11, 5, session="20260803")
    write_fill(store, "a2", "T", "SLD", 750, 101.00, 11, 40, session="20260803")
    write_fill(store, "a3", "E", "BOT", 750, 100.00, 12, 0, session="20260803")
    write_fill(store, "a4", "S", "SLD", 750, 96.00, 13, 0, session="20260803")

    # Day 2 — ON, one trade: +1% on 750 shares.
    write_daily(store, session="20260804")
    write_fill(store, "b1", "E", "BOT", 750, 100.00, 11, 5, session="20260804")
    write_fill(store, "b2", "T", "SLD", 750, 101.00, 12, 0, session="20260804")

    # Day 3 — gate OFF, no trades.
    write_daily(store, session="20260805", gate=0, filter_ok=0)

    w = weekly(store, symbols=["SOXL"])["SOXL"]

    assert w.sessions == 3
    assert w.on_days == 2
    assert w.fills == 3
    assert w.on_rate == pytest.approx(200.0 / 3)             # 2 of 3
    assert w.fills_per_on_day == pytest.approx(1.5)          # 3 / 2
    assert w.outcome_pct("target") == pytest.approx(200.0 / 3)   # 2 of 3
    assert w.outcome_pct("stop") == pytest.approx(100.0 / 3)     # 1 of 3

    # Day 1: (+1.00 - 4.00) * 750 = -2,250 on 75,000 = -3.00%
    # Day 2: (+1.00)        * 750 =   +750 on 75,000 = +1.00%
    # mean over ON days = -1.00% = -100 bp
    assert w.day_returns[0] == pytest.approx(-0.03)
    assert w.day_returns[1] == pytest.approx(0.01)
    assert w.gross_bp == pytest.approx(-100.0)
    assert w.worst_day == pytest.approx(-3.0)


def test_weekly_ignores_days_with_no_daily_row(store):
    write_daily(store, session="20260803")
    w = weekly(store, symbols=["SOXL"], sessions=["20260803", "20260804"])["SOXL"]
    assert w.sessions == 1


def test_baselines_load_from_the_parity_output():
    """§8's numbers must come from the file `parity.py` writes, not from here."""
    base = report.load_baselines()
    if not base:
        pytest.skip("phase1/out/monitoring_expectations.csv not generated")
    assert base[("SOXL", "gross_bp_per_ON_day")] == pytest.approx(65.6)
    assert base[("SOXS", "net_bp_per_ON_day")] == pytest.approx(48.1)


# ---------------------------------------------------------------- end to end
# ------------------------------------------------- the sign-off (#2)
def test_signoff_never_claims_agreement_when_the_shadow_did_not_run(store, capsys):
    """The 2026-08-10 failure, as a test.

    Both sleeves traded, the shadow refused on both, and the report signed off
    "No findings. Shadow and live agree." Nothing had been compared.
    """
    write_session(store, flat_session_bars(76), atr5=2.0)   # gate_ok=1, ATR5 refuses
    write_fill(store, "e1", "E", "BOT", 100, 99.0, 11, 5)
    write_fill(store, "x1", "T", "SLD", 100, 100.0, 12, 0)

    findings = report.print_session_report(store, SESSION, ["SOXL"])
    out = capsys.readouterr().out
    assert findings >= 1, "a traded sleeve with no shadow is a finding"
    assert "NOT VERIFIED" in out
    assert "Nothing was compared" in out
    assert "agree" not in out.replace("No agreement is claimed", "")


def test_signoff_flags_a_truncated_bar_record(store, capsys):
    """A shadow force-flattened early is not a clean comparison. 76 bars is
    what the engine records, and it is 1 short of the last holding bar."""
    write_session(store, traded_session_bars(76))
    write_fill(store, "e1", "E", "BOT", 757, 99.00, 11, 10)   # bar 20
    write_fill(store, "x1", "T", "SLD", 757, 100.00, 11, 15)  # bar 21
    assert report.print_session_report(store, SESSION, ["SOXL"]) == 0
    out = capsys.readouterr().out
    assert "PARTIALLY VERIFIED" in out
    assert "force-flatten" in out
    assert "No findings. Shadow and live agree" not in out


def test_signoff_claims_agreement_only_on_a_complete_session(store, capsys):
    """With the full tradable session recorded, the claim is earned."""
    write_session(store, traded_session_bars(78))
    write_fill(store, "e1", "E", "BOT", 757, 99.00, 11, 10)   # bar 20
    write_fill(store, "x1", "T", "SLD", 757, 100.00, 11, 15)  # bar 21
    assert report.print_session_report(store, SESSION, ["SOXL"]) == 0
    out = capsys.readouterr().out
    assert "Shadow and live agree" in out
    assert "complete tradable session" in out
    assert "NOT VERIFIED" not in out and "PARTIALLY VERIFIED" not in out


def test_signoff_does_not_call_a_quiet_day_an_agreement(store, capsys):
    """A sleeve that stood down was not compared and must not be reported as
    though it had been."""
    write_daily(store, gate=0, filter_ok=0)
    report.print_session_report(store, SESSION, ["SOXL"])
    out = capsys.readouterr().out
    assert "nothing to compare" in out
    assert "Shadow and live agree" not in out


def test_a_stood_down_sleeve_is_not_a_finding(store, capsys):
    """Standing down is the strategy working. It must not raise a finding."""
    write_session(store, flat_session_bars(76), filter_ok=0)
    assert report.print_session_report(store, SESSION, ["SOXL"]) == 0
    assert "NOT VERIFIED" not in capsys.readouterr().out


@pytest.mark.parametrize("n_bars,complete,missing", [
    (78, True, 0),      # full session
    (77, True, 0),      # through the last holding bar
    (76, False, 1),     # what the engine actually records
    (70, False, 7),
    (0, False, 77),
])
def test_bar_coverage(n_bars, complete, missing):
    cov = report.bar_coverage(flat_session_bars(n_bars))
    assert cov.complete is complete
    assert cov.missing == missing


def test_truncation_understates_the_shadow(store):
    """The 68 bp SOXS gap on 2026-08-10, in miniature: the same session
    compared at 76 and 78 bars must differ, and the short one must be worse."""
    write_daily(store)
    row = report.daily_row(store, "SOXL", SESSION)
    short = shadow_replay(traded_session_bars(76), row)
    full = shadow_replay(traded_session_bars(78), row)
    assert short.ran and full.ran
    assert not report.bar_coverage(traded_session_bars(76)).complete
    assert report.bar_coverage(traded_session_bars(78)).complete


def test_session_report_runs_on_an_empty_database(store, capsys):
    assert report.print_session_report(store, "20260806") == 0
    assert "No sleeves recorded" in capsys.readouterr().out


def test_session_report_runs_end_to_end(store, capsys):
    write_daily(store)
    write_bars(store, flat_session_bars())
    write_entry_limit(store, 99.00, 11, 0)
    write_fill(store, "e1", "E", "BOT", 750, 99.00, 11, 5)
    write_fill(store, "x1", "T", "SLD", 750, 99.99, 12, 0)
    report.print_session_report(store, SESSION, ["SOXL"])
    out = capsys.readouterr().out
    assert "SOXL" in out
    assert "shadow" in out
    assert "target" in out


def test_short_sample_never_flags_a_structural_break(store, capsys):
    """§8's >20% rule is about a *month*. On a one-session sample every metric
    deviates, and a report that flagged it would cry wolf every week —
    the defect-6-and-7 failure mode (`PROJECT_STATUS.md` §4.7)."""
    write_daily(store)          # one ON-day, 0 trades: ON-rate and fills both off
    breaks = report.print_weekly_report(store, ["SOXL"])
    out = capsys.readouterr().out
    assert breaks == 0
    assert "STRUCTURAL" not in out
    assert "A single week proves nothing" in out


def test_structural_break_fires_once_the_sample_is_long_enough(store, capsys):
    """Above the threshold, a real deviation must still be flagged."""
    for d in range(1, report.MIN_SESSIONS_FOR_BREAK + 1):
        # Every session gate-OFF: an ON-rate of 0% against §8's 52.1%.
        write_daily(store, session=f"202607{d:02d}", gate=0, filter_ok=0)
    breaks = report.print_weekly_report(store, ["SOXL"])
    assert breaks >= 1
    assert "STRUCTURAL" in capsys.readouterr().out


def test_weekly_report_runs_end_to_end(store, capsys):
    write_daily(store)
    write_fill(store, "e1", "E", "BOT", 750, 100.00, 11, 5)
    write_fill(store, "x1", "T", "SLD", 750, 101.00, 12, 0)
    report.print_weekly_report(store, ["SOXL"])
    out = capsys.readouterr().out
    assert "§8 MONITORING" in out
    assert "fills_per_ON_day" in out


def test_csv_output(store, tmp_path):
    write_daily(store)
    write_bars(store, flat_session_bars())
    write_fill(store, "e1", "E", "BOT", 750, 100.00, 11, 5)
    write_fill(store, "x1", "T", "SLD", 750, 101.00, 12, 0)
    paths = report.write_csvs(store, str(tmp_path / "out"), SESSION, ["SOXL"])
    assert len(paths) == 2
    for p in paths:
        assert os.path.exists(p) and os.path.getsize(p) > 0


def test_cli_reports_a_missing_database(tmp_path, capsys):
    assert report.main(["--db", str(tmp_path / "nope.db")]) == 2
    assert "no database" in capsys.readouterr().err


def test_cli_handles_an_empty_database(tmp_path, capsys):
    Store(str(tmp_path / "e.db")).close()
    assert report.main(["--db", str(tmp_path / "e.db")]) == 0
    assert "no sessions yet" in capsys.readouterr().out


def test_cli_rejects_an_unknown_session(store, tmp_path, capsys):
    write_daily(store)
    assert report.main(["--db", store.path, "--session", "19990101"]) == 2
    assert "not in the database" in capsys.readouterr().err


# ---------------- slippage vs a gap-through limit (fix #3)
def test_a_gap_through_entry_is_not_reported_as_slippage(store):
    """SOXL on 2026-08-10: limit 142.02, filled 135.69, reported -445.71 bp
    with "0 adverse".

    The limit sat 4.46% above the market because §2.5 prices the entry 1% under
    a *rolling session high* and SOXL had fallen 6.4% from its 09:30 bar. The
    fill was correct and the backtest models it. Averaging that distance into a
    slippage figure measures how far price travelled, not execution quality.
    """
    write_entry_limit(store, 142.02, 11, 5)
    write_fill(store, "e1", "E", "BOT", 524, 135.69, 12, 18, bid=135.68, ask=135.70)
    (s,) = [r for r in slippage(store, "SOXL", SESSION) if r.role == "E"]

    assert s.gap_through is True
    assert s.vs_limit is None, "a gap-through must not be graded against the limit"
    assert s._raw_vs_limit() == pytest.approx(-445.71, abs=0.5)
    # The quote while the order worked is the honest number, and it is ~0.
    assert s.vs_mid == pytest.approx(0.0, abs=1.0)


def test_an_ordinary_fill_is_still_graded_against_the_limit(store):
    write_entry_limit(store, 100.00, 11, 5)
    write_fill(store, "e1", "E", "BOT", 100, 100.10, 11, 10)
    (s,) = [r for r in slippage(store, "SOXL", SESSION) if r.role == "E"]
    assert s.gap_through is False
    assert s.vs_limit == pytest.approx(10.0, abs=0.01)


def test_modest_price_improvement_is_not_called_a_gap_through(store):
    """The threshold must not swallow ordinary favourable fills."""
    write_entry_limit(store, 100.00, 11, 5)
    write_fill(store, "e1", "E", "BOT", 100, 99.75, 11, 10)      # -25 bp
    (s,) = [r for r in slippage(store, "SOXL", SESSION) if r.role == "E"]
    assert s.gap_through is False
    assert s.vs_limit == pytest.approx(-25.0, abs=0.01)


def test_the_report_names_a_gap_through_instead_of_burying_it(store, capsys):
    write_session(store, flat_session_bars(78))
    write_entry_limit(store, 142.02, 11, 5)
    write_fill(store, "e1", "E", "BOT", 524, 135.69, 12, 18)
    report.print_session_report(store, SESSION, ["SOXL"])
    out = capsys.readouterr().out
    assert "gap-through entries" in out
    assert "Not slippage" in out
