# V10 Test Program — Volatility Gate for the Churn Harvester Core

Current value: **trade only when ATR5 ≥ 6.0%**, where ATR5 = 5-session
trailing mean of (High−Low)/Open, known before the open. What IS tested:
the gate's existence and rough location (quartile decomposition −9/+30/
+20/+51 bp; 6% vs 8% thresholds; walk-forward survival) and the cliff-vs-
ramp question (V11-T6: the 5→7 ramp REJECTED — ATR 5–6 days are negative-
edge). What is NOT tested: the exact cutoff (6.0 was a round number), the
**lookback** (5 days, never varied), the **form** (absolute % vs
percentile vs vol-expansion ratio), the **input** (SOXL's own range vs
the sector's), and **hysteresis** (the gate flips ON/OFF at a cliff —
operational whipsaw never measured). One prior finding hangs over the
program: Sharpe-by-ATR5-bucket is **U-shaped** (just-above-gate days
Sharpe ~4.9, mid-vol trough ~1.1, wildest days 2.5) — unexplained.

Baseline for every comparison: the current locked core WITH the V9
direction-aware filter — **65.6 bp/traded-day, Sharpe 3.09**. Corrected
engine, start 11:00, breaker on. All thresholds trailing-computed where
the form requires history. Discipline: monotone cutoffs only — no
carve-outs of the mid-vol trough unless T1 shows it is structural, and
even then as a *documented finding for next review*, not a rule (a
non-monotone gate is a data-mining signature).

---

## T1 runs FIRST — fine-grained edge map (measurement)

**Mechanic.** All days (gate OFF), V9 filter applied, daily P&L binned by
ATR5 in 1-point bins (≤3, 3–4, …, 15–16, >16): n, mean bp, Sharpe, worst
day per bin, plus the same map split by year-group (2020–22 vs 2023–26)
to see whether the cutoff location is stable across vol eras. This
prices every cutoff and diagnoses the U-shape: if the mid-vol trough
(ATR ~7–9) persists in both era halves it is structural; if it flips, it
was noise and the U-shape stops driving decisions.

**Data now:** sufficient. **Depth:** hours. **Downside:** none.
**Expected (guess):** negative below 5, steep transition 5.5–6.5, the
trough partially noise; cutoff lands within ±0.5 of the incumbent.

## T2. Cutoff sweep

**Mechanic.** Absolute cutoff ∈ {4, 5, 5.5, **6**, 6.5, 7, 8}, all else
locked. Report bp/day, Sharpe, worst day, ON-day count, by-year. Plateau
verdict standard (challenger needs better Sharpe, no-worse worst day,
neighbor support, consistent years). Note the trade-off axis explicitly:
lower cutoffs buy more trading days (compounding calendar time) at lower
per-day edge — report **annualized calendar return** alongside per-day
stats, since a 60 bp/day gate that is ON 40% of days can lose to a 55
bp/day gate ON 60% of days in a compounding account.

**Data now:** sufficient. **Depth:** hours.
**Max upside:** a slightly lower cutoff adds ON-days at acceptable edge
→ +calendar return with flat Sharpe; guessed worth 0–15% more ON-days.
**Max downside:** none structural — 6.0 confirmed on a plateau.

## T3. Form and input source

**Mechanic.** Four prespecified forms, each swept over a small grid,
compared on identical protocol:
  a. **absolute** ATR5 ≥ X (incumbent form);
  b. **trailing percentile**: ATR5 ≥ its trailing-504d p ∈ {50, 60, 70} —
     adapts across vol eras, the case that 6.0% means different things
     in 2021 vs 2026;
  c. **vol-expansion ratio**: ATR5 ≥ k × ATR63, k ∈ {1.0, 1.15, 1.3} —
     gates on vol RISING vs its own regime rather than vol being high;
     directly motivated by the burst-clustering finding (P(high-vol |
     high-vol yesterday) = 38% vs 17% base);
  d. **input source**: incumbent 6% cutoff but ATR5 computed from SOXX
     (the sector index, ×3 to SOXL scale; `SOXX_5min_6Years.csv` is in
     the repo, needs LFS pull) — asks whether the signal is the ETF's
     own churn or the sector's vol. If (d) ≈ (a), the gate is robust to
     instrument quirks (halts, splits); if they differ, the difference
     IS the finding.
