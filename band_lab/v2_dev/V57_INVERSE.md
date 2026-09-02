# V57 — Why you cannot just invert V54

V54's short straddle lost on every cell, the roll-21 variant at t = −8.84. The
obvious question is why not take the other side. This runs the long side through
the identical code, the identical cycles and the identical cost model, changing
one flag.

    python3 band_lab/v2_dev/short_vol_backtest.py --side long

The short side reproduces V54 to the decimal after the change, so the two
columns below differ only in which side of the trade is taken.

## The answer, in one table

| tenor | exit | short | t | long | t | **SUM** | spreads paid |
|---|---|---|---|---|---|---|---|
| 21-30d | expiry | −6.65% | −2.41 | **+4.76%** | 1.75 | **−1.88%** | 1 (entry only) |
| 31-45d | expiry | −6.44% | −1.78 | **+3.35%** | 0.95 | **−3.09%** | 1 |
| 46-60d | expiry | −16.63% | −2.11 | **+14.40%** | 1.84 | **−2.23%** | 1 |
| 21-30d | roll21 | −3.10% | −8.84 | **−1.30%** | −3.86 | **−4.40%** | 2 (round trip) |
| 31-45d | roll21 | −4.20% | −4.83 | **−0.81%** | −0.95 | **−5.01%** | 2 |
| 46-60d | roll21 | −9.72% | −1.67 | +3.97% | 0.69 | **−5.75%** | 2 |

**The two sides do not sum to zero. They sum to the spread.**

| | mean of the two sides |
|---|---|
| expiry exit — one spread paid | **−2.40%** |
| roll-21 exit — two spreads paid | **−5.05%** |
| ratio | **2.11x** |

Doubling the spreads paid roughly doubles the joint loss. That is as direct a
demonstration as this project has produced that **the spread, not the direction,
is what these tests keep measuring.** Flipping the position flips the sign of
the edge and leaves the sign of the cost alone, because the short sells the bid
and buys the ask while the long buys the ask and sells the bid. Both are on the
losing side of the quote, twice, every cycle.

**At roll-21, both sides lose.** Three of nine cells lose on the short and the
long simultaneously — which is impossible if direction were the thing being
measured, and inevitable if the spread is.

## So can you make money on the long side?

At the expiry exit the mean is positive on all three tenors: +4.76%, +3.35%,
+14.40%. That is real and it comes from paying only the entry spread.

**But no long cell reaches t > 2.0.** The best is 1.84 on 27 cycles. It would
fail V53's B1 exactly as the short side did, for the opposite reason: the short
side's losses are small and relentless, the long side's gains are large and
rare. Win rates of 43-52% with worst cycles of −24% to −36% and best cycles far
larger is a lottery-shaped payoff, and a lottery needs far more than 27 tickets
before its mean can be trusted.

This is the third time this repository has reached that result. V34 measured an
unhedged long straddle at +14.40% with t = +0.94 and 1 of 6 cells positive.
V31 delta-hedged it and got −2.94%, because hedging costs turn a thin positive
into a negative.

## A defect found and fixed in the writing

The first long run produced 562 cycles at 21-30 days against expiry's 59, which
is not a plausible ratio. `tp50` had been written as "close when the position is
worth half the credit", which for a short is taking half the profit and for a
long is a **stop-loss at −50%** — it fired almost immediately, on nearly every
cycle. Mirrored properly (sell out at 1.5x the debit paid) the counts fall to
72, 54 and 36 and the results change sign in two cells. The numbers above are
the corrected ones.

A second, smaller one: the premium guard `credit <= 0.10` rejected every long
cycle, because a long pays a debit and `credit` is negative there. Now tests
magnitude.

## What it settles

Inverting a losing strategy does not produce a winning one when the loss is
transaction cost. It produces a different losing strategy, and at the round-trip
exits it produces the same one.

The only configuration with a positive mean is the one that **pays the fewest
spreads** — hold to expiry, never close early — and even that cannot clear its
own standard error on this sample.
