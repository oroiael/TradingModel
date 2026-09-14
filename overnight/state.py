"""What the enter job leaves for the exit job, and the ledger.

**State is a record, never an authority.** The exit job sizes its sell from
`broker.position()`, not from this file. That is not belt-and-braces, it is the
rule band_lab learned the hard way: defect 3 sized a protective order from an
execution instead of from the position and left 241 of 541 shares unprotected.
If this file is lost, corrupted, or stale, the exit must still sell exactly what
the account holds.

So what is it for? Reporting, reconciliation and the audit trail — knowing what
the engine *intended*, so a difference from what the broker *did* is visible
rather than silent.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Intent:
    """What the enter job decided and sent, for the morning to compare against."""

    decision_date: str
    leg: str
    multiple: float
    shares: int
    order_id: int
    order_ref: str
    equity_at_entry: float
    reference_price: float
    primary_rv: Optional[float] = None
    primary_threshold: Optional[float] = None
    cover_rv: Optional[float] = None
    cover_threshold: Optional[float] = None
    submitted_at: str = ""
    transmitted: bool = False
    #: Filled in by the `confirm` job after the 16:00 auction. The entry fill
    #: CANNOT be read the next morning: `IBBroker.executions` reads
    #: `ib.fills()`, which is the current session only, so yesterday's MOC print
    #: is gone by the time the exit job connects. It has to be captured the same
    #: evening or it is lost.
    filled_shares: int = 0
    fill_price: float = 0.0
    confirmed_at: str = ""

    @property
    def entry_confirmed(self) -> bool:
        return self.filled_shares > 0 and self.fill_price > 0

    @property
    def is_flat(self) -> bool:
        return self.leg == "FLAT" or self.shares == 0

    @property
    def is_actionable(self) -> bool:
        """Did this intent put a real order into the market?

        A rehearsal writes an intent too — it computes the same decision and
        sizes the same order, it just never sends it. That file then sits in
        `out/` until the next run overwrites it, and the morning's jobs read it
        as though the position were real: `exit` warns that the account does not
        hold what state says, and `report` exits non-zero looking for a fill
        that was never going to exist.

        Nothing traded wrong — `exit` sizes from `broker.position()` and the
        watchdog reads the broker — but a scheduled system that cries wolf every
        time someone rehearses is a system whose alarms get ignored. So an
        untransmitted intent is treated as no intent at all.
        """
        return not self.is_flat and self.transmitted


def write_intent(path: str, intent: Intent) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(asdict(intent), fh, indent=2)
    os.replace(tmp, path)          # atomic: a crash mid-write cannot truncate it


def read_intent(path: str) -> Optional[Intent]:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            return Intent(**json.load(fh))
    except Exception:              # noqa: BLE001 — a bad state file must not
        return None                # stop the exit job; the position is truth


#: `shares` is what actually traded. `intended_shares` and `multiple_actual`
#: are here because the first live night filled 629 of 1,390 — an MOC is not
#: guaranteed to fill in full, and a row that records only the intent would
#: make a 0.45x night look like a 1.00x one.
LEDGER_COLUMNS = [
    "decision_date", "leg", "shares", "intended_shares", "fill_rate_pct",
    "multiple_intended", "multiple_actual",
    "entry_price", "exit_price",
    "gross_pct", "cost_pct", "net_pct", "pnl_dollars",
    "equity_before", "equity_after", "peak_equity", "drawdown_pct",
    "primary_rv", "primary_threshold", "cover_rv", "cover_threshold",
    "hold_days", "note",
]


def append_ledger(path: str, row: dict) -> None:
    """One row per completed trade, from inception. The running total lives here.

    Shaped to diff against the backtest ledger row for row — that comparison is
    the entire reason to run on paper.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS, lineterminator="\n",
                           extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


def read_ledger(path: str) -> "list[dict]":
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def running_totals(path: str, starting_equity: float) -> dict:
    """Inception-to-date, derived from the ledger alone."""
    rows = read_ledger(path)
    if not rows:
        return dict(trades=0, wins=0, win_rate=0.0, total_pct=0.0,
                    equity=starting_equity, peak=starting_equity, drawdown_pct=0.0)
    eq = starting_equity
    peak = starting_equity
    worst = 0.0
    wins = 0
    for r in rows:
        net = float(r["net_pct"]) / 100.0
        eq *= (1 + net)
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1)
        if net > 0:
            wins += 1
    return dict(trades=len(rows), wins=wins, win_rate=wins / len(rows) * 100.0,
                total_pct=(eq / starting_equity - 1) * 100.0,
                equity=eq, peak=peak, drawdown_pct=worst * 100.0)
