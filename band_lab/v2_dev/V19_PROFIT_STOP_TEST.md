# V19 — The day profit stop: should a sleeve stop once it is up X%?

**Line:** v2.0-dev (DEVELOPMENT). Nothing here changes v1.0 production.

**Status: DIAGNOSTIC — complete, NOT ADOPTED, and never a candidate.**

> This document breaks the house pattern in one way that has to be stated
> plainly. `README.md` requires an adoption bar written and signed off *before*
> a program runs. **No bar was written for V19**, so no result here is eligible
> to change v1.0 no matter how it had come out. It ran as a diagnostic in answer
> to a direct question. §6 records what a real V19 would still need — and why
> nobody should bother.

Run: `python3 band_lab/v2_dev/profit_stop_test.py`

---

## 1. The question

Stop opening new positions once the day's realised P&L reaches +1% (or +0.5%)
of sleeve capital; otherwise follow the existing rules to the close.

It is a fair question to ask, because the sleeve's existing breakers are
**asymmetric**. It truncates a day downward twice — V11's 2-stop breaker and
§12's `DAY_LOSS_KILL` at −8.5% — and upward never. Nothing in the variable
board (V1–V12, V16–V18) has ever tested an upward truncation. The nearest
neighbour is V7, the trade cap, which truncates by *count* and is indifferent to
whether the day is up or down.

## 2. What the rule actually is (D0) — and it is not what it looks like

Under the backtest config the sleeve sizes off the fill price with fractional
shares, so **a target trade returns exactly `f × target_pct` = 1.00% of sleeve
capital**, and a stop-out returns −4%. Realised day P&L at the only moment the
rule is consulted — `_arm`, on the exit event, with the sleeve flat — is
therefore a sum of `+1`s and `−4`s. The rule reduces to:

> **"stop after `ceil(threshold / 1%)` winning trades"**

This is fatal to the distinction the question drew. **+0.5% and +1.0% are the
same rule.** Both fire after the first winner. Nothing in the strategy can
produce a day that sits between them, because nothing produces a partial
winner: the target is the only profitable exit that re-arms, and it always pays
exactly 1%. The sweep confirms it — 0.25%, 0.50%, 0.75% and 1.00% return
byte-identical results in both sleeves.

It also means a +1% threshold sits exactly on top of a quantity that, in binary
floating point, lands on `0.009999999999999998` about as often as on `0.01`.
Without an epsilon the rule would mean "after one winner" or "after two"
depending on rounding noise in the entry price — a 100 bp/day difference decided
by nothing. `SleeveStateMachine.day_profit_reached` carries that epsilon and
says why.

## 3. The trades a stop deletes (D1) — the whole question, in one table

A profit stop does exactly one thing: it deletes the trades taken after the day
was already up X. Whatever those trades earn is what the stop costs. 1-minute
fills, net of V17's per-fill cost, 2022-01 →.

| threshold | trades cut | % of all | **mean net bp** | win rate | bp/ON-day lost | *vs the trades it keeps* |
|---|---:|---:|---:|---:|---:|---:|
| **SOXL** — no stop: 39.3 bp/ON-day, 2,157 trades, 12.4 bp/trade |
| 0.25 – 1.00% | 1,122 | 52% | **+17.3** | 74.5% | −28.6 | *7.0* |
| 1.50 – 2.00% | 634 | 29% | **+15.2** | 74.3% | −14.2 | *11.2* |
| 3.00% | 317 | 15% | **+12.5** | 74.4% | −5.8 | *12.4* |
| 4.00% | 123 | 6% | **+12.3** | 75.6% | −2.2 | *12.4* |
| **SOXS** — no stop: 30.3 bp/ON-day, 2,290 trades, 9.1 bp/trade |
| 0.25 – 1.00% | 1,241 | 54% | **+14.9** | 75.0% | −26.7 | *2.4* |
| 1.50 – 2.00% | 751 | 33% | **+17.5** | 75.2% | −19.0 | *5.0* |
| 3.00% | 406 | 18% | **+17.9** | 75.6% | −10.5 | *7.2* |
| 4.00% | 168 | 7% | **+11.7** | 73.2% | −2.9 | *8.9* |

**The trades a profit stop deletes are the best trades the strategy has.** At
the thresholds asked about, they earn +17.3 bp against +7.0 for the trades kept
(SOXL) and +14.9 against +2.4 (SOXS) — more than double, and on SOXS six times.
Half of all round trips sit in that row.

The mechanism is not mysterious once stated. A day that has already produced a
winning round trip *is an oscillating day*, and oscillation is the entire regime
this mean-reversion strategy exists to harvest. The first winner is not a
warning that the day is used up; it is the strongest evidence available that the
day is the right kind. Stopping there systematically cuts short exactly the
sessions the strategy is built for — which is also why V2 measured instant
re-entry at +47.9 bp of a 65.6 bp edge.

## 4. The sweep (D2)

