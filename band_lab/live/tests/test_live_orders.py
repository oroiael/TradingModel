"""
Stage 3 tests — OrderManager against FakeIB.

These cover the four rules PHASE2_PLAN.md §4.5 calls out as easy to implement
backwards, plus §4.1 partial fills and §3 reconcile-on-connect. They are the
substitute for a broker we cannot reach from CI.
"""

from __future__ import annotations

import pytest

from broker import BrokerError, FakeIB, WorkingOrder, is_working
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


# ------------------------------- an exit settles in slices too (2026-08-06)
def test_a_split_exit_books_the_whole_trade_not_the_first_slice(tmp_path):
    """Live: a +1% target reported `ret=+18.1bp` instead of +96.5.

    541 shares were entered in five executions, so the state machine booked the
    quantity as the first slice's 100. The exit then sold 100 + 441, booked on
    the first of those, and re-armed §2.5's entry while 441 shares were still
    being sold — a race that can leave two positions open at once.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    entry = [o for o in ib.orders.values() if o.order_type == "LMT"][-1]
    total = entry.qty
    ib.fill(entry.order_id, qty=total * 0.2, price=100.0)   # a thin first slice
    om.on_executions(START_IDX)
    ib.fill(entry.order_id, qty=total * 0.8, price=100.0)
    om.on_executions(START_IDX)
    assert sm._qty == pytest.approx(total), "the whole entry, not the first slice"

    target = [o for o in ib.orders.values()
              if o.action == "SELL" and o.order_type == "LMT"
              and o.status in ("Submitted", "PreSubmitted")][-1]
    ib.fill(target.order_id, qty=total * 0.2, price=101.0)   # exit slice 1
    om.on_executions(START_IDX + 1)
    assert sm.in_position, "must not book while shares are still held"
    assert not sm.trades, "and must not re-arm into a half-sold position"

    ib.fill(target.order_id, qty=total * 0.8, price=101.0)   # the rest
    om.on_executions(START_IDX + 1)
    assert sm.trades, "booked once flat"
    t = sm.trades[-1]
    assert t.qty == pytest.approx(total)
    assert t.ret == pytest.approx(total * 1.0 / sm.cfg.sleeve_capital), \
        "the return is on every share, not on the first slice"


def test_amend_entry_is_inert_when_flat(tmp_path):
    """It must never invent a position — replay depends on that."""
    om, ib, sm = _om(tmp_path)
    sm.amend_entry(123.45, 999)
    assert sm._qty == 0.0 and not sm.in_position


# ------------------------------------------- the 15:55 flatten (2026-08-06)
def test_ensure_flat_never_stacks_duplicate_market_orders(tmp_path):
    """Three sells of 541 against one long 541 is a short 1,082.

    The loop re-sent a market order for the *whole* position on every attempt
    with no pause between them, so on 2026-08-06 all three ran inside one second
    against a position that could not possibly have settled yet. Failing to
    flatten is bad; inverting the position is the one direction §11 forbids.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)
    held = ib.position("SOXL")
    assert held > 0

    ib.fill = lambda *a, **k: None          # nothing settles; every attempt sees the position
    assert om.ensure_flat(attempts=3, settle=0) is False
    sells = [o for o in ib.orders.values()
             if o.order_type == "MKT" and o.action == "SELL"]
    assert len(sells) == 1, \
        f"one flatten order, re-used — not {len(sells)} stacked sells"
    assert sells[0].qty == pytest.approx(held)


def test_ensure_flat_returns_true_once_the_position_closes(tmp_path):
    """A market order that behaves like one: sent, then filled."""
    om, ib, sm = _armed(tmp_path, high=100.0)
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)

    real_place = ib.place_market
    def place_and_fill(symbol, action, qty, order_ref):
        oid = real_place(symbol, action, qty, order_ref)
        ib.fill(oid, price=99.5)                  # as the market would
        return oid
    ib.place_market = place_and_fill

    assert om.ensure_flat(attempts=3, settle=0) is True
    assert abs(ib.position("SOXL")) < 1e-9
    sells = [o for o in ib.orders.values()
             if o.order_type == "MKT" and o.action == "SELL"]
    assert len(sells) == 1, "one order was enough; no second attempt"


