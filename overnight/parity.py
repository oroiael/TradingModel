"""P0's gate: does the live core reproduce the research ledger, exactly?

`retreat_lab/final_config.py` produced `out/proposed_ledger.csv` — the 895
decisions the backtested numbers in `STRATEGY.md` §4.2 are computed from. This
drives `core.py` and `features.py` over the same history and diffs the result
row for row.

**Exact means exact.** Not "close", not "within a basis point": the same leg on
every day and the same return to the ledger's four decimal places. The research
code and the live code are two independent expressions of one specification, and
the only useful evidence that the specification is unambiguous is that they
agree to the last digit. band_lab's Phase 1 gate is the same idea and caught
real defects.

Exits 0 on agreement, 1 on any disagreement, and prints the first rows that
differ.

    python3 overnight/parity.py
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from constants import (                                       # noqa: E402
    COVER_COST_BPS,
    FLAT,
    PRIMARY_COST_BPS,
    PRIMARY_SYMBOL,
)
import core                                                   # noqa: E402
import features                                               # noqa: E402

ROOT = os.path.dirname(_HERE)
PRIMARY_BARS = os.path.join(ROOT, "SOXL_1min.csv")
COVER_BARS = os.path.join(ROOT, "retreat_lab/out/XLU_daily_ibkr.csv")
LEDGER = os.path.join(ROOT, "retreat_lab/out/proposed_ledger.csv")
START_YEAR = 2023


def replay(start_year: int = START_YEAR) -> "list[dict]":
    """Every decision the strategy would have made, in ledger shape."""
    primary = features.build(features.load_sessions(PRIMARY_BARS))
    cover = features.build(features.load_sessions(COVER_BARS))

    rows = []
    for day in sorted(primary):
        if day.year < start_year or day not in cover:
            continue
        p, c = primary[day], cover[day]
        sp, sc = core.signals(p.rv, p.threshold, c.rv, c.threshold)
        decision = core.decide(sp, sc)

        if decision.leg == PRIMARY_SYMBOL:
            overnight, cost = p.overnight_return, PRIMARY_COST_BPS
        elif decision.leg == FLAT:
            overnight, cost = 0.0, 0.0
        else:
            overnight, cost = c.overnight_return, COVER_COST_BPS

        rows.append(dict(
            decision_date=day,
            leg=decision.leg,
            # The hold window is the PRIMARY instrument's calendar in both legs.
            # SOXL and XLU are both NYSE Arca-listed and share a session
            # calendar, so this is the same set of dates either way; taking it
            # from one instrument keeps a single clock in the ledger.
            hold_to=p.next_date,
            calendar_days=p.calendar_days,
            net=core.net_on_equity(overnight, decision.multiple, cost),
            decision=decision,
        ))
    return rows


def load_ledger() -> "list[dict]":
    with open(LEDGER) as fh:
        return [dict(decision_date=dt.date.fromisoformat(r["decision_date"]),
                     leg=r["leg"],
                     hold_to=dt.date.fromisoformat(r["hold_to"]),
                     calendar_days=int(r["calendar_days"]),
                     return_pct=float(r["return_pct"]))
                for r in csv.DictReader(fh)]


def main() -> int:
    mine = replay()
    theirs = load_ledger()
    print(f"live core : {len(mine)} decisions")
    print(f"research  : {len(theirs)} decisions  ({os.path.relpath(LEDGER, ROOT)})")

    failures: list[str] = []
    if len(mine) != len(theirs):
        failures.append(f"row count {len(mine)} != {len(theirs)}")

    for a, b in zip(mine, theirs):
        where = f"{a['decision_date']}"
        if a["decision_date"] != b["decision_date"]:
            failures.append(f"{where}: date != {b['decision_date']}"); continue
        if a["leg"] != b["leg"]:
            failures.append(f"{where}: leg {a['leg']} != {b['leg']}")
        if a["hold_to"] != b["hold_to"]:
            failures.append(f"{where}: hold_to {a['hold_to']} != {b['hold_to']}")
        if a["calendar_days"] != b["calendar_days"]:
            failures.append(f"{where}: days {a['calendar_days']} != {b['calendar_days']}")
        # the ledger stores percent rounded to 4dp; match it at its own precision
        if round(a["net"] * 100, 4) != b["return_pct"]:
            failures.append(f"{where}: return {round(a['net']*100,4):+.4f} "
                            f"!= {b['return_pct']:+.4f}")

    counts: dict[str, int] = {}
    for r in mine:
        counts[r["leg"]] = counts.get(r["leg"], 0) + 1
    print(f"legs      : " + "  ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    if failures:
        print(f"\nFAILURES: {len(failures)}")
        for f in failures[:20]:
            print(f"  {f}")
        if len(failures) > 20:
            print(f"  ... and {len(failures)-20} more")
        return 1

    print("\nPARITY: exact — every leg and every return to 4 decimal places.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
