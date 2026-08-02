"""
Weekend pre-flight — everything that can be checked against TWS with the
market closed.

Run this before the Stage 4 dry run (DEPLOYMENT.md §12.1). It exercises the
three broker calls the pre-open job depends on, and answers the one question
still open from the 1-minute study: **does IBKR's 5-minute history reproduce
the research record?** `thr80` is a percentile over 504 prior sessions, so if
the live feed and the CSV backbone disagree, the filter threshold drifts
across the seam and the live system stops matching the validated series.

Live market data is deliberately *expected* to fail outside RTH — that check
belongs to Monday.

    python band_lab/live/preflight.py                 # TWS paper on 7497
    python band_lab/live/preflight.py --port 4002     # IB Gateway paper
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
ROOT = os.path.dirname(_BAND_LAB)
for _p in (_HERE, os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

NY = ZoneInfo("America/New_York")


def main() -> int:
    from broker import IBBroker, NotLiveDataError
    from replay import load_sessions

    ap = argparse.ArgumentParser(description="weekend pre-flight against TWS")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497)
    ap.add_argument("--client-id", type=int, default=98)
    ap.add_argument("--symbols", default="SOXL,SOXS")
    ap.add_argument("--duration", default="30 D")
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    # readonly: a pre-flight must be structurally incapable of sending an order
    broker = IBBroker(host=args.host, port=args.port, client_id=args.client_id,
                      readonly=True)
    failures = []

    print(f"connecting to {args.host}:{args.port} ...")
    broker.connect()
    try:
        print(f"  connected={broker.connected()}  "
              f"NetLiquidation=${broker.net_liquidation():,.2f}")
        cap = min(broker.net_liquidation(), 150_000.0)
        print(f"  capital basis ${cap:,.0f} -> ${cap * 0.5:,.0f} per sleeve")

        # --- 1. contract + session hours -------------------------------
        print("\n[1] contract details and session hours")
        probe = datetime.now(NY) + timedelta(days=1)
        for sym in symbols:
            c = broker.contract(sym)
            print(f"  {sym}: conId={c.conId} exch={c.exchange} "
                  f"primary={c.primaryExchange}")
            for ahead in range(0, 5):        # find the next trading day
                day = probe + timedelta(days=ahead)
                try:
                    h = broker.session_hours(sym, day)
                except Exception:            # holiday/weekend -> try the next
                    continue
                print(f"       next session {h.open:%Y-%m-%d %H:%M} → "
                      f"{h.close:%H:%M} half_day={h.is_half_day}")
                break
            else:
                failures.append(f"{sym}: no session hours in the next 5 days")
                print("       NO SESSION HOURS FOUND in the next 5 days")

        # --- 2. historical bars vs the CSV backbone --------------------
        print(f"\n[2] historical 5-min bars ({args.duration}) vs the CSV record")
        for sym in symbols:
            live = dict(broker.historical_sessions(
                sym, datetime.now(NY), args.duration, "5 mins"))
            if not live:
                failures.append(f"{sym}: no historical bars returned")
                print(f"  {sym}: NO BARS RETURNED")
                continue
            days = sorted(live)
            print(f"  {sym}: {len(days)} sessions, "
                  f"{days[0].date()} → {days[-1].date()}")

            csv = dict(load_sessions(sym, ROOT))
            shared = sorted(set(days) & set(csv))
            if not shared:
                print("       no overlap with the CSV — cannot cross-check "
                      "(expected if the CSV ends well before today)")
                continue
            worst_bp, worst_day, checked = 0.0, None, 0
            for d in shared:
                ref = {b.idx: b for b in csv[d]}
                for b in live[d]:
                    r = ref.get(b.idx)
                    if r is None:
                        continue
                    checked += 1
                    for a, c in ((b.open, r.open), (b.high, r.high),
                                 (b.low, r.low), (b.close, r.close)):
                        if c and abs(a - c) / abs(c) * 1e4 > worst_bp:
                            worst_bp, worst_day = abs(a - c) / abs(c) * 1e4, d
            print(f"       {len(shared)} overlapping sessions, {checked} bars, "
                  f"worst {worst_bp:.2f} bp"
                  + (f" on {worst_day.date()}" if worst_day else ""))
            if worst_bp > 1.0:
                failures.append(
                    f"{sym}: live bars differ from the CSV by {worst_bp:.2f} bp")
                print("       ABOVE 1 bp — the live feed does not reproduce the "
                      "research record; thr80 will drift across the seam")

        # --- 3. live data (expected to fail out of hours) --------------
        print("\n[3] live market data (expected to FAIL outside RTH)")
        try:
            broker.assert_live_data()
            print("  live data available")
        except NotLiveDataError as exc:
            print(f"  not live: {exc}")
            print("  fine on a weekend. It MUST pass on Monday or the engine "
                  "will refuse to trade (§4).")
        except Exception as exc:             # noqa: BLE001
            print(f"  probe unavailable: {exc}")

    finally:
        broker.disconnect()

    print("\n" + "=" * 62)
    if failures:
        print("PRE-FLIGHT FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PRE-FLIGHT CLEAN — nothing blocking the Stage 4 dry run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
