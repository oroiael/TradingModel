# The put: when is it worth enough, and do we ever collect it?


## The short answer

The put is **already worth enough** at the moment the re-strike loss happens. It is not a sizing problem or a strike problem. The rule simply realises it at the wrong time: the share loss is booked the day the call assigns, at the low, while the put is held on to its own expiry weeks later, by which point the stock has usually bounced and the put is worth far less.


## The April 2025 case, step by step

| | |
|---|---|
| 2025-02-24 | Bought 21 puts, strike **$27.00**, 81 DTE, at $4.40 — **$9,240** |
| 2025-02-18 → 04-25 | SOXL falls 29.12 → 12.33; the call is re-struck down every Monday |
| 2025-04-25 | Called away at **$9.00**. Share lot realises **−$42,252** |
| *same instant* | Puts held were worth **$35,209** of intrinsic — **83% of the loss** |
| 2025-05-16 | Put expires. SOXL has rebounded to **$18.39**; it cash-settles for **$18,081** |

The hedge did its job and then gave most of it back while we watched. Between the assignment and the put's expiry SOXL rose from $12.33 to $18.39, and roughly **$17,000 of protection that existed on the day we needed it** evaporated before we were allowed to touch it. Across all of 2025 the puts returned $19,186 — **45%** of the share loss they were sitting against, not the 83% they were worth at the moment of impact.

This is a clock mismatch, not a hedging failure. The call resolves **weekly** and crystallises the share loss at whatever Friday's price happens to be. The put resolves **quarterly**. The hedge cannot respond to the event that did the damage.


## Testing the obvious fix

Once the shares are called away the put is an unhedged long option protecting nothing. This variant sells it at market that day and buys a fresh one when the share position is re-established. (Selling, not exercising — exercising throws away the remaining time value.)

| variant | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| hold the put to expiry (the rule) | -39.7% | -16.6% | -33.5% | -37.6% | -11.4% |
| sell the put once the shares are gone | -35.1% | -24.3% | -31.5% | -8.6% | -12.9% |
| buy & hold SOXL | -86.2% | +227.1% | -6.5% | +45.4% | +278.8% |

And on the put leg alone:

| year | put P&L, held to expiry | put P&L, sold when flat | improvement |
|---|---:|---:|---:|
| 2022 | $+41,973 | $+41,715 | **$-258** |
| 2023 | $-64,495 | $-68,985 | **$-4,490** |
| 2024 | $-26,197 | $-26,589 | **$-392** |
| 2025 | $-28,750 | $-20,184 | **$+8,566** |
| 2026 | $-54,935 | $-49,617 | **$+5,318** |

In 2025 and 2026 this recovers roughly $23,000 a year of hedge value that the hold-to-expiry rule was throwing away. 2023 is slightly worse — in a straight-up year the puts you sell early were going to expire worthless anyway, and you pay the spread to find that out.


## What this does and does not fix

- It **does** stop the hedge decaying unwatched after it has already paid off. That is worth 8-46 points depending on the year.
- It does **not** address the cost of the insurance itself: a just-out-of-the-money put on a 3x ETF still runs ~17% of spot per ~84 days.
- It does **not** stop the re-strike selling the recovery. That is the sticky-strike question, measured separately in `STICKY.md`.
- Selling on the day of assignment is a mechanical rule, not an attempt to time the bottom. No variant here looks ahead.
