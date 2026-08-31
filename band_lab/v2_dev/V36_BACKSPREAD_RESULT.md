# V36 — Call backspread (V29 Tier 1 #3). Result.

Tested against `V35_BACKSPREAD_BAR.md`, committed before the code existed.

    python3 band_lab/v2_dev/backspread_backtest.py --grid

## Verdict

**Not adopted. B1, B2, B4 and B5 all fail.**

| bar | test | result | |
|---|---|---|---|
| B1 | return/cycle > 0, t > 2.0 | **+3.72%, t = +0.35** | **FAIL** |
| B2 | positive in ≥ 4 of 5 years | **3 of 5** | **FAIL** |
| B3 | every cost charged | yes | PASS |
| B4 | ≥ 5 of 6 cells positive | **2 of 6** | **FAIL** |
| B5 | headline within 1 se of grid median | **median −7.40%** | **FAIL** |
| B7 | max drawdown < 35% | −24% | PASS |

## The headline was positive, so V35's discard rule fired

V35 said in advance: *"A positive result. Not because positives are forbidden,
but because the screen says it should lose by 5.5×, and a positive would mean the
simulator is crediting something the arithmetic says is not there. It would be
investigated before it was believed."*

The headline came in at **+3.72%**. Investigated:

| | |
|---|---|
| mean | +3.72%, se 10.76%, **t = +0.35** |
| 95% CI | **[−17.4%, +24.8%]** |
| **drop the 3 best cycles** | **−11.75%** |
| drop 3 best AND 3 worst (symmetric) | **−5.46%** |
| the 3 best | **+323%, +245%, +109%** |

**Three cycles out of 46 carry the entire result.** The symmetric trim — the
fair test, since it cuts both tails — is **−5.46%**, in line with the grid
median of −7.40%. The positive headline is not an edge; it is three tail events
in a sample where SOXL rose 152.8%.

And part of it is direction, not convexity:

| | cycles | mean return |
|---|---|---|
| SOXL rose over the cycle | 25 | **+5.45%** |
| SOXL fell over the cycle | 21 | +1.65% |

Correlation of cycle return with the underlying's move: **+0.51**.

## The prespecified grid

| long delta | exit | cycles | return/cycle | t | win% |
|---|---|---|---|---|---|
| 0.20 | expiry | 46 | −8.85% | −1.18 | 59% |
| 0.20 | roll | 70 | −6.84% | −1.71 | 37% |
| **0.25** | **expiry** | **46** | **+3.72%** | **+0.35** | 59% |
| 0.25 | roll | 74 | −7.95% | −1.87 | 24% |
| 0.30 | expiry | 46 | +11.58% | +0.85 | 26% |
| 0.30 | roll | 74 | −8.80% | −1.09 | 9% |

**Every roll cell is negative** (−6.84% to −8.80%), and the two positive cells
are both hold-to-expiry. That reproduces V34's finding independently: not
crossing the exit spread is the largest single effect in this line of work.

Note the 0.30/expiry cell — +11.58% on a **26% win rate**. That is the same tail
signature as the headline, more extreme.

## The screen was right, and it was right for the stated reason

V35 predicted before running: *"#3 loses, and by more than #1 or #2."* It does.
The mechanism named in advance holds:

| | spread | net vega | spread per unit of net vega |
|---|---|---|---|
| ATM straddle (V32, live) | $5.00 | 26.97 | **18.5 vol pts** |
| call backspread | $1.67 | 2.557 | **65.3 vol pts** |

**Selling an option to finance a long-volatility position cancels most of the
vega you are paying for and none of the spread you pay to sell it.**

**A caveat on the ranking.** #3's returns are on **max loss**; #1 and #2's are on
**premium**. Those denominators are not comparable, so "loses by more than #1 or
#2" cannot be checked strictly. What can be said: all four core bars fail, every
roll cell is firmly negative, and the one positive headline is three cycles.

## The correction to V29 that did hold

V29's skew figure was wrong and I re-measured it before writing the bar. Paired
per trade date over 1,125 dates rather than pooled as a median:

| | V29 cited | measured |
|---|---|---|
| skew (25d − ATM call) | −0.8 vol pts | **−2.92** (median −3.95) |
| dates the 25d call is cheaper | — | **81%** |

**The skew is 3.6× better than V29 claimed** — genuinely in the structure's
favour, and still nowhere near enough. The edge is worth $0.075/share against
$1.67 of entry spread, a ratio of 22×. Being right about the skew and wrong
about the cost is the same shape of error V29 made on the straddle, where it
took a median spread for a mean.

## Tier 1 is now complete

| | verdict | |
|---|---|---|
| #1 straddle, delta-hedged daily | **rejected** | −10.11%/cycle of premium, t = −3.76 |
| #2 straddle, unhedged | **not adopted** | −0.22%/cycle of premium; one outlier cell |
| #3 call backspread | **not adopted** | −5.46% trimmed; three cycles carry the headline |

**Every Tier 1 structure fails, and all three fail on the same thing.** The
volatility edge on SOXL is real — V27 measured it, V30 predicted it to within 0.3
vol points, V31 confirmed the machinery works with a +0.85 correlation. The cost
of collecting it exceeds it, and the live measurement in V32 made that worse
rather than better.

The one durable finding across all three: **cross the option spread as few times
as possible.** Holding to expiry beats rolling in every structure tested — worth
+6.65 points a cycle on the straddle, and the difference between all-negative and
two-positive cells here.

## What is left in the catalogue

Tier 2, none of which this work has eliminated:

- **#4 long-dated straddle (91–365 DTE)** — the cheapest spread on the surface at
  4.9 vol points against the ATM 30-day's 8.1, and the cheapest implied vol at
  95.4%. Given that cost is what killed #1–#3, this is the obvious next test.
  The matched-tenor realised-vs-implied comparison has never been run; it is one
  parameter in `vol_premium.py`.
- **#5 long both SOXL and SOXS, unrebalanced** — real convexity, no option, no
  spread, no roll. Its mean rests on very few events and needs the pre-2022 data.
- **#6 straddle hedged only at the open** — isolates the overnight gap, which is
  48% of variance.
- **#7 asymmetric strangle** avoiding the expensive put wing.

**#4 is the one indicated by everything measured so far.**
