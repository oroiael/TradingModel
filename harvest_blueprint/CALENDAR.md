# The calendar / diagonal, measured — the last short-premium structure fails too

`README.md` §3 of this directory closed by naming calendars **"the one
defensible way to be short premium here"** and "the honest home for the
blueprint's instinct." That recommendation was based on a pricing disparity,
not on a traded result. It has now been traded.

**It does not survive. The short overlay cost money in every one of the 40
configurations that carried one, in both rights, at both strike disciplines,
and under a sizing-free test that holds the long book exactly constant.**

Engine: `calendar_backtest.py`. Reproduce with `python3 calendar_backtest.py`
(needs `git lfs pull` for the option chains). Report: `qa/calendar_report.txt`;
grid `calendar_grid.csv`; base ledger `calendar_ledger.csv`.
**47 runs, 0 QA reconciliation failures.**

---

## 1. What was tested, and why it looked promising

The thesis came from two measurements on SOXL's own surface:

* the ATM term structure is **inverted on 67–68% of days** — the front week
  averages **+6.7 IV points over 30d** and +9.6 over 180d;
* the 7-day tenor is the **only** one whose variance risk premium is not
  negative (+0.7 pts), while 30/90/180d run **−14/−22/−29 pts**.

So: sell the one tenor that is not underpriced, own the tenor that is most
underpriced. Unlike a naked weekly, a calendar is defined-risk and roughly
delta-neutral at inception, which is exactly what the naked short-premium
structures in `qa/pricing_lab_report.txt` S6 lacked.

**Structure.** Long one back-month option (strike = `long_mness` × spot, DTE
targeted in a window, rolled at `long_roll_dte` or on drift); short one
front-week option of the same right, struck `short_offset` further OTM,
held to expiry and cash-settled at intrinsic, re-sold weekly for as long as
the long leg lives. Risk is defined by construction: the short is never
struck closer to the money than the long, so the spread cannot be worth less
than zero and max loss is the net debit.

**Grid.** Long tenor {30, 60, 90, 150 DTE} × moneyness {0.90 … 1.10} ×
offset {0, 3, 5, 8%} × right {CALL, PUT} × risk fraction {10, 25, 50%},
plus a re-centred variant that keeps the short leg on spot each week instead
of letting it go stale, plus a drift re-strike. Execution is the project's
20%-of-spread rule on real quotes, $0.65/contract/leg, EOD decisions,
2024-01-02 → 2026-07-02 (131 weeks; the base config trades 116 of them).

---

## 2. The decisive test — sizing-free, identical long book

Wealth curves are not comparable across strategies whose position sizes
compound differently, and the existing PMCC engine's `LONGONLY` control has
exactly that problem. So the deciding run holds **one contract per leg**: no
sizing rule, no compounding, no capital constraint. The long book is then
*byte-identical* between a calendar and its long-only control — confirmed by
`long_realized` matching to the dollar within each right — and the only
difference in the result is the short overlay itself.

P&L per unit, 2024-01 → 2026-07:

### CALL side — long leg alone: **+$15,301**

| overlay | premium sold | overlay P&L | **cost of the overlay** | mean abs net delta |
|---|---:|---:|---:|---:|
| diagonal 5%, re-centred | $16,541 | +$11,872 | **−$3,429** | 0.395 |
| calendar, re-centred | $26,710 | +$11,563 | **−$3,739** | 0.255 |
| diagonal 5%, stale strike | $129,263 | +$5,034 | **−$10,267** | 0.175 |
| calendar, stale strike | $142,094 | +$4,989 | **−$10,313** | 0.130 |

### PUT side — long leg alone: **+$695**

| overlay | premium sold | overlay P&L | **cost of the overlay** | mean abs net delta |
|---|---:|---:|---:|---:|
| diagonal 5%, re-centred | $10,771 | −$9,215 | **−$9,910** | 0.197 |
| calendar, re-centred | $15,900 | −$10,654 | **−$11,350** | 0.132 |
| diagonal 5%, stale strike | $41,991 | −$10,935 | **−$11,630** | 0.153 |
| calendar, stale strike | $53,944 | −$12,046 | **−$12,742** | 0.145 |

**Eight overlays, eight losses.** Not one improved on simply holding the long
leg and never selling anything against it.

The two sides matter jointly. On the call side the long leg won large, so an
overlay that caps upside is expected to cost something. **On the put side the
long leg was flat (+$695) — there was no upside to cap — and the overlay still
cost $9,910 to $12,742.** If the front week carried a real premium edge, that
is precisely where it should have shown up. It did not. The result is
direction-independent.

### The pure form of the trade is the worst form

On the call side the ordering is monotonic in the wrong direction: the
**most delta-neutral** configuration (mean abs net delta 0.130 — a genuinely
delta-light structure, not a strawman) carried the **largest** overlay cost
(−$10,313), and the most directional one (0.395) the smallest (−$3,429). The
closer the structure came to a pure term-structure trade with direction
stripped out, the more it lost.

Two honest qualifications. First, this ordering is clean on the call side and
only directionally consistent on the put side (0.132 → −$11,350 breaks strict
monotonicity). Second, strike staleness confounds it: the stale-strike runs
are simultaneously more delta-neutral *and* sellers of far more gross premium,
so the two effects cannot be fully separated here. What is not confounded is
the sign — every cell is negative.

**A caveat on the "premium sold" column:** for a stale-strike short that has
gone deep ITM, most of that figure is intrinsic value handed straight back at
settlement. $142,094 is not $142,094 of income, and the column should be read
as gross flow, not earnings. The overlay-cost column is the one that means
something.

