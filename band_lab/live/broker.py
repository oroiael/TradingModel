"""
Stage 2 — the IBKR adapter (ib_async), plus a FakeIB test double.

`PHASE2_PLAN.md` §3: reconciliation from the broker is the only way state is
ever established, so there is no distinct "restart path" — every path is the
restart path. This module therefore exposes the broker as a set of *queries*
about the world (what is my position, what orders are working, what did I
execute) and a small set of commands, and never caches anything the broker
can be asked for.

Everything here is guarded by the §6 open questions, which could not be
verified against IBKR's documentation from the build environment (outbound
access to interactivebrokers.github.io is blocked, still, as of this build).
Each unverified assumption is marked `ASSUMPTION §6.n` at its use site so it
can be checked on the first paper session rather than discovered later.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from strategy_core import Bar  # noqa: E402

NY = ZoneInfo("America/New_York")

#: §2 of the plan — the engine refuses to trade on delayed data.
#: 1 = live, 2 = frozen, 3 = delayed, 4 = delayed-frozen.
MARKET_DATA_LIVE = 1

#: IBKR error codes that say, in words, "you are not getting live data here".
#: These are the *reliable* signal — observed 2026-08-03, when TWS emitted 10089
#: four times while `marketDataType` stayed silent. The `marketDataType` probe
#: below is the backstop for a silent downgrade, not the primary detector.
NO_LIVE_DATA_ERRORS = frozenset({354, 10089, 10090, 10167, 10168})

#: How long to wait for TWS to describe the feed before warning and proceeding.
PROBE_SECONDS = 5.0


def _has_quote(ticker) -> bool:
    """Is real data flowing? A live bid/ask is evidence in its own right."""
    for attr in ("bid", "ask", "last"):
        v = getattr(ticker, attr, None)
        if v is not None and v == v and v > 0:    # not None, not NaN, positive
            return True
    return False


#: `ib_async.OrderStatus.DoneStates`, transcribed from the installed package.
#: An order in any *other* state — including `PendingCancel` — is still working
#: as far as the broker is concerned, because `IB.openTrades()` is defined as
#: "every trade whose status is not a DoneState".
#:
#: This exists because the two implementations below had drifted. `IBBroker`
#: reports whatever `openTrades()` returns, so a cancel that TWS has not yet
#: confirmed shows up as working — which is what `LMT SELL 524 (PendingCancel)`
#: was on 2026-08-10. `FakeIB` filtered to `Submitted`/`PreSubmitted`, so the
#: state that broke that session could not be represented in a test at all.
#: One predicate, used by both, is the only thing that keeps them honest.
DONE_STATES = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive"})

#: `ib_async.OrderStatus.ActiveStates`. Note `PendingCancel` is in neither set:
#: it is a limbo the client enters on `cancelOrder` and leaves only when TWS
#: says so. Nothing may treat it as done.
ACTIVE_STATES = frozenset({"PendingSubmit", "ApiPending", "PreSubmitted",
                           "Submitted", "ValidationError", "ApiUpdate"})


def is_working(status: str) -> bool:
    """Would `IB.openTrades()` still return an order in this state?"""
    return status not in DONE_STATES


class BrokerError(RuntimeError):
    pass


class NotLiveDataError(BrokerError):
    """Raised when the feed is not real-time. Never trade through this."""


class MarketClosedError(BrokerError):
    """No regular session today — weekend or holiday.

    This is an *expected* daily condition, not a fault. It gets its own type
    so the engine can stand the sleeves down and exit cleanly, while a genuine
    failure to read contract details still fails loudly. An always-on service
    meets this every Saturday and Sunday.
    """


def bar_time_et(raw) -> datetime:
    """An IBKR bar timestamp as **exchange wall-clock**, whatever form it takes.

    `Bar.idx` is minutes since 09:30 ET, so this conversion is load-bearing: an
    hour of error is twelve bars of error, and a bar index outside 0-77 quietly
    matches neither the 10:00 filter (bar 5) nor the 11:00 activation (bar 18) —
    the engine then runs a whole session without deciding anything.

    `ib_async.util.parseIBDatetime` can hand back any of three things depending
    on the TWS version and its configured timezone: a tz-aware datetime carrying
    an IANA zone, a tz-aware UTC datetime decoded from an epoch, or a naive one
    with no zone at all. Only the last is safe to read hour-of-day from
    directly, and only because a zone-less TWS timestamp is already exchange
    time — the same convention the repository's CSVs use.
    """
    if not isinstance(raw, datetime):
        try:
            return datetime.strptime(str(raw), "%Y%m%d  %H:%M:%S")
        except ValueError:
            return datetime.strptime(str(raw)[:19].replace("-", "").replace(" ", ""),
                                     "%Y%m%d%H:%M:%S")
    return raw.astimezone(NY).replace(tzinfo=None) if raw.tzinfo else raw


def parse_liquid_hours(hours: str, target: str):
    """IBKR `liquidHours` -> (open, close) for `target` (YYYYMMDD), or None.

    Format is `20260803:0930-20260803:1600;20260804:CLOSED`, with an older
    variant that omits the date on the close side. Both are handled. A day
    marked CLOSED and a day that is simply absent both return None — for the
    caller they mean the same thing.

    Split out as a plain function because the version inside `session_hours`
    could only be exercised against a live TWS, which is how it shipped with
    an unhandled weekend.
    """
    for chunk in (hours or "").split(";"):
        chunk = chunk.strip()
        if not chunk or not chunk.startswith(target):
            continue
        if "CLOSED" in chunk.upper():
            return None
        if "-" not in chunk:
            continue
        a, b = chunk.split("-", 1)
        try:
            o = datetime.strptime(a, "%Y%m%d:%H%M").replace(tzinfo=NY)
        except ValueError:
            continue
        try:
            c = datetime.strptime(b, "%Y%m%d:%H%M").replace(tzinfo=NY)
        except ValueError:
            try:                       # older form: close time only
                t = datetime.strptime(b, "%H%M")
            except ValueError:
                continue
            c = o.replace(hour=t.hour, minute=t.minute)
        return o, c
    return None


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    last: float
    bid_size: float = 0.0
    ask_size: float = 0.0

    @property
    def ok(self) -> bool:
        return self.bid > 0 and self.ask > 0 and self.ask >= self.bid


@dataclass(frozen=True)
class Execution:
    exec_id: str
    order_ref: str
    perm_id: int
    symbol: str
    side: str            # "BOT" | "SLD"
    qty: float
    price: float
    time: datetime


@dataclass(frozen=True)
class WorkingOrder:
    order_ref: str
    order_id: int
    perm_id: int
    symbol: str
    action: str
    order_type: str
    qty: float
    filled: float
    limit_px: float
    aux_px: float
    oca_group: str
    status: str

    @property
    def remaining(self) -> float:
        return self.qty - self.filled


@dataclass(frozen=True)
class SessionHours:
    """Today's regular trading hours, from contract details."""
    open: datetime
    close: datetime
    is_half_day: bool

    @property
    def minutes(self) -> float:
        return (self.close - self.open).total_seconds() / 60.0


