# The active volatility-harvesting blueprint, tested on SOXL

The standard automated short-vol playbook — delta-neutral premium selling, gated
on IV percentile and VIX term structure, protected by stop-losses and a VIX
circuit breaker, with a premium-funded tail hedge and dynamic sizing — evaluated
component by component against this repository's measured SOXL data.

**Verdict: one of its eight components survives contact with SOXL, and it is the
one that contains no edge.** The blueprint is a well-built machine pointed at the
wrong sign. Its architecture is worth keeping; its direction has to be reversed.

Reproduce: `python3 harvest_blueprint/blueprint_tests.py` (no `git lfs pull`
needed — it reads the committed `pricing_lab/*.csv` tables).

---

## 1. The one measurement that decides it

Everything in the blueprint rests on a single premise: that options are, on
average, expensive relative to what the underlying then does. That premise is
true for SPX. **It is false for SOXL**, and it has been measured here three
independent times:

| tenor | mean IV | mean subsequent realized | **VRP** | seller was overpaid |
|---|---:|---:|---:|---:|
| 7d (weekly) | 106% | 105% | **+0.7 pts** | 56% of weeks |
| 30d | 100% | 114% | **−14 pts** | 43% |
| 90d | 100% | 122% | **−22 pts** | 35% |
| 180d | 94% | 122% | **−29 pts** | 12% |

`qa/pricing_lab_report.txt` S2, 919,090 option quotes, 2024-01 → 2026-07.
`vol_anatomy/harvestability.py` reproduces it on a separate window and on TQQQ;
`call_spread_lab/FINDINGS_2` reproduces it again at −8 vol points 2022–2026.

Sharper still — regress subsequently-realized vol on implied (test 3):

| tenor | corr | fitted relationship |
|---|---:|---|
| 7d | +0.60 | realized = −0.24 + **1.22** × implied |
| 30d | +0.58 | realized = −0.07 + **1.21** × implied |
| 90d | +0.57 | realized = −0.32 + **1.54** × implied |
| 180d | +0.53 | realized = −0.11 + **1.42** × implied |

**Every slope exceeds 1.** Each additional point of implied vol arrived with
*more* than a point of realized vol. SOXL's options are not merely fairly
priced — they get *cheaper* relative to outcome as vol rises. That single fact
is what breaks the blueprint, and it breaks the entry signal and the risk filter
by the same mechanism.

### Why SOXL differs from the index this playbook was written for

The index VRP is compensation for bearing crash and correlation risk that most
participants want to shed. SOXL is a **3× daily-levered single-sector ETF** —
`vol_anatomy` measures 116.9% close-to-close vol, exactly 3.00× its index on
both bases, 40% of days moving >5% and 12.7% moving >10%. On that distribution a
"crash" is a routine Tuesday. There is no natural crowd of hedgers overpaying to
be insured against normal behaviour.

And the tail is **not** one-sided. Weekly Mon-10:00 → Fri-15:30, n=154:
sd 13.9%, p01 −31.5%, **p99 +37.8%**; weeks beyond +10% are **24.0%** against
20.8% beyond −10%. The upside tail is the fatter one. This is why the short
*call* leg — the reliable earner in an index condor — bled here too: the
10%-OTM weekly short call won **90% of the time and still lost $34.2/share**
over 119 weeks.

---

## 2. Component scorecard

| # | Blueprint component | Verdict | Measured basis |
|---|---|---|---|
| 1 | Iron condors / strangles / short straddles | **Fails** | 37/37 condor configs negative; 31/31 weekly permutations negative |
| 2 | VIX term-structure contango gate | **Fails / inverted** | contango only 31.8% of days; backwardation had the *better* VRP |
| 3 | IV-percentile > 70 entry trigger | **Fails, harmful** | selects the worst bucket; realized P&L 2.2× worse |
| 4 | Delta-hedging triggers | **Structurally blocked** | 37–41% of variance is untradeable overnight gap |
| 5 | Hard stop-loss at 2–3× credit | **Fails, measured** | stops made every variant worse |
| 6 | VIX > 30 circuit breaker | **Contradicts #3** | the two rules fire on the same days |
| 7 | Premium-funded tail hedge | **No funding source** | the premium engine's mean is negative |
| 8 | Dynamic position sizing | **Survives** | the one component every lab here endorses |

