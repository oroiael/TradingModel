# V50 — The intraday short straddle, and the comparison that made it look good

Band A #2, the last structure on the list whose measured premium had the right
sign for a seller. It does not have the right sign. The sign came from comparing
two different exposures, and the comparison was mine.

## The claim being tested

V27 measured SOXL's 30-day implied at 98.6% against an intraday-only realised
path of 81.0%, and 48% of variance sitting overnight. The inference drawn — by
me, in the queue — was that a seller who is flat overnight collects 17.6
volatility points of premium for risk never taken.

## Why that is wrong

An option's implied volatility prices the risk **over the option's own life**.
An instrument that exposes you only to intraday risk is priced on intraday risk.
There is no transfer.

The file settles it directly. ATM quotes, by days to expiry:

| DTE | what its life contains | n | median IV |
|---|---|---|---|
| **0** | expires today — **no overnight gap at all** | 217 | **68.4%** |
| **1** | expires tomorrow — **one gap** | 301 | **132.1%** |
| 2 | two gaps | 330 | 134.9% |
| 7 | one week | 328 | 111.8% |

**A 64-point step across the boundary where gap exposure begins.** The market
charges for the gap and does not charge for it when it is absent.

The 30-day implied of 98.6% is gap-inclusive. Setting it against an
intraday-only realised of 81.0% subtracts one thing from a different thing.
Doing exactly that produced, on first run here, a headline of **+0.312% of spot
per session after crossing the spread** — roughly 79%/yr, which is what a
number looks like when the units are wrong.

## The variance split, measured

| | annualised | share |
|---|---|---|
| intraday, open to close | **87.5%** | 60.4% |
| overnight, close to open | **70.9%** | **39.6%** |
| close to close, both | **116.2%** | |

1,653 sessions. V27 reported the overnight share at 48% on a different window;
39.6% here. Either way the gap is a large minority of total variance and it is
priced.

## The comparison that IS apples to apples

A 1-DTE option prices one session plus one gap, and close-to-close realised is
exactly that exposure:

| | |
|---|---|
| 1-DTE median IV | 132.1% |
| close-to-close realised | 116.2% |
| **edge to the seller** | **+15.9 vol pts** |
| 1-DTE round trip (spread 29.3% of mid) | **38.7 vol pts** |
| **net** | **−22.8 vol pts** |

The premium at one day is genuinely positive — larger than the 30-day, which
V27 measured *negative* — and the one-day spread is two and a half times it.

## And the structural problem that holds regardless

A position opened and closed every session pays the whole spread every session
while collecting one session of decay. The spread does not shrink with the
holding period; the decay does. From live quotes, 2026-09-02:

| tenor | straddle | one day of theta | daily round trip | cost / theta |
|---|---|---|---|---|
| 9d | $12.78 | $0.73 | $1.50 | **2.1x** |
| 30d | $25.68 | $0.43 | $4.80 | **11.1x** |
| 79d | $42.42 | $0.27 | $3.60 | **13.4x** |

Shorter tenors are better because theta accelerates into expiry, which is what
pointed at 0DTE. 0DTE removes the closing spread — it expires — but it is also
the contract with no gap in it, priced at 68.4% against an intraday realised of
87.5%. The seller is **underpaid by 19 points** there.

## Verdict

Not adopted, and the queue entry that produced it was wrong at the premise
rather than at the execution. Band A #2 is retired.

Every version of the trade fails for one of two reasons, and they are the same
reason seen twice: **the gap premium exists only in instruments that carry the
gap**, and **a daily round trip pays a spread sized for a position, against
decay sized for a day**.
