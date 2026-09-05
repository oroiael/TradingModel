# ccp_lab — SOXL covered call + 90-day protective put, one script per year

A literal backtest of the rule as stated, on real data, rebuilt from scratch:

> Every Monday at 10:00 write a weekly call so the premium collected is 5% of the
> value of the underlying held. Buy the underlying at the **high** of the 10:00
> one-minute bar. Hold a put 90 days out, just out of the money. Never trade the
> put — hold it to expiry, exercise if needed, then reload on the same terms.
> Start with $100,000 and reinvest. Whole shares. Whole or half-dollar strikes only.

## Setup

```bash
pip install -r ccp_lab/requirements.txt

git lfs install && git lfs pull    # the data is in Git LFS; without this every
                                   # CSV is a 130-byte pointer file

python ccp_lab/doctor.py           # preflight: packages, data, cache. Run this
                                   # first if anything below fails.
```

`doctor.py` prints exactly what is missing and how to fix it. The most common
problems it catches:

| symptom | cause | fix |
|---|---|---|
| `ImportError: Unable to find a usable engine ... pyarrow` | no parquet engine | `pip install pyarrow`, or just re-run — the cache rebuilds as pickle automatically |
| `FileNotFoundError` on a cache file | cache never built | nothing to do; the runners build it on first use |
| a CSV parses as one junk row | Git LFS pointer, not data | `git lfs install && git lfs pull` |
| `UnicodeEncodeError` writing a summary | Windows cp1252 console | already handled — all IO is forced to UTF-8 |
| `ZoneInfoNotFoundError: America/New_York` | Windows ships no IANA tz database | already handled — the cache builder reads the vendor's ET wall clock straight off the string and never converts a timezone |

`pyarrow` is optional. Without it the cache is written as pickle, which needs no
extra package; it is larger and slower to load but produces identical results.

## Running it

The runners build the cache themselves on first use (15–25 minutes, once), so on
a fresh checkout you can go straight to any year:

```bash
python ccp_lab/run_2024.py         # one year -> out/summary_2024.md

python ccp_lab/build_cache.py      # (optional) build the cache up front instead
python ccp_lab/qa_data.py          # data QA/QC          -> out/QA_DATA.md
python ccp_lab/audit.py            # engine invariants   -> must print AUDIT PASSED

python ccp_lab/run_2022.py         # one script per year -> out/summary_<year>.md
python ccp_lab/run_2023.py
python ccp_lab/run_2024.py
python ccp_lab/run_2025.py
python ccp_lab/run_2026.py         # partial year, data ends 2026-07-02

python ccp_lab/roll_2022.py       # same year, rolling  -> out/summary_2022_roll.md
python ccp_lab/roll_2023.py       #   ... and so on through roll_2026.py

python ccp_lab/run_all.py         # all five + rollup   -> out/SUMMARY_ALL.md
python ccp_lab/roll_all.py        # rolling + baseline  -> out/SUMMARY_ROLL.md
python ccp_lab/roll_mechanism.py  # what rolling changes-> out/ROLL_MECHANISM.md
python ccp_lab/controls.py        # leg-by-leg controls -> out/CONTROLS.md
python ccp_lab/mechanism.py       # why it loses        -> out/MECHANISM.md
python ccp_lab/cashflow.py        # pure cash ledger    -> out/CASHFLOW.md
python ccp_lab/sticky.py          # sticky vs re-strike -> out/STICKY.md
python ccp_lab/put_policy.py      # when the put pays   -> out/PUT_POLICY.md
python ccp_lab/combo.py           # both fixes together -> out/COMBO.md
python ccp_lab/put_trigger.py     # what should trigger the put sale -> out/PUT_TRIGGER.md
python ccp_lab/exit_range.py      # the same, priced three ways -> out/EXIT_RANGE.md
python ccp_lab/cohorts.py 2026    # a cohort per start month -> out/COHORTS_2026.md
python ccp_lab/weekly_flat.py     # no put, no carry -> out/WEEKLY_FLAT.md
python ccp_lab/moneyness.py       # ITM vs OTM strikes -> out/MONEYNESS.md
python ccp_lab/sweep.py           # premium-target sweep-> out/SWEEP.md
```

Each year is an **independent $100,000 experiment**: capital goes in on the first
Monday of the year and everything is liquidated at the last close **for which an
option chain exists**. That last clause matters: the 2026 price tape runs to
07-30 but the chains stop at 07-02, and running past them leaves the position
unwritten and unhedged through a −36.4% tail. Every 2026 figure produced before
that cap was added — benchmark included — was wrong. Years do not
compound into each other, so no year's result is contaminated by another's.