### 1. Delta-neutral premium structures — the core trade

`r3_iron_condor_backtest.py`, 131 weeks, real fills, QA-reconciled 37/37:

| config | end wealth | total | CAGR | max DD | win rate |
|---|---:|---:|---:|---:|---:|
| base IC 22Δp/12Δc/8% wide | $31,298 | **−79.1%** | −46.3% | −77.6% | **69%** |
| best that actually traded | $62,057 | −58.6% | −29.6% | −71.5% | 74% |
| best on paper (traded 4 of 131 weeks) | $142,443 | −5.0% | −2.0% | −25.3% | 75% |

**All 37 configurations lost money.** Both wings lost independently — put side
−$186,093, call side −$116,197 — so this is not a directional accident. The 69%
win rate is exactly the short-vol signature: win small and often, lose large and
rarely, and the mean is what compounds. The only config that nearly broke even
did so by declining to trade 127 of 131 weeks.

The same result appears in a second engine: `qa/pricing_lab_report.txt` S6 tested
**31 weekly short-premium permutations** (put/call/strangle/straddle × 10–50Δ)
over 119 Mondays with 20%-rule fills. **Every one lost money.**

### 2. Term-structure / contango gate

SOXL has no VIX of its own, so test 2 uses SOXL's own 7d-vs-30d ATM curve — the
faithful analogue, and the right variable regardless.

| regime | n | mean VRP | % positive |
|---|---:|---:|---:|
| steep contango (< −5 pts) | 62 | +0.024 | 54.8% |
| mild contango | 59 | +0.016 | 55.9% |
| mild backwardation | 56 | +0.002 | 51.8% |
| **steep backwardation (> +5 pts)** | 204 | **+0.066** | **60.3%** |

The rule is **backwards on SOXL**: backwardation carried the better forward VRP.
And SOXL's curve is *inverted 68.2% of the time* (front-week vol persistently
rich vs the back), so a contango gate would sit out two-thirds of the sample to
select the worse third. Spearman(slope, forward VRP) = +0.087 — indistinguishable
from noise either way.

Separately: **VIX is not SOXL's volatility.** VIX is S&P-wide; SOXL's vol is
semiconductor-specific and 3× levered. `vol_anatomy` measures the semis index at
39.0% vs ~16% for a broad index. Gating a semis trade on an S&P vol signal
imports a regime variable that does not govern the position.

### 3. The IV-percentile trigger — the component that inverts

This is the blueprint's central claim, and it is the one that fails hardest.
Test 1, 7-day tenor, run two ways — with a **look-ahead** full-sample percentile
(impossible live, included as the most generous possible reading) and with a
live trailing-252-day percentile:

| IVP band | n | mean VRP | % positive | **p05 (left tail)** | mean IV |
|---|---:|---:|---:|---:|---:|
| 0–30 (cheap) | 148 | −0.007 | 52.0% | −0.867 | 0.76 |
| **30–70 (middle)** | 199 | **+0.072** | **60.3%** | **−0.586** | 0.99 |
| **>70 ← blueprint gate** | 149 | **−0.064** | 54.4% | **−1.547** | 1.46 |
| >90 (extreme) | 50 | **−0.236** | 46.0% | −1.867 | 1.82 |

The gate **selects the worst bucket and nearly triples the left tail.** The live
trailing version agrees (>70: −0.054; 30–70: +0.091). At 30d and 90d every band
is negative and the gate is still the worst of them.

Then the decisive version — test 5 gates the **actual trades**, not the premium.
All 31 weekly structures, real fills, split by entry-time IVP:

| | all weeks | **IVP > 70 (blueprint)** | IVP 30–70 (inverse) |
|---|---:|---:|---:|
| profitable structures | 0 / 31 | 1 / 31 | 2 / 31 |
| mean $/share-week | −0.693 | **−1.518** | **−0.258** |
| worst single week | −62.88 | **−62.88** | −14.82 |

