# fas_lab — an active daily FAS strategy

Built from `band_lab`'s locked SOXL rules and the findings in `vol_anatomy`.
Data: `FAS_5min_6Years.csv`, `SOXL_5min_6Years.csv` (2020-07-16 → 2026-07-21).

```bash
python3 fas_lab/build_fas.py    # reproduce band_lab's FAS cells, then leverage
python3 fas_lab/search.py       # in-sample parameter fit, out-of-sample check
python3 fas_lab/final.py        # plateau, leverage, independence, portfolio
```

## The harness is validated before anything is claimed

`engine.py` implements `band_lab/IMPLEMENTATION_SPEC.md` §2 verbatim, including the
normative anti-lookahead convention (entry bar: stop only; stop checked before
target). Run on SOXL with the locked settings it reproduces the published series:

| | ON days | trades/ON-day | bp/ON-day | Sharpe | max DD | CAGR | worst day |
|---|---:|---:|---:|---:|---:|---:|---:|
| band_lab published | 787 | 3.17 | 65.6 | 3.09 | −36.5% | 118.5% | −8.0% |
| **this engine** | **787** | **3.169** | **65.59** | **3.09** | **−36.53%** | **118.5%** | **−8.0%** |

All four published FAS cells also reproduce (A −2.8, B −9.4 vs −8.9, C +6.8 vs
+7.1, D +2.0 vs +2.4 bp; trades/day exact on all four).

## Costs are modelled, not assumed away

`cost_bp` charges an all-in round-trip cost on every fill. At **2 bp** SOXL loses
6.3 bp/ON-day — inside band_lab's own stated 4–7 bp/day drag, which calibrates the
figure. FAS is charged **3 bp** for its thinner book. Every FAS number below is
**net**.

## Leverage does not help — confirming `vol_anatomy`

`vol_anatomy` predicted that leverage multiplies amplitude and leaves structure
alone, so Sharpe should be leverage-invariant. It is, exactly:

| FAS recommended | bp/ON-day | **Sharpe** | max DD | CAGR |
|---|---:|---:|---:|---:|
| lev 1× | +16.0 | **1.24** | −23.3% | +9.6% |
| lev 2× | +32.0 | **1.24** | −43.3% | +16.6% |
| lev 3× | +48.1 | **1.24** | −59.8% | +20.4% |

bp/day and drawdown scale together and Sharpe never moves. Worse, CAGR grows
*sublinearly* (+9.6 → +16.6 → +20.4%) because variance drag is quadratic in
leverage — the same arithmetic that makes SOXL a 3× fund rather than a 3× return.
**Leverage is a position-sizing dial, not an edge.** Use `lev` to hit a drawdown
budget, never to rescue a weak Sharpe.

## The recommended FAS sleeve

The improvement over band_lab's FAS cells is **not** leverage. It is the entry
band and the gate. band_lab scaled SOXL's 1% dip by FAS's range ratio to 0.55%;
the fit says go tighter still, to **0.30%**, and raise the gate well above the
range-matched 3.74%.

**Rules — identical to `band_lab` §2 except the four constants:**

| | SOXL (locked) | **FAS (this sleeve)** |
|---|---|---|
| Daily gate | ATR5 ≥ 6.00% | **ATR5 ≥ 4.25%** |
| Morning filter | stand down if OR30 ≥ thr80 **and** pos10 < 2/3 | *unchanged* |
| First order | 11:00 ET (bar 18) | *unchanged* |
| Entry | resting buy limit at session-high × (1 − **1.0%**), ratchets up only | session-high × (1 − **0.30%**) |
| Target | E × (1 + **1.0%**) | E × (1 + **0.30%**) |
| Stop | E × (1 − **4.0%**) | E × (1 − **3.0%**) |
| Breakers | max 5 fills, max 2 stop-outs | *unchanged* |
| Flatten | 15:55, never overnight | *unchanged* |