## Results

| year | final | return | buy & hold | median premium | called away |
|---|---:|---:|---:|---:|---:|
| 2022 | $60,291 | **−39.7%** | −86.2% | 4.75% | 20 / 52 |
| 2023 | $83,432 | **−16.6%** | +227.1% | 3.27% | 23 / 52 |
| 2024 | $66,472 | **−33.5%** | −6.5% | 3.87% | 25 / 53 |
| 2025 | $62,382 | **−37.6%** | +45.4% | 3.91% | 25 / 53 |
| 2026 | $88,632 | **−11.4%** | +278.8% | 5.01% | 15 / 26 |

The rule loses money in all five years, including the two in which SOXL more than
doubled. It beats buy & hold only in 2022, the −86% year, which is what a hedge is
supposed to do.

## Rolling the call instead of taking assignment

`roll_<year>.py` runs the identical rule except an in-the-money call is **bought
back on expiry day** rather than allowed to assign, with the far leg of the same
combo order selling the following week (strike never below the old one, premium
targeted at 5% of spot). Where the net debit cannot be funded from cash the
shares are still assigned, and that is counted rather than wished away.

| variant | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| take assignment (baseline) | −39.7% | −16.6% | −33.5% | −37.6% | −17.8% |
| buy back Friday, re-write Monday | −45.5% | −10.3% | −30.1% | +4.0% | +6.9% |
| **roll as one combo order** | **−37.5%** | **−0.0%** | **−40.7%** | **+0.3%** | **+36.7%** |
| buy & hold SOXL | −86.2% | +227.1% | −6.5% | +45.4% | +140.8% |

**Rolling is a real improvement and not a fix.** It wins in three of five years,
by more than 40 points in 2025 and 2026, and it still loses money in 2022 and
2024 and still trails buy & hold everywhere except the crash.

What it changes: the shares are never sold at the strike and never repurchased at
Monday's higher open — the +9.4% median whipsaw measured under assignment simply
stops happening. What it does not change: at the instant of expiry, buying the
call back for its intrinsic and being assigned at the strike are worth **exactly
the same**. A roll defers the loss rather than avoiding it. Across 105 rolls the
strike ratcheted up a median **+11.1%**, but only 30% of rolls were a net credit,
and rolls chain — up to **5 consecutive weeks** of paying intrinsic to keep a
position that stays capped.

One practical finding: **rolling needs cash the reinvest-everything rule does not
leave.** With no reserve, 47 buybacks across five years could not be funded and
assigned anyway. A 10–20% cash reserve removes almost all of them and barely moves
the return — the funding constraint was real, but it was never what drove the
result.

## Sticky strike — not re-striking down after a decline

The rule as written picks a new strike every Monday at the 5%-premium target, so
after a decline it re-caps at the new lower price and the recovery is sold at the
bottom. `sticky.py` keeps the old strike while the shares are held.

| variant | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| re-strike every Monday (the rule) | −39.7% | −16.6% | −33.5% | −37.6% | −17.8% |
| **sticky strike** | −50.5% | **+38.1%** | **−23.1%** | **+5.6%** | **+6.8%** |
| sticky + combo roll | −52.9% | +0.3% | −26.2% | +9.3% | +25.1% |
| buy & hold SOXL | −86.2% | +227.1% | −6.5% | +45.4% | +140.8% |

Wins in four years of five, loses badly in the fifth — 2022, the −86% year that
never recovered inside the window. Sticky is a bet that a decline mean-reverts.

**The cost is the income itself.** In 2025 the median weekly premium falls from
**3.91% to 0.33%** and annual premium roughly halves. Once the stock has fallen
away from the stranded strike the call is nearly worthless, so nothing is
collected — but the whole rebound up to that strike is kept. Assignments drop by
about two thirds and the 2025 share leg goes from **−$16,940 to +$25,931**.

The stranded strike is not an income rule. It is a *stop-capping-after-a-decline*
rule that happens to be spelled like one — and **it is no longer the strategy as
specified**: it does not pay 5% a week, or anything like it.

## The put: worth enough, collected too late

The put is already worth enough at the moment the re-strike loss happens — the
rule just realises it at the wrong time. On 2025-04-25 the shares were called
away at $9.00 for a **−$42,252** loss on that lot; at that instant the puts held
were worth **$35,209** of intrinsic, **83% of the loss**. By their 2025-05-16
expiry SOXL had rebounded to $18.39 and they settled for $18,081. Across 2025 the
puts returned **45%** of the loss they sat against, not the 83% they were worth on
the day of impact.