def test_the_flatten_waits_for_the_bracket_to_actually_cancel(tmp_path):
    """Cancelling is not the same as having cancelled.

    2026-08-07: the flatten sent a market SELL for 1,680 about a millisecond
    after asking IBKR to cancel the bracket, so the target and the stop were
    still live. 1,680 shares were already committed to working sells, the
    market order queued behind them, nothing filled, and the position went into
    the weekend. `working: 3` in the reconcile line is the two bracket legs plus
    the flatten.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)
    assert [o for o in ib.orders.values()
            if o.action == "SELL" and o.status in ("Submitted", "PreSubmitted")], \
        "the bracket is working before the flatten"

    sent_while_working = []
    real_place = ib.place_market
    def place_and_check(symbol, action, qty, order_ref):
        sent_while_working.append([
            o for o in ib.orders.values()
            if o.action == "SELL" and o.order_type in ("LMT", "STP")
            and o.status in ("Submitted", "PreSubmitted")])
        oid = real_place(symbol, action, qty, order_ref)
        ib.fill(oid, price=99.5)
        return oid
    ib.place_market = place_and_check

    assert om.ensure_flat(attempts=3, settle=0) is True
    assert sent_while_working, "the flatten was sent"
    assert sent_while_working[0] == [], \
        "no bracket leg may still be working when the market order goes out"


def test_clear_working_reports_what_it_could_not_cancel(tmp_path):
    """A cancel that does not take must be named, not silently retried."""
    said = []
    om, ib, sm = _armed(tmp_path, high=100.0)
    om.on_event = lambda l, m: said.append((l, m))
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)
    ib.cancel = lambda oid: None                 # cancels never take effect
    assert om._clear_working(timeout=0.5) is False
    assert any(l == "critical" and "still working" in m for l, m in said)


# ------------------------------- the 15:55 flatten deadline (2026-08-10, #4)
class StuckCancelIB(FakeIB):
    """Cancels TWS never confirms — the 2026-08-10 state, as the broker models it.

    Built on `FakeIB`'s own two-phase cancel rather than on a bespoke no-op:
    `stall_cancels` leaves the legs in `PendingCancel`, which is exactly what
    `IBBroker` reported for `LMT SELL 524` and `STP SELL 524` at 15:55. Before
    the double carried that state, this class had to fake the stall by ignoring
    `cancel` outright, which left the orders `Submitted` — behaviourally similar
    and mechanically wrong.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.stall_cancels = True

    def cancel_all(self) -> None:
        # §6.7's hammer resolves the stall; ordinary cancels work again after.
        self.stall_cancels = False
        super().cancel_all()


def _in_position(tmp_path, **kw):
    """A sleeve holding a bracketed position, as at 15:55."""
    om, ib, sm = _armed(tmp_path, high=100.0, **kw)
    ib.fill(om.entry_id, price=99.0)
    om.on_executions(START_IDX)
    assert ib.position("SOXL") > 0
    return om, ib, sm


def test_flatten_is_budgeted_in_time_not_attempts(tmp_path):
    """The 2026-08-10 failure: five attempts spent in 23 seconds, then it quit
    with §12's 16:00 deadline still four minutes away."""
    om, ib, sm = _in_position(tmp_path, ib=StuckCancelIB())
    calls = []
    om.broker.cancel_all = lambda: calls.append(1)      # neutered: stays stuck

    import time as _t
    t0 = _t.time()
    assert om.ensure_flat(settle=0, budget=0.6, escalate_after=999) is False
    elapsed = _t.time() - t0
    # It spent the budget rather than five quick attempts.
    assert elapsed >= 0.6, f"gave up after {elapsed:.2f}s of a 0.6s budget"


def test_flatten_escalates_to_global_cancel_when_cancels_stall(tmp_path):
    """§6.7's hammer, applied only after the ordinary cancels demonstrably fail."""
    om, ib, sm = _in_position(tmp_path, ib=StuckCancelIB())
    assert ib.global_cancels == 0
    om.ensure_flat(settle=0, budget=0.5, escalate_after=0.0)
    assert ib.global_cancels >= 1, "the stuck bracket was never force-cancelled"


def test_flatten_does_not_escalate_when_cancels_are_working(tmp_path):
    """A hammer that swings on a healthy book is defects 6 and 7 again."""
    om, ib, sm = _in_position(tmp_path)                 # plain FakeIB: cancels work
    om.ensure_flat(settle=0, budget=0.3, escalate_after=0.0)
    assert ib.global_cancels == 0


