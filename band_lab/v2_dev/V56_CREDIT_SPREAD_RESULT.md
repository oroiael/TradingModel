# V56 — Defined-risk credit spreads, measured. Not adopted.

Tested against `V55_CREDIT_SPREAD_BAR.md`, committed before the code existed.

    python3 band_lab/v2_dev/credit_spread_backtest.py

1,336,996 quotes, 1,128 dates, 2022-01-03 → 2026-07-02. 1,748 cycles across 27
cells. Short leg 25-delta, long leg 10-delta, every leg crossing its spread,
$0.65 a contract a side, expiry settled at intrinsic.

## Verdict

**Not adopted. 0 of 27 cells positive.**

| bar | test | result | |
|---|---|---|---|
| B1 | best-cell mean > 0, t > 2.0 | **−1.56%, t = −0.16** | **FAIL** |
| B2 | positive in ≥ 4 of 5 years | 4 of 5 | PASS |
| B3 | every cost charged | $4,198, 100% of cycles | PASS |
| B4 | ≥ 20 of 27 cells positive | **0 of 27** | **FAIL** |
| B5 | headline within 1 SE of grid median | 0.83 SE | PASS |
| B6 | max drawdown < 50% | **−354%** | **FAIL** |
| B7 | beat buy-and-hold on MAR | negative vs **1.67** | **FAIL** |
| B8 | no cycle exceeds its max loss | see below | **qualified** |

B2 and B5 pass only because the best cell is a 27-cycle sample whose mean is
indistinguishable from zero — passing a consistency gate by being too small to
say anything is not a pass worth having.

## B8 fired, and it was worth writing

147 of 1,748 cycles lost more than the stated max loss. Investigated rather than
reported around:

- **95.9% are commission.** Median excess 0.49% of max loss against fees of
  0.38%. B8 compared P&L to a **pre-fee** theoretical max loss, so paying the
  commission takes a fully-breached spread just past it. The gate's threshold
  was mis-specified, not the simulator.
- **5 are `roll21` exits** where buying the short back at the ask and selling
  the long at the bid on a deep-in-the-money vertical costs $0.20 to $2.95 more
  than the width. That is a real execution cost of crossing both sides, and it
  is conservative rather than wrong.

Re-scored against a fee-inclusive max loss: **6 breaches in 1,748 (0.34%)**, all
early exits. **The position was never misrepresented.** The gate did its job —
it forced the check that showed there was nothing to find.

## Why it fails, in one table

| structure | credit / width | breakeven win rate | actual win rate at expiry |
|---|---|---|---|
| put credit spread | **18%** | **82%** | 71% |
| call credit spread | **9%** | **91%** | 77% |
| iron condor | **24%** | **76%** | 50% |

A 25/10 vertical collects a fifth of its width, so it must win four times in
five simply to break even, and every loss is close to the full width. None of
the three gets there. **Defining the risk did truncate the tail — V54's worst
cycle was −268.8% and here the worst is −147% — and it truncated the credit by
more.**

## The skew is why the call side is worse

The put spread collects 18% of its width and the call spread 9%. That is the
+11.6-point put skew V28 measured, seen from the selling side: puts are dear and
calls are cheap, so selling calls collects half as much for the same width.
Selling the cheap side into a window where SOXL rose 151% was doubly wrong, and
the call spread's −15.6% a cycle at 21-30 days is the worst single structure in
this study.

## What this settles

| | naked (V54) | defined-risk (V56) |
|---|---|---|
| cells positive | 0 of 18 | **0 of 27** |
| best cell | −1.600%, t = −2.69 | −1.56%, t = −0.16 |
| worst cycle | −268.8% | −147% |

Forty-five grid cells across two studies, five years, 3,096 cycles, every cost
charged, both bars written before their code. **Not one cell is positive.**

The tail was never the reason short vol failed here. The reason is that the
credit does not cover the move, and capping the loss caps the credit with it.

## Known omissions, unchanged

Early assignment is not modelled and hurts the short leg. Pin risk is ignored.
Margin appears only as the max-loss denominator. No IV-rank or regime gate.
