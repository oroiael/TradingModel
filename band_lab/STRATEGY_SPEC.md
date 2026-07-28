# SOXL Intraday Churn Harvester — Strategy Specification (CORE, locked)

Status: **core strategy** as of 2026-07-28. Multi-day cycle strategy
(cycle_lab) demoted to optional satellite pending a regime kill-switch.

## 0. Locked definition

> On days when trailing 5-day average range (ATR5) ≥ 6% and the opening
> 30-min range is not in the top quintile: starting at 10:30, place a limit
> buy 1% below the intraday rolling high; on fill, exit at +1% (limit) or
> −4% (stop); repeat until 5 trades **or 2 stop-outs**, whichever comes
> first (2-stop circuit breaker adopted from the V11 program: +1.3 bp/day,
> Sharpe 2.25 vs 2.15, worst day −8.0% vs −11.4%); force-flat at the
> close. Long only, one position at a time, no overnight exposure.
> Sizing: flat fraction f of the sleeve per trade — f=1.0 growth-seeking,
> f=0.5 for a P(−30% DD/yr) ≤ ~5% risk budget (V11_SIZING_TESTS.md T5).

Backtest references: in-sample 43.5 bp/traded-day, Sharpe 2.14 (2020-07 →
2026-07); walk-forward OOS 36.3 bp/day, Sharpe 1.64 (2022–2026, yearly
re-selection). Code: `churn_harvest.py`, `regime_gate.py`,
`walk_forward_and_combo.py`.

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

### V5. Start time — **10:30** (bar 12)
- Role: waits until the band is ~68% built and the excursion window (58%
  of steep moves fire 09:30–10:30) has passed.
- Tested: derived from the range-completion curve
  (`range_completion_by_time.csv`), NOT swept as a parameter. 10:00 /
  11:00 / 13:00 variants have never been run.

### V6. End-of-day flat — **close of last bar, always**
- Role: removes overnight gap risk entirely (gaps are the main excursion
  channel). Open positions at the bell exit at the last bar's close.
- Tested: not varied. Holding winners overnight, exiting at 15:55, or MOC
  order modeling have not been run. (Note: round-1 cycle results suggest
  overnight holds add return and add tail risk — that experiment would
  effectively re-merge the sleeves.)

### V7. Max trades/day — **5**
- Tested: swept 1–10 (`cap_sweep.py`, `out/cap_sweep.csv`). On gated days
  the cap binds far more than first claimed (36% of days at cap 5).
  bp/day rises 6.8 → 43.5 from cap 1→5, then flattens (~47 at 8–10);
  Sharpe peaks at cap 5 (2.14) and decays above; worst day deteriorates
  −11.4% → −17% at cap 8. **Cap 5 confirmed as the risk-adjusted optimum**;
  6 is equivalent; 8+ is a small return add paid for in tail risk.

### V8. Direction & concurrency — **long only, one position at a time**
- Tested: shorts never tested in the harvester. (Context: SOXL's 6-year
  drift is up; the failed OR-low fade was also long-only, so "short the
  band top" is genuinely unexplored, not rejected.)
- Untested: short side of the band, two-sided market-making variant,
  pyramiding on deeper dips.

### V9. Day filter — **skip OR30 top-quintile days** (threshold = trailing
80th percentile, known by 10:00)
- Role: removes days carrying the excursion signature (trend days the
  dip-buy would fight all day).
- Tested: none / orq5 / gap2 (|gap|>2%) / orq5+gap2 / orq5+excursion-lag
  across the whole grid. orq5 and gap2 are near-substitutes (both proxy
  "violent morning"); walk-forward alternated between them, both worked
  OOS. The 80th-percentile boundary itself was never swept, nor was
  combining with the 1.9×OR30 range forecast for position sizing.

### V10. Regime gate — **trade only when ATR5 ≥ 6%** (known before open)
- Role: the largest single discovery: the edge by ATR5 quartile is
  −9 / +30 / +20 / +51 bp/day. Quiet tape = no edge; the churn income IS
  the vol.
- Tested: quartile decomposition + 6% and 8% absolute thresholds
  (`regime_gate.csv`). 6% robust (7/7 years positive in-sample, survived
  walk-forward); 8% doubles bp/day but on 168 days with negative years —
  flagged overfit-prone.
- Untested: ATR lookback (5d fixed), relative gates (ATR5 vs its own
  percentile instead of absolute 6%), alternative vol inputs (overnight
  gap vol, SOX index vol, VIX), gate hysteresis (enter at 6%, exit at 5%).

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
