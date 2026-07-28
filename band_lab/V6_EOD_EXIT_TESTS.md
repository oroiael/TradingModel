# V6 Test Program — End-of-Day Exit for the Churn Harvester Core

Current value: **force-flat at the close, always** (open position exits at
the last bar's close). Never varied. This rule is also a design principle,
not just a parameter: flat-overnight is what makes the sleeve structurally
neutral to the gap — the single biggest excursion channel — and is why the
sleeve earned the core role while the overnight-holding cycle strategy
was demoted to satellite. Any V6 change therefore faces a higher adoption
bar than a normal knob: an overnight-holding variant that *wins on
return* can still be **rejected on role** (the portfolio already has a
satellite for overnight exposure; the core's job is to not have any).

Context from prior programs that frames V6: the V5-T2 map showed entries
after 15:00 resolve as forced EOD exits 72% of the time, yet the V5-T4
cutoff test proved those late entries still carry positive edge — the
truncation is costly but the trades are worth having. V6 asks: is the
truncation itself the best resolution, or is there a better one?

Engine note: all tests run on the corrected engine only
(`v5_corrected_rerun.py` rules). Bars end 15:55–16:00; "the close" is the
last bar's close, a proxy for the official closing print (see T2).

---

## T1 runs FIRST — anatomy of the forced EOD exit (measurement)

**Mechanic.** Regenerate trade logs and isolate every trade that ends as
a forced EOD exit: count (share of all trades), mean/median return at the
forced exit, distribution by entry time, and — the pricing step — **what
would have happened if held**: mark each such position at (a) the next
day's open, (b) the next day's 11:00 bar, (c) first touch of the original
target/stop within the next 3 sessions. This one table prices every T3
variant before any simulation runs (the V11/V5 "conditional stat before
the rule" discipline — it has paid off twice).

**Data now:** fully sufficient — next-day bars are in the same file.
**Better with:** nothing at this depth.
**Depth:** hours. **Downside:** none — measurement.
**Expected shape (guess):** EOD-exit trades are ~10–15% of all trades,
slightly negative at the forced exit; the held-overnight mark is the
open question — gated days are high-vol days, so the overnight gap on
them is fat in BOTH tails.

## T2. Exit-time sweep (the small knob)

**Mechanic.** Force-flat at {15:30, 15:45, 15:55, last-bar close
(incumbent)}. Also run the incumbent with a 1-bar-earlier exit as an MOC
proxy sanity check. Small expected differences; the point is closing the
cell and quantifying how sensitive the sleeve is to end-of-day
microstructure before the cost model lands (the 15:30–16:00 window is
the day's second vol peak AND its second liquidity peak — effects fight).

**Data now:** sufficient. **Better with:** closing-auction (MOC) fill
data — the only way to know if "last bar close" flatters or punishes.
**Depth:** hours.
**Max upside:** ±0–3 bp/day; **max downside:** none — worst case confirms
the incumbent and documents the sensitivity.

## T3. Overnight-hold variants (the structural question)

**Mechanic.** Three prespecified variants, nothing else:
  a. **hold-to-open** — any open position at the close is held and sold
     at the next day's open (pure gap exposure, minimal holding change);
  b. **hold-to-resolution** — held position keeps its original target and
     stop working the next day(s), max 3 sessions, then market exit
     (the position becomes a miniature cycle-lot);
  c. **hold-winners-only** — held only if marked above entry at the
     close; losers still cut flat (asymmetric: keeps gap risk only on
     positions with cushion).
Each reported with the full tail battery: worst day, worst overnight gap
taken, maxDD, and the by-year table. Compare against T1's "what if held"
pricing for consistency.

**Data now:** sufficient (gaps and next-day bars all present).
**Better with:** halt/LULD event data — an overnight position through a
halted open is the unmodelable tail; 1-min data for next-morning exits.
**Depth:** half-day.
**Max upside (guess):** if the overnight drift after weak closes on
high-vol days is positive (mean reversion), +5–15 bp/day on the ~10–15%
of trades affected — material. **Max downside:** the gap tail — a single
−20% overnight move on a held position is −20% of the sleeve, vs the
−8% worst day the breaker currently guarantees. This is the test where
the ROLE argument can veto a winning backtest: adopting (a)/(b) makes
the sleeve's risk class overlap the satellite's.

## T4. Interaction cell — late entries under the winning exit rule

**Mechanic.** Only runs if T3 adopts anything: re-test the V5-T4
last-entry-cutoff question under the new exit rule. Rationale: "no
cutoff" won partly BECAUSE truncation-at-close is a mediocre resolution;
if late trades instead resolve overnight, their economics change and the
cutoff question reopens. One sweep, same cells as V5-T4.

**Data now:** sufficient. **Depth:** hours.
**Bounds:** small either way; exists to keep the parameter set coherent
rather than to find return.

## T5. Robustness + role protocol (meta-test)

**Mechanic.** For whatever T2/T3 propose: (a) yearly walk-forward
(variant selected on prior years only, OOS table decides); (b) tail
audit — the adopted rule's worst-gap-taken and a stress line: replay the
five biggest overnight gaps in the sample landing on a held position;
(c) **role review** — explicit statement of whether the sleeve is still
gap-neutral, and if not, what the combined core+satellite book's gap
exposure becomes (the two sleeves' overnight risks must not silently
stack). Adoption bar: OOS win in ≥4 of 5 years AND worst-day/DD not
materially worse AND the role review signed off in the results doc.

**Data now:** sufficient. **Depth:** hours (harness exists).

---

## Program summary

| test | depth | data now | decisive question | best case | worst case |
|---|---|---|---|---|---|
| **T1 EOD-exit anatomy** | hours | ✅ | what do forced exits cost, what would holding pay? | prices all of T3 in one table | — (measurement) |
| T2 exit-time sweep | hours | ✅ (MOC data better) | is last-bar-close the right print? | ±3 bp/day, sensitivity known | incumbent confirmed |
| T3 overnight holds | half-day | ✅ (halt data better) | is truncation the best resolution? | +5–15 bp/day on affected trades | gap tail; vetoed on role |
| T4 cutoff interaction | hours | ✅ | does the cutoff question reopen? | coherent parameter set | — |
| T5 robustness + role | hours | ✅ | does it survive OOS, tails, and the role review? | adoption evidence | reverts to flat-at-close |

**Recommended order: T1 → T2 → T3 → T4 → T5.**

---

# RESULTS (run 2026-07-28, `v6_eod_exit_tests.py` → `out/v6_results.csv`,
# `out/v6_eod_trades.csv`; corrected engine, start 11:00)

## T1 — the truncation is the worst possible resolution

Forced EOD exits are **18.7% of all trades** (439 of 2,342; they occur on
59% of traded days) and cost **−82.9 bp** on average at the forced print
(72% negative). Every held alternative marks better: next open −53.6 bp
(+29.3 per trade), next-day 11:00 −34.6 bp, worked-to-resolution −38.5 bp
mean with a **median of +100 bp** — more than half of truncated positions
hit their full +1% target within a median of ONE further session. The
overnight mean-reversion on these stalled positions is real.

## T2 — incumbent confirmed

flat 15:55 and last-bar close are statistically identical (58.4/2.88 vs
58.9/2.84); exiting earlier costs monotonically (15:30 → 51.3 bp). Cell
closed.

## T3/T5 — overnight holds WIN on return and are REJECTED on role

| variant | bp/day | Sharpe | worst day | worst o/n gap taken |
|---|---:|---:|---:|---|
| incumbent flat-at-close | 58.9 | 2.84 | **−8.0%** | none |
| (a) hold-to-open | 76.1 | 2.79 | −13.6% | −13.6% |
| (c) winners-only | 58.4 | 2.67 | −10.4% | −11.1% |
| (b) hold-to-resolution ≤3d | 84.9 | 3.04 | −13.6% | (same channel) |

The walk-forward picks (b) in 4 of 5 years (OOS 77.4 bp, Sharpe 2.89) —
the return case is genuine. The adoption bar was prespecified as
"worst-day/DD not materially worse AND role review": **worst day −13.6%
vs the breaker's guaranteed −8.0% is materially worse**, the sample's
gap stress shows −21.6% and −19.8% overnight gaps exist (2026-06-23,
2024-08-05) — a held position through one of those is a double-digit
single-print loss the intraday breaker can never see coming — and the
role review fails by construction: holding to resolution makes the core a
miniature cycle sleeve, stacking overnight risk the satellite already
owns. **Flat-at-close is retained.**

Two findings worth keeping alongside the rejection:
1. **The price of gap neutrality is now a number: ~17–26 bp/day** (what
   (a)/(b) would add). That is the insurance premium the core pays for
   its −8% worst-day guarantee and its role in the book. It was assumed
   worth paying; now it is *known* what it costs.
2. **Winners-only holding is disproved** — (c) adds nothing (58.4 vs
   58.9). The overnight value is entirely in holding LOSERS (they mean-
   revert); protecting winners overnight protects nothing. Any future
   revisit of this question should test *loser*-sizing rules (e.g.,
   hold-to-open at half position), which would take roughly half the
   +17 bp for roughly half the −13.6% tail — flagged as a possible
   follow-up under V11's sizing framework, not adopted here.

## T4 — moot (nothing adopted; the V5 no-cutoff verdict stands).

## Net effect

No change to the locked core — and that IS the result: every load-bearing
time rule in the sleeve (V5 start, V7 cap, V6 exit) has now been audited;
two moved (start, engine fix), two held (cap, EOD-flat), and the one
standing assumption that remained unpriced now has a price tag.

**Aggregate bounds:** best case — a winners-only overnight rule adds
~5–10 bp/day with a quantified, bounded gap tail and the role review
passes because only cushioned positions carry it. Worst case — flat-at-
close is confirmed and V6 closes with evidence, completing the audit of
every load-bearing time rule in the sleeve (V5 start, V7 cap, V6 exit).
Either outcome, T1's held-position pricing table permanently documents
what the EOD-flat principle costs — the number that has been assumed
worth paying since the sleeve was born. Total cost: under a day. The one
genuine risk in this program is adopting overnight exposure on backtest
numbers whose tail the sample cannot contain — which is exactly what the
T5 role review exists to veto.
