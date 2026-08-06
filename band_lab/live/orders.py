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
    oca_group: str = ""
    seq: int = 0
    seen_execs: set = field(default_factory=set)
    highest_limit: float = 0.0          # the ratchet witness

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
        """§4.1 — cancel the remainder, bracket what actually filled, count one."""
        if self.entry_id is not None:
            working = {w.order_id: w for w in self.broker.working_orders(self.symbol)}
            w = working.get(self.entry_id)
            if w is not None and w.remaining > 0:
                self.broker.cancel(self.entry_id)
                self.on_event("warn",
                              f"{self.symbol} partial entry fill {e.qty} of "
                              f"{w.qty}; cancelled remainder, bracketing {e.qty}")
            self.entry_id = None
        self.sm.on_entry_fill(e.price, bar_idx, qty=e.qty)
        self.apply(self.sm.drain_intents())

    def _on_exit_exec(self, e: Execution, bar_idx: int, role: str) -> None:
        outcome = {ROLE_TARGET: "target", ROLE_STOP: "stop", ROLE_FLAT: "flatten"}[role]
        if not self.sm.in_position:
            return
        self.sm.on_exit_fill(e.price, bar_idx, outcome)
        last = self.sm.trades[-1] if self.sm.trades else None
        self.on_event("info",
                      f"{self.symbol} EXIT {outcome.upper()} @ {e.price:.4f}"
                      + (f"  ret={last.ret*1e4:+.1f}bp" if last else "")
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

    def ensure_flat(self, attempts: int = 3) -> bool:
        """§4.7 — re-send until flat; critical alert if not flat by 16:00."""
        for i in range(attempts):
            pos = self.broker.position(self.symbol)
            if abs(pos) < 1e-9:
                return True
            self._cancel_bracket()
            self._cancel_entry()
            ref = self._next_ref(ROLE_FLAT)
            self.broker.place_market(self.symbol, "SELL" if pos > 0 else "BUY",
                                     abs(pos), ref)
            self._log_order(ref, ROLE_FLAT, "SELL" if pos > 0 else "BUY", "MKT",
                            f"flatten_attempt_{i+1}", qty=abs(pos))
            self.on_executions(bar_idx=-1)
        flat = abs(self.broker.position(self.symbol)) < 1e-9
        if not flat:
            self.on_event("critical",
                          f"{self.symbol} NOT FLAT after {attempts} attempts: "
                          f"position={self.broker.position(self.symbol)}")
        return flat
