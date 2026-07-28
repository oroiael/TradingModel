# 1% Cycle Lab — SOXL shares-only cycle with 5-day-stall put hedge

Backtests the rule set: buy 100 SOXL; limit-sell at +1% and restart; if a lot
stalls 5 trading days, buy a new 100-share lot **and** buy one ~30-DTE put
(first strike below spot) against the stalled lot; at put expiry either
exercise or sell (whichever is better) and sell the stalled shares.

- Underlying: `SOXL_5min_6Years.csv` (2020-07-16 → 2026-07-21, unadjusted;
  the 2021-03-02 15:1 split is adjusted in-code).
- Options: `SOXL_Options_2022..2026.csv` EOD chains (real bid/ask). Puts are
  bought at the ask, sold at the bid; exercise modeled at intrinsic.
- Strategy window: **2022-01-03 → 2026-07-02** (options data coverage).
  No commissions (see caveats).

Run: `python3 cycle_lab/one_pct_cycle_lab.py` → outputs in `cycle_lab/out/`.

## Part A — how often does SOXL cross +1% of entry?

Full 6-year history, entry re-based only when the target is hit:

| target | intraday hits | per year | median days to hit | % hit ≤5 trading days | EOD-close hits |
|-------:|--------------:|---------:|-------------------:|----------------------:|---------------:|
| +0.5%  | 434 | 72 | 0 (same day) | 96.8% | 70 |
| +1.0%  | **227** | **38** | **0 (same day)** | **93.0%** | **64** |
| +2.0%  | 126 | 21 | 1 | 87.3% | 54 |
| +3.0%  |  87 | 15 | 1 | 82.8% | 48 |

Intraday matters a lot: checking only EOD closes detects ~1/4 of the 1%
touches (64 vs 227). Within the strategy itself (entry re-based every ≤5
days), **1,460 lots were started over 4.5 years: 1,363 (93.4%) hit +1%
within 5 trading days — 70% the same day — and 97 (6.6%) stalled.**

## Part B — the strategy as specified

2022-01-03 → 2026-07-02, 100 sh/lot, real put quotes:

| metric | value |
|---|---|
| Total P&L | **+$17,119** |
| Cycle wins | 1,363 × avg **+$65** = +$88.1k |
| Stalled lots | 97 × avg **−$640** = −$62.1k |
| Put spend / put P&L | $40.4k spent, **−$31.7k net** (51 exercised, 43 worthless, 3 sold) |
| Max concurrent lots | 5 (4 hedged + active) → max capital ≈ **$81.8k** |
| Max drawdown | −$27.2k |
| Return on max capital | 20.9% (4.5 yrs) |
| Buy & hold 100 sh (same window) | +$10.9k on $30.1k max capital, DD −$12.0k |

The shape of the trade: many small wins, few large losses. One stalled lot
(−$640 avg) erases ~10 wins (+$65 avg). The puts were exercised more often
than not (51/97) yet still lost $31.7k net — an ATM 30-day SOXL put costs
~$416/contract (~14% of notional at 80–110% IV), so the insurance premium
ate the protection.

## Part C — variants and controls

| variant | total P&L | put/option P&L | max capital | max DD | ret on max cap |
|---|---:|---:|---:|---:|---:|
| **USER SPEC** 1%/5d/put just-OTM | +$17.1k | −$31.7k | $81.8k | −$27.2k | 20.9% |
| No hedge (same timeline) | **+$24.5k** | 0 | $81.8k | −$30.1k | 29.9% |
| Stop & reset (sell stalled lot, no double-up) | +$8.3k | 0 | **$30.1k** | **−$12.5k** | 27.6% |
| Early unwind hedged lot at breakeven | +$13.2k | −$26.1k | $54.6k | −$16.2k | 24.2% |
| Put 5% / 10% further OTM | +$17.1k / +$17.2k | −$24.8k / −$19.9k | $81.8k | ≈−$28k | ~21% |
| **Target 2%** (else user spec) | **+$29.6k** | −$34.0k | $81.8k | −$27.4k | **36.1%** |
| Target 3% | +$23.4k | −$35.5k | $81.8k | −$27.3k | 28.5% |
| Stall 3d | +$29.9k | −$53.3k | $90.3k | −$29.7k | 33.1% |
| Stall 10d | +$4.8k | −$15.8k | $60.2k | −$20.7k | 7.9% |
| **Covered call on stalled lot** (just OTM, instead of put) | +$17.3k | **+$35.7k collected** | $81.8k | **−$12.9k** | 21.2% |
| Covered call 5% OTM | +$16.1k | +$29.5k | $81.8k | −$13.8k | 19.6% |
| Buy & hold 100 sh | +$10.9k | — | $30.1k | −$12.0k | 36.2% |

## Recommendations

1. **Drop the bought put.** It is the single biggest drag: $40.4k spent,
   $8.7k recovered. The no-hedge control beats the spec by +$7.3k with only
   marginally worse drawdown. SOXL implied vol (80–110%) makes 30-day ATM
   puts structurally too expensive for a 30-day hold.
2. **If you want the stalled lot protected, sell a covered call on it
   instead.** Same total P&L as the spec (+$17.3k) but **half the drawdown**
   (−$12.9k vs −$27.2k), because you collect ~$35.7k of premium instead of
   paying $40.4k. It caps the stalled lot's recovery, which historically cost
   almost nothing.
3. **Raise the target from 1% to 2%.** Nearly identical win count in dollar
   terms per attempt but far fewer round trips (730 vs 1,363) and the best
   total P&L / return on capital (+$29.6k, 36%). At 1%, 70% of fills happen
   the same day — you're paying churn (and would pay commissions/slippage)
   for tiny increments while keeping full downside.
4. **Mind the stacking.** The "buy another 100 on stall" rule quietly ran up
   to 5 concurrent lots — $82k committed when the headline trade is $30k.
   If capital is fixed, the stop-and-reset control (sell the stalled lot,
   restart — never double up) returns 27.6% on a third of the capital with
   −$12.5k DD, and is the most capital-efficient of the rule-based variants.
5. Deeper-OTM puts (5–10%) don't help; hedging sooner (3-day stall) adds
   P&L but burns even more premium and capital; waiting 10 days is worst.

## Caveats

- No commissions/slippage: 1,460 stock round trips ≈ $3k at $2/round-trip,
  which would eat ~18% of the spec's P&L (the 2% target halves this churn).
- Limit fills assumed at the target price (gap-up opens fill at the open).
- Options are EOD quotes; the put is assumed bought at that day's closing ask.
- Mid-2025 → mid-2026 in this dataset is extraordinarily volatile
  (±15–25% days); it drives a large share of cycle wins. The 2022 bear
  drives most of the stall losses. Regime dependence is severe.
