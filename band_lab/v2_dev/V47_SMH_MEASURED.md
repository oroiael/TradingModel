
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

## The diagnostic ran, and my verdict logic was wrong

```
raw OPTION_IMPLIED_VOLATILITY, last 5 bars:  0.0748 0.0740 0.0706 0.0691 0.0645

reference 1  live ATM chain 116.04%  vs series 6.91%   ratio 16.793
reference 2  my realised   101.96%   vs HV     6.12%   ratio 16.432
```

It reported **"the two references DISAGREE"** and refused the correction. That
verdict is wrong. **The two references agree with each other to 2.2%** — 16.793
against 16.432. What they disagree with is my *candidate list*: the nearest
convention, √252 = 15.87, is 3.5–5.8% below both. I coded the check to compare
each reference against the candidates instead of first asking whether the
references agreed with each other, so a 2% agreement got reported as a
disagreement. Fixed.

The substantive conclusion still stands, for a different reason: **a unit
convention is exact.** A consistent 3–6% overshoot on 1,222 matched dates is not
noise, and no convention sits at 16.6. So something beyond units is in play, and
the obvious candidate is that IBKR's estimator is not mine — its window, mean
handling and day count are all unknown here, and each moves the level a few
percent without touching the unit.

### `--calibrate` separates the two

It reconstructs `HISTORICAL_VOLATILITY` from IBKR's own TRADES bars across 72
estimators (12 windows × 3 mean treatments × 2 lags) and forms

    ratio_t = my_daily_sigma_t / ibkr_raw_t

**If the estimator is right, that ratio is constant.** The dispersion is the
evidence; the value it settles at is the unit convention, read off rather than
guessed — ~1.00 means daily sigma, ~0.063 means already annualised. Candidates
are ranked by dispersion alone, never by closeness to an expected answer, so the
search cannot find what it is looking for. `HISTORICAL_VOLATILITY` involves no
options, so whatever it settles at is a property of the encoding.

Verified offline in `--selftest`: the search recovers a planted 21-session
`std_ddof1` at √252 and a planted 30-session `rms_zero_mean` at 1.0, both to
dispersion 0.00e+00, and reports 74% dispersion on an unrelated series.

### And it crashed on the first live run

```
TypeError: unsupported format string passed to method.__format__
```

The grid column was named `shift`. **`shift` is a pandas Series method**, so
`row.shift` returned the bound method rather than the value, and formatting it
raised. `median` and `corr` were the same trap — `median` survived only because
I happened to use bracket access there.

The fix is the rename (`lag`, `ratio`, `correl`), not a reminder to use brackets.
Two selftests now enforce it: one asserts no grid column name collides with a
`pd.Series` attribute, the other formats every column through attribute access —
the exact operation that crashed. Both were confirmed to fail against the old
names before being kept. 10/10.

## Calibration ran. The estimator search FAILED; the units are identified anyway.

```
 window       estimator  lag  dates  median ratio  IQR/median    corr
     45   rms_zero_mean    0  1,207        1.0157      13.76%  0.9300
     45       std_ddof1    0  1,207        1.0164      13.84%  0.9273
     45       std_ddof0    0  1,207        1.0050      13.84%  0.9273
     30   rms_zero_mean    0  1,222        1.0335      13.99%  0.9606
     30       std_ddof1    0  1,222        1.0351      15.09%  0.9596
```

**Best dispersion 13.76% against a 2% bar. That is a failure and it is reported
as one — IBKR's exact estimator is not in the grid.** Its window is somewhere
near 30–45 sessions and is probably calendar-based, which no session count
reproduces exactly. Correlation 0.93–0.96 confirms both series are measuring the
same thing; they just use different windows, and two windows 15 sessions apart
genuinely disagree 10–15% day to day.

**But the units question is a different question, and I set the gate on the
wrong one.**

| | |
|---|---|
| identifying the **estimator** | needs a tight ratio — 2% is the right bar, and it failed |
| identifying the **units** | asks only whether the ratio is near **1.0** or near **0.063** |

Those two hypotheses are a **factor of 16** apart. Across all ten best
estimators the ratio spans **1.0041 to 1.0351** — every one on daily sigma,
**16× clear of the alternative**. Window noise of a few percent cannot move a
band from 1.0 to 0.063. **The units survive never identifying the estimator at
all.**

So: `OPTION_IMPLIED_VOLATILITY` and `HISTORICAL_VOLATILITY` are **daily sigma**,
and annualising needs **√252 = 15.8745**. Corroborated independently — SOXL's
raw IV bars run 0.0645–0.0748 in late August, which annualise to 102%–119%,
squarely where SOXL's implied vol actually sits.

**This is not self-validating and is not meant to be.** The arbiter is the Part B
control against V37's vendor option files, a completely independent source. If
SOXL's 1-month edge lands within 3 points of +10.9 the scale is confirmed. If it
does not, the scale is wrong and Part B stays unreported.

Three selftests now guard the units logic: it must read the real observed band
as daily, flip correctly for an annualised band, and **refuse an ambiguous one**
— so it cannot say yes to everything. 13/13 pass.

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
