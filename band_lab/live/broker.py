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
    def assert_live_data(self) -> None: ...
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

    # ---------------------------------------------------------- lifecycle
    def connect(self) -> None:
        from ib_async import IB
        if self._ib is None:
            self._ib = IB()
        if self._ib.isConnected():
            return
        self._ib.connect(self.host, self.port, clientId=self.client_id,
                         timeout=30, readonly=self.readonly)
        self._on_event("info", f"connected {self.host}:{self.port} "
                               f"clientId={self.client_id}")

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

    def contract(self, symbol: str, sec_type: str = "STK"):
        """Qualify a contract. `sec_type` "CASH" builds an FX pair (EURUSD).

        FX is supported so the instrument screen can *measure* currency
        candidates rather than assert anything about them. Nothing on the
        trading path uses it — §11 permits no additional instruments.
        """
        key = (symbol, sec_type)
        if key in self._contracts:
            return self._contracts[key]
        ib = self._require()
        if sec_type == "CASH":
            from ib_async import Forex
            c = Forex(symbol)
        else:
            from ib_async import Stock
            c = Stock(symbol, self.exchange, "USD", primaryExchange=self.primary)
        q = ib.qualifyContracts(c)
        if not q:
            raise BrokerError(f"could not qualify {symbol} ({sec_type})")
        self._contracts[key] = q[0]
        return q[0]

    # ------------------------------------------------------------- guards
    def assert_live_data(self) -> None:
        """§2 — refuse to trade on delayed data.

        `reqMarketDataType(1)` requests live; IBKR silently downgrades to
        delayed when the subscription is missing, which is exactly the failure
        this guards. The engine calls this before every order-placing phase,
        not once at startup.
        """
        ib = self._require()
        ib.reqMarketDataType(MARKET_DATA_LIVE)
        ticker = getattr(ib, "_ccr_probe_ticker", None)
        if ticker is None:
            return
        mdt = getattr(ticker, "marketDataType", MARKET_DATA_LIVE)
        if mdt != MARKET_DATA_LIVE:
            raise NotLiveDataError(f"marketDataType={mdt}, refusing to trade")

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

    def _dated_bars(self, symbol, end, duration, bar_size, sec_type="STK"):
        """(date, Bar) pairs. Bars are clock-indexed like the CSVs — §2.1:
        index 0 is the 09:30 bar, addressed by clock time, not file position."""
        ib = self._require()
        bars = ib.reqHistoricalData(
            self.contract(symbol, sec_type),
            endDateTime=end.strftime("%Y%m%d %H:%M:%S US/Eastern") if end else "",
            durationStr=duration, barSizeSetting=bar_size,
            # FX has no consolidated trade tape; MIDPOINT is the only sane
            # analogue, and the difference is itself worth seeing in a screen.
            whatToShow="MIDPOINT" if sec_type == "CASH" else "TRADES",
            useRTH=True, formatDate=1, keepUpToDate=False)
        step = 5 if bar_size.startswith("5") else 1
        out = []
        for b in bars:
            dt = b.date if isinstance(b.date, datetime) else datetime.strptime(
                str(b.date), "%Y%m%d  %H:%M:%S")
            mins = dt.hour * 60 + dt.minute - (9 * 60 + 30)
            out.append((dt.date(), Bar(mins // step, float(b.open), float(b.high),
                                       float(b.low), float(b.close), float(b.volume))))
        return out

    def historical_bars(self, symbol, end, duration, bar_size="5 mins") -> list[Bar]:
        return [b for _, b in self._dated_bars(symbol, end, duration, bar_size)]

    def historical_sessions(self, symbol, end, duration,
                            bar_size="5 mins", sec_type="STK") -> list[tuple]:
        """Grouped by calendar date, oldest first — the shape FeatureHistory
        and the shadow-parity replay both consume."""
        grouped: dict = {}
        for day, bar in self._dated_bars(symbol, end, duration, bar_size, sec_type):
            grouped.setdefault(day, []).append(bar)
        return [(d, sorted(v, key=lambda b: b.idx)) for d, v in sorted(grouped.items())]

    # ------------------------------------------------------------ commands
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
        o = self._order(action, qty, order_ref, oca_group, transmit)
        o.orderType = "LMT"
        o.lmtPrice = round(float(limit_px), 2)
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def place_stop(self, symbol, action, qty, stop_px, order_ref,
                   oca_group="", transmit=True) -> int:
        ib = self._require()
        o = self._order(action, qty, order_ref, oca_group, transmit)
        o.orderType = "STP"
        # ASSUMPTION §6.1: a broker-side STP that survives an API disconnect.
        # §6.1 requires this; it is the most safety-critical unverified item.
        o.auxPrice = round(float(stop_px), 2)
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def place_market(self, symbol, action, qty, order_ref) -> int:
        ib = self._require()
        o = self._order(action, qty, order_ref, "", True)
        o.orderType = "MKT"          # §4.7 — MKT, not MOC
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def modify_limit(self, order_id: int, limit_px: float, qty: float) -> None:
        ib = self._require()
        for t in ib.openTrades():
            if t.order.orderId == order_id:
                t.order.lmtPrice = round(float(limit_px), 2)
                t.order.totalQuantity = qty
                ib.placeOrder(t.contract, t.order)   # same id = modify
                return
        raise BrokerError(f"order {order_id} not working; cannot modify")

    def cancel(self, order_id: int) -> None:
        ib = self._require()
        for t in ib.openTrades():
            if t.order.orderId == order_id:
                ib.cancelOrder(t.order)
                return

    def cancel_all(self) -> None:
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

    def assert_live_data(self) -> None:
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
        return [WorkingOrder(o.order_ref, o.order_id, self._next_perm, o.symbol,
                             o.action, o.order_type, o.qty, o.filled,
                             o.limit_px, o.aux_px, o.oca_group, o.status)
                for o in self.orders.values()
                if o.symbol == symbol and o.status in ("Submitted", "PreSubmitted")]

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
        o = self.orders.get(order_id)
        if o and o.status in ("Submitted", "PreSubmitted"):
            o.status = "Cancelled"

    def cancel_all(self) -> None:
        self.global_cancels += 1
        for o in self.orders.values():
            if o.status in ("Submitted", "PreSubmitted"):
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
