"""The two jobs. Everything that touches the broker with intent lives here.

`core.py` decides; this places. The split matters because the decision is pure
and testable and this is neither — it has a clock, a broker and side effects.

Both jobs follow the same shape: refuse early, connect, establish ground truth
from the BROKER, act once, confirm, record. Neither loops, neither sleeps for
long, and neither runs outside its window.

## The rules these jobs are written around

**The broker is the only source of truth.** The exit job sells what
`position()` reports, never what the state file remembers. band_lab's defect 3
sized from an execution instead of a position and left 241 of 541 shares
unprotected; the same class of error here would leave a 3x ETF held through a
session.

**One order is not one fill.** `executions()` returns as many rows as the book
required. Anything comparing a count must count round trips, not executions.

**15:50 is a commitment point.** After it an MOC can be neither cancelled nor
reduced (`IBKR Order types.md:14`), so the enter job checks the clock before it
sends and never after.

**Fail closed.** Every refusal below leaves the account flat or unchanged. There
is no path where uncertainty results in a larger position.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from dataclasses import dataclass
from typing import Callable, NamedTuple, Optional
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import core                                                   # noqa: E402
import features                                               # noqa: E402
import state as state_mod                                     # noqa: E402
from config import OvernightConfig, TIMEZONE                  # noqa: E402
from constants import (                                       # noqa: E402
    COVER_SYMBOL, FLAT, PRIMARY_SYMBOL, RV_LAG, RV_WINDOW,
)

NY = ZoneInfo(TIMEZONE)


class Refused(RuntimeError):
    """A guard stopped the job. The account is flat or unchanged."""


@dataclass
class JobResult:
    job: str
    acted: bool
    detail: str
    intent: Optional[state_mod.Intent] = None
    ledger_row: Optional[dict] = None


def now_et() -> dt.datetime:
    return dt.datetime.now(NY)


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.2f}%"


def _log(events, level, msg):
    if events:
        events(level, msg)
    print(f"  [{level}] {msg}", flush=True)


# ------------------------------------------------------------- the clock lock

def _bypass_clock(cfg, events=None, window="") -> bool:
    """True when the clock guards may be skipped, because nothing can be sent.

    The two hard deadlines are about orders, not about runs. An MOC arriving
    after 15:50 is rejected and, once accepted, cannot be cancelled or reduced;
    Arca rejects new MOO orders from 09:29:55. A job with `transmit` off places
    neither, so for it the deadlines describe nothing.

    That reasoning holds ONLY while nothing can be sent, so the condition is
    re-checked here rather than trusted from the flag. `config.validate()`
    already refuses the combination; this is the second lock on the same door,
    because the door opens onto a rejected live order.
    """
    if not getattr(cfg, "rehearse_now", False):
        return False
    if cfg.transmit:
        raise Refused(
            "rehearse_now is set AND transmit is on. The clock guards are the "
            "only thing between this run and a rejected late auction order. "
            "Refusing to run either way.")
    if window:
        _log(events, "warn",
             f"OUT-OF-HOURS REHEARSAL — the {window} window is not enforced. "
             f"Nothing will be sent. This exercises the data path only; the "
             f"real run must still land inside the window.")
    return True


# ------------------------------------------------------------------ features

def daily_features(broker, symbol: str, cfg: OvernightConfig, asof: dt.datetime,
                   events: Optional[Callable] = None):
    """Fetch daily bars for one instrument, ending strictly before the decision day.

    The walk-forward threshold is a percentile of ALL prior RV observations, so
    a short history is a *different* threshold, not a noisier one. `min_sessions`
    is enforced rather than warned about for that reason.

    Daily bars come from `AuctionBroker.daily_sessions`, not band_lab's
    `historical_sessions` — that one indexes bars by minutes since 09:30 and
    refuses a `1 day` size outright, which is correct for what it is for.

    **The decision day's own bar is dropped.** `reqHistoricalData` with an
    `endDateTime` inside a live session returns a PARTIAL bar for that day, and
    after 16:00 it returns a complete one. Either would put day D's close inside
    the RV window, which is the single thing `RV_LAG` exists to prevent — and it
    would do so silently, because a partial bar looks like any other bar. The
    filter is on the date, so it is correct at 15:45, at 20:10, and on a
    weekend alike.
    """
    bars = broker.daily_sessions(symbol, asof, cfg.history_duration)
    sessions = [features.Session(_bar_date(b), float(b.open), float(b.close))
                for b in bars]
    sessions.sort(key=lambda s: s.date)

    cutoff = asof.date()
    dropped = [s for s in sessions if s.date >= cutoff]
    if dropped:
        _log(events, "info",
             f"{symbol}: dropped {len(dropped)} bar(s) dated {cutoff} or later "
             f"— day D's own close can never enter its own RV window")
        sessions = [s for s in sessions if s.date < cutoff]

    if len(sessions) < cfg.min_sessions:
        raise Refused(f"{symbol}: {len(sessions)} sessions, need "
                      f"{cfg.min_sessions} — the threshold would be wrong")
    return sessions


def cross_check_basis(symbol: str, sessions, reference_csv: str,
                      events: Optional[Callable] = None,
                      tolerance: float = 0.002) -> Optional[float]:
    """Compare live closes against the research file, on the dates both cover.

    The threshold is a percentile of the instrument's own RV history, so the
    live feed has to be the SAME SERIES the backtest measured, not merely a
    correct one. `whatToShow="ADJUSTED_LAST"` would back-adjust for dividends
    and remove the quarterly ex-div gaps from the close-to-close returns; XLU
    yields about 2.8%, so five years of that is a double-digit divergence in the
    old prices and a visibly lower RV. Requesting the wrong basis is silent —
    both series look like plausible prices — so it is measured instead.

    Returns the largest relative difference, or None when the dates do not
    overlap. Informational: it never refuses, because a stale research file is
    not a reason to stop trading.
    """
    if not reference_csv or not os.path.exists(reference_csv):
        _log(events, "warn", f"{symbol}: no research file to cross-check against")
        return None
    try:
        ref = {s.date: s.close for s in features.load_sessions(reference_csv)}
    except Exception as exc:                                  # noqa: BLE001
        _log(events, "warn", f"{symbol}: could not read {reference_csv}: {exc}")
        return None

    pairs = [(s.date, s.close, ref[s.date]) for s in sessions if s.date in ref]
    if not pairs:
        _log(events, "warn", f"{symbol}: research file and live history do not "
                             f"overlap; basis unverified")
        return None

    worst_date, live, book = max(pairs, key=lambda t: abs(t[1] / t[2] - 1.0))
    worst = abs(live / book - 1.0)
    level = "info" if worst <= tolerance else "error"
    _log(events, level,
         f"{symbol}: {len(pairs)} dates overlap {min(p[0] for p in pairs)}"
         f"..{max(p[0] for p in pairs)}; worst close mismatch {worst*100:.3f}% "
         f"on {worst_date} (live {live:.4f} vs research {book:.4f})")
    if worst > tolerance:
        _log(events, "error",
             f"{symbol}: the live feed is NOT the series the threshold was "
             f"fitted on. Check whatToShow — TRADES vs ADJUSTED_LAST is the "
             f"usual cause. The decision below is computed on a different "
             f"history than the backtest.")
    return worst


def _bar_date(bar) -> dt.date:
    d = getattr(bar, "date", None) or getattr(bar, "time", None)
    if isinstance(d, dt.datetime):
        return d.date()
    if isinstance(d, dt.date):
        return d
    return dt.date.fromisoformat(str(d)[:10])


class LegSignal(NamedTuple):
    """What one instrument contributes to tonight's decision."""

    rv: Optional[float]
    threshold: Optional[float]
    last_date: dt.date
    last_close: float