def test_flatten_escalates_at_most_once(tmp_path):
    om, ib, sm = _in_position(tmp_path, ib=StuckCancelIB())
    ib.cancel_all_calls = 0
    real = ib.cancel_all
    def counted():
        ib.cancel_all_calls += 1
        real()
    ib.cancel_all = counted
    om.ensure_flat(settle=0, budget=0.5, escalate_after=0.0)
    assert ib.cancel_all_calls == 1


def test_flatten_resends_after_the_global_cancel_takes_its_own_order(tmp_path):
    """reqGlobalCancel kills this sleeve's own working flatten too.

    If the loop stopped there, the escalation would leave nothing working and
    the position would go overnight anyway — the failure it exists to prevent.
    """
    om, ib, sm = _in_position(tmp_path, ib=StuckCancelIB())
    held = ib.position("SOXL")
    om.ensure_flat(settle=0, budget=0.5, escalate_after=0.0)
    flats = [o for o in ib.orders.values()
             if o.order_type == "MKT" and o.status in ("Submitted", "PreSubmitted")]
    assert flats, "no live flatten left after the global cancel"
    assert sum(o.qty for o in flats) == pytest.approx(held), \
        "the re-sent flatten must cover the whole position, and only once"
    assert ib.global_cancels == 1


def test_flatten_never_stacks_duplicates_over_a_long_budget(tmp_path):
    """The safety invariant, re-asserted under the new deadline loop.

    Looping for minutes instead of attempts multiplies the chances of the
    2026-08-06 bug: three sells of 541 against one long 541 is a short 1,082,
    the one direction §11 forbids outright. At no point may the working sell
    quantity exceed the position.
    """
    om, ib, sm = _in_position(tmp_path)
    held = ib.position("SOXL")
    ib.fill = lambda *a, **k: None                      # nothing ever settles

    assert om.ensure_flat(settle=0, budget=0.8) is False
    sells = [o for o in ib.orders.values()
             if o.order_type == "MKT" and o.action == "SELL"
             and o.status in ("Submitted", "PreSubmitted")]
    assert len(sells) == 1, f"{len(sells)} stacked flatten orders"
    assert sells[0].qty == pytest.approx(held)
    assert ib.position("SOXL") >= 0, "never inverted"


def test_flatten_makes_one_attempt_even_with_no_budget_left(tmp_path):
    """A flatten that starts late still tries. Zero budget is not zero effort."""
    om, ib, sm = _in_position(tmp_path)
    real_place = ib.place_market
    def place_and_fill(symbol, action, qty, order_ref):
        oid = real_place(symbol, action, qty, order_ref)
        ib.fill(oid, price=99.5)
        return oid
    ib.place_market = place_and_fill
    assert om.ensure_flat(settle=0, budget=0.0) is True
    assert abs(ib.position("SOXL")) < 1e-9


def test_flatten_returns_true_without_acting_when_already_flat(tmp_path):
    om, ib, sm = _om(tmp_path)
    assert om.ensure_flat(settle=0, budget=5.0) is True
    assert not [o for o in ib.orders.values() if o.order_type == "MKT"]


class BlockedMarketIB(StuckCancelIB):
    """StuckCancelIB, plus the reason the flatten could not fill.

    IBKR holds the shares against a working sell, so while the bracket's SELL
    LMT / SELL STP are alive the flatten's market order cannot be filled. This
    is the whole mechanism of 2026-08-10 in one double: the cancels do not land,
    so the shares stay committed, so the market order sits.
    """

    def place_market(self, symbol, action, qty, order_ref):
        oid = super().place_market(symbol, action, qty, order_ref)
        # `is_working`, not a hand-written status list — the same mistake this
        # whole change exists to remove. A leg in PendingCancel still holds the
        # shares, which is the entire mechanism of 2026-08-10.
        blocked = [o for o in self.orders.values()
                   if o.symbol == symbol and o.action == "SELL"
                   and o.order_type in ("LMT", "STP") and is_working(o.status)]
        if not blocked:
            self.fill(oid, price=99.5)
        return oid


def test_the_2026_08_10_flatten_now_reaches_flat(tmp_path):
    """The regression, end to end.

    On 2026-08-10 this exact situation left 524 shares overnight: the loop
    burned five attempts in 23 seconds and quit at 15:55:39 with the 16:00
    deadline four minutes away. With a clock-based budget it keeps trying,
    escalates to reqGlobalCancel once the ordinary cancels have plainly failed,
    re-sends the market order the global cancel took with it, and gets flat.
    """
    om, ib, sm = _in_position(tmp_path, ib=BlockedMarketIB())
    held = ib.position("SOXL")
    assert held > 0

    # The old budget, for contrast: five attempts and no escalation.
    assert om.ensure_flat(attempts=5, settle=0, escalate_after=1e9) is False
    assert ib.position("SOXL") == pytest.approx(held), "the old path leaves it open"

    # The new one.
    assert om.ensure_flat(settle=0, budget=10.0, escalate_after=0.2) is True
    assert abs(ib.position("SOXL")) < 1e-9, "still not flat"
    assert ib.global_cancels == 1, "escalated exactly once"


