# SOXL Intraday Churn Harvester — Master Strategy Document

Version 1.0 — 2026-07-28. Prepared for third-party validation and live
implementation. Repository: `oroiael/TradingModel`, directory `band_lab/`
(research programs, results, and this document), `cycle_lab/` (data
loaders and the demoted satellite strategy).

---

## 1. Executive summary — in plain English

### What the trade is

Semiconductor stocks swing violently. SOXL is an ETF that multiplies
those swings by three, and SOXS is its mirror image — it rises exactly
when semiconductors fall. On a typical day SOXL travels about 6.7%
between its high and its low, and it reverses direction by 1% or more
roughly **fifteen times a day**. In six years of data there has not been
a single day without one of those swings.

This strategy is a machine for harvesting those reversals. It does one
simple thing, over and over:

> Wait until 11:00 in the morning. Watch the highest price the stock has
> reached so far today. Place an order to buy 1% below that high. If it
> fills, immediately place two exit orders: sell at 1% profit, or sell at
> 4% loss — whichever comes first. When you exit, do it again. Stop after
> five trades, or after two losses, whichever comes sooner. **Sell
> everything before the closing bell, every single day, no exceptions.**

That is the whole trade. It holds nothing overnight, uses no leverage, no
options, and no short selling.

Two further rules decide *whether to trade at all* on a given day, and
they matter as much as the trade itself:

1. **Only trade when the market is churning.** If the average daily swing
   over the last five sessions was under 6%, the strategy sits in cash.
   This turns it off roughly half the time — deliberately.
2. **Skip violent down-mornings.** If the first 30 minutes are unusually
   wild *and* the stock is sagging at 10:00, stand down for the day. This
   was the one day-type that reliably lost money.

Finally, the strategy runs on **both SOXL and SOXS at the same time**,
capital split evenly. Because the two move in opposite directions, a bad
day for one is usually a good day for the other.

### Why it works

**The money comes from timing, not from betting on direction.** That is a
strong claim, so here is the proof: the same rules applied to SOXS — an
instrument that lost essentially **100% of its value** over the six
years — still earned 57.7 basis points per trading day. If the strategy
were secretly just "being long a rising asset," SOXS would have destroyed
it. Measured against simply buying at 11:00 and holding to the close, the
strategy adds +39 bp/day on SOXL and +62 bp/day on SOXS. That difference
is the actual edge.

**The mechanism is staying invested below a stale ceiling.** The strategy
anchors to the highest price of the day, which never resets downward. On
a day that drifts lower it therefore keeps buying back in just beneath
that old high, repeatedly. We tested removing only this behaviour and
returns collapsed from 65.6 to 17.7 bp/day — **roughly three-quarters of
the edge is the willingness to keep re-entering**, not the "buy a 1% dip"
rule that appears on the surface.

**The volatility filter does real work.** Sorted by how choppy the
preceding week was, the quietest quarter of days *lose* money while the
wildest quarter earn about five times the average. The strategy simply
refuses to play when the game is not paying.

**The pair works because the strategy's own filter picks the direction.**
On mornings when SOXL sells off hard the filter benches SOXL — and those
exact days are SOXS's best (+152 bp average). The two sleeves end up
−0.70 correlated without ever being told about one another.

### The results

Six years of 5-minute data (2020–2026), after Interactive Brokers
commissions and estimated spreads, both sleeves at a 50/50 split:

| | |
|---|---|
| Days it trades | ~52% (in cash the rest of the time) |
| Typical trading day | ~3 round-trip trades |
| Winning days | ~64% |
| **Worst possible day** | **−8%** — hard-capped by design (two 4% stops, then it stops for the day) |
| Worst peak-to-trough loss | **−10.8%** out-of-sample |
| Out-of-sample Sharpe ratio | **4.08** (versus 2.20 for SOXL alone) |
| Weekly pattern | 64% of weeks profitable; the median week is small, the average is carried by volatile bursts |

Every one of the strategy's twelve rules was tested individually against
its alternatives, and each year's settings were chosen using only data
available *before* that year — so these are results the rules produced on
data they had never seen. In that out-of-sample test the pair beat the
single sleeve in **all five years**.

**What $150,000 would have become:** $8.6M over 5.5 years, with a peak
drawdown near 10%. That figure deserves heavy scepticism, and §6.4
explains why in detail — it assumes fills that 5-minute bars cannot fully
verify, ignores the practical limits of trading ever-larger size, and
covers a period containing two extraordinary volatility events. **The
defensible claims are the per-day edge (~50 bp net on days it trades) and
the risk profile (−8% worst day, ~−11% worst drawdown) — not the terminal
figure.**

### What could go wrong

If semiconductor volatility permanently subsides the strategy stops
trading and sits in cash, which is correct behaviour rather than a loss.
The genuine unknowns are whether real-world fills match the backtest —
the largest untested assumption in this work — and whether an edge
validated on the data that shaped it persists live. The recommended path
is paper trading, then small size, then scale; never straight to full
capital.

## 2. The instrument and the opportunity

