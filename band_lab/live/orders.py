"""
Stage 3 — OrderManager: turns `Intent`s into broker orders, and broker
executions back into state-machine events.

Four things here are load-bearing, and each corresponds to a rule that is easy
to implement backwards (`PHASE2_PLAN.md` §4.5):

1. **The entry limit never moves down.** The ratchet is asserted in code, after
   tick rounding as well as before, because rounding is what makes an
   apparently-monotone sequence non-monotone.
2. **The re-arm after an exit is immediate** — on the exit event, not at the
   next bar close. V2 measures instant re-entry at +47.9 bp of the 65.6 bp
   total, so a one-bar delay here silently deletes most of the edge.
3. **Partial fills** (§4.1): on the first execution against an entry, cancel
   the remainder, bracket the actual filled quantity, count it as one fill.
4. **Reconciliation is the only way state is established** (§3). `reconcile()`
   runs on every connect, and there is no separate restart path.

Order references are deterministic — `(date, sleeve, role, sequence)` — so the
counters are reconstructible from IBKR's execution log alone, with no
dependence on this process having stayed alive.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from broker import Broker, Execution, Quote, WorkingOrder  # noqa: E402
from sleeve import Intent, IntentKind, SleeveStateMachine  # noqa: E402
from spec_constants import round_to_tick                   # noqa: E402

ROLE_ENTRY, ROLE_TARGET, ROLE_STOP, ROLE_FLAT = "E", "T", "S", "F"


class RatchetViolation(AssertionError):
    """The entry limit moved down. §2.5 forbids this; fail loudly."""


def order_ref(session: str, sleeve: str, role: str, seq: int) -> str:
    """Deterministic and parseable: 20260803-SOXL-E-3."""
    return f"{session}-{sleeve}-{role}-{seq}"


def parse_ref(ref: str) -> Optional[tuple[str, str, str, int]]:
    parts = (ref or "").split("-")
    if len(parts) != 4:
        return None
    try:
        return parts[0], parts[1], parts[2], int(parts[3])
    except ValueError:
        return None


@dataclass
class OrderManager:
    broker: Broker
    symbol: str
    session: str
    sm: SleeveStateMachine
    store: Optional[object] = None
    tick: float = 0.01
    on_event: Callable[[str, str], None] = lambda level, msg: None

    entry_id: Optional[int] = None
    entry_ref: str = ""
    entry_limit: float = 0.0
    target_id: Optional[int] = None
    stop_id: Optional[int] = None
    target_px: float = 0.0              # remembered so the legs can be resized
    stop_px: float = 0.0
    bracket_ref: str = ""               # the entry whose fill opened this position
    entry_qty: float = 0.0              # accumulated across this entry's executions
    entry_notional: float = 0.0         # ... so the levels can use the true VWAP
    exit_qty: float = 0.0               # the same, for an exit still settling
    exit_notional: float = 0.0
    exit_outcome: str = ""
    oca_group: str = ""
    seq: int = 0
    seen_execs: set = field(default_factory=set)
    highest_limit: float = 0.0          # the ratchet witness

    def __post_init__(self) -> None:
        """Recover which executions have already been handled.

        `seen_execs` is what makes a reconnect safe: IBKR replays the whole
        day's executions to every newly-connected client. In memory only, that
        guarantee lasts exactly as long as the process — so a restart re-drained
        the morning's fills as if they were new, which on 2026-08-06 replayed a
        541-share entry three times into a state machine that was OBSERVING and
        raised on each one.

        The `fills` table already has the answer, keyed on the same `exec_id`
        and unique. Reading it back on construction makes idempotency survive
        the restart it was written for.
        """
        if self.store is None:
            return
        try:
            rows = self.store.rows(
                "SELECT exec_id FROM fills WHERE symbol=? AND session=?",
                (self.symbol, self.session))
        except Exception:                                   # noqa: BLE001
            return                       # a fresh db has nothing to recover
        recovered = {r["exec_id"] for r in rows}
        if recovered:
            self.seen_execs |= recovered
            self.on_event("info", f"{self.symbol} recovered {len(recovered)} "
                                  f"execution(s) already handled today")

    # ------------------------------------------------------------- helpers
    def _next_ref(self, role: str) -> str:
        self.seq += 1
        return order_ref(self.session, self.symbol, role, self.seq)

    def _log_order(self, ref, role, action, otype, event, **kw):
        if self.store is not None:
            self.store.order(self.symbol, self.session, ref, role, action,
                             otype, event, **kw)

    def _px(self, p: float) -> float:
        return round_to_tick(float(p), self.tick)

    # --------------------------------------------------------- intent sink
    def apply(self, intents: list[Intent]) -> None:
        for it in intents:
            if self.store is not None:
                self.store.decision(self.symbol, self.session, it.bar_idx,
                                    it.kind.value, limit_px=it.limit_px,
                                    qty=it.qty, target_px=it.target_px,
                                    stop_px=it.stop_px, anchor=self.sm.anchor,
                                    reason=it.reason)
            handler = {
                IntentKind.PLACE_ENTRY: self._place_entry,
                IntentKind.MODIFY_ENTRY: self._modify_entry,
                IntentKind.CANCEL_ENTRY: self._cancel_entry,
                IntentKind.PLACE_BRACKET: self._place_bracket,
                IntentKind.CANCEL_BRACKET: self._cancel_bracket,
                IntentKind.FLATTEN: self._flatten,
                IntentKind.DORMANT: self._dormant,
            }[it.kind]
            handler(it)

    # ------------------------------------------------------------- entries
    def _assert_ratchet(self, limit_px: float) -> None:
        if limit_px + 1e-9 < self.highest_limit:
            raise RatchetViolation(
                f"{self.symbol}: entry limit {limit_px:.2f} below previous "
                f"{self.highest_limit:.2f} — §2.5 forbids the limit moving down")
        self.highest_limit = max(self.highest_limit, limit_px)

    def _place_entry(self, it: Intent) -> None:
        px, qty = self._px(it.limit_px), it.qty
        if qty <= 0:
            return
        self._assert_ratchet(px)
        self.entry_ref = self._next_ref(ROLE_ENTRY)
        self.entry_limit = px
        self.entry_id = self.broker.place_limit(
            self.symbol, "BUY", qty, px, self.entry_ref)
        self._log_order(self.entry_ref, ROLE_ENTRY, "BUY", "LMT", "placed",
                        order_id=self.entry_id, qty=qty, limit_px=px)
        self.on_event("info", f"{self.symbol} ARM  buy limit {qty:.0f} @ {px:.2f} "
                              f"({self.entry_ref})")

    def _modify_entry(self, it: Intent) -> None:
        px, qty = self._px(it.limit_px), it.qty
        if self.entry_id is None:
            return self._place_entry(it)
        self._assert_ratchet(px)
        if abs(px - self.entry_limit) < self.tick / 2 and qty == 0:
            return
        was = self.entry_limit
        self.broker.modify_limit(self.entry_id, px, qty)
        self.entry_limit = px
        self._log_order(self.entry_ref, ROLE_ENTRY, "BUY", "LMT", "modified",
                        order_id=self.entry_id, qty=qty, limit_px=px)
        self.on_event("info", f"{self.symbol} RATCHET {was:.2f} -> {px:.2f} "
                              f"x{qty:.0f}")

    def _cancel_entry(self, it: Intent = None) -> None:
        if self.entry_id is not None:
            self.broker.cancel(self.entry_id)
            self._log_order(self.entry_ref, ROLE_ENTRY, "BUY", "LMT", "cancelled",
                            order_id=self.entry_id)
            self.entry_id = None

    # ------------------------------------------------------------ brackets
    def _place_bracket(self, it: Intent) -> None:
        qty = it.qty
        self.oca_group = f"{self.session}-{self.symbol}-OCA-{self.seq}"
        tref = self._next_ref(ROLE_TARGET)
        sref = self._next_ref(ROLE_STOP)
        tpx, spx = self._px(it.target_px), self._px(it.stop_px)
        self.target_px, self.stop_px = tpx, spx
        self.target_id = self.broker.place_limit(
            self.symbol, "SELL", qty, tpx, tref, oca_group=self.oca_group)
        self.stop_id = self.broker.place_stop(
            self.symbol, "SELL", qty, spx, sref, oca_group=self.oca_group)
        self._log_order(tref, ROLE_TARGET, "SELL", "LMT", "placed",
                        order_id=self.target_id, qty=qty, limit_px=tpx,
                        oca_group=self.oca_group)
        self._log_order(sref, ROLE_STOP, "SELL", "STP", "placed",
                        order_id=self.stop_id, qty=qty, aux_px=spx,
                        oca_group=self.oca_group)
        self.on_event("info", f"{self.symbol} BRACKET x{qty:.0f}  target "
                              f"{tpx:.2f} / stop {spx:.2f}  oca={self.oca_group}")

    def _cancel_bracket(self, it: Intent = None) -> None:
        for oid, role in ((self.target_id, ROLE_TARGET), (self.stop_id, ROLE_STOP)):
            if oid is not None:
                self.broker.cancel(oid)
                self._log_order("", role, "SELL", "", "cancelled", order_id=oid)
        self.target_id = self.stop_id = None

    def cover_whole_position(self) -> bool:
        """Make the protective legs cover every share actually held.

        IBKR settles one order in as many executions as the book requires — a
        541-share entry came back as 300 + 210 + 31 on 2026-08-06. The bracket
        was sized from the *first* execution, so 241 shares carried no stop and
        no target, and the state machine believed the position was 300.

        The broker's position is the only trustworthy quantity here, so the legs
        are rebuilt against it at the same prices. §6.1's guarantee is that a
        protective stop is always resting for what is held; a bracket sized from
        one execution of several does not deliver it.
        """
        pos = abs(self.broker.position(self.symbol))
        if pos <= 0 or self.target_px <= 0:
            return False
        # §2.6 prices the bracket off `E`, the entry fill. With one order settled
        # in several executions there is no single E — the honest one is the
        # volume-weighted average, and it only exists once they have all landed.
        if self.entry_qty > 0:
            vwap = self.entry_notional / self.entry_qty
            self.target_px = self._px(vwap * (1.0 + self.sm.cfg.target_pct))
            self.stop_px = self._px(vwap * (1.0 - self.sm.cfg.stop_pct))
            # The state machine booked both from the first execution. Correct
            # them, or the trade's return is computed on a fraction of what is
            # actually held — 100 of 541 shares, live, on 2026-08-06.
            self.sm.amend_entry(vwap, pos)
        working = {w.order_id: w for w in self.broker.working_orders(self.symbol)}
        t, s = working.get(self.target_id), working.get(self.stop_id)
        covered = max((o.remaining for o in (t, s) if o is not None), default=0.0)
        # The quantity is not the only thing a later execution can move. Once
        # the legs are sized from `position()` they usually already cover the
        # whole holding, so a quantity-only test would return here and leave the
        # bracket at prices computed from the *first* execution while the vwap
        # above had moved under it. Before this sized off the broker the two
        # almost always disagreed, which hid the gap.
        repriced = not (t is not None and s is not None
                        and abs(t.limit_px - self.target_px) < 1e-9
                        and abs(s.aux_px - self.stop_px) < 1e-9)
        if abs(covered - pos) < 1e-9 and not repriced:
            return False
        why = (f"covers {covered:.0f} of {pos:.0f} held" if abs(covered - pos) >= 1e-9
               else f"is priced off a stale entry — target {self.target_px:.2f} "
                    f"/ stop {self.stop_px:.2f} now")
        self.on_event("warn",
                      f"{self.symbol} bracket {why} — replacing so every share "
                      f"has a stop at the right price")
        self._cancel_bracket()
        self._place_bracket(Intent(kind=IntentKind.PLACE_BRACKET,
                                   bar_idx=self.sm._last_bar_idx, qty=pos,
                                   target_px=self.target_px,
                                   stop_px=self.stop_px))
        return True

    def _flatten(self, it: Intent) -> None:
        """§4.7 — MKT, not MOC. Residual is re-sent by `ensure_flat`."""
        qty = it.qty or abs(self.broker.position(self.symbol))
        if qty <= 0:
            return
        ref = self._next_ref(ROLE_FLAT)
        oid = self.broker.place_market(self.symbol, "SELL", qty, ref)
        self._log_order(ref, ROLE_FLAT, "SELL", "MKT", "placed",
                        order_id=oid, qty=qty)

    def _dormant(self, it: Intent) -> None:
        self.on_event("info", f"{self.symbol} dormant: {it.reason}")

    # -------------------------------------------------------------- events
    def on_executions(self, bar_idx: int) -> list[Execution]:
        """Drain new executions and drive the state machine.

        Idempotent on `exec_id`, which is what makes a reconnect safe: IBKR
        replays the day's executions on connect and this must not double-count.
        """
        fresh = []
        for e in self.broker.executions(self.symbol):
            if e.exec_id in self.seen_execs:
                continue
            self.seen_execs.add(e.exec_id)
            fresh.append(e)
            self._record_fill(e)
            parsed = parse_ref(e.order_ref)
            role = parsed[2] if parsed else ""
            if role == ROLE_ENTRY:
                self._on_entry_exec(e, bar_idx)
            elif role in (ROLE_TARGET, ROLE_STOP, ROLE_FLAT):
                self._on_exit_exec(e, bar_idx, role)
        # A position can go flat between executions, so re-check even when this
        # poll brought nothing new — otherwise a settled exit never books.
        self._book_exit_if_flat(bar_idx)
        return fresh

    def _record_fill(self, e: Execution) -> None:
        parsed = parse_ref(e.order_ref)
        role = parsed[2] if parsed else "?"
        self.on_event("info", f"{self.symbol} FILL {role} {e.side} {e.qty:.0f} "
                              f"@ {e.price:.4f}  ({e.order_ref})")
        if self.store is None:
            return
        try:
            q: Quote = self.broker.quote(self.symbol)
        except Exception:                                   # noqa: BLE001
            q = Quote(0.0, 0.0, 0.0)
        self.store.fill(self.symbol, self.session, e.exec_id,
                        order_ref=e.order_ref, perm_id=e.perm_id,
                        role=parsed[2] if parsed else "", side=e.side,
                        qty=e.qty, price=e.price,
                        bid=q.bid, ask=q.ask, last=q.last)
        # §1 — the evidence that decides whether paper can test A1 at all.
        self.store.quote(self.symbol, self.session, f"fill:{e.exec_id}",
                         q.bid, q.ask, q.last)

    def _on_entry_exec(self, e: Execution, bar_idx: int) -> None:
        """§4.1 — cancel the remainder, bracket what actually filled, count one.

        "One execution" and "one fill" are not the same thing. When IBKR settles
        a single entry order in several executions, every one after the first is
        a continuation of the *same* logical entry: it must widen the bracket,
        not open a second position or raise.
        """
        if self.sm.in_position and e.order_ref and e.order_ref == self.bracket_ref:
            self.entry_qty += e.qty
            self.entry_notional += e.qty * e.price
            vwap = self.entry_notional / self.entry_qty
            self.on_event("info",
                          f"{self.symbol} entry {e.order_ref} settled in another "
                          f"execution ({e.qty:.0f} @ {e.price:.4f}) — same fill, "
                          f"vwap {vwap:.4f} over {self.entry_qty:.0f}")
            self.cover_whole_position()
            return
        if self.entry_id is not None:
            working = {w.order_id: w for w in self.broker.working_orders(self.symbol)}
            w = working.get(self.entry_id)
            if w is not None and w.remaining > 0:
                self.broker.cancel(self.entry_id)
                self.on_event("warn",
                              f"{self.symbol} partial entry fill {e.qty} of "
                              f"{w.qty}; cancelled remainder, bracketing {e.qty}")
            self.entry_id = None
        self.bracket_ref = e.order_ref
        self.entry_qty, self.entry_notional = e.qty, e.qty * e.price
        # Size off the broker, not off this one execution. `position()` runs
        # *ahead* of the execution stream: on 2026-08-10 it already read 524
        # while the first execution reported 27. Sizing from the execution
        # placed a 27-share bracket and then immediately cancelled it to place
        # a 524-share one — two generations of OCA orders per entry, the
        # `Error 202` / `Error 10148` cascade in that day's log, and very
        # likely the reason the cancels were still stuck in `PendingCancel` at
        # 15:55. One correctly-sized bracket does not need replacing.
        #
        # When `position()` has *not* caught up, `max` leaves the old behaviour
        # intact and `cover_whole_position` remains the safety net.
        pos = abs(self.broker.position(self.symbol))
        self.sm.on_entry_fill(e.price, bar_idx, qty=max(e.qty, pos))
        self.apply(self.sm.drain_intents())
        self.cover_whole_position()

    def _on_exit_exec(self, e: Execution, bar_idx: int, role: str) -> None:
        """An exit settles in several executions too, and must not book early.

        Booking on the first slice reported the trade on that slice alone *and*
        re-armed §2.5's entry while the rest of the position was still being
        sold — a race that can leave two positions open at once. The trade is
        booked when the broker says the position is actually closed.
        """
        outcome = {ROLE_TARGET: "target", ROLE_STOP: "stop", ROLE_FLAT: "flatten"}[role]
        if not self.sm.in_position:
            return
        self.exit_qty += e.qty
        self.exit_notional += e.qty * e.price
        self.exit_outcome = outcome
        self._book_exit_if_flat(bar_idx)

    def _book_exit_if_flat(self, bar_idx: int) -> None:
        if not (self.sm.in_position and self.exit_qty > 0):
            return
        pos = abs(self.broker.position(self.symbol))
        if pos > 1e-9:
            self.on_event("info",
                          f"{self.symbol} exit settling — {pos:.0f} still held, "
                          f"{self.exit_qty:.0f} sold; not booking or re-arming yet")
            return
        e_px = self.exit_notional / self.exit_qty
        outcome = self.exit_outcome
        self.exit_qty = self.exit_notional = 0.0
        self.exit_outcome = ""
        self.bracket_ref = ""
        self.entry_qty = self.entry_notional = 0.0
        self._book_exit(e_px, bar_idx, outcome)

    def _book_exit(self, price: float, bar_idx: int, outcome: str) -> None:
        self.sm.on_exit_fill(price, bar_idx, outcome)
        last = self.sm.trades[-1] if self.sm.trades else None
        self.on_event("info",
                      f"{self.symbol} EXIT {outcome.upper()} @ {price:.4f}"
                      + (f" x{last.qty:.0f}  ret={last.ret*1e4:+.1f}bp" if last else "")
                      + f"  fills={self.sm.fills}/{self.sm.cfg.max_fills}"
                      f" stops={self.sm.stop_outs}/{self.sm.cfg.max_stops}")
        self._cancel_bracket()
        # §4.5 — re-arm is immediate, on the exit event.
        self.apply(self.sm.drain_intents())

    # ------------------------------------------------------- reconciliation
    def reconcile(self) -> dict:
        """§3 — establish state from the broker. Runs on every connect.

        Returns a summary rather than mutating the state machine: the engine
        decides what to do about a mismatch, because the right response differs
        between pre-open, intraday and post-close.
        """
        pos = self.broker.position(self.symbol)
        working = self.broker.working_orders(self.symbol)
        execs = self.broker.executions(self.symbol)
        entries = [e for e in execs
                   if (parse_ref(e.order_ref) or ("", "", "", 0))[2] == ROLE_ENTRY]
        stops = [e for e in execs
                 if (parse_ref(e.order_ref) or ("", "", "", 0))[2] == ROLE_STOP]
        summary = dict(
            position=pos, working=len(working),
            broker_fills=len(entries), broker_stop_outs=len(stops),
            sm_fills=self.sm.fills, sm_stop_outs=self.sm.stop_outs,
            sm_in_position=self.sm.in_position,
            agrees=(len(entries) == self.sm.fills
                    and len(stops) == self.sm.stop_outs
                    and (abs(pos) > 0) == self.sm.in_position),
        )
        if self.store is not None:
            self.store.counters(self.session, self.symbol, len(entries),
                                len(stops), "reconciled" if summary["agrees"]
                                else "MISMATCH")
        if not summary["agrees"]:
            self.on_event("error", f"{self.symbol} reconcile mismatch: {summary}")
        # keep the highest-limit witness consistent across a restart
        for w in working:
            p = parse_ref(w.order_ref)
            if p and p[2] == ROLE_ENTRY:
                self.entry_id, self.entry_ref = w.order_id, w.order_ref
                self.entry_limit = w.limit_px
                self.highest_limit = max(self.highest_limit, w.limit_px)
            elif p and p[2] == ROLE_TARGET:
                self.target_id = w.order_id
            elif p and p[2] == ROLE_STOP:
                self.stop_id = w.order_id
            if p:
                self.seq = max(self.seq, p[3])
        return summary

    def _working_flatten(self) -> list:
        """Flatten orders already at the broker for this symbol."""
        out = []
        for w in self.broker.working_orders(self.symbol):
            parsed = parse_ref(w.order_ref)
            if parsed and parsed[2] == ROLE_FLAT and w.remaining > 0:
                out.append(w)
        return out

    def _clear_working(self, timeout: float = 5.0) -> bool:
        """Cancel every non-flatten order and wait for the broker to confirm.

        `cancel` is asynchronous. The first flatten sent a market SELL for the
        whole position roughly a millisecond after asking IBKR to cancel the
        bracket, so on 2026-08-07 the target and the stop were still live: 1,680
        shares already committed to working sell orders, and a second sell for
        the same 1,680 behind them. Nothing filled, and the position went into
        the weekend.

        Cancelling is not the same as *having cancelled*. This waits for the
        difference.
        """
        self._cancel_bracket()
        self._cancel_entry()
        deadline = time.time() + timeout
        while True:
            stuck = [w for w in self.broker.working_orders(self.symbol)
                     if not (parse_ref(w.order_ref)
                             and parse_ref(w.order_ref)[2] == ROLE_FLAT)]
            if not stuck:
                return True
            if time.time() >= deadline:
                self.on_event("critical",
                              f"{self.symbol} {len(stuck)} order(s) still working "
                              f"after {timeout:.0f}s of cancel: "
                              + ", ".join(f"{w.order_type} {w.action} "
                                          f"{w.remaining:.0f} ({w.status})"
                                          for w in stuck)
                              + " — they hold the shares the flatten needs")
                return False
            time.sleep(0.25)

    def ensure_flat(self, attempts: int = 5, settle: float = 3.0,
                    budget: Optional[float] = None,
                    escalate_after: float = 20.0) -> bool:
        """§4.7 — re-send until flat; critical alert if not flat by 16:00.

        Three things this has to get right. The first version got none of them,
        the second got two.

        **Give the order time to fill.** The original looped with no pause, so on
        2026-08-06 all three attempts ran inside the same second: the position
        still read 541 each time because no market order can fill that fast, and
        it declared failure while the sells were in flight.

        **Never stack duplicates.** Worse than declaring failure, that loop sent
        a *fresh* market order for the whole position on every attempt. Three
        sells of 541 against one long 541 is a short 1,082 — turning a failure to
        flatten into an inverted position, which is the one direction §11
        prohibits outright. A flatten already working is left alone.

        **Spend the time you actually have.** On 2026-08-10 the bracket's SELL
        LMT and SELL STP went to `PendingCancel` and stayed there, holding the
        524 shares the flatten needed. The loop was budgeted in *attempts*, so
        it exhausted five of them in **23 seconds** and gave up at 15:55:39 with
        §12's `HARD_FLAT_BY` still four minutes and twenty-one seconds away. The
        shares went overnight and lost money the next morning. A deadline is a
        time, not a count: pass `budget` and this keeps working until it is
        spent.

        **Escalate when cancelling is not working.** Individual `cancelOrder`
        calls can sit in `PendingCancel` indefinitely. After `escalate_after`
        seconds of failing to clear the orders that hold the shares, this fires
        `reqGlobalCancel` **once** — the same §6.7 hammer `watchdog.py` uses.
        That also cancels this sleeve's own working flatten, which is why the
        loop must continue afterwards: the next pass sees nothing working, and
        re-sends a market order that now has nothing standing in front of it.
        """
        start = time.time()
        escalated = False
        stuck_since: Optional[float] = None
        i = 0

        def spent() -> bool:
            # `budget` wins when given: the 15:55 flatten has until 16:00 and
            # must use it. Without one, the attempt count is the only limit —
            # which is what the tests drive and what a non-deadline caller gets.
            if budget is not None:
                return (time.time() - start) >= budget
            return i >= attempts

        def clear_timeout(default: float) -> float:
            # `_clear_working` blocks, so an unbounded timeout can overshoot the
            # whole budget in a single call and turn a deadline into a suggestion.
            if budget is None:
                return default
            return max(0.25, min(default, budget - (time.time() - start)))

        # Checked at the top and spent at the bottom, so a zero or already-past
        # budget still buys one honest attempt rather than none.
        while True:
            pos = self.broker.position(self.symbol)
            if abs(pos) < 1e-9:
                return True
            i += 1
            # The stall clock starts *here*, before the blocking cancel — not
            # when it returns. `_clear_working` can spend most of the budget
            # failing, and measuring only the time after it returns meant the
            # escalation could never come due before the deadline did.
            attempt_started = time.time()
            already = self._working_flatten()
            if already:
                self.on_event("info",
                              f"{self.symbol} flatten already working for "
                              f"{sum(w.remaining for w in already):.0f} — waiting, "
                              f"not re-sending")
                # A flatten that is working but not filling is usually blocked by
                # something else holding the shares, so keep clearing.
                cleared = self._clear_working(timeout=clear_timeout(2.0))
            else:
                cleared = self._clear_working(timeout=clear_timeout(5.0))
                ref = self._next_ref(ROLE_FLAT)
                self.broker.place_market(self.symbol, "SELL" if pos > 0 else "BUY",
                                         abs(pos), ref)
                self._log_order(ref, ROLE_FLAT, "SELL" if pos > 0 else "BUY", "MKT",
                                f"flatten_attempt_{i}", qty=abs(pos))
                self.on_event("info", f"{self.symbol} FLATTEN market "
                                      f"{'SELL' if pos > 0 else 'BUY'} {abs(pos):.0f}")

            # --- escalation: the cancels themselves are not landing
            if cleared:
                stuck_since = None
            else:
                if stuck_since is None:
                    stuck_since = attempt_started
                if not escalated and (time.time() - stuck_since) >= escalate_after:
                    escalated = True
                    self.on_event("critical",
                                  f"{self.symbol} orders have refused to cancel for "
                                  f"{escalate_after:.0f}s — firing reqGlobalCancel "
                                  f"(§6.7) to release the shares")
                    try:
                        self.broker.cancel_all()
                    except Exception as exc:                        # noqa: BLE001
                        # Nothing was freed, so the fast path below must not be
                        # taken: re-sending immediately would put a second
                        # market order behind the same bracket that is still
                        # holding the shares. Fall through and let the budget
                        # decide. (`_clear_working` has already cleared the
                        # bracket ids, so there is nothing to restore here.)
                        self.on_event("error",
                                      f"{self.symbol} reqGlobalCancel failed: {exc!r}")
                    else:
                        # The global cancel takes this sleeve's own flatten with
                        # it. Forget the ids so the next pass re-sends rather
                        # than believing an order is still working.
                        self.target_id = self.stop_id = self.entry_id = None
                        # Go straight round again, without consulting the budget.
                        # Escalating and *then* stopping would leave nothing
                        # working at all — strictly worse than never escalating,
                        # because the market order this just cancelled was the
                        # only thing trying to close the position. The re-send
                        # is not optional.
                        self.on_executions(bar_idx=-1)
                        continue
            if settle > 0:
                time.sleep(settle)
            self.on_executions(bar_idx=-1)
            if spent():
                break

        flat = abs(self.broker.position(self.symbol)) < 1e-9
        if not flat:
            spent_desc = (f"{time.time() - start:.0f}s of a {budget:.0f}s budget"
                          if budget is not None else f"{attempts} attempts")
            self.on_event("critical",
                          f"{self.symbol} NOT FLAT after {spent_desc}: "
                          f"position={self.broker.position(self.symbol)} — "
                          f"CLOSE IT BY HAND. §1 forbids holding overnight.")
        return flat