Full sample, net of costs:

| | ON days | ON rate | trades/day | bp/ON-day | Sharpe | max DD | CAGR | win rate | worst day | yrs + |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SOXL locked | 787 | 52% | 3.17 | **+59.3** | **2.80** | −38.1% | +101.3% | 76.3% | −8.0% | 6/7 |
| **FAS recommended** | 395 | 26% | 4.23 | **+16.0** | **1.24** | −23.3% | +9.6% | 86.7% | −6.1% | 4/7 |

That is a **real improvement on band_lab's FAS** — from +7.1 bp/ON-day *gross* at
Sharpe 0.49 to **+16.0 bp net at Sharpe 1.24** — and it is honest out-of-sample:
parameters were chosen on 2020-07→2024-06 only, and the surviving cells hold up on
2024-07→2026-07 (IS→OOS bp correlation **+0.86**).

### Where it is fragile

* **The gate is the whole game.** 3.34% → +6.1 bp/0.53; 3.74% → +7.2/0.58;
  **4.25% → +16.0/1.24**; 4.75% → +20.3/1.54; 5.25% → +15.0/1.09. Below ~4.25 the
  edge collapses. This is a cliff, not a gentle slope.
* **The dip is a genuine plateau** (0.25–0.35% all give 1.09–1.24 Sharpe).
* **The stop is not.** 2.00% → +10.3, 2.50% → **+7.2**, 3.00% → +16.0, 3.50% →
  +13.9. The non-monotonicity across 2.5% says this axis is noise; do not read the
  3.0% choice as optimised.
* Only **4 of 7 years positive** (2022 −5.4%, 2026 −0.7%), on 19–170 ON days a year.
* The out-of-sample survivors carry 53–88 ON days. Small samples.

## The finding that decides the allocation question

band_lab found that SPXL and FAS both *lose* on the days SOXL is idle. **This
sleeve replicates it, on its own re-fitted parameters:**

| | n days | bp/day | cumulative |
|---|---:|---:|---:|
| FAS ON **and** SOXL ON | 290 | **+25.9** | +75.1% |
| FAS ON, **SOXL idle** | 105 | **−11.2** | **−11.8%** |

FAS earns only when SOXL's volatility regime is also live, and loses on precisely
the days that would have supplied independent diversification. Correlation on
both-ON days is +0.477.

Consequently a FAS sleeve does not improve a SOXL book at any weight:

| SOXL / FAS | CAGR | max DD | Sharpe |
|---|---:|---:|---:|
| 1.00 / 0.00 | +101.7% | −38.1% | **2.01** |
| 0.90 / 0.10 | +91.0% | −35.2% | 2.01 |
| 0.75 / 0.25 | +75.6% | −30.7% | 2.00 |
| 0.50 / 0.50 | +51.4% | −22.7% | 1.91 |
| 0.00 / 1.00 | +9.6% | −23.3% | 0.63 |

Sharpe never improves; CAGR falls monotonically. The blends only reduce drawdown,
which the `f` dial on SOXL does more cheaply.

## Verdict

**As a standalone sleeve, this is tradable** — Sharpe 1.24 net, −23.3% max
drawdown, 86.7% win rate, a −6.1% structural worst day, on 26% of sessions. If FAS
is the only instrument available, these are the constants to use, and they are
roughly twice as good as rescaling SOXL's.

**As an addition to a SOXL book, it is not worth funding.** It earns nothing on
the days it would diversify, and no weight improves portfolio Sharpe. That
reproduces band_lab's conclusion on independently re-fitted parameters, which
makes it a property of the strategy family rather than of their parameter choice.

**On leverage:** it changes the size of the outcome and never its quality. Because
the sleeve is flat overnight, leverage here is day-trading buying power and carries
no financing cost — which makes it tempting and no less dangerous. At 3× the
drawdown is −59.8% for a CAGR of +20.4%.