def todays_signals(broker, cfg: OvernightConfig, asof: dt.datetime,
                   events: Optional[Callable] = None):
    """RV and threshold for both legs, as of the decision day.

    After `daily_features` the newest session is D-1, which is exactly what the
    RV window must end on. The decision day itself is `asof`; its close does not
    exist yet and must not.

    The threshold history is built here rather than taken from `features.build`.
    `build` emits a row only for days that have a FOLLOWING session, because it
    also measures the realised overnight return — so its newest row is D-2, and
    using it would decide today against a cut one observation short of what the
    research computes. The loop below runs to D-1 inclusive, which is every
    decision day strictly before today, and that is what `build` gives a day in
    the middle of the history.
    """
    out = {}
    for symbol in cfg.symbols:
        sessions = daily_features(broker, symbol, cfg, asof, events)
        if getattr(cfg, "rehearse_now", False):
            cross_check_basis(symbol, sessions,
                              cfg.reference_csv.get(symbol, ""), events)
        returns = features.close_to_close(sessions)
        n = len(sessions)                       # sessions[n-1] is D-1
        hist = []
        for i in range(RV_WINDOW + RV_LAG, n):  # every decision day before today
            v = features.realised_vol(returns, i)
            if v is not None:
                hist.append(v)
        # today is decision index n: its window ends at sessions[n-1].close.
        rv = features.realised_vol(returns, n)
        cut = features.threshold_at(hist)
        out[symbol] = LegSignal(rv, cut, sessions[-1].date, sessions[-1].close)
    return out