---

## 3. The compounding grid agrees

With real position sizing and compounding (risk 25% of equity per cohort):

| config | end wealth | CAGR | max DD | short premium | short realized |
|---|---:|---:|---:|---:|---:|
| **LONGONLY call (no overlay)** | **$1,025,945** | **+116.0%** | −65.8% | 0 | 0 |
| BUYHOLD SOXL | $970,697 | +111.3% | −88.0% | 0 | 0 |
| best calendar (diagonal 5%, re-centred) | $555,972 | +69.0% | −54.8% | $576,001 | **−$169,559** |
| calendar, re-centred | $396,626 | +47.6% | −44.0% | $835,755 | **−$161,586** |
| base calendar (90 DTE, ATM, stale) | $179,621 | +7.5% | −30.5% | $2,538,512 | **−$173,286** |
| LONGONLY put | $53,033 | −34.1% | −68.3% | 0 | 0 |
| base put calendar | $40,313 | −40.9% | −71.8% | $690,012 | **−$51,555** |

Across the whole grid — **40 runs carrying a short leg — `short_realized` is
positive in exactly zero of them.**

The long-only call control beats every calendar variant, and also beats buying
the shares. The put-side long-only control beats every put calendar. The
overlay is a cost on both sides of the market.

One number is worth sitting with: the base calendar collected **$2.54 million**
in gross premium over 131 weeks and finished at **+7.5% CAGR**, against
**+116%** for the identical long leg with nothing sold against it.

---

## 4. Why it fails

The disparity is real; it is just not an edge.

**The front week is richer because it delivers.** A +6.7 IV-point term premium
is compensation for one week of SOXL gamma, and SOXL supplies it: weekly
Mon→Fri sd is 13.9%, with 24.0% of weeks beyond +10% and 20.8% beyond −10%.
`harvest_blueprint/README.md` §1 measures the general form of this — forward
realized vol regresses on implied with a slope **above 1.0 at every tenor**.
The term structure being inverted does not mean the front is overpriced; it
means the near future is genuinely more dangerous than the far future, and the
market is saying so correctly.

**Friction is charged against a spread that is thin to begin with.** A calendar
cycle crosses the bid/ask four times — open and close on each leg — on a chain
whose median relative spread at the weekly tenor is **20.7% of mid at 10–20
delta** and **66.7% at 0–10 delta**, with 27.4% of the far-OTM weekly quotes
rejected outright (`qa/pricing_lab_report.txt` S5). Round-trip friction is
0.6 × spread. A 6.7-point IV edge does not clear that repeatedly.

**Defined risk is not the binding constraint.** The calendar fixed the thing
that killed the naked weeklies — the uncapped tail — and it still lost. That
localizes the failure: it was never only about tail risk. There is no premium
in the front week to pay for the structure in the first place.

---

## 5. What this changes

`harvest_blueprint/README.md` §3 recommended calendars as the one defensible
short-premium structure on SOXL. **That recommendation is withdrawn.** The
scorecard in §2 of that document is unaffected — every component tested there
still fails or survives as reported — but the constructive half now reads:

> On this data, over this window, there is **no** short-premium structure on
> SOXL that pays. Not naked (31/31 weekly permutations negative), not
> defined-risk (37/37 condor configs negative), not calendarized (40/40 short
> legs negative), not gated on IV percentile (2.2× worse), not protected by
> stops (monotonically worse). The instrument's variance risk premium is
> negative, and every structure that sells it inherits that sign.

The long-vol findings in §3 of that README are untouched and are still where
the measured edge is: 120–150 DTE strangles harvested at +50% on fractional
sizing, and `bull_call` debit spreads, positive in every year 2022–2026.

---

## 6. Honest limitations

* **Window.** 131 weeks, 2024-01 → 2026-07 — the same window as the condor and
  diagonal engines, and it contains the 2026 melt-up. A melt-up is the hardest
  regime for any structure that sells calls, which is exactly why the put-side
  result carries the argument: it is the direction-independent half.
* **EOD only.** Option quotes are end-of-day snapshots, so the short leg is
  opened at Monday's close and held to expiry. A calendar trader who manages
  intraday — closing the short early at 50% of max, rolling on a touch — is not
  simulated here, and that is a real gap rather than a rounding error.
* **No delta hedging.** The measured structure is delta-*light*, not
  delta-neutral (base mean abs net delta 0.127, range −0.23 to +0.39). A
  continuously delta-hedged calendar is a different trade; `vol_anatomy` flags
  gamma-scalping economics on SOXL as genuinely open, and this run does not
  settle it.
* **Weeks skipped.** The base config found no admissible short in 13 of 131
  weeks (the defined-risk constraint plus a $0.02 minimum sale price), so it
  traded 116. Skipped weeks are recorded in the ledger, not silently dropped.
* **One instrument.** This says calendars fail on SOXL over this window. On an
  index with a positive VRP the same structure may well pay; nothing here
  speaks to that.

---

## 7. Reproduce

```bash
git lfs pull                       # option chains are LFS-backed
python3 calendar_backtest.py       # 47 runs -> calendar_grid.csv,
                                   # calendar_ledger.csv, qa/calendar_report.txt
```

Controls built into the grid, and what each one isolates:

| control | isolates |
|---|---|
| `LONGONLY_*` | the long leg with no overlay, same risk fraction |
| `*_1x` (unit mode) | one contract per leg — sizing and compounding removed |
| `*_szL` | long-cost sizing, so the pair matches at inception |
| `SHORTONLY_*` | the weekly short alone, cash-secured (different sizing basis) |
| `BUYHOLD` | SOXL shares |
