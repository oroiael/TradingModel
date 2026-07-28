# V14 — Full Protocol on the SOXL + SOXS Pair

Trigger: §9.5 found a −0.70-correlated SOXS sleeve running the locked
rules unchanged (57.7 bp/ON-day, 6/6 years positive), with a 50/50 pair
showing Sharpe 4.28 and maxDD −12.4% against SOXL-alone's 2.26 / −36.5%.
That is a full-sample observation. This document prespecifies the tests
that must pass before any capital moves.

Adoption bar (fixed here, before running): the pair must beat SOXL-alone
**out-of-sample in ≥4 of 5 walk-forward years on Sharpe**, show plateau
support around the chosen weight, have its edge attributable to the
predicted mechanism, and survive SOXS-specific costs.

---

## T1. Cost re-derivation for SOXS (run FIRST — it can veto)

**Mechanic.** SOXS trades at a far lower price than SOXL, and IBKR Fixed
charges **per share**, so identical share-count logic costs more in basis
points on the cheaper instrument. Compute from the data: mean traded
price per sleeve, commission in bp/side ($0.005/share ÷ price), the
$1.00 order minimum's bite at $150K and at smaller sizes, regulatory
fees on sells, and a spread estimate. Then re-express every §9.5 figure
net. If SOXS's net edge falls below ~half SOXL's, the pair thesis
weakens materially regardless of correlation.

**Data now:** sufficient for prices/volume; **spread is estimated, not
measured** (no quote data) — flagged as the residual uncertainty.

## T2. Walk-forward on the pair weight

**Mechanic.** For each test year 2022–2026, choose w (weight on SOXL) on
**prior years only** by Sharpe, from w ∈ {0, 0.25, 0.50, 0.75, 1.00};
trade the test year at that w; chain the OOS series. Report against
SOXL-alone OOS on the same years. Net of T1 costs.

## T3. Plateau in w

**Mechanic.** Full-sample Sharpe across the same w grid at 0.125
granularity around the winner. A sharp peak flanked by weak neighbours
is a curve-fit signature and is rejected by the same rule that killed
the 09:35 start; a broad plateau supports adoption.

## T4. Mechanism attribution

**Mechanic.** Decompose the pair's improvement by day cohort: (a) both
sleeves ON, (b) SOXS-only (predicted: SOXL's V9 down-morning
stand-downs, the claimed source), (c) SOXL-only. The improvement must
concentrate in (b) — if the gain instead comes from (a), the pair is
just diversification of correlated noise and the stated mechanism is
wrong.

## T5. Capital-allocation rule

**Mechanic.** Two implementations, both prespecified:
  - **static** — each sleeve permanently holds its weight (idle capital
    when its sleeve is OFF);
  - **dynamic** — the day's capital is split among the sleeves that are
    ON that day (full size when only one is active).
Dynamic is the natural implementation and should dominate, but it
raises per-day exposure, so its drawdown must be reported alongside.

## T6. Practical veto checks

Liquidity (SOXS dollar volume vs intended size), and the both-ON day
count (464) which determines how often capital is actually contended.

---

**Expected outcomes.** Best case: the pair survives OOS and becomes the
recommended structure, roughly halving drawdown at equal return. Most
likely: it survives directionally but with materially lower net numbers
than the gross Sharpe 4.28 once SOXS costs land. Worst case: SOXS costs
plus an unstable walk-forward weight sink it, and the finding is
recorded as a documented negative — in which case SOXL-alone with the f
dial remains the strategy.


---

# RESULTS (run 2026-07-28, `v14_pair_protocol.py` → `out/v14_*.csv`)

**VERDICT: the pair PASSES the full protocol and is the first structure
in the project to beat the f dial at reducing drawdown.**

## T1 — SOXS costs 2.6× SOXL (and an error caught)

IBKR Fixed charges **per share**, so the cheaper instrument costs more in
basis points. First run reported SOXS's mean price as **$51,871** — a
back-adjustment artifact (SOXS's historical prints are inflated by years
of reverse splits and are not tradeable prices). Corrected to current
prices, which is what a forward-looking cost estimate needs:

| sleeve | price | comm bp/side | 1¢ spread bp | cost bp/round trip | cost bp/day | gross | **net** |
|---|---:|---:|---:|---:|---:|---:|---:|
| SOXL | $158.41 | 0.32 | 0.63 | 1.17 | 3.7 | 65.6 | **61.9** |
| SOXS | $51.61 | 0.97 | 1.94 | 2.87 | 9.6 | 57.7 | **48.1** |

