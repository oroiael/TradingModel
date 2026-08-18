# instrument_lab — what a weekly covered-call income strategy actually needs

```bash
python3 instrument_lab/screen.py   # the metric, on the repo's instruments
python3 instrument_lab/rank.py     # the screen + drivers + drift sensitivity
```

Turns the question around: instead of "does this work on SOXL", it asks **what
would an instrument have to look like for it to work**, and makes that a
computable screen requiring nothing but weekly closes.

## The identity everything rests on

A covered call returns `min(S_T, K) + premium`. Buy-and-hold returns `S_T`. So

```
covered call  -  buy & hold  =  premium  -  max(0, S_T - K)
```

exactly. The strategy beats holding **if and only if the premium exceeds the
payout you actually make.** The premium is the *risk-neutral* expectation of that
payout (drift = r); what you pay is the *real-world* expectation (drift = μ). To
first order:

```
edge  ≈  vega × (IV − RV)   −   delta × (μ − r) × T
         ^ variance risk premium   ^ the drift you hand over on the capped part
```

Two terms, both measurable. **Volatility appears in neither as a level** — it
scales the premium and the payout together. That is why "high vol = more income"
is a trap: it raises the gross and the cost in the same proportion.

## The screen

Premium priced at the instrument's **own realised vol** — i.e. assuming *zero*
VRP — so any positive edge is structural, earned from drift and shape before the
market pays a single vol point. Best strike chosen per instrument. 2022-01 → 2026-08.

| instrument | drift | vol | skew | best δ | OTM | premium/wk | **edge/yr** | assign |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FAS 3x financials | +21.7% | 56.9% | −0.13 | 0.30 | 4.55% | 1.442% | **+5.80%** | 27% |
| XLU 3x synthetic | +18.4% | 51.6% | −0.23 | 0.30 | 4.09% | 1.313% | **+3.96%** | 28% |
| SOXL 3x semis | +75.0% | 106.1% | +0.11 | **0.05** | 28.8% | 0.291% | +1.93% | 5% |
| financials 1x | +7.2% | 19.0% | −0.13 | 0.30 | 1.42% | 0.494% | +1.29% | 28% |
| XLU utilities | +6.1% | 17.2% | −0.23 | 0.30 | 1.29% | 0.449% | +0.72% | 31% |
| SPY S&P 500 | +12.4% | 16.3% | −0.12 | 0.25 | 1.56% | 0.333% | −0.76% | 26% |
| SPY 2x synthetic | +24.7% | 32.6% | −0.12 | 0.25 | 3.20% | 0.659% | −0.91% | 24% |
| semis 1x | +25.0% | 35.4% | +0.11 | 0.20 | 8.53% | 0.101% | −2.33% | 6% |

SOXL's "best" is a **5-delta** strike — the optimiser's way of saying *barely
write a call at all*. At that strike the income is 0.29%/week, which defeats the
purpose. Every well-behaved instrument optimises at **25–30 delta.**

## What drives it — one property neutralised at a time

| instrument | actual | drift removed | skew flipped | **cost of drift** | **cost of skew** |
|---|---:|---:|---:|---:|---:|
| SOXL 3x semis | −1.71% | +10.34% | +5.67% | **−12.05%** | **−7.38%** |
| semis 1x | −3.79% | +0.79% | −1.49% | −4.58% | −2.30% |
| SPY 2x | −1.52% | +2.24% | −3.15% | −3.76% | +1.63% |
| FAS 3x | +2.58% | +5.88% | +1.16% | −3.30% | +1.42% |
| SPY | −1.01% | +0.90% | −1.93% | −1.91% | +0.92% |
| XLU | +0.38% | +1.43% | −0.37% | −1.05% | +0.75% |

**Drift is the dominant destroyer, everywhere.** And SOXL is the only instrument
in the set where *skew also costs money* — everything else has the negative skew
a call seller wants, and is paid for it.

### The break-even, isolated

SPY's own return shape, shifted to different annual drifts, 20-delta:

| drift | 0% | +5% | +10% | +15% | +20% | +30% | +50% |
|---|---:|---:|---:|---:|---:|---:|---:|
| edge/yr | +0.90% | +0.14% | −0.63% | −1.46% | −2.40% | −4.53% | −10.25% |

**A weekly covered call breaks even at roughly +5–6% annual price drift and loses
beyond it.** SOXL ran at +75%.

