# V27 — Can the range be harvested?

Question: the V26 ladder showed a 250 bp/day band. Can we get it?

    python3 band_lab/v2_dev/range_census.py
    python3 band_lab/v2_dev/vol_premium.py

## First: the 250 bp is not an opportunity

It is the width of an error bar. It is the difference between filling at the
best price inside every minute and the worst. Buying the low of a minute
requires knowing the minute's low before the minute is over. The number measures
what the data cannot see, not money lying on the ground.

## But the range itself is real and it is enormous

SOXL, 1,147 sessions, 2022-01-03 → 2026-07-30:

| | |
|---|---|
| average session high-to-low range | **8.07%** |
| average path length (every 1-minute move added up) | **71.83%** |
| average \|open-to-close\| move | 4.24% |
| efficiency (\|net\| / path) | **5.87%** |

The price travels 71.8% of distance in a day and ends up 4.2% from where it
started. **94% of the motion cancels itself out.** That cancelling motion is
what "harvest the volatility" means, and it is genuinely there.

## The wall: what it costs to reach

Perfect foresight — catch every single move, long and short, at that horizon:

| horizon | trades/day | gross/day | friction/day | net/day | avg move | **break-even accuracy** |
|---|---|---|---|---|---|---|
| 1 min | 388.6 | 7,183 bp | 2,604 bp | 4,579 bp | 18 bp | **68.1%** |
| 2 min | 194.3 | 5,094 bp | 1,302 bp | 3,793 bp | 26 bp | **62.8%** |
| 5 min | 77.7 | 3,256 bp | 521 bp | 2,735 bp | 42 bp | **58.0%** |
| 15 min | 25.9 | 1,872 bp | 174 bp | 1,698 bp | 72 bp | **54.6%** |
| 30 min | 13.0 | 1,344 bp | 87 bp | 1,257 bp | 104 bp | **53.2%** |
| 60 min | 7.0 | 986 bp | 47 bp | 939 bp | 141 bp | **52.4%** |
| 1 day | 1.0 | 424 bp | 7 bp | 417 bp | 424 bp | **50.8%** |

**Every directional signal measured anywhere in this repository comes in at
49–51%.** The dip (48.3% vs a 48.5% baseline). Momentum at every lookback
(47–51%). Reach +X before −X from any minute (49.2–50.0%). The best of 35
weekday × hour cells (57.8%, zero survive multiple-comparison correction).

What each accuracy level is worth, net of friction, bp/day:

| horizon | 50% | 51% | 52% | 55% | 60% | 70% |
|---|---|---|---|---|---|---|
| 1 min | −2604 | −2460 | −2317 | −1886 | −1169 | +266 |
| 5 min | −521 | −456 | −391 | −196 | +130 | +780 |
| 60 min | −47 | −27 | −7 | +52 | +150 | +347 |
| 1 day | −7 | +2 | +10 | +36 | +78 | +163 |

The range is not the constraint. **Direction is.** Trading faster raises the
number of chances and the accuracy bar together, and friction wins that race
early.

## The one direction-free harvest: own gamma

Delta-hedging an option forces you to sell into strength and buy into weakness
mechanically. You never have to call direction. Your P&L is approximately
`0.5 × Γ × S² × (realised variance − implied variance)`. So there is exactly one
thing to be right about: **is implied vol below what the stock actually does?**

Measured — 1,117 trade dates, ~30-day ATM implied vol vs the following 30
sessions of realised vol:

| | mean | median |
|---|---|---|
| implied vol the market charged | **98.6%** | 95.4% |
| realised, close-to-close — all of it | **110.4%** | 103.2% |
| realised, 1-minute path — **the part you can hedge** | **81.0%** | 75.5% |

### Where the variance lives

| | vol | share of variance | |
|---|---|---|---|
| total, close to close | 116.6% | 100% | |
| inside the day session | 84.4% | **52%** | hedgeable |
| **overnight, market closed** | 80.4% | **48%** | **not hedgeable** |

**Nearly half of SOXL's variance happens when the market is shut.**

### The gamma buyer's edge

| | mean | median | % of days > 0 |
|---|---|---|---|
| against all realised vol | **+11.8%** | +6.7% | 63% |
| against the part you can hedge | **−17.6%** | −19.2% | **12%** |

An intraday delta-hedger pays 98.6 and collects 81. That loses on 88% of start
dates. The entire positive premium is in the overnight gap, and the overnight
gap cannot be delta-hedged — by definition, nothing trades.

### And then the hedging bill

| hedge frequency | friction | per year on hedged notional |
|---|---|---|
| 1×/day | 3 bp/day | 8% |
| 4×/day | 13 bp/day | **34%** |
| 13×/day | 44 bp/day | 110% |
| 78×/day | 261 bp/day | 658% |

A vol edge of a few points on a 70–100% vol underlying is worth a few hundred bp
a year. Hedging four times a day costs 34% a year. The friction is not a detail;
it is the whole trade.

## By year, because 4.5 years is one regime

| year | implied | realised (cc) | edge | % days RV>IV |
|---|---|---|---|---|
| 2022 | 112.3% | 130.4% | +18.1% | 82% |
| 2023 | 83.6% | 82.2% | −1.4% | 48% |
| 2024 | 90.2% | 102.4% | +12.2% | 61% |
| 2025 | 96.2% | 108.7% | +12.6% | 51% |
| 2026 (114 dates) | 125.4% | 149.8% | +24.5% | 84% |

## Answer

1. **The 250 bp cannot be harvested.** It is measurement uncertainty.
2. **The 71.8%/day of path is real** and cannot be reached directionally —
   every horizon needs 51–68% accuracy and nothing measured here exceeds 51%.
3. **Gamma is the only direction-free route, and intraday it loses.** The market
   charges 98.6 vol; the intraday path delivers 81. Negative on 88% of dates.
4. **The only positive volatility premium in this data is overnight** — 48% of
   total variance, realised 110.4% against 98.6% implied. Owning it means
   holding options through the close unhedged. That is a real trade with a real
   historical edge in this sample, and it is a completely different business
   from anything the band does: a levered overnight gap bet, sized so a 2022 or
   an April 2025 does not end the account.

## The honest footnote about market making

The business that harvests range without predicting anything is being **paid**
the spread instead of paying it. This account pays 5.7 bp of spread per round
trip, 6.5 times a day — about 37 bp/day handed to whoever is on the other side.
That is not available through a retail IBKR account: it needs queue priority,
exchange rebates, and the capacity to survive adverse selection (you get filled
on the bid precisely when the price is about to fall). It is named here for
completeness, not as a proposal.

## Methodology note that changed a conclusion

An open-to-close variance estimator was tried first and dropped. It uses one
observation per day, so its **mean** is set by a handful of huge trending
sessions: the ratio of *mean* 1-minute realised variance to *mean* squared
open-to-close return is 0.86, while the **median** per-day ratio is 2.11.
Reporting the first would have claimed intraday moves trend. They do not — on a
typical day intraday chop delivers about twice the variance of the net move,
which is what the band strategy assumed and one of the few of its premises that
holds up.
