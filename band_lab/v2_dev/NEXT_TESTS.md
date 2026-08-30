# What to test next — a menu, not a plan

**Status: PROPOSAL. Nothing here has been run.** Priors are stated so they can
be scored later.

---

# Part 1 — What "harvesting volatility" actually means

The phrase has been doing a lot of work in this project and it hides four
completely different businesses. Only one of them is what the band strategy
attempted, and it is the only one that requires predicting direction.

| # | mechanism | what you get paid for | needs direction? |
|---|---|---|---|
| **M1** | **Spread capture** | providing liquidity — you quote both sides and earn the bid-ask | **no** |
| **M2** | **Variance risk premium** | bearing the risk of a large move; implied vol exceeds realized on average | **no** |
| **M3** | **Rebalancing / volatility pumping** | mechanically selling what rose and buying what fell across a portfolio | **no** |
| **M4** | **Volatility drag capture** | the mathematical decay a leveraged daily-reset fund suffers | **no** |
| **M5** | **Directional timing** | correctly guessing which way price goes next | **YES** |

**The band strategy is M5 wearing M3's clothes.** "Buy the dip, sell the pop" is
not rebalancing — rebalancing has no view, it just trims winners into losers on a
schedule. The band picks a moment and bets price reverts. That is a forecast, and
three independent measurements say the forecast is worthless here:

```
  from any minute            +0.5% before -0.5%   48.5%
  after a 1% dip                                  48.3%
  after any trailing move, any lookback           47-51%
```

**The one thing that IS forecastable is magnitude.** Implied volatility predicts
next-day realized range at R² = 0.25, t = 11.15. Direction: R² = 0.001.

**So the organising principle for everything below: build on volatility, never on
direction.** Every test in Part 2 is scored against that.

---

# Part 2 — The tests

Effort: **S** hours, **M** a day, **L** several days.
Prior: my honest guess at the chance it survives, before running it.

## Group A — Mechanical, no forecast required

### T1. Short both SOXL and SOXS (decay harvest) — **already partly measured**
Both are 3x daily-reset funds. Both bleed to volatility drag regardless of
direction. Short both in equal notional and you hold ~zero delta and collect the
bleed. **Measured, 2022+, daily rebalance:**
```
  SHORT both 50/50   +6.0% total   CAGR +1.3%   vol 2.0%   maxDD -1.2%   t=+1.43
  LONG  both 50/50   -5.9% total   CAGR -1.3%   (the same number, sign-flipped)
  daily correlation  -0.9995
```
The mechanism is real and the sign is right. **The problem is size:** 1.3%/yr
before borrow costs, and leveraged inverse ETFs frequently carry 1–5% borrow
fees, with SOXS often hard-to-borrow.
**Test:** get IBKR's actual historical borrow rates for both, subtract, see what
survives. Also sweep leverage — 2.0% vol and −1.2% drawdown is a lot of room.
**Kills it:** borrow > 1.3%/yr, which is likely.
**Effort S. Prior: 20%** it survives borrow. Worth doing because it is cheap and
the answer is a hard number.

### T2. Rebalancing bonus, SOXL against cash
Classic volatility pumping. Hold x% SOXL, (1−x)% cash, rebalance on a schedule.
The rebalance itself harvests variance without any view.
**Test:** sweep x ∈ {20,30,40,50%} × rebalance ∈ {daily, weekly, monthly,
5%-band, 10%-band}. Benchmark: buy-and-hold x% SOXL, never rebalanced.
**The number that matters:** rebalanced minus never-rebalanced, not the total.
**Effort S. Prior: 60%** it shows a positive bonus; **10%** it is large enough to
matter after costs.

### T3. Rebalancing between SOXL and SOXS
At −0.9995 correlation this is the textbook setup for a rebalancing bonus. It is
also a textbook trap: both legs decay, so you may be paying two decays to harvest
one bonus.
**Test:** same sweep as T2, and decompose the result into bonus vs decay so the
two are not confused.
**Effort S. Prior: 15%.** T1 already suggests the decay dominates.

### T4. Rebalance-frequency sensitivity as a diagnostic
If T2/T3 show a bonus, it must scale with rebalance frequency in a specific way.
If it doesn't, the "bonus" is something else.
**Effort S.** Run only if T2 or T3 is positive.

## Group B — Leveraged-ETF structural effects

