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

#: `ib_async.Wrapper.error`'s own warning set, transcribed from the installed
#: package and asserted against it by `test_the_warning_set_matches_ib_async`.
#:
#: The distinction is the whole reason this matters. A code **in** here leaves
#: the order working and sets `ValidationError`, which is an ActiveState.
#: Anything **outside** it makes `wrapper.error` set the trade `Cancelled` — a
#: DoneState — so `openTrades()` drops it even when IBKR is still working the
#: order. ib_async's own comment on that line: *"modification to existing order
#: just has an update error, but the order is STILL LIVE"*.
IB_WARNING_CODES = frozenset({105, 110, 165, 321, 329, 399, 404, 434, 492, 10167})

#: Connection-status notices TWS emits constantly ("market data farm connection
#: is OK"). They are in the 2100-2199 warning band but say nothing about this
#: engine, so they are not worth a line each. Same list `diagnose.py` filters.
IB_STATUS_CHATTER = frozenset({2104, 2106, 2107, 2119, 2158})


def is_warning(code: int) -> bool:
    """Would `ib_async` leave the order working after this code?"""
    return code in IB_WARNING_CODES or 2100 <= code < 2200

#: How long to wait for TWS to describe the feed before warning and proceeding.
PROBE_SECONDS = 5.0

#: How long a *new* market-data subscription may take to produce its first
#: quote. Paid once per symbol per connection, not once per read — see `quote`.
QUOTE_WARMUP_SECONDS = 2.0


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

    def refresh_orders(self) -> None:
        """Re-read the open orders from TWS itself, not from the client's copy.

        The client's copy can be wrong in the one direction that matters.
        `ib_async.Wrapper.error` marks a trade `Cancelled` — a DoneState — for
        every error code outside its warning set, and its own comment says why
        that is not always true: *"modification to existing order just has an
        update error, but the order is STILL LIVE"*. `openTrades()` then drops
        it, so `working_orders`, `_clear_working`, `verify_flat` and the
        watchdog's `exposure()` all report a clean book while IBKR holds a live
        order. That is the shape of 2026-08-10.

        `IB.reqAllOpenOrders` is the documented way back. IBKR's own client:
        *"request the open orders placed from all clients and also from TWS.
        Each open order will be fed back through the openOrder() and
        orderStatus() functions"* — and `orderStatus` overwrites the local
        status with whatever TWS reports, which is exactly what revives a trade
        the client wrongly buried.

        Note from the same docstring: *"No association is made between the
        returned orders and the requesting client."* So this can also surface
        orders placed by hand in TWS or by the watchdog. Callers must keep
        filtering on `orderRef`, which is what `parse_ref` is for.

        Default is a no-op: nothing to re-read without a real TWS.
        """

    def wait(self, seconds: float) -> None:
        """Pause **without going deaf**. Never call `time.sleep` on this path.

        `ib_async` is single-threaded asyncio with no background reader — the
        package contains no `threading` import at all. The socket is drained
        only while the event loop runs, and `IB.positions()`, `openTrades()`,
        `fills()` and `accountValues()` are plain reads of the dictionaries that
        loop fills in. `util.sleep`'s own docstring says it outright: *"Wait for
        the given amount of seconds while everything still keeps processing in
        the background. Never use time.sleep()."*

        This is load-bearing, not tidiness. Three loops wait for a change they
        can only learn about from the socket:

        * `ensure_flat` places a market order, waits, then re-reads `position()`;
        * `_clear_working` polls `working_orders()` for a cancel to confirm;
        * `watchdog.check` polls `exposure()` for the position it exists to close.

        Under `time.sleep` none of them can ever observe what they are waiting
        for, because nothing pumps the loop in between. That is consistent with
        the 2026-08-06 and 2026-08-10 sessions, where the position read
        unchanged on every attempt and the failure was put down to fill latency.

        The default here is `time.sleep`, which is right for `FakeIB` (no loop
        to pump) and for any caller with no live connection. `IBBroker`
        overrides it.
        """
        time.sleep(seconds)


