# Weekly flat — no put, nothing held over a weekend

Buy at the 10:00 Monday high, write the weekly call at the 5% premium target, and on expiry either be called away at the strike or sell at the close. No protective put. Every week is a closed round trip.


## Results

| variant | 2022 | 2023 | 2024 | 2025 | 2026 | mean |
|---|---:|---:|---:|---:|---:|---:|
| the rule as written (put + carry) | -39.7% | -16.6% | -33.5% | -37.6% | -11.4% | **-27.8%** |
| carry, no put (call only) | -71.4% | +63.4% | -16.3% | -13.2% | +51.8% | **+2.8%** |
| WEEKLY FLAT, no put | -64.6% | +30.2% | -34.2% | -32.9% | +53.8% | **-9.5%** |
| weekly flat, no put, no call (control) | -85.4% | +226.6% | -6.5% | +47.3% | +280.2% | **+92.4%** |
| buy & hold SOXL | -86.2% | +227.1% | -6.5% | +45.4% | +278.8% | **+91.7%** |

Three things fall out of that table.

**Dropping the put is the single biggest lever in this whole lab.** The rule as written averages −27.8%; the same rule with no put and no other change averages +2.8%. Nothing else tested comes close to a 30-point swing.

**Being flat over the weekend is close to free.** The no-call control — buy Monday, sell Friday, every week, 236 round trips — returns +92.4% against buy & hold's +91.7%. Weekend gaps and the trading friction of a weekly round trip roughly cancel. So whatever the weekly-flat rule loses, it is not losing it on transaction costs or missed weekends.

**Adding the flat rule to the call makes it worse, not better** (+2.8% → −9.5%). Selling every Friday and re-buying at Monday's 10:00 *high* pays a bad entry 52 times a year instead of 25.


## The weekly distribution — why 65% winners still loses

| | |
|---|---:|
| weeks traded | 233 |
| called away | 107 (46%) |
| winning weeks | 64% |
| **median** week | **+3.49%** |
| **mean** week | **-0.12%** |
| weekly standard deviation | 8.51% |
| skew | -1.33 |
| best week | +18.5% |
| worst week | **-37.2%** |

The median week makes **+3.49%** and the mean week makes **-0.12%**. That gap is the entire story: a long left tail. The five worst weeks compound to **-80%**; the worst quartile on its own compounds to **−100%**.


## The edge is exactly the size of the variance drag

| | per week | annualised |
|---|---:|---:|
| arithmetic mean | -0.119% | -6% |
| **geometric mean** | **-0.514%** | **-23%** |
| variance drag | 0.395% | |
| σ²/2 | 0.362% | |

The drag (0.395%) and σ²/2 (0.362%) agree, and both are the same size as the arithmetic edge (-0.119%). **Writing weekly calls on a 3x ETF earns roughly what the volatility of a 3x ETF costs you to compound.** The premium is real and the drag eats it.


## And the edge is not measurable anyway

- t-statistic on the weekly mean: **-0.21** (about 2.0 is the usual bar).
- 95% confidence interval on the weekly mean: **-1.211% to +0.973%** — annualised, **-47% to +65%**.
- Weeks needed to reach t = 2 at this mean and volatility: **20520**, about **395 years**.

This is the answer to a live account disagreeing with a backtest. The true expectation of this rule cannot be pinned down from five years of data — the honest interval spans everything from ruinous to excellent. Two accounts running identical rules will land in different places, and neither result is evidence about the rule. Any backtest of this structure that quotes a single number, including every number in this lab, is quoting one draw from a distribution that wide.

