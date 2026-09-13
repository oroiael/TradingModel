"""A broker double for the two jobs.

Models only what `schedule.py` calls, and models it the way the real adapter
behaves — in particular an order is NOT working until `refresh_orders` has been
called at least once, so the confirmation loop is exercised rather than trivially
satisfied.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class Q:
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0


@dataclass
class W:
    order_ref: str
    order_id: int
    symbol: str
    action: str
    order_type: str
    qty: float
    filled: float = 0.0
    status: str = "PreSubmitted"


@dataclass
class B:
    date: dt.date
    open: float
    close: float


class FakeBroker:
    def __init__(self, *, equity=140_000.0, positions=None, quotes=None,
                 sessions=None, ack_after=1, transmit=True):
        self.transmit = transmit
        self._equity = equity
        self._positions = dict(positions or {})
        self._quotes = dict(quotes or {})
        self._sessions = dict(sessions or {})
        self._working: list[W] = []
        self._pending: list[W] = []
        self._ack_after = ack_after          # refreshes before an order shows
        self._refreshes = 0
        self.placed: list[dict] = []
        self.waits = 0
        self._next_id = 1000

    # ---- reads
    def net_liquidation(self): return self._equity
    def position(self, symbol): return self._positions.get(symbol, 0.0)
    def quote(self, symbol): return self._quotes.get(symbol, Q())
    def working_orders(self, symbol):
        return [w for w in self._working if w.symbol == symbol]

    def historical_sessions(self, symbol, end, duration, bar_size="1 day"):
        return list(self._sessions.get(symbol, []))

    def refresh_orders(self):
        self._refreshes += 1
        if self._refreshes >= self._ack_after:
            self._working.extend(self._pending)
            self._pending = []

    def wait(self, seconds): self.waits += 1

    # ---- writes
    def _place(self, kind, symbol, action, qty, order_ref):
        oid = self._next_id
        self._next_id += 1
        self.placed.append(dict(kind=kind, symbol=symbol, action=action,
                                qty=qty, order_ref=order_ref, order_id=oid))
        if not self.transmit:
            return -oid                      # synthetic, as the real adapter does
        self._pending.append(W(order_ref, oid, symbol, action, kind, qty))
        return oid

    def place_moc(self, symbol, action, qty, order_ref):
        return self._place("MOC", symbol, action, qty, order_ref)

    def place_moo(self, symbol, action, qty, order_ref):
        return self._place("MOO", symbol, action, qty, order_ref)


def ramp(n, start=100.0, step=0.004, seed=7):
    """A deterministic price path with enough dispersion to produce an RV."""
    out, px, d = [], start, dt.date(2022, 1, 3)
    for k in range(n):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        px *= 1 + step * (((k * seed) % 11) - 5) / 5.0
        out.append(B(d, px, px))
        d += dt.timedelta(days=1)
    return out


def calm_then(n, calm=0.0005, seed=3):
    """A path whose recent volatility is LOW, so the instrument is eligible."""
    out, px, d = [], 100.0, dt.date(2022, 1, 3)
    for k in range(n):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        wig = 0.02 if k < n - 40 else calm          # noisy history, calm recently
        px *= 1 + wig * (((k * seed) % 11) - 5) / 5.0
        out.append(B(d, px, px))
        d += dt.timedelta(days=1)
    return out


def stormy_recently(n, seed=3):
    """A path whose RECENT volatility is the highest in its history.

    Guarantees the instrument is ineligible: today's RV sits above every prior
    observation, so it cannot be below their 60th percentile.
    """
    out, px, d = [], 100.0, dt.date(2022, 1, 3)
    for k in range(n):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        wig = 0.001 if k < n - 30 else 0.05          # calm history, storm now
        px *= 1 + wig * (((k * seed) % 11) - 5) / 5.0
        out.append(B(d, px, px))
        d += dt.timedelta(days=1)
    return out
