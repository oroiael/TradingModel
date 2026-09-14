"""The job that makes sure the account is flat, when `exit` did not.

    python3 overnight/run.py --job watchdog --transmit

**The one unrecoverable state in this strategy is holding a 3x ETF through a
session.** Everything else fails safe: a missed `enter` means no trade, a bad
quote means a refusal, a flat night means nothing happens. But a position that
survives 09:30 is exposed to a full trading day at 1x to 2.5x leverage, and the
strategy has no view whatsoever on intraday direction — it was never asked.

`exit` places a MOO at 09:15. It can fail to leave the account flat in at least
four ways, and only the first is one it can report:

1. the MOO is placed and rejected, or never acknowledged;
2. the MOO is placed and does not execute in the auction;
3. `exit` never runs at all — the machine slept, TWS was down, the scheduler
   did not fire;
4. `exit` runs after 09:29:30 and correctly refuses, leaving the position.

In three of those four nothing is running to notice. So this is a separate job
on its own schedule, and it reads the BROKER rather than anything `exit` wrote.

## The rules it is built from

Every one of these is a defect band_lab paid for; `orders.py:ensure_flat` carries
the full history.

**Give an order time to fill.** The first version of band_lab's flatten looped
with no pause, ran three attempts inside one second, saw 541 shares each time
because no market order fills that fast, and declared failure while its own
sells were in flight.

**Never stack duplicates.** That same loop then sent a *fresh* market order for
the whole position on each attempt. Three sells of 541 against one long 541 is a
short 1,082 — a failure to flatten turned into an inverted position, which is
worse than the thing it was fixing. A flatten already working is left alone.

**Budget in time, not attempts.** On 2026-08-10 a five-attempt loop exhausted
itself in 23 seconds with four minutes still on the clock, and the shares went
overnight.

**Only ever flatten.** This cannot open a position and has no opinion about
strategy. It sells what is there and stops.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time
from typing import Callable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import state as state_mod                                     # noqa: E402
from config import OvernightConfig                            # noqa: E402
from schedule import JobResult, Refused, _log, now_et         # noqa: E402

#: IBKR's own word for a sell, from `Execution.side`. Not "SELL".
SOLD = "SLD"

from constants import COVER_SYMBOL, PRIMARY_SYMBOL            # noqa: E402

#: Only these are ever sold. Named here so the warning can say so out loud.
_SYMBOLS_HINT = (PRIMARY_SYMBOL, COVER_SYMBOL)

#: Every order this job places ends with it, so it can recognise its own.
FLATTEN_SUFFIX = "-FLATTEN"

#: Market orders per symbol per run. See `_flatten_one` for why it is 2.
MAX_SENDS = 2


def flatten(broker, cfg: OvernightConfig, *,
            asof: Optional[dt.datetime] = None,
            events: Optional[Callable] = None,
            budget: float = 120.0,
            settle: float = 6.0,
            clock: Callable[[], float] = time.time) -> JobResult:
    """Sell anything still held in this strategy's symbols. Runs after 09:31 ET.

    Idempotent by construction: it sizes from `position()` every pass and leaves
    an already-working sell alone, so running it five times a day costs nothing
    on the four days it finds nothing.
    """
    asof = asof or now_et()
    wall = asof.timetz().replace(tzinfo=None)

    if wall < cfg.watchdog_open:
        raise Refused(
            f"{wall} is before {cfg.watchdog_open}. A market order sent into a "
            f"closed book is queued to an open this job cannot see the result "
            f"of — and at 09:15 the MOO has not had its auction yet. Waiting.")
    if wall >= cfg.watchdog_close:
        raise Refused(
            f"{wall} is past {cfg.watchdog_close}. A market order this close to "
            f"the bell competes with the closing auction for the same "
            f"liquidity, and `enter` is about to run. Flatten manually in TWS.")

    held = {s: broker.position(s) for s in cfg.symbols}
    live = {s: q for s, q in held.items() if abs(q) > 1e-9}

    intent = state_mod.read_intent(cfg.state_path)
    _describe(intent, held, events)

    if not live:
        _log(events, "info", "account is flat — nothing to do")
        return JobResult("watchdog", False, "flat", intent)

    shorts = {s: q for s, q in live.items() if q < 0}
    if shorts:
        raise Refused(
            f"short position {shorts} — this strategy never shorts, so buying "
            f"to cover would be acting on a state nobody designed. A human has "
            f"to look at this.")

    _log(events, "error",
         f"STILL HOLDING {live} after the open. The exit did not leave the "
         f"account flat; flattening now at market.")

    start = clock()
    sold: list[str] = []
    for symbol in list(live):
        sold.append(_flatten_one(broker, cfg, symbol, start, budget, settle,
                                 clock, events))

    remaining = {s: broker.position(s) for s in cfg.symbols}
    still = {s: q for s, q in remaining.items() if abs(q) > 1e-9}
    detail = "; ".join(sold)
    if still:
        _log(events, "error",
             f"NOT FLAT after {clock()-start:.0f}s: {still}. Sell it in TWS by "
             f"hand. This is the state the whole job exists to prevent and it "
             f"has failed — do not wait for the next run.")
        return JobResult("watchdog", True, f"{detail} | STILL HOLDING {still}",
                         intent)

    _log(events, "info", f"flat after {clock()-start:.0f}s")
    return JobResult("watchdog", True, detail, intent)


def _flatten_one(broker, cfg, symbol, start, budget, settle, clock, events) -> str:
    """Sell one symbol to flat, re-reading the position every pass.

    **At most `MAX_SENDS` market orders per symbol per run**, and never while
    one of ours is visibly working. That cap is the whole safety argument, so
    it is worth stating why it is 2 and not 1 or 5.

    Not 5, or unbounded: band_lab's first flatten re-sent the full position on
    every pass and turned a long 541 into a short 1,082. Overselling is not a
    smaller failure than holding, it is a different one — and this job is only
    ever supposed to reduce risk.

    Not 1: a non-warning IBKR error marks a trade `Cancelled` in the client
    while IBKR keeps working it (`wrapper.error`, and the 2026-08-10 ghost), and
    the inverse also happens — an order the client never saw acknowledged. One
    send with no retry means a single lost order leaves the position on the
    books until the next scheduled run.

    2 bounds the damage at one duplicate in the pathological case, recovers
    from a single lost order, and this job runs several times a day anyway.
    """
    sends = 0
    waited_for_foreign = False
    while True:
        qty = broker.position(symbol)
        if abs(qty) < 1e-9:
            return f"{symbol} flat after {sends} market order(s)"
        if clock() - start >= budget:
            return (f"{symbol} {qty:+.0f} UNSOLD after {sends} market "
                    f"order(s) and {budget:.0f}s")

        broker.refresh_orders()
        ours, foreign = _classify_sells(broker, symbol)

        if ours:
            # Never a second market order on top of our own. The position read
            # is the thing that ends this loop, and a fill will move it.
            _log(events, "info",
                 f"{symbol}: our flatten for {sum(ours):.0f} is working; "
                 f"waiting {settle:.0f}s for it rather than stacking")
            broker.wait(settle)
            continue

        if foreign and not waited_for_foreign:
            # Most likely the morning MOO. Give it exactly one settle to be
            # the thing that fixes this before taking it out of the way.
            _log(events, "info",
                 f"{symbol}: {len(foreign)} existing sell(s) for "
                 f"{sum(foreign):.0f}; giving them {settle:.0f}s")
            waited_for_foreign = True
            broker.wait(settle)
            continue

        if foreign:
            # An OPG order that missed its auction holds nothing and blocks the
            # fix. Clear it, then sell — never both at once.
            _log(events, "warn",
                 f"{symbol}: cancelling {len(foreign)} stale sell(s) and going "
                 f"to market")
            _cancel_sells(broker, symbol, events)
            broker.wait(1.0)
            continue

        if sends >= MAX_SENDS:
            _log(events, "error",
                 f"{symbol}: {sends} market orders sent and still holding "
                 f"{qty:+.0f}, with nothing showing as working. Refusing to "
                 f"send a third — an order IBKR is working but the client "
                 f"cannot see would be sold twice. Sell it in TWS by hand.")
            return f"{symbol} {qty:+.0f} UNSOLD — send cap reached"

        ref = f"ON-{dt.date.today():%Y%m%d}-{symbol}-FLATTEN"
        _log(events, "error", f"SELL MKT {qty:.0f} {symbol} ({ref})")
        broker.place_market(symbol, "SELL", qty, ref)
        sends += 1
        broker.wait(settle)                 # no market order fills instantly


def _classify_sells(broker, symbol):
    """Working sells, split into ours (this job's) and everything else.

    Ours are identified by `order_ref`, which is the only marker that survives
    the round trip. A flatten we sent is never cancelled and never added to; a
    foreign sell — the morning MOO, or a hand-placed order — can be cleared.
    """
    ours, foreign = [], []
    for w in broker.working_orders(symbol):
        if not str(getattr(w, "action", "")).upper().startswith("S"):
            continue
        qty = float(getattr(w, "qty", 0.0) or 0.0)
        ref = str(getattr(w, "order_ref", "") or "")
        (ours if ref.endswith(FLATTEN_SUFFIX) else foreign).append(qty)
    return ours, foreign


def _cancel_sells(broker, symbol, events) -> None:
    for w in list(broker.working_orders(symbol)):
        if not str(getattr(w, "action", "")).upper().startswith("S"):
            continue
        if str(getattr(w, "order_ref", "") or "").endswith(FLATTEN_SUFFIX):
            continue                        # never cancel our own
        oid = getattr(w, "order_id", None)
        if oid is None:
            continue
        try:
            broker.cancel(oid)
        except Exception as exc:            # noqa: BLE001
            _log(events, "warn", f"{symbol}: cancel({oid}) raised {exc}")


def _describe(intent, held, events) -> None:
    """Say what was expected against what is there, every run, flat or not."""
    if intent is None:
        _log(events, "info", f"no intent on file; broker holds {held}")
        return
    if intent.is_flat:
        stray = {s: q for s, q in held.items() if abs(q) > 1e-9}
        if stray:
            # Not a reason to refuse: failing to flatten is the unrecoverable
            # state and a stale state file is not. But it is worth saying,
            # because the other reading is that something else owns these.
            _log(events, "warn",
                 f"state says last night was FLAT but the broker holds {stray}. "
                 f"Selling it anyway — an unexplained 3x position through a "
                 f"session is the worse outcome. Note this only ever touches "
                 f"{', '.join(_SYMBOLS_HINT)}; if another strategy trades those "
                 f"on this account, the two will collide and one must move.")
        return
    kind = "intent" if intent.transmitted else "rehearsal intent (never sent)"
    _log(events, "info",
         f"{kind}: {intent.shares} {intent.leg} from {intent.decision_date}; "
         f"broker holds {held}")