V9's lesson tempers expectations for (b)/(c) — relative forms lost
there — but the gate is a regime detector, not a day filter; the
question is genuinely different.

**Data now:** sufficient (+1 LFS pull for SOXX). **Depth:** half-day.
**Max upside:** an era-adaptive form that keeps the gate honest if SOXL
vol structurally shifts (the known A10 fragility); guessed ±0–3 bp/day
today, insurance value later. **Max downside:** multiple-comparison
surface — contained by the T5 walk-forward bar.

## T4. Lookback sweep

**Mechanic.** ATR lookback ∈ {3, **5**, 10, 20} sessions at the winning
form. To keep cells comparable, each lookback's cutoff is set to admit
the same trailing fraction of days as the winner admits (matching
ON-rates isolates the lookback's *timing* effect from its *level*
effect). Shorter lookbacks enter bursts earlier and exit earlier —
vol clustering says bursts run up to 11 sessions, so a 3-day ATR should
catch onset ~2 days sooner; a 20-day ATR would coast through the
1–2-week bursts the user first asked about.

**Data now:** sufficient. **Depth:** hours.
**Max upside:** lookback 3 catching burst onsets adds the FIRST days of
each burst — often the most violent, per the excursion clustering;
guessed +0–4 bp/day. **Max downside:** faster lookback = more whipsaw
(measured in T5); 5 confirmed as the compromise.

## T5. Hysteresis, whipsaw, and the validation protocol

**Mechanic.** (a) Whipsaw audit of the winner: ON/OFF transitions per
year, median episode length, P&L of the first and last day of each ON
episode (are edge-of-gate days different?); (b) hysteresis pair — gate
ON at the winning cutoff, OFF only below (cutoff − 1): fewer flips,
slightly more marginal days; compare; (c) full validation: yearly
walk-forward with form+cutoff+lookback selected on prior years only
(adoption bar: OOS ≥4 of 5 years no worse than incumbent), plateau
report, day-overlap mechanism analysis (which days flip and why), and
the desk restatement — the winner must reduce to one pre-open sentence.

**Data now:** sufficient. **Depth:** half-day.
**Max upside:** hysteresis is mostly operational polish (fewer
regime-flip decisions for the desk); the whipsaw audit may explain the
U-shape (if first-days-of-episodes are the +4.9-Sharpe cohort, the
"just-above-gate" mystery resolves as burst-onset alpha). **Max
downside:** none — reverts to the 6%/5d cliff.

---

## Program summary

| test | depth | data now | decisive question | best case | worst case |
|---|---|---|---|---|---|
| **T1 fine edge map** | hours | ✅ | where exactly does edge switch on; is the U-shape real? | prices all cutoffs; explains U | — (measurement) |
| T2 cutoff sweep | hours | ✅ | is 6.0 right, counting calendar time? | more ON-days, flat Sharpe | 6.0 confirmed |
| T3 form + input | half-day | ✅ (+SOXX LFS pull) | absolute / percentile / expansion / sector? | era-adaptive gate (A10 insurance) | forms lose again, absolute confirmed |
| T4 lookback | hours | ✅ | does ATR3 catch burst onsets? | +0–4 bp from burst first-days | 5 confirmed |
| T5 hysteresis + validation | half-day | ✅ | whipsaw cost; does the winner survive OOS? | adoption evidence + U-shape explained | reverts to incumbent |

**Recommended order: T1 → T2 → T3 → T4 → T5.**

---

# RESULTS (run 2026-07-28, `v10_gate_tests.py` → `out/v10_results.csv`,
# `out/v10_fine_map.csv`; V9-refined baseline 65.6 bp / Sharpe 3.09)

