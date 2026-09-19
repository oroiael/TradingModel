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

#: IBKR US stock/ETF commission. This account is on the FIXED schedule, not
#: the tiered one: back-solved from the DU1790300 activity statement for
#: 2026-09-14..17, where all four buys reproduce to the ninth decimal as
#: `0.005 * shares + 0.000003 * shares` and none of the residuals is nonzero.
#: The code carried the TIERED rate ($0.0035) for the first four live nights,
#: which understated the per-share rate by 43%.
#:
#: The MINIMUM is the one that matters: it binds below 200 shares, and at the
#: wrong account size it costs pp of CAGR. STRATEGY.md §3.5. $1.00 is the
#: Fixed schedule's minimum and is INFERRED from identifying the schedule --
#: no order in the statement was small enough to trigger it (the smallest,
#: 218 SOXL, paid $1.0907).
COMMISSION_PER_SHARE = 0.005
COMMISSION_MIN_ORDER = 1.00
COMMISSION_MAX_PCT = 0.01

#: NSCC/DTCC clearing, charged per share on both sides. Exact: it is the
#: entire residual after the per-share commission on all four statement buys.
CLEARING_PER_SHARE = 0.000003

#: Sell-side only; buys pay neither. This is why an exit costs more than the
#: entry that opened it -- $4.63 out against $3.15 in, on the 629-share SOXL
#: round trip.
#:
#: Back-solved by least squares from the three statement sells, which span
#: $41.55 to $104.82 and so identify the two rates separately. The fit is
#: EXACT -- three equations, two unknowns, zero residual on all three, and
#: both parameters land on round numbers. That is the real schedule, not a
#: curve fit.
#:
#: The NAMES are an attribution, not a measurement: a per-share sell fee and a
#: fee on proceeds is the shape of FINRA's TAF and the SEC's Section 31 fee,
#: but IBKR does not break the line item out per trade, so only the TOTAL is
#: evidenced. If a future statement disagrees, refit -- do not assume the
#: published TAF rate.
SELL_TAF_PER_SHARE = 0.000195
SELL_SEC_FEE_RATE = 20.60e-6

#: MEASURED per-side cost in basis points OF THAT LEG'S NOTIONAL, for auction
#: (MOC/MOO) execution where no spread is crossed and fees are the whole cost.
#: From the seven fills in the 2026-09-14..17 activity statement:
#:
#:     SOXL  0.494 / 0.702 / 0.436  ->  mean 0.544   (at $101.26-114.82)
#:     XLU   1.211 / 1.456 / 1.211 / 1.457  ->  mean 1.334   (at $41.32-41.59)
#:
#: These REPLACE 0.29 / 0.83, which were the same calculation run at the
#: tiered rate. Realised cost came in 1.9x the assumption on SOXL and 1.6x on
#: XLU; across the first three closed round trips the old numbers overstated
#: P&L by $78.22 on $6,363.14 realised (1.23%).
#:
#: A flat bps figure is an approximation: a per-share fee is a LARGER fraction
#: of a cheap share, so these are only valid near the prices above. XLU costs
#: 2.5x as much per side as SOXL in bps purely because it trades at a third
#: of the price -- not because it is a worse fill. Backtests reaching into
#: SOXL's sub-$20 history understate cost badly at this constant; use
#: `core.commission` there instead.
PRIMARY_COST_BPS = 0.54
COVER_COST_BPS = 1.33

#: FROZEN. The cost assumption `retreat_lab/final_config.py` priced
#: `out/proposed_ledger.csv` with, and therefore the one `parity.py` must
#: replay at. It is deliberately NOT the live rate: the parity gate exists to
#: prove the live core reproduces the research ledger's DECISIONS and RETURN
#: ARITHMETIC, and it cannot do that if one side of the comparison is silently
#: repriced. Never "update" these to match reality.
#:
#: What this does NOT do is make the research right. STRATEGY.md §4.2's
#: backtested numbers are priced at the tiered rate this account does not pay,
#: so they are optimistic. Re-running the research at the real schedule is a
#: separate job; until it is done, treat §4.2 as an upper bound.
LEDGER_PRIMARY_COST_BPS = 0.29
LEDGER_COVER_COST_BPS = 0.83

#: Equity below which the commission minimum binds on the primary leg, at a
#: given price. Kept as a function rather than a number because it moves with
#: the share price.
def min_equity_for_per_share_rate(price: float, multiple: float = PRIMARY_MULTIPLE) -> float:
    """Equity at which an order is big enough to escape the $1.00 floor."""
    return COMMISSION_MIN_ORDER / COMMISSION_PER_SHARE * price / multiple