## Adding a real variance risk premium

Edge once the market actually overprices the option, in vol points:

| instrument | RV | VRP +0pp | +2pp | +4pp |
|---|---:|---:|---:|---:|
| FAS 3x | 56.9% | +5.80% | **+10.85%** | +15.94% |
| financials 1x | 19.0% | +1.29% | **+6.37%** | +11.57% |
| XLU | 17.2% | +0.72% | **+5.81%** | +11.02% |
| SPY | 16.3% | −0.76% | **+3.94%** | +8.84% |
| semis 1x | 35.4% | −3.79% | +0.33% | +4.60% |
| SOXL 3x | 106.1% | +1.93% | +3.46% | +5.07% |

A vol point is worth roughly the **same dollars** on any instrument (ATM vega is
`S·√T·0.4`, near-independent of vol) — so as a fraction of the trade it is worth
far more on a low-vol name. And on a high-vol name you are pushed to a far-OTM
strike to escape the drift and tail problem, which collapses your vega and with
it your ability to collect any VRP at all. **SOXL gains least from the very thing
that makes the strategy work.**

Measured VRP at 7 days (`vol_anatomy`): SOXL **+2.5 vol points**, TQQQ **+0.7**.
Both turn negative beyond a week (SOXL −10.3pp at 30d, −15.9pp at 90d).

## The specification, in order of importance

| # | property | target | why |
|---|---|---|---|
| 1 | **annual price drift** | **< 6%**, ideally 0–5% | dominant term; every +10pp of drift costs ~0.8pp of edge at 16% vol and far more at high vol |
| 2 | **skew** | **≤ 0** | you want the fat tail on the side you keep, not the side you sold |
| 3 | **weekly VRP** | **positive, ≥ 2 vol points** | the only actual source of profit; worth ~+2.9pp of annual edge per vol point at 25–30δ |
| 4 | **realised vol** | **15–60%** | a scale, not an edge: enough for the premium to matter, low enough that a 25–30δ strike is not absurdly far out |
| 5 | **dividend yield** | **high is free** | not capped by the call, and ex-div drops lower the drift the call must overcome — it helps twice |
| 6 | **option liquidity** | tight weeklies | the spread is paid 52×/yr; `cc_lp_lab` measured 10.9% relative spread on SOXL weeklies |
| 7 | **strike** | **25–30 delta** | optimal for every well-behaved instrument here; ~25–30% assignment rate |

**The archetype:** a moderate-vol, high-dividend, negatively-skewed, low-drift
index or sector fund with liquid weeklies — utilities, staples, financials, broad
index. Not a levered single-sector growth fund in a boom.

**The anti-archetype is exactly SOXL**: highest drift in the set, the only
positive skew, near-zero VRP, and a vol so high that the only profitable strike
generates almost no income.

## How to screen a candidate

From 3–5 years of weekly closes alone: annualise the mean and stdev, compute skew,
set `K` at the 25–30 delta level under that vol, then compare `BS_call(K, RV)`
against the realised `mean(max(0, S·(1+r) − K))`. Positive difference = structural
edge before any VRP. `screen.profile()` also returns `vrp_req`, the implied-minus-
realised the instrument must earn just to break even — the single number to rank on.

## Caveats

* 2022–2026 was an exceptional equity bull market, so **every drift figure here is
  period-specific and biased high**. The ranking is more durable than the levels.
* Eight instruments, two of them synthetic re-scalings. Not a broad cross-section.
* VRP is measured on only SOXL and TQQQ; the SPY/XLU VRP columns are illustrative
  sensitivities, not measurements from their own chains.
* Price returns only. Dividends are additive to the holder and are noted, not modelled.
* Assumes the strike is set at a constant delta each week and held to expiry, which
  is the structure `cc_lp_lab` found least bad — not the two-strikes rule.


---

# Backtesting the weekly covered call on FAS and XLU — `fas_xlu_cc.py`

## The honest constraint, stated first

**This repo has no option chain for FAS or XLU.** Only SOXL and TQQQ. So the
premium cannot be observed and any "backtest" has to invent it.

I built a model-priced engine (`cc_backtest.py`) and tested it against the one
case where a real-quote answer exists. Result:

