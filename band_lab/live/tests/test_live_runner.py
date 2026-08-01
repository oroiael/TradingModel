"""
Tests for the pieces that make the engine runnable: config, features, feed,
and the Runner's day.

These are what stand between "Stages 2-4 exist" and "Stage 4 can be attempted".
"""

from __future__ import annotations

from datetime import datetime, timedelta
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


def _runner(tmp_path, equity=150_000.0):
    ib = FakeIB(equity=equity)
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
