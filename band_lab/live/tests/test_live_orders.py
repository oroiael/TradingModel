"""
Stage 3 tests — OrderManager against FakeIB.

These cover the four rules PHASE2_PLAN.md §4.5 calls out as easy to implement
backwards, plus §4.1 partial fills and §3 reconcile-on-connect. They are the
substitute for a broker we cannot reach from CI.
"""

from __future__ import annotations

import pytest

from broker import FakeIB
from orders import OrderManager, RatchetViolation, order_ref, parse_ref
from sleeve import Bar, SleeveConfig, SleeveStateMachine, START_IDX
from store import Store


def _sm(symbol="SOXL", capital=75_000.0):
    cfg = SleeveConfig(symbol=symbol, sleeve_capital=capital)
    sm = SleeveStateMachine(cfg)
    sm.begin_session("20260803", atr5=10.0, is_half_day=False, late_open=False)
    sm.apply_morning_filter(or30=3.0, thr80=5.0, pos10=0.5)
    sm.drain_intents()
    return sm


def _om(tmp_path, symbol="SOXL", sm=None, ib=None, db=None):
    ib = ib or FakeIB()
    ib.connect()
    sm = sm or _sm(symbol)
    store = Store(db or str(tmp_path / "t.db"))
    return OrderManager(broker=ib, symbol=symbol, session="20260803",
                        sm=sm, store=store), ib, sm


def _armed(tmp_path, high=100.0, **kw):
    """Drive the state machine to ARMED the way the engine does — through bars.

    Feeding intents straight into the OrderManager would bypass §2.5's
    activation and test a state the live engine can never be in.
    """
    om, ib, sm = _om(tmp_path, **kw)
    for i in range(START_IDX):
        sm.on_bar_open(i)
        sm.on_bar_close(Bar(i, high, high, high, high))
    sm.on_bar_open(START_IDX)
    om.apply(sm.drain_intents())
    return om, ib, sm


# --------------------------------------------------------------- order refs
def test_order_ref_round_trips():
    r = order_ref("20260803", "SOXL", "E", 3)
    assert r == "20260803-SOXL-E-3"
    assert parse_ref(r) == ("20260803", "SOXL", "E", 3)


def test_parse_ref_rejects_junk():
    assert parse_ref("") is None
    assert parse_ref("not-a-ref") is None


# ----------------------------------------------------------------- ratchet
def test_entry_limit_never_moves_down(tmp_path):
    """§2.5 — the ratchet. Asserted in code, not merely intended."""
    om, ib, sm = _armed(tmp_path)
    assert om.entry_limit == pytest.approx(99.0)

    # a higher session high must raise the limit
    sm.on_bar_close(Bar(START_IDX, 100.0, 110.0, 100.0, 110.0))
    om.apply(sm.drain_intents())
    assert om.entry_limit == pytest.approx(108.9)

    # and a manufactured lower limit must be refused
    from sleeve import Intent, IntentKind
    with pytest.raises(RatchetViolation):
        om.apply([Intent(IntentKind.MODIFY_ENTRY, START_IDX + 1,
                         limit_px=100.0, qty=10)])


def test_ratchet_checked_after_tick_rounding(tmp_path):
    """Rounding is what turns a monotone sequence non-monotone (§4.5)."""
    om, ib, sm = _om(tmp_path)
    from sleeve import Intent, IntentKind
    om.apply([Intent(IntentKind.PLACE_ENTRY, 18, limit_px=100.004, qty=10)])
    assert om.entry_limit == pytest.approx(100.00)
    with pytest.raises(RatchetViolation):
        om.apply([Intent(IntentKind.MODIFY_ENTRY, 19, limit_px=99.994, qty=10)])


# ------------------------------------------------------------ partial fills
def test_partial_entry_fill_cancels_remainder_and_brackets_actual(tmp_path):
    """§4.1 — cancel the rest, bracket what filled, count it as one fill."""
    om, ib, sm = _armed(tmp_path)
    eid = om.entry_id
    full = ib.orders[eid].qty
    ib.fill(eid, qty=full * 0.4, price=99.0)          # partial
    om.on_executions(START_IDX)

    assert sm.fills == 1, "a partial entry counts as exactly one fill"
    assert ib.orders[eid].status == "Cancelled", "remainder must be cancelled"
    brackets = [o for o in ib.orders.values()
                if o.action == "SELL" and o.status == "Submitted"]
    assert len(brackets) == 2
    assert all(o.qty == pytest.approx(full * 0.4) for o in brackets), \
        "bracket the ACTUAL filled qty"


