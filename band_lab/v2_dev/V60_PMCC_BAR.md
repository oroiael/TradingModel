# V60 — The bar for the PMCC, written before the code

**Status: PRESPECIFIED. No backtest code exists yet. Results go in V61.**

V22 audited this project's own top recommendations against the thing they trade
and found R1 lost 65% of capital while SOXL rose 383%. In the same audit, one
structure came out the other way:

> **R2 is the more interesting case and should not be called a failure.** It
> returns less than the underlying but takes far less risk: MAR 1.61
> (65.8/40.8) against buy-and-hold's 0.98 (86.0/88.0). A deep-ITM call is a
> leveraged long, so most of its return is beta — but it is beta with a defined
> floor, which is a real thing to want. **It was never presented that way
> because the benchmark was never computed.**

That is the only benchmark-beating number in this repository, and it has never
been tested against a prespecified bar. This is that bar, committed before the
code so it cannot be moved to fit what comes back.

## The structure

**PMCC / call diagonal.** Per `STRATEGY_RECOMMENDATIONS.md` R2:

| leg | rule |
|---|---|
| LONG | one call, delta nearest the target, **120–180 DTE** at entry. Rolled to a new 120–180 DTE call when DTE ≤ 45. |
| SHORT | one call, delta nearest the target, nearest expiry at **3–10 DTE**. Held to expiry, settled at intrinsic against SOXL's close. |
| ratio | strictly **1:1**. The short is always covered by the long. Never naked. |

No restrikes, no delta-defense trigger, no put wings, no regime gate. Those are
searchable parameters and V22's warning about `active_lab` — top row of a sorted
grid, one episode contributing +326% — is exactly what searching produces. This
test searches nine cells and stops.

**Window:** the full option chain, 2022-01-03 → 2026-07-02. Deliberately wider
than V22's 2024–2026, because that window is a +383% melt-up and 2022 is the
only bear regime in the files.

## The grid — 9 cells, fixed now

Long delta **{0.70, 0.75, 0.80}** × short delta **{0.10, 0.175, 0.25}**.
Nothing else is varied.

## The three controls, which are the point

| control | what it isolates |
|---|---|
| `buy_hold` | SOXL shares. **The benchmark.** |
| `long_only` | the deep-ITM call alone, shorts off | 
| `covered_call` | shares plus the same short calls |

`long_only` is the control that matters. If PMCC ≈ `long_only`, then the short
call adds nothing and the structure is not a strategy — it is "buy a deep-ITM
call," and should be described that way. **B7 exists to force that admission.**

## Sizing — the assumption that decides whether the MAR claim means anything

V22's R2 was sized to the **same notional** as a 75% share position. A
0.75-delta call at the same notional carries **0.75× the delta of the shares**,
so a lower drawdown is partly just a smaller position. That would make the MAR
advantage an artifact of exposure rather than a property of the structure.

**Primary test is delta-matched.** Contracts are sized so the PMCC's initial
delta equals the benchmark's share delta:

    contracts = floor( equity / (spot * 100 * long_delta) )

Any drawdown reduction that survives delta-matching is a real property of owning
convexity with a floor. Same-notional sizing is reported second, labelled, and
is not what the gates are read against.

**Unspent cash earns 0%** in the headline. A PMCC frees roughly two thirds of
the capital and what that cash earns is a large part of the answer, so the
T-bill case is run as a stated sensitivity — never as the headline.

## Costs, all charged

| | |
|---|---|
| every option leg opened | pay the **ask** |
| every option leg closed | receive the **bid** — cross the full spread |
| short call held to expiry | settled at intrinsic, **no closing spread** |
| commission | **$0.65** per contract per side |
| shares (benchmark and `covered_call`) | at the file's EOD underlying price |

This is V54/V56/V58's convention exactly — `fill = 1.0` in V58's parameterisation
— so the numbers are comparable to everything in the V53–V58 sequence. V22 noted
the prior R2 engine charged only **0.6×** the spread; that is rung D of the V58
ladder, and this test does not use it.

## Gates

| bar | test | why |
|---|---|---|
| **B1** | beats buy-and-hold SOXL on **MAR**, delta-matched, full window | the entire claim |
| **B2** | beats buy-and-hold on MAR in **≥ 4 of 5** calendar years | not one regime |
| **B3** | every cost above actually charged, verified in the ledger | process |
| **B4** | **≥ 7 of 9** grid cells beat buy-and-hold on MAR | not a lucky corner |
| **B5** | headline cell's mean weekly return within **1 SE of the grid median** | not cherry-picked |
| **B6** | max drawdown **strictly lower** than buy-and-hold's | the mechanism being claimed |
| **B7** | beats the **`long_only`** control on MAR | the short leg must earn its place |
| **B8** | no single calendar quarter contributes **> 50%** of total P&L | V22's `meltup26` lesson |

**All eight must pass.** B1 alone reproduces V22's finding; it is B4, B7 and B8
that decide whether the finding is a strategy or an artifact.

## Stated in advance

**This structure is long beta and the sample is a melt-up.** SOXL rose 540%
across the files and +383% in V22's sub-window. A long-biased structure is
exactly what such a sample flatters, and B1/B2/B6 can all pass for that reason
alone. **B7 is the gate that cannot be passed by beta**, because `long_only` is
beta too. If B1–B6 pass and B7 fails, the correct conclusion is "hold a deep-ITM
call instead of shares," not "run a PMCC."

**The prior.** V22 measured MAR 1.61 against 0.98 on 131 weeks at a 0.6 fill and
same-notional sizing. Crossing the full spread, delta-matching, and adding the
2022 bear should all move it down. I expect B1 to be close and B7 to be the one
that fails. Recording that expectation now so it can be wrong in public.

**What a pass would mean.** Eight gates over 4.5 years of EOD quotes with full
spread crossing, against a benchmark computed inside the same harness. That is
the first adoptable result this project would have produced — and it would be a
*risk-shaping* result, not an edge. The PMCC returning less than SOXL while
drawing down less is a success under this bar. Raw return is not a gate, on
purpose.

## Known omissions, named now

- **Early assignment on the short call is not modelled.** SOXL pays dividends,
  and a short call that goes deep ITM into a dividend is the standard assignment
  case. This is the single largest unmodelled risk in the test.
- Early exercise of the long leg is likewise not modelled.
- EOD quotes only — no intraday roll or defense, which is what R2's spec calls
  for. This test is the set-and-forget version of R2, and is weaker than the
  strategy as written.
- Whole-contract rounding at $100,000 of starting capital; no fractional sizing.
- Taxes and borrow are out of scope.
- One underlying, one window, one bear regime.
