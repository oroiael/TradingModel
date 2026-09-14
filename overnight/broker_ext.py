"""MOC and MOO, which `band_lab/live/broker.py` does not place.

`IBBroker` is reused wholesale — its connect path, its account guards, its
order-state discipline and five live sessions of defect fixes are worth far more
than a fresh adapter. What it does not have is the two order types this strategy
is built on. `place_market` is explicitly "MKT, not MOC" (§4.7), and `_order`
hardcodes `tif = "DAY"`, which is right for a band_lab bracket and wrong for a
market-on-open.

So this subclasses rather than edits: band_lab's 232 tests keep passing and its
engine is untouched.

**Verified from the TWS API source committed in this repository**, not recalled:

    MOC   orderType = "MOC"
          `TWS API/samples/Python/Testbed/OrderSamples.py:100`
          `TWS API/source/JavaClient/com/ib/client/OrderType.java:25` lists
          MOC among the real types: MOC( Arrays.asList("MOC","MKT CLS","MKTCLS") )

    MOO   orderType = "MKT", tif = "OPG"
          `TWS API/samples/Python/Testbed/OrderSamples.py:117`

**Deadlines, from `IBKR Order types.md` and `NYSE Arca Auction.md`:**

    MOC   must reach NYSE markets by 15:50 ET, and after 15:50 can be neither
          cancelled nor reduced (`IBKR Order types.md:13-14`). Submission is a
          commitment.
    MOO   Arca rejects new MOO orders from 09:29:55 and cancels from 09:29
          (`NYSE Arca Auction.md`).

Routing: smart-routed MOC orders execute on the primary listing exchange
(`IBKR Order types.md:93`). SOXL and XLU are both Arca-listed, so both trade in
the Arca auctions — which is the fill the backtest assumes.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from typing import NamedTuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import bandlab                                                # noqa: E402

_broker_mod = bandlab.load("broker")
IBBroker = _broker_mod.IBBroker
bar_time_et = _broker_mod.bar_time_et

#: What `Order.tif` must be for a market-on-open. Not "DAY".
OPG = "OPG"

#: Which price series IBKR returns for the daily history.
#:
#: TRADES, to match the research. `SOXL_1min.csv` — the series the backtest and
#: therefore the p60 threshold were computed on — was fetched with
#: `whatToShow="TRADES"` (`ibkr_intraday_fetcher_2.py:121`,
#: `band_lab/live/fetch_1min.py:148`), and band_lab's own `_dated_bars`
#: hardcodes the same.
#:
#: ADJUSTED_LAST is not a formatting choice, it is a different series: it
#: back-adjusts the whole history for dividends and splits, which removes the
#: quarterly ex-dividend gaps from the close-to-close returns and lowers RV.
#: The threshold is a percentile of that history, so requesting the other basis
#: would move the cut and change which nights trade. `run.py --job enter
#: --rehearse-now` cross-checks the fetched closes against the research CSVs
#: for exactly this reason.
DAILY_WHAT_TO_SHOW = "TRADES"


class DailyBar(NamedTuple):
    """One daily bar. Deliberately not band_lab's `Bar`, which carries `idx`."""

    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


class QuoteDetail(NamedTuple):
    """A quote plus what is known about how much to trust it.

    band_lab's `Quote` carries prices only, which is right for an engine that
    crosses a spread every few minutes and would notice a bad one immediately.
    This strategy reads a quote ONCE a day, sizes an irreversible MOC from it,
    and does not look again — so the provenance matters as much as the number.
    """

    bid: float
    ask: float
    last: float
    #: Seconds since TWS last updated this quote, or None when it does not say.
    #: **Diagnostic only, and deliberately so.** ib_async is not installed in
    #: the environment this was written in, so which attribute carries the
    #: timestamp and in what type is UNVERIFIED — and band_lab already has a
    #: scar from a guard that refused on an inconclusive probe and cost a
    #: healthy session (`broker.py:assert_live_data`). It is logged so that a
    #: real run can settle it; nothing refuses on it.
    age_seconds: "float | None"
    #: 1 live, 2 frozen, 3 delayed, 4 delayed-frozen, 0 when TWS did not say.
    market_data_type: int

    @property
    def spread_pct(self) -> "float | None":
        """Relative spread, or None when the book is not two-sided."""
        if self.bid > 0 and self.ask > 0 and self.ask >= self.bid:
            mid = (self.bid + self.ask) / 2.0
            return (self.ask - self.bid) / mid if mid > 0 else None
        return None

    def describe(self) -> str:
        age = "unknown" if self.age_seconds is None else f"{self.age_seconds:.0f}s"
        kind = {1: "live", 2: "FROZEN", 3: "DELAYED",
                4: "DELAYED-FROZEN"}.get(self.market_data_type, "unstated")
        spread = self.spread_pct
        sp = "one-sided" if spread is None else f"{spread*100:.3f}%"
        return (f"bid {self.bid:.4f} ask {self.ask:.4f} last {self.last:.4f} "
                f"| spread {sp} | age {age} | {kind}")


