# V33 — Long straddle, UNHEDGED. Adoption bar, written before running.

Tests V29 Tier 1 **#2**, which V29 said to run "as the zero-hedge end of a
frequency sweep" alongside #1 and which was then not run: V30 fixed hedging at
"once daily at the close" and swept only entry and roll DTE. Confirmed absent —
`straddle_backtest.py` carries no hedge-frequency parameter.

Committed before the code that answers it exists.

## What changes from V30

Identical entry rule, identical contracts, identical data, identical costs on
the option legs. **Two things differ:**

1. **No delta hedge.** Zero stock trades. So no hedge P&L and no hedge friction.
2. **An exit-at-expiry option.** Held to expiry the ITM leg auto-exercises into
   stock and the OTM leg expires worthless, so **the exit half of the option
   spread is never paid.** Given that the spread is what killed #1, this is the
   part of #2 that could genuinely differ rather than merely being noisier.

## The prediction

Unhedged, the payoff is not accumulated variance — it is one terminal move
against the premium. The straddle wins if `|S_T − K| > premium paid`.

Two forces pull opposite ways and the test is which wins:

- **For it:** rolling at 14 DTE pays a full round-trip spread every cycle.
  Holding to expiry pays the **entry half only**, then liquidates the exercised
  leg at stock friction (6.70 bp) instead of an option spread (~17.8 vol
  points). That is the single largest cost in #1, roughly halved.
- **Against it:** V31 showed cycle return correlates **+0.85** with realised
  minus implied. Removing the hedge removes the machinery that converts that
  correlation into money, leaving a lottery ticket on one endpoint.

**If #2 beats #1, it is because of the spread, not because of the edge.** That
distinction has to be visible in the output or the result is not interpretable.

## Prespecified grid

Headline: **enter nearest 37 DTE, hold to expiry, no hedge.**

- exit rule: **roll at 14 DTE** (matches #1) and **hold to expiry** — 2
- entry DTE: **30, 37, 45** — 3
- hedge: **none** (that is the whole point) — 1

Six cells. The daily-hedged runs from V31/V32 are the comparison arm and are not
re-swept.

**Both spread regimes are reported for every cell:** the vendor end-of-day
spread as V31 charged it, and that plus the **V32-measured shortfall**. The
headline is the measured one, because V32 established the vendor figure
understates by 7.2 vol points.

**The shortfall is a ROUND-TRIP figure.** A cycle held to expiry crosses the
spread once, so it is charged **half** (3.6 points), not the full 7.2. Charging
the full amount to a position that never sells would manufacture a cost that
cannot occur, which is the mirror of the error V26 caught in the band study.

## Adoption bars

| # | bar | note |
|---|---|---|
| **B1** | mean return per cycle > 0 with **t > 2.0** | unchanged from V30 |
| **B2** | positive in **≥ 4 of 5** calendar years | unchanged |
| **B3** | every cost charged: entry spread, exit spread **or** exercise + stock liquidation, option commission, exercise fee | the exit path changes which costs apply |
| **B4** | **≥ 5 of 6** grid cells positive | 6 cells here, not 9 |
| **B5** | headline within **1 standard error** of the grid median | unchanged |
| **B6** | benchmark via `research_kit.Result` | unchanged |
| **B7** | max drawdown **< 35%** | unchanged |

B1–B5 must all pass. A result that beats #1 while still failing B1 is a *less
bad* loser, not a strategy, and will be reported as such.

## New assumptions this test introduces

| # | assumption | kind |
|---|---|---|
| A13 | At expiry the ITM leg exercises and is liquidated at the next session's close, paying the measured **6.70 bp** stock round trip. The OTM leg expires worthless at no cost. | `[ASSUMED]` mechanics; `[MEASURED]` cost |
| A14 | Exercise/assignment fee **$0 per contract**. IBKR's published schedule is not reachable from this environment and the user's statement contains no option trades, so this is **unverified**. It **flatters** the strategy; a fee of a few dollars a contract would make it worse. | `[ASSUMED]` |
| A15 | Settlement price is SOXL's close on the expiry date from the 5-minute price file. Options settle on the closing price, so this is the right series, but it ignores that a Friday-afternoon exercise decision is made before the close is known. | `[ASSUMED]` |
| A16 | No early exercise. The position is long-only so there is no assignment risk, and exercising a long option early forfeits time value. | `[VERIFIED]` by option pricing, not by IBKR behaviour |
| A17 | The half-spread shortfall on a one-way cross is exactly half the round-trip shortfall. | `[ASSUMED]` — symmetric bid/ask around mid, which V32's ticks support but did not test directly |

Assumptions A1–A12 from V30 carry over unchanged except A4 and A7, which no
longer apply to unhedged cells because there is no stock position.

## What would make me discard the result

- A cycle whose exit proceeds exceed the option's intrinsic value at settlement.
- Any unhedged cycle carrying a non-zero hedge P&L or hedge friction.
- A held-to-expiry cycle charged a full round-trip spread shortfall.
- Total cost below `entry spread + 2 x $0.65 x contracts`.

Asserted in code, not read off a table afterwards.