**The gate makes the average trade 2.2× worse, and it does not avoid the worst
week — the worst week is identical, because the gate is what puts you in it.**
The live no-look-ahead run agrees: −1.354 vs −0.516 $/share-week.

The mechanism is test 3. High IVP does not mean "premium is historically
expensive"; on SOXL it means "the market has correctly detected that a violent
period is underway, and is still underpricing it by 22%."

### 4. Delta-hedging triggers

Two measured obstacles, both structural rather than a matter of tuning.

**37–41% of SOXL's total variance sits in the overnight gap** (`vol_anatomy`;
corroborated at 41% in `pricing_lab` S1). A delta-hedging loop only acts while
the market is open. It cannot rehedge through the gap that carries two-fifths of
the risk, so a "delta-neutral" book is neutral only during the session and
carries unmanaged directional risk every night.

**The rehedge is expensive.** `pricing_lab` S5 measures median bid-ask as a
share of mid at **20.7% for 10–20Δ options inside 9 DTE**, with **27.4% of
0–10Δ quotes rejected outright** (bid=0 or inverted). Round-trip friction runs
0.6 × spread. An iron condor is four legs, and delta-drift adjustment adds more.

Note the honest asymmetry: the negative VRP at 30–90 days means the *profitable*
side of SOXL vol over this window was **buying** it — and capturing that does
require delta-hedging (gamma scalping), paying the same spreads. `vol_anatomy`
flags this as a genuinely open question rather than a solved one.

### 5. Hard stop-losses at 2–3× credit

Measured directly in the condor grid, same config, only the stop varying:

| stop rule | end wealth | total return | max DD |
|---|---:|---:|---:|
| **no stop** | **$31,298** | **−79.1%** | −77.6% |
| stop at 3× credit | $30,399 | −79.7% | −78.3% |
| stop at 2× credit | $26,735 | −82.2% | −80.9% |
| stop at 2× credit, 50% margin | $22,150 | −85.2% | −82.7% |

**Every stop made it worse, monotonically in tightness.** `call_spread_lab`
FINDINGS_2 reproduces this on defined-risk spreads and finds something sharper:
stopping out produced a **worst trade of −179% of the debit** against a −100%
structural maximum, because closing a spread at stressed mid-crisis bid/ask costs
more than letting it settle at capped intrinsic — and you forfeit SOXL's frequent
snap-back. On a defined-risk structure the structure *is* the stop.

### 6. The VIX > 30 circuit breaker

The breaker is sound risk management in isolation. The problem is that it reads
the same variable as the entry gate. Test 4, on SOXL's own IV:

| halt threshold | of the 149 IVP>70 entries, blocked | surviving |
|---|---:|---:|
| above 70th pct of IV | 149 (100.0%) | **0** |
| above 80th pct | 99 (66.4%) | 50 |
| above 90th pct | 50 (33.6%) | 99 |
| above 95th pct | 25 (16.8%) | 124 |

Rule 1.3 says *enter* when vol is in the top 30%. Rule 2.3 says *halt* when vol
spikes. These are **one variable read twice with opposite signs**, so they
overlap by construction: a halt set anywhere at or below the 70th percentile
removes every entry the gate admits, and tightening the breaker only widens the
gate. VIX > 30 sits at roughly the top decile of VIX days, so the 90th-percentile
row is the closest analogue — it blocks a third of the gate's entries.

The overlap is not the deepest problem, though; it is the *selection*. The
breaker blocks precisely the highest-IV entries, which is to say the ones the
gate is most eager to take — and test 1 shows those are the worst ones
(IVP>90: mean VRP −0.236). The breaker is quietly correcting the entry signal.
That is worth noticing: **the blueprint's own risk control is compensating for
its own edge thesis.** When a system's safety rule and its entry rule disagree
about the same variable, one of them is wrong, and here it is measurably the
entry rule.

*(The halt is expressed on SOXL IV because no VIX series exists in this repo.
That is the correct regime variable for a semis position anyway; the point is
structural, not threshold-specific.)*

### 7. Tail hedging funded by harvested premium