# --------------------------------------------------------------------------
class Broker:
    """Interface the engine and OrderManager code against.

    Implemented by `IBBroker` (real) and `FakeIB` (tests). Keeping the engine
    ignorant of ib_async is what lets §10.9-12 be tested without a broker.
    """

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    @property
    def connected(self) -> bool: ...
    def assert_live_data(self, symbol: Optional[str] = None) -> None: ...
    def session_hours(self, symbol: str, day: datetime) -> SessionHours: ...
    def net_liquidation(self) -> float: ...
    def position(self, symbol: str) -> float: ...
    def working_orders(self, symbol: str) -> list[WorkingOrder]: ...
    def executions(self, symbol: str) -> list[Execution]: ...
    def quote(self, symbol: str) -> Quote: ...
    def historical_bars(self, symbol: str, end: datetime, duration: str,
                        bar_size: str = "5 mins") -> list[Bar]: ...
    def historical_sessions(self, symbol: str, end: datetime, duration: str,
                            bar_size: str = "5 mins") -> list[tuple]: ...
    def place_limit(self, symbol, action, qty, limit_px, order_ref,
                    oca_group="", transmit=True) -> int: ...
    def place_stop(self, symbol, action, qty, stop_px, order_ref,
                   oca_group="", transmit=True) -> int: ...
    def place_market(self, symbol, action, qty, order_ref) -> int: ...
    def modify_limit(self, order_id: int, limit_px: float, qty: float) -> None: ...
    def cancel(self, order_id: int) -> None: ...
    def cancel_all(self) -> None: ...