### T5. End-of-day rebalancing flow — **the most interesting untested idea**
Leveraged ETFs must trade near the close to reset their leverage: after an up
day they buy, after a down day they sell, proportional to the day's move. This is
a mechanical, predictable, published flow. On a big day it is enormous.
**Test:** regress the 15:30–16:00 return on the 09:30–15:30 return, across all
1,150 days. If the flow is real, the coefficient is positive and grows with the
size of the earlier move.
**Why it might work:** this is not a forecast about the market, it is a forecast
about a forced trade by a known participant at a known time.
**Why it might not:** it is well known, so it may already be arbitraged into the
pre-close price.
**Effort S. Prior: 50%** the effect is visible; **20%** it is tradeable after
costs. **This is my top pick in the whole document.**

### T6. Forecast the decay, then size the harvest
Volatility drag ≈ ½σ²L(L−1) per period. σ² is forecastable (IV → RV, R² = 0.25).
Therefore **tomorrow's decay is forecastable even though tomorrow's direction is
not.**
**Test:** predict next-day realized variance from IV, size the T1 short-both
position proportional to it, compare against constant sizing.
**Effort M. Prior: 40%** it beats constant sizing; the underlying trade still has
to survive T1's borrow problem.

### T7. Overnight vs intraday decomposition
The options study found 41% of total variance is overnight — and the band
strategy is flat every night by construction, so it sits out 41% of the movement
and cannot hedge any of it.
**Test:** split every day into overnight (close→open) and intraday
(open→close). Are their return distributions different? Is either forecastable
from the other, or from IV?
**Effort S. Prior: 70%** the distributions differ materially; **25%** it is
tradeable.

### T8. Tracking-error mean reversion, SOXL vs 3× SOXX
SOXL is supposed to be 3× SOXX daily. We measured the realized slope at 2.986.
Deviations from the mechanical relationship should revert, because an authorised
participant is paid to make them revert.
**Test:** compute SOXL/(3×SOXX) intraday, look for reversion in the residual.
**Effort M. Prior: 30%** visible; **10%** tradeable retail — this is exactly the
kind of thing HFT eats first.

## Group C — Genuine out-of-sample tests (data exists, LFS restored)

### T9. Run the band strategy on FAS and SPXL — **the held-out data I said didn't exist**
`FAS_5min_6Years.csv` (3× financials) and `SPXL_5min_6Years.csv` (3× S&P) are in
LFS and pullable. **The band strategy was never fitted to either.** This is a
real out-of-sample test of the whole idea, not a re-slice of the same data.
**Test:** run the corrected simulator, unchanged parameters, on FAS and SPXL.
Benchmark each against its own underlying.
**Kills it:** if it also loses there, the idea is dead across instruments rather
than specific to semiconductors.
**Effort S. Prior: 10%** it works — but the *information value is high either
way*, and it is the closest thing to a clean test this project has ever had.
**Second pick in the document.**

### T10. The dip and momentum censuses on FAS/SPXL/SOXX
Is 48.5% a SOXL fact or a market fact? Running the census on other instruments
answers it in an afternoon.
**Effort S. Prior: 85%** they all come back ~48-50%, which is itself worth
knowing because it closes the question permanently.

### T11. The census on SOXX — the unlevered index
No daily reset, no decay, tighter spreads. Friction as a share of a 0.5% move is
much smaller.
**Effort S. Prior: 20%.**

## Group D — Dimensions of the band never tested at all

### T12. The short side
`V8_DIRECTION_TESTS.md` states plainly: *"long only, one position at a time.
Never tested — the short side is unexplored (not rejected)."* Four years on, it
is still unexplored.
**Test:** mirror the rules. Sell the rip, cover 1% lower, stop 4% higher.
**Effort S. Prior: 15%** — the censuses say the distribution is near-symmetric,
so a mirror of a losing strategy probably also loses. But it is a stated gap in
the project's own documentation and cheap to close.

### T13. Both directions at once
Long the dip and short the rip simultaneously — a synthetic straddle in shares.
Zero net delta at the midpoint; profits if price oscillates through both.
**Effort M. Prior: 10%.** Pays double friction, and friction is what kills
everything here.

### T14. Multiple concurrent positions
Also never varied. Currently one position at a time.
**Effort S. Prior: 10%.**

### T15. Hold overnight
The 15:55 flatten is a design principle, "never varied" per V6. Given T7 (41% of
variance is overnight), this is a large unexplored surface.
**Effort M. Prior: 20%** — and note it changes the risk profile completely.

## Group E — Volatility-conditioned versions of what exists

