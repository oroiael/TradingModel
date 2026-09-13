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

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import bandlab                                                # noqa: E402

IBBroker = bandlab.load("broker").IBBroker

#: What `Order.tif` must be for a market-on-open. Not "DAY".
OPG = "OPG"


class AuctionBroker(IBBroker):
    """`IBBroker` plus the two auction order types."""

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