# --------------------------------------------------------------------------
class IBBroker(Broker):
    """ib_async implementation. Imported lazily so tests never need ib_async."""

    def __init__(self, host="127.0.0.1", port=7497, client_id=11,
                 exchange="SMART", primary="ARCA", readonly=False,
                 on_event: Optional[Callable[[str, str], None]] = None) -> None:
        self.host, self.port, self.client_id = host, port, client_id
        self.exchange, self.primary = exchange, primary
        self.readonly = readonly
        self._on_event = on_event or (lambda level, msg: None)
        self._ib = None
        self._contracts: dict[str, Any] = {}
        self._dry_seq = 0
        self._no_live_data: set = set()
        self._error_hooked = False

    # ---------------------------------------------------------- lifecycle
    def connect(self) -> None:
        from ib_async import IB
        if self._ib is None:
            self._ib = IB()
        if self._ib.isConnected():
            return
        self._ib.connect(self.host, self.port, clientId=self.client_id,
                         timeout=30, readonly=self.readonly)
        if not self._error_hooked:
            # Once per IB object, not per connect — `+=` on an ib_async Event
            # registers a second handler and would double-fire on every reconnect.
            self._ib.errorEvent += self._on_ib_error
            self._error_hooked = True
        self._on_event("info", f"connected {self.host}:{self.port} "
                               f"clientId={self.client_id}")

    def _on_ib_error(self, reqId, errorCode, errorString, contract=None) -> None:
        """Record the subscription errors that mean the feed is not live.

        TWS reports a missing subscription by error code and then quietly serves
        delayed data. Nothing else in the API says so as plainly, so this is
        where §4's "must detect delayed-data mode and refuse to trade" is
        actually decided.
        """
        if errorCode not in NO_LIVE_DATA_ERRORS:
            return
        symbol = getattr(contract, "symbol", None) or "*"
        if symbol not in self._no_live_data:
            self._on_event("error", f"IBKR {errorCode} on {symbol}: {errorString}")
        self._no_live_data.add(symbol)

    def disconnect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()

    @property
    def connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    def _require(self):
        if not self.connected:
            raise BrokerError("not connected")
        return self._ib

    def contract(self, symbol: str):
        if symbol in self._contracts:
            return self._contracts[symbol]
        from ib_async import Stock
        ib = self._require()
        c = Stock(symbol, self.exchange, "USD", primaryExchange=self.primary)
        q = ib.qualifyContracts(c)
        if not q:
            raise BrokerError(f"could not qualify {symbol}")
        self._contracts[symbol] = q[0]
        return q[0]

    # ------------------------------------------------------------- guards
    def assert_live_data(self, symbol: Optional[str] = None) -> None:
        """§2 — refuse to trade on delayed data.

        `reqMarketDataType(1)` requests live; IBKR silently downgrades to
        delayed when the subscription is missing, which is exactly the failure
        this guards. The engine calls this before every order-placing phase.

        **History, because both mistakes are instructive.** Until 2026-08-03 this
        read `ib._ccr_probe_ticker`, an attribute nothing ever set, so it was a
        no-op on every real connection — found on an account that was in fact
        serving delayed data. The replacement then refused on *silence*, on the
        reasoning that unknown should fail safe. On 2026-08-06 that stood a
        healthy sleeve down at 11:05 on a confirmed-good subscription and cost
        the session.

        The measurement settled it: **TWS does not reliably send a
        `marketDataType` callback when it is already serving what was asked
        for.** Silence is the ordinary case, so refusing on it makes the guard
        fire mostly on healthy days — the opposite of a safety feature.

        What refuses now is **positive evidence** of non-live data, in order of
        authority:

        1. the **error codes** in `NO_LIVE_DATA_ERRORS` — TWS says so in words,
           and this is what actually fired in the field on 2026-08-03; and
        2. **`Ticker.marketDataType` of 2/3/4** — frozen or delayed arriving
           without an error.

        Neither present, with a quote flowing, passes silently. Neither present
        and no quote either passes with a loud warning rather than a refusal:
        the authoritative detector is the error path, and standing a whole
        session down on an inconclusive probe is the worse of the two failures.
        §4's requirement is carried by (1) and (2), which is where the signal
        actually lives.
        """
        ib = self._require()
        ib.reqMarketDataType(MARKET_DATA_LIVE)

        def _refuse(why: str) -> None:
            raise NotLiveDataError(f"{symbol or 'account'}: {why}")

        if "*" in self._no_live_data or (symbol and symbol in self._no_live_data):
            _refuse("IBKR reported no live market-data subscription "
                    "(see the 10089/354 error above); §4 forbids trading on "
                    "delayed data")
        if symbol is None:
            return

        contract = self.contract(symbol)
        ticker = ib.reqMktData(contract, "", False, False)
        ticker.marketDataType = 0                 # sentinel; the default is 1
        deadline = time.time() + PROBE_SECONDS
        while time.time() < deadline:
            if ticker.marketDataType or _has_quote(ticker):
                break
            if symbol in self._no_live_data:      # the error arrived mid-wait
                break
            ib.sleep(0.1)
        mdt = int(ticker.marketDataType or 0)
        quoted = _has_quote(ticker)
        if symbol not in self._no_live_data:
            # A rejected subscription has no ticker to cancel, and asking makes
            # TWS answer 300 "Can\'t find EId" — a confusing error attributed to
            # whatever step happens to be running when it arrives.
            try:
                ib.cancelMktData(contract)
            except Exception:                     # noqa: BLE001
                pass                              # tidying up must not refuse

        if symbol in self._no_live_data:
            _refuse("IBKR reported no live market-data subscription")
        if mdt in (2, 3, 4):
            _refuse(f"marketDataType={mdt} "
                    f"(2=frozen 3=delayed 4=delayed-frozen) — refusing to trade")
        if mdt == MARKET_DATA_LIVE:
            return
        self._on_event(
            "warn",
            f"{symbol}: no marketDataType callback in {PROBE_SECONDS:.0f}s"
            + (" but a quote is flowing" if quoted else " and no quote arrived")
            + " — proceeding. IBKR reported no subscription error, which is the"
              " signal that fires when the feed is not live.")

    def session_hours(self, symbol: str, day: datetime) -> SessionHours:
        """Today's RTH from contract details.

        ASSUMPTION §6: half days are expressed as a shortened liquidHours
        range, not a separate flag. Raises `MarketClosedError` on a weekend or
        holiday — the caller stands down rather than treating it as a fault.
        """
        ib = self._require()
        det = ib.reqContractDetails(self.contract(symbol))
        if not det:
            raise BrokerError(f"no contract details for {symbol}")
        hours = det[0].liquidHours or det[0].tradingHours or ""
        target = day.astimezone(NY).strftime("%Y%m%d")
        parsed = parse_liquid_hours(hours, target)
        if parsed is None:
            weekday = day.astimezone(NY).strftime("%A")
            raise MarketClosedError(
                f"{symbol}: no regular session on {target} ({weekday})")
        o, c = parsed
        return SessionHours(o, c,
                            is_half_day=(c - o) < timedelta(hours=6, minutes=15))

    # -------------------------------------------------------------- state
    def net_liquidation(self) -> float:
        ib = self._require()
        for v in ib.accountValues():
            if v.tag == "NetLiquidation" and v.currency == "USD":
                return float(v.value)
        raise BrokerError("NetLiquidation (USD) not reported")

    def position(self, symbol: str) -> float:
        ib = self._require()
        return float(sum(p.position for p in ib.positions()
                         if p.contract.symbol == symbol))

    def working_orders(self, symbol: str) -> list[WorkingOrder]:
        ib = self._require()
        out = []
        for t in ib.openTrades():
            if t.contract.symbol != symbol:
                continue
            o, s = t.order, t.orderStatus
            out.append(WorkingOrder(
                order_ref=o.orderRef or "", order_id=o.orderId,
                perm_id=o.permId or 0, symbol=symbol, action=o.action,
                order_type=o.orderType, qty=float(o.totalQuantity),
                filled=float(s.filled or 0.0), limit_px=float(o.lmtPrice or 0.0),
                aux_px=float(o.auxPrice or 0.0), oca_group=o.ocaGroup or "",
                status=s.status))
        return out

    def executions(self, symbol: str) -> list[Execution]:
        ib = self._require()
        out = []
        for f in ib.fills():
            if f.contract.symbol != symbol:
                continue
            e = f.execution
            out.append(Execution(exec_id=e.execId, order_ref=e.orderRef or "",
                                 perm_id=e.permId or 0, symbol=symbol,
                                 side=e.side, qty=float(e.shares),
                                 price=float(e.price), time=e.time))
        return out

    def quote(self, symbol: str) -> Quote:
        ib = self._require()
        t = ib.reqMktData(self.contract(symbol), "", False, False)
        ib.sleep(0.4)
        def _f(x):
            return float(x) if x is not None and x == x else 0.0
        return Quote(_f(t.bid), _f(t.ask), _f(t.last), _f(t.bidSize), _f(t.askSize))

    def _dated_bars(self, symbol, end, duration, bar_size):
        """(date, Bar) pairs. Bars are clock-indexed like the CSVs — §2.1:
        index 0 is the 09:30 bar, addressed by clock time, not file position."""
        ib = self._require()
        bars = ib.reqHistoricalData(
            self.contract(symbol),
            endDateTime=end.strftime("%Y%m%d %H:%M:%S US/Eastern") if end else "",
            durationStr=duration, barSizeSetting=bar_size, whatToShow="TRADES",
            useRTH=True, formatDate=1, keepUpToDate=False)
        step = 5 if bar_size.startswith("5") else 1
        out = []
        for b in bars:
            dt = bar_time_et(b.date)
            mins = dt.hour * 60 + dt.minute - (9 * 60 + 30)
            out.append((dt.date(), Bar(mins // step, float(b.open), float(b.high),
                                       float(b.low), float(b.close), float(b.volume))))
        return out

    def historical_bars(self, symbol, end, duration, bar_size="5 mins") -> list[Bar]:
        """Bars for **one** calendar session — the day `end` falls on.

        `Bar.idx` is a clock offset from 09:30 and carries no date, so a window
        spanning two sessions collapses into one after `sorted(key=idx)`: the
        prior session's 11:00-16:00 bars would arrive as *today's* afternoon.
        IBKR's duration semantics for a request made inside RTH are §6.4 — an
        open question — so the date is filtered here rather than assumed away.
        Before the open this correctly yields nothing: no session, no bars.
        """
        dated = self._dated_bars(symbol, end, duration, bar_size)
        if not dated:
            return []
        when = end or datetime.now(NY)
        want = (when.astimezone(NY) if when.tzinfo else when).date()
        return [b for d, b in dated if d == want]

    def historical_sessions(self, symbol, end, duration,
                            bar_size="5 mins") -> list[tuple]:
        """Grouped by calendar date, oldest first — the shape FeatureHistory
        and the shadow-parity replay both consume."""
        grouped: dict = {}
        for day, bar in self._dated_bars(symbol, end, duration, bar_size):
            grouped.setdefault(day, []).append(bar)
        return [(d, sorted(v, key=lambda b: b.idx)) for d, v in sorted(grouped.items())]

    # ------------------------------------------------------------ commands
    def _dry(self, what: str) -> int:
        """Dry run: log the order that *would* have been sent, send nothing.

        `readonly` in ib_async is a client-side flag only — it skips two
        startup requests and does **not** stop `placeOrder`. Stage 4's
        acceptance ("one live session with orders not transmitted") therefore
        has to be enforced here, in the adapter, or `--dry-run` places real
        orders. Synthetic ids are negative so a stray modify/cancel against one
        is unmistakable and cannot collide with a real IBKR orderId.
        """
        self._dry_seq -= 1
        self._on_event("info", f"DRY RUN — not sent: {what}")
        return self._dry_seq

    def _order(self, action, qty, order_ref, oca_group, transmit):
        from ib_async import Order
        o = Order()
        o.action = action
        o.totalQuantity = qty
        o.orderRef = order_ref
        o.tif = "DAY"                 # §4.5 — belt and braces on flat-overnight
        o.outsideRth = False
        o.transmit = transmit
        if oca_group:
            o.ocaGroup = oca_group
            # ASSUMPTION §6.3: ocaType 1 = cancel remaining with block.
            o.ocaType = 1
        return o

    def place_limit(self, symbol, action, qty, limit_px, order_ref,
                    oca_group="", transmit=True) -> int:
        ib = self._require()
        px = round(float(limit_px), 2)
        if self.readonly:
            return self._dry(f"{action} LMT {qty} {symbol} @ {px} ({order_ref})")
        o = self._order(action, qty, order_ref, oca_group, transmit)
        o.orderType = "LMT"
        o.lmtPrice = px
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def place_stop(self, symbol, action, qty, stop_px, order_ref,
                   oca_group="", transmit=True) -> int:
        ib = self._require()
        px = round(float(stop_px), 2)
        if self.readonly:
            return self._dry(f"{action} STP {qty} {symbol} @ {px} ({order_ref})")
        o = self._order(action, qty, order_ref, oca_group, transmit)
        o.orderType = "STP"
        # ASSUMPTION §6.1: a broker-side STP that survives an API disconnect.
        # §6.1 requires this; it is the most safety-critical unverified item.
        o.auxPrice = px
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def place_market(self, symbol, action, qty, order_ref) -> int:
        ib = self._require()
        if self.readonly:
            return self._dry(f"{action} MKT {qty} {symbol} ({order_ref})")
        o = self._order(action, qty, order_ref, "", True)
        o.orderType = "MKT"          # §4.7 — MKT, not MOC
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def modify_limit(self, order_id: int, limit_px: float, qty: float) -> None:
        ib = self._require()
        if self.readonly or order_id < 0:
            self._dry(f"modify {order_id} -> {qty} @ {round(float(limit_px), 2)}")
            return
        for t in ib.openTrades():
            if t.order.orderId == order_id:
                t.order.lmtPrice = round(float(limit_px), 2)
                t.order.totalQuantity = qty
                ib.placeOrder(t.contract, t.order)   # same id = modify
                return
        raise BrokerError(f"order {order_id} not working; cannot modify")

    def cancel(self, order_id: int) -> None:
        ib = self._require()
        if self.readonly or order_id < 0:
            return
        for t in ib.openTrades():
            if t.order.orderId == order_id:
                ib.cancelOrder(t.order)
                return

    def cancel_all(self) -> None:
        if self.readonly:
            self._dry("reqGlobalCancel")
            return
        self._require().reqGlobalCancel()


