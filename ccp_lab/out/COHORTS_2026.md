# Start-date cohorts — 2026

Each cell is an independent $100,000 account opened on the first trading Monday on or after that month's 1st, run to **2026-07-02** and liquidated. Same rules, same data, same fills; only the start date differs.


> **2026 runs to 2026-07-02, not to the end of the price tape.** The option chains stop there. Earlier versions of this lab ran on to 2026-07-30, leaving the position unwritten and unhedged through a **−36.4%** tail and liquidating into it. Every 2026 figure quoted before this correction was wrong, benchmark included.


## Every permutation, every start month

| strategy | Jan | Feb | Mar | Apr | May | Jun | median | worst | best | spread |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| the rule as written | -11% | -23% | -32% | +1% | -12% | -19% | **-16%** | -32% | +1% | **32 pts** |
| roll the call | +57% | +42% | +20% | +40% | -8% | -9% | **+30%** | -9% | +57% | **66 pts** |
| sticky strike | +18% | +6% | -3% | +6% | -11% | -22% | **+1%** | -22% | +18% | **41 pts** |
| sell put when flat | -13% | -12% | -21% | -13% | -6% | -6% | **-12%** | -21% | -6% | **15 pts** |
| sticky + sell put when flat | +15% | +5% | -0% | -6% | -0% | -9% | **-0%** | -9% | +15% | **24 pts** |
| sticky + sell put + 30% roll-down | +26% | +17% | -0% | -6% | -0% | -9% | **-0%** | -9% | +26% | **35 pts** |
| weekly flat, no put | +54% | +20% | +4% | +24% | -1% | -16% | **+12%** | -16% | +54% | **70 pts** |
| carry, no put (call only) | +52% | +16% | +2% | +23% | -1% | -15% | **+9%** | -15% | +52% | **67 pts** |
| buy & hold SOXL | +279% | +187% | +199% | +247% | +40% | -15% | **+193%** | -15% | +279% | **294 pts** |

## What this says

- **The start month is worth more than the rule.** The rule as written spans 32 points across start dates (-32% to +1%); the gap between the worst and best *permutation* at a fixed start is usually smaller than that.
- The best permutation beats buy & hold at 1 of 6 start months.
- A backtest quoting one start date for 2026 is quoting one draw from a distribution this wide. So is a live account: **an account opened in March and one opened in May are running the same rule and will not agree**, and neither is evidence about the rule.
- Ranking is more stable than level. Read the ordering of the rows, not the numbers in them.

## Which permutation wins, by start month

| permutation | start months where it is best |
|---|---:|
| roll the call | 4 of 6 |
| sell put when flat | 1 of 6 |
| sticky + sell put when flat | 1 of 6 |
| sticky + sell put + 30% roll-down | 1 of 6 |
| the rule as written | 0 of 6 |
| sticky strike | 0 of 6 |
| weekly flat, no put | 0 of 6 |
| carry, no put (call only) | 0 of 6 |

Note how badly a single annual figure represents this. A rule can be the best choice in most months and still look ordinary in a calendar-year backtest, because the calendar year is just the January cohort.