### T16. Replace the ATR5 gate with an IV-based gate
The current gate uses 5 *completed prior* sessions — backward-looking. IV is
forward-looking and we have proven it predicts next-day range at R² = 0.25.
**Test:** gate on IV instead of ATR5. Same everything else.
**Effort M. Prior: 25%** it improves things; the strategy still has to overcome a
negative base rate, so this is a smaller version of a losing bet.

### T17. Size by predicted volatility
Fixed fractional sizing ignores that some days are 3× more volatile.
**Effort S. Prior: 40%** it improves risk-adjusted return; **5%** it turns a
negative expectancy positive. **Sizing cannot fix a negative edge** — say this out
loud before running it.

### T18. Trade only the top-decile IV days
V17's R5 found the edge concentrated in ~30% of ON days. If that concentration is
predictable from IV, it matters.
**Effort M. Prior: 20%.**

## Group F — Execution side

### T19. Earn the spread instead of paying it
We measured that live pays **5.7 bp round trip** in spread. A market maker earns
that. The band always crosses.
**Test:** simulate resting limit orders on both sides with a realistic fill
probability, instead of taking liquidity.
**Honest problem:** modelling queue position from OHLCV is guesswork, and
guessing it favourably is exactly the error that killed the original backtest.
**Effort L. Prior: 15%,** and high risk of fooling ourselves. Would need the fill
assumption validated against live paper fills before any number is believed.

### T20. Total friction budget as a screen
Before testing any new idea, compute friction as a share of the target move.
We already know: 32% of a 0.25% move, 8% of a 1% move.
**Effort S.** Not a strategy — a filter to stop us testing things that cannot
clear costs. **Should be run first and applied to everything else.**

## Group G — Options (partly settled)

### T21. Short straddle / strangle on top-decile IV days, defined risk
The prior study's F6 killed naked selling in all 30 permutations, but F7 found
losses concentrated in 3–5 weeks out of 2.5 years, and buying a wing *improved*
total P&L. That combination was never re-tested across the full 2022–2026 sample
now available.
**Effort L. Prior: 25%.** The variance risk premium is the most robust of the
five mechanisms in Part 1, and it is the only one this project has real data for
across a bear year.

### T22. Re-run the whole options study on 2022–2026 with the benchmark column
The original study had 2024–2026 only, and never printed the underlying's return.
Both are now fixed. Every one of its nine findings should be recomputed.
**Effort M. Prior: 60%** that at least one finding materially changes.

## Group H — Methodology (do these regardless)

### T23. Make the benchmark column mandatory
Audit finding F3. One line. Would have caught the band strategy, R1 and the PMCC.
**Effort S. Do this first.**

### T24. Standard error printed beside every sweep
V21 found parameter curves flat inside one standard error. Any sweep whose range
is inside its own error bar is not an optimisation and must not be reported as
one.
**Effort S.**

### T25. Re-audit V1–V14
Never independently reviewed. All ran on the bug. Their conclusions are currently
unsupported rather than wrong.
**Effort L.**

---

# Part 3 — What NOT to test

- **Any further parameter sweep on the band.** V21: curves flat inside one
  standard error. There is nothing there.
- **Anything requiring a directional forecast at a 1-minute-to-1-day horizon.**
  Three independent censuses. It is settled.
- **Smaller thresholds.** Friction is 32% of a 0.25% move.
- **A broad search across many ideas.** With ~1,150 days, 100 tests produce ~5
  false winners, and there is no held-out data to catch them — except what T9
  creates.

---

# Part 4 — Suggested order

| order | test | why |
|---|---|---|
| 1 | **T23, T20** | benchmark column + friction screen. Prevents the next mistake. Hours. |
| 2 | **T5** — EOD rebalancing flow | best mechanism-to-effort ratio in the document; a forced trade by a known party at a known time |
| 3 | **T9** — band on FAS/SPXL | the only genuine out-of-sample test available; informative whichever way it lands |
| 4 | **T1 + borrow costs** | the decay is measured and real; one number decides it |
| 5 | **T7** — overnight/intraday split | 41% of the variance we have never looked at |
| 6 | **T22** — options study rebuilt on 2022–2026 | the variance risk premium is the strongest of the five mechanisms |
| 7 | **T12** — the short side | a stated four-year-old gap, cheap to close |

**If only one thing gets run: T5.** It is the only idea in this document that
pays for something other than a forecast, has a named counterparty who is forced
to trade, and has data already on disk.

**Nothing here should be run as a search.** Each gets a prespecified bar and a
benchmark column, or it does not get run.
