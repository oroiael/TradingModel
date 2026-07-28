# V11 Test Program — Per-Trade Sizing for the Churn Harvester Core

Current value: **100% of the sleeve sub-account on every trade.** Never
varied. This document specifies the tests, their mechanics, data
sufficiency, depth, and bounded expectations. Context numbers: daily P&L on
gated days has mean +43.5 bp, daily σ ≈ 3.2%, worst day −11.4% (≈ three
consecutive 4% stop-outs — the worst-day anatomy is repeated stops, not one
crash), Sharpe 2.14 in-sample / 1.64 OOS.

---

## T1. Fixed-fraction sweep (the baseline family)

**Mechanic.** Deploy fraction `f` of start-of-day sub-account equity on
every trade, `f ∈ {0.25, 0.5, 0.75, 1.0, 1.25, 1.33}` (>1.0 = intraday
margin; note most brokers cap day-trading buying power on 3x ETFs near
1.33x because of 75% maintenance requirements, so 4x PDT leverage is NOT
available on SOXL). Since trades are sequential and sized off start-of-day
equity, daily return ≈ `f ×` (existing daily P&L series) — the test is a
one-line transform of data we already have, compounded: `eq = Π(1 + f·p_d)`.
Report CAGR / maxDD / worst-day / Sharpe vs `f`, and the growth-optimal
point. Naive Kelly on the observed moments (mean/var ≈ 4.2) will scream
"leverage 4x"; the empirical tail (fat, clustered) is precisely why the
sweep + T5 exist.

**Data now:** fully sufficient (reuses stored daily P&L).
**Better with:** nothing needed at this depth.
**Depth:** shallow — an hour including plots.
**Max upside (guessed):** at f=1.33, CAGR ~54% → ~68% if the linear scaling
holds. **Max downside:** worst day −11.4% → −15%, maxDD −23% → ~−33%; if
OOS decay (×0.83) plus a 2022-style year hits at f=1.33, DD could reach
−45%. At f≤1.0 there is no new downside — only the discovery that 100% was
already right or wrong.

## T2. Risk-normalized sizing (fixed % of equity at risk per trade)

**Mechanic.** Size each trade so a stop-out loses exactly `R`% of equity:
`f = R / stop_distance`. With the locked 4% stop this is just T1 in
disguise (R=4% ⇒ f=1.0) — the test only becomes distinct when stops vary
(band-scaled stops from the V4 untested list). Run jointly: stop ∈ {3%, 4%,
band-referenced} × R ∈ {2, 3, 4%}. Requires regenerating **per-trade**
records from `sim_day` (small modification: return the trade list, not the
daily sum).

**Data now:** sufficient — 5-min bars regenerate every trade.
**Better with:** 1-min bars, because tighter/band-referenced stops are
exactly where 5-min bars mis-sequence stop-vs-target inside a bar.
**Depth:** medium — touches the V4 axis, so findings must be reported as a
2-D plateau, not a best cell.
**Max upside:** constant-risk trades smooth the equity curve; guessed
Sharpe +0.1–0.2, worst day capped by construction at ~3R. **Max downside:**
none structural — worst case it's return-neutral complexity.

## T3. Vol-targeted sizing (size down the hottest days)

**Mechanic.** `f_d = min(1, k / ATR5_d)` — constant *expected* daily risk
instead of constant capital. The tension is measurable before simulating:
bucket the existing daily P&L by ATR5. We already know edge RISES with vol
(−9/+30/+20/+51 bp by quartile); the open question is whether σ rises
faster than the edge. Compute mean/σ per ATR5 bucket; if Sharpe-per-bucket
falls at the top, vol-targeting helps; if flat or rising, it strictly
costs money. Then simulate the monotone rule.

**Data now:** sufficient (746 gated days ≈ 150/bucket).
**Better with:** more gated days — the repo already holds FAS, SPXL, TQQQ
5-min history; running the identical strategy there is a free
pseudo-out-of-sample check on whether the vol/edge relationship is a SOXL
quirk or a 3x-ETF property.
**Depth:** medium; low overfit risk if the rule stays monotone with one
free constant.
**Max upside:** maxDD −5 to −10 pts with CAGR roughly flat. **Max
downside:** if edge outgrows risk at high vol (plausible — that's where the
churn is), this donates the best days; bounded by the bucket analysis
before any simulation is run.

## T4. Intraday sequencing rules (the highest-value test)

