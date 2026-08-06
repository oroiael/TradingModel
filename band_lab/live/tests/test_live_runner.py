"""
Tests for the pieces that make the engine runnable: config, features, feed,
and the Runner's day.

These are what stand between "Stages 2-4 exist" and "Stage 4 can be attempted".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import features
from broker import FakeIB
from config import EngineConfig
from feed import BarFeed
from run import Runner
from spec_constants import ConfigError, OR_PCTL_MINOBS
from store import Store
from strategy_core import Bar

NY = ZoneInfo("America/New_York")
DAY = datetime(2026, 8, 3, tzinfo=NY)


# ------------------------------------------------------------------ config
def test_defaults_are_the_locked_constants():
    EngineConfig().validate()          # must not raise


def test_a_strategy_change_in_disguise_is_rejected():
    """§6.8 — config may carry deployment choices, never strategy numbers."""
    with pytest.raises(ConfigError):
        EngineConfig(dip_pct=0.005).validate()
    with pytest.raises(ConfigError):
        EngineConfig(max_fills=8).validate()
    with pytest.raises(ConfigError):
        EngineConfig(f=1.5).validate()


def test_live_money_port_is_refused_by_default():
    """Phase 2 is paper only; the live port needs an explicit acknowledgement."""
    with pytest.raises(ConfigError):
        EngineConfig(port=7496).validate()
    EngineConfig(port=7496, allow_live_account=True).validate()


def test_transmit_defaults_off():
    assert EngineConfig().transmit is False


# ------------------------------------------------------------------- feed
def _bars(n, high=100.0):
    return [Bar(i, high, high, high, high, 1.0) for i in range(n)]


def test_feed_holds_back_the_forming_bar():
    """§2.5.1 — the anchor updates only on completed bars, enforced in transport."""
    ib = FakeIB(); ib.connect()
    ib.bars["SOXL"] = _bars(4)
    f = BarFeed(ib, "SOXL")
    out = f.poll()
    assert [b.idx for b in out] == [0, 1, 2], "bar 3 is still forming"


def test_feed_emits_each_bar_once():
    ib = FakeIB(); ib.connect()
    ib.bars["SOXL"] = _bars(4)
    f = BarFeed(ib, "SOXL")
    assert len(f.poll()) == 3
    assert f.poll() == [], "a second poll with no new data emits nothing"
    ib.bars["SOXL"] = _bars(6)
    assert [b.idx for b in f.poll()] == [3, 4]


def test_feed_reports_missing_bars():
    ib = FakeIB(); ib.connect()
    ib.bars["SOXL"] = [Bar(0, 1, 1, 1, 1), Bar(3, 1, 1, 1, 1), Bar(4, 1, 1, 1, 1)]
    f = BarFeed(ib, "SOXL")
    f.poll()
    assert f.missing_before(3) == [1, 2]


def test_feed_reset_clears_the_session():
    ib = FakeIB(); ib.connect()
    ib.bars["SOXL"] = _bars(4)
    f = BarFeed(ib, "SOXL")
    f.poll(); f.reset()
    assert f.last_idx == -1 and not f.seen
    assert len(f.poll()) == 3


# --------------------------------------------------------------- features
def test_bootstrap_builds_history_from_the_csv_backbone(tmp_path):
    """The live features must come from the same series the numbers came from."""
    b = features.build("SOXL", _repo_root(), broker=None)
    assert b.sessions >= OR_PCTL_MINOBS
    assert b.sufficient
    assert b.from_broker == 0
    assert b.history.atr5() > 0
    assert b.history.thr80() > 0


def test_bootstrap_tops_up_from_the_broker(tmp_path):
    """Sessions after the CSV's last date come from IBKR, dated, once."""
    ib = FakeIB(); ib.connect()
    base = features.build("SOXL", _repo_root(), broker=None)
    newer = base.last_session.date() + timedelta(days=1)
    older = base.last_session.date() - timedelta(days=5)
    ib.sessions["SOXL"] = [(older, _bars(78)), (newer, _bars(78))]
    b = features.build("SOXL", _repo_root(), broker=ib,
                       today=datetime.combine(newer, datetime.min.time()) +
                       timedelta(days=3))
    assert b.from_broker == 1, "only the session newer than the CSV is added"


def test_check_flags_insufficient_history():
    seen = []
    boot = features.Bootstrap("SOXL", None, sessions=10, last_session=None,
                              from_csv=10, from_broker=0)
    assert features.check({"SOXL": boot}, lambda l, m: seen.append((l, m))) is False
    assert any(l == "critical" for l, _ in seen)