SOXL moves in a wide intraday band: median daily range **6.7% of the
open** (IQR 4.9–9.1%), containing on average **15 completed ≥1% swings
per day** — there has not been a single 0-swing day in six years. The
band is built early (68% of the day's final range is set by 10:30) and
its width is predictable (day range ≈ 1.9 × the opening 30-min range,
correlation 0.62). Volatility clusters violently: P(high-vol day |
high-vol yesterday) = 38% vs a 17% base rate, with bursts up to 11
straight sessions. The strategy is a systematic harvester of that churn,
switched on only when the churn is rich enough to pay (trailing 5-day
range ≥ 6%) and switched off on the one morning type with measured
negative edge (violent *down*-opens).

## 3. What the trade actually is (mechanism)

The naive description — "buy 1% dips, sell +1% pops" — understates what
the audit found. The final mechanism picture, each element measured:

1. **Exposure below the high** (V2 program): the entry anchor is the
   session high, which never decays. After any exit, if price still sits
   ≥1% below that high, the strategy re-enters essentially immediately.
   These re-entries — 1–4% below the anchor — are the BEST trades in the
   book (31–33 bp/trade vs 12.8 bp for "true" fresh 1% dips). Removing
   instant re-entry collapses the edge from 65.6 to 17.7 bp/day.
   **The willingness to stay exposed below a standing high is ~73% of
   the edge.**
2. **The +1% cadence** (V1/V3): SOXL's harvestable reversion operates at
   a ~1% grain regardless of how wide the day is — adaptive levels were
   tested and rejected (the optimum does not migrate across band
   regimes).
3. **The volatility gate** (V10): edge by trailing-vol quartile is
   −9/+30/+20/+51 bp/day. Quiet tape = no edge. The gate is sector vol,
   not instrument vol (a SOXX-derived gate selects 777 of 787 identical
   days).
4. **The morning filter** (V9): violent down-opens (top-quintile opening
   range with the 10:00 print in the lower ⅔ of it) are the one cohort
   with negative edge (−66 bp/day); violent UP-opens are among the best
   days (+89 bp/day) and are traded.
5. **The 2-stop breaker** (V11): after two stop-outs, the measured
   rest-of-day expectation is negative (−20 bp); after one it is positive
   (+23 bp). Quitting at exactly two both adds return and converts the
   worst day from −11.4% to a structural −8.0% (2 × −4%).
6. **Flat overnight** (V6): holding stalled positions overnight would add
   17–26 bp/day and was rejected deliberately: the sample contains −21.6%
   and −19.8% overnight gaps, and the sleeve's design role is zero gap
   exposure. This is the insurance premium, paid knowingly, priced
   precisely.

## 4. The locked rules

Applied **independently to each sleeve** on that sleeve's own price data
(its own ATR5, its own opening range, its own session high). The sleeves
never reference each other.

> **Gate (pre-open):** trade this sleeve today only if its ATR5 ≥ 6.0%,
> where ATR5 = 5-session trailing mean of (High−Low)/Open. Skip
> scheduled half-days.
> **Filter (10:00):** compute OR30 = (09:30–10:00 High−Low)/Open. If
> OR30 ≥ its trailing-2yr 80th percentile (recomputed each session) AND the
> 10:00 print sits below the top third of that opening range → stand
> down for the day.
> **Trading window:** 11:00 → close. Maintain a resting buy limit at
> 0.99 × session high (ratchets up only, never down). On fill at E:
> OCA bracket — sell limit 1.01×E, sell stop 0.96×E. After any exit,
> recompute the session high and re-arm.
> **Counters:** stop this sleeve for the day after 5 entries or 2
> stop-outs, whichever comes first.
> **15:55–16:00: flatten, no exceptions.**
> **Structure:** run SOXL and SOXS sleeves in parallel, **w = 0.50**
> capital each (walk-forward validated, §9.5/V14). Sizing within a sleeve
> is a flat fraction f of that sleeve's capital — f=1.0 growth, lower f
> to reduce risk. Never above f=1.0. No pyramiding, no leverage, no
> shorts, nothing held overnight.

Recorded alternatives (tested, documented, not default): gate at 5.5%
(better calendar compounding, −0.24 Sharpe), SOXX-derived gate (validated
fallback input), pair weight anywhere in 0.375–0.75 (plateau; w≈0.75
maximises return at a still-halved drawdown), mid-morning filter
re-admission (flagged for next annual review).

## 5. Variables: how each was tested and what happened

Method used throughout: (1) a written test plan per variable with all
parameters prespecified BEFORE running; (2) measurement-first
("conditional stat before the rule"); (3) plateau verdicts — a winner
needs neighbor support, never a lone spike; (4) yearly walk-forward with
selection on prior data only, adoption bar OOS ≥4 of 5 years; (5) a
mechanism requirement — wins must be explainable by WHICH days/trades
they fix, or they are treated as curve-fit and rejected.

| var | parameter | final | program outcome |
|---|---|---|---|
| V1 | dip depth | 1% fixed | swept 1–3%; adaptive (×band) rejected — optimum does not migrate |
| V2 | entry anchor | session high | windowed/VWAP/prior-close/reset all rejected monotonically; instant re-entry priced at +47.9 bp/day |
| V3 | target | +1% fixed | swept 1–2%; adaptive rejected on mechanism + OOS |
| V4 | stop | −4% **absolute** | swept 2/3/4 twice; scaled stop broke the worst-day guarantee (−20%) — absolute matters, not ratio |
| V5 | start time | 11:00 | swept 09:35–13:00 on corrected engine; plateau 10:30–11:30; 09:35 spike exposed the engine bug and was rejected by plateau rule |
| V6 | EOD exit | flat at close | overnight holds win +17–26 bp/day and were REJECTED on role (gap tail −20%+); premium priced |
| V7 | trade cap | 5 | swept 1–10; Sharpe peaks at 5 |
| V8 | direction | long only | mirror short −17.7 bp under honest fills; SSR binds 16.6% of gated days; excursion momentum rejected; the pyramid variant adopted here was later WITHDRAWN (§6.7) |
| V9 | day filter | direction-aware OR30 | boundary plateau-confirmed; direction split (+89 up / −66 down) found the true mechanism; adopted, WF 5/5 |
| V10 | vol gate | ATR5 ≥ 6, 5d, cliff | every knob confirmed; U-shape anomaly closed as era-noise; ATR10 "win" exposed as matched-rate artifact |
| V11 | sizing | flat f + 2-stop breaker | six-test program; breaker adopted (better return AND tail); leverage rejected; pyramid variant later WITHDRAWN and bootstrap re-run on the current series (§6.7) |
| V12 | role | intraday core, cycle satellite | walk-forward: core retains ~83% of edge OOS; satellite failed OOS (3.3% CAGR) until SMA100 kill-switch (27% OOS CAGR) |

Errors found and fixed along the way (disclosed deliberately): a
**same-bar lookahead bug** in the original simulator (entry trigger set
by the current bar's own high could be "filled" by that same high) —
found when a 09:35-start cell printed Sharpe 5.7, fixed by making the
trigger a true resting limit (prior bars only) with next-bar-earliest
target fills; the fix *raised* the honest 10:30 baseline (the bug cut
both ways midday) and destroyed the morning mirage. Additionally, four
attractive in-sample results were rejected by protocol: the 09:35 start,
the ATR10 lookback (matched-rate artifact), the adaptive target cell,
and the frictionless two-sided book (Sharpe 4.05 → 1.56 under tradable
fills).

## 6. Backtest results and expected performance ($150,000 start)

### 6.1 Headline series (locked core, 2020-07 → 2026-07)

- ON days: 787 of 1,510 (52%); ~3.2 fills per ON day.
- Gross: **65.6 bp/ON-day, Sharpe 3.09** (ON-day basis), ON-day win rate
  63.7%, median ON-day +77 bp, worst day −8.0% (structural).
- Max drawdown on the calendar equity curve: −36.5%.
- Note: 2020 H2 contributes ~zero because the filter requires ~6 months
  of threshold history before it can trade.

### 6.2 The honesty chain (what to actually expect)

Full-sample gross is an upper bound. The discount chain:
1. **Out-of-sample haircut.** The original core retained ~83% of its
   in-sample edge under yearly walk-forward. Each later refinement
   passed its own walk-forward, but successively adopted refinements
   accumulate selection bias no per-program test fully removes.
2. **Costs.** IBKR Pro Fixed ≈ 0.9 bp/round-trip commission at $150K
   size; with spread costs on stops and EOD flattens, all-in drag ≈ 4–7
   bp/ON-day.
3. **Fill realism.** Entries/targets assume resting limits fill at the
   touch on 5-min bars. Unverified below the 5-min grain (top remaining
   risk — see §7).

**Conservative planning scenario** (gross × 0.83, minus 5 bp/day costs):
**49.4 bp/ON-day**.

### 6.3 Weekly expectations at $150,000 (flat sizing, no compounding)

From the 315-week backtest distribution:

| metric | gross | conservative |
|---|---:|---:|
| mean week | +$2,458 | +$1,853 |
| median week | +$440 | +$215 |
| P25 / P75 | $0 / +$6,465 | ≈$0 / ≈+$5,300 |
| 5th percentile week | −$10,643 | −$9,103 |
| worst week in sample | −$23,701 | ≈−$20,000 |
| best week in sample | +$27,477 | ≈+$22,500 |
| weeks with any trading | 77% | 77% |
| positive weeks (of trading weeks) | 69% | ~67% |

Read this table honestly: **the strategy earns in lumps.** A typical
week is roughly flat-to-slightly-positive; the annual result is carried
by the high-volatility burst weeks. Annual gross P&L at flat $150K
varied from +$74K (2025, 2026-H1) to +$216K (2022) — the strategy's
year is decided by how much vol the market delivers, which the gate can
select for but not create.

### 6.4 Compounded projections (and why to distrust them)

Reinvesting fully, the gross series compounds $150K → $16.5M over the
6-year sample (118%/yr); the conservative series → $5.3M (81%/yr).
**These numbers should be treated as arithmetic, not expectations.**
No allowance is made for: capacity/impact above ~$1M positions, fill
degradation as size grows, regime shift (a low-vol era turns the
strategy off — correct behavior, zero return), or the residual
optimism in any strategy validated on the data that shaped it. The
defensible planning claim is the per-ON-day range (≈50–65 bp gross-to-
net) and the weekly distribution above — compounding is then a choice,
not a promise.

### 6.5 Drawdown: the three numbers and how they relate

These are distinct metrics — do not conflate them:

| metric | value | definition |
|---|---:|---|
| worst single day | **−8.0%** | structural cap: 2 stop-outs × −4%, breaker halts the day |
| worst 10 consecutive ON-days | −29.3% | capped days CHAIN — a drawdown is a sequence, not one day |
| max drawdown, compounded equity (f=1.0) | **−36.5%** | peak 2025-11-12 → trough 2026-03-26 (92 sessions), recovered 2026-05-06 |
| same episode at FLAT $150K sizing | −$63.9K (−42.6% of start) | flat sizing looks worse in % of starting capital because positions don't shrink during the streak |
| bootstrap P(−30% DD per 252-ON-day year), gross, f=1.0 | 14.5% | one ON-day year ≈ 2 calendar years; across the sample's ~3.1 ON-day years P(seeing one −30% DD) ≈ 38% — consistent with the realized −36.5%. |
| same, **conservative assumptions**, f=1.0 | **26.7%** | the honest planning number (§6.7) — less edge at unchanged volatility means DEEPER drawdowns, not shallower |

(An earlier 46% figure appears in `V11_SIZING_TESTS.md`; it was computed
on the weaker pre-refinement P&L series and is superseded by §6.7.)

(Historical note for readers of earlier round documents: a −22.9% max-DD
figure appears in the round-3 combined-backtest table — that was the
ORIGINAL day-sleeve configuration (10:30 start, plain filter, no
breaker, pre-bug-fix engine, 2022-start window) and is superseded; the
current locked core's number is the −36.5% above.)

Anyone uncomfortable with a −36.5% realized / −30%-per-year-near-coin-flip
profile must reduce f (§6.7) or use the 25% SOXS overlay dial — not
run full size.

### 6.6 Documented negatives: drawdown defenses tested and rejected

Both tested 2026-07-28 after the §6.5 reconciliation; scripts in
Appendix B, results in `out/put_overlay_curves.csv`, `out/v13_results.csv`.

**Long-dated protective puts — rejected, mechanism decisive.** A rolling
~180-DTE, 20%-OTM SOXL put overlay (real chains, ask/bid fills, sized to
sleeve equity) made everything worse: CAGR 146→125%, **max DD −36.5% →
−60.0%**, overlay cost ≈ −$634K/yr at compounded size, and it LOST a
further $1.6M during the very drawdown it was meant to protect. Root
cause: **SOXL rose +11.9% during the sleeve's worst drawdown** — the
losing streaks are chop, not slides (corr of sleeve P&L with SOXL
direction is only 0.4), so a put hedges a risk the sleeve does not have
while paying 80–110% implied vol for it. Third independent confirmation
that bought options are structurally unprofitable in this system
(round-1 cycle puts, V8 short side, this).

**Streak-based de-risking — rejected, and the measurement is the
finding.** E[ON-day P&L | k prior consecutive losing days]: k=0 → 51 bp;
k=1 → **96 bp (Sharpe 4.6)**; k=2 → 94 bp; k=3 → **151 bp**. The
sleeve's own P&L mean-reverts: post-loss days are its BEST days, so any
rule that cuts size after losses sells the recovery. All three
prespecified rules confirmed it (halve-after-2-losses: −13 CAGR pts for
1.1 DD pts; halve-after-1-loss: −39 CAGR pts for 7.1 DD pts;
trailing-DD-trigger: strictly worse). None met the adoption bar.

**Consequence — the risk story as it stood:** the worst day is capped by
the breaker (−8%); losing streaks are neither predictable nor pruneable
(their aftermath is the best edge in the book); and every overlay tested
to that point (puts, streak de-risking, pyramiding) was dominated by
simply choosing a smaller f.

> **SUPERSEDED IN PART (2026-07-28).** The claim that the f dial was the
> *only* legitimate drawdown control held until SOXS was tested. A
> SOXL+SOXS pair passed the full protocol (§9.5, `V14_PAIR_PROTOCOL.md`)
> and beats the dial decisively at matched risk — e.g. at a −15%
> drawdown budget the dial yields 34.6% CAGR while the pair yields
> 121.4%. The rest of this section stands: de-risking after losses and
> buying optionality remain pre-refuted.

### 6.7 The sizing dial — verified, and two of my own errors corrected

The spec's engine-correction header left two sizing items open: the
per-unit pyramid had only ever been validated on the pre-bugfix engine
and the old configuration, and the V11 bootstrap ran on the
pre-refinement P&L series. Both were closed 2026-07-28
(`sizing_verification.py` → `out/sizing_verification.csv`,
`out/sizing_bootstrap.csv`). Closing them exposed two errors in my own
earlier analysis, both of which had flattered the results:

**Error 1 — the pyramid was never a "half-capital" variant.** Measured
average exposure is **0.483** of equity, versus 0.362 for flat f=0.5 and
0.724 for flat f=1.0; it reaches **full 1.0 exposure on 81% of ON days**.
Comparing it to flat f=0.5 (as V8 did) compared a bigger position to a
smaller one and called the difference alpha. The correct benchmark is
flat sizing at the same average exposure, f = 0.667:

| setting | bp/ON-day | Sharpe | worst day | cal CAGR | maxDD | avg expo | **bp per unit exposure** |
|---|---:|---:|---:|---:|---:|---:|---:|
| flat f=0.50 | 32.8 | 3.09 | −4.0% | 50.7% | −19.8% | 0.362 | **90.6** |
| flat f=0.67 (exposure-matched) | 43.7 | 3.09 | −5.3% | 71.3% | −25.7% | 0.483 | **90.6** |
| pyramid (2 × f/2) | 37.6 | 2.65 | −6.0% | 58.0% | −25.4% | 0.483 | **77.9** |
| flat f=1.00 | 65.6 | 3.09 | −8.0% | 118.5% | −36.5% | 0.724 | **90.6** |

At matched exposure flat sizing earns **43.7 bp against the pyramid's
37.6 bp for the same −25% drawdown** — 16% more return for the same
risk. Flat sizing returns 90.6 bp per unit of average exposure at every
f (exact linearity); the pyramid returns 77.9, because its two units
stop out together in the same adverse move, correlating losses that
sequential flat bets keep independent. **The pyramid is dominated, not a
midpoint: it is withdrawn entirely.** The V8 claim that it "dominates
flat half-size by +58%" was an artifact of the pre-bugfix engine
compounded by the exposure mismatch.

**Error 2 — my conservative bootstrap understated drawdown risk.**
Modelling the conservative case by multiplying returns by 0.83 shrinks
volatility along with edge, which is wrong: edge decay and costs reduce
the *mean* while volatility is unchanged. Rebuilt correctly
(`conservative = ON-day series − 16.2 bp constant drag`):

| scenario | P(DD<−30%) | P(DD<−20%) | median DD | median yr | 5th-pct yr |
|---|---:|---:|---:|---:|---:|
| gross f=1.00 | 14.5% | 61.5% | −21.7% | +355% | +114% |
| **conservative f=1.00** | **26.7%** | **74.5%** | −24.9% | +201% | +39% |
| conservative f=0.67 | 3.4% | 33.0% | −16.9% | +117% | +31% |
| conservative f=0.50 | 0.5% | 9.1% | −12.9% | +80% | +23% |

The corrected conservative figure is *worse* than the gross one —
27% chance of a −30% drawdown per ON-day year at full size, roughly
one such year every two calendar years. My earlier "7.6%" was an
artifact of the flawed rescaling and should be disregarded.

**Final guidance (this is now a closed risk-preference choice, not a
research question):** use flat sizing and pick a point on the f dial.
Sharpe is invariant in f, so the dial trades return against drawdown at
constant return quality — there is no clever structure that beats it, as
the pyramid, put-overlay, and streak-rule results all independently
confirm. Reference points under conservative assumptions: **f=1.0** →
~+200% median ON-year, but a 27% chance of a −30% drawdown; **f=0.67**
→ ~+117% median, 3% chance; **f=0.5** → ~+80% median, negligible −30%
risk and a −12.9% median drawdown. Given the un-modelled fill risk
(§7 item 1), starting at **f ≤ 0.5 and raising it only after live
results confirm the backtest** is the defensible path.

### 6.8 Final summary table (all revisions applied)

Realized-path results, corrected engine, current locked rules, full
sample 2020-07 → 2026-07 (787 ON days = 52% of sessions). "Conservative"
= the §6.2 chain: 0.17 × mean edge decay + 5 bp costs = **16.2 bp/day
drag applied to the mean, volatility unchanged**. $ columns are weekly
at $150,000. Source: `out/final_summary_table.csv`.

| basis | setting | bp/ON-day | bp/calendar-day | worst day | max DD | CAGR | wk mean | wk median | wk 5th-pct |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Gross** | f=1.00 (no dial) | 65.6 | 34.2 | −8.0% | −36.5% | 118.5% | $2,458 | $440 | −$10,643 |
| Gross | f=0.67 | 43.9 | 22.9 | −5.4% | −25.8% | 71.7% | $1,647 | $295 | −$7,131 |
| Gross | f=0.50 | 32.8 | 17.1 | −4.0% | −19.8% | 50.7% | $1,229 | $220 | −$5,321 |
| Gross | f=0.25 | 16.4 | 8.5 | −2.0% | −10.3% | 23.3% | $615 | $110 | −$2,661 |
| **Conservative** | **f=1.00 (no dial)** | **49.4** | 25.8 | **−8.2%** | **−41.5%** | **77.0%** | $1,853 | **$0** | −$11,515 |
| Conservative | f=0.67 | 33.1 | 17.3 | −5.5% | −29.7% | 49.1% | $1,241 | $0 | −$7,715 |
| **Conservative** | **f=0.50** | **24.7** | 12.9 | **−4.1%** | **−22.9%** | **35.6%** | $926 | $0 | −$5,757 |
| Conservative | f=0.25 | 12.4 | 6.4 | −2.0% | −12.1% | 17.0% | $463 | $0 | −$2,879 |

Three things this table makes explicit that earlier drafts obscured:

1. **Conservative drawdowns are DEEPER than gross at every setting**
   (−41.5% vs −36.5% at full size). Less edge against unchanged
   volatility digs deeper holes — the realized path confirms the
   bootstrap in §6.7. Any document quoting a conservative return
   alongside a *gross* drawdown is understating risk.
2. **The median week is zero under conservative assumptions.** The
   strategy's entire expectation lives in the upper tail of weeks; a
   flat month is normal, not a malfunction. Operators must be able to
   sit through that without intervening.
3. **The dial is close to linear in return and drawdown** (halving f
   roughly halves both), because Sharpe is invariant in f — which is
   precisely why no clever structure (pyramid, puts, streak rules)
   beat simply choosing a smaller f.

For flat (non-compounding) $150K sizing, annual P&L ran $60K–$171K
(conservative) / $75K–$216K (gross) across 2021–2026, with 2020
contributing zero (the filter needs ~6 months of threshold history).
The CAGR column compounds fully and should be read with the §6.4
warning: it is arithmetic, not a forecast.

### 6.9 Week-by-week path, and the profit-sweep question

`v15_weekly_sweep.py` → `out/v15_weekly_sweep.csv` (all 290 weeks). Pair
at w=0.50, net of costs, $150,000 start, 2021-01 → 2026-07.

Weekly texture: **290 weeks, 186 winning (64%)**, 42 with no trading at
all. Weekly profit mean $29,216 against a **median of $7,148** — the
average is carried by a minority of volatile weeks, and dollar figures
grow with the compounding account (early weeks in the hundreds, late
weeks in the hundreds of thousands). Best week +$818,679; worst
−$437,387.

A 5% weekly profit sweep to a cash account was tested (V15, appended to
`V14_PAIR_PROTOCOL.md`). **It is not recommended as a risk instrument:**
it costs $1,798,310 — 17.3% of terminal wealth — to hold 6.3% of wealth
in cash, and improves max drawdown only from −9.4% to −9.2%. The
cost-to-protection ratio stays near 2.2–2.7× at every sweep rate from 5%
to 50%, because cash compounds at 0–4% against the account's ~115%. Even
under a simulated edge *reversal* the sweep still underperforms, because
the compounding forgone before the reversal exceeds the cash rescued.

Critically, the sweep changes **no** strategy statistic — percentage
returns, Sharpe, and percentage drawdown of the trading account are
identical with or without it. It is purely a wealth-allocation overlay.
If capital must leave the account for external reasons, the tested
numbers price that decision precisely: roughly **15–17% of terminal
wealth per 5 percentage points of sweep rate** at these compounding
levels.

## 7. Double-check: verified, unverified, and items for third-party review

**Verified in this work:**
- No-lookahead audit of every input: gate uses prior-day data (shifted);
  filter threshold uses shifted rolling quantiles; the 10:00 direction
  check precedes the 11:00 start; the engine's trigger uses prior bars
  only and targets fill next-bar-earliest; split adjustment (2021 15:1)
  verified against the discontinuity scan; SOXS/SOXX files verified
  back-adjusted/clean.
- Commission arithmetic confirmed against the published IBKR Pro Fixed
  schedule (uploaded to the repo owner 2026-07-28).
- Every adopted rule carries a yearly walk-forward OOS table in its
  results doc.

**Known limitations / unverified assumptions (the honest list):**
1. **Sub-5-minute fill sequencing** (A1/A2): stop-before-target within a
   bar is assumed (conservative), and limit fills at the touch are
   assumed (optimistic). 1-minute or tick data would settle both. This
   is the highest-priority item for the validator.
2. **Cumulative selection bias**: 12 sequential audit programs each ran
   walk-forwards, but the sequence itself was steered by results. The
   clean test is forward: paper trading against the backtest's daily
   expectations.
3. **Single instrument, single regime history**: 6 years, one ETF, a
   sample whose last 18 months were extraordinarily volatile. A first
   transfer test (SPXL, locked settings) was run 2026-07-28 — see §9;
   it was INCONCLUSIVE by construction (the absolute gate admits only 63
   SPXL days). FAS/TQQQ remain unrun.
4. **Costs are estimated, not simulated**: the 4–7 bp/day drag is
   arithmetic, not a fill-by-fill cost model.
5. **The V9 direction refinement and V5 start move were adopted from
   full-sample evidence with WF support** — their incremental ~+10 bp
   over the original 10:30/orq5 core is the least-seasoned part of the
   edge estimate. The conservative scenario effectively assumes much of
   it away.

**Suggested third-party validation checklist:**
(a) re-run every `band_lab/v*_tests.py` script from raw CSVs and diff
against `band_lab/out/*.csv`; (b) independently re-implement the locked
rules from §4 alone (clean-room) and compare daily P&L series; (c)
obtain 1-minute data for 2022 and 2026 and re-test fills; (d) run the
transfer test on TQQQ/FAS/SPXL; (e) audit the no-lookahead claims in
`v2_anchor_tests.py` (the canonical current-core implementation);
(f) 3–6 months of paper trading with fills logged against the §6.3
distribution before capital.

## 9. Transfer test: SPXL with settings untouched (2026-07-28)

`transfer_test.py` → `out/transfer_test.csv`. Locked rules applied
verbatim; nothing re-tuned; the OR30 filter self-calibrates (trailing
percentile of the instrument's own history) but the **ATR5 ≥ 6.0% gate
is absolute and was deliberately not rescaled**.

| | median day range | ON days | ON rate | bp/ON-day | Sharpe | ON win rate | worst day | maxDD | CAGR | wk mean $150K |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SOXL (reference) | 6.67% | 787 | 52.1% | 65.6 | 3.09 | 63.7% | −8.0% | −36.5% | 118.5% | $2,458 |
| **SPXL (locked settings)** | 2.92% | **63** | **4.2%** | 30.5 | 1.34 | 66.7% | −8.0% | −17.0% | **2.5%** | $92 |

**Verdict: not a valid test of transferability — the gate refuses to
trade SPXL, which is the gate working as designed.** SPXL's median daily
range (2.92%) is under half SOXL's (6.67%), so an absolute 6% ATR5
threshold admits only 4.2% of days, and **46 of the 63 admitted days
fall in 2022** (2023: 4 days, 2024: 3, 2025: 6, 2026: 0). Per-year
figures on 3–6 observations are noise. The 2.5% CAGR is not a
performance statement; it is the arithmetic of a strategy that sat in
cash 96% of the time.

**Mechanism — why the gate is right to refuse:** the strategy harvests
completed ≥1% swings, and SPXL simply does not produce them at SOXL's
density.

| | ≥1% swings/day (mean / median) | ≥2% swings/day | days with zero 1% swings |
|---|---:|---:|---:|
| SOXL | 15.0 / 14 | 5.9 | 0% |
| SPXL | **5.3 / 4** | 1.7 | 2% |

With ~4 qualifying swings a day against a 5-entry cap, SPXL cannot
support the trade cadence the edge depends on. This is the "fails safe
to cash" property (§8.3) demonstrated on live data rather than asserted.

**Encouraging but not evidence:** on the 63 days it did trade, the
strategy was *positive* — 30.5 bp/ON-day at a 66.7% win rate (a higher
win rate than SOXL's 63.7%), with the −8.0% structural worst-day cap
holding exactly as designed on a different instrument. That is
consistent with the mechanism generalising, but n=63 concentrated in one
bear market proves nothing on its own.

### 9.1 Vol-scaled SPXL cells — EXPLORATORY, NOT ADOPTED

`spxl_scaling_test.py` → `out/spxl_scaling.csv`. Scaling factor: SPXL
median range 2.92% / SOXL 6.67% = 0.44. Two independent derivations of
the gate agree (6.0 × 0.44 = 2.6; percentile-matched = 2.94). Two knobs,
commonly conflated: the **gate** decides WHICH DAYS trade, the **dip**
decides HOW MANY TRADES per day. SPXL needed both rescaled.

| cell | gate | dip/tgt | ON days | trades/day | bp/ON-day | Sharpe | win% | maxDD | yrs + |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A locked (§9) | 6.00 | 1.0% | 63 | 2.84 | 30.5 | 1.34 | 66.7 | −17.0% | 4/5 |
| B gate-scaled only | 2.94 | 1.0% | 549 | **1.73** | **4.5** | 0.33 | 51.0 | −31.1% | 3/6 |
| **C gate + dip scaled** | 2.94 | **0.5%** | 549 | **3.07** | **14.1** | 1.03 | 59.2 | −25.4% | 4/6 |
| D fully scaled (stop 2%) | 2.94 | 0.5% | 549 | 3.31 | 12.9 | 1.05 | 61.7 | −25.4% | 4/6 |
| SOXL reference | 6.00 | 1.0% | 787 | 3.17 | **65.6** | **3.09** | 63.7 | −36.5% | 6/6 |

**The 0.5% dip was necessary and correct.** Cell B — rescaling only the
gate — produced almost nothing (4.5 bp, Sharpe 0.33) because the 1% trigger
starved the cadence to 1.73 trades/day. Halving the dip restored cadence to
3.07/day (SOXL runs 3.17) and **tripled the edge** to 14.1 bp. A resolution
check confirms this is not a 5-minute-bar artifact: same-bar exits 1.5% and
within-one-bar 26.7% for cell C, versus 1.1% / 25.5% for SOXL at 1% levels —
the tighter levels are proportionally no coarser, because SPXL's bars are
proportionally smaller.

**But the transferred edge is weak.** Even correctly scaled, SPXL delivers
**21% of SOXL's bp/day at a third of the Sharpe** (1.03 vs 3.09), with the
most recent year negative in every cell (2026: −37 to −38 bp).

### 9.2 Should capital be allocated to SPXL? — the data says no

The transfer test is already **fully signal-independent**: SPXL uses its own
ATR5, its own trailing OR30 percentile, its own session high. No SOXL signal
enters it. The only thing borrowed was the constant (6%), now rescaled. So
the question is purely portfolio: is an independent SPXL sleeve worth
funding? Three measurements say no.

**(1) Splitting capital is monotonically value-destroying** (both sleeves
sized to their own allocation; capital split, not duplicated):

| w SOXL / w SPXL | bp/calendar-day | Sharpe | maxDD | CAGR |
|---|---:|---:|---:|---:|
| **1.00 / 0.00** | **35.7** | **2.26** | −36.5% | **133.7%** |
| 0.90 / 0.10 | 32.7 | 2.23 | −34.6% | 118.3% |
| 0.75 / 0.25 | 28.1 | 2.15 | −31.8% | 96.8% |
| 0.50 / 0.50 | 20.5 | 1.91 | −26.8% | 64.5% |
| 0.00 / 1.00 | 5.4 | 0.64 | −25.4% | 12.3% |

Every dollar moved to SPXL lowers return *and* Sharpe. It does reduce
drawdown — but **the f dial reduces drawdown far more cheaply**: 25% into
SPXL buys maxDD −31.8% at Sharpe 2.15, whereas simply setting f=0.67 on
SOXL alone gives −25.8% at Sharpe 3.09 (§6.8). Diversification that is
dominated by turning your own size down is not diversification.

**(2) The "independent" days are precisely the losing days.** This is the
decisive finding for the question as asked:

| SPXL days | n | mean | note |
|---|---:|---:|---|
| SOXL also ON | 445 | **+24.5 bp** | correlation with SOXL P&L **0.75** — a weaker, correlated copy |
| **SOXL idle** | **104** | **−30.4 bp** | the genuine-diversification days: 53% win rate, **−31.6% of capital cumulatively** |

SPXL's edge exists only when SOXL's regime is *also* hot. When the S&P is
volatile but semis are calm — exactly the independence being proposed — the
volatility is the wrong kind (slower and trendier rather than choppy), and
the sleeve loses. Funding SPXL therefore buys correlated exposure on the
good days and a negative-edge cohort on the independent ones.

**(3) Standalone on separate capital**, SPXL earns 12.3% CAGR for a −25.4%
drawdown (Sharpe 1.04). Positive expectancy, but a poor risk-reward for
fresh capital, and not comparable to raising f on the proven sleeve.

### 9.3 FAS — and the replicated finding across instruments

`etf_scaling_test.py` (generalized harness) → `out/etf_scaling_FAS.csv`,
`out/etf_churn_density.csv`, `out/etf_overlap_*.csv`. FAS scale factor
k = 3.69/6.67 = 0.554, matched gate 3.74%, scaled dip 0.55%. (This run
re-derives SPXL's dip from k as 0.44% rather than the rounded 0.5% used
in §9.1 — 16.5 vs 14.1 bp; immaterial to the verdict.)

| instrument / cell | ON days | trades/day | bp/ON-day | Sharpe | maxDD | yrs + |
|---|---:|---:|---:|---:|---:|---:|
| **SOXL locked (reference)** | 787 | 3.17 | **65.6** | **3.09** | −36.5% | **6/6** |
| FAS A locked | 111 | 2.52 | **−2.8** | −0.14 | −27.4% | 4/6 |
| FAS B gate-scaled, dip 1% | 580 | 1.89 | **−8.9** | −0.61 | −55.6% | 1/6 |
| FAS C gate+dip scaled (0.55%) | 580 | 3.06 | **+7.1** | 0.49 | −40.0% | 4/6 |
| FAS D fully scaled | 580 | 3.32 | +2.4 | 0.18 | −45.8% | 4/6 |
| SPXL C (for comparison) | 551 | 3.31 | +16.5 | 1.21 | −25.5% | 4/6 |

**FAS is worse than SPXL and negative under locked settings.** Its best
cell earns 7.1 bp at Sharpe 0.49 — 11% of SOXL's edge at a sixth of the
risk-adjusted quality — and 2026 is negative (−19.8 bp). Once again the
dip rescaling was essential and directionally confirmed your call: cell B
(gate rescaled, dip left at 1%) is **−8.9 bp with 1/6 years positive**;
halving the dip to 0.55% restored cadence 1.89 → 3.06 trades/day and
flipped the sign to +7.1 bp.

**The independence result replicated.** This is the important part —
what looked like an SPXL quirk is now a pattern across two instruments:

| | edge when SOXL is ON | edge when SOXL is IDLE | corr on both-ON days |
|---|---:|---:|---:|
| SPXL | +25.9 bp (n=445) | **−23.3 bp** (n=106, −24.7% cumulative) | 0.75 |
| FAS | +14.9 bp (n=405) | **−10.9 bp** (n=175, −19.1% cumulative) | 0.58 |

Both sister instruments earn only when SOXL's regime is *also* hot, and
both **lose** on precisely the days that would provide independent
diversification. Two independent replications make this a property of the
strategy family rather than a coincidence: the edge is not "3x ETF churn"
generically — it requires the specific volatility regime that SOXL
signals, and days when other sectors are volatile *without* semis are
systematically the wrong kind of volatility.

**Churn density — SOXL is genuinely unusual:**

| | median day range | ≥1% swings/day (mean / median) | ≥2% swings/day | zero-swing days |
|---|---:|---:|---:|---:|
| **SOXL** | **6.67%** | **15.0 / 14** | **5.9** | **0.0%** |
| FAS | 3.69% | 6.4 / 5 | 2.2 | 0.1% |
| SPXL | 2.92% | 5.3 / 4 | 1.7 | 1.7% |

SOXL delivers 2.3–2.8× the ≥1% swing density of either sibling. But note
the relationship is **not** cleanly monotonic — FAS has *more* swings than
SPXL (6.4 vs 5.3) yet a *weaker* edge (7.1 vs 16.5 bp) — so swing density
is necessary but not sufficient; the character of the churn (choppy
mean-reversion vs news-driven trending) differs by sector in a way this
study does not isolate. That is an honest open question, not a settled one.

*Methodological caveat:* the matched gates were set to admit SOXL's 52%
ON-rate **by gate alone**; after the V9 filter the comparison instruments
trade ~37% of days versus SOXL's 52%. A fully matched design would admit
somewhat more days. This does not change the direction of any finding.

**Conclusion:** neither SPXL nor FAS is adopted, in any allocation. The
mechanism partially transfers to both — genuine evidence that the SOXL edge
is a volatility-churn phenomenon rather than a single-instrument artifact —
but neither transfers *strongly enough* to fund (16.5 and 7.1 bp/day at
Sharpe 1.21 and 0.49, against 65.6 at 3.09), and in both cases the
independent days are negative. If additional capital ever needs deploying,
the f dial on the proven sleeve is the better instrument. Running these
sleeves through the full protocol (walk-forward, plateau, mechanism
attribution) is only worth doing to formally challenge the above; on these
numbers it would be confirming sleeves that are dominated before they start.

### 9.4 TQQQ — NOT RUN (no intraday data in the repository)

Requested 2026-07-28; **cannot be simulated with available data.** The
repository holds TQQQ only as `TQQQ_IBKR_3YR_EOD.csv` (daily bars,
2023-07-05 → 2026-07-02) and options chains (`raw_data/TQQQ_*`). The
strategy is intraday by construction — it needs 5-minute bars for the
opening-range filter, the session-high anchor, the dip trigger and the
intraday exits. Daily bars cannot produce any of the reported metrics.

What the daily data DOES establish (all four instruments measured over
TQQQ's shorter 2023-07 → 2026-07 window for fairness):

| instrument | median daily range | vs SOXL (k) |
|---|---:|---:|
| SOXL | 6.24% | 1.000 |
| **TQQQ** | **3.56%** | **0.570** |
| FAS | 3.25% | 0.521 |
| SPXL | 2.57% | 0.412 |

Under the locked gate (ATR5 ≥ 6%) TQQQ would trade on only **9.4%** of
days; its matched gate would be ~3.65% and its scaled dip ~0.57%.

**Prior, not result:** TQQQ sits in the same volatility class as FAS
(k = 0.57 vs 0.55) — and FAS was the weakest transfer tested (+7.1
bp/day, Sharpe 0.49, negative under locked settings). The reasonable
expectation is therefore a similarly weak transfer, with the same
independence problem. **That is an extrapolation from a volatility
profile, not a measurement, and must not be quoted as a TQQQ result.**

To close it properly, 5-minute TQQQ bars for 2020-07 → 2026-07 are
needed; the repository already contains a fetcher pattern
(`ibkr_intraday_fetcher.py`) that pulls exactly this from a live IBKR
connection. Once the file exists as `TQQQ_5min_6Years.csv`, the test is
one command: `python3 band_lab/etf_scaling_test.py TQQQ`.

### 9.5 SOXS — the strongest transfer result, and the drift question settled

`etf_scaling_test.py SOXS` → `out/etf_scaling_SOXS.csv`. SOXS is −3x the
same semiconductor sector: k = 1.017, so **no rescaling is needed — the
locked settings apply verbatim**. Churn density is a near-perfect match
(15.3 ≥1% swings/day vs SOXL's 15.0; identical 5.9 ≥2% swings; zero
zero-swing days in both).

| | ON days | trades/day | bp/ON-day | Sharpe | win % | worst day | maxDD | yrs + |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SOXL (locked) | 787 | 3.17 | 65.6 | 3.09 | 63.7 | −8.0% | −36.5% | 6/6 |
| **SOXS (locked, unchanged)** | 801 | 3.36 | **57.7** | **2.63** | 57.6 | −8.0% | −37.0% | **6/6** |

**88% of SOXL's edge, on an instrument that lost 100% of its value over
the sample.** Positive in all six years (2021–2026: 44.9, 86.2, 21.1,
33.1, 102.2, 62.5 bp), including 2023 — a large semiconductor bull year
in which SOXS decayed relentlessly.

**This settles the drift-versus-reversion question.** Benchmark: buy at
the 11:00 bar close, hold to the session close, on the same ON days, at
the strategy's own measured average exposure — a fully implementable
passive alternative.

| | strategy | passive 11:00→close at same exposure | **residual (timing alpha)** |
|---|---:|---:|---:|
| SOXL | +65.6 bp | +26.2 bp | **+39.4 bp** |
| SOXS | +57.7 bp | **−4.2 bp** | **+61.9 bp** |

On SOXL, 60% of the return is genuine timing alpha and 40% is drift
capture. On SOXS the passive benchmark *loses* money and the strategy
still earns +57.7 bp — **the entire return is timing alpha, and the alpha
is larger than on SOXL.** The edge is mean-reversion harvesting, not a
disguised long position. The machinery also controls risk: on SOXS the
strategy's maxDD is −37.0% against the passive benchmark's −66.1%, and
worst day −8.0% against −14.4%.

**Mechanism — why SOXS complements rather than duplicates.** Of the 165
days SOXS trades and SOXL does not, **79% are days SOXL's gate was ON but
the V9 direction filter stood down** — SOXL's violent *down*-mornings are
SOXS's violent *up*-mornings, which the filter welcomes. The strategy's
own filter therefore selects direction, and the two sleeves are **−0.70
correlated** on days both trade. Those SOXL-stand-down days are SOXS's
best: **+151.7 bp mean, +162.6 bp median** (median above mean — not
outlier-driven), 69% win rate, top-5 days only 14% of the total, positive
in all six years.

**Paired portfolio** (capital split, not duplicated):

| w SOXL / w SOXS | bp/calendar-day | Sharpe | maxDD | CAGR |
|---|---:|---:|---:|---:|
| 1.00 / 0.00 | 35.7 | 2.26 | −36.5% | 133.4% |
| 0.75 / 0.25 | 34.7 | 3.36 | −14.5% | 138.7% |
| **0.50 / 0.50** | 33.8 | **4.28** | **−12.4%** | 136.4% |
| 0.00 / 1.00 | 31.9 | 1.94 | −37.0% | 110.4% |

A 50/50 pair holds CAGR essentially flat (136.4% vs 133.4%) while cutting
max drawdown from **−36.5% to −12.4%** and nearly doubling Sharpe to
**4.28**. Unlike SPXL/FAS — where every dollar moved was value-destroying
and the f dial dominated — this is real diversification, because the
negative correlation is structural rather than incidental.

**Reconciliation with V8 (a validator will ask).** V8 concluded "the short
side is dead," including a SOXS cell. That test is not this test: V8-T2
generated **SOXL mirror signals** (sell rallies off SOXL's rolling low)
and routed them through SOXS. Selling a rally at the touch is not a
resting order, which is precisely why honest fills destroyed it (−17.7
bp). The present test runs the **native long dip-buy on SOXS's own bars**
— its own session high, its own opening range, its own gate — preserving
the resting-buy-limit fill structure the whole edge depends on. V8 killed
mirror-signal shorting; it never tested this.

**STATUS: PROTOCOL PASSED (2026-07-28) — see `V14_PAIR_PROTOCOL.md`.**
Walk-forward 5/5 years with w=0.50 selected on prior data only (OOS
Sharpe 4.08 vs solo 2.20, OOS maxDD −10.8% vs −37.7%); plateau confirmed
(w 0.375–0.75); mechanism attribution confirms the SOXS-only
down-morning cohort is the source (+117.2% of capital); costs
re-derived — **SOXS costs 2.6× SOXL in bp** because IBKR charges per
share and SOXS trades near $52 (net 48.1 vs 61.9 bp/day).

**The pair beats the f dial decisively at matched risk:** at a −15%
drawdown budget, dialling SOXL down to f=0.35 yields 34.6% CAGR while
the pair at w≈0.725 yields 121.4% — 3.5×. At w≈0.75 the pair holds
SOXL-alone's full-size CAGR (121.7% vs 121.5%) at **less than half the
drawdown** (−15.7% vs −37.7%). Recommended structure: **w=0.50**
(walk-forward validated; CAGR 114.9%, maxDD −13.0%, Sharpe 3.83).

**Residual risk before capital moves:** the spread is *estimated* at 1¢,
not measured — SOXS costs are already 2.6× SOXL's, and a true 2–3¢
spread would cost a further 2–4 bp/day on that sleeve. Quote data or
paper fills should settle it. Operationally the pair roughly doubles what
the automation manages (two instruments, capital contention on 636 days),
and the V6 flat-at-close rule becomes load-bearing: SOXS decayed ~100%
over the sample, so any overnight hold there would be catastrophic.

**What this does buy the core case:** two independent instruments show a
positive edge once the constants are scaled to their volatility, with the
structural worst-day cap holding exactly as designed on both. The SOXL
result is therefore unlikely to be a data-mining artifact of one price
series — it is the same mechanism operating where the churn is dense enough
to pay for it. SOXL appears to be the only one of the three where it is.

## 8. Automation architecture (IBKR) — attended and unattended

> **BUILD SPECIFICATION: see `IMPLEMENTATION_SPEC.md`.** That document is
> the normative, self-contained build prompt — exact rules, architecture,
> state machine, safety systems, build phases, 16 acceptance tests, and a
> single-source-of-truth constants block. This section remains as the
> architectural overview; where the two differ, the implementation spec
> governs.

The system design in outline:

### 8.1 Platform components

- **Broker interface:** IB Gateway (headless) or TWS, managed by IBC
  (auto-login/restart). API via the official Python API or `ib_async`.
  Client Portal API is an alternative but the socket API's native
  bracket/OCA and pegged orders fit this strategy better.
- **Market data:** IBKR US equities L1 subscription (a few $/mo;
  waived-tier data is delayed — not acceptable). The strategy needs only
  SOXL 5-second/5-minute bars (`reqRealTimeBars` aggregated, or
  `reqHistoricalData` keep-up-to-date) and daily history for the gate.
- **Host:** a small VPS (or always-on local machine) in a US-East region
  for latency symmetry; the strategy is not latency-sensitive (5-min
  granularity) but IS uptime-sensitive between 09:30–16:00 ET.
- **State store:** a small local DB (SQLite is sufficient) persisting:
  daily gate/filter decisions, session high, open order IDs, position,
  counters (fills, stop-outs), and every fill — so a process restart
  mid-day recovers exact state instead of re-deciding.

### 8.2 Daily state machine

1. **06:00 ET — pre-open job:** pull last 5 completed daily bars,
   compute ATR5, write gate decision. Recompute the OR30 threshold
   from the 504 sessions ending yesterday. If gate OFF → the
   engine stays dormant; nothing can place an order (hard interlock).
2. **09:30–10:00 — observe:** build OR30 from live bars.
3. **10:00 — filter decision:** OR30 vs threshold + top-third direction
   check; write ON/STAND-DOWN. Track session high continuously.
4. **11:00 — activate:** place the resting buy limit at 0.99 × session
   high, sized floor(f × equity / price). On every new session high,
   modify the order upward (never downward). This ratchet is the one
   behavior IBKR has no native order type for — it is ~20 lines of
   event-driven logic on the 5-min bar close.
5. **On fill:** immediately place the OCA pair (limit +1%, stop −4%,
   stop-market). Increment fill counter. Suspend the entry limit while
   the position is open.
6. **On exit:** log; increment stop counter if stopped; if counters
   allow (fills < 5, stops < 2), recompute session high and re-place the
   entry limit; else cancel everything and go dormant.
7. **15:55 — flatten:** cancel all orders; if a position exists, market
   (or MOC) sell. Verify flat by 16:00; alert loudly if not.
8. **16:10 — reconcile:** compare internal fills vs IBKR execution
   report; write the daily row (P&L, fills, counters, gate/filter
   state); append to the live-vs-backtest monitoring series.

### 8.3 Attended vs unattended

- **Attended mode** (recommended first 3–6 months): the engine runs the
  full state machine but a human confirms two things daily — the 10:00
  stand-down decision and the 15:55 flat state — via a dashboard or even
  a two-line phone notification with an approve/abort action. Human can
  hit a global KILL (cancel all, flatten, dormant) at any time.
- **Unattended mode** adds: IBC-managed auto-restart and daily Gateway
  re-auth; a connectivity watchdog (if the API session or market data
  drops >60s while in a position → flatten via a redundant path);
  process-level "dead-man" — a second tiny process whose only job is to
  verify the main engine heartbeats and flatten if it doesn't;
  broker-side protective stop always resting (never rely on
  software-only stops); daily-loss circuit breaker (if day P&L <
  −8.5% of sleeve — beyond the structural worst day — flatten and
  dormant pending human review); notifications (push/SMS/email) on
  every fill, every state transition, and every anomaly.
- **Fail-safe philosophy:** every failure mode resolves to FLAT. The
  strategy's whole design (no overnight, resting stops, hard counters)
  is unusually compatible with unattended operation because the
  worst-case of "do nothing" is being flat in cash.

### 8.4 Rollout plan

1. Paper account: run the full engine 4+ weeks; diff fills vs backtest
   assumptions (the #1 unverified item in §7).
2. Live at 10–20% size ($15–30K): 4–8 weeks; verify cost/slippage
   arithmetic against real executions.
3. Scale to target size only if live bp/ON-day sits within the §6.3
   conservative band; any structural shortfall (fill rates, filter
   frequencies off by >20%) → back to research, not to hope.

---

## Appendix A — Trading desk runbook (manual operation)

*(Identical to STRATEGY_SPEC.md §2.5; reproduced for standalone use.)*

**Account:** IBKR Pro, Fixed pricing, margin-type account (for same-day
proceeds re-use, not leverage), equity > $25K (PDT). No short/options
permissions required. Nothing held overnight.

**Pre-open:** ATR5 = 5-day mean of (H−L)/O. ≥6.0% → ON, else OFF.
Half-days OFF.
**10:00:** OR30 = (H−L)/O of 09:30–10:00. If OR30 ≥ trailing 80th
percentile (≈5.4%, recompute each session): stand down UNLESS the 10:00 print
is in the top third of the opening range. No trading before 11:00 ever.
**11:00:** resting BUY LIMIT at 0.99 × session high, floor(f×equity/px)
shares; raise the limit on every new session high (never lower).
**On fill at E:** OCA pair — SELL LIMIT 1.01×E + SELL STOP 0.96×E
(stop-market). Entry limit stays pulled while in a position.
**Counters:** max 5 entries; hard stop after the 2nd stop-out — cancel
everything, done for the day. No discretion.
**After any exit:** recompute session high, re-place entry limit,
re-arm.
**15:55:** replace bracket with market/MOC sell. Flat by 16:00 always.
**Sizing:** flat f only — f=1.0 growth, f=0.5 risk-budget, any
intermediate f permitted; never above f=1.0; no pyramiding (withdrawn).
**Costs (verified vs IBKR schedule):** $0.005/sh, $1 min/order, ~0.35 bp
regulatory on sells ⇒ ≈0.9 bp/round trip at $150K; expected all-in drag
4–7 bp/ON-day.
**Prohibitions (each closed by a test):** no pre-11:00 entries; no
trading on stand-down or gate-off days; no shorts (incl. SOXS); no
overnight positions; no third stop; no "one more trade"; no leverage;
never scale the stop.
**Monitoring:** log every fill; weekly compare fills/day (≈3–3.5),
target-hit share (≈75–80%), net bp/ON-day (≈50s, wide variance).
Structural breaks (counts off >20% for a month) → halt and investigate.
Yearly: re-run the walk-forward with new data before re-committing.

## Appendix B — Final scripts (in the repository)

**Canonical current-core reference (corrected engine + all adopted
rules):**
- `band_lab/v2_anchor_tests.py` — most recent full implementation of the
  locked core (its "session" path) + V2 program.
- `band_lab/v5_corrected_rerun.py` — the corrected reference engine
  (`sim_trades_fixed`) and the bug-fix validation run.

**Variable audit programs (corrected engine):**
- `band_lab/v6_eod_exit_tests.py` — V6 EOD-exit program.
- `band_lab/v9_filter_tests.py` — V9 filter program (direction-aware
  filter adoption).
- `band_lab/v10_gate_tests.py` — V10 gate program.
- `band_lab/v1v3_adaptive_tests.py` — V1/V3 adaptive-levels program.

**Variable audit programs (pre-fix engine; verdicts re-verified or
conservative, flagged in STRATEGY_SPEC header):**
- `band_lab/cap_sweep.py` — V7 trade-cap sweep.
- `band_lab/v11_sizing_tests.py` — V11 sizing program (breaker adopted;
  re-verified on corrected engine in v5_corrected_rerun).
- `band_lab/v8_direction_tests.py` — V8 direction program (rejections;
  conservative under the optimistic engine).
- `band_lab/v5_start_time_tests.py` — V5 first pass (superseded by
  v5_corrected_rerun; retained as the bug-discovery record).

**Transfer test (§9):**
- `band_lab/transfer_test.py` — runs the locked rules verbatim on any
  `<SYM>_5min_6Years.csv` (SPXL run; FAS/TQQQ ready).
- `band_lab/spxl_scaling_test.py` — vol-scaled SPXL cells, resolution
  diagnostic, and the SOXL/SPXL overlap + portfolio analysis (§9.1–9.2).
- `band_lab/etf_scaling_test.py` — generalized harness for any 3x ETF
  (FAS/SPXL run; TQQQ ready) + churn-density comparison (§9.3).

**Sizing verification (§6.7):**
- `band_lab/sizing_verification.py` — exposure profile, exposure-matched
  sizing table, and gross/conservative bootstraps. Supersedes the V11-T5
  bootstrap and the V8-T4 pyramid recommendation.

**Drawdown-defense negatives (documented rejections, §6.6):**
- `band_lab/put_overlay_test.py` — LEAP protective-put overlay (real
  chains; rejected, made DD worse).
- `band_lab/v13_streak_tests.py` — streak-based de-risking (rejected;
  post-loss days are the best days).

**Foundation research:**
- `band_lab/band_analysis.py` — daily-band/excursion study + failed
  OR-fade control.
- `band_lab/churn_harvest.py` — original harvester grid (pre-fix
  engine; historical).
- `band_lab/regime_gate.py` — original vol-gate discovery.
- `band_lab/walk_forward_and_combo.py` — day/cycle walk-forwards +
  two-sleeve combined backtest.

**Satellite (cycle strategy, demoted; optional):**
- `cycle_lab/one_pct_cycle_lab.py` — data loaders (split adjustment) +
  original cycle engine + options-based rounds 1–2.
- `cycle_lab/grid_sweep.py`, `cycle_lab/compound_engine.py`,
  `cycle_lab/kill_switch.py` — cycle grids, $150K compounding engine,
  SMA100 kill-switch validation.

**Pair structure and weekly path:**
- `band_lab/v14_pair_protocol.py` — full protocol on the SOXL+SOXS pair
  (costs, walk-forward, plateau, attribution, capital rule, liquidity).
- `band_lab/v15_weekly_sweep.py` — week-by-week engine and sweep tests.

**Documents:** `band_lab/IMPLEMENTATION_SPEC.md` (build prompt),
`band_lab/V14_PAIR_PROTOCOL.md` (pair plan + results + V15),
`band_lab/STRATEGY_SPEC.md` (spec + status board + desk
runbook), `band_lab/V*_TESTS.md` (per-variable plans + results),
`band_lab/README.md`, `cycle_lab/README.md`, this document.

## Appendix C — Data inventory

- `SOXL_5min_6Years.csv` — primary series, IBKR 5-min RTH bars,
  2020-07-16 → 2026-07-21, unadjusted (2021-03-02 15:1 split adjusted
  in-code; verified by discontinuity scan).
- `SOXS_5min_6Years.csv` — inverse ETF, back-adjusted (V8 program).
- `SOXX_5min_6Years.csv` — sector index proxy (V10 input test).
- `FAS_5min_6Years.csv`, `SPXL_5min_*.csv`, TQQQ files — available for
  the recommended (not yet run) transfer test.
- `SOXL_Options_*.csv` — EOD option chains (used only by the demoted
  cycle strategy rounds).
- All large files via Git LFS; results CSVs in `band_lab/out/` and
  `cycle_lab/out/` are plain text for diffability.