| SOXL, 2022-01→2026-07, 0.20δ, no put, with costs | real quotes | model |
|---|---:|---:|
| shares only, no calls | $271,740 | **$271,748** |
| 0.20δ re-struck weekly | $164,853 | $211,582 |

**The share leg reproduces to $8. The option leg does not** — the model is ~5 CAGR
points optimistic, because trailing realised vol places the delta-targeted strike
further out than the real contract sat, and vol was falling across this sample.
That error comes precisely from having no implied vol, which is exactly what FAS
and XLU lack. **So no model-priced P&L for FAS or XLU is reported here.**

What *can* be backtested from real prices is the whole strategy except the price
you were paid: at a delta-targeted strike, the weekly payout `max(0, S_T − K)` is
observable week by week. That gives the exact premium each instrument had to earn,
and the implied vol it had to be quoted at.

## The measured result — 0.30-delta weekly call, 2022-01 → 2026-07

No option data used anywhere in this table.

| instrument | vol | strike OTM | assigned | **premium needed/wk** | /yr | required IV | **required VRP** | worst week |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **FAS** 3x financials | 50.5% | 4.04% | 29.7% | **1.206%** | 62.7% | 49.1% | **−1.4pp** | 17.1% |
| **XLU** utilities | 17.2% | 1.26% | 33.9% | **0.502%** | 26.1% | 18.1% | **+0.9pp** | 5.8% |
| SPY S&P 500 | 15.7% | 1.17% | 31.2% | 0.470% | 24.5% | 16.9% | +1.2pp | 5.2% |
| SOXL 3x semis | 96.9% | 8.33% | 26.1% | 2.762% | 143.6% | 104.8% | **+7.9pp** | 41.1% |

**FAS breaks even at a NEGATIVE required VRP (−1.4pp)** — its options could have
been quoted *below* realised vol and the covered call would still have beaten
holding. **XLU needs +0.9pp and SPY +1.2pp**, both small and well inside the
3–4 vol points index options have historically carried. **SOXL needs +7.9pp**,
against a measured VRP of roughly zero.

## Edge over buy & hold, as a function of the one unknown

| instrument | income/wk | break-even VRP | VRP −2pp | **VRP 0** | **VRP +2pp** | VRP +4pp |
|---|---:|---:|---:|---:|---:|---:|
| **FAS** | 1.271% | **−1.4pp** | −1.6% | **+3.4%** | **+8.4%** | +13.5% |
| **XLU** | 0.457% | +0.9pp | −7.3% | −2.4% | **+2.8%** | +8.0% |
| SPY | 0.411% | +1.2pp | −8.0% | −3.1% | +2.0% | +7.2% |
| SOXL | 2.377% | +7.9pp | −25.0% | −20.0% | −15.0% | −10.0% |

## Which one is the income instrument

FAS produces the bigger number — **1.21% a week, ~63%/yr gross** — and is the only
name that clears at zero VRP. But its cost is violently concentrated: **the worst
single week cost 17.1% of spot, and the five worst weeks are 28.5% of the entire
four-and-a-half-year cost.** That is the SOXL failure mode in milder form.

XLU is the one that matches the brief of *steady weekly cash, smaller amounts*:

* **0.50% a week (~26%/yr gross)** at a 1.26%-OTM strike
* worst week costs **5.8%** of spot, not 17.1%
* top five weeks are **19.6%** of total cost, the least concentrated in the set
* assigned 34% of weeks, but the strike is only 1.26% away, so each assignment
  surrenders very little
* needs just **+0.9 vol points** of variance premium
* and a **~3%/yr dividend sits on top**, uncapped by the call — the screen's point
  that yield helps twice

## Caveats

* **No FAS or XLU option prices exist here.** The premium column is what the
  instrument *needed to be paid*, not what it *was* paid. Verifying the second
  requires their option chains, which this repo does not contain.
* XLU is built from weekly closes (IBKR), so its entry is the prior Friday close
  rather than Monday 10:00. FAS and SOXL use real 5-min Monday-10:00 entries.
* Strikes use trailing 13-week realised vol, which is implementable, but the SOXL
  check shows this places strikes slightly further out than a true 0.30-delta
  contract. That biases every required-VRP figure **low** — i.e. the real hurdles
  are somewhat higher than the table shows, for all four instruments equally.
* 2022–2026 only. Financials and utilities had no crisis in this window; a 2008
  or a rate shock would change FAS's tail materially.
