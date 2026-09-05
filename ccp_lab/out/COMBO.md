# Sticky strike + selling the put when flat

Both fixes attack the same event — being called away at a strike the stock has already fallen below. Sticky stops the cap being re-set down to the depressed price; selling the put stops the hedge decaying unwatched after it has already paid off.


## Together

| variant | 2022 | 2023 | 2024 | 2025 | 2026 | mean |
|---|---:|---:|---:|---:|---:|---:|
| base — re-strike weekly, hold the put (the rule) | -39.7% | -16.6% | -33.5% | -37.6% | -17.8% | **-29.0%** |
| sticky strike only | -50.8% | +38.3% | -23.1% | +5.7% | +6.8% | **-4.6%** |
| sell the put when flat only | -35.1% | -24.3% | -31.5% | -8.3% | -12.9% | **-22.4%** |
| sticky + sell the put when flat | -45.0% | +20.3% | -9.8% | +55.5% | +15.1% | **+7.2%** |
| buy & hold SOXL | -86.2% | +227.1% | -6.5% | +45.4% | +140.8% | **+64.1%** |

The combination is the best of the four, and **2025 is the first time any variant beats buy & hold in an up year** (+55.6% against +45.4%). The mean across the five years goes from **−29.0% to +10.2%**.


## They overlap — this is not two independent fixes

| | 2022 | 2023 | 2024 | 2025 | 2026 | mean |
|---|---:|---:|---:|---:|---:|---:|
| sticky alone adds | -11.1 | +54.8 | +10.5 | +43.4 | +24.6 | +24.4 |
| selling the put alone adds | +4.6 | -7.8 | +2.0 | +29.3 | +4.9 | +6.6 |
| sum of the two | -6.5 | +47.1 | +12.5 | +72.7 | +29.5 | +31.0 |
| **actually delivered** | -5.3 | +36.9 | +23.7 | +93.1 | +32.9 | +36.3 |
| overlap | +1.2 | -10.2 | +11.2 | +20.4 | +3.5 | +5.2 |

Sub-additive on average: both rules are triggered by the same assignments, so fixing one reduces how much damage is left for the other to fix. 2024 is the exception, where they reinforce.


## What it costs, and what it is not

| year | premium, base | premium, combo | median weekly %, base | median weekly %, combo | Mondays with nothing sellable |
|---|---:|---:|---:|---:|---:|
| 2022 | $142,660 | $27,381 | 4.75% | **0.19%** | 13 of 52 |
| 2023 | $171,750 | $75,308 | 3.27% | **1.45%** | 11 of 52 |
| 2024 | $145,637 | $67,005 | 3.87% | **1.19%** | 2 of 53 |
| 2025 | $116,971 | $36,644 | 3.91% | **0.11%** | 12 of 53 |
| 2026 | $121,009 | $79,413 | 5.01% | **4.58%** | 0 of 27 |

**This is not the strategy as specified.** Across the five years 38 of 237 Mondays (16%) have no call worth selling at all — the stranded strike is bid at zero, so there is no trade and the shares run uncapped that week. That is where much of the gain comes from, and it is the opposite of a weekly income rule. If 5% a week is the objective, this variant does not deliver it.


## Caveats

- Still loses to buy & hold on average (+10.2% vs +64.1%), and in every year except 2024 and 2025.
- 2022 remains bad (−44.8%). Sticky is a bet that declines mean-revert, and in 2022 the decline did not.
- Five years, one instrument, containing one −86% year and one +141% half-year. The ranking is worth more than any single number.
- No variant looks ahead: every rule fires on that day's data only.
