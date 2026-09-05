# The 30% put roll-down, priced three ways


## The methodology, stated up front

Every result below rests on one assumption: **what a deep in-the-money put can actually be sold for.** Those contracts are illiquid — across the exits in this test the median quoted spread is **10.8%**, the 75th percentile **19.4%**, and the bid sits **below intrinsic in 64% of cases**. So the exit is modelled three ways and the answer is a range, not a number.

| model | rule | rationale |
|---|---|---|
| **generous** | the mid | assumes a limit order fills at the midpoint of a 10-20% spread. Optimistic, and more so in size. |
| **central** | better of the bid, or exercise-and-rebuy | exercising captures intrinsic and re-buying the shares restores the position; the cost is a **stock** round trip ($0.02/share: two commissions plus about a cent of spread), and SOXL is liquid where the option is not. Never more than arbitrage allows, never less than a rational holder would accept. |
| **worst** | the bid, no floor | you always hit the bid, even where it is ~9% below intrinsic and any rational holder would exercise instead. A genuine worst case rather than a likely one. |

The central model is the one to reason from. The other two bound it.


## Results

| config | 2022 | 2023 | 2024 | 2025 | 2026 | mean |
|---|---:|---:|---:|---:|---:|---:|
| take assignment / **generous** | -40.9% | +53.3% | +9.1% | +126.9% | +43.4% | **+38.3%** |
| take assignment / **central** | -42.0% | +50.4% | +2.1% | +111.9% | +26.1% | **+29.7%** |
| take assignment / **worst** | -46.9% | +46.1% | -3.3% | +105.7% | +16.5% | **+23.6%** |
| roll the call (combo) / **generous** | -45.4% | +0.3% | -32.2% | +77.7% | +80.8% | **+16.2%** |
| roll the call (combo) / **central** | -46.3% | +0.3% | -33.5% | +64.3% | +77.5% | **+12.5%** |
| roll the call (combo) / **worst** | -50.6% | +0.3% | -34.8% | +63.7% | +90.6% | **+13.8%** |
| buy & hold SOXL | -86.2% | +227.1% | -6.5% | +45.4% | +278.8% | +91.7% |

**The exit assumption is worth about 15 points of mean return** — from +38.3% on generous fills to +23.6% on worst-case fills. That band is the honest uncertainty on this idea. Even at the worst end it beats the rule as written (−29.0%) by a wide margin, so the direction survives; the magnitude is not knowable to better than ~15 points.


## Rolling the call makes this *worse*, and the reason is structural

| config | 2022 | 2023 | 2024 | 2025 | 2026 | total |
|---|---:|---:|---:|---:|---:|---:|
| put exits, take assignment | 14 | 25 | 21 | 6 | 16 | **82** |
| put exits, roll the call (combo) | 9 | 0 | 2 | 3 | 1 | **15** |

Rolling the call cuts put exits from 82 to 15 across the five years, and to **zero in 2023** — which is why all three exit models give an identical +0.3% that year: no put was ever sold, so the pricing model had nothing to price.

The mechanism is a coupling nobody designed. `sell the put when flat` is **triggered by assignment**. Roll the call and you are never flat, so the hedge is never harvested — the rule that was recovering the put's value simply stops firing. Rolling and monetising the put are **substitutes here, not complements**: rolling protects the share position, and in doing so it removes the trigger that was collecting on the insurance.


## What still has to be said

- Every configuration still loses to buy & hold (+91.7%). None of this makes the structure competitive with owning the shares.
- 2022 is negative in all six configurations. Nothing tested rescues a sustained 86% decline.
- The 30% trigger fires 23 times in five years. That is a small sample and the threshold is not identifiable from it — see `PUT_TRIGGER.md`.
- None of this is the strategy as specified: no 5% weekly premium, and the put is traded, which the original rule forbids.