That is a clock mismatch, not a hedging failure: the call resolves **weekly** and
books the share loss at Friday's price; the put resolves **quarterly**.

Selling the put once the shares are gone (it protects nothing at that point):

| variant | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| hold the put to expiry (the rule) | −39.7% | −16.6% | −33.5% | −37.6% | −17.8% |
| **sell the put once the shares are gone** | **−35.1%** | −24.3% | **−31.5%** | **−8.3%** | **−12.9%** |

Better in three years of five and still losing in all five. These numbers are
**with the exit sold at the bid** — an earlier version of this lab priced put
exits at the model mark, which on deep in-the-money contracts sat a median +11.8%
above the bid against a 10% quoted spread, and overstated this variant by roughly
9 points of mean return. See `PUT_TRIGGER.md`.

## Both fixes together

| variant | 2022 | 2023 | 2024 | 2025 | 2026 | mean |
|---|---:|---:|---:|---:|---:|---:|
| base — the rule as written | −39.7% | −16.6% | −33.5% | −37.6% | −17.8% | −29.0% |
| sticky only | −50.8% | +38.3% | −23.1% | +5.7% | +6.8% | −4.6% |
| sell the put when flat only | −35.1% | −24.3% | −31.5% | −8.3% | −12.9% | −22.4% |
| **sticky + sell the put when flat** | −45.0% | +20.3% | **−9.8%** | **+55.5%** | +15.1% | **+7.2%** |
| buy & hold SOXL | −86.2% | +227.1% | −6.5% | +45.4% | +140.8% | +64.1% |

Mean goes from −29.0% to +7.2%, and 2025 is the first time any variant beats
buy & hold in an up year. The two are **sub-additive**: both are triggered by the
same assignments, so fixing one leaves less for the other. Put exits are sold at
the **bid** throughout — see `PUT_TRIGGER.md` for why that matters more than any
other assumption here.

A large part of the gain is not income at all — **38 of 237 Mondays (16%) have no
call worth selling**, because the stranded strike is bid at zero. Those weeks the
shares run uncapped. It still loses to buy & hold on average, 2022 is still bad,
and it is emphatically **not a 5%-a-week strategy**.

## Writing the call in the money

A covered call is synthetically a short put at the same strike, so writing deep
ITM means being called away almost every week for only the time value.

**The risk control works exactly as advertised.** At 30% ITM the assignment rate
is 97%, weekly volatility falls from 9.4% to 1.1%, and the worst single week
improves from −38.5% to −8.1%.

**Then you cross the spread and the ranking inverts:**

| strike | on my marks | less measured half-spread | at the bid |
|---|---:|---:|---:|
| −30% (deep ITM) | **+18.0%** | **−29.7%** | −25.7% |
| −10% | −8.3% | −25.2% | −12.8% |
| 0% (ATM) | −12.1% | −19.3% | −10.3% |
| +5% (OTM) | −10.9% | **−15.9%** | **−9.1%** |

Deep ITM goes from best to worst. The arithmetic: a 30%-ITM weekly call carries a
median time value of **0.13% of spot** while those contracts quote a **5.1%
median spread (12.3% at the 75th percentile)**, and **the bid is below intrinsic
in 53% of weeks**. You pay a 5–12% transaction cost to collect 0.13%.

Being called out every week does manage variance — but note that a crash is
precisely the case where you are *not* called away.

## The result that explains all the others

`weekly_flat.py` strips the structure back: buy Monday, write the call, be flat by
Friday's close, **no put and nothing carried over a weekend**.

| variant | 2022 | 2023 | 2024 | 2025 | 2026 | mean |
|---|---:|---:|---:|---:|---:|---:|
| the rule as written (put + carry) | −39.7% | −16.6% | −33.5% | −37.6% | −11.4% | −27.8% |
| carry, no put (call only) | −71.4% | +63.4% | −16.3% | −13.2% | +51.8% | **+2.8%** |
| weekly flat, no put | −64.6% | +30.2% | −34.2% | −32.9% | +53.8% | −9.5% |
| weekly flat, no put, **no call** (control) | −85.4% | +226.6% | −6.5% | +47.3% | +280.2% | +92.4% |
| buy & hold SOXL | −86.2% | +227.1% | −6.5% | +45.4% | +278.8% | +91.7% |

**Dropping the put is the biggest single lever in the lab** — a 30-point swing,
larger than anything else tested. **Being flat over the weekend is nearly free**:
the no-call control does 236 round trips and lands within 1 point of buy & hold,
so friction and weekend gaps roughly cancel.

### Why 65% winning weeks still loses money