# ----------------------------------------------------------------- runner
def _repo_root():
    """tests/ -> live/ -> band_lab/ -> repo root."""
    import os
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))


def _runner(tmp_path, equity=150_000.0, top_up=True):
    """A runner whose feature history is *fresh*, which is the healthy case.

    The repository CSVs end 2026-07-21, so without a broker top-up every fixture
    dated `DAY` is two weeks stale and `features.check` now refuses the run —
    correctly. Supplying the sessions IBKR would have supplied keeps these tests
    about the runner rather than about staleness, which has its own tests below.
    """
    ib = FakeIB(equity=equity)
    if top_up:
        ib.sessions["SOXL"] = [(date(2026, 7, 30), _bars(78)),
                               (date(2026, 7, 31), _bars(78))]
        ib.sessions["SOXS"] = list(ib.sessions["SOXL"])
    store = Store(str(tmp_path / "r.db"))
    cfg = EngineConfig(symbols=("SOXL",), db_path=str(tmp_path / "r.db"))
    return Runner(cfg, broker=ib, store=store, root=_repo_root()), ib, store


def test_pre_open_wires_features_into_the_engine(tmp_path):
    r, ib, store = _runner(tmp_path)
    r.pre_open(DAY)
    assert "SOXL" in r.engine.sleeves
    assert r.engine.sleeve_capital == pytest.approx(75_000.0)


def test_runner_day_completes_and_reconciles(tmp_path):
    """A whole day end to end, no clock: pre-open, bars, flatten, reconcile."""
    r, ib, store = _runner(tmp_path)
    assert r.pre_open(DAY) in (True, False)          # gate may be OFF on real data
    r.engine.on_bar("SOXL", Bar(0, 100.0, 100.0, 100.0, 100.0, 1.0))
    summary = r.close_out()
    assert "SOXL" in summary
    assert abs(ib.position("SOXL")) < 1e-9


def test_connect_reconciles_before_doing_anything(tmp_path):
    """§3 — every connect is a restart."""
    r, ib, store = _runner(tmp_path)
    r.pre_open(DAY)
    ib.disconnect()
    r._connect()
    assert ib.connected and ib.connect_count >= 2


def test_events_are_persisted(tmp_path):
    r, ib, store = _runner(tmp_path)
    r.session = "20260803"
    r._event("info", "hello")
    rows = store.rows("SELECT * FROM events WHERE message='hello'")
    assert len(rows) == 1


# ------------------------------------------------- market closed (weekends)
def test_parse_liquid_hours_modern_format():
    from broker import parse_liquid_hours
    h = "20260803:0930-20260803:1600;20260804:0930-20260804:1600"
    o, c = parse_liquid_hours(h, "20260803")
    assert (o.hour, o.minute) == (9, 30)
    assert (c.hour, c.minute) == (16, 0)


def test_parse_liquid_hours_half_day():
    from broker import parse_liquid_hours
    o, c = parse_liquid_hours("20261127:0930-20261127:1300", "20261127")
    assert (c - o).total_seconds() / 3600 == pytest.approx(3.5)


def test_parse_liquid_hours_older_close_only_form():
    from broker import parse_liquid_hours
    o, c = parse_liquid_hours("20260803:0930-1600", "20260803")
    assert (c.hour, c.minute) == (16, 0) and c.date() == o.date()


def test_parse_liquid_hours_closed_day_returns_none():
    """A Sunday. This is the case that crashed the first real dry run."""
    from broker import parse_liquid_hours
    assert parse_liquid_hours("20260802:CLOSED;20260803:0930-20260803:1600",
                              "20260802") is None


def test_parse_liquid_hours_absent_day_returns_none():
    from broker import parse_liquid_hours
    assert parse_liquid_hours("20260803:0930-20260803:1600", "20260802") is None


def test_market_closed_stands_the_sleeve_down_instead_of_crashing(tmp_path):
    """An always-on service meets a closed market every Saturday and Sunday."""
    from broker import MarketClosedError
    r, ib, store = _runner(tmp_path)

    def closed(symbol, day):
        raise MarketClosedError(f"{symbol}: no regular session (Sunday)")
    ib.session_hours = closed

    r.pre_open(DAY)                       # must not raise
    rt = r.engine.sleeves["SOXL"]
    assert rt.dormant and rt.dormant_reason == "market_closed"
    row = store.rows("SELECT * FROM daily WHERE symbol='SOXL'")[0]
    assert row["gate_ok"] == 0 and row["gate_reason"] == "market_closed"