def test_bracket_legs_share_an_oca_group(tmp_path):
    om, ib, sm = _armed(tmp_path)
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)
    legs = [o for o in ib.orders.values() if o.action == "SELL"]
    assert len({o.oca_group for o in legs}) == 1
    assert all(o.oca_group for o in legs)


def test_target_fill_cancels_the_stop_via_oca(tmp_path):
    om, ib, sm = _armed(tmp_path)
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)
    target = next(o for o in ib.orders.values() if o.order_type == "LMT"
                  and o.action == "SELL")
    stop = next(o for o in ib.orders.values() if o.order_type == "STP")
    ib.fill(target.order_id, price=99.99)
    assert stop.status == "Cancelled"


# --------------------------------------------------------------- re-arm
def test_re_arm_is_immediate_on_the_exit_event(tmp_path):
    """§4.5 / V2: instant re-entry is +47.9 bp of the 65.6 bp total.

    A one-bar delay here silently deletes most of the edge, so the re-arm must
    happen on the exit execution, not at the next bar close.
    """
    om, ib, sm = _armed(tmp_path)
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)
    target = next(o for o in ib.orders.values()
                  if o.order_type == "LMT" and o.action == "SELL")

    ib.fill(target.order_id, price=99.99)
    om.on_executions(START_IDX)          # same bar — no bar close in between

    assert sm.fills == 1 and len(sm.trades) == 1
    working_buys = [o for o in ib.orders.values()
                    if o.action == "BUY" and o.status == "Submitted"]
    assert working_buys, "a new entry order must be working immediately"


def test_counters_stop_the_re_arm_at_two_stop_outs(tmp_path):
    """§2.7 — the 2-stop breaker, driven entirely through broker events."""
    om, ib, sm = _armed(tmp_path)
    for _ in range(2):
        assert om.entry_id is not None
        ib.fill(om.entry_id, price=99.0)
        om.on_executions(START_IDX)
        stop = next(o for o in ib.orders.values()
                    if o.order_type == "STP" and o.status == "Submitted")
        ib.fill(stop.order_id, price=95.04)
        om.on_executions(START_IDX)
    assert sm.stop_outs == 2
    assert not sm.trading_today or not [
        o for o in ib.orders.values() if o.action == "BUY" and o.status == "Submitted"]


# ------------------------------------------------------------- executions
def test_executions_are_idempotent_across_a_reconnect(tmp_path):
    """IBKR replays the day's executions on connect; they must not double-count."""
    om, ib, sm = _armed(tmp_path)
    ib.fill(om.entry_id, price=99.0)
    assert len(om.on_executions(START_IDX)) == 1
    assert om.on_executions(START_IDX) == [], "second drain sees nothing new"
    assert sm.fills == 1


def test_store_rejects_duplicate_exec_ids(tmp_path):
    store = Store(str(tmp_path / "d.db"))
    assert store.fill("SOXL", "20260803", "exec-1", qty=1, price=1.0) is True
    assert store.fill("SOXL", "20260803", "exec-1", qty=1, price=1.0) is False


# ---------------------------------------------------------- reconciliation
def test_reconcile_agrees_when_state_matches(tmp_path):
    om, ib, sm = _armed(tmp_path)
    qty = ib.orders[om.entry_id].qty
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)
    r = om.reconcile()
    assert r["broker_fills"] == sm.fills == 1
    assert r["position"] == pytest.approx(qty)
    assert r["agrees"] is True


def test_reconcile_flags_a_mismatch(tmp_path):
    """A position the state machine does not know about must not pass silently."""
    om, ib, sm = _om(tmp_path)
    ib.positions["SOXL"] = 25.0
    r = om.reconcile()
    assert r["agrees"] is False


