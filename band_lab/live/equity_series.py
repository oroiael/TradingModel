"""
The account equity path, session by session — the number every drawdown
figure in this project rests on.

Every percentage quoted about live performance so far has been measured
against a peak of 148,942 that was carried forward in conversation rather
than read from anywhere. `daily.account_equity` has been recorded since the
first session; nothing was reading it back. This does.

Drawdown is measured from the running peak, which is not necessarily the
starting equity — if the account rose before it fell, the two differ, and
"down 4.8%" and "down 0.9% since inception" can both be true. This prints
both so they stop being confusable.

    python band_lab/live/equity_series.py
    python band_lab/live/equity_series.py --db path/to/live.db
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from store import Store                                  # noqa: E402


def default_db() -> str:
    return os.path.join(_HERE, "out", "live.db")


def series(store: Store) -> list[tuple[str, float, float]]:
    """(session, account_equity, sleeve_capital), one row per session.

    `daily` carries a row per sleeve per session and both record the same
    account equity, so the sleeves are collapsed with MAX rather than summed —
    summing would double every figure.
    """
    rows = store.rows(
        "SELECT session, MAX(account_equity) AS eq, MAX(sleeve_capital) AS cap "
        "FROM daily WHERE account_equity IS NOT NULL "
        "GROUP BY session ORDER BY session")
    return [(r["session"], float(r["eq"]),
             float(r["cap"]) if r["cap"] is not None else float("nan"))
            for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description="live account equity path")
    ap.add_argument("--db", default=default_db())
    a = ap.parse_args()
    if not os.path.exists(a.db):
        print(f"No store at {a.db} — pass --db.")
        return 1

    rows = series(Store(a.db))
    if not rows:
        print("No sessions carry account_equity.")
        return 1

    start = rows[0][1]
    peak = start
    print(f"{'session':>10} {'equity':>12} {'chg':>10} {'vs start':>10} "
          f"{'vs peak':>10}  {'peak':>12}")
    print("-" * 70)
    prev = start
    worst, worst_at = 0.0, rows[0][0]
    for s, eq, _cap in rows:
        peak = max(peak, eq)
        dd = eq / peak - 1.0
        if dd < worst:
            worst, worst_at = dd, s
        print(f"{s:>10} {eq:>12,.0f} {eq - prev:>+10,.0f} "
              f"{eq / start - 1:>+10.2%} {dd:>+10.2%}  {peak:>12,.0f}")
        prev = eq

    last = rows[-1][1]
    print("-" * 70)
    print(f"  sessions recorded          {len(rows)}  "
          f"({rows[0][0]} -> {rows[-1][0]})")
    print(f"  starting equity            {start:>12,.0f}   <- the number that was missing")
    print(f"  peak equity                {peak:>12,.0f}")
    print(f"  latest equity              {last:>12,.0f}")
    print()
    print(f"  return since inception     {last / start - 1:>+11.2%}")
    print(f"  drawdown from peak         {last / peak - 1:>+11.2%}")
    print(f"  max drawdown in the record {worst:>+11.2%}  (at {worst_at})")
    print()
    print("  Note: the pre-open `equity=` line is read BEFORE that session "
          "trades, so\n  the last row does not yet include the most recent "
          "session's own P&L.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
