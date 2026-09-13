"""The specification's numbers, in one place.

`STRATEGY.md` §2 is prose; this is the same thing as constants. Nothing in
`overnight/` re-types any of these — a second copy is a second source of truth,
which is how band_lab's `spec_constants.py` came to exist and why this file
mirrors that convention.

Every value here is load-bearing. Changing one changes what the engine trades,
so each carries the reason it has the value it has.
"""

from __future__ import annotations

#: Sessions in the realised-volatility window. STRATEGY.md §2.2.
RV_WINDOW = 20

#: How far back the window ENDS from the decision day, in sessions.
#:
#: 1, and it is forced rather than conservative. An MOC order must reach NYSE
#: markets by 15:50 ET (`IBKR Order types.md:13`), so day D's close is not
#: known when the decision is made. The window therefore ends at D-1.
RV_LAG = 1

#: Trading sessions per year, for annualising the volatility.
ANNUALISATION = 252

#: The percentile of an instrument's OWN prior RV history below which it is
#: eligible. STRATEGY.md §2.2.
PERCENTILE = 60.0

#: Prior observations required before any threshold is computed. Below this the
#: instrument is ineligible and the engine holds nothing on its account.
MIN_HISTORY = 60

#: Leg notional as a multiple of account equity. STRATEGY.md §2.1.
#:
#: XLU is 1x utilities, so 3x notional is needed to match the exposure SOXL
#: gives at 1x. The two legs are mutually exclusive, so gross notional is 1.0x
#: on a SOXL night and 3.0x on an XLU night, never 4.0x.
PRIMARY_SYMBOL = "SOXL"
PRIMARY_MULTIPLE = 1.0
COVER_SYMBOL = "XLU"

#: The RESEARCH multiple. 3.0x XLU matches the exposure 1.0x SOXL gives, and is
#: what `retreat_lab/out/proposed_ledger.csv` is priced at, so `parity.py` must
#: use it. It is not necessarily what gets deployed -- see COVER_MULTIPLE_LIVE.
COVER_MULTIPLE = 3.0

#: The DEPLOYED multiple, and the reason it is lower.
#:
#: 3.0x gross notional sits exactly on a 3:1 house cap, which leaves no headroom
#: at all: at precisely 3:1 any adverse overnight move puts the account over.
#: 2.5x is the figure the account actually has available and leaves 20% of room.
#: It costs 4.4 pp of CAGR (106.7% -> 102.3%), takes Sharpe 1.85 -> 1.82 and
#: leaves max drawdown unchanged at -28.9%. Cheap insurance against the one
#: constraint that can force a liquidation.
#:
#: XLU is a 1x ETF, so the leveraged-ETF schedule in
#: `Margin Trading Information from interactive brokers.md` (min(30% x leverage
#: factor, 100%) maintenance) does not apply to it; ordinary requirements do.
COVER_MULTIPLE_LIVE = 2.5

#: The flat state, named so no caller spells it as a bare string.
FLAT = "FLAT"

#: IBKR Pro tiered US stock/ETF commission, verified from
#: `IBKR Commission Fees.md`. The MINIMUM is the one that matters: it binds
#: below 100 shares, and at the wrong account size it costs 18.7 pp of CAGR.
#: STRATEGY.md §3.5.
COMMISSION_PER_SHARE = 0.0035
COMMISSION_MIN_ORDER = 0.35
COMMISSION_MAX_PCT = 0.01

#: Measured per-side cost in basis points OF THAT LEG'S NOTIONAL, for auction
#: (MOC/MOO) execution where no spread is crossed and commission is the whole
#: cost. From `retreat_lab/fills.py` and `out/fill_quality_20260912.csv`:
#: $0.0035/share over the share price. These are the numbers the proposed
#: ledger was priced with; they assume the account is above the §3.5 floor.
PRIMARY_COST_BPS = 0.29
COVER_COST_BPS = 0.83

#: Equity below which the commission minimum binds on the primary leg, at a
#: given price. Kept as a function rather than a number because it moves with
#: the share price.
def min_equity_for_per_share_rate(price: float, multiple: float = PRIMARY_MULTIPLE) -> float:
    """Equity at which an order reaches 100 shares and escapes the $0.35 floor."""
    return COMMISSION_MIN_ORDER / COMMISSION_PER_SHARE * price / multiple
