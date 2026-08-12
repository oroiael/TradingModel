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
import time
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
from sleeve import (                                        # noqa: E402
    Intent, IntentKind, SleeveConfig, SleeveStateMachine,
)
from store import Store                                     # noqa: E402
from strategy_core import (                                 # noqa: E402
    Bar, FeatureHistory, session_stats,
)
from spec_constants import (                                # noqa: E402
    DAY_LOSS_KILL, F_SIZE, FLATTEN_TIME, HARD_FLAT_BY, START_TIME,
    TIMEZONE, W_PER_SLEEVE, _minutes, bar_index,
)

NY = ZoneInfo("America/New_York")
START_IDX = bar_index("11:00")
FILTER_IDX = bar_index("09:55")          # bar 5; closes at 10:00
FLATTEN_IDX = bar_index("15:55")

#: §2 of the plan — capital basis is capped, so the published cost rows apply.
CAPITAL_CAP = 150_000.0


def _at_time(day: datetime, hhmm: str) -> datetime:
    """`day` at the given exchange wall-clock time."""
    h, m = (int(v) for v in hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


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

            # §3 — reconciliation from the broker is the only way state is ever
            # established, "so there is no distinct restart path, because every
            # path is the restart path". The cold path was the exception, and
            # nothing said so: `Runner.pre_open` connects before `self.sleeves`
            # exists, so `on_connect` iterated an empty dict and reconciled
            # nothing, and this method then built fresh state machines without
            # asking the broker anything. Only a *re*connect ever reconciled.
            #
            # It runs before the gate, and before the market-closed check, on
            # purpose: a position left by a dead process is exactly as real on a
            # holiday or a gated-off day, and those are the days nothing else
            # would look.
            summary = om.reconcile()
            if summary["position"] or summary["working"]:
                self.on_event("warn",
                              f"{symbol} pre-open reconcile found broker state "
                              f"already in place: position={summary['position']:.0f}, "
                              f"{summary['working']} working order(s) — adopted, "
                              f"not replaced")

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

    def stand_down(self, symbol: Optional[str], reason: str,
                   detail: str = "") -> list[str]:
        """Stop a sleeve trading, and take its resting order off the market.

        One sleeve when the caller knows which — entitlements are per contract,
        and on 2026-08-06 a `NotLiveDataError` on SOXL ended the session for
        SOXS too. **All** of them when it does not: an unattributed live-data
        failure could be either, and §4 forbids trading on delayed data.

        The DORMANT intent is applied rather than the flag merely being set.
        Both `not_live_data` paths used to set `rt.dormant` directly, which
        skipped `_dormant` entirely — so a sleeve that lost its feed while armed
        went dormant with its buy limit still resting at IBKR, free to fill into
        a sleeve that had stopped watching.
        """
        targets = [symbol] if symbol in self.sleeves else list(self.sleeves)
        stood_down = []
        for s in targets:
            rt = self.sleeves[s]
            if rt.dormant:
                continue
            rt.dormant, rt.dormant_reason = True, reason
            stood_down.append(s)
            self.on_event("critical", f"{s} STANDING DOWN ({reason})"
                                      + (f": {detail}" if detail else ""))
            self.store.daily(self.session, s, filter_ok=0, filter_reason=reason)
            rt.om.apply([Intent(kind=IntentKind.DORMANT,
                                bar_idx=rt.sm._last_bar_idx, reason=reason)])
        return stood_down

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
                self.stand_down(symbol, "not_live_data",
                                f"{exc} — this sleeve only; the other is "
                                f"unaffected, entitlements are per contract")
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

    # ----------------------------------------------------------- 11:00
    def activate_due(self, now: datetime) -> list[str]:
        """§2.5's activation is a **clock** event. Fire it on the clock.

        `SleeveStateMachine.on_bar_open` already says so — "at 11:00 the limit
        goes live priced off the bars completed before it" — and the backtest
        does exactly that: `replay.py` opens bar 18 and then lets bar 18 trade
        against the resting limit.

        The live runner could not. It only ever learns of a bar once the feed
        reports it *completed*, so the bar labelled 11:00 arrived at 11:05 and
        the limit was armed after that bar had already traded. Every session,
        five minutes late.

        Measured against the 2020-07 -> 2026-07 sample by running the reference
        engine at `start_idx=19` instead of 18:

            SOXL  65.93 -> 62.02 bp/ON-day   (-3.91)
            SOXS  61.18 -> 57.72 bp/ON-day   (-3.46)

        — about 6% of the edge, given away structurally rather than to the
        market. The anchor needs nothing that is not already in hand at 11:00:
        §2.5 prices off *prior* bars, and bars 0..17 have all closed by then.

        Refuses to arm on an incomplete record, because an anchor built from a
        gapped session understates the session high, which is the one input the
        whole strategy ratchets from.
        """
        fired = []
        if now < _at_time(now, START_TIME):
            return fired
        for symbol, rt in self.sleeves.items():
            if rt.dormant or rt.activated or not rt.filtered:
                continue
            have = set(rt.session_bars)
            missing = [i for i in range(START_IDX) if i not in have]
            if missing:
                self.on_event("warn",
                              f"{symbol} 11:00 reached but bars {missing[:5]}"
                              f"{'...' if len(missing) > 5 else ''} are missing "
                              f"— not arming on an understated session high")
                continue
            try:
                self.broker.assert_live_data(symbol)
            except NotLiveDataError as exc:
                self.stand_down(symbol, "not_live_data", str(exc))
                continue
            rt.activated = True
            rt.sm.on_bar_open(START_IDX)
            rt.om.apply(rt.sm.drain_intents())
            fired.append(symbol)
            self.on_event("info", f"{symbol} 11:00 activation on the clock")
        return fired

    # ----------------------------------------------------------- 15:55
    def hard_flat_budget(self, now: Optional[datetime] = None,
                         margin: float = 20.0) -> float:
        """Seconds the flatten may spend, from `now` to §12's `HARD_FLAT_BY`.

        §12 sets the flatten at 15:55 and the hard deadline at 16:00, so a
        flatten that begins on time has five minutes. On 2026-08-10 it used
        **23 seconds** of them and carried 524 shares overnight, because the
        loop counted attempts instead of watching the clock.

        `margin` keeps a little back so the 16:00 verify runs against a settled
        book rather than against orders still in flight. Never negative: a
        flatten that starts late still gets one attempt (`ensure_flat` checks
        the position before it checks the budget).
        """
        now = now or datetime.now(ZoneInfo(TIMEZONE))
        hh, mm = (int(v) for v in HARD_FLAT_BY.split(":"))
        deadline = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        # Capped at the §12 window itself (15:55 -> 16:00). Called at 09:00 by a
        # disconnect path the raw arithmetic would hand out seven hours, and
        # `ensure_flat` would spend every one of them.
        window = (_minutes(HARD_FLAT_BY) - _minutes(FLATTEN_TIME)) * 60.0
        return max(0.0, min(window, (deadline - now).total_seconds() - margin))

    def flatten_all(self, bar_idx: int = FLATTEN_IDX,
                    settle: float = 2.0,
                    now: Optional[datetime] = None,
                    budget: Optional[float] = None) -> dict[str, bool]:
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
        # The deadline is only in force when the caller supplies the clock.
        # Reading `datetime.now()` here made the flatten's duration depend on
        # what time of day the process happened to run: the same call returned a
        # 0-second budget after 16:00 and a 300-second one in the morning, which
        # is how a 300-second spin got through a green suite. `run.py` owns the
        # wall clock and passes it; everything else keeps the attempt-based path.
        if budget is None and now is not None:
            budget = self.hard_flat_budget(now)
        started = time.monotonic()
        out = {}
        for symbol, rt in self.sleeves.items():
            # Drain before deciding. `ensure_flat` returns immediately when the
            # broker is already flat, without draining, so an exit that had
            # already settled — above all one this engine did not order — was
            # never attributed before the sleeve was asked whether it still held
            # anything. It answered yes, and the booking below did the rest.
            rt.om.on_executions(bar_idx)
            # Share what is left between the sleeves that still hold something.
            # Sequential and un-shared, the first stuck sleeve would spend the
            # whole budget and leave the second with none — turning one
            # overnight position into two.
            share = None
            if budget is not None:
                left = max(0.0, budget - (time.monotonic() - started))
                holding = sum(1 for s in self.symbols
                              if abs(self.broker.position(s)) > 1e-9)
                share = left / max(1, holding)
            flat = rt.om.ensure_flat(settle=settle, budget=share)
            # `sm.flatten` books a trade whenever the sleeve is in a position,
            # and it is only ever handed 0.0 — so the guard is `in_position`,
            # not `not flat`. Guarding on `not flat` left the other half open:
            # a position closed by something the engine could not attribute
            # leaves the sleeve in_position with the broker already flat, and
            # that booked the trade at zero. On 2026-08-06 the same arithmetic
            # reported a day as -4018 bp; a reproduction against a watchdog
            # flatten reports -9084 against a real +101.
            if rt.sm.in_position:
                pos = self.broker.position(symbol)
                if not flat:
                    self.on_event("critical",
                                  f"{symbol} STILL HOLDS {pos:.0f} SHARES — not "
                                  f"booking a trade, because the position is real "
                                  f"and still open. Close it by hand now: §1's first "
                                  f"design priority is never holding overnight.")
                else:
                    # Flat at the broker, still holding as far as the sleeve
                    # knows, and no execution explained the difference — so
                    # there is no price to book. A missing trade is recoverable
                    # from IBKR's own log; a fabricated one looks like a
                    # catastrophic loss and buries whatever really happened.
                    self.on_event("critical",
                                  f"{symbol} is flat at the broker but the sleeve "
                                  f"still holds {rt.sm._qty:.0f} shares from bar "
                                  f"{rt.sm.entry_bar} @ {rt.sm._entry_px:.4f}, and "
                                  f"no execution accounts for the close. NOT "
                                  f"booking a trade — reconcile this against "
                                  f"IBKR's execution log by hand.")
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

    # ----------------------------------------------------------- 16:00
    def record_session_tail(self, day: Optional[datetime] = None) -> dict[str, int]:
        """Store the bars the session loop never saw. **Writes, decides nothing.**

        `run_session` polls until 15:55 and stops, so the bar labelled 15:50
        (`LAST_HOLDING_IDX`) and the one labelled 15:55 (`FLATTEN_IDX`) are
        never recorded — a real session leaves 76 bars, idx 0..75. Nothing in
        the *trading* path needs them: the sleeve is flat by then.

        `report.py` does. Its shadow replays the recorded bars, and
        `replay_session`'s tail rule force-flattens at the last bar it is given
        — so the shadow closed its last trade at bar 75 while the live session
        went on trading in bar 76. On 2026-08-10 that understated the SOXS
        shadow by 68 bp (233.04 against 301.44) and made the live session look
        like it had beaten the backtest.

        This is deliberately not on the trading path and deliberately not
        idempotency-critical: `store.bar` is INSERT OR REPLACE on
        (symbol, session, bar_idx, source).
        """
        day = day or datetime.now(NY)
        out: dict[str, int] = {}
        for symbol in self.symbols:
            n = 0
            try:
                bars = self.broker.historical_bars(symbol, day, "1 D", "5 mins")
            except Exception as exc:                            # noqa: BLE001
                # The record is evidence, not control. Failing to complete it
                # must never affect the reconcile that follows.
                self.on_event("warn", f"{symbol} tail bars unavailable: {exc!r}")
                out[symbol] = 0
                continue
            for b in bars:
                if b.idx > FLATTEN_IDX:
                    continue
                self.store.bar(symbol, self.session, b.idx, b.open, b.high,
                               b.low, b.close, b.volume)
                n += 1
            out[symbol] = n
            self.on_event("info", f"{symbol} session record completed to bar "
                                  f"{max((b.idx for b in bars), default=-1)} "
                                  f"({n} bars)")
        return out

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