Across 236 weekly round trips the **median week makes +3.67%** and the **mean
week makes +0.48%**. That gap is a long left tail — the worst week is **−37.2%**
and the worst quartile compounds to **−100%** on its own.

| | per week | annualised |
|---|---:|---:|
| arithmetic mean | +0.475% | +28% |
| **geometric mean** | **+0.017%** | **+1%** |
| variance drag | 0.458% | |
| σ²/2 | 0.430% | |

The drag and σ²/2 agree, and both are the same size as the edge. **Writing weekly
calls on a 3× ETF earns approximately what the volatility of a 3× ETF costs you to
compound.**

### And the edge is not measurable

t = **0.79**. The 95% interval on the weekly mean annualises to **−31% to +136%**.
Reaching t = 2 at this mean and volatility would take **29 years**.

That is the real answer to a live account disagreeing with a backtest: the true
expectation cannot be pinned down from five years of a 3× ETF. Two accounts on
identical rules will land in different places and neither is evidence about the
rule — **including every single number in this lab**.

## Start-date cohorts — the number moves more than the rule does

`cohorts.py` opens an independent $100,000 account on the first Monday of each
month and runs them all in parallel to the end of the data. 2026:

| strategy | Jan | Feb | Mar | Apr | May | Jun | spread |
|---|---:|---:|---:|---:|---:|---:|---:|
| the rule as written | −11% | −23% | −32% | +1% | −12% | −19% | 32 pts |
| **roll the call** | **+58%** | **+42%** | **+20%** | **+40%** | −8% | −9% | 66 pts |
| sticky strike | +18% | +6% | −3% | +6% | −11% | −23% | 41 pts |
| sell put when flat | −13% | −12% | −21% | −13% | −6% | −6% | 15 pts |
| sticky + sell put when flat | +15% | +5% | −0% | −6% | −0% | −9% | 24 pts |
| sticky + sell put + 30% roll-down | +26% | +17% | −0% | −6% | −0% | −9% | 35 pts |
| buy & hold SOXL | +279% | +188% | +199% | +247% | +40% | −15% | 304 pts |

**The start month is worth more than the rule.** The rule as written spans 32
points on start date alone; the gap between permutations at a fixed start is
often smaller than that. Two live accounts running identical rules from March and
May will not agree, and neither is evidence about the rule.

It also overturns a conclusion: **rolling the call is the best permutation in 4 of
6 start months in 2026**, which the calendar-year number hid — a calendar year is
just the January cohort.

## Why — three measured mechanisms

**1. A 5% weekly premium mostly does not exist.** An at-the-money weekly call is
worth about `0.055 × IV × spot`, so 5% needs roughly **90% implied vol**. Across
2022–2026 the best premium available from any strike at or above spot had a median
of 2.8–5.3% depending on the year, and cleared 5% on only 5–60% of days. Chasing
the target therefore pins the strike **at the money** (median 0.9–2.2% OTM), which
is what drives everything else.

**2. The short call gives back more than it collects.** $698,027 of premium
collected over 236 writes; $820,158 of intrinsic surrendered on 108 assignments.
Net **−$122,131**. Writing barely out of the money means ~46% of weeks finish in
the money, and the ones that do finish far in.

**3. The put costs more than the whole call program earns.** A just-OTM put on a 3×
semiconductor ETF costs a median **16.8% of spot per 84 days** — reloaded ~4× a
year, on the order of **50–60% of the position's value annually**. $293,234 paid,
net **−$112,439**.

And the structure whipsaws: across 107 assignments the shares went back on at a
median **+9.4% above the strike they were called away at**, higher in **94%** of
cases. Selling at a fixed strike on Friday and rebuying at the market on Monday is
a sell-low/buy-high rule whenever the stock trends up.

## Controls — which leg costs the money

| variant | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| CC + long put (the rule) | −39.7% | −16.6% | −33.5% | −37.6% | −17.8% |
| covered call only | −71.4% | +63.4% | −16.3% | −13.2% | +5.6% |
| shares + long put only | −57.6% | +67.8% | −19.3% | +7.9% | +90.2% |
| shares only | −85.4% | +226.6% | −6.5% | +47.3% | +141.7% |
| 5% read as *total* gain if called | −36.3% | −20.4% | −31.9% | −32.4% | −15.5% |
| the rule, frictionless | −38.3% | −14.1% | −32.1% | −35.3% | −17.1% |
| buy & hold SOXL | −86.2% | +227.1% | −6.5% | +45.4% | +140.8% |

Reading down: **both legs lose, and each is worse with the other attached.**
Removing costs entirely changes almost nothing, so this is not a friction story.
The "shares only" row lands within ~1 point of buy & hold, which is the engine
validating itself — the share, cash and reinvestment machinery is not the problem.