# --------------------------------------------------------------- ENTER (MOC)

def enter(broker, cfg: OvernightConfig, *, asof: Optional[dt.datetime] = None,
          events: Optional[Callable] = None) -> JobResult:
    """Decide tonight's leg and send the MOC. Runs 15:30-15:50 ET."""
    asof = asof or now_et()
    clock = asof.timetz().replace(tzinfo=None)
    rehearsing = _bypass_clock(cfg, events,
                               f"{cfg.enter_open}-{cfg.enter_deadline} MOC")

    if not rehearsing:
        if clock < cfg.enter_open:
            raise Refused(f"{clock} is before the {cfg.enter_open} window opens")
        if clock >= cfg.enter_deadline:
            raise Refused(
                f"{clock} is past the {cfg.enter_deadline} MOC deadline. A late "
                f"MOC is rejected, not queued, and after 15:50 it can be neither "
                f"cancelled nor reduced. Doing nothing.")

    # Ground truth before anything else. Both must be clean.
    for symbol in cfg.symbols:
        pos = broker.position(symbol)
        if abs(pos) > 1e-9:
            raise Refused(
                f"already holding {pos:+.0f} {symbol}. The exit job should have "
                f"sold this at the open — investigate before trading on top of it.")
        working = broker.working_orders(symbol)
        if working:
            raise Refused(f"{len(working)} working order(s) on {symbol}; refusing "
                          f"to add another")

    equity = broker.net_liquidation()
    if equity < cfg.min_equity:
        raise Refused(f"equity ${equity:,.0f} is below the ${cfg.min_equity:,.0f} "
                      f"floor — the $0.35 commission minimum would dominate")

    sigs = todays_signals(broker, cfg, asof, events)
    primary, cover = sigs[PRIMARY_SYMBOL], sigs[COVER_SYMBOL]
    p_rv, p_cut = primary.rv, primary.threshold
    c_rv, c_cut = cover.rv, cover.threshold
    sp, sc = core.signals(p_rv, p_cut, c_rv, c_cut)
    decision = core.decide(sp, sc, cfg.primary_multiple, cfg.cover_multiple)
    _log(events, "info",
         f"newest session {primary.last_date} (D-1) | "
         f"{PRIMARY_SYMBOL} rv {_pct(p_rv)} vs cut {_pct(p_cut)} | "
         f"{COVER_SYMBOL} rv {_pct(c_rv)} vs cut {_pct(c_cut)}")
    _log(events, "info", decision.describe())

    intent = state_mod.Intent(
        decision_date=asof.date().isoformat(), leg=decision.leg,
        multiple=decision.multiple, shares=0, order_id=0, order_ref="",
        equity_at_entry=equity, reference_price=0.0,
        primary_rv=p_rv, primary_threshold=p_cut,
        cover_rv=c_rv, cover_threshold=c_cut,
        submitted_at=asof.isoformat(), transmitted=False)

    if decision.is_flat:
        state_mod.write_intent(cfg.state_path, intent)
        _log(events, "info", "FLAT tonight — no order")
        return JobResult("enter", False, "flat", intent)

    price = _reference_price(broker, decision.leg, sigs[decision.leg], cfg,
                             rehearsing, events)

    shares = core.target_shares(equity, decision.multiple, price)
    notional = shares * price
    if shares <= 0:
        raise Refused(f"sizing produced {shares} shares at ${price:.2f}")
    if notional > cfg.max_notional:
        raise Refused(f"${notional:,.0f} exceeds the ${cfg.max_notional:,.0f} cap")

    ref = f"ON-{asof:%Y%m%d}-{decision.leg}-ENTER"
    _log(events, "info",
         f"BUY MOC {shares} {decision.leg} @ ~${price:.2f} = ${notional:,.0f} "
         f"({decision.multiple:.2f}x on ${equity:,.0f})")

    order_id = broker.place_moc(decision.leg, "BUY", shares, ref)
    intent.shares = shares
    intent.order_id = order_id
    intent.order_ref = ref
    intent.reference_price = price
    intent.transmitted = bool(getattr(broker, "transmit", True)) and order_id > 0
    state_mod.write_intent(cfg.state_path, intent)

    confirmed = _confirm_working(broker, decision.leg, order_id, cfg, events)
    return JobResult("enter", True,
                     f"MOC {shares} {decision.leg} id={order_id} "
                     f"{'acknowledged' if confirmed else 'NOT ACKNOWLEDGED'}",
                     intent)


