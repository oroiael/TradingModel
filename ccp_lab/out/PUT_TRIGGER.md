# What should trigger selling the put?


## What the shipped rule actually does

Nothing clever. The trigger is **position state, not price**: when the shares are called away the put is protecting nothing, so it is sold. There is no percentage-loss test, no moneyness test and no profit target anywhere in it. That was deliberate — it is the one condition that needs no parameter — but it is obviously not the only choice.


## The alternative: roll the put down when it is deep in the money

A put far in the money is nearly all intrinsic. There is no optionality left to wait for, only a rebound that can take the gain away. Selling it and immediately buying a fresh ~90-day just-OTM put harvests the gain and resets the insurance at the current level in one move. The trigger is measured on the day; nothing looks ahead.

| trigger | 2022 | 2023 | 2024 | 2025 | 2026 | mean |
|---|---:|---:|---:|---:|---:|---:|
| none (position-state only) | -45.0% | +20.3% | -9.9% | +55.5% | +15.1% | **+7.2%** |
| put 10% in the money | -61.5% | +65.8% | -11.6% | +85.9% | +9.5% | **+17.6%** |
| put 20% in the money | -56.3% | +42.8% | +1.5% | +98.2% | +8.8% | **+19.0%** |
| put 30% in the money | -42.0% | +50.4% | +2.1% | +111.9% | +26.1% | **+29.7%** |
| put 40% in the money | -31.9% | +63.1% | -5.2% | +133.8% | +15.1% | **+35.0%** |
| put 50% in the money | -41.8% | +20.3% | -5.0% | +65.0% | +15.1% | **+10.7%** |

**Yes, it makes a major difference — and no, you cannot use this table to pick a threshold.** Two things have to be said before anyone acts on it.


## Caveat 1: the fills were fantasy on the first pass

The first version priced these exits at the model mark. Checked against the vendor's own end-of-day quotes, those marks sat a median **+11.8% above the bid**, on contracts whose median quoted spread is **10%** — some near 20%. Deep in-the-money options on a 3x ETF are illiquid and quoted very wide; you are not getting the mid, let alone better.

Every put exit in this lab now sells at the **bid**, floored at intrinsic (exercising is always available instead). That correction alone cost 6-8 points of mean return. Any version of this idea that does not model the exit spread is not measuring anything real.


## Caveat 2: the threshold is not identifiable from five years

| trigger | 2022 | 2023 | 2024 | 2025 | 2026 | events |
|---|---:|---:|---:|---:|---:|---:|
| put 10% in the money | 15 | 7 | 11 | 7 | 3 | **43** |
| put 20% in the money | 15 | 4 | 8 | 7 | 2 | **36** |
| put 30% in the money | 9 | 2 | 6 | 5 | 1 | **23** |
| put 40% in the money | 7 | 2 | 2 | 5 | 0 | **16** |
| put 50% in the money | 3 | 0 | 1 | 3 | 0 | **7** |

At the 40% trigger the whole result rests on **16 events across five years**, none of them in 2026. And the best threshold moves every year — 40, 10, 30, 40, 30 — with 14 to 69 points between the best and worst choice within a single year. There is no stable optimum here, only noise with a trend through it.

What *is* robust: **every threshold beats the position-state trigger on the mean.** The direction — do not sit on a deep in-the-money hedge and wait for expiry — survives every cut. The specific number does not, and a tight trigger is actively dangerous: 10% is the worst choice in 2022 (−61.5%) and the best in 2023 (+65.8%).


## The honest recommendation

- Use a **wide** trigger (30-40% in the money) if you use one at all: it fires rarely, only when the put has genuinely done its job, and it is the region that survives 2022 least badly.
- Model the exit at the bid. This idea lives or dies on the spread.
- Treat any single number in the first table as unreliable. Five years of one 3x ETF, 16-44 events, and one −86% year is not enough to fit a threshold on.
