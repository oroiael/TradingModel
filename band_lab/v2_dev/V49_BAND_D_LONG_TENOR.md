# V49 — Band D re-priced at the long tenor

V48 found SOXL's 79-day round trip is less than half its 30-day, and that every
structure in this project had been priced at 30-45 days, the dearest point on
the curve. This re-prices the three surviving structures at both tenors against
live quotes taken 2026-09-02 ~14:05 ET.

## A defect found on the way, and what it did not touch

`bs.py:43` tests `right == "CALL"` and falls through to the **put** branch for
anything else. V48's helper passed `"C"`, so every call was priced as a put.

It surfaced rather than hid, because `implied_vol` returns NaN outside the
no-arbitrage band and a 130-strike "put" quoted at 4.60 against a 105.87 spot is
far below its 24.13 intrinsic. The docstring's refusal to return a boundary
value is what made the bug visible instead of plausible.

**V48's published numbers are unaffected.** Its ratio table used IBKR's own
midpoint IV, which never touched `bs.py`. Its spread table used the *difference*
between IV at bid and IV at ask, and for a near-ATM option the mispricing moves
both by nearly the same amount:

| | V48 published | corrected |
|---|---|---|
| SOXL 30d round trip | 20.1 | **20.1** |
| SOXX 30d | 7.5 | **7.5** |
| SMH 30d | 3.3 | **3.3** |

Identical to the decimal. The levels moved; the differences did not.

## Skew replicates at both tenors

| tenor | 25d put | 25d call | skew |
|---|---|---|---|
| 30d | 113.5% (Δ−0.21) | 100.5% (Δ+0.29) | **+12.96** |
| 79d | 119.3% (Δ−0.18) | 107.4% (Δ+0.33) | **+11.94** |

V28 measured +11.6. Both tenors land on it.

## The calendar's premise is inverted today

| | SOXL ATM IV |
|---|---|
| 9d | 96.25% |
| 30d | 106.07% |
| 79d | 108.99% |

**Upward sloping.** V28 measured the opposite — 112.8% at 2-7 DTE against 95.4%
at 91-365, a 17.4-point inversion. Selling the front and buying the back was a
credit on V28's surface and is a **debit** on today's.

That is a regime difference, not a contradiction: term structure normally slopes
up in calm markets and inverts under stress. It means the calendar's edge is not
a property of the instrument, it is a property of the day.

## Band D, re-priced

| structure | tenor | edge | spreads | net |
|---|---|---|---|---|
| **#7 calendar** | 9d/79d | −12.74 | 20.9 | **−33.6** |
| **#7 calendar** | 30d/79d | −2.92 | 29.6 | **−32.5** |
| **#9 risk reversal** | 30d | +12.96 | 15.1 | **−2.1** |
| **#9 risk reversal** | **79d** | **+11.94** | **11.9** | **+0.0** |
| **#8 put ratio / BWB** | 30d | +12.96 | 35.2 | **−22.2** |
| **#8 put ratio / BWB** | 79d | +11.94 | 21.5 | **−9.5** |

The long tenor helps materially — #9 moves from −2.1 to break-even, #8 from
−22.2 to −9.5 — and it is still not enough. **Nothing clears with room.**

## The long-tenor discount is not uniform

V48 measured it at the money only. Across the surface it does not hold:

| leg | 30d | 79d | |
|---|---|---|---|
| ATM call | 20.1 | 9.6 | halves |
| 25d put | 7.5 | 3.9 | halves |
| 25d call | 7.6 | **8.1** | **widens** |

The put wing and the body get cheaper with tenor; the call wing does not. Any
structure whose edge lives in the call wing gains nothing from going out.

## Verdict

**#7 dead** at every tenor pair, and its premise is regime-dependent besides.
**#8 dead**, −9.5 at its best.
**#9 is exactly break-even at 79 days** — the closest anything in this project
has come — and break-even is where it stops being interesting. It is short skew,
which is short crash protection, on an instrument whose worst rolling year in
V44's sample was **−86.5%**. Before commission, before financing, before the
delta-hedging V29 priced at 8%/yr on hedged notional, the expectation is zero
and the tail is the worst on the board.

A zero-expectation trade with that tail is not a marginal opportunity. It is a
well-priced option, which is what the whole surface has looked like from the
start.