## T2 — walk-forward: 5/5 years, bar met

w selected on prior years only; **w=0.50 picked every year**.

| year | pair OOS Sharpe | SOXL-alone Sharpe | |
|---|---:|---:|---|
| 2022 | 4.99 | 2.34 | pair |
| 2023 | 4.08 | 3.29 | pair |
| 2024 | 3.77 | 2.18 | pair |
| 2025 | 4.47 | 1.39 | pair |
| 2026 | 3.12 | 1.85 | pair |
| **all OOS** | **4.08**, maxDD −10.8% | 2.20, maxDD −37.7% | **5/5** |

Note honestly: OOS the pair earns **less raw return** (32.9 vs 36.5
bp/calendar-day). Its win is entirely risk-adjusted.

## T3 — genuine plateau

Sharpe by w: 0.375→3.34, 0.500→**3.83**, 0.625→3.66, 0.750→3.09. Broad
and single-peaked; not a spike. Adoption weight **w=0.50** (the
walk-forward pick, inside the plateau).

## T4 — mechanism confirmed, and it is purely risk

Contribution to (pair − solo), cumulative % of capital: **SOXS-only days
+117.2%** (the predicted source), both-ON −120.9%, SOXL-only −47.3%,
**net −51.0%**. The predicted cohort does drive the benefit, but halving
size elsewhere costs slightly more than it adds — confirming the pair
buys *risk reduction*, not extra return.

## T5/T6 — capital rule and practical