def _working_sells(broker, symbol) -> "list[float]":
    """Quantities of any working SELL. Empty when the broker cannot answer —
    unknown must not become a reason to skip the exit."""
    try:
        broker.refresh_orders()
        working = list(broker.working_orders(symbol))
    except Exception:                                         # noqa: BLE001
        return []
    return [float(getattr(w, "qty", 0.0) or 0.0) for w in working
            if str(getattr(w, "action", "")).upper().startswith("S")]


def cancel_working_buys(broker, symbols, events=None) -> int:
    """Kill any working BUY before exiting. Returns how many were cancelled.

    The morning jobs sell; nothing in them should ever add. A BUY still working
    at 09:15 can only be last night's entry that did not complete, and leaving
    it alone risks the worst shape this strategy has: sell the position at the
    open, then have the leftover buy fill at tonight's close, leaving a position
    nobody decided to hold and no exit scheduled to close it.

    Whether an unfilled MOC survives its own auction is NOT verified — IBKR's
    documentation is unreachable from here and the first live night's 629-of-
    1,390 fill is the only evidence this project has. Cancelling costs nothing
    when there is nothing to cancel, which is the whole argument for doing it
    unconditionally rather than waiting to find out.
    """
    killed = 0
    for symbol in symbols:
        try:
            broker.refresh_orders()
            working = list(broker.working_orders(symbol))
        except Exception as exc:                              # noqa: BLE001
            _log(events, "warn", f"{symbol}: could not read working orders: {exc}")
            continue
        for w in working:
            if not str(getattr(w, "action", "")).upper().startswith("B"):
                continue
            oid = getattr(w, "order_id", None)
            _log(events, "warn",
                 f"{symbol}: a BUY is still working (id={oid}, "
                 f"{getattr(w, 'qty', '?')} shares). Cancelling it — the exit "
                 f"must never leave something behind that can open a position "
                 f"tonight with no exit scheduled for it.")
            if oid is None:
                continue
            try:
                broker.cancel(oid)
                killed += 1
            except Exception as exc:                          # noqa: BLE001
                _log(events, "error",
                     f"{symbol}: cancel({oid}) raised {exc} — check TWS by hand")
    return killed


def _reference_price(broker, symbol: str, signal: "LegSignal",
                     cfg: OvernightConfig, rehearsing: bool,
                     events: Optional[Callable] = None) -> float:
    """A price to size against, at 15:45. It is NOT the fill price.

    The MOC fills at the closing auction, which has not happened. This only has
    to be close enough that `floor(equity * multiple / price)` lands on the
    right share count — and "right" is exact, not approximate: the multiple is
    defined against equity, so the notional is equity x multiple AT THE PRICE
    USED. A price that is not the current market is therefore not a rounding
    error, it is the wrong position size, and after 15:50 an MOC can be neither
    cancelled nor reduced.

    The first pre-flight made that concrete. At 21:29 on a Sunday the quote read
    $111.56 against Friday's $121.82 close, and sized 1,277 shares where 1,149
    was the intent — 9% over, silently, with nothing on screen to say the price
    was 8% from anything the strategy knew. Whether that was IBKR's overnight
    session genuinely quoting semis lower or a stale book was not knowable from
    the log, which was the actual defect.

    So: log the provenance always, prefer a midpoint only from a book tight
    enough to have one, and let a TRANSMITTING run refuse a price that is not
    plausibly a price. A rehearsal never refuses — it is there to show you this.
    """
    detail = _quote_detail(broker, symbol)
    close, when = signal.last_close, signal.last_date
    _log(events, "info", f"{symbol} quote: {detail.describe()}")

    spread = detail.spread_pct
    if spread is not None and spread <= cfg.max_quote_spread:
        price, source = (detail.bid + detail.ask) / 2.0, "midpoint"
    elif detail.last > 0:
        price, source = float(detail.last), "last"
        if spread is not None:
            _log(events, "warn",
                 f"{symbol}: {spread*100:.2f}% spread is wider than the "
                 f"{cfg.max_quote_spread*100:.2f}% a midpoint is trusted at "
                 f"(measured normal is 0.008% SOXL / 0.024% XLU); using `last`")
    elif rehearsing and close > 0:
        price, source = close, f"{when} close"
        _log(events, "warn",
             f"{symbol}: no usable quote out of hours; sizing this rehearsal "
             f"off the {when} close. A real run REFUSES here.")
    else:
        raise Refused(f"no usable price for {symbol}: {detail.describe()}")

    if close > 0:
        drift = price / close - 1.0
        line = (f"{symbol}: sizing off {source} ${price:.4f}, "
                f"{drift*100:+.2f}% from the {when} close ${close:.4f}")
        if abs(drift) <= cfg.max_price_deviation:
            _log(events, "info", line)
        elif rehearsing:
            _log(events, "warn", line + " — a real run would REFUSE this")
        else:
            raise Refused(
                line + f" — beyond the {cfg.max_price_deviation*100:.0f}% band. "
                f"The worst 15:45 move on a traded night in six years was "
                f"23.65%, so this is not a market move; it is a quote that is "
                f"not a price. Sizing on it would send the wrong number of "
                f"shares into an auction that cannot be undone.")
    return price


