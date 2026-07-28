# SOXL Intraday Churn Harvester — Strategy Specification (CORE, locked)

Status: **core strategy** as of 2026-07-28. Multi-day cycle strategy
(cycle_lab) demoted to optional satellite pending a regime kill-switch.

> **ENGINE CORRECTION (2026-07-28, found during the V5 program).** All
> results produced before `v5_corrected_rerun.py` used a simulator with a
> same-bar lookahead: the entry trigger could be set by the current bar's
> own high and the target filled by that same high. The corrected engine
> (trigger from prior bars only = a genuine resting limit; target fills
> from the next bar onward; same-bar stop still allowed) is now the
> reference. Net effect at the locked config: the core is *stronger* than
> previously reported (53.8→59.6 bp/day at the adopted start, Sharpe up),
> while early-morning starts were massively inflated (09:35 fell from a
> fictional 127 bp/Sharpe 5.7 to 68 bp/2.74 and fails the plateau rule).
> Re-verified on the corrected engine: 2-stop breaker (bigger win now:
> 53.8 vs 45.3 bp at 10:30), start-time verdicts, cutoff verdict.
> Direction-only conclusions (short-side rejection) were made under the
> *optimistic* engine and are conservative. Flagged for re-verification
> on the corrected engine: pyramid-vs-flat comparison (relative, both
> arms shared the bug), cap sweep exact values, cost estimates.

## 0. Locked definition

> On days when trailing 5-day average range (ATR5) ≥ 6% and the day is
> not filtered out (opening 30-min range in the top quintile AND the
> 10:00 print below the top third of that range — V9 program: violent
> up-mornings trade normally, violent down/mid mornings stand down):
> starting at **11:00** (V5
> program, corrected engine — plateau 10:30–11:30, 11:00 best: 59.6
> bp/day, Sharpe 2.87, walk-forward-supported), place a limit buy 1%
> below the intraday rolling high (prior bars only); on fill, exit at
> +1% (limit, fills from the next bar) or −4% (stop); repeat until 5
> trades **or 2 stop-outs**, whichever comes first (breaker re-verified
> on the corrected engine: 53.8 vs 45.3 bp/day at 10:30, worst day −8.0%
> vs −15.2%); no last-entry cutoff (tested, costs money); force-flat at
> the close. Long only, one position at a time, no overnight exposure.
> Sizing: flat fraction f of the sleeve per trade — f=1.0 growth-seeking,
> f=0.5 for a P(−30% DD/yr) ≤ ~5% risk budget (V11_SIZING_TESTS.md T5).

Backtest references (corrected engine): **59.6 bp/traded-day, Sharpe 2.87,
worst day −8.0%, maxDD −32.1%** on gated days 2020-07 → 2026-07;
walk-forward-supported (start-time OOS 60.6 bp / Sharpe 2.76; original
config-selection OOS retained ~83% of in-sample edge). Code:
`churn_harvest.py`, `regime_gate.py`, `walk_forward_and_combo.py`,
`v5_corrected_rerun.py` (reference engine), `v11_`/`v8_`/`v5_`/`v6_*.py`.

## 0.1 Variable status board (all audits as of 2026-07-28)

| var | parameter | final value | program / evidence | status |
|---|---|---|---|---|
| V1 | dip depth | 1% (fixed) | swept 1–3%; adaptive rejected (V1/V3 program: no migration) | **tested & confirmed** |
| V2 | entry anchor | session rolling high (prior bars) | vs failed band-edge fade; corrected engine | **tested** — VWAP/windowed anchors open |
| V3 | profit target | +1% (next-bar fills) | swept 1–2%; adaptive rejected on mechanism + OOS | **tested & confirmed** |
| V4 | stop | −4% **absolute** | swept 2/3/4% twice; scaled-stop test broke worst-day (−20%) — it's the absolute, not the ratio | **tested & confirmed** |
| V5 | start time | **11:00** | full program; plateau 10:30–11:30; WF OOS 60.6 bp | **tested & moved** (was 10:30) |
| V6 | EOD exit | flat at close | full program; overnight +17–26 bp REJECTED on role | **tested & held** — gap premium priced |
| V7 | trade cap | 5/day | swept 1–10; Sharpe peak at 5 | **tested & confirmed** |
| V8 | direction | long only | full program; short −17.7 bp honest fills; SSR 16.6% | **tested & closed** |
| V9 | day filter | skip OR30 > trailing 80th pct **unless 10:00 in top ⅓ of OR** | full program; boundary plateau-confirmed; direction rule +4.6 bp WF 5/5 | **tested & refined** |
| V10 | vol gate | ATR5 ≥ 6% (5d, cliff, SOXL input) | full program: cutoff/lookback/form/input/hysteresis all confirmed; U-shape closed as era-noise | **tested & confirmed** |
| V11 | sizing | flat f; **2-stop breaker**; pyramid for half-capital | six-test program + bootstrap | **tested & adopted** |
| V12 | sleeve role | day sleeve = core | four splits; WF (core robust, satellite fragile) | **tested** |
| — | engine | prior-bar trigger, next-bar target | lookahead bug found & fixed in V5 | **corrected** |

