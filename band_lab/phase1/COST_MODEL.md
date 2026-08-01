# Cost Model — review and per-trade replacement

> **AMENDED 2026-08.** The per-trade cost model here is unaffected by fill resolution and stands. The *gross* edge it is netted against is not: see `../live/PHASE2_PARITY.md` S11 — costs are a larger share of a 42.5 bp gross edge than of a 65.6 bp one, which matters most for SOXS (9.6 bp/ON-day against 34.2 gross).

**Short answer: the incumbent cost model is not wrong, it is conservative,
and its conservatism is hidden inside the wrong term.** Replacing it with
per-trade costing built on the Phase 1 trade logs moves net edge by
**+0.5 bp/ON-day on SOXL and +1.1 on SOXS** — i.e. the v14 numbers are
slightly pessimistic, which is the safe direction.

Two things did need fixing, and one turned up a live problem with §9's
Phase 3 acceptance criterion.

Regenerate everything here with `python3 band_lab/phase1/cost_model.py`.

---

## 1. What the incumbent does

`v14_pair_protocol.cost_bp` charges a flat per-ON-day figure — SOXL 3.7 bp,
SOXS 9.6 bp — built as

```
per_round_trip = 2 x commission_bp + 0.35 reg_bp + 0.30 x full_spread_bp
per_day        = per_round_trip x assumed_trades_per_day   (3.17 / 3.36)
```

Three structural gaps:

| | gap | status |
|---|---|---|
| **G1** | every ON day is charged the same, though fill counts are bimodal and correlate +0.44 with the day's P&L | **fixed** — per-trade costing off the real trade log |
| **G2** | charges `0.30 x full spread` per round trip; crossing costs a *half* spread, and only the stop and flatten legs cross | **fixed** — and the 0.30 guess turns out to be very close |
| **G3** | assumes a 1-cent spread always, on a strategy that only trades when ATR5 ≥ 6% | **cannot be fixed here** — no quote data exists; quantified as a sensitivity instead |

---

## 2. G2 — which legs actually cross

The strategy's own structure decides this, so it is measurable rather than
assumable:

| leg | order type | crosses? |
|---|---|---|
| entry | resting BUY LIMIT at 0.99 × anchor | no |
| target exit | resting SELL LIMIT at 1.01 × E | no |
| stop exit | SELL STOP → market | **yes** |
| 15:55 flatten | market | **yes** |

Measured share of exits that cross: **28.7% (SOXL), 28.2% (SOXS)** — against
the model's assumed 30%. The guess was very nearly exact.

But it is charged as 30% of a *full* spread, where crossing costs half a
spread on ~29% of round trips. The incumbent therefore charges roughly twice
the spread it names. That excess is not an error — it is a slippage buffer
that was never labelled as one. Solving for the buffer:

> **The v14 flat charge equals per-trade costing at a 1-cent spread plus
> 0.88c (SOXL) / 0.63c (SOXS) of extra slippage on the stop and flatten
> legs.**

That is a reasonable assumption. The point of naming it is that Phase 2 can
now falsify it against real fills; buried inside a spread term, it could not.

### Cost per round trip, by exit type ($150K sleeve, f = 1.0)

| sleeve | price | shares | exit | % of exits | commission | regulatory | execution | **total** |
|---|---|---|---|---|---|---|---|---|
| SOXL | $158.41 | 946 | target | 71.3% | 0.63 | 0.29 | 0.00 | **0.92 bp** |
| SOXL | | | stop | 9.9% | 0.63 | 0.29 | 0.32 | **1.24 bp** |
| SOXL | | | flatten | 18.8% | 0.63 | 0.29 | 0.32 | **1.24 bp** |
| SOXS | $51.61 | 2,906 | target | 71.8% | 1.94 | 0.31 | 0.00 | **2.25 bp** |
| SOXS | | | stop | 9.3% | 1.94 | 0.31 | 0.97 | **3.22 bp** |
| SOXS | | | flatten | 18.9% | 1.94 | 0.31 | 0.97 | **3.22 bp** |