def test_a_failed_global_cancel_does_not_take_the_fast_path(tmp_path):
    """Found by review, not by a failing run.

    The escalation normally skips the budget check and re-sends at once, because
    the global cancel just took this sleeve's own flatten with it. If the cancel
    *raised*, nothing was freed — so re-sending immediately would only queue a
    second market order behind the same bracket. The error is reported and the
    budget still decides.
    """
    events = []
    om, ib, sm = _in_position(tmp_path, ib=StuckCancelIB())
    om.on_event = lambda level, msg: events.append((level, msg))
    def boom():
        raise RuntimeError("IBKR said no")
    ib.cancel_all = boom

    assert om.ensure_flat(settle=0, budget=0.5, escalate_after=0.0) is False
    assert any(lvl == "error" and "reqGlobalCancel failed" in m
               for lvl, m in events), events
    sells = [o for o in ib.orders.values()
             if o.order_type == "MKT" and o.status in ("Submitted", "PreSubmitted")]
    assert len(sells) <= 1, "a failed escalation must not stack a second flatten"


# ------------------- one bracket, sized off the broker (2026-08-10, fix #5)
def _brackets(ib, symbol="SOXL"):
    """Every protective leg ever placed, grouped by OCA generation."""
    groups = {}
    for o in ib.orders.values():
        if o.symbol == symbol and o.action == "SELL" and o.order_type in ("LMT", "STP"):
            groups.setdefault(o.oca_group, []).append(o)
    return groups


def test_one_entry_in_many_executions_places_exactly_one_bracket(tmp_path):
    """2026-08-10: 524 shares in 7 executions, and two brackets per entry.

    `position()` runs ahead of the execution stream — it already read 524 when
    the first execution reported 27 — so the engine placed a 27-share bracket
    and cancelled it a millisecond later for a 524-share one. Two OCA
    generations per entry is the churn behind that day's `Error 202` /
    `Error 10148` cascade, and the reason cancels were still stuck in
    `PendingCancel` at 15:55.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    eid = om.entry_id
    full = ib.orders[eid].qty
    # settle it the way IBKR did: several executions, position already complete
    for frac in (0.05, 0.20, 0.15, 0.25, 0.35):
        ib.fill(eid, qty=full * frac, price=99.0)
    assert ib.position("SOXL") == pytest.approx(full)

    om.on_executions(START_IDX)

    groups = _brackets(ib)
    assert len(groups) == 1, \
        f"{len(groups)} bracket generations for one entry: {list(groups)}"
    legs = next(iter(groups.values()))
    assert len(legs) == 2                                     # target + stop
    assert all(o.qty == pytest.approx(full) for o in legs), \
        "the one bracket must cover every share from the start"
    assert all(o.status in ("Submitted", "PreSubmitted") for o in legs)


def test_the_bracket_still_covers_when_position_lags_the_executions(tmp_path):
    """The safety net stays. If `position()` has not caught up, the legs are
    sized from the execution and `cover_whole_position` widens them after."""
    om, ib, sm = _armed(tmp_path, high=100.0)
    eid = om.entry_id
    full = ib.orders[eid].qty

    ib.fill(eid, qty=full * 0.4, price=99.0)
    om.on_executions(START_IDX)                 # position is only 40% here
    ib.fill(eid, qty=full * 0.6, price=99.0)
    om.on_executions(START_IDX)

    live = [o for o in ib.orders.values()
            if o.action == "SELL" and o.status in ("Submitted", "PreSubmitted")]
    assert live, "no protective legs left"
    assert all(o.qty == pytest.approx(full) for o in live), \
        "every share must end up covered however the executions arrived"


def test_a_later_execution_that_moves_the_vwap_reprices_the_bracket(tmp_path):
    """The bug fix #5 would otherwise have unmasked.

    Sized off `position()`, the legs usually already cover the whole holding —
    so a quantity-only test returns early and leaves the bracket priced off the
    *first* execution while the vwap moved under it. §2.6 prices the bracket off
    E, and with one order settled in several executions the honest E is the
    volume-weighted average.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    eid = om.entry_id
    full = ib.orders[eid].qty

    # Both executions land before the first drain, so `position()` is complete
    # from the outset and the legs are sized right immediately. The quantity
    # therefore never disagrees, and only the price path can fix the bracket —
    # which is precisely the case a quantity-only test cannot reach.
    ib.fill(eid, qty=full * 0.5, price=99.00)
    ib.fill(eid, qty=full * 0.5, price=101.00)          # vwap is 100.00
    om.on_executions(START_IDX)

    stop = [o for o in ib.orders.values()
            if o.order_type == "STP" and o.status in ("Submitted", "PreSubmitted")]
    assert len(stop) == 1
    assert stop[0].aux_px == pytest.approx(round(100.00 * 0.96, 2)), \
        "the stop is still priced off the first execution, not the vwap"
    assert stop[0].qty == pytest.approx(full)