def _quote_detail(broker, symbol: str):
    """`quote_detail` when the broker has one, else adapt a plain `quote`."""
    if hasattr(broker, "quote_detail"):
        return broker.quote_detail(symbol)
    q = broker.quote(symbol)
    from broker_ext import QuoteDetail                        # noqa: PLC0415
    return QuoteDetail(float(q.bid), float(q.ask), float(q.last or 0.0),
                       None, 0)


def _confirm_working(broker, symbol, order_id, cfg, events, tries=10, pause=3.0):
    """Poll until IBKR reports the order working. Silence here is the failure.

    A synthetic id (negative) comes from a rehearsal and has nothing to confirm.
    """
    if order_id < 0:
        _log(events, "info", "rehearsal — nothing to confirm")
        return True
    for _ in range(tries):
        try:
            broker.refresh_orders()
            working = list(broker.working_orders(symbol))
        except Exception as exc:                              # noqa: BLE001
            # The order is ALREADY PLACED. Letting this raise would report a
            # failure for an order that reached IBKR, and the obvious response
            # to that — run it again — would send a second one.
            _log(events, "error",
                 f"cannot confirm order {order_id}: {exc}. It was sent and may "
                 f"be working. Do NOT re-run this job; look in TWS.")
            return False
        for w in working:
            if getattr(w, "order_id", None) == order_id:
                _log(events, "info", f"order {order_id} acknowledged by IBKR")
                return True
        broker.wait(pause)
    _log(events, "error",
         f"order {order_id} never appeared as working. It may still have "
         f"reached IBKR — do NOT re-place it; check TWS before 15:50.")
    return False


# -------------------------------------------------------------- CONFIRM (fill)

#: IBKR's own words for the two sides of an execution, from `Execution.side`
#: in band_lab's adapter: "BOT" | "SLD". Not "BUY"/"SELL".
BOUGHT, SOLD = "BOT", "SLD"


def confirm(broker, cfg: OvernightConfig, *, asof: Optional[dt.datetime] = None,
            events: Optional[Callable] = None) -> JobResult:
    """After the closing auction: record what the MOC actually filled at.

    **This job exists because the entry fill cannot be read the next morning.**
    `IBBroker.executions` reads `ib.fills()`, which covers the current session
    only; once the connection is gone and the day has rolled, yesterday's 16:00
    print is not retrievable through that path. Capture it the same evening or
    lose it — and losing it means never measuring fill quality against the
    auction print, which is the entire reason to run on paper.

    Runs after 16:00 ET. Read-only: it places nothing.
    """
    asof = asof or now_et()
    intent = state_mod.read_intent(cfg.state_path)
    if intent is None:
        raise Refused("no intent on file — nothing to confirm")
    if intent.is_flat:
        _log(events, "info", "flat night — nothing to confirm")
        return JobResult("confirm", False, "flat", intent)

    execs = [e for e in broker.executions(intent.leg)
             if str(e.side).upper() == BOUGHT]
    if not execs:
        _log(events, "error",
             f"MOC for {intent.shares} {intent.leg} shows NO fill. Either it "
             f"missed the auction or it was rejected. The account may be flat "
             f"tonight — check TWS.")
        return JobResult("confirm", False, "no fill", intent)

    qty = sum(float(e.qty) for e in execs)
    px = sum(float(e.qty) * float(e.price) for e in execs) / qty
    pos = broker.position(intent.leg)

    intent.filled_shares = int(qty)
    intent.fill_price = round(px, 4)
    intent.confirmed_at = asof.isoformat()
    state_mod.write_intent(cfg.state_path, intent)

    detail = (f"{intent.leg} filled {qty:.0f} @ {px:.4f} "
              f"across {len(execs)} execution(s); position {pos:+.0f}")
    if abs(pos - qty) > 1e-9:
        _log(events, "warn",
             f"position {pos:+.0f} != filled {qty:.0f} — the exit sizes from "
             f"the position, so this is a reporting discrepancy, not a risk")
    if int(qty) != intent.shares:
        _log(events, "warn",
             f"partial: ordered {intent.shares}, filled {qty:.0f}")
    _log(events, "info", detail)
    return JobResult("confirm", True, detail, intent)