# --------------------------------------------------------------------------
class IBBroker(Broker):
    """ib_async implementation. Imported lazily so tests never need ib_async."""

    def __init__(self, host="127.0.0.1", port=7497, client_id=11,
                 exchange="SMART", primary="ARCA", dry_run=False,
                 on_event: Optional[Callable[[str, str], None]] = None) -> None:
        self.host, self.port, self.client_id = host, port, client_id
        self.exchange, self.primary = exchange, primary
        #: Refuse to transmit. Named for what it does, because the old name —
        #: `readonly`, borrowed from ib_async — is precisely what led three
        #: documents to promise that a dry run reached the market with nothing
        #: while every order went through (§4.1). ib_async's flag of that name
        #: is unrelated: it skips two startup requests and stops no order.
        self.dry_run = dry_run
        self._on_event = on_event or (lambda level, msg: None)
        self._ib = None
        self._contracts: dict[str, Any] = {}
        self._dry_seq = 0
        self._no_live_data: set = set()
        self._error_hooked = False
        #: One live market-data subscription per symbol. See `_ticker`.
        self._tickers: dict[str, Any] = {}

    # ---------------------------------------------------------- lifecycle
    def connect(self) -> None:
        from ib_async import IB
        if self._ib is None:
            self._ib = IB()
        if self._ib.isConnected():
            return
        self._ib.connect(self.host, self.port, clientId=self.client_id,
                         # Always a full client, dry run or not. ib_async's
                         # `readonly` skips `reqOpenOrders` and
                         # `reqCompletedOrders` at startup and does not stop
                         # `placeOrder`, so passing it bought nothing but an
                         # `openTrades()` the live path fills and the dry run
                         # leaves empty. Every guard that matters now reads
                         # `openTrades()`: reconcile on startup, the duplicate
                         # -entry check before arming, the dormant cancel. A
                         # rehearsal that skips them rehearses a different
                         # engine.
                         timeout=30, readonly=False)
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
        symbol = getattr(contract, "symbol", None) or "*"

        # Everything IBKR says, not only the market-data codes. Until now every
        # other code was dropped here, so when `Error 103` arrived on
        # 2026-08-10 — and `ib_async` marked the trade Cancelled while IBKR went
        # on to fill 1,703 shares — this engine's own record said nothing at
        # all. The session had to be reconstructed from TWS's log afterwards,
        # and the cause was then inferred rather than read.
        if errorCode not in IB_STATUS_CHATTER:
            if is_warning(errorCode):
                self._on_event("warn", f"IBKR {errorCode} req={reqId} {symbol}: "
                                       f"{errorString}")
            else:
                self._on_event(
                    "error",
                    f"IBKR {errorCode} req={reqId} {symbol}: {errorString} "
                    f"— not in ib_async's warning set, so it has marked this "
                    f"trade Cancelled locally. The order may still be live at "
                    f"IBKR; reconcile before believing it is gone.")

        if errorCode not in NO_LIVE_DATA_ERRORS:
            return
        self._no_live_data.add(symbol)

    def disconnect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            # Release the streaming subscriptions rather than leaving them for
            # TWS to reap. The reconnect path re-creates them on first read.
            for symbol in list(self._tickers):
                try:
                    self._ib.cancelMktData(self.contract(symbol))
                except Exception:                 # noqa: BLE001
                    pass                          # never block a disconnect
            self._ib.disconnect()
        self._tickers.clear()

    @property
    def connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    def _require(self):
        if not self.connected:
            raise BrokerError("not connected")
        return self._ib

    def wait(self, seconds: float) -> None:
        """`IB.sleep` — runs the event loop, so callbacks land while we wait.

        Deliberately does **not** go through `_require`. A pause must work while
        disconnected too: `run_session` sleeps between polls whether or not the
        last reconnect succeeded, and raising there would turn a recoverable
        outage into a dead session loop.
        """
        ib = self._ib
        if ib is None:
            time.sleep(seconds)
            return
        try:
            ib.sleep(seconds)
        except Exception:                                     # noqa: BLE001
            # A pause must never be what fails a flatten. The fallback still
            # waits the full interval — it just waits deaf, which is no worse
            # than the behaviour this method replaces.
            time.sleep(seconds)

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
            # `cancelMktData` is looked up by *contract*, so it cancels whatever
            # subscription this symbol currently has — including the streaming
            # one `_ticker` holds. Forget it, or `quote` would go on reading a
            # Ticker that TWS has stopped updating and report a frozen book as
            # a live one.
            self._tickers.pop(symbol, None)

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

    def _ticker(self, symbol: str):
        """One streaming subscription per symbol, held for the connection.

        `IB.reqMktData` takes a **new reqId from `getReqId()` on every call**
        and `wrapper.startTicker` overwrites `ticker2ReqId[tickType][ticker]`
        with it. The `Ticker` object is reused, so the data still arrives and
        nothing looks wrong — but the previous reqId is orphaned at TWS, and
        `cancelMktData` can only ever cancel the newest. Calling it per read
        therefore leaks a market-data line per read, against a concurrent-line
        limit that is typically 100.

        `_record_fill` reads a quote on **every execution** — §1's evidence for
        whether IBKR's simulator fills a resting limit without the quote
        reaching it — and IBKR settles one order in as many executions as the
        book requires. Eleven executions was eleven orphaned lines.
        """
        t = self._tickers.get(symbol)
        if t is not None:
            return t
        ib = self._require()
        t = ib.reqMktData(self.contract(symbol), "", False, False)
        self._tickers[symbol] = t
        # A fresh subscription is empty. Wait here, once, rather than on every
        # read: the old code slept 0.4s per call, which an eleven-execution
        # entry paid eleven times — 4.4 seconds, some of it out of the 15:55
        # flatten's budget.
        deadline = time.time() + QUOTE_WARMUP_SECONDS
        while time.time() < deadline and not _has_quote(t):
            ib.sleep(0.05)
        return t

    def quote(self, symbol: str) -> Quote:
        t = self._ticker(symbol)
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
            # VERIFIED 2026-08-11, no longer §6.3's assumption. IBKR's own
            # client says so in the field's declaration — `ibapi/order.py:51`:
            #   ocaType = 0  # 1 = CANCEL_WITH_BLOCK, 2 = REDUCE_WITH_BLOCK,
            #                #                        3 = REDUCE_NON_BLOCK
            # The default of 0 is why it has to be set at all. What is still
            # unverified is the behaviour under a *partial* fill, which the
            # committed documentation does not cover.
            o.ocaType = 1
        return o

    def place_limit(self, symbol, action, qty, limit_px, order_ref,
                    oca_group="", transmit=True) -> int:
        ib = self._require()
        px = round(float(limit_px), 2)
        if self.dry_run:
            return self._dry(f"{action} LMT {qty} {symbol} @ {px} ({order_ref})")
        o = self._order(action, qty, order_ref, oca_group, transmit)
        o.orderType = "LMT"
        o.lmtPrice = px
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def place_stop(self, symbol, action, qty, stop_px, order_ref,
                   oca_group="", transmit=True) -> int:
        ib = self._require()
        px = round(float(stop_px), 2)
        if self.dry_run:
            return self._dry(f"{action} STP {qty} {symbol} @ {px} ({order_ref})")
        o = self._order(action, qty, order_ref, oca_group, transmit)
        o.orderType = "STP"
        # ASSUMPTION §6.1: a broker-side STP that survives an API disconnect.
        # §6.1 requires this; it is the most safety-critical unverified item.
        o.auxPrice = px
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def place_market(self, symbol, action, qty, order_ref) -> int:
        ib = self._require()
        if self.dry_run:
            return self._dry(f"{action} MKT {qty} {symbol} ({order_ref})")
        o = self._order(action, qty, order_ref, "", True)
        o.orderType = "MKT"          # §4.7 — MKT, not MOC
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def modify_limit(self, order_id: int, limit_px: float, qty: float) -> None:
        ib = self._require()
        if self.dry_run or order_id < 0:
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
        if self.dry_run or order_id < 0:
            return
        for t in ib.openTrades():
            if t.order.orderId == order_id:
                ib.cancelOrder(t.order)
                return
        # Silence here made "cancelled" and "never found" the same outcome to
        # every caller. `_cancel_entry` then set `entry_id = None` and moved on,
        # which is right when the order is done and wrong when the client has
        # merely lost sight of it.
        self._on_event("warn",
                       f"cancel({order_id}): no working order with that id. "
                       f"Either it is already done, or the client marked it "
                       f"Cancelled on an error while IBKR still holds it — "
                       f"reconcile calls reqAllOpenOrders for exactly that case")

    def refresh_orders(self) -> None:
        """`reqAllOpenOrders` — synchronous, and it pumps the event loop."""
        self._require().reqAllOpenOrders()

    def cancel_all(self) -> None:
        if self.dry_run:
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
        #: Order ids TWS still holds that the *client* has wrongly buried — the
        #: state a non-warning error such as 103 leaves behind, where
        #: `wrapper.error` sets the trade `Cancelled` while it is still live
        #: upstream. Hidden from `working_orders` until `refresh_orders()`
        #: re-reads them, which is what `reqAllOpenOrders` does. Without this
        #: the ghost could not be expressed in a test at all — the same gap
        #: that let `PendingCancel` go unmodelled until it cost a session.
        self.ghosts: set = set()
        self.refreshes = 0

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
                if o.symbol == symbol and self._client_sees(o)]

    def refresh_orders(self) -> None:
        """TWS re-reports what it holds, and the client's copy is corrected."""
        self.refreshes += 1
        self.ghosts.clear()

    def hide(self, order_id: int) -> None:
        """Test control: the client loses sight of a still-live order."""
        self.ghosts.add(order_id)

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

    def _client_sees(self, o: _FakeOrder) -> bool:
        """Would `IB.openTrades()` return this order?

        `IBBroker` asks that question exactly once, through `openTrades()`, and
        every path it has — `working_orders`, `modify_limit`, `cancel` — is
        downstream of it. So the double asks it once too. Hand-writing the
        answer per method is what let `FakeIB` diverge before, and the skill is
        blunt about it: never write a status list.
        """
        return is_working(o.status) and o.order_id not in self.ghosts

    def modify_limit(self, order_id, limit_px, qty) -> None:
        # `IBBroker` scans `openTrades()` and raises `BrokerError` when the id
        # is not there. It does **not** care which working state the order is
        # in: `IB.placeOrder`-as-modify asserts only that the status is not a
        # DoneState, so a `PendingCancel` or `ValidationError` order is modified
        # without complaint. This used to accept `Submitted`/`PreSubmitted`
        # only, and to raise `KeyError` rather than `BrokerError` on an unknown
        # id — so the engine's behaviour against four reachable states was
        # untestable, and its behaviour against a missing one was tested
        # against the wrong exception.
        o = self.orders.get(order_id)
        if o is None or not self._client_sees(o):
            raise BrokerError(f"order {order_id} not working; cannot modify")
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
        if o is None or not self._client_sees(o):
            # `IBBroker.cancel` scans `openTrades()` and warns when the id is
            # not there — a ghost included, which is the whole point of one.
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
                        and is_working(other.status)):
                    # Every working sibling, not just the two states someone
                    # happened to list — `ocaType=1` is CANCEL_WITH_BLOCK and
                    # `PendingSubmit`, `ValidationError` and the rest are all
                    # orders IBKR still has. Set directly rather than through
                    # `cancel()`: this is the broker acting, so it lands as
                    # `Cancelled` and never passes through the client-side
                    # `PendingCancel` limbo that `IB.cancelOrder` creates.
                    other.status = "Cancelled"
        return e
