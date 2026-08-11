#!/usr/bin/env python3
"""Check every factual claim in SKILL.md against the installed ib_async.

A reference that quietly goes stale is worse than no reference: it reads with
the same authority whether or not it is still true. This is the cheapest
possible guard — run it after any `pip install -U ib_async`, and after editing
the skill.

    python3 .claude/skills/ibkr-semantics/scripts/verify_claims.py

Exit 0 means every claim still holds. Exit 1 names the ones that do not, and
the skill needs editing before it is trusted again.
"""

from __future__ import annotations

import inspect
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIVE = os.path.join(_HERE, "..", "..", "..", "..", "band_lab", "live")
for _p in (os.path.abspath(_LIVE), os.path.abspath(os.path.join(_LIVE, "..", "phase1"))):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import ib_async                                             # noqa: E402
import ib_async.ib as I                                     # noqa: E402
import ib_async.wrapper as W                                # noqa: E402
from ib_async.order import OrderStatus                      # noqa: E402


def flat(fn) -> str:
    """Source with whitespace normalised — docstrings wrap, and a naive
    substring test on the raw text fails for that reason alone. The first
    version of this script reported reqGlobalCancel as unverified because of
    a line break, which is a false alarm about a true claim."""
    return " ".join(inspect.getsource(fn).split())


def main() -> int:
    err = flat(W.Wrapper.error)
    failures = []

    claims = [
        ("DoneStates == {Filled, Cancelled, ApiCancelled, Inactive}",
         set(OrderStatus.DoneStates) == {"Filled", "Cancelled", "ApiCancelled",
                                         "Inactive"}),
        ("ActiveStates is the six the skill lists",
         set(OrderStatus.ActiveStates) == {"PendingSubmit", "ApiPending",
                                           "PreSubmitted", "Submitted",
                                           "ValidationError", "ApiUpdate"}),
        ("PendingCancel is in neither set",
         OrderStatus.PendingCancel not in OrderStatus.DoneStates
         and OrderStatus.PendingCancel not in OrderStatus.ActiveStates),
        ("openTrades() returns everything not in DoneStates",
         "DoneStates" in flat(I.IB.openTrades)),
        ("cancelOrder sets PendingCancel, not Cancelled",
         "PendingCancel" in flat(I.IB.cancelOrder)),
        ("placeOrder-as-modify asserts only not-DoneStates",
         "assert trade.orderStatus.status not in OrderStatus.DoneStates"
         in flat(I.IB.placeOrder)),
        ("warningCodes are the ten listed, plus 2100-2199",
         "frozenset({105, 110, 165, 321, 329, 399, 404, 434, 492, 10167})" in err
         and "2100 <= errorCode < 2200" in err),
        ("103 is not a warning code",
         "103" not in err.split("warningCodes")[1][:120]),
        ("a non-warning error sets the trade Cancelled",
         "trade.orderStatus.status = OrderStatus.Cancelled" in err),
        ("ib_async states a modify error can leave the order live",
         "modification to *existing* order just has an update error, "
         "but the order is STILL LIVE" in err),
        ("orderStatus overwrites the local status from TWS",
         "dataclassUpdate(trade.orderStatus" in flat(W.Wrapper.orderStatus)),
        ("reqGlobalCancel reaches other clients' orders",
         "other clients or TWS/IB gateway" in flat(I.IB.reqGlobalCancel)),
        ("Order.ocaType defaults to 0, so it must be set explicitly",
         ib_async.Order().ocaType == 0),
    ]

    # The engine's own transcription, when it is importable from here.
    try:
        from broker import ACTIVE_STATES, DONE_STATES, is_working
        claims += [
            ("broker.DONE_STATES matches the package",
             DONE_STATES == set(OrderStatus.DoneStates)),
            ("broker.ACTIVE_STATES matches the package",
             ACTIVE_STATES == set(OrderStatus.ActiveStates)),
            ("is_working treats PendingCancel as working",
             is_working("PendingCancel")),
        ]
    except ImportError:
        print("  [skip] band_lab/live not importable — package claims only")

    print(f"ibkr-semantics: {len(claims)} claims vs ib_async "
          f"{getattr(ib_async, '__version__', '?')}")
    for label, held in claims:
        print(f"  [{'ok  ' if held else 'FAIL'}] {label}")
        if not held:
            failures.append(label)

    if failures:
        print(f"\n{len(failures)} claim(s) no longer hold. Edit SKILL.md before "
              f"relying on it.")
        return 1
    print("\nAll claims verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