## The rule as implemented

| spec | implementation |
|---|---|
| Monday 10:00 entry | First trading day of each ISO week, the 10:00 **1-minute** bar. Holiday Mondays fall through to Tuesday. |
| Buy at the 10:00 high | `high` of that bar — a deliberately conservative fill. |
| Premium = 5% of underlying value | Among strikes **at or above spot** (so being called away is always a gain), the one whose 10:00 premium is closest to `0.05 × spot`. The realised premium and shortfall are logged every week. |
| Weekly call | The last listed expiry inside that Monday's week. Held to expiry; assigned if it finishes in the money. |
| Put 90 days out, just OTM | Listed expiry nearest 90 DTE (median 88); highest valid strike strictly **below** spot. |
| Never trade the put | Puts are only ever expired or exercised, never sold. New puts are bought only to cover lots that have none. |
| $100,000, reinvest, whole shares | Position resized every Monday to the largest number of 100-share lots that is fully put-hedged and fully funded. Cash never goes negative — no implicit leverage. |
| Whole or .5 strikes | Enforced on every leg. 2022 carries 20% non-standard strikes from a corporate action; they are filtered out. |

Costs: $0.65/contract, $0.005/share. Options are marked at a real 10:00 trade print
where one exists (85–100% of fills by year), the nearest print inside 09:30–10:30
next, and Black-Scholes off that contract's own EOD implied vol otherwise.

## Correctness

`audit.py` prints **AUDIT PASSED** and checks, for every year:

- P&L attributed to shares/calls/puts/fees reconciles to final equity **to the cent**
- no naked calls, and no call ever written below spot
- every share lot carries a put, every week
- cash never negative — no accidental leverage
- no assignment of an out-of-the-money call, no exercise of an out-of-the-money put
- every share sold was bought first; no NaNs in the equity curve

## Caveats

- **Assignment is modelled at expiry only.** American calls can be assigned early,
  especially around ex-dividend. Writing at the money makes this a live risk, so the
  real-world result would be *worse*, not better.
- **Rolling is modelled at expiry, not before.** The roll happens on expiry day
  at the EOD chain mid. A trader who rolls on Wednesday, or on a delta trigger,
  gets a different (usually better) entry than this measures.
- **The roll buys back at the EOD mid, floored at intrinsic.** That is neutral
  execution on a two-sided quote; paying the ask on every buyback would be worse.
- Fills are at trade prints, which is optimistic on size; cash earns 0%; no taxes,
  and 108 assignments in five years is a heavy short-term-gain load.
- Five years of a 3× ETF spanning one −86% year and one +141% half-year is a small
  sample of regimes.

## Files

| file | what |
|---|---|
| `build_cache.py` | normalises the five vendor CSV dialects into parquet |
| `engine.py` | pricing, contract selection, and the backtest state machine |
| `report.py` | per-year summary writer |
| `run_<year>.py` | one script per year, taking assignment |
| `roll_<year>.py` | one script per year, rolling instead of assigning |
| `run_all.py` · `roll_all.py` | rollups for the two builds |
| `controls.py` · `mechanism.py` · `roll_mechanism.py` · `sweep.py` | controls, mechanisms, premium-target sweep |
| `cashflow.py` | brokerage-statement view: every dollar in and out, no attribution |
| `sticky.py` | keeping the old strike vs re-striking down every Monday |
| `put_policy.py` | what the put was worth when it mattered, vs what we collected |
| `combo.py` | sticky strike and the put policy applied together |
| `put_trigger.py` | position-state vs deep-ITM roll-down triggers, and exit-spread realism |
| `exit_range.py` | roll-down under generous / central / worst-case put exits |
| `cohorts.py` | one account per start month, run in parallel — start-date sensitivity |
| `weekly_flat.py` | no put, nothing carried over a weekend |
| `moneyness.py` | writing the call in the money, and what the spread does to it |
| `audit.py` · `qa_data.py` | engine invariants (all three modes), data QA |
| `doctor.py` · `compat.py` · `requirements.txt` | preflight, cross-platform IO, deps |
| `out/summary_<year>.md` · `out/summary_<year>_roll.md` | the per-year summary files |
| `out/ledger_<year>.csv` | one row per Monday: spot, lots, strike, premium, moneyness |
| `out/events_<year>.csv` | every fill, assignment, exercise, expiry |
| `out/equity_<year>.csv` | daily marked-to-market equity |
| `out/CASHFLOW.md` | every year as cash in / cash out, reconciled to the cent |
