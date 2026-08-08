"""
Stage 6 — the shadow-parity report (§10.16).

The acceptance test asks that the report "matches hand-computed values on a
fixture week". These build a store by hand, so every number the report prints
has an arithmetic answer written next to it in the test.
"""

from __future__ import annotations

import pytest

from report import SessionReport, weekly
from store import Store

SESSION = "20260807"


def _store(tmp_path, name="r.db") -> tuple[Store, str]:
    path = str(tmp_path / name)
    return Store(path), path


def _session(st: Store, symbol="SOXS", capital=75_000.0, filter_ok=1):
    st.daily(SESSION, symbol, gate_ok=1, gate_reason="atr5_ok",
             filter_ok=filter_ok, filter_reason="ok", atr5=12.0, or30=3.0,
             thr80=5.0, pos10=0.5, account_equity=150_000.0,
             sleeve_capital=capital)


def _fill(st, symbol, exec_id, role, side, qty, price, ts_hint=0, **kw):
    st.fill(symbol, SESSION, exec_id, order_ref=f"{SESSION}-{symbol}-{role}-1",
            role=role, side=side, qty=qty, price=price, **kw)


# ------------------------------------------------- round trips from executions
def test_a_trade_split_across_executions_is_one_round_trip(tmp_path):
    """IBKR settled a 1,680-share entry in 14 pieces on 2026-08-07."""
    st, db = _store(tmp_path)
    _session(st)
    for i, (q, p) in enumerate([(120, 43.35), (560, 43.36), (1000, 43.37)]):
        _fill(st, "SOXS", f"e{i}", "E", "BOT", q, p)
    _fill(st, "SOXS", "x0", "F", "SLD", 1680, 42.2316)

    trades, manual = SessionReport(db, SESSION).live_trades("SOXS")
    assert len(trades) == 1, "one round trip, however many executions"
    t = trades[0]
    assert t.qty == pytest.approx(1680)
    assert t.entry_execs == 3 and t.exit_execs == 1
    vwap = (120 * 43.35 + 560 * 43.36 + 1000 * 43.37) / 1680
    assert t.entry_px == pytest.approx(vwap)
    assert t.outcome == "flatten"
    assert manual == 0


def test_the_reported_bp_matches_the_hand_computation(tmp_path):
    """2026-08-07's actual numbers: -253 bp on a $75,000 sleeve."""
    st, db = _store(tmp_path)
    _session(st)
    _fill(st, "SOXS", "e0", "E", "BOT", 1680, 43.3626)
    _fill(st, "SOXS", "x0", "F", "SLD", 1680, 42.2316)

    t = SessionReport(db, SESSION).live_trades("SOXS")[0][0]
    expected = 1680 * (42.2316 - 43.3626) / 75_000 * 1e4
    assert t.bp_on(75_000) == pytest.approx(expected, abs=0.05)
    assert t.bp_on(75_000) == pytest.approx(-253.3, abs=0.5)


def test_hand_placed_fills_are_counted_but_never_traded(tmp_path):
    """The 1,082-share manual cover on 2026-08-07 was not the engine's trade."""
    st, db = _store(tmp_path, "m.db")
    _session(st, symbol="SOXL")
    st.fill("SOXL", SESSION, "manual-1", order_ref="", role="", side="BOT",
            qty=1082, price=137.22)
    trades, manual = SessionReport(db, SESSION).live_trades("SOXL")
    assert trades == [] and manual == pytest.approx(1082)


# --------------------------------------------------------- evidence quality
def test_a_restart_is_flagged(tmp_path):
    st, db = _store(tmp_path)
    _session(st)
    for _ in range(3):
        st.event("info", "runner", "pre-open 20260807 | ...", session=SESSION)
    flags = SessionReport(db, SESSION).integrity("SOXS")
    assert any("started 3 times" in f for f in flags)


def test_a_late_start_is_flagged(tmp_path):
    st, db = _store(tmp_path)
    _session(st)
    for i in range(20, 30):
        st.bar("SOXS", SESSION, i, 43.0, 43.1, 42.9, 43.0, 1000)
    flags = SessionReport(db, SESSION).integrity("SOXS")
    assert any("first bar seen was idx 20" in f for f in flags)


