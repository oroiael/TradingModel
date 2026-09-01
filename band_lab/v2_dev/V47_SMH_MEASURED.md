
# V47 — SMH measured against a live IBKR session. Result.

Run: `vol_premium_ibkr.py`, 2026-08-31, paper session, server version 178.
Cross-section as of Friday 2026-08-28, 35 DTE. Selftest 5/5 before connecting.

## Part A settles the V45/V46 question. The additive model is dead.

|  | IV_SOXL / IV_SOXX |
|---|---|
| proportional predicts | **2.97** |
| additive predicts | 3.75 |
| **observed** | **2.97**  (116.0% / 39.1%) |

An essentially exact hit, 0.01 away from the prediction and 0.79 from the
alternative. **V44's additive assumption is refuted by measurement**, not just by
the arbitrage argument V46 rested on. The leverage identity holds in live
prices: the market prices the 3× fund's volatility at 2.97× the index's, the
same ratio at which the fund delivers it.

### The spreads replicated exactly

| symbol | spot | K | DTE | IV | round trip |
|---|---|---|---|---|---|
| SOXL | 111.37 | 111.0 | 35d | 116.0% | **18.5 vol pts** |
| SOXX | 508.53 | 507.5 | 35d | 39.1% | **8.0 vol pts** |
| SMH | 553.09 | 552.5 | 35d | 35.0% | **2.9 vol pts** |

V43 measured 18.5 / 8.0 / 2.9 on a different session. Reproducing three spreads
to the decimal on a different day is a stronger check on V43 than anything run
at the time.

## Part B's control FAILED, and it was right to

| | implied | realised | edge |
|---|---|---|---|
| V37, vendor option files | 99.2% | 110.2% | +10.9 |
| IBKR `OPTION_IMPLIED_VOLATILITY` | **6.2%** | 108.9% | +102.7 |

**Gap 91.8 volatility points against a 3-point tolerance.** The realised side
agrees to 1.3 points; only the implied side is wrong, and it is wrong by a
**factor of 16.0**, not an offset.

Without the control, Part B would have reported SMH's 1-month edge as **+32.9
with t = 22.33, clearing its 2.9 spread by an order of magnitude** — and every
symbol at every tenor showing `YES`. That table is not a discovery, it is a unit
error, and a gate written before the run is the only reason it is labelled as
one. This is the V28 vega mistake in a different field, caught this time.

### The likely cause, not yet adopted

SOXL's annualised implied vol of 99.2% is a **daily** sigma of
0.992 / √252 = **6.25%**. The series reports **6.2%**.

That fits to within the printed precision, and √252 = 15.87 against the observed
factor of 16.0. But **a factor that reproduces one number is a coincidence until
it reproduces an independent one**, so it is not applied. `--diagnose` tests it
against two references on matched dates:

1. `OPTION_IMPLIED_VOLATILITY` vs the live ATM chain IV computed here from
   bid/ask through Black-Scholes — same symbol, same session, two unrelated
   paths through the API.
2. `HISTORICAL_VOLATILITY` vs trailing 30-session realised vol computed here
   from the TRADES bars — **no options involved at all**, so agreement means the
   factor is a property of IBKR's volatility encoding rather than of one field.

A correction fitting only one reference is rejected. If both agree the factor is
identified, and the Part B control is then what validates it.

## Where this is heading, stated before the rerun

Applying √252 to the printed figures gives:

| symbol | implied | realised | edge | spread | **net** | clears? |
|---|---|---|---|---|---|---|
| SOXL | 98.4% | 108.1% | +9.7 | 18.5 | −8.8 | no |
| SOXX | 33.3% | 36.4% | +3.1 | 8.0 | −4.9 | no |
| **SMH** | **33.3%** | **35.0%** | **+1.7** | **2.9** | **−1.2** | **no** |

The SOXL row would put the control at +9.7 against V37's +10.9 — **a 1.2-point
gap, inside the 3-point tolerance. The control would pass.**

**And SMH would not clear.** V46 predicted +3.7 against 2.9 for a net of +0.8;
the measurement points to **+1.7 against 2.9, net −1.2**. The printed 2.1% is
rounded to one decimal, so the true value lies in 2.05–2.15 and the edge in
**+0.9 to +2.5 — below 2.9 across the whole range.**

These figures are **provisional** and depend entirely on a correction that has
not yet passed its own diagnostic. They are recorded now so the rerun confirms
or refutes a stated expectation rather than producing one.

## A distinction V46 blurred, and the measurement forces

V46 used "proportional" for two different claims:

1. **Implied vol scales with leverage across a levered pair.** Part A confirms
   this, decisively, at 2.97 against 2.97.
2. **The premium as a *fraction* of implied vol is the same on every
   underlying.** V46 assumed this to carry SOXL's 11% relative premium onto SMH
   and get +3.7. **Part A does not establish it, and Part B's provisional
   numbers contradict it:** SOXL's ratio RV/IV is 108.1/98.4 = **1.099**, SMH's
   is 35.0/33.3 = **1.051**. SMH's relative premium looks like roughly **half**
   SOXL's.

That is plausible on its own terms — leveraged-ETF options carry demand a plain
index ETF's do not — but it was assumed rather than measured, and assuming it
is what produced V46's +3.7. **Claim 1 survives. Claim 2 does not, and it was
the one doing the work.**

## Status of the catalogue

Every structure in V29 has now been resolved against, and the necessary
condition — edge > own spread — is not met by **any** of the three underlyings
measured, once the units are right. SMH was the last candidate.

The rerun with `--iv-scale` is what makes that final rather than provisional.