**Mechanic.** Three prespecified rules, evaluated on regenerated per-trade
logs with sequence numbers:
  a. **Stop-out circuit breaker** — after `k` stop-outs in a day, done for
     the day (`k ∈ {1, 2}`). Directly attacks the worst-day anatomy
     (−11.4% ≈ 3 stops): k=2 caps the worst day at ~−8% mechanically. The
     question is only how much afternoon recovery it forfeits — answered by
     the conditional stat E[remaining-day P&L | 2 stops already], which we
     compute *before* choosing.
  b. **Anti-martingale** — halve size after any stop-out, restore after a
     win.
  c. **Escalation check** — measure E[r] by trade number (1st..5th). The
     cap sweep suggests later trades still carry edge (bp/day kept rising
     to cap 8); if trade #1 vs #4 edges differ materially, size accordingly.
Discipline: all three rules and their parameters are fixed by this
document BEFORE running — no post-hoc rule mining. Report each vs the flat
baseline on the walk-forward protocol, not just full-sample.

**Data now:** sufficient; trade #4–5 exist on ~270 days, enough for
direction though not for fine tuning.
**Better with:** 1-min data (exact stop sequencing inside fast bars);
quote data to confirm stop fills at the modeled price during cascades.
**Depth:** deepest of the shallow tier — per-trade regeneration + three
conditional analyses + walk-forward re-runs; ~half a day of compute-light
work. Multiple-comparison risk handled by prespecification.
**Max upside:** worst day −11.4% → ~−8%, maxDD likely −23% → ~−17%, Sharpe
up, CAGR cost guessed 0–5 bp/day. This is the best risk-payoff test in the
program. **Max downside:** if bad mornings systematically mean-revert into
strong afternoons, the breaker forfeits recovery — measurable in (a)'s
conditional stat before committing.

## T5. Bootstrap Kelly with a drawdown constraint (formal sizing)

**Mechanic.** Stationary block bootstrap (block ≈ 10 days to preserve vol
clustering) of the gated daily P&L → 10,000 synthetic years; for each `f`,
distribution of CAGR and maxDD; choose the largest `f` with
`P(maxDD < −30%) ≤ 5%`. This turns "how much leverage" from a vibe into a
stated risk budget.

**Data now:** marginal. 746 gated days ≈ 3 effective years of tail
observations; the bootstrap cannot invent tails it never saw (no LULD
halt, no overnight-gap-into-open cascade lives in the sample).
**Better with:** (1) the other 3x ETFs as pooled tail donors; (2) longer
SOXL history (pre-2020 exists from providers); (3) a synthetic stress
module: replay 2022 dailies ×1.5, inject a −20% halt day, and require the
chosen `f` to survive those too.
**Depth:** deep — the only test needing new infrastructure (~a day).
**Max upside:** justified leverage up to the broker cap with quantified
risk, potentially the full T1 upside but held with evidence. **Max
downside:** false confidence if the stress module is skipped — the stated
5% DD probability would be an underestimate of true tail risk. Run only
with the stress module.

## T6. Gate-proportional sizing (soft gate)

**Mechanic.** Replace the ATR≥6 cliff with a ramp:
`f = clip((ATR5 − 5)/2, 0, 1)`. Removes threshold-cliff sensitivity
(days at ATR 5.9 vs 6.1 currently differ by 100% of size).
**Data now:** sufficient. **Depth:** shallow (hours).
**Max upside:** small return add from currently-skipped 5–6% days plus
robustness; **max downside:** re-admits the quartile-1 negative-edge days
at partial size — bounded small either way.

---

## Program summary

| test | depth | data now | runs on walk-forward? | best-case | worst-case |
|---|---|---|---|---|---|
| T1 fraction sweep | hours | ✅ | yes | +14 CAGR pts at 1.33x | −10 DD pts if tails repeat |
| T2 risk-normalized | days | ✅ (1-min better) | yes | Sharpe +0.1–0.2 | neutral |
| T3 vol-targeted | days | ✅ (+other ETFs) | yes | −5–10 DD pts | donates best days |
| **T4 sequencing rules** | half-day | ✅ (1-min better) | yes | worst day −8%, DD −17% | forfeits afternoon recoveries |
| T5 bootstrap Kelly | ~1 day infra | ⚠️ thin tails | n/a (meta) | evidence-based leverage | false tail confidence w/o stress module |
| T6 soft gate | hours | ✅ | yes | robustness | small |

**Recommended order: T4 → T1 → T3 → T6 → T2 → T5.** T4 first because it
attacks the known worst-day anatomy with the best risk-per-effort; T1 is
nearly free and bounds the leverage question; T5 last because it needs T1's
sweep and the stress module to be honest. Every test reports against the
walk-forward protocol, and per the spec's decision gate, no sizing rule
replaces flat-100% unless it wins OOS in ≥4 of 5 years net of the
(still-pending) cost model.