class AuctionBroker(IBBroker):
    """`IBBroker` plus the two auction order types and a daily-bar history."""

    def daily_sessions(self, symbol: str, end, duration: str,
                       what: str = DAILY_WHAT_TO_SHOW) -> "list[DailyBar]":
        """Daily bars, oldest first. **Not** `IBBroker.historical_sessions`.

        band_lab refuses a `1 day` bar size, and is right to: its `Bar.idx` is a
        fixed-width clock offset from 09:30, so a size with no minute grid would
        silently mis-index every bar (`broker.py:853-861`, guarding a real
        defect where `startswith("5")` gave "15 mins" a 1-minute grid). A daily
        bar has no intraday position at all, so it needs a different return
        type, not a wider lookup table — hence this method instead of an edit
        that would weaken a guard five live sessions paid for.

        Everything else mirrors the request that produced the research data:
        `useRTH=True`, `formatDate=1`, `keepUpToDate=False`
        (`soxl_ibkr_historical_3yr.py:63-73`).
        """
        ib = self._require()
        bars = ib.reqHistoricalData(
            self.contract(symbol),
            endDateTime=self._end_stamp(end),
            durationStr=duration, barSizeSetting="1 day", whatToShow=what,
            useRTH=True, formatDate=1, keepUpToDate=False)

        if not bars and end is not None:
            # OPEN QUESTION, not verified: whether IBKR accepts an endDateTime
            # that falls outside trading hours — a Sunday-evening pre-flight, in
            # particular. An empty result is the shape a rejection would take,
            # and "" means "up to the present moment", which is what the
            # repository's own proven daily fetcher passes. Callers slice to
            # dates strictly before the decision day either way, so this cannot
            # widen what the decision sees.
            self._event("warn", f"{symbol}: no daily bars for endDateTime "
                                f"{self._end_stamp(end)!r}; retrying open-ended")
            bars = ib.reqHistoricalData(
                self.contract(symbol), endDateTime="",
                durationStr=duration, barSizeSetting="1 day", whatToShow=what,
                useRTH=True, formatDate=1, keepUpToDate=False)

        out = [DailyBar(bar_time_et(b.date).date(), float(b.open), float(b.high),
                        float(b.low), float(b.close), float(b.volume))
               for b in bars]
        out.sort(key=lambda b: b.date)
        return out

    def quote_detail(self, symbol: str) -> QuoteDetail:
        """`quote()` plus the provenance needed to decide whether to size on it.

        Every attribute below is read with `getattr` and a fallback. ib_async's
        exact spelling for a tick timestamp is UNVERIFIED here — the package is
        not installed in the environment this was written in — and the official
        tick types list both `LAST_TIMESTAMP` (45) and `DELAYED_LAST_TIMESTAMP`
        (`TWS API/source/pythonclient/ibapi/ticktype.py:56,99`), so more than one
        spelling is plausible. Missing means unknown, and unknown never refuses.
        """
        t = self._ticker(symbol)
        q = self.quote(symbol)
        return QuoteDetail(q.bid, q.ask, q.last,
                           self._quote_age(t),
                           int(getattr(t, "marketDataType", 0) or 0))

    @staticmethod
    def _quote_age(ticker) -> "float | None":
        """Seconds since the quote was last updated, or None if TWS did not say."""
        now = dt.datetime.now(dt.timezone.utc)
        for attr in ("lastTimestamp", "time", "rtTime"):
            raw = getattr(ticker, attr, None)
            if raw is None:
                continue
            try:
                if isinstance(raw, dt.datetime):
                    when = raw if raw.tzinfo else raw.replace(
                        tzinfo=dt.timezone.utc)
                elif isinstance(raw, (int, float)) and raw > 0:
                    # epoch seconds, or milliseconds for rtTime
                    secs = raw / 1000.0 if raw > 1e11 else float(raw)
                    when = dt.datetime.fromtimestamp(secs, dt.timezone.utc)
                else:
                    continue
                return max((now - when).total_seconds(), 0.0)
            except (ValueError, OverflowError, OSError):
                continue
        return None

    @staticmethod
    def _end_stamp(end) -> str:
        """band_lab's proven `endDateTime` spelling (`broker.py:850`)."""
        return end.strftime("%Y%m%d %H:%M:%S US/Eastern") if end else ""

    def _event(self, level: str, msg: str) -> None:
        """`IBBroker.__init__` stores the callback as `_on_event` (broker.py:449)."""
        cb = getattr(self, "_on_event", None)
        if callable(cb):
            cb(level, msg)
        print(f"  [{level}] {msg}", flush=True)

    def place_moc(self, symbol: str, action: str, qty: float,
                  order_ref: str) -> int:
        """Market-on-close. Fills at the official closing auction print.

        No limit price: the whole point is to take the auction price rather than
        cross a spread. `transmit=True` always — an untransmitted MOC is not a
        resting order, it is nothing, and there is no second chance after 15:50.
        """
        ib = self._require()
        if self.dry_run:
            return self._dry(f"{action} MOC {qty} {symbol} ({order_ref})")
        o = self._order(action, qty, order_ref, "", True)
        o.orderType = "MOC"
        return ib.placeOrder(self.contract(symbol), o).order.orderId

    def place_moo(self, symbol: str, action: str, qty: float,
                  order_ref: str) -> int:
        """Market-on-open: a MKT order with the OPG time in force.

        `_order` sets `tif = "DAY"`, which would make this an ordinary market
        order firing at 09:30 into whatever the book looks like — the 09:30
        one-minute bar ranges 31 bp on XLU. OPG is what routes it to the auction
        instead, so the override is the entire point of this method.
        """
        ib = self._require()
        if self.dry_run:
            return self._dry(f"{action} MOO {qty} {symbol} ({order_ref})")
        o = self._order(action, qty, order_ref, "", True)
        o.orderType = "MKT"
        o.tif = OPG
        return ib.placeOrder(self.contract(symbol), o).order.orderId
