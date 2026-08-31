# V38 — Long-dated straddle (V29 Tier 2 #4). Result: **inconclusive**, as prespecified.

Tested against `V37_LONGDATED_BAR.md`, committed before the code existed.

    python3 band_lab/v2_dev/vol_premium_tenors.py
    python3 band_lab/v2_dev/straddle_backtest.py --v37

## Verdict

**Not adopted — but for a different reason than Tier 1.** #1, #2 and #3 were
resolved and failed. This one **cannot be resolved on 4.49 years of data**, which
V37 named as the expected outcome before the code was written.

| bar | test | result | |
|---|---|---|---|
| B1 | return > 0, t > 2.0 on independent cycles | **+69.07%, t = +1.13** | **FAIL** |
| B3 | every cost charged | yes | PASS |
| B4 | ≥ 5 of 6 cells positive | **4 of 6** | **FAIL** |
| B5 | headline within 1 se of grid median | median +16.58% | PASS |
| B7 | max drawdown < 35% | −5% | PASS |

**The headline's 95% confidence interval is [−50.4%, +188.6%].** That is not a
result, it is the absence of one. Reaching t = 2.0 at this effect size needs
**28 cycles = 14 years** of data against the 4.49 available.

## The genuinely new finding, which is not the backtest

The matched-tenor premium had never been measured. **Implied volatility falls
with tenor while realised volatility does not:**

| tenor | implied | realised | **edge** | indep. windows | t |
|---|---|---|---|---|---|
| 1 week | 104.8% | 104.6% | **−0.2** | 224 | −0.08 |
| 1 month | 99.2% | 110.2% | **+10.9** | 53.6 | **2.52** |
| 3 months | 97.0% | 109.1% | +12.0 | 7.3 | 1.20 |
| 6 months | **92.2%** | 108.0% | **+15.8** | 6.1 | 2.00 |
| 1 year | **87.8%** | 108.5% | +20.7 | 1.0 | 1.16 |

The market charges 104.8% for a week and 87.8% for a year; SOXL delivers ~108%
at every horizon. **The premium is therefore largest exactly where V28 measured
the spread to be cheapest.** That is a real term-structure fact, it is the first
thing in this catalogue whose arithmetic survives its own costs, and it is
measured on far more data than any backtest of it can be.

**Only the 1-month row has enough independent windows to carry a t-statistic**,
and V31/V32 already showed that tenor losing 10.11% per cycle once the real
spread is charged. Everything longer is directionally encouraging and
statistically empty.

## The check that deflates the headline

| DTE | cycles | unhedged | win% | hedged daily | win% |
|---|---|---|---|---|---|
| 90 | 17 | −5.10% | 29% | −2.06% | 59% |
| **180** | **9** | **+69.07%** | **44%** | **+0.65%** | **67%** |
| 270 | 6 | +51.56% | 50% | +32.51% | 83% |

The hedged column is the version with the machinery that actually converts a
volatility edge into money — V31 measured a **+0.85** correlation between cycle
return and realised-minus-implied under a daily hedge.

**At 180 DTE the hedged version returns +0.65% per cycle on a 67% win rate.
Essentially zero, consistently.** The unhedged version at the same tenor returns
+69% on a **44%** win rate.

A high mean with a *low* win rate is tail exposure, not harvested volatility.
**The hedge removes the tails and what is left is nothing.** That is the same
shape V36 found in the backspread, where three cycles out of 46 carried a +3.72%
headline.

Note also that the tenor with the most data (90 DTE, 17 cycles) is **negative in
both columns**, and the two positive tenors are the two with the fewest cycles.
That is the signature of noise growing as the sample shrinks. It does not prove
the long-tenor edge is absent — the premium table above is real — but it means
this backtest cannot tell the two apart.

## What was and was not established

**Established.** SOXL's volatility term structure slopes down while its realised
volatility does not, giving a premium that grows from −0.2 vol points at a week
to +15.8 at six months. Measured on 1,120 dates at the short end and 757 at six
months, with standard errors computed on non-overlapping windows.

**Not established.** That the premium is harvestable. The only tenor with a
usable sample loses once the real spread is charged; the tenors where the
arithmetic works have 6 to 9 independent observations and confidence intervals
wider than the effect.

**Working against the structure and not priced in:** the spread shortfall is
unmeasured beyond ~35 DTE (A22), long-dated depth is unmeasured and certainly
thinner than the 512 contracts V32 found at one month (A23), and six months of
SOXL distributions are ignored (A24). All three flatter the result above.

## Where the catalogue stands

| | verdict | on what |
|---|---|---|
| #1 straddle, hedged daily | **rejected** | −10.11%/cycle, t = −3.76, resolved |
| #2 straddle, unhedged | **not adopted** | −0.22%/cycle, one outlier cell |
| #3 call backspread | **not adopted** | −5.46% trimmed, three cycles carried it |
| #4 long-dated straddle | **inconclusive** | CI [−50%, +189%] on 9 cycles |

Three structures resolved and failed. The fourth cannot be resolved here, and
the reason is the data, not the strategy.

**What would settle #4 is the same thing V31 named for #1: more history.** SOXL
has traded since 2010-03-11 and these option files begin 2022-01-03. Twelve more
years would take the 180-DTE sample from 9 cycles to about 33 — past the 28 the
arithmetic says are needed. That is a purchase, not an analysis.

Failing that, the honest position is that **#4 has the best case in the
catalogue and no evidence behind it**, and the two should not be confused.