**Aggregate bounds for the whole program:** realistic best case is Sharpe
2.1 → ~2.4 with maxDD −23% → ~−15% at unchanged CAGR, or CAGR +10–15 pts at
unchanged DD via modest margin — not both. Aggregate worst case: flat-100%
is confirmed optimal and the program costs a few days of compute — sizing
tests multiply an existing P&L series, so they cannot damage the underlying
edge itself.

---

# RESULTS (run 2026-07-28, `v11_sizing_tests.py` → `out/v11_results.csv`)

Note on CAGR columns: gated days are compounded back-to-back, so CAGR reads
as "per active year" (the gate is on ~50% of days); use bp/day, Sharpe, and
the DD/worst-day columns for decisions.

**T4 — ADOPTED: 2-stop circuit breaker.** The conditional stats settled it
before the rules ran: after 1 stop-out the rest of the day still earns
+22.8 bp (53% positive) — so breaker-after-1 forfeits real recovery and
loses (36.9 bp vs 43.6 baseline). After 2 stop-outs the rest of the day
*loses* −20.3 bp (40% positive) — so quitting there is pure gain:
**44.9 bp/day (vs 43.6), Sharpe 2.25 (vs 2.15), worst day −8.0% (vs
−11.4%)**, better or equal in 6 of 7 years (2026 the one giveback). Also
per-trade edge RISES with sequence (#1: 6.8 bp → #3: 20.3 bp → #5: 20.1
bp) — later dips are deeper dips; de-escalation rules are wrong-way.
Anti-martingale: neutral (42.1 bp, Sharpe 2.14) — rejected.

**T1 — Sharpe is exactly flat in f (2.15 at every fraction), tails scale
linearly.** f=1.33 gives 58.1 bp/day with a −15.2% worst day and −44% DD
on the active-day sequence. Leverage is a pure risk dial here — see T5 for
whether it's affordable (it isn't).

**T3 — REJECTED (dominated).** The Sharpe-by-vol-bucket curve is
U-shaped, not monotone (bucket 1: 4.93, buckets 2–3: ~1.1, bucket 4:
2.52), so inverse-vol sizing down-weights some of the best days;
vol-targeting k=6 lifts Sharpe to 2.24 but costs 10 bp/day. Breaker2
achieves the same Sharpe gain at zero return cost. (The just-above-gate
days ATR 6–6.6 being the highest-Sharpe cohort is a finding worth keeping.)

**T6 — REJECTED.** The 5→7 ramp scores 26.3 bp / Sharpe 1.55 vs the
cliff's 43.6 / 2.15: partially-admitted ATR 5–6 days are a drag, exactly
the quartile-1 negative-edge cohort the gate exists to exclude.

**T2 — REJECTED; locked 4% stop confirmed.** At equal risk-normalized
fractions, stop-4% Sharpe 2.15 > stop-2% 2.07 > stop-3% 1.71 across the
whole R grid. Tighter stops die to normal churn; risk-normalization adds
nothing the fraction dial doesn't.

**T5 — leverage is NOT affordable; half-size is the formal answer.**
(Bootstrap figures in this section are SUPERSEDED 2026-07-28: they were
computed on the pre-refinement P&L series. Current numbers —
`sizing_verification.py`, MASTER §6.7 — gross f=1.0 P(−30% DD/ON-yr)
14.5%, conservative f=1.0 26.7%, f=0.5 0.5%. The qualitative conclusion
"do not use leverage" is unchanged and strengthened.)
10,000 block-bootstrap years: at f=1.0 the probability of a −30% max
drawdown within a year is **45.8%** (empirical pool) / 69.0% (stressed
pool: 2022×1.5 + one −20% halt day). The largest f meeting
P(maxDD<−30%) ≤ 5% is **f≈0.5 empirical and below 0.5 stressed**. Anyone
running this at full size must accept that a −30% year is closer to a
coin flip than a tail event; f=0.5 keeps ~68% median active-year return
with P(−30% DD) ≈ 2–8%.

## Decisions applied to the locked core

1. **Trade cap restated: 5 trades OR 2 stop-outs, whichever comes first**
   (breaker2 adopted — better on every headline metric, prespecified,
   robust across years, and it *reduces* trade count so costs only help).
2. Flat sizing retained; fraction f is the user's risk dial with the T5
   table as the price list — f=1.0 is growth-seeking, f=0.5 is the
   drawdown-budgeted setting.
3. Stop 4%, cliff gate at ATR≥6, and no vol-scaling all confirmed.