# --------------- the ratchet race and Error 103 (2026-08-10, fix #7)
class RejectModifyIB(FakeIB):
    """IBKR answers `Error 103, Duplicate order id` and keeps the original.

    `IBBroker.modify_limit` mutates the local `Order` and then calls
    `placeOrder`, which `ib_async` treats as a modification of the existing
    trade. The rejection arrives asynchronously, so by the time it lands the
    client's copy already carries the new price. On 2026-08-10 the engine
    believed `43.78 x1701` while the broker still had `43.71 x1703` — and the
    fill proved the broker won, settling 1,703 shares.
    """

    def modify_limit(self, order_id, limit_px, qty) -> None:
        return                            # accepted locally, refused upstream


class PendingSubmitIB(FakeIB):
    """An order TWS has not acknowledged yet."""

    def _add(self, *a, **kw) -> int:
        oid = super()._add(*a, **kw)
        self.orders[oid].status = "PendingSubmit"
        return oid

    def working_orders(self, symbol):
        return [WorkingOrder(o.order_ref, o.order_id, 0, o.symbol, o.action,
                             o.order_type, o.qty, o.filled, o.limit_px,
                             o.aux_px, o.oca_group, o.status)
                for o in self.orders.values()
                if o.symbol == symbol
                and o.status in ("Submitted", "PreSubmitted", "PendingSubmit")]


def _ratchet_to(om, sm, idx, high):
    sm.on_bar_close(Bar(idx, high, high, high, high))
    sm.on_bar_open(idx + 1)
    om.apply(sm.drain_intents())


def test_a_refused_ratchet_is_corrected_from_the_broker_next_bar(tmp_path):
    """The engine's limit is a belief; the broker's is the fact."""
    om, ib, sm = _armed(tmp_path, high=100.0, ib=RejectModifyIB())
    assert om.entry_limit == pytest.approx(99.00)
    original = ib.orders[om.entry_id].limit_px

    _ratchet_to(om, sm, START_IDX, 110.0)              # asks for 108.90
    assert om.entry_limit == pytest.approx(108.90), "optimistic in the moment"
    assert ib.orders[om.entry_id].limit_px == pytest.approx(original), \
        "the broker refused it"

    events = []
    om.on_event = lambda lvl, msg: events.append((lvl, msg))
    _ratchet_to(om, sm, START_IDX + 1, 111.0)
    assert any(lvl == "warn" and "drifted from the broker" in m
               for lvl, m in events), events


def test_the_engine_never_believes_a_price_the_broker_refused(tmp_path):
    """The resync replaces the belief with the fact.

    Asserting this *after* a ratchet would not show it: the engine adopts the
    broker's price and then optimistically writes the newly-requested one, so
    the end state is always the optimistic value. The correction is what
    `_resync_entry` does, and that is what is asserted.
    """
    om, ib, sm = _armed(tmp_path, high=100.0, ib=RejectModifyIB())
    _ratchet_to(om, sm, START_IDX, 110.0)
    assert om.entry_limit == pytest.approx(108.90)          # believed
    assert ib.orders[om.entry_id].limit_px == pytest.approx(99.00)   # actual

    assert om._resync_entry() is not None
    assert om.entry_limit == pytest.approx(99.00), \
        "the engine is still carrying a price the broker refused"