# --------------------------------------------------------------------------
@dataclass
class _FakeOrder:
    order_id: int
    order_ref: str
    symbol: str
    action: str
    order_type: str
    qty: float
    limit_px: float = 0.0
    aux_px: float = 0.0
    oca_group: str = ""
    filled: float = 0.0
    status: str = "Submitted"


class FakeIB(Broker):
    """Deterministic in-memory broker for the §10 acceptance tests.

    It is not a market simulator — it fills only when a test tells it to. That
    keeps the tests about the engine's behaviour rather than about a second,
    unvalidated fill model.
    """

    def __init__(self, symbols=("SOXL", "SOXS"), equity=150_000.0) -> None:
        self.symbols = list(symbols)
        self.equity = equity
        self._connected = False
        self._next_id = 1
        self._next_perm = 1000
        self.orders: dict[int, _FakeOrder] = {}
        self.positions: dict[str, float] = {s: 0.0 for s in symbols}
        self.execs: list[Execution] = []
        self.quotes: dict[str, Quote] = {s: Quote(10.0, 10.02, 10.01) for s in symbols}
        self.hours: dict[str, SessionHours] = {}
        self.bars: dict[str, list[Bar]] = {}
        self.sessions: dict[str, list[tuple]] = {}
        self.market_data_type = MARKET_DATA_LIVE
        self.global_cancels = 0
        #: Leave cancels in `PendingCancel` instead of confirming them,
        #: reproducing the 2026-08-10 stall. See `cancel`.
        self.stall_cancels = False
        self.connect_count = 0

    # lifecycle
    def connect(self) -> None:
        self._connected = True
        self.connect_count += 1

    def disconnect(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def assert_live_data(self, symbol: Optional[str] = None) -> None:
        if self.market_data_type != MARKET_DATA_LIVE:
            raise NotLiveDataError(f"marketDataType={self.market_data_type}")

    def session_hours(self, symbol, day) -> SessionHours:
        if symbol in self.hours:
            return self.hours[symbol]
        o = day.replace(hour=9, minute=30, second=0, microsecond=0, tzinfo=NY)
        return SessionHours(o, o.replace(hour=16, minute=0), is_half_day=False)

    def net_liquidation(self) -> float:
        return self.equity

    def position(self, symbol) -> float:
        return self.positions.get(symbol, 0.0)

    def working_orders(self, symbol) -> list[WorkingOrder]:
        # `is_working`, not a hand-written status list: `IBBroker` reports
        # whatever `IB.openTrades()` returns, and that includes `PendingCancel`.
        return [WorkingOrder(o.order_ref, o.order_id, self._next_perm, o.symbol,
                             o.action, o.order_type, o.qty, o.filled,
                             o.limit_px, o.aux_px, o.oca_group, o.status)
                for o in self.orders.values()
                if o.symbol == symbol and is_working(o.status)]

    def executions(self, symbol) -> list[Execution]:
        return [e for e in self.execs if e.symbol == symbol]

    def quote(self, symbol) -> Quote:
        return self.quotes[symbol]

    def historical_bars(self, symbol, end, duration, bar_size="5 mins"):
        return list(self.bars.get(symbol, []))

    def historical_sessions(self, symbol, end, duration, bar_size="5 mins"):
        return list(self.sessions.get(symbol, []))

    # commands
    def _add(self, symbol, action, qty, order_type, order_ref,
             limit_px=0.0, aux_px=0.0, oca_group="") -> int:
        oid = self._next_id
        self._next_id += 1
        self.orders[oid] = _FakeOrder(oid, order_ref, symbol, action, order_type,
                                      float(qty), float(limit_px), float(aux_px),
                                      oca_group)
        return oid

    def place_limit(self, symbol, action, qty, limit_px, order_ref,
                    oca_group="", transmit=True) -> int:
        return self._add(symbol, action, qty, "LMT", order_ref,
                         limit_px=limit_px, oca_group=oca_group)

    def place_stop(self, symbol, action, qty, stop_px, order_ref,
                   oca_group="", transmit=True) -> int:
        return self._add(symbol, action, qty, "STP", order_ref,
                         aux_px=stop_px, oca_group=oca_group)

    def place_market(self, symbol, action, qty, order_ref) -> int:
        return self._add(symbol, action, qty, "MKT", order_ref)

    def modify_limit(self, order_id, limit_px, qty) -> None:
        o = self.orders[order_id]
        if o.status not in ("Submitted", "PreSubmitted"):
            raise BrokerError(f"order {order_id} not working")
        o.limit_px = float(limit_px)
        o.qty = float(qty)

    def cancel(self, order_id) -> None:
        """Cancel in two phases, the way `ib_async` actually does it.

        `IB.cancelOrder` sets the local status to `PendingCancel` and leaves it
        there until TWS confirms; only an untransmitted `PendingSubmit` order or
        an `Inactive` one goes straight to `Cancelled`. `PendingCancel` is in
        neither `ActiveStates` nor `DoneStates`, so `openTrades()` keeps
        returning it — which is precisely how two SOXL legs were still holding
        524 shares at 15:55 on 2026-08-10.

        `stall_cancels` leaves them there, so a test can reproduce that session
        without inventing a mechanism. The default confirms immediately, which
        is the ordinary case and keeps the happy path fast.
        """
        o = self.orders.get(order_id)
        if o is None or not is_working(o.status):
            return
        o.status = "PendingCancel"
        if not self.stall_cancels:
            o.status = "Cancelled"

    def confirm_cancels(self, symbol: Optional[str] = None) -> int:
        """TWS finally acknowledges — `PendingCancel` becomes `Cancelled`."""
        n = 0
        for o in self.orders.values():
            if o.status == "PendingCancel" and (symbol is None or o.symbol == symbol):
                o.status, n = "Cancelled", n + 1
        return n

    def cancel_all(self) -> None:
        # §6.7 `reqGlobalCancel`. Modelled as authoritative — it is the escape
        # hatch precisely because individual cancels can stall. Whether IBKR
        # really frees a stuck OCA leg this way is NOT verified here; see the
        # `ibkr-semantics` skill.
        self.global_cancels += 1
        for o in self.orders.values():
            if is_working(o.status):
                o.status = "Cancelled"

    # ------------------------------------------------------- test controls
    def fill(self, order_id: int, qty: Optional[float] = None,
             price: Optional[float] = None) -> Execution:
        """Fill (or partially fill) a working order, as the market would."""
        o = self.orders[order_id]
        q = float(o.qty - o.filled if qty is None else qty)
        px = float(o.limit_px or o.aux_px or self.quotes[o.symbol].last
                   if price is None else price)
        o.filled += q
        o.status = "Filled" if o.filled >= o.qty else "Submitted"
        sign = 1.0 if o.action == "BUY" else -1.0
        self.positions[o.symbol] = self.positions.get(o.symbol, 0.0) + sign * q
        e = Execution(f"exec-{len(self.execs)+1}", o.order_ref, self._next_perm,
                      o.symbol, "BOT" if o.action == "BUY" else "SLD", q, px,
                      datetime.now(NY))
        self._next_perm += 1
        self.execs.append(e)
        if o.status == "Filled" and o.oca_group:
            for other in self.orders.values():
                if (other is not o and other.oca_group == o.oca_group
                        and other.status in ("Submitted", "PreSubmitted")):
                    other.status = "Cancelled"
        return e