`pricing_lab` S8 prices the anchor: a ~150-DTE ATM SOXL put costs **$14.02 on a
$49.33 spot — 25.2% of spot** — and bleeds **$0.21/week on average, $0.38 in
flat weeks**. The premium engine meant to fund it has a mean of **−0.693
$/share-week** (test 5). You cannot fund a hedge from a negative cash flow. This
component does not underperform; it has no input.

S7 tests the cheaper in-structure version — buying the wing instead of the
external hedge. It works as insurance and fails as economics: the wing costs
**37% of the credit**, improves the worst week from −$31.61 to −$27.67, and
takes total P&L from **−$112.55 to −$63.36 per share-week**. Less negative is
not positive.

### 8. Dynamic position sizing — the component that survives

This one is right, and it is the most strongly supported finding in the entire
repository. Every lab reaches it independently:

- `call_spread_lab` FINDINGS_3: the best long-strangle cell returns +44% CAGR at
  10–15% sizing and **−96% drawdown at full deployment** — same trades.
- FINDINGS_2: "invest 100%" on long premium is ruin on trade #1; fractional
  sizing turns the identical trade sequence into large compounding.
- The condor grid: holding deltas and width fixed and moving only the margin
  fraction from 10% to 25% moved max drawdown from **−64.4% to −77.6%**.

Keep it. Note what it is, though: sizing is **survival**, not edge. It converts a
positive-expectancy trade into a compounding one and a negative-expectancy trade
into a slower loss. Applied to short premium on SOXL it buys time, not profit.

---

## 3. What the SOXL version looks like

The blueprint's machinery — automated entries, regime gating, hard risk limits,
volatility-scaled sizing, a circuit breaker — is all worth building. Point it the
other way.

**Own the vol.** The original version of this line also said “and sell the one
tenor that is not cheap”; that half has since been measured and withdrawn
(`CALENDAR.md`). On this data there is no short-premium structure on SOXL that
pays — not naked, not defined-risk, not calendarized, not gated, not stopped.

**And there is one long structure that pays on SOXL: delta-hedged long gamma,
+$21,771 over 15 cycles, hedged ONCE A DAY rather than continuously. But the
out-of-sample instrument test FAILED — TQQQ is negative on the same engines over
the same window, gross as well as net, in 0 of 12 entry timings. Read it as a
single-instrument finding whose generality is unproven. See `GAMMA.md` §4c.**

| | blueprint | SOXL version | why |
|---|---|---|---|
| direction | short premium | **long premium** | VRP is −14 to −29 pts at 30–180d |
| core structure | iron condor | **long strangle, actively harvested** | 120–150 DTE rows uniformly positive |
| tenor | weekly | **120–150 DTE** | 30 DTE bleeds (−72% to −87% DD); 180d too costly |
| strike | 10–20Δ | **5–10% OTM** | best region on both return and drawdown |
| the "harvest" | collect decay | **bank spikes at +50%** | +44% CAGR / −36% DD vs +27% / −67% unharvested |
| IV gate | enter IVP > 70 | **enter on price weakness** | RSI14<45 entries +17.6% vs RSI14>55 −1.5% |
| stops | 2–3× credit | **none; structure is the stop** | every stop tested made it worse |
| sizing | scale down in high vol | **10–15% of equity per leg** | unchanged — the one component that carries over |
| tail hedge | buy OTM puts with premium | **not needed** | long premium *is* long the tail |

Measured performance of that configuration (`call_spread_lab/strangle_harvest.py`,
2022-01 → 2026-07, audited by `verify_strangle.py`, all checks pass): 120 DTE /
7.5% OTM / harvest at +50% / 15% per leg — **+44% CAGR, −36% max drawdown**,
$100k → $509k over 4.5 years across 63 harvests. The 120- and 150-DTE rows are
positive in *every* strike cell, so this is a region rather than a lucky cell.
The active harvest is doing real work: 2024 round-tripped and *destroyed* a
passive strangle (−75%) while the harvested version made **+68%**.

Two structures worth pairing with it:

- **`bull_call` debit spreads** — the most *robust* winner in the repo, positive
  in **every year 2022–2026** including the −87% bear, because defined risk caps
  the frequent misses while still catching the up-tail.
- ~~**Calendars / diagonals — the one defensible way to be short premium
  here.**~~ **Withdrawn — tested and refuted; see `CALENDAR.md`.** The
  disparity is real (the 7-day tenor is the only one whose VRP is not negative,
  and the curve is inverted 67–68% of days), but it does not survive being
  traded. `calendar_backtest.py` runs 47 configurations and the short overlay
  loses in **all 40** that carry one — on both rights, and in a sizing-free
  test that holds the long book identical. The front week is richer because it
  delivers, not because it is overpriced.

**Where the automation actually earns its keep:** the harvest trigger is a
per-leg "+50% from cost" rule evaluated continuously across two legs and multiple
open tranches, with re-arming around the new price. That is genuinely tedious by
hand and genuinely mechanical — exactly what an automated system is for. The
blueprint's engineering was never the problem.

---

## 4. Honest limitations

- **Window.** The VRP and gated-P&L tests use 2024-01 → 2026-07 option data
  (2.5 years, 627 trade dates). The strangle results use 2022-01 → 2026-07.
  Short, and both contain the 2026 melt-up.
- **Regime dependence cuts both ways.** The long-vol edge leans on 2022, 2024
  and 2025; **2023 — a smooth +240% grind — was −14%**, because a strangle needs
  movement and reversals. Do not annualize +44% as a durable expectation.
- **In-sample grids.** 120 DTE / 7.5% is the best *cell* in this sample. Trust
  the 120–150 DTE *region*, which is uniformly positive; not the exact cell.
- **EOD marks.** Option quotes are end-of-day snapshots. Intraday harvest spikes
  are neither captured nor charged, and the Monday-10:00 execution in the
  strategy docs cannot be priced from this data — Monday EOD is the proxy.
- **A negative result is not a universal one.** This says the blueprint fails
  *on SOXL over this window*. It works on SPX, and nothing here contradicts that.
  The distinguishing feature is the 3× levered single-sector underlying.
- **Commissions** are modeled in the condor grid but not in the strangle harvest;
  the 20% fill rule already charges bid/ask on every trade. The high-frequency
  harvest triggers (189 harvests at +5%) would be eroded most.
- **Test 4's halt** is expressed on SOXL IV, not VIX; no VIX series exists here.

---

## 5. Reproduce

```bash
python3 harvest_blueprint/blueprint_tests.py     # tests 1-5 -> harvest_blueprint/out/*.csv
```

Runs off the committed `pricing_lab/*.csv` tables — no `git lfs pull`, no
options download. Requires `pandas` and `numpy` only.

Supporting evidence, already in the repo:

| claim | source |
|---|---|
| delta-hedged long gamma is positive — the one options structure that pays | `harvest_blueprint/GAMMA.md`, `gamma_scalp_backtest.py`, `qa/gamma_scalp_report.txt` |
| the same trade on TQQQ is negative — out-of-sample instrument test failed | `harvest_blueprint/GAMMA.md` §4c, `gamma_tqqq_backtest.py`, `qa/gamma_tqqq_report.txt` |
| calendars/diagonals fail too (40/40 short legs negative) | `harvest_blueprint/CALENDAR.md`, `calendar_backtest.py`, `qa/calendar_report.txt` |
| condor grid, 37 configs, stops | `qa/r3_condor_report.txt`, `r3_iron_condor_backtest.py` |
| VRP by tenor, term structure, skew, spreads, wings, put bleed | `qa/pricing_lab_report.txt`, `volatility_pricing_lab.py` |
| VRP reproduced on a second window and on TQQQ | `vol_anatomy/harvestability.py` |
| SOXL's vol decomposition, 3× drag, overnight share | `vol_anatomy/README.md`, `anatomy.py` |
| long-strangle harvest grid, sizing, triggers | `call_spread_lab/FINDINGS_3_strangle_harvest.md` |
| debit-spread expectancy, signal gating, stop tests | `call_spread_lab/FINDINGS_2_long_side_and_signals.md` |