**Headline: the incumbent gate — ATR5 ≥ 6.0%, 5-day lookback, absolute
cliff, SOXL-derived — survives every test. V10 is the first program
where every knob passes its audit unchanged.**

**T1 — the U-shape is noise, not structure.** The fine map's mid-vol
trough flips sign between era halves (ATR 8–9 bin: −71 bp in 2020–22,
+62 bp in 2023–26); the only era-stable feature is the one the gate
already encodes — weak/negative below ~6, positive above. The U-shape
question is closed as unactionable.

**T2 — cutoff 6.0 retained; 5.5 documented as the growth alternative.**
Per-day edge rises monotonically with the cutoff (81 bp at ≥8) but
calendar compounding peaks LOW: the new calendar-CAGR column shows 5.5
compounds best (127%/yr vs 118.5% at 6.0) by buying 129 more ON-days at
~+22 bp each, at a cost of −0.24 Sharpe. By the prespecified Sharpe
standard 6.0 stands; **ATR5 ≥ 5.5 is recorded as a legitimate
growth-oriented setting** for an account prioritizing calendar
compounding over per-day quality.

**T3 — relative forms rejected; the gate is sector vol.** Percentile and
vol-expansion forms post high per-day Sharpe on so few days that
calendar returns collapse (34–61%/yr). The input-source test is the
finding: a SOXX-derived gate (×3) selects **777 of the incumbent's 787
days** and scores identically (65.1 vs 65.6 bp) — the gate measures the
semiconductor sector's vol regime, not SOXL quirks, making it robust to
instrument-specific data issues.

**T4 — ATR5 lookback confirmed; the ATR10 "win" was an artifact.** At
full-sample-matched ON-rates ATR10 looked better (Sharpe 3.28), but
with honest fixed cutoffs ATR10 ≥ 6.0 scores 63.9/2.98 vs the
incumbent's 65.6/3.09, the walk-forward drifts back to the incumbent by
2024, and the day-overlap shows a ~100-for-68 day swap with no mean
advantage. A textbook case of why matched-rate comparisons need a
fixed-cutoff re-test before believing them.

**T5 — whipsaw benign; burst-onset hypothesis REFUTED; hysteresis
rejected.** 29 transitions/yr, median ON-episode 5 days. Edge by
position in episode: first days are the WEAKEST (47.9 bp), last days the
STRONGEST (80.6 bp) — the dip-buy earns most as a vol burst fades, the
opposite of the burst-onset-alpha guess, and consistent with
mean-reversion after climax. Hysteresis (on 6 / off 5) dilutes with
sub-6 days (Sharpe 2.77) — rejected by standard; available as
operational polish if desk whipsaw ever becomes a practical problem.

## Decisions
1. Gate unchanged in every dimension: **ATR5 ≥ 6.0, 5-day lookback,
   absolute cliff, SOXL input.** V10 closed.
2. Recorded, not adopted: ATR5 ≥ 5.5 as the calendar-growth setting;
   SOXX-derived gate as a validated fallback input; hysteresis as
   optional operational polish.

**Aggregate bounds:** best case — a slightly lower or faster gate adds
10–15% more ON-days (calendar compounding) and/or +2–4 bp/day, the
U-shape is explained as burst-onset alpha, and the gate gains an
era-adaptive form as insurance against the one structural fragility the
assumptions register names (A10: a low-vol decade turns the sleeve off).
Realistic case — cutoff and lookback confirmed on plateaus, hysteresis
adopted as operational polish, and V10 graduates to closed. Worst case —
everything reverts to the incumbent 6%/5-day cliff with its mechanism
finally documented. Nothing here can damage the core: the gate only
decides which days to trade, and every candidate is benchmarked against
the current ON-day set. Total cost: about a day. This is the last
partially-tested variable on the status board with material open
surface — after V10, only the adaptive-levels question (V1/V3) and the
anchor family (V2) remain.
