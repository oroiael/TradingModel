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
python ccp_lab/sweep.py           # premium-target sweep-> out/SWEEP.md
```

Each year is an **independent $100,000 experiment**: capital goes in on the first
Monday of the year and everything is liquidated at the last close. Years do not
compound into each other, so no year's result is contaminated by another's.

## Results

| year | final | return | buy & hold | median premium | called away |
|---|---:|---:|---:|---:|---:|
| 2022 | $60,291 | **−39.7%** | −86.2% | 4.75% | 20 / 52 |
| 2023 | $83,432 | **−16.6%** | +227.1% | 3.27% | 23 / 52 |
| 2024 | $66,472 | **−33.5%** | −6.5% | 3.87% | 25 / 53 |
| 2025 | $62,382 | **−37.6%** | +45.4% | 3.91% | 25 / 53 |
| 2026 | $82,213 | **−17.8%** | +140.8% | 5.01% | 15 / 26 |

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
| `audit.py` · `qa_data.py` | engine invariants (all three modes), data QA |
| `doctor.py` · `compat.py` · `requirements.txt` | preflight, cross-platform IO, deps |
| `out/summary_<year>.md` · `out/summary_<year>_roll.md` | the per-year summary files |
| `out/ledger_<year>.csv` | one row per Monday: spot, lots, strike, premium, moneyness |
| `out/events_<year>.csv` | every fill, assignment, exercise, expiry |
| `out/equity_<year>.csv` | daily marked-to-market equity |
| `out/CASHFLOW.md` | every year as cash in / cash out, reconciled to the cent |
