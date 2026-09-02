# V53 — The bar for the short-vol backtest, written before the code

**Status: PRESPECIFIED. No code exists yet. Results go in V54.**

Long volatility has been backtested five times here — V31, V34, V36, V38, V42 —
and **short volatility has never been backtested once.** Every short structure
was retired on a volatility-point screen, and V31 is the standing proof that the
screen can be wrong by more than its own answer: it said +3.7 points and the
backtest returned −2.94%/cycle.

This is the bar that decides whether the short side is adopted. It is committed
before the code so it cannot be moved to fit what comes back.

## The structure

Short an ATM straddle on SOXL, and short a 25-delta strangle, from the EOD quote
file. One position at a time, cycles non-overlapping so observations are
independent.

## Costs, all charged, no exceptions

| | |
|---|---|
| entry | sell at the **bid** — cross the full spread |
| exit | buy back at the **ask** — cross it again |
| expiry exit | settle at intrinsic against SOXL's close, **no closing spread** |
| commission | $0.65 per contract per side |
| assignment | not modelled; noted as a known omission |

The expiry path genuinely avoids a closing spread and that is a real advantage
of holding to expiry, not an accounting convenience.

## The grid — 3 tenors x 3 exit rules

Tenors by DTE at entry: **21-30, 31-45, 46-60.**
Exits: **hold to expiry**, **take profit at 50% of credit**, **roll/close at 21
DTE.** Both structures run the full grid. No other parameters are searched.

## Gates

| bar | test | why |
|---|---|---|
| **B1** | mean return per cycle > 0 with **t > 2.0** | the headline |
| **B2** | positive in **at least 4 of 5** calendar years | not one regime |
| **B3** | every cost above actually charged, verified in the ledger | process |
| **B4** | **at least 7 of 9** grid cells positive | not a lucky corner |
| **B5** | headline cell within **1 SE of the grid median** | not cherry-picked |
| **B6** | max drawdown **< 50%** on the cycle equity curve | survivable |
| **B7** | **beats buy-and-hold SOXL on MAR** over the identical window | V22's lesson: no strategy here was ever measured against the thing it trades |

**All seven must pass.** V22 found the project's top recommendation lost 65%
while the underlying rose 383%, because nobody printed the benchmark. B7 is not
optional.

## Stated in advance

**Short vol's payoff is many small wins and rare large losses.** A positive mean
with a t of 2.1 and a −70% drawdown is a fail, not a marginal pass — which is
what B6 and B7 exist to catch. The mean is the least informative number this
test will produce and it is deliberately not the only gate.

**The prior.** Eleven structures have been screened negative and two were
measured negative. The screen said the short straddle nets roughly −30
volatility points. If that is even half right the backtest fails B1 immediately.
The reason to run it anyway is that the screen has a known error of unknown sign
on short gamma, and one measurement beats an argument.

**What a pass would mean.** Seven gates on five years of EOD quotes with full
spread crossing. That is evidence worth acting on, not proof — the sample is
~40-60 independent cycles depending on tenor, and assignment risk is unmodelled.

## Known omissions, named now

- Early assignment on short American options is not modelled.
- Margin is not modelled; results are per-straddle, not per-dollar-of-capital.
- No IV-rank or regime gate — that is P3 and depends on this existing first.
- EOD quotes only, so no intraday management of any kind.
