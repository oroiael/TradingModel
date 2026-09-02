# V48 — The leverage ratio across tenors, and the sqrt(252) question settled

Queue item #4. Run 2026-09-02 ~13:58 ET, market open, IBKR MCP snapshots.
ATM calls, three symbols, three tenors. Gates written before the run.

## The unit question V47 left open is now settled

V47 found IBKR's `OPTION_IMPLIED_VOLATILITY` reporting 6.2% where the vendor
files said 99.2% — a factor of 16.0 — and hypothesised sqrt(252) = 15.87 but
refused to adopt it, on the grounds that **a factor reproducing one number is a
coincidence until it reproduces an independent one**.

It now reproduces on two independent fields at once. The snapshot API returns
both encodings, labelled:

| field | daily | annual | ratio |
|---|---|---|---|
| `historical-vol` (SOXL) | 0.0945955 | 1.5016570 | **15.8745** |
| `implied-vol-underlying` (SOXL) | 0.0662518 | 1.0517142 | **15.8745** |

sqrt(252) = 15.87451. Both to five significant figures, on a field with no
options in it (`historical-vol`) and one derived entirely from them. **V47's
hypothesis is confirmed and its Part B is unblocked** — the historical series
needs multiplying by sqrt(252), and the daily/annual pair is served explicitly
so no correction has to be guessed.

*Verified from the API response, not inferred.*

## Gates, all four passed

| gate | threshold | result | |
|---|---|---|---|
| C1 | SOXL ATM IV in 50-200% | 96.0 / 108.4 / 119.4% | PASS |
| C2 | ratio ~2.97 proportional vs ~3.75 additive | 2.79-2.82 | proportional |
| C3 | round trip near V43's 18.5 / 8.0 / 2.9 | 20.1 / 7.5 / 3.3 | PASS |
| C4 | own Black-Scholes vs IBKR's IV field | agree, no sqrt(252) | PASS |

C3 is the notable one: **V43's spread surface replicates on a third independent
session**, all three symbols within 1.5 volatility points.

## Finding 1 — the ratio is flat across tenors, and it is not 2.97

Using IBKR's own midpoint IV, which handles the dividend yield that SOXX and SMH
pay and SOXL does not:

| tenor | SOXL | SOXX | SMH | SOXL/SOXX | SOXL/SMH |
|---|---|---|---|---|---|
| 9d | 96.25% | 34.52% | 29.84% | **2.788** | 3.226 |
| 30d | 106.07% | 37.68% | 31.89% | **2.815** | 3.326 |
| 79d | 108.99% | 38.59% | 34.84% | **2.824** | 3.129 |

**Flat to within 0.036 across a 9-to-79-day span.** That is the question #4 was
asked and the answer is yes: the proportional identity holds along the term
structure, and the additive alternative at 3.75 is nowhere near.

But the level is **2.81, not the 2.97 V47 measured five days earlier**, and not
the 2.964 the realised 30-day vols imply. Implied leverage is priced *below*
delivered leverage, and the estimate moves day to day by more than #2 can bear.

## Finding 2 — this weakens #2's positive result

#2 derived the index's implied vol as SOXL's divided by 2.97. Dividing by 2.81
instead raises the derived implied and shrinks the edge:

| ratio used | derived index implied | fwd realised | edge | net vs SMH's ~3 |
|---|---|---|---|---|
| 2.97 (V47) | 35.6% | 39.3% | +3.64 | +0.74 |
| **2.81 (here)** | **38.2%** | 39.3% | **+1.1** | **−1.8** |

The +0.74 that #2 reported as "clears, by 0.22 standard errors" does not survive
a ratio measured on a different day. **#2's edge is uncertain by roughly the size
of the thing it was clearing.**

## Finding 3 — the 30-day tenor is the worst one to trade

Round trip in volatility points, IV at ask minus IV at bid:

| symbol | 9d | 30d | 79d |
|---|---|---|---|
| SOXL | 11.3 | **20.1** | 9.6 |
| SOXX | 7.0 | **7.5** | 2.8 |
| SMH | 3.2 | **3.3** | 1.6 |

Every symbol is cheapest at the long tenor and dearest at 30 days — SOXL's
79-day round trip is **less than half** its 30-day. Consistent with V28's
term structure of spreads (4.9 points at 91-365 DTE against 8.1 at 22-45).

Every structure priced in this project was priced at 30-45 days, which is the
most expensive point on the curve.

## What this does not establish

One session, one moment, ATM calls only, three tenors. The ratio's day-to-day
variation is inferred from two points (2.97 on 2026-08-28, 2.81 today) and needs
a series, not a second snapshot. The tenor spread pattern is one observation per
cell with no error bar.
