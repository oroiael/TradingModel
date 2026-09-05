# Rolling the call instead of taking assignment

Same rule, same data, same put. The only change: on expiry day an in-the-money call is **bought back** rather than allowed to assign, and the far leg of the same combo order sells the following week's call (strike never below the old one, premium targeted at 5% of spot). Where the net debit cannot be funded from cash, the shares are still assigned and that is counted.


## Headline

| variant | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| take assignment (baseline) | -39.7% | -16.6% | -33.5% | -37.6% | -11.4% |
| buy back Friday, re-write Monday | -45.5% | -10.3% | -30.1% | +4.0% | +19.9% |
| roll as one combo order | -37.5% | -0.0% | -40.7% | +0.3% | +57.5% |
| buy & hold SOXL | -86.2% | +227.1% | -6.5% | +45.4% | +278.8% |

Rolling is a real improvement in three of the five years — 2025 and 2026 swing by more than 40 points — and it is not a fix. The rule still loses money in 2022 and 2024, and still trails buy & hold in every year except the crash.


## What the rolls cost

| year | rolled | assigned anyway | paid to buy back | received on the far leg | net |
|---|---:|---:|---:|---:|---:|
| 2022 | 19 | 8 | $51,496 | $32,110 | $-19,386 |
| 2023 | 24 | 13 | $90,978 | $56,684 | $-34,294 |
| 2024 | 23 | 10 | $83,871 | $46,810 | $-37,062 |
| 2025 | 24 | 11 | $81,914 | $52,150 | $-29,765 |
| 2026 | 15 | 5 | $111,538 | $67,020 | $-44,517 |
| **all** | 105 | 47 | **$419,798** | **$254,774** | **$-165,023** |

Rolling does not make the loss go away — it **defers** it. The buyback pays the intrinsic that assignment would have surrendered, and the far leg only partly refunds it. What rolling actually buys is staying continuously long: the shares are never sold at the strike and never repurchased at Monday's higher open.


## How much cash does rolling need?

A buyback that cannot be funded is still an assignment, and the reinvest-everything rule leaves almost no cash on Friday. Holding back a share of equity fixes that:

| cash reserve | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| 0% | -37.5% (8 forced) | -0.0% (13 forced) | -40.7% (10 forced) | +0.3% (11 forced) | +57.5% (5 forced) |
| 5% | -41.3% (4 forced) | -1.0% (6 forced) | -27.1% (6 forced) | -7.5% (7 forced) | +51.6% (3 forced) |
| 10% | -41.1% (3 forced) | -11.0% (5 forced) | -23.4% (3 forced) | -7.7% (2 forced) | +29.5% (2 forced) |
| 20% | -37.4% (1 forced) | -11.4% (2 forced) | -18.2% (0 forced) | -7.7% (1 forced) | +13.2% (1 forced) |

The reserve reliably removes the forced assignments, and barely moves the return. The funding constraint was real but it was never the thing driving the result.