| threshold | net bp | vs incumbent | Sharpe | ΔSharpe | MaxDD | **worst day** | fills/d | days bound |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **SOXL** incumbent | 39.3 | — | 2.01 | — | −40.6% | **−8.02%** | 3.18 | — |
| 0.25 – 1.00% | 16.1 | **−23.2** | 1.29 | −0.72 | −31.3% | **−8.02%** | 1.35 | 75-77% |
| 1.50 – 2.00% | 27.4 | −11.9 | 1.73 | −0.28 | −38.9% | **−8.02%** | 2.16 | 50-52% |
| 3.00% | 34.3 | −5.0 | 1.93 | −0.09 | −34.9% | **−8.02%** | 2.68 | 31% |
| 4.00% | 37.1 | −2.2 | 1.96 | −0.05 | −41.7% | **−8.02%** | 3.00 | 19% |
| **SOXS** incumbent | 30.3 | — | 1.54 | — | −36.5% | **−8.06%** | 3.31 | — |
| 0.25 – 1.00% | 1.8 | **−28.5** | 0.15 | −1.40 | −42.4% | **−8.06%** | 1.33 | 72% |
| 1.50 – 2.00% | 10.7 | −19.6 | 0.69 | −0.85 | −49.4% | **−8.06%** | 2.15 | 51% |
| 3.00% | 19.6 | −10.7 | 1.12 | −0.42 | −42.1% | **−8.06%** | 2.70 | 36% |
| 4.00% | 27.4 | −2.9 | 1.46 | −0.09 | −37.4% | **−8.06%** | 3.07 | 25% |

Four things, in descending order of how decisive they are:

1. **The result is monotonic in the direction of doing nothing.** Every
   threshold loses, and the loss shrinks as the threshold rises out of reach.
   The best version of this rule is the version that never fires. That is the
   signature of a lever with no edge at all — not a lever mis-tuned.

2. **The worst day is identical at every threshold, in both sleeves, to two
   decimal places.** This is the argument that should end the discussion. A
   profit stop can only fire on a day that is *already winning*, so it has
   literally no effect on the days that hurt. It buys no downside protection,
   because it is structurally incapable of acting on the downside. If the goal
   is "stop the 8/12-shaped days", this rule cannot touch them.

3. **Sharpe falls at every threshold in both sleeves.** So the loss is not a
   return-for-risk trade being made badly — there is no risk reduction being
   bought. SOXS at the asked-for thresholds keeps 6% of its return (30.3 → 1.8
   bp) for a Sharpe of 0.15.

4. **Drawdown is mixed and mostly worse.** SOXL improves (−40.6% → −31.3%) but
   SOXS deteriorates (−36.5% → −42.4%) at the same thresholds — the sleeves
   disagree in *direction*, the same structural failure that closed V1 in V16.
   Cutting winners short does not shrink drawdowns; it removes the gains that
   were climbing out of them.

## 5. Per-year consistency (D3)

At the thresholds asked about: **0 of 5 years positive, in both sleeves.**

| | 2022 | 2023 | 2024 | 2025 | 2026 | wins |
|---|---:|---:|---:|---:|---:|---:|
| SOXL @ 0.25–1.00% | −42.9 | −6.1 | −23.5 | −2.1 | −41.3 | 0/5 |
| SOXS @ 0.25–1.00% | −48.9 | −11.6 | −3.3 | −32.2 | −55.9 | 0/5 |

V16 R4.2 established that walk-forward is not protective on this dataset, so
this is a consistency check rather than evidence. It is worth reading only
because it is unanimous: there is no year, in either sleeve, where the rule
would have helped.

## 6. What a real V19 would need — and why there should not be one

For completeness, since no adoption bar was prespecified: a genuine V19 would
need a bar fixed before the run, per-**calendar**-day accounting if the rule
ever became day-selective, and the V16 R4.2 caveat carried explicitly.

**None of that is worth doing.** D1 closes the question on mechanism, not on
arithmetic: the deleted trades have *higher* expectancy than the kept ones, in
both sleeves, at every threshold, in every year. A parameter search over a rule
whose marginal population is better than its retained population cannot produce
a winner — it can only produce a threshold high enough that the rule stops
firing, which is what the 4.00% row is.

**V19 is closed.** The asymmetry noted in §1 is real but correctly directed: the
downside breakers exist because a −4% stop and a −8.5% day are events the
strategy must survive, while a +1% day is the strategy working.

## 7. What changed in the production code

`SleeveConfig` gained `day_profit_stop`, defaulting to `None` — off, and the
§12 behaviour. Production is bit-identical and asserted so: `replay.py`'s Stage
1 equivalence and `phase1/parity.py`'s 16 published §8 numbers reproduce
unchanged. The live engine constructs `SleeveConfig` without the field
(`engine.py:pre_open`), and `spec_constants.validate_config` refuses any config
carrying a non-`None` value, so the production path cannot drift into it.

The check lives in `SleeveStateMachine._arm`, beside the two existing breakers,
because `_arm` is the single funnel through which a resting entry can exist.