def test_runner_day_skips_weekends_without_connecting(tmp_path):
    r, ib, store = _runner(tmp_path)
    sunday = datetime(2026, 8, 2, tzinfo=NY)
    assert sunday.weekday() == 6
    assert r.day(sunday) == {}
    assert ib.connect_count == 0, "no reason to open a connection on a Sunday"


# ------------------------------------------------------ stale feature history
def test_a_stale_top_up_refuses_the_whole_run(tmp_path):
    """§2.2: do not trade when ATR5/thr80 data is "unavailable **or stale**".

    Observed 2026-08-03: IBKR error 162 killed both top-up requests and the
    engine carried on with features ending 2026-07-21 — thirteen days and a
    volatility regime out of date — announcing it only as a log line. Refusing
    costs a trading day; gating and arming off the wrong fortnight is silent.
    """
    r, ib, store = _runner(tmp_path, top_up=False)     # as if 162 killed it
    assert r.pre_open(DAY) is False, "must refuse, not proceed on stale features"
    assert "SOXL" not in r.engine.sleeves, "no sleeve may be armed at all"


def test_a_fresh_top_up_is_accepted(tmp_path):
    r, ib, store = _runner(tmp_path)                   # top_up=True
    r.pre_open(DAY)
    assert "SOXL" in r.engine.sleeves


def test_freshness_tolerates_a_long_weekend():
    """Tuesday after a Monday holiday is 4 days off the last session."""
    import features
    from features import MAX_FEATURE_AGE_DAYS

    def boot(last):
        return SimpleNamespace(sessions=600, sufficient=True, last_session=last)

    tue = date(2026, 8, 4)
    assert features.check({"SOXL": boot(date(2026, 7, 31))}, None, today=tue)
    assert MAX_FEATURE_AGE_DAYS >= 4
    assert not features.check({"SOXL": boot(date(2026, 7, 21))}, None, today=tue)


def test_freshness_is_skipped_when_no_date_is_supplied():
    """`today=None` keeps the old contract for callers that only want size."""
    import features
    b = SimpleNamespace(sessions=600, sufficient=True, last_session=date(2020, 1, 2))
    assert features.check({"SOXL": b}, None)


# ------------------------------------------------------------ transmit flag
def _main(argv):
    """Run run.main() with argv, returning (exit_code, stdout)."""
    import io, contextlib, sys as _sys
    import run as run_mod
    buf = io.StringIO()
    old = _sys.argv
    _sys.argv = ["run.py"] + argv
    try:
        with contextlib.redirect_stdout(buf):
            rc = run_mod.main()
    finally:
        _sys.argv = old
    return rc, buf.getvalue()


def test_dry_run_and_transmit_together_are_refused():
    """Contradictory intent must fail loudly, never be resolved by precedence."""
    rc, out = _main(["--dry-run", "--transmit"])
    assert rc == 2
    assert "contradictory" in out.lower()


def test_transmit_flag_turns_the_order_path_on():
    from config import EngineConfig
    cfg = EngineConfig()
    assert cfg.transmit is False, "the default must stay OFF"
    cfg.transmit = True
    cfg.validate()                       # paper port 7497 — must not raise


def test_transmit_is_still_refused_on_a_live_money_port():
    """--transmit must not become a route around the Phase 2 paper-only rule."""
    from config import EngineConfig
    for port in (7496, 4001):
        with pytest.raises(ConfigError):
            EngineConfig(port=port, transmit=True).validate()


# ------------------------------------------------------------------ heartbeat
def test_heartbeat_reports_each_sleeve(tmp_path):
    """Silence has two readings — "nothing yet" and "died an hour ago"."""
    r, ib, store = _runner(tmp_path)
    seen = []
    r._event = lambda l, m: seen.append(m)
    r.pre_open(DAY)
    r.heartbeat()
    assert seen and seen[-1].startswith("heartbeat |")
    assert "SOXL" in seen[-1]


def test_heartbeat_names_the_reason_a_sleeve_is_dormant(tmp_path):
    r, ib, store = _runner(tmp_path)
    r.pre_open(DAY)
    seen = []
    r._event = lambda l, m: seen.append(m)
    rt = r.engine.sleeves["SOXL"]
    rt.dormant, rt.dormant_reason = True, "stand_down_wide_or_weak_pos10"
    r.heartbeat()
    assert "dormant(stand_down_wide_or_weak_pos10)" in seen[-1]


def test_heartbeat_can_be_disabled():
    from config import EngineConfig
    EngineConfig(heartbeat_seconds=0).validate()      # 0 disables, must not raise
    with pytest.raises(ConfigError):
        EngineConfig(heartbeat_seconds=-1).validate()
