"""
Stage 4 — the engine: `IMPLEMENTATION_SPEC.md` §5's daily timetable.

| 06:00 | pre-open: features, gate, sleeve capital, hard interlock if OFF |
| 09:30 | record bars, no orders |
| 10:00 | bar 5 closes -> OR30, pos10, morning filter |
| 11:00 | activate: anchor from completed bars, place the resting limit |
| ..15:55| on each bar close ratchet; on fill bracket; on exit re-arm |
| 15:55 | flatten |
| 16:00 | verify flat, alert if not |
| 16:10 | reconcile, write the daily row |

The engine owns *time*; `SleeveStateMachine` owns strategy; `OrderManager`
owns orders. Nothing here re-implements a strategy rule — where it looks like
it does (the 11:00 activation, the 15:55 flatten) it is calling the state
machine and forwarding intents.

Restart safety (§5): the engine reconciles from the broker before it resumes,
never from its own memory. `run_session` is written so that entering it late —
at 13:00, after a crash — produces the same state as having run since 09:30,
because the bar history is re-fetched and replayed rather than remembered.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from broker import (                                        # noqa: E402
    Broker, MarketClosedError, NotLiveDataError, SessionHours,
)
from orders import OrderManager                             # noqa: E402
from sleeve import SleeveConfig, SleeveStateMachine         # noqa: E402
from store import Store                                     # noqa: E402
from strategy_core import (                                 # noqa: E402
    Bar, FeatureHistory, session_stats,
)
from spec_constants import (                                # noqa: E402
    DAY_LOSS_KILL, F_SIZE, W_PER_SLEEVE, bar_index,
)

NY = ZoneInfo("America/New_York")
START_IDX = bar_index("11:00")
FILTER_IDX = bar_index("09:55")          # bar 5; closes at 10:00
FLATTEN_IDX = bar_index("15:55")

#: §2 of the plan — capital basis is capped, so the published cost rows apply.
CAPITAL_CAP = 150_000.0


@dataclass
class SleeveRuntime:
    symbol: str
    sm: SleeveStateMachine
    om: OrderManager
    history: FeatureHistory
    dormant: bool = False
    dormant_reason: str = ""
    session_bars: dict = field(default_factory=dict)
    activated: bool = False
    filtered: bool = False


class Engine:
    """One process, one broker connection, N independent sleeves."""

    def __init__(self, broker: Broker, store: Store, symbols=("SOXL", "SOXS"),
                 f: float = F_SIZE, w: float = W_PER_SLEEVE,
                 capital_cap: float = CAPITAL_CAP,
                 on_event: Optional[Callable[[str, str], None]] = None) -> None:
        self.broker = broker
        self.store = store
        self.symbols = list(symbols)
        self.f, self.w, self.capital_cap = f, w, capital_cap
        self.on_event = on_event or self._default_event
        self.sleeves: dict[str, SleeveRuntime] = {}
        self.session = ""
        self.sleeve_capital = 0.0

    def _default_event(self, level: str, msg: str) -> None:
        self.store.event(level, "engine", msg, session=self.session or None)
        print(f"[{level}] {msg}", flush=True)

    # ----------------------------------------------------------- 06:00
    def pre_open(self, day: datetime, features: dict[str, FeatureHistory],
                 hours: Optional[dict[str, SessionHours]] = None) -> None:
        """Features, gate, capital. Sets the hard interlock when the gate is OFF.

        `features` carries the 5-minute history each sleeve's ATR5 and thr80 are
        computed from — always the full record (§4.4 stores percentages only,
        never historical prices, which is the S7 trap).
        """
        self.session = day.strftime("%Y%m%d")
        if not self.broker.connected:
            self.broker.connect()

        equity = self.broker.net_liquidation()
        basis = min(equity, self.capital_cap)
        self.sleeve_capital = self.w * basis
        self.on_event("info", f"equity={equity:,.0f} basis={basis:,.0f} "
                              f"sleeve_capital={self.sleeve_capital:,.0f}")

        for symbol in self.symbols:
            hist = features[symbol]
            cfg = SleeveConfig(symbol=symbol, sleeve_capital=self.sleeve_capital,
                               f=self.f)
            sm = SleeveStateMachine(cfg)
            om = OrderManager(broker=self.broker, symbol=symbol,
                              session=self.session, sm=sm, store=self.store,
                              on_event=self.on_event)
            rt = SleeveRuntime(symbol=symbol, sm=sm, om=om, history=hist)
            self.sleeves[symbol] = rt

            try:
                sh = (hours or {}).get(symbol) or self.broker.session_hours(symbol, day)
            except MarketClosedError as exc:
                # Weekend or holiday. Expected, not a fault — an always-on
                # service meets this every Saturday and Sunday.
                rt.dormant, rt.dormant_reason = True, "market_closed"
                self.on_event("info", f"{symbol} MARKET CLOSED: {exc}")
                self.store.daily(self.session, symbol, gate_ok=0,
                                 gate_reason="market_closed",
                                 account_equity=equity,
                                 sleeve_capital=self.sleeve_capital)
                continue
            atr5 = hist.atr5()
            gate = sm.begin_session(day, atr5, sh.is_half_day, late_open=False)
            om.apply(sm.drain_intents())
            if not gate.ok:
                rt.dormant, rt.dormant_reason = True, gate.reason
                self.on_event("info", f"{symbol} GATE OFF: {gate.reason}")
            self.store.daily(self.session, symbol, gate_ok=int(gate.ok),
                             gate_reason=gate.reason, atr5=atr5,
                             thr80=hist.thr80(), account_equity=equity,
                             sleeve_capital=self.sleeve_capital)

    # ----------------------------------------------------------- 10:00
    def apply_morning_filter(self, symbol: str, bars: list[Bar]) -> bool:
        rt = self.sleeves[symbol]
        if rt.dormant or rt.filtered:
            return not rt.dormant
        stats = session_stats(bars)
        thr80 = rt.history.thr80()
        decision = rt.sm.apply_morning_filter(stats.or30, thr80, stats.pos10)
        rt.om.apply(rt.sm.drain_intents())
        rt.filtered = True
        if not decision.ok:
            rt.dormant, rt.dormant_reason = True, decision.reason
            self.on_event("info", f"{symbol} STAND DOWN: {decision.reason}")
        self.store.daily(self.session, symbol, filter_ok=int(decision.ok),
                         filter_reason=decision.reason, or30=stats.or30,
                         pos10=stats.pos10, thr80=thr80)
        return decision.ok

    # ------------------------------------------------- 09:30 .. 15:55
    def on_bar(self, symbol: str, bar: Bar) -> None:
        """One completed 5-minute bar. The only entry point during the session.

        Gap detection is not optional (§ Stage 2 acceptance): a missed bar
        understates `session_high`, which is the anchor the whole strategy
        ratchets from.
        """
        rt = self.sleeves[symbol]
        prev = max(rt.session_bars) if rt.session_bars else None
        if prev is not None and bar.idx > prev + 1:
            self.on_event("error", f"{symbol} BAR GAP: {prev} -> {bar.idx}; "
                                   "session_high may be understated")
        rt.session_bars[bar.idx] = bar
        self.store.bar(symbol, self.session, bar.idx, bar.open, bar.high,
                       bar.low, bar.close, bar.volume)

        if bar.idx == FILTER_IDX:
            ordered = [rt.session_bars[i] for i in sorted(rt.session_bars)]
            self.apply_morning_filter(symbol, ordered)
        if rt.dormant:
            return

        if bar.idx >= START_IDX and not rt.activated:
            # Per symbol, and contained to that symbol: entitlements are per
            # contract, so one sleeve losing its feed says nothing about the
            # other. Letting this propagate stood the whole session down on
            # 2026-08-06 when a single probe was inconclusive.
            try:
                self.broker.assert_live_data(symbol)   # never arm on delayed data
            except NotLiveDataError as exc:
                rt.dormant, rt.dormant_reason = True, "not_live_data"
                self.on_event("critical", f"{symbol} NOT LIVE DATA: {exc} — "
                                          f"this sleeve stands down; the other "
                                          f"is unaffected")
                self.store.daily(self.session, symbol, filter_ok=0,
                                 filter_reason="not_live_data")
                return
            rt.activated = True
        rt.sm.on_bar_open(bar.idx)
        rt.om.apply(rt.sm.drain_intents())
        rt.om.on_executions(bar.idx)
        rt.sm.on_bar_close(bar)
        rt.om.apply(rt.sm.drain_intents())
        rt.om.on_executions(bar.idx)
        self.store.counters(self.session, symbol, rt.sm.fills, rt.sm.stop_outs,
                            rt.sm.state.value if hasattr(rt.sm.state, "value")
                            else str(rt.sm.state))

    def poll(self, bar_idx: int) -> None:
        """Between bars: drain executions so the re-arm is immediate (§4.5)."""
        for rt in self.sleeves.values():
            if not rt.dormant:
                rt.om.on_executions(bar_idx)

    # ----------------------------------------------------------- 15:55
    def flatten_all(self, bar_idx: int = FLATTEN_IDX,
                    settle: float = 2.0) -> dict[str, bool]:
        """15:55 — cancel everything, close any position (§2.8).

        The flatten's own executions book the trade through the ordinary exit
        path, at the price they actually filled at. `sm.flatten` is therefore
        only needed to close the *session*, and it must never be handed a price.

        It used to be called unconditionally with `price=0.0`, on a comment
        asserting "not in a position now" — an assumption that is false exactly
        when it matters. On 2026-08-06 `ensure_flat` failed, the sleeve was still
        holding 541 shares, and booking an exit at zero reported the day as
        **-4018 bp** against a real position that was merely still open. A
        fabricated price is worse than no number: it looks like a catastrophic
        loss and buries the real fault, which was that 541 shares were about to
        be carried overnight.
        """
        out = {}
        for symbol, rt in self.sleeves.items():
            rt.om._cancel_entry()
            rt.om._cancel_bracket()
            flat = rt.om.ensure_flat(settle=settle)
            if rt.sm.in_position and not flat:
                pos = self.broker.position(symbol)
                self.on_event("critical",
                              f"{symbol} STILL HOLDS {pos:.0f} SHARES — not "
                              f"booking a trade, because the position is real "
                              f"and still open. Close it by hand now: §1's first "
                              f"design priority is never holding overnight.")
            else:
                rt.sm.flatten(price=0.0, bar_idx=bar_idx)
                rt.om.apply(rt.sm.drain_intents())
            out[symbol] = flat
        return out

    # ----------------------------------------------------------- 16:00
    def verify_flat(self) -> bool:
        ok = True
        for symbol in self.symbols:
            pos = self.broker.position(symbol)
            if abs(pos) > 1e-9:
                ok = False
                self.on_event("critical",
                              f"{symbol} NOT FLAT at 16:00: position={pos}")
        if ok:
            self.on_event("info", "all sleeves flat")
        return ok

    # ----------------------------------------------------------- 16:10
    def reconcile(self) -> dict[str, dict]:
        out = {}
        for symbol, rt in self.sleeves.items():
            summary = rt.om.reconcile()
            realised = sum(t.ret for t in rt.sm.trades)
            self.store.daily(self.session, symbol, fills=rt.sm.fills,
                             stop_outs=rt.sm.stop_outs, realised_pnl=realised,
                             flat_at_close=int(abs(self.broker.position(symbol)) < 1e-9))
            out[symbol] = summary
            self.on_event("info",
                          f"{symbol} EOD fills={rt.sm.fills} stops={rt.sm.stop_outs} "
                          f"pnl={realised*1e4:.1f}bp agrees={summary['agrees']}")
        return out

    # ------------------------------------------------------- safety (§6)
    def day_loss_breached(self) -> bool:
        """§6 / §12 DAY_LOSS_KILL. Checked by the caller; acting on it is
        Stage 7's `risk.py`, but the measurement belongs with the P&L."""
        for symbol, rt in self.sleeves.items():
            realised = sum(t.ret for t in rt.sm.trades)
            if realised <= DAY_LOSS_KILL:
                self.on_event("critical",
                              f"{symbol} day loss {realised:.2%} <= "
                              f"{DAY_LOSS_KILL:.2%} — kill switch condition")
                return True
        return False

    def on_connect(self) -> dict[str, dict]:
        """§3 — every connect is a restart. Reconcile before resuming."""
        if not self.broker.connected:
            self.broker.connect()
        return {s: rt.om.reconcile() for s, rt in self.sleeves.items()}