def test_reconcile_recovers_the_ratchet_witness_after_restart(tmp_path):
    """A fresh process must not be able to place a lower limit than the one
    already resting at the broker."""
    ib = FakeIB(); ib.connect()
    om1, _, sm1 = _om(tmp_path, ib=ib)
    from sleeve import Intent, IntentKind
    om1.apply([Intent(IntentKind.PLACE_ENTRY, START_IDX, limit_px=108.9, qty=10)])

    om2, _, sm2 = _om(tmp_path, ib=ib)            # simulated restart
    om2.reconcile()
    assert om2.highest_limit == pytest.approx(108.9)
    with pytest.raises(RatchetViolation):
        om2.apply([Intent(IntentKind.MODIFY_ENTRY, START_IDX, limit_px=100.0, qty=10)])


# --------------------------------------------------------------- flatten
def test_ensure_flat_resends_until_flat(tmp_path):
    om, ib, sm = _om(tmp_path)
    ib.positions["SOXL"] = 10.0

    real_place = ib.place_market
    def place_and_fill(symbol, action, qty, ref):
        oid = real_place(symbol, action, qty, ref)
        ib.fill(oid, price=100.0)
        return oid
    ib.place_market = place_and_fill

    assert om.ensure_flat() is True
    assert ib.position("SOXL") == pytest.approx(0.0)


def test_ensure_flat_reports_critical_when_it_cannot_flatten(tmp_path):
    om, ib, sm = _om(tmp_path)
    ib.positions["SOXL"] = 10.0          # nothing ever fills
    seen = []
    om.on_event = lambda lvl, msg: seen.append((lvl, msg))
    assert om.ensure_flat(attempts=2) is False
    assert any(lvl == "critical" for lvl, _ in seen)


# --------------------------------------------------- the console must speak
def test_the_live_order_path_reports_to_the_console(tmp_path):
    """A live session was silent: orders and fills went to SQLite only.

    Dry runs printed "DRY RUN — not sent" for every order while a real session
    printed nothing at all, so the mode with consequences was the quiet one.
    §1's fifth design priority is observability.
    """
    seen = []
    ib = FakeIB(); ib.connect()
    sm = _sm()
    store = Store(str(tmp_path / "t.db"))
    om = OrderManager(broker=ib, symbol="SOXL", session="20260806", sm=sm,
                      store=store, on_event=lambda l, m: seen.append(m))
    sm.on_bar_open(START_IDX - 1)
    sm.on_bar_close(Bar(START_IDX - 1, 100.0, 100.0, 100.0, 100.0, 1.0))
    sm.on_bar_open(START_IDX)
    om.apply(sm.drain_intents())
    assert any("ARM" in m for m in seen), "the arming must be visible"

    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    ib.fill(entry.order_id)
    om.on_executions(START_IDX)
    assert any("FILL" in m for m in seen), "every execution must be visible"
    assert any("BRACKET" in m for m in seen), "the protective legs must be visible"

    target = [o for o in ib.orders.values()
              if o.action == "SELL" and o.order_type == "LMT"][-1]
    ib.fill(target.order_id)
    om.on_executions(START_IDX + 1)
    assert any("EXIT TARGET" in m for m in seen), "the outcome must be visible"
    assert any("ret=" in m for m in seen), "and so must the P&L"


