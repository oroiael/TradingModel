"""
Stage 2 — SQLite persistence (WAL).

Everything the engine does is written here before or as it happens, because
the 16:10 reconcile (Stage 6) and the daily shadow-parity report need to
replay a session exactly as it was decided, not as it is remembered.

Design note: this store is an **audit log, not the source of truth**.
`PHASE2_PLAN.md` §3 makes reconciliation from the broker the only way state is
ever established, so nothing here is ever read back to decide what the engine
should do next. That keeps the restart path and the normal path identical.

The one exception is `quotes`, which exists solely to answer the §1 question:
whether IBKR's paper simulator ever fills a resting limit without the quote
reaching it. Nothing reads it either; it is evidence for humans.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS bars (
    ts TEXT NOT NULL, symbol TEXT NOT NULL, session TEXT NOT NULL,
    bar_idx INTEGER NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    source TEXT NOT NULL DEFAULT 'feed',
    PRIMARY KEY (symbol, session, bar_idx, source)
);

CREATE TABLE IF NOT EXISTS decisions (
    ts TEXT NOT NULL, symbol TEXT NOT NULL, session TEXT NOT NULL,
    bar_idx INTEGER NOT NULL, kind TEXT NOT NULL,
    limit_px REAL, qty REAL, target_px REAL, stop_px REAL,
    anchor REAL, reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_decisions_session ON decisions(session, symbol);

CREATE TABLE IF NOT EXISTS orders (
    ts TEXT NOT NULL, symbol TEXT NOT NULL, session TEXT NOT NULL,
    order_ref TEXT NOT NULL, perm_id INTEGER, order_id INTEGER,
    role TEXT NOT NULL, action TEXT NOT NULL, order_type TEXT NOT NULL,
    qty REAL, limit_px REAL, aux_px REAL, oca_group TEXT,
    status TEXT, event TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_orders_ref ON orders(order_ref);
CREATE INDEX IF NOT EXISTS ix_orders_session ON orders(session, order_ref);

CREATE TABLE IF NOT EXISTS fills (
    ts TEXT NOT NULL, symbol TEXT NOT NULL, session TEXT NOT NULL,
    order_ref TEXT, exec_id TEXT NOT NULL UNIQUE, perm_id INTEGER,
    role TEXT, side TEXT, qty REAL, price REAL,
    bid REAL, ask REAL, last REAL, commission REAL
);

CREATE TABLE IF NOT EXISTS quotes (
    ts TEXT NOT NULL, symbol TEXT NOT NULL, session TEXT NOT NULL,
    context TEXT NOT NULL, bid REAL, ask REAL, last REAL,
    bid_size REAL, ask_size REAL
);

CREATE TABLE IF NOT EXISTS counters (
    session TEXT NOT NULL, symbol TEXT NOT NULL,
    fills INTEGER, stop_outs INTEGER, state TEXT, ts TEXT NOT NULL,
    PRIMARY KEY (session, symbol)
);

CREATE TABLE IF NOT EXISTS daily (
    session TEXT NOT NULL, symbol TEXT NOT NULL,
    gate_ok INTEGER, gate_reason TEXT, filter_ok INTEGER, filter_reason TEXT,
    atr5 REAL, or30 REAL, thr80 REAL, pos10 REAL,
    account_equity REAL, sleeve_capital REAL,
    fills INTEGER, stop_outs INTEGER, realised_pnl REAL, flat_at_close INTEGER,
    ts TEXT NOT NULL,
    PRIMARY KEY (session, symbol)
);

CREATE TABLE IF NOT EXISTS events (
    ts TEXT NOT NULL, level TEXT NOT NULL, source TEXT NOT NULL,
    session TEXT, symbol TEXT, message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Store:
    path: str

    def __post_init__(self) -> None:
        d = os.path.dirname(os.path.abspath(self.path))
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30.0,
                                    detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row
        with closing(self.conn.cursor()) as c:
            c.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------- writes
    def _ins(self, table: str, **kw) -> None:
        kw.setdefault("ts", _now())
        cols = ",".join(kw)
        marks = ",".join("?" * len(kw))
        with closing(self.conn.cursor()) as c:
            c.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})",
                      tuple(kw.values()))
        self.conn.commit()

    def bar(self, symbol, session, bar_idx, o, h, l, c_, v, source="feed") -> None:
        self._ins("bars", symbol=symbol, session=session, bar_idx=bar_idx,
                  open=o, high=h, low=l, close=c_, volume=v, source=source)

    def decision(self, symbol, session, bar_idx, kind, **kw) -> None:
        self._ins("decisions", symbol=symbol, session=session, bar_idx=bar_idx,
                  kind=kind, limit_px=kw.get("limit_px"), qty=kw.get("qty"),
                  target_px=kw.get("target_px"), stop_px=kw.get("stop_px"),
                  anchor=kw.get("anchor"), reason=kw.get("reason"))

    def order(self, symbol, session, order_ref, role, action, order_type,
              event, **kw) -> None:
        self._ins("orders", symbol=symbol, session=session, order_ref=order_ref,
                  role=role, action=action, order_type=order_type, event=event,
                  perm_id=kw.get("perm_id"), order_id=kw.get("order_id"),
                  qty=kw.get("qty"), limit_px=kw.get("limit_px"),
                  aux_px=kw.get("aux_px"), oca_group=kw.get("oca_group"),
                  status=kw.get("status"))

    def fill(self, symbol, session, exec_id, **kw) -> bool:
        """Idempotent on exec_id. Returns False if this execution was already
        recorded — the duplicate guard the reconnect path depends on."""
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT 1 FROM fills WHERE exec_id=?", (exec_id,))
            if c.fetchone():
                return False
        self._ins("fills", symbol=symbol, session=session, exec_id=exec_id,
                  order_ref=kw.get("order_ref"), perm_id=kw.get("perm_id"),
                  role=kw.get("role"), side=kw.get("side"), qty=kw.get("qty"),
                  price=kw.get("price"), bid=kw.get("bid"), ask=kw.get("ask"),
                  last=kw.get("last"), commission=kw.get("commission"))
        return True

    def quote(self, symbol, session, context, bid, ask, last,
              bid_size=None, ask_size=None) -> None:
        self._ins("quotes", symbol=symbol, session=session, context=context,
                  bid=bid, ask=ask, last=last, bid_size=bid_size, ask_size=ask_size)

    def counters(self, session, symbol, fills, stop_outs, state) -> None:
        self._ins("counters", session=session, symbol=symbol, fills=fills,
                  stop_outs=stop_outs, state=state)

    def daily(self, session, symbol, **kw) -> None:
        """Upsert — the daily row is written in three passes.

        06:00 writes the gate, 10:00 the filter, 16:10 the outcome. INSERT OR
        REPLACE would blank the earlier columns each time, silently losing the
        gate and filter reasons that the shadow-parity report needs.
        """
        kw = {k: v for k, v in kw.items() if v is not None}
        kw["ts"] = _now()
        cols = ["session", "symbol", *kw]
        vals = [session, symbol, *kw.values()]
        marks = ",".join("?" * len(cols))
        sets = ",".join(f"{c}=excluded.{c}" for c in kw)
        with closing(self.conn.cursor()) as c:
            c.execute(
                f"INSERT INTO daily ({','.join(cols)}) VALUES ({marks}) "
                f"ON CONFLICT(session, symbol) DO UPDATE SET {sets}",
                tuple(vals))
        self.conn.commit()

    def event(self, level, source, message, session=None, symbol=None) -> None:
        self._ins("events", level=level, source=source, message=message,
                  session=session, symbol=symbol)

    # -------------------------------------------------------------- reads
    def rows(self, sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with closing(self.conn.cursor()) as c:
            c.execute(sql, tuple(args))
            return c.fetchall()

    def session_bars(self, symbol: str, session: str) -> list[sqlite3.Row]:
        return self.rows("SELECT * FROM bars WHERE symbol=? AND session=? "
                         "AND source='feed' ORDER BY bar_idx", (symbol, session))

    def duplicate_order_refs(self, session: str) -> list[sqlite3.Row]:
        """Refs that identify more than one order id. Should always be empty.

        The `orders` table is an event log — placed, modified, cancelled all
        share a ref — so a UNIQUE constraint would be wrong. What must never
        happen is one ref covering two *different* orders: `reconcile` counts
        entries as a set of refs, so a collision silently under-counts §2.7's
        breaker, and the audit trail stops identifying anything.
        """
        return self.rows(
            "SELECT order_ref, COUNT(DISTINCT order_id) AS n "
            "FROM orders WHERE session=? AND order_id IS NOT NULL "
            "GROUP BY order_ref HAVING n > 1", (session,))

    def session_fills(self, symbol: str, session: str) -> list[sqlite3.Row]:
        return self.rows("SELECT * FROM fills WHERE symbol=? AND session=? "
                         "ORDER BY ts", (symbol, session))

    def close(self) -> None:
        self.conn.close()