SOXS costs ~2.5× SOXL per round trip for one reason: IBKR charges per
*share*, and $150K buys 3× more shares of a $51 instrument than a $158 one.

---

## 3. G1 — per-trade costing vs the flat charge

Fill counts are strongly bimodal — 243 of 787 SOXL ON-days hit the 5-fill
cap, 131 take a single fill — and they correlate **+0.44** (SOXL) / **+0.57**
(SOXS) with the day's P&L. Mean P&L by fill count (SOXL, bp): 1 fill −54,
2 fills −100, 3 fills −17, 4 fills +67, 5 fills +298.

A flat charge is right on the mean and wrong on the distribution: it
overcharges the low-fill days, which are the losing days, and undercharges
the 5-fill days, which are the winners.

| sleeve | model | net bp/ON-day | Sharpe | worst day | mean cost | cost p5 | cost p95 |
|---|---|---|---|---|---|---|---|
| SOXL | v14 flat | 61.9 | 2.91 | −8.037% | 3.71 | 3.71 | 3.71 |
| SOXL | **per-trade** | **62.4** | **2.94** | **−8.025%** | 3.21 | 1.24 | 4.92 |
| SOXS | v14 flat | 48.1 | 2.19 | −8.096% | 9.63 | 9.63 | 9.63 |
| SOXS | **per-trade** | **49.2** | **2.25** | **−8.064%** | 8.47 | 3.22 | 12.22 |

Real per-day cost spans **1.24 → 4.92 bp** on SOXL and **3.22 → 12.22 bp**
on SOXS, against a flat 3.71 / 9.63. The worst-day figure improves slightly
under per-trade costing, because the worst days are two-stop days that carry
only two round trips.

---

## 4. G3 — the spread assumption, which nobody has measured

The repository holds 5-minute OHLCV and no quotes, so **the spread cannot be
measured here at all.** What can be measured is the regime it is sampled in,
and the strategy self-selects into volatile days by construction:

| sleeve | median 5-min bar range, ON days | OFF days | ratio |
|---|---|---|---|
| SOXL | 66.0 bp | 55.3 bp | **1.19×** |
| SOXS | 69.4 bp | 59.0 bp | **1.18×** |

So a 1-cent assumption calibrated on an average day is optimistic for the
days actually traded — but only mildly. A ~1.2× regime scaling implies
~1.2 cents, not 3–5.

### Sensitivity — net bp per ON-day

**SOXL** (gross 65.6) — barely sensitive, because it is a $158 instrument
where commission dominates:

| spread ↓ / slippage → | 0c | 1c | 2c |
|---|---|---|---|
| 1c | 62.4 | 61.8 | 61.2 |
| 2c | 62.1 | 61.5 | 61.0 |
| 3c | 61.8 | 61.2 | 60.7 |
| 5c | 61.2 | 60.7 | 60.1 |

**SOXS** (gross 57.7) — 3× more sensitive, because a cent is 1.94 bp on a
$51 instrument:

| spread ↓ / slippage → | 0c | 1c | 2c |
|---|---|---|---|
| 1c | 49.2 | 47.4 | 45.6 |
| 2c | 48.3 | 46.5 | 44.6 |
| 3c | 47.4 | 45.6 | 43.7 |
| 5c | 45.6 | 43.7 | 41.9 |

Across the whole grid SOXL moves 2.3 bp and SOXS moves 7.3 bp. **All cost
uncertainty in this strategy lives in the SOXS sleeve**, and it is a
price-level effect, not a strategy effect — if SOXS reverse-splits to a
higher price, its cost in bp falls proportionally.

---

## 5. Does any of this move w? No.

§2.9 sets w = 0.50 per the validated plateau. The obvious worry is that a
harsher SOXS cost model should shift capital toward SOXL. It does not:

| cost scenario | SOXL net | SOXS net | argmax w | Sharpe at argmax | Sharpe at w=0.5 |
|---|---|---|---|---|---|
| v14 flat (incumbent) | 61.9 | 48.1 | **0.50** | 3.83 | 3.83 |
| per-trade, 1c spread | 62.4 | 49.2 | **0.50** | 3.90 | 3.90 |
| per-trade, 2c + 1c slip | 61.5 | 46.5 | **0.50** | 3.76 | 3.76 |
| per-trade, SOXS stressed 5c + 2c slip | 60.1 | 41.9 | **0.50** | 3.54 | 3.54 |

w = 0.50 is the Sharpe argmax under every scenario tested, including one
that strips 7.3 bp off SOXS. The pair decision is not cost-model-dependent —
it rests on the diversification of ON-days, not on the level of either
sleeve's edge.

---

## 6. A live problem with §9's Phase 3 criterion

§9 Phase 3 runs at **10–20% of intended capital**, then asks whether
realised cost matches "the modelled 3.7 bp/day (SOXL) and 9.6 bp/day
(SOXS)". Those are **$150K figures**. IBKR's **$1.00 per-order minimum**
binds well before that:

| sleeve capital | SOXL shares/order | $1 min binds | SOXL cost bp/ON-day | SOXS cost bp/ON-day |
|---|---|---|---|---|
| $10,000 | 63 | **YES** | **7.5** | 8.7 |
| $22,500 | 142 | **YES** | **4.0** | 8.5 |
| $30,000 | 189 | **YES** | 3.3 | 8.5 |
| $50,000 | 315 | no | 3.2 | 8.5 |
| $150,000 | 946 | no | 3.2 | 8.5 |
| $500,000 | 3,156 | no | 3.2 | 8.5 |

At 15% of a $150K sleeve ($22.5K) SOXL costs **4.0 bp/ON-day, not 3.2** —
25% higher, purely from the order minimum. At $10K it is 7.5 bp, more than
double. A correctly functioning system measured against the $150K number
would look like it was failing.

**Phase 3 must compare realised cost against the row for its own account
size, not against the $150K row.** `out/cost_by_account_size.csv` is that
table. SOXS is largely immune — a cheap instrument buys enough shares that
the minimum rarely binds.

---

## 7. Recommendations

1. **Keep the conservatism, do not bank the +0.5 / +1.1 bp.** The per-trade
   model is more accurate, but the difference is a slippage buffer that has
   never been tested against a real fill. Carry `v14`'s numbers as the
   planning case and the per-trade model as the measurement instrument.
2. **Carry the buffer explicitly** as 1c spread + ~0.9c (SOXL) / ~0.6c
   (SOXS) slippage on the stop and flatten legs, so Phase 2 can falsify it.
3. **Fix §9's Phase 3 criterion** to size-appropriate targets. *(Done — §9
   now points at the account-size table.)*
4. **Phase 2 should log the quoted spread at every order event.** It is the
   one input here that no amount of further analysis can supply, and it is
   the only one with real leverage — on SOXS.
5. **Re-check the SEC Section 31 rate before Phase 3.** The model carries
   0.28 bp; the SEC resets the rate at least annually and it has moved by
   more than 3× between recent fiscal years. It is a small term, but it is
   free to get right.

## 8. What is deliberately *not* modelled

- **Borrow and financing costs** — none apply. No shorting, nothing held
  overnight, no margin beyond settlement convenience (§11).
- **Market-data subscription** — a fixed monthly fee, ~0.03 bp/day amortised
  over a $300K account. The parameter exists (`market_data_usd_per_month`)
  and defaults to 0.
- **Market impact** — v14 §T6 measured a $150K order at 1.09 bp (SOXL) and
  2.18 bp (SOXS) of a day's dollar volume. At that participation, impact is
  not distinguishable from spread and is folded into the slippage term.
- **Fill probability.** The largest untested assumption in the project is
  not a cost at all: whether a resting 0.99× limit fills the way the
  backtest assumes. No cost model can address it. Paper trading can.
