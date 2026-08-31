
# V41 — Asymmetric strangle (V29 Tier 2 #7). Bar, before the code.

Buy a **near-the-money put** and a **wide (25-delta) call**, avoiding the
expensive put wing. Committed before the code exists.

## The skew is real and larger than V29 said

Measured per trade date, 1,125 dates, 24–50 DTE:

| leg | implied vol |
|---|---|
| ATM call | 96.7% |
| ATM put | 98.0% |
| **25-delta call** (the cheap wing) | **93.8%** |
| **25-delta put** (the expensive wing) | **106.2%** |

**Put wing minus call wing: +12.35 volatility points.** V29 cited 11.6 from a
pooled median; per date it is larger. The premise — that the put wing is the
expensive thing to avoid — holds.

## And the structure comparison that kills it

| structure | vega-wtd IV | vega | spread $ | **spread, vol pts** | net delta |
|---|---|---|---|---|---|
| straddle (ATM call + ATM put) | 97.31% | 9.16 | 1.52 | **13.9** | −0.00 |
| symmetric strangle (25d + 25d) | 99.97% | 7.21 | 0.99 | **10.6** | +0.00 |
| **#7: ATM put + 25d call** | **96.07%** | 8.14 | 1.37 | **14.1** | **−0.25** |

#7 buys volatility **1.24 points cheaper** than the straddle. But its round-trip
spread is **14.1 vol points against the straddle's 13.9** — 0.3 worse. Net
advantage: **+0.94 volatility points per cycle.**

V32 established the straddle's deficit at **−6.3 vol points** net (gross edge
+11.5 against a measured spread of 17.8), which came out at −10.11% per cycle.

**+0.94 against −6.3 closes 15% of the gap.** It is not close.

### A side observation worth recording

The **symmetric** strangle has the cheapest spread of the three — 10.6 vol
points against the straddle's 13.9 — because both its legs are out of the money
and cheaper to cross. But it buys the most expensive volatility (99.97%),
because it includes the very put wing #7 exists to avoid. The two effects nearly
cancel: +2.66 worse on vol, −3.3 better on spread, net +0.64.

**All three structures land within 1 volatility point of each other.** The skew
is large, the spread differences are large, and they offset. That is the finding
the structure comparison actually produces, and it is more useful than any one
of them.

## The problem V29 did not mention

**Net delta −0.25.** Unhedged, #7 is a *directional short bet* on a fund that
rose **152.8%** over the sample. It is not a volatility structure unless it is
delta-hedged, and V31/V32 measured the daily-hedged straddle losing 10.11% per
cycle. Both versions are run; the hedged one is the fair test of the skew claim.

## The prediction

**#7 loses, by roughly the straddle's margin less one volatility point.**
Unhedged it should lose considerably more, because a −0.25 delta into a +152.8%
market is a directional loss with nothing to do with skew.

## Prespecified grid

Headline: **ATM put + 25-delta call, nearest 37 DTE, roll at 14, hedged daily at
the close** — matching V31/V32 in every respect except the strikes, so the
comparison isolates the structure.

- call-leg delta: **0.20, 0.25, 0.30** — 3
- hedge: **daily**, **none** — 2

Six cells, both spread regimes. Nothing else swept.

## Adoption bars

| # | bar | note |
|---|---|---|
| **B1** | return/cycle > 0 with **t > 2.0** | |
| **B1b** | **must beat the straddle at the same DTE and hedge mode** | #7 is a strike change to #1; if it does not beat #1 it has no reason to exist |
| **B3** | every cost charged | |
| **B4** | ≥ 5 of 6 cells positive | |
| **B7** | max drawdown < 35% | |

## New assumptions

| # | assumption | kind |
|---|---|---|
| A26 | Both legs come from the same expiry, with the put nearest 50 delta and the call nearest the target delta. A date where either is unavailable within 0.08 delta is skipped. | `[ASSUMED]` |
| A27 | The V32 spread shortfall (7.2 vol pts round trip, measured on an ATM straddle) applies to this structure scaled by the ratio of its vendor spread to the straddle's — 14.1/13.9. **The shortfall has not been measured on out-of-the-money legs**, whose spreads are wider in vol terms, so this likely understates it. | `[ASSUMED]` |

V30 A1–A12 carry over.

## What would make me discard the result

- The hedged #7 cell beating the hedged straddle by more than ~1 volatility
  point can explain. The screen says the whole structural advantage is +0.94; a
  larger win means something other than skew is being credited, and V39 has just
  demonstrated what that looks like — three defects, the last of them lookahead
  worth +2.47 points per cycle, all found because a prespecified prediction kept
  being contradicted.
- Any unhedged cell showing a net delta materially different from −0.25 at entry.
