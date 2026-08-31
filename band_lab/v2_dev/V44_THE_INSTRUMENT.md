# V44 — The instrument is the problem, not the strategy

Reconstructed from SOXL's own daily returns. SOXL delivers 3× the index's
**daily** return by construction, so the index is recoverable exactly — this is
the product's definition, not a proxy.

## 2022-01-03 → 2026-07-30

| | |
|---|---|
| underlying semiconductor index | **+159.0%** |
| **SOXL actual (3×, daily reset)** | **+119.9%** |
| 3 × the index's total return | +477.0% |
| **realised leverage** | **0.75×** — paid for 3× |
| volatility decay cost | **−357 percentage points** |

**The unlevered index beat the 3× fund**, over 4.5 years, in a market that rose
159%. Holders paid for three turns of leverage, received three-quarters of one,
and carried three times the risk to get it.

Rolling 1-year holds (887 overlapping windows, ~3.5 independent — weak, and
reported as such):

| | SOXL | index |
|---|---|---|
| median | +55.9% | +30.6% |
| worst | **−86.5%** | −37.8% |
| % positive | 67% | 78% |

## What this settles

The catalogue asked, eighteen times, *"is there a statistical regularity in
SOXL's price series?"* The answer is no, and that was always the likely answer:
it is among the most heavily traded leveraged ETFs in existence and any pattern
in its 1-minute bars is arbitraged by faster people with lower costs.

**But no strategy was ever going to fix an instrument that converts +159% into
+120%.** The three findings now line up on the same conclusion:

| finding | measured in |
|---|---|
| realised leverage 0.75× against 3× paid for | V44 |
| option round trip 18.5 vol points, vs SMH's 2.9 | V43 |
| gross volatility edge +11.5 vol points | V31 |

The edge is real. The instrument takes 18.5 vol points to access it and 2.25
turns of leverage to hold it.

## Who is actually paid on SOXL

Not a rhetorical list — each is a measured or contractual transfer:

- **Direxion**: 0.75%/yr expense ratio on the fund's assets. Contractual.
- **Market makers**: the 18.5 volatility points measured in V43, on every round
  trip. That is not a fee to the fund; it is paid to whoever is on the other
  side of the quote.
- **Securities lenders**: SOXL is hard to borrow and the fund lends its holdings.
- **Directionally correct short-horizon traders**: real, unmodellable, and not
  what any test here attempted.

**The ETF is a product, not an opportunity.** Its economics are designed to sell
leverage for a fee. There is no residual edge inside the wrapper for the buyer to
find, and eighteen studies looking for one is consistent with that.

## What was never tested, stated plainly

Every strategy here was **direction-free or mechanical**. The measured 49–51%
hit rate applies to *simple* signals on the price series — dips, momentum,
time-of-day, weekday. It does **not** establish that no forecast works. Earnings,
supply cycles, capex, macro and cross-asset signals are untested and are not
testable from a 1-minute price file.

"No statistical property of this price series is exploitable" and "nothing works"
are different claims, and only the first has been demonstrated.

## What the data actually points at

Same sector exposure, three measured improvements:

| | SOXL | SMH / SOXX |
|---|---|---|
| 4.5-year return | +119.9% | index +159.0% |
| option round trip | 18.5 vol pts | **2.9** (SMH) / 8.0 (SOXX) |
| leverage decay | −357 pp | none |

**Everything that failed on SOXL failed on cost and leverage, and both are
properties of the instrument rather than the strategy.** The straddle's gross
edge of +11.5 volatility points is larger than SMH's entire round-trip spread of
2.9 — which is the first arithmetic in this project where the edge exceeds the
cost by a wide margin.

Whether SMH *carries* that premium is unmeasured. That is the next test, and it
is the one worth running.