def test_a_vanished_entry_order_is_never_silently_re_armed(tmp_path):
    """The dangerous half of Error 103.

    A rejected modify leaves `ib_async`'s copy marked Cancelled — `openTrades`
    drops it, because Cancelled is a DoneState — while the original order is
    still live at IBKR. Re-arming there would put a second buy limit behind one
    that then filled 1,703 shares. A missed ratchet costs basis points; a
    duplicate position costs control of the sleeve.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    before = len([o for o in ib.orders.values() if o.action == "BUY"])
    ib.orders[om.entry_id].status = "Cancelled"        # gone, locally

    events = []
    om.on_event = lambda lvl, msg: events.append((lvl, msg))
    _ratchet_to(om, sm, START_IDX, 110.0)

    after = len([o for o in ib.orders.values() if o.action == "BUY"])
    assert after == before, "a second entry order was placed"
    assert any(lvl == "critical" and "NOT re-arming" in m for lvl, m in events), \
        events


def test_the_ratchet_waits_for_an_unacknowledged_order(tmp_path):
    """2026-08-10: the arm and the ratchet were 2 ms apart, and IBKR answered
    Error 103. Modifying an order it has not acknowledged is deferred a bar."""
    om, ib, sm = _armed(tmp_path, high=100.0, ib=PendingSubmitIB())
    at_arm = ib.orders[om.entry_id].limit_px

    events = []
    om.on_event = lambda lvl, msg: events.append((lvl, msg))
    _ratchet_to(om, sm, START_IDX, 110.0)

    assert ib.orders[om.entry_id].limit_px == pytest.approx(at_arm), \
        "modified an order TWS had not acknowledged"
    assert any("ratchet deferred" in m for _, m in events), events
    # Once acknowledged, the ratchet proceeds normally. The high must actually
    # rise — an unchanged session high emits no intent at all.
    ib.orders[om.entry_id].status = "Submitted"
    _ratchet_to(om, sm, START_IDX + 1, 120.0)
    assert ib.orders[om.entry_id].limit_px == pytest.approx(118.80)


def test_a_broker_error_on_modify_does_not_kill_the_session(tmp_path):
    om, ib, sm = _armed(tmp_path, high=100.0)
    def boom(order_id, limit_px, qty):
        raise BrokerError("no")
    ib.modify_limit = boom
    events = []
    om.on_event = lambda lvl, msg: events.append((lvl, msg))
    _ratchet_to(om, sm, START_IDX, 110.0)              # must not raise
    assert any(lvl == "error" and "refused" in m for lvl, m in events), events


# ------------- reconcile counts round trips, not executions (fix #6)
def test_reconcile_agrees_when_one_entry_settles_in_many_executions(tmp_path):
    """2026-08-10 reported MISMATCH on both sleeves, every session.

    `broker_fills` counted executions (7 on SOXL, 31 on SOXS) against
    `sm_fills`, which counts §2.7 round trips (1 and 3). Both numbers were
    right about different things. SOXS reconciled perfectly — position 0, not
    in position — and was still reported as a mismatch.
    """
    om, ib, sm = _armed(tmp_path, high=100.0)
    eid = om.entry_id
    full = ib.orders[eid].qty
    for frac in (0.05, 0.20, 0.15, 0.25, 0.35):
        ib.fill(eid, qty=full * frac, price=99.0)
    om.on_executions(START_IDX)

    r = om.reconcile()
    assert r["broker_entry_execs"] == 5, "five executions really did arrive"
    assert r["broker_fills"] == 1, "but they are one entry"
    assert r["sm_fills"] == 1
    assert r["agrees"] is True, r


def test_reconcile_still_catches_a_real_disagreement(tmp_path):
    """The check must keep its teeth: a position the state machine denies."""
    om, ib, sm = _armed(tmp_path, high=100.0)
    ib.positions["SOXL"] = 500.0          # held, with no fill ever seen
    r = om.reconcile()
    assert r["agrees"] is False
    assert r["sm_in_position"] is False and r["position"] == pytest.approx(500.0)


def test_reconcile_counts_two_separate_entries_as_two(tmp_path):
    """Two round trips are two, however many executions each took."""
    om, ib, sm = _armed(tmp_path, high=100.0)
    for _ in range(2):
        eid = om.entry_id
        ib.fill(eid, qty=ib.orders[eid].qty * 0.5, price=99.0)
        ib.fill(eid, price=99.0)
        om.on_executions(START_IDX)
        target = next(o for o in ib.orders.values()
                      if o.order_type == "LMT" and o.action == "SELL"
                      and is_working(o.status))
        ib.fill(target.order_id, price=99.99)
        om.on_executions(START_IDX)
    assert om.reconcile()["broker_fills"] == 2 == sm.fills
