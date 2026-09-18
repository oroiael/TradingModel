"""The pure strategy core.

Every strategy decision the engine makes is computed here and nowhere else.
No IBKR, no I/O, no clock, no dates, no global state — a pile of functions over
numbers, so `parity.py` can drive it with history and the live schedule can
drive it with today's, and the two are provably the same thing.

The shape mirrors `band_lab/live/strategy_core.py` for the same reason it works
there: a decision that cannot reach a broker cannot place a surprising order,
and a decision with no clock cannot behave differently at 15:45 than it does in
a test.

Constants come from `constants.py`. Nothing here re-types one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from constants import (
    CLEARING_PER_SHARE,
    COMMISSION_MAX_PCT,
    COMMISSION_MIN_ORDER,
    COMMISSION_PER_SHARE,
    COVER_MULTIPLE,
    COVER_SYMBOL,
    FLAT,
    PRIMARY_MULTIPLE,
    PRIMARY_SYMBOL,
    SELL_SEC_FEE_RATE,
    SELL_TAF_PER_SHARE,
)


@dataclass(frozen=True)
class Signal:
    """One instrument's eligibility on one decision day."""

    symbol: str
    rv: Optional[float]
    threshold: Optional[float]

    @property
    def eligible(self) -> bool:
        """Strictly below the cut, and only when both numbers exist.

        A missing RV or a missing threshold is ineligible, never eligible —
        the burn-in and a data gap must both fail closed. `<` not `<=` matches
        the research code; on a tie the instrument sits out.
        """
        if self.rv is None or self.threshold is None:
            return False
        return self.rv < self.threshold

    @property
    def margin(self) -> Optional[float]:
        """How far below the cut, in annualised volatility points.

        Negative means benched. For the report, not for the decision.
        """
        if self.rv is None or self.threshold is None:
            return None
        return self.threshold - self.rv


@dataclass(frozen=True)
class Decision:
    """What to hold tonight."""

    leg: str
    multiple: float
    primary: Signal
    cover: Signal

    @property
    def is_flat(self) -> bool:
        return self.leg == FLAT

    def describe(self) -> str:
        bits = []
        for s in (self.primary, self.cover):
            if s.rv is None or s.threshold is None:
                bits.append(f"{s.symbol} n/a")
            else:
                bits.append(f"{s.symbol} RV {s.rv:.1f} "
                            f"{'<' if s.eligible else '>='} {s.threshold:.1f}")
        return f"{self.leg} @ {self.multiple:.1f}x  ({', '.join(bits)})"


def decide(primary: Signal, cover: Signal,
           primary_multiple: float = PRIMARY_MULTIPLE,
           cover_multiple: float = COVER_MULTIPLE) -> Decision:
    """The rule, in full. STRATEGY.md §2.3.

    Primary first, cover only if the primary is benched, flat if neither
    qualifies. The legs are mutually exclusive by construction — there is no
    branch in which both are held, which is what keeps gross notional at the
    cover multiple rather than the sum of both on a cover night.

    The multiples are arguments rather than hardcoded because the deployed
    cover size differs from the researched one: the ledger is priced at 3.0x,
    the account trades 2.5x to stay off a 3:1 house cap. Defaulting to the
    research values is what lets `parity.py` remain a real test — a deployment
    change must not be able to silently redefine what the gate checks.
    """
    if primary.eligible:
        return Decision(primary.symbol, primary_multiple, primary, cover)
    if cover.eligible:
        return Decision(cover.symbol, cover_multiple, primary, cover)
    return Decision(FLAT, 0.0, primary, cover)


def signals(primary_rv: Optional[float], primary_cut: Optional[float],
            cover_rv: Optional[float], cover_cut: Optional[float]) -> "tuple[Signal, Signal]":
    """Build the two signals with the configured symbols attached."""
    return (Signal(PRIMARY_SYMBOL, primary_rv, primary_cut),
            Signal(COVER_SYMBOL, cover_rv, cover_cut))


def target_shares(equity: float, multiple: float, price: float) -> int:
    """Whole shares for a leg, rounded DOWN so the target notional is a ceiling.

    Whole shares, not fractional: an auction order is the point of this strategy
    and fractional quantities do not participate in one. Rounding down means an
    under-fill against target rather than unplanned leverage.
    """
    if equity <= 0 or multiple <= 0 or price <= 0:
        return 0
    return int(math.floor(equity * multiple / price))


def commission(shares: int, price: float, side: str = "BUY") -> float:
    """All-in IBKR cost for one order, back-solved from the activity statement.

    $0.005/share on the FIXED schedule, minimum $1.00, capped at 1% of trade
    value, plus $0.000003/share clearing. A SELL additionally pays the FINRA
    Trading Activity Fee per share and the SEC Section 31 fee on proceeds, so
    an exit is dearer than the entry that opened it — on the 629-share SOXL
    round trip, $4.63 out against $3.15 in.

    The minimum is why `STRATEGY.md` §3.5 sets a funding floor: below 200
    shares an order pays $1.00 whatever its size.

    Only the commission is capped at 1% — the regulatory fees are statutory
    and ride on top, which is what the statement shows.
    """
    if shares <= 0:
        return 0.0
    value = shares * price
    total = max(min(shares * COMMISSION_PER_SHARE, value * COMMISSION_MAX_PCT),
                COMMISSION_MIN_ORDER)
    total += shares * CLEARING_PER_SHARE
    if side.upper() == "SELL":
        total += shares * SELL_TAF_PER_SHARE + value * SELL_SEC_FEE_RATE
    return total


def round_trip_cost_bps(shares: int, entry: float, exit_: float,
                        equity: float) -> float:
    """Both commissions as basis points of ACCOUNT EQUITY, not of notional.

    Equity is the denominator throughout this strategy because the cover leg
    runs at 3x notional: a cost quoted against notional understates it threefold
    on exactly the nights it is largest.
    """
    if equity <= 0:
        return 0.0
    total = (commission(shares, entry, "BUY")
             + commission(shares, exit_, "SELL"))
    return total / equity * 10_000.0


def net_on_equity(overnight_return: float, multiple: float,
                  cost_bps_per_side: float) -> float:
    """Realised return on EQUITY for one held night.

    `cost_bps_per_side` is charged against NOTIONAL and therefore scales with
    `multiple`, which is what makes the cover leg's friction three times the
    primary's at the same quoted rate. A flat night is `multiple = 0` and
    returns exactly 0.0 — no cost is charged for an order never placed.
    """
    gross = multiple * overnight_return
    return gross - multiple * 2.0 * cost_bps_per_side / 10_000.0


def net_return(entry: float, exit_: float, multiple: float,
               cost_bps_per_side: float) -> float:
    """`net_on_equity` from a fill pair rather than a precomputed return."""
    return net_on_equity(exit_ / entry - 1.0, multiple, cost_bps_per_side)