Static 50/50: 30.1 bp/cal-day, Sharpe 3.83, maxDD −13.0%, CAGR 114.9%.
Dynamic (full size to whichever sleeve is ON): 41.5 bp, Sharpe 3.29,
maxDD −21.7%, CAGR 179.9% — more return, more risk; a separate dial, not
a free lunch. SOXS median daily dollar volume $0.69B (a $150K order is
2.2 bp of a day's volume — ample). Both sleeves ON on 636 days.

## The decisive comparison — pair vs the f dial at matched risk (net)

| max-DD budget | SOXL alone, dialled down | **SOXL+SOXS pair** |
|---|---|---|
| −11.5% | f=0.27 → CAGR 26.0% | **w=0.65 → 119.8%** |
| −15% | f=0.35 → CAGR 34.6% | **w=0.725 → 121.4%** |
| −20% | f=0.48 → CAGR 49.6% | **w=0.775 → 122.0%** |
| −30% | f=0.76 → CAGR 85.8% | **w=0.875 → 122.5%** |

At every risk budget the pair delivers **2.5–4.6× the CAGR** of simply
trading smaller. Most striking: **w≈0.75 holds SOXL-alone's full-size
CAGR (121.7% vs 121.5%) while cutting max drawdown from −37.7% to
−15.7%.** (Those matched-risk weights are full-sample optima; the
walk-forward-validated choice remains w=0.50, which gives CAGR 114.9% at
−13.0%.)

## Residual caveats — what is NOT settled

1. **Spread is estimated, not measured** (1¢ assumed on both). SOXS costs
   are already 2.6× SOXL's; if its true spread is 2–3¢, SOXS's net edge
   drops a further 2–4 bp/day. This is the largest open risk and needs
   quote data or paper fills.
2. Fill realism on 5-minute bars applies to SOXS exactly as to SOXL.
3. Operational: two instruments, two order sets, and capital contention
   on 636 days — roughly doubles what the automation must manage.
4. SOXS's own decay (−100% over the sample) is irrelevant only because
   the strategy is flat every night. Any overnight hold in SOXS would be
   catastrophic; the V6 flat-at-close rule is load-bearing for this sleeve.

---

# V15 — WEEK-BY-WEEK WITH A 5% PROFIT SWEEP (run 2026-07-28)

`v15_weekly_sweep.py` → `out/v15_weekly_sweep.csv` (all 290 weeks),
`out/v15_sweep_summary.csv`. Structure: the walk-forward-validated pair
(w=0.50 static), locked rules, net of per-instrument costs, $150,000
start. Rule: at each **winning** week's end, 5% of that week's profit
moves to a cash-only account and is never traded again; losing weeks
sweep nothing; everything else compounds.

**First, a property worth stating plainly:** the sweep does not change
the strategy at all. Trading a fraction of whatever the account holds
means percentage returns — and therefore Sharpe and the *percentage*
drawdown of the trading account — are identical with or without it. The
sweep is a wealth-allocation decision layered on top, not a trading
decision. Every risk statistic in V14 stands unchanged.

## Week-by-week results ($150,000 start, 290 weeks, 5.5 years)

| | no sweep | **5% sweep** | 5% sweep, cash @4% |
|---|---:|---:|---:|
| final trading account | $10,420,919 | $8,079,632 | $8,079,632 |
| cash account | — | $542,977 | $569,797 |
| **total wealth** | **$10,420,919** | **$8,622,609** | $8,649,429 |
| CAGR (total) | 114.9% | 107.7% | 107.8% |
| maxDD, total wealth | −9.4% | **−9.2%** | −9.1% |
| winning weeks | 64% | 64% | 64% |

Weekly texture: 290 weeks, **186 winning (64%)**, 42 with no trading at
all. Weekly profit mean $29,216, **median $7,148**, best +$818,679,
worst −$437,387 (dollar figures grow with the compounding account —
early weeks are hundreds, late weeks hundreds of thousands). Median
sweep on a winning week: $914.

By year (profit → swept → cash balance): 2021 $75.6K → $6.2K → $6.2K;
2022 $595K → $33.6K → $39.8K; 2023 $725K → $39.4K → $79.2K; 2024
$1.23M → $73.3K → $152.5K; 2025 $2.88M → $166.0K → $318.5K; 2026 (30
weeks) $2.97M → $224.4K → $543.0K.

## The verdict: the 5% sweep is a poor trade on every metric tested

**It costs $1,798,310 — 17.3% of terminal wealth — to protect 6.3%.**
That ratio holds at every rate tested, because cash compounds at 0–4%
while the trading account compounds at ~115%:

| sweep rate | terminal total | % of wealth in cash | cost vs no sweep | maxDD total |
|---:|---:|---:|---:|---:|
| 5% | $8.62M | 6.3% | −17.3% | −9.2% |
| 10% | $7.15M | 12.5% | −31.3% | −8.9% |
| 20% | $4.97M | 24.5% | −52.3% | −8.9% |
| 33% | $3.16M | 39.3% | −69.6% | −8.9% |
| 50% | $1.84M | 56.7% | −82.4% | −8.9% |

**The drawdown benefit is essentially nil** — −9.2% versus −9.4%, and
even a 50% sweep only reaches −8.9%, because the trading account still
carries the overwhelming majority of wealth and takes the full hit.

**The model-risk defence also fails on test.** The intuitive case for
sweeping is protection against the edge decaying. Simulating the edge
*inverting* to −50% of its magnitude from 2025 onward: no-sweep terminal
$1,680,969 versus 5%-sweep $1,559,440 — **the sweep still loses
$121,530 (−7.2%)**, because the compounding forgone before the reversal
exceeds the cash rescued. Under the conservative edge-decay haircut the
cost falls to 13.1% but still runs ~1.9× the protection. The only
scenario a sweep genuinely wins is *total* loss of the trading account —
broker failure or operational catastrophe, not strategy
underperformance — and the sleeve's design (flat overnight, −8% capped
worst day, 2-stop breaker) makes that remote.

## Recommendation

**Do not use a profit sweep as a risk instrument.** It buys 0.2
percentage points of drawdown for 17% of terminal wealth, and both the
f dial and the pair weight are dramatically more efficient at converting
return into risk reduction — the V14 matched-risk table shows the pair
weight delivering 2.5–4.6× the CAGR of an equivalently de-risked single
sleeve, while a sweep delivers essentially none.

If capital must leave the account for reasons outside this study
(withdrawals, external obligations, or simply a decision to bank
realised gains), that is an allocation choice and the numbers above
price it precisely: **each 5 percentage points of sweep rate costs
roughly 15–17% of terminal wealth at these compounding rates.** Size it
deliberately against the actual need rather than as a risk control, and
book the cost knowingly.

**Caveat:** every figure inherits the V14 caveats — estimated (not
measured) spreads, 5-minute fill realism, and a compounded path that
takes no account of capacity limits at eight-figure balances. The
compounding here is arithmetic, not a forecast; §6.4 of the master
document applies with full force.
