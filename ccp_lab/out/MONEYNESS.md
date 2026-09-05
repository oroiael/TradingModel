# Writing the call in the money


## The idea, and the trap in it

A covered call is synthetically a **short put at the same strike**. Writing deep in the money is therefore selling a deep out-of-the-money put: you are called away almost every week, you keep only the time value, and your breakeven sits at `strike − time value`.

That does give real protection — but note what assignment actually is. **You are called away when the stock stays up.** If it crashes through the strike you are *not* called away: you keep a falling stock and lose with it, one for one, to zero. Being called out every week is what happens when things go well, not a shield against them going badly.


## On paper, deep in the money looks excellent

| strike | called | median time value | mean/wk | geo/wk | weekly σ | worst week | best week |
|---|---:|---:|---:|---:|---:|---:|---:|
| -40% | 98% | 0.143% | +0.335% | +0.331% | 0.96% | -8.1% | +5.4% |
| -30% | 97% | 0.130% | +0.411% | +0.405% | 1.09% | -8.1% | +5.4% |
| -20% | 94% | 0.184% | +0.177% | +0.140% | 2.55% | -27.2% | +5.2% |
| -15% | 87% | 0.559% | -0.037% | -0.100% | 3.34% | -27.2% | +6.2% |
| -10% | 78% | 1.316% | -0.155% | -0.265% | 4.46% | -29.2% | +6.8% |
| -5% | 67% | 2.546% | -0.250% | -0.463% | 6.18% | -33.6% | +8.7% |
| +0% | 51% | 4.405% | -0.160% | -0.497% | 7.80% | -35.5% | +11.5% |
| +5% | 36% | 2.647% | -0.107% | -0.590% | 9.39% | -38.5% | +14.7% |

**The risk control is real and it works.** Weekly volatility falls from **9.39%** at 5% out of the money to **1.09%** at 30% in the money, and the worst single week improves from **-38.5%** to **-8.1%**. Assignment rises to 97%. Everything the idea promises, it delivers.


## And then you have to cross the spread

| strike | mark (optimistic) | less the measured half-spread | at the bid |
|---|---:|---:|---:|
| -40% | +13.9% | -37.0% | -32.9% |
| -30% | +18.0% | -29.7% | -25.7% |
| -20% | +5.4% | -28.2% | -20.6% |
| -15% | -3.7% | -28.1% | -17.0% |
| -10% | -8.3% | -25.2% | -12.8% |
| -5% | -13.6% | -25.2% | -13.8% |
| +0% | -12.1% | -19.3% | -10.3% |
| +5% | -10.9% | -15.9% | -9.1% |
| buy & hold | +91.7% | +91.7% | +91.7% |

**The ranking inverts completely.** On my marks, 30% in the money is the best strike tested (+18.0%) and 5% out of the money the worst (−10.9%). Pay the measured half-spread and 30% ITM becomes the *worst* (−29.7%) and 5% OTM the least bad (−15.9%). At the bid, same ordering.

The reason is arithmetic. A 30%-in-the-money weekly call carries a median time value of **0.13% of spot** — that is the entire prize — while those contracts quote a **5.1% median spread, 12.3% at the 75th percentile**. On a $17 premium the spread is dollars and the time value is cents. **The bid sits below intrinsic in 53% of weeks**: you would be selling the call for less than the stock is already worth above the strike, which is worse than simply selling the stock.


## Answering the question directly

- **Does it work in the money?** On mid-market marks, yes, strikingly. At any realistic fill, no — it is the worst region of the curve, and the deeper you go the worse it gets.
- **Does being called out almost every week manage the danger?** For variance and for the ordinary tail, genuinely yes. But it does not remove the crash case, because a crash is precisely the scenario in which you are *not* called away.
- **Is that a good trade?** Not at these spreads. You are paying a 5-12% transaction cost to collect 0.13% of time value. The risk reduction is real and you are over-paying for it by an order of magnitude.

If this structure is worth pursuing at all it is at strikes near or above the money, where the premium is large enough to survive the spread — and even there every configuration in this lab still loses to simply holding the shares (+92%).


## The out-of-the-money side, sold at the bid

| strike | 2022 | 2023 | 2024 | 2025 | 2026 | mean |
|---|---:|---:|---:|---:|---:|---:|
| +0% | -70.1% | +45.2% | -41.3% | -37.6% | +52.4% | **-10.3%** |
| +2% | -71.7% | +42.1% | -42.8% | -42.7% | +71.0% | **-8.8%** |
| +5% | -74.3% | +36.1% | -45.1% | -40.2% | +77.9% | **-9.1%** |
| +10% | -76.0% | +63.9% | -42.2% | -40.2% | +100.8% | **+1.3%** |
| +20% | -78.4% | +106.3% | -33.9% | -46.4% | +127.3% | **+15.0%** |
| +30% | -77.8% | +128.7% | -29.2% | -43.0% | +155.7% | **+26.9%** |
| **buy & hold** | -86.2% | +227.1% | -6.5% | +45.4% | +278.8% | **+91.7%** |

**The further out you write, the better it gets — and the limit of that is not writing at all.** The mean improves monotonically from -10.3% at the money to +26.9% at 30% out, and buy & hold (+91.7%) sits above every one of them. Sold at a price anyone would actually fill, **the weekly call is a net cost at every strike tested**.

The one exception is the crash. In 2022 the call *helped*: -70.1% at the money against buy & hold's -86.2%, and there the ordering reverses — closer to the money cushions more, because the premium is the cushion. That is the whole trade in one line: **you are paid to give up the upside, and the payment only covers you in the year the upside does not come.**


### 2026, the same sweep by start month

| strike | Jan | Feb | Mar | Apr | May | Jun |
|---|---:|---:|---:|---:|---:|---:|
| +0% | +52% | +28% | +13% | +28% | +4% | -6% |
| +2% | +71% | +46% | +24% | +38% | +7% | -6% |
| +5% | +78% | +43% | +23% | +45% | +8% | -8% |
| +10% | +101% | +58% | +33% | +54% | +5% | -13% |
| +20% | +127% | +78% | +66% | +88% | +6% | -20% |
| +30% | +156% | +95% | +89% | +122% | +3% | -25% |

Monotonic in five of the six months and **reversed in June** — the month SOXL fell. That is the tell that the monotonicity is a directional bet on the underlying, not an edge in the option: in rising months less cap is better, in the falling month more cap is better. A single 2026 figure for any of these rows is one draw from that spread.