---

## 1. Variables — value, role, evidence, untested dimensions

### V1. Dip depth (entry trigger) — **1%** below intraday rolling high
- Role: defines "the churn" being harvested; directly sets trade frequency
  (~1.4 trades/day at 1%).
- Tested: 1 / 1.5 / 2 / 3% across the full grid (`churn_grid.csv`), every
  filter combination; walk-forward re-picked 1% in 4 of 5 years (2% once).
  Edge is a plateau: 1–2% all positive after gating; 3% starves trade count.
- Untested: adaptive depth (e.g., 0.25 × OR30 or 0.15 × ATR5, so the dip
  scales with the day's band); depth below 1% (needs 1-min data — 5-min
  bars can't resolve sub-1% triggers cleanly).

### V2. Entry anchor — **rolling intraday high since the open**
- Role: what a "dip" is measured from. Includes the pre-10:30 high.
- Tested: only implicitly — the failed control (`band_analysis.py` §4)
  anchored to the opening-range *low* (buy a static band edge) and lost
  −1.1%/day, vs +43.5 bp for the rolling-high anchor. That comparison is
  the single strongest structural result so far: **buy pullbacks in an
  advancing/flat tape, never catch the falling band edge.**
- Untested: VWAP anchor, previous-close anchor, rolling high over last N
  bars only (forgetting the morning), midpoint anchors.

### V3. Profit target — **+1%** from entry
- Tested: 1 / 1.5 / 2%. 1% best after gating; 1.5% close (picked once in
  walk-forward 2026); 2% degrades — matches the churn stat (15 completed
  ≥1% swings/day vs ~6 ≥2% swings).
- Untested: band-scaled targets (fraction of OR30), trailing exits,
  partial scale-outs, time-based exit ("out after N bars if neither side
  hit").

### V4. Stop — **−4%** from entry
- Role: the breakout-neutrality backstop; the only unbounded-risk control
  in the day.
- Tested: 2% / 4% / no-stop. 4% best blend (2% stops out inside normal
  churn; no-stop widens worst-day to −18.9%). Asymmetric 4:1 risk:reward
  is deliberate — win rate does the work.
- Untested: band-referenced stops (below day low, below OR low), time
  stops, vol-scaled stops.

### V5. Start time — **11:00** (bar 18; plateau 10:30–11:30)
- Tested: full program (`V5_START_TIME_TESTS.md`, corrected engine).
  Sweep 09:35–13:00: 11:00 best (59.6 bp/day, Sharpe 2.87, maxDD −32.1%)
  on a genuine plateau with 11:30 (2.85) and 10:30 (2.46); walk-forward
  start selection stays inside that plateau every year (OOS 60.6 bp,
  Sharpe 2.76). 09:35 rejected by the plateau rule — its lone-spike
  Sharpe sits next to the sweep's WORST cell (10:00, 1.68) and the
  morning open is where fill assumptions are least trustworthy.
  Last-entry cutoff rejected (monotonically costs money — late entries
  carry edge). Conditional start rejected (dominated). Finding the V5
  answer also exposed and fixed the same-bar lookahead bug (see header).

### V6. End-of-day flat — **close of last bar, always (retained on role)**
- Tested: full program (`V6_EOD_EXIT_TESTS.md`, corrected engine).
  Exit-time sweep: 15:55 ≈ close, earlier costs — incumbent confirmed.
  Overnight holds WIN on return (hold-to-open +17 bp/day; hold-to-
  resolution +26 bp/day, Sharpe 3.04, walk-forward-picked 4/5 years) and
  are REJECTED by the prespecified role bar: worst day −13.6% vs the
  breaker's −8.0%, sample contains −21.6%/−19.8% overnight gaps, and
  held positions re-merge the core into the satellite's risk class.
  **The cost of gap neutrality is now priced: ~17–26 bp/day.**
  Winners-only holding disproved (adds nothing — the overnight value is
  all in holding losers, which mean-revert; median truncated position
  hits its full target within one further session). Possible follow-up
  under V11 sizing: hold-to-open at reduced size for the loser cohort.

### V7. Max trades/day — **5**
- Tested: swept 1–10 (`cap_sweep.py`, `out/cap_sweep.csv`). On gated days
  the cap binds far more than first claimed (36% of days at cap 5).
  bp/day rises 6.8 → 43.5 from cap 1→5, then flattens (~47 at 8–10);
  Sharpe peaks at cap 5 (2.14) and decays above; worst day deteriorates
  −11.4% → −17% at cap 8. **Cap 5 confirmed as the risk-adjusted optimum**;
  6 is equivalent; 8+ is a small return add paid for in tail risk.

### V8. Direction & concurrency — **long only; pyramid variant for half-capital**
- Tested: full six-test program (`V8_DIRECTION_TESTS.md`,
  `v8_direction_tests.py`). Short side CLOSED: mirror-short edge is
  +7.6 bp only under invalid touch fills, −17.7 bp with honest fills
  (fill-style drag −25.4 bp), −23.1 bp via SOXS; SSR restricts real
  shorting on 16.6% of gated days. Long/short correlation −0.76 makes a
  25% SOXS overlay a legitimate optional smoothing dial (Sharpe 2.37,
  −5 DD pts, costs ~6 bp/day) but not core. Excursion-day momentum
  rejected (negative 3 of 7 years). **Adopted:** per-unit pyramiding
  (2 units, f/2 each, second unit 1% deeper, own exits) as the
  half-capital risk-budget config — 35.5 bp/day, Sharpe 2.60, +58% over
  flat f=0.5 at the same capital ceiling, positive all 7 years.

### V9. Day filter — **direction-aware OR30 filter** (adopted 2026-07-28)
- Rule: skip the day only if OR30 ≥ trailing 80th percentile AND the
  10:00 print sits below the top third of the opening range.
- Tested: full program (`V9_FILTER_TESTS.md`). Boundary 80 confirmed on
  a plateau (60–80 within noise; no-filter clearly worse); absolute and
  ATR-relative threshold forms rejected; recompute cadence robust.
  The decile map showed OR30 *size* was never the mechanism — the
  conditional split found the filtered days divide into up-mornings
  (+89.3 bp, Sharpe 3.58) and down-mornings (−66.2 bp, Sharpe −2.40),
  so direction, not violence, is what the filter was proxying.
  Refinement walk-forward-picked 5/5 years: 65.6 bp/day, Sharpe 3.09,
  +129 traded days, worst day unchanged. Recorded for next annual
  review (not adopted, post-hoc): mid-morning cohort is also positive
  (+113.5 bp, n=54) — "skip only bottom-third mornings" may be the
  fuller rule.

### V10. Regime gate — **ATR5 ≥ 6% — fully confirmed** (V10 program)
- Role: the largest single discovery: quiet tape = no edge; the churn
  income IS the vol.
- Tested (full program, `V10_GATE_TESTS.md`): cutoff 6.0 retained
  (Sharpe standard; **5.5 recorded as the calendar-growth setting** —
  127%/yr calendar CAGR vs 118.5%, −0.24 Sharpe); 5-day lookback
  confirmed after exposing a matched-rate artifact that flattered
  ATR10; percentile and vol-expansion forms rejected (calendar returns
  collapse); **SOXX-derived gate selects 777/787 identical days** —
  the signal is sector vol, validated as a fallback input; hysteresis
  rejected by standard; the U-shaped Sharpe anomaly closed as era-noise;
  burst-onset hypothesis refuted (episode LAST days are the strongest,
  +80.6 bp — the edge peaks as bursts fade).

### V11. Per-trade sizing — **flat fraction, 2-stop circuit breaker**
- Tested: full six-test program (`V11_SIZING_TESTS.md`,
  `v11_sizing_tests.py`). Adopted: 2-stop/day circuit breaker (better
  return, Sharpe, and tail simultaneously). Rejected: 1-stop breaker
  (forfeits the +22.8 bp post-first-stop recovery), anti-martingale
  (neutral), vol-targeting (dominated; Sharpe-by-vol is U-shaped),
  soft gate ramp (drag), tighter stops (Sharpe 2.15 > 2.07 > 1.71 for
  4/2/3%). Leverage: bootstrap says P(−30% DD/yr) = 46% at f=1.0 —
  f≈0.5 is the largest drawdown-budgeted setting.

### V12. Sleeve allocation — day sleeve as core
- Tested: the four splits above; every dollar moved cycle→day raised CAGR
  and cut max DD (43.0%/−81.8% at 150/0 → 53.7%/−22.9% at 0/150); sleeve
  correlation 0.28.

---

## 2. Assumptions register

| # | Assumption | Risk if wrong | Status |
|---|---|---|---|
| A1 | Limit buys at the trigger fill when the 5-min low touches it; gap-throughs fill at the bar open (favorable). | Fill rates in fast tape lower than modeled; queue position ignored. | **Untested** — needs 1-min/tick data or paper trading. |
| A2 | Within a bar that spans both stop and target, the stop is taken first (conservative), but true sub-bar sequencing is unknown. | Cuts both ways; net effect unknown. | Untested; 1-min data would mostly resolve it. |
| A3 | Zero commissions/slippage. ~1.4 trades/day × 252 → ~$700–1,400/yr at $1–2 per round trip, plus spread. SOXL spread ≈ 1–2¢ on a $158 stock ≈ 1 bp/side. | At $50K+ per trade, total drag ≈ 3–5 bp/traded-day — i.e., ~10% of the OOS edge. Material but not fatal. | **Not modeled** — top gap in the backtest. |
| A4 | 5-min IBKR RTH bars are accurate; 2021 15:1 split adjusted in-code; no other corporate actions distort the series. | Verified: only the split and real market shocks appear in the discontinuity scan. | Verified. |
| A5 | Liquidity/capacity: SOXL trades ~$1–3B/day; sub-$1M orders have negligible impact. | Fine at $150K–$1M scale. | Reasonable, unverified. |
| A6 | No overnight positions ⇒ no margin, no gap risk, no borrow. PDT rules satisfied ($150K ≫ $25K). | — | Structural. |
| A7 | The strategy family (long dip-buy mean reversion) was chosen after seeing the OR-fade fail **on the same data**. Walk-forward validates parameters, not the family choice. | Residual data-snooping bias that no in-sample test can remove. | Mitigable only by live/paper forward performance. |
| A8 | ATR≥6% gate and OR30-quintile filter use full-sample constants in the fixed-config results (walk-forward recomputed the OR30 threshold from train data; the 6% was fixed throughout). | Small; walk-forward stability suggests low sensitivity. | Partially validated. |
| A9 | Taxes ignored (all gains short-term). | Materially changes net returns by holder; not a model question. | Out of scope. |
| A10 | Regime continuity: SOXL keeps existing, keeps 3x leverage, semis stay volatile. A decade of 4% ATR5 would leave the gate off most of the time (by design — it fails safe to cash). | Opportunity cost, not loss. | Structural, fails safe. |

---

## 2.5 Trade Mechanics — Trading Desk Instructions (IBKR Pro, Fixed pricing)

Written as a runbook: a desk (or bot) following only this section should
reproduce the backtested behavior. Instrument: SOXL, regular trading hours
only, US/Eastern times throughout.

### Account prerequisites
- IBKR Pro, **Fixed** pricing, **margin-type account** — not for leverage
  (none is used) but because up to 5 same-day round trips re-use proceeds;
  a cash account risks free-riding/settlement violations.
- Equity above the $25K PDT floor (the sleeve is a pattern day trader by
  design). At the reference $150K sleeve this is a non-issue.
- No short permissions, no options permissions needed. Nothing is ever
  held overnight, so no overnight margin requirement applies.

### Step 1 — pre-open gate (before 09:30, ~2 minutes)
Compute **ATR5** = average over the last 5 completed sessions of
(session High − session Low) / session Open × 100.
- **ATR5 ≥ 6.0 → the sleeve is ON today.** ATR5 < 6.0 → OFF: no orders
  today, re-check tomorrow. (Roughly half of all days are ON; in violent
  regimes it stays ON for weeks — e.g. 13.9% at the data's last date.)
- Scheduled half-days (early closes): treat as OFF.

### Step 2 — 10:00 checkpoint: opening-range filter (direction-aware)
Compute **OR30** = (High − Low of 09:30–10:00) / 09:30 Open × 100.
Compare to the **trailing 80th percentile** of OR30 (recompute monthly
from the last 2 years; currently ≈ **5.4%**).
- OR30 below the threshold → proceed (normal day).
- OR30 at/above the threshold → check WHERE the 10:00 print sits inside
  the 09:30–10:00 range: **top third → proceed** (violent up-mornings
  are among the best dip-buy days: +89 bp mean, V9 program); **middle or
  bottom third → stand down for the day** (down-morning violence is the
  one cohort with genuinely negative edge, −66 bp).
- Do NOT trade between 09:30 and 11:00 regardless — the morning is
  observation only (it builds the session high the trigger hangs from).

### Step 3 — 11:00 activation: the resting entry order
- Let **H** = the session high so far (09:30 → now, RTH prints only).
- Maintain a **resting BUY LIMIT at 0.99 × H**, size = floor(f ×
  sleeve equity / limit price) shares (f = 1.0 growth setting; see
  Sizing below).
- **Ratchet rule:** every time SOXL prints a new session high, raise the
  limit to 0.99 × (new H). The limit only ever moves UP. This is not a
  native IBKR order type: automate via API (modify order on new-high
  events; 5-minute polling matches the backtest) or manage manually.
  IBKR's native "trailing buy" trails the low, not the high — do not use
  it, it is a different trade.

### Step 4 — on fill: bracket immediately (OCA)
The instant the entry fills at price **E**, place an OCA
(one-cancels-all) pair:
- SELL LIMIT at **1.01 × E** (the target), and
- SELL STOP at **0.96 × E** (stop-market; accept slippage — the 4% stop
  exists for disaster days, precision is not the point).
While a position is open, the entry limit stays pulled (one position at
a time). The backtest books target fills no earlier than the bar after
entry; a real resting limit may occasionally do better — acceptable.

### Step 5 — counters and the circuit breaker
Maintain two counters from 11:00, reset daily:
- **Fills (entries): max 5.** After the 5th entry resolves, done for the
  day.
- **Stop-outs: max 2.** The moment the second stop fires, cancel all
  orders, done for the day. This breaker is load-bearing: it converts
  the worst day from −11%+ to the −8% design guarantee, and the measured
  edge after a second stop is negative — there is no discretion here.
After every exit (target or first stop), recompute H (it may have risen
while in-position), re-place the entry limit at 0.99 × H, and re-arm.

### Step 6 — 15:55–16:00: flatten, no exceptions
If a position is open at 15:55, replace the bracket with a market sell
(or MOC order). **Nothing is ever held overnight** — this rule was
re-challenged with data and retained deliberately: holding would add
~17–26 bp/day and was rejected because the sample contains −20%+
overnight gaps and the sleeve's role in the book is to carry zero gap
risk. The forced sale of a loser at the close is the insurance premium,
pre-paid knowingly.

### Sizing (from the V11/V8 programs)
- **Growth setting: f = 1.0** — each entry uses the full sleeve equity.
  Accept: worst day −8%, maxDD ≈ −32% on active days, and a bootstrap
  P(−30% DD within a year) near a coin flip.
- **Risk-budget setting: per-unit pyramid at half capital** — two units
  of f = 0.5: first unit at the normal trigger, second only if price
  falls another 1% below the first entry; each unit carries its own
  +1%/−4% bracket; the breaker counts unit-stops. (35.5 bp/day at
  Sharpe 2.60 — dominates flat half-size.)
- **Never trade above f = 1.0.** Leverage was tested and rejected:
  Sharpe is flat in f, so margin buys tail risk and nothing else.

### Costs at IBKR Pro Fixed (why this account type is fine)
Confirmed against the published IBKR schedule (uploaded 2026-07-28):
Fixed = $0.005/share, **$1.00 min per order, max 1% of trade value**
(never binds at our sizes), exchange/clearing bundled, regulatory fees
(SEC + FINRA TAF, sells only) passed through — ~0.35 bp. At the
reference sleeve ($150K, ~950 shares at $158): ≈ $4.75/side commission
+ ≈ $4.30 SEC/TAF on the sell ⇒ **≈ $14 ≈ 0.9 bp per round trip**. With
~3.1 fills/day that is ~3 bp/day of commission against a 59.6 bp/day
gross edge (~5%). Spread cost: entries and targets are resting limits
(earn or neutral); stops and EOD flattens cross the spread (~0.6
bp/side at a 1¢ spread). Realistic all-in drag ≈ 4–7 bp/day ⇒ **expected
net ≈ 52–56 bp per traded day**. Cost scales DOWN with account size
(the $1 minimums stop binding); below ~$20K/trade the minimums start to
bite — this sleeve should not run under ~$25K for cost as well as PDT
reasons. Aside: at this sleeve's ~125K shares/month, IBKR Pro **Tiered**
($0.0035/share bracket) with maker rebates on the resting entry/target
limits could shave the commission line further — an optional account
optimization, not a requirement; all published numbers assume Fixed.

### Standing prohibitions (each closed by a test, not by taste)
1. No trading before 11:00 (V5 — and the 09:35 mirage was a sim bug).
2. No entries on OR30-filtered or gate-off days (V9/V10 — the edge on
   those days is negative, not merely smaller).
3. No shorts, in any wrapper, including SOXS (V8 — −17.7 bp/day under
   honest fills; SSR binds 16.6% of gated days anyway).
4. No overnight positions (V6 — priced and rejected on role).
5. No third stop, no "one more trade" past the counters (V7/V11).
6. No leverage (V11-T5).

### Monitoring (live vs. backtest)
Log every fill. Weekly, compare: fills/day (expect ≈ 3–3.5 on ON days),
target-hit share (expect ≈ 75–80%), net bp/traded-day (expect ≈ 50s
with wide variance — single weeks prove nothing). Investigate structural
breaks, not noise: a month of fill counts far off the expectation means
the market or the execution, not luck, has changed. Re-run the
walk-forward yearly with the new data before re-committing capital.

## 3. Should we build a big combinatorial search engine?

**Short answer: yes to a targeted harness, no to brute-force permutation
mining.** The evidence from our own results:

**Against brute force.** (1) The edge sits on a plateau — dip 1–2%, target
1–1.5%, stop 4%, gate 6% all work, and walk-forward kept re-picking the
same region. Finer tuning of these knobs is harvesting noise: in-sample
already overstates OOS by ~17% (43.5 → 36.3 bp), and every additional
searched combination widens that gap (more selection bias, thinner
samples). (2) The gated sample is only ~750 trading days; a 6-parameter
exhaustive sweep runs thousands of configs against 750 observations —
guaranteed false positives. (3) The two structural discoveries so far
(rolling-high anchor beats band-edge fade; vol gate) came from hypothesis →
test, not from sweeping.

**For a targeted harness.** The valuable untested dimensions are
*structural*, not numeric: entry anchor (V2), adaptive/band-scaled
levels (V1/V3/V4), start-time (V5), the short side (V8), within-sleeve
sizing (V11), and the fill/cost model (A1–A3). Each is a handful of
variants, not millions — but each needs the same expensive scaffolding:
walk-forward evaluation by default, cost model, plateau reporting,
year-by-year robustness. That scaffolding is ~80% written across
`churn_harvest.py` / `regime_gate.py` / `walk_forward_and_combo.py`;
consolidating it into one harness is roughly a day of work and every
future idea then gets an honest OOS verdict automatically.

**Recommended build, in order of expected payoff:**
1. **Cost & fill module** (A3, A1): commissions, spread, and a
   pessimistic-fill mode. Changes the headline number; everything else is
   relative comparison. Cheap.
2. **Unified sweep-with-walk-forward harness**: any config grid in, OOS
   table + plateau map out; hard cap ~6 free parameters per experiment;
   report neighborhoods, never single best cells.
3. **1-minute data for 1–2 key years** (2022, 2026): validates A1/A2 and
   opens sub-1% dip depths — the one place where "more resolution" could
   genuinely raise capacity of the edge.
4. **Structural variant queue** through the harness: adaptive dip/target
   (× OR30), start-time sweep, band-referenced stops, short side, sizing
   rules.
5. **Not recommended**: genetic/pattern-mining searches over rule
   combinations, indicator zoos, or grids beyond ~10³ configs — with 750
   gated days the discovery rate of real effects at that scale is near
   zero and the false-discovery rate is near one.

Decision gate: after step 2, any variant must beat the locked core by a
margin OOS (> ~5 bp/day net of costs) across ≥4 of 5 walk-forward years to
replace it. Otherwise the core stays as specified in §0.