# --------------------------------------- one order, several executions (§4.1)
def test_an_entry_settled_in_several_executions_is_one_fill(tmp_path):
    """IBKR splits a fill across executions; the engine must not split the trade.

    Observed live 2026-08-06: a 541-share entry came back as 300 + 210 + 31.
    The first execution bracketed 300 and the next two raised
    RuntimeError('entry fill in state IN_POSITION') — leaving 241 shares held
    with no stop and no target, and a state machine that believed it held 300.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    total = entry.qty

    ib.fill(entry.order_id, qty=total * 0.55, price=99.0)   # first slice
    om.on_executions(START_IDX)
    assert sm.in_position
    assert sm.fills == 1

    ib.fill(entry.order_id, qty=total * 0.45, price=99.0)   # the remainder
    om.on_executions(START_IDX)                              # must not raise

    assert sm.fills == 1, "one order is one fill, however many executions"
    stops = [o for o in ib.orders.values()
             if o.order_type == "STP" and o.status in ("Submitted", "PreSubmitted")]
    assert stops, "a protective stop must still be resting"
    assert stops[-1].qty == pytest.approx(ib.position("SOXL")), \
        "and it must cover every share held, not just the first execution"


def test_the_bracket_is_resized_to_the_broker_position(tmp_path):
    """§6.1 is 'a stop is always resting for what is held', not 'for part'."""
    om, ib, sm = _armed(tmp_path, high=100.0)
    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    ib.fill(entry.order_id, qty=100, price=99.0)
    om.on_executions(START_IDX)

    ib.positions["SOXL"] = 250.0            # as if the rest settled unseen
    assert om.cover_whole_position() is True
    for otype in ("LMT", "STP"):
        leg = [o for o in ib.orders.values()
               if o.action == "SELL" and o.order_type == otype
               and o.status in ("Submitted", "PreSubmitted")][-1]
        assert leg.qty == pytest.approx(250.0), f"{otype} leg must cover 250"


def test_cover_whole_position_is_a_no_op_when_already_covered(tmp_path):
    om, ib, sm = _armed(tmp_path, high=100.0)
    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    ib.fill(entry.order_id)
    om.on_executions(START_IDX)
    before = len(ib.orders)
    assert om.cover_whole_position() is False
    assert len(ib.orders) == before, "no churn when the legs already match"


# ------------------------------------------ idempotency across a *restart*
def test_executions_already_handled_are_not_replayed_after_a_restart(tmp_path):
    """IBKR replays the day's executions to every newly-connected client.

    `seen_execs` lived only in memory, so a restart re-drained the morning's
    fills as if new. On 2026-08-06 that replayed a 541-share entry (300+210+31)
    into a fresh state machine that was still OBSERVING, raising three times and
    aborting the bar loop with it.
    """
    db = str(tmp_path / "r.db")
    ib = FakeIB(); ib.connect()

    om1, _, sm1 = _armed(tmp_path, high=100.0, ib=ib, db=db)
    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    ib.fill(entry.order_id)
    assert om1.on_executions(START_IDX), "the first process handles it"

    # A restart: same broker and same db, brand-new OrderManager and state.
    sm2 = _sm()
    om2 = OrderManager(broker=ib, symbol="SOXL", session="20260803", sm=sm2,
                       store=Store(db))
    assert om2.on_executions(START_IDX) == [], \
        "a restart must not re-process this morning's executions"
    assert sm2.fills == 0, "and must not double-count them"


def test_the_bracket_uses_the_volume_weighted_entry_price(tmp_path):
    """§2.6 prices the bracket off `E`. Several executions have no single E.

    Live 2026-08-06: 541 shares filled as 100/181/143/106/11 across 136.19 to
    136.24. The bracket was priced off the *first* execution, putting the target
    and the stop 2c low — 1.6 bp of error on a strategy whose whole edge is
    ~40 bp/day, which the shadow-parity report would have read as fill quality.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    total = entry.qty

    ib.fill(entry.order_id, qty=total / 2, price=100.00)
    om.on_executions(START_IDX)
    ib.fill(entry.order_id, qty=total / 2, price=101.00)   # a worse half
    om.on_executions(START_IDX)

    from strategy_core import round_to_tick
    vwap = 100.50                                  # (100.00 + 101.00) / 2
    stop = [o for o in ib.orders.values()
            if o.order_type == "STP" and o.status in ("Submitted", "PreSubmitted")][-1]
    target = [o for o in ib.orders.values()
              if o.action == "SELL" and o.order_type == "LMT"
              and o.status in ("Submitted", "PreSubmitted")][-1]
    assert stop.aux_px == pytest.approx(round_to_tick(vwap * 0.96, 0.01)), \
        "the stop must sit 4% below the average paid, not below the first slice"
    assert target.limit_px == pytest.approx(round_to_tick(vwap * 1.01, 0.01))
    assert stop.qty == pytest.approx(ib.position("SOXL"))
    assert stop.aux_px > round_to_tick(100.00 * 0.96, 0.01), \
        "and strictly above where the first execution alone would have put it"
