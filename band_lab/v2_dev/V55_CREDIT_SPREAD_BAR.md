# V55 — The bar for defined-risk credit spreads, written before the code

**Status: PRESPECIFIED. No code exists yet. Results go in V56.**

V54 measured naked short vol and it failed all seven gates: median credit 21.0%
of spot against a median cost of 22.2%, plus six cycles in 680 that lost more
than the notional the position controlled.

Defined risk changes two things at once and they pull in opposite directions:

- **the tail is truncated** — the −268.8% cycle becomes bounded at the width
- **the credit shrinks and the leg count doubles** — you sell a 25-delta option
  and buy back part of what you just sold, then pay spread on both

The screen said this was a wash and worse. V54 is the reason not to trust that:
the screen and the measurement had never agreed until V54, and one agreement is
not a track record.

## The structures

Short leg at **25 delta**, long leg at **10 delta** — the width is set by the
market's own pricing rather than a dollar figure that means different things at
$9 and $164.

1. **Put credit spread** — sell 25Δ put, buy 10Δ put
2. **Call credit spread** — sell 25Δ call, buy 10Δ call
3. **Iron condor** — both of the above at once

## Grid — 3 structures x 3 tenors x 3 exits = 27 cells

Tenors by DTE at entry: **21-30, 31-45, 46-60.**
Exits: **hold to expiry**, **take profit at 50% of credit**, **close at 21 DTE.**
Identical to V54 so the two are directly comparable. Nothing else is searched.

## Costs, unchanged from V54

Entry sold at the **bid** and bought at the **ask** — every leg crosses. Early
exits reverse at the touch. Expiry settles at intrinsic with **no closing
spread**. Commission **$0.65 per contract per side**, so a condor pays eight
commissions a round trip against a straddle's four.

## Return convention

**P&L divided by max loss**, which for a defined-risk spread is
`(width − credit) × 100` — the capital genuinely committed. That is the correct
denominator here and it is directly comparable to buy-and-hold, whose
denominator is the share price. V54's return-on-notional is reported alongside
so the two studies can be read against each other.

## Gates

| bar | test |
|---|---|
| **B1** | best-cell mean return per cycle > 0 with **t > 2.0** |
| **B2** | positive in **at least 4 of 5** calendar years |
| **B3** | every cost above verified charged in the ledger |
| **B4** | **at least 20 of 27** grid cells positive |
| **B5** | headline cell within **1 SE of the grid median** |
| **B6** | max drawdown **< 50%** on the cycle equity curve |
| **B7** | **beats buy-and-hold SOXL on MAR** over the identical window |
| **B8** | **no cycle loses more than its stated max loss** — the defined-risk claim has to hold in the ledger, not just in the description |

All eight must pass. B8 is new and is a correctness check on the simulator: if a
cycle exceeds its width the position was not what the code claimed to hold.

## Stated in advance

**The prior is failure, and the reason is arithmetic.** A 25-delta short option
carries roughly a 25% chance of finishing in the money. The credit on a 25/10
spread is typically a quarter to a third of the width, which needs a win rate
near 70-75% merely to break even before costs — and the costs here are four legs
of a spread that V32 measured at 12-16% of mid.

**What would change my mind.** B1 and B4 passing together on a structure whose
median credit-to-width ratio is high enough to survive the four-leg toll. If
only the put side passes, that is a bull-market artifact over a window where
SOXL rose 151%, and B2 across five years is the gate that should catch it.

## Known omissions

Early assignment is not modelled and hurts the short leg. Margin is not modelled
beyond using max loss as the denominator. Pin risk at expiry is ignored. No
IV-rank or regime gate.