# ----------------------------------------------------------------- EXIT (MOO)

def exit_(broker, cfg: OvernightConfig, *, asof: Optional[dt.datetime] = None,
          events: Optional[Callable] = None) -> JobResult:
    """Sell whatever is held, at the opening auction. Runs 09:00-09:29:30 ET.

    Sizes from `broker.position()`. The state file is read only to enrich the
    report — if it disagrees with the broker, the broker wins and the difference
    is logged.
    """
    asof = asof or now_et()
    clock = asof.timetz().replace(tzinfo=None)
    rehearsing = _bypass_clock(cfg, events,
                               f"{cfg.exit_open}-{cfg.exit_deadline} MOO")

    if not rehearsing:
        if clock < cfg.exit_open:
            raise Refused(f"{clock} is before the {cfg.exit_open} window opens")
        if clock >= cfg.exit_deadline:
            raise Refused(
                f"{clock} is past the {cfg.exit_deadline} MOO deadline (Arca "
                f"rejects new MOO orders from 09:29:55). A position left open "
                f"now will be held through the session — flatten it manually.")

    cancel_working_buys(broker, cfg.symbols, events)

    held = {s: broker.position(s) for s in cfg.symbols}
    live = {s: q for s, q in held.items() if abs(q) > 1e-9}

    intent = state_mod.read_intent(cfg.state_path)
    if intent and intent.is_actionable and intent.leg not in live:
        _log(events, "warn",
             f"state says {intent.shares} {intent.leg} but the account does not "
             f"hold it — the MOC may not have filled. Selling what is there.")
    elif intent and not intent.is_flat and not intent.transmitted:
        _log(events, "info",
             f"the last intent on file ({intent.shares} {intent.leg}, "
             f"{intent.decision_date}) was a rehearsal and was never sent")

    if not live:
        _log(events, "info", "nothing held — no exit order")
        return JobResult("exit", False, "flat", intent)

    sent = []
    for symbol, qty in live.items():
        if qty < 0:
            raise Refused(f"{symbol} position is {qty:+.0f} (short). This strategy "
                          f"never shorts — investigate before acting.")

        # A sell already working covers this position. Adding a second is how a
        # long 541 became a short 1,082 in band_lab, and this job is re-runnable
        # by hand and by a scheduler that saw a non-zero exit code — so it has to
        # be safe to run twice.
        existing = _working_sells(broker, symbol)
        if existing and sum(existing) >= qty - 1e-9:
            _log(events, "warn",
                 f"{symbol}: {len(existing)} sell(s) for {sum(existing):.0f} "
                 f"already working against {qty:.0f} held. NOT sending another — "
                 f"two sells against one position is a short, which is worse "
                 f"than the thing it would be fixing.")
            sent.append((symbol, qty, 0, True))
            continue

        ref = f"ON-{asof:%Y%m%d}-{symbol}-EXIT"
        _log(events, "info", f"SELL MOO {qty:.0f} {symbol}")
        oid = broker.place_moo(symbol, "SELL", qty, ref)
        ok = _confirm_working(broker, symbol, oid, cfg, events)
        sent.append((symbol, qty, oid, ok))

    detail = "; ".join(f"{s} {q:.0f} id={o}{'' if ok else ' NOT ACKNOWLEDGED'}"
                       for s, q, o, ok in sent)
    return JobResult("exit", True, detail, intent)