def test_missing_bars_are_flagged(tmp_path):
    st, db = _store(tmp_path)
    _session(st)
    for i in (0, 1, 2, 40, 41):
        st.bar("SOXS", SESSION, i, 43.0, 43.1, 42.9, 43.0, 1000)
    flags = SessionReport(db, SESSION).integrity("SOXS")
    assert any("missing bar" in f for f in flags)


def test_a_clean_session_carries_no_flags(tmp_path):
    st, db = _store(tmp_path)
    _session(st)
    st.event("info", "runner", "pre-open 20260807 | ...", session=SESSION)
    for i in range(78):
        st.bar("SOXS", SESSION, i, 43.0, 43.1, 42.9, 43.0, 1000)
    assert SessionReport(db, SESSION).integrity("SOXS") == []


# --------------------------------------------------------- the two questions
def test_a_fill_below_the_prevailing_ask_is_reported(tmp_path):
    """§12.3 Q1 — if the simulator does this, paper cannot test A1."""
    st, db = _store(tmp_path)
    _session(st)
    _fill(st, "SOXS", "e0", "E", "BOT", 100, 43.00, bid=43.10, ask=43.12)
    assert len(SessionReport(db, SESSION).fills_without_the_quote("SOXS")) == 1


def test_a_fill_at_the_ask_is_not_reported(tmp_path):
    st, db = _store(tmp_path)
    _session(st)
    _fill(st, "SOXS", "e0", "E", "BOT", 100, 43.12, bid=43.10, ask=43.12)
    assert SessionReport(db, SESSION).fills_without_the_quote("SOXS") == []


def test_a_reentry_after_an_exit_is_measured(tmp_path):
    """§12.3 Q2 — S11 predicts the achieved re-entry is systematically worse."""
    st, db = _store(tmp_path)
    _session(st)
    st.fill("SOXS", SESSION, "e0", order_ref="r-E-1", role="E", side="BOT",
            qty=100, price=43.00)
    st.fill("SOXS", SESSION, "t0", order_ref="r-T-2", role="T", side="SLD",
            qty=100, price=43.43)
    st.fill("SOXS", SESSION, "e1", order_ref="r-E-3", role="E", side="BOT",
            qty=100, price=43.50)
    re = SessionReport(db, SESSION).same_bar_reentries("SOXS")
    assert len(re) == 1
    sold, bought, gap_bp, _ = re[0]
    assert (sold, bought) == (pytest.approx(43.43), pytest.approx(43.50))
    assert gap_bp == pytest.approx((43.50 - 43.43) / 43.43 * 1e4, abs=0.1)
    assert gap_bp > 0, "bought back higher than sold — S11's prediction"


# ---------------------------------------------------------------- rendering
def test_the_report_renders_and_names_its_caveats(tmp_path):
    st, db = _store(tmp_path)
    _session(st)
    for _ in range(2):
        st.event("info", "runner", "pre-open 20260807", session=SESSION)
    _fill(st, "SOXS", "e0", "E", "BOT", 1680, 43.3626)
    _fill(st, "SOXS", "x0", "F", "SLD", 1680, 42.2316)
    out = SessionReport(db, SESSION).render()
    assert "EVIDENCE QUALITY" in out
    assert "started 2 times" in out
    assert "-253" in out
    assert "§12.3 Q1" in out and "§12.3 Q2" in out


def test_weekly_refuses_to_pretend_a_short_sample_is_a_measurement(tmp_path):
    st, db = _store(tmp_path)
    _session(st)
    st.event("info", "runner", "pre-open 20260807", session=SESSION)
    _fill(st, "SOXS", "e0", "E", "BOT", 1680, 43.3626)
    _fill(st, "SOXS", "x0", "F", "SLD", 1680, 42.2316)
    out = weekly(db, [SESSION])
    assert "§8 baseline" in out and "S11 plan" in out
    assert "not yet a measurement" in out
