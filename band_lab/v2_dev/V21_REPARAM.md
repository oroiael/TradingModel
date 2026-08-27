# V21 — Were the strategy's parameters chosen by the bug?

**Status: BAR PRESPECIFIED, WRITTEN AND COMMITTED BEFORE THE RUN.**

Run: `python3 band_lab/v2_dev/reparam.py --run` then `--verify`

---

## The question

Every parameter in the strategy — the 1% dip, the 1% target, the 4% stop, the
11:00 start, the five-fill cap, the 6% volatility gate — was picked by an
earlier study (V1–V12) that scored candidates on a simulator which let a sell
and a re-buy happen inside the same minute, pricing the re-buy at that minute's
opening price. That bug was 66% of SOXL's measured profit and 106% of SOXS's.

So the parameters were not merely *measured* wrong. They may have been
*selected* wrong: 1% might have won its contest because 1% targets get re-bought
in the same minute more often, not because 1% is a good target.

This re-scores each parameter on the corrected simulator and asks whether the
incumbent choice survives.

## This is a diagnostic, not an optimisation

**P5 (stated first, because it is the rule most likely to be broken later): no
parameter is changed on the basis of this run.** Picking the winner of a sweep
on the only data we have is precisely what produced the current configuration.
Adopting a new value would need out-of-sample data, and there is none left.

What this run can legitimately conclude is whether the incumbent was an artifact
of the bug. That is a statement about the past, not a licence to retune.

## How each parameter is read — fixed before the numbers exist

**P1 — unrefuted.** If the incumbent is within one standard error of the best
value on the corrected simulator, the original choice survives. The bug did not
drive it.

**P2 — artifact.** If some other value beats the incumbent by more than two
standard errors *and* does so in at least 4 of 5 years *in both sleeves*, the
incumbent was chosen by the bug. Report it. Do not adopt it (P5).

**P3 — the parameter never mattered.** If the spread from best to worst across
the swept range is under one standard error, the parameter carries no
information and any earlier claim that it was "optimised" was noise all along.
This is the most likely outcome for most of them and it is not a failure.

**P4 — overfitting signature.** If the curve is spiky — a value beating both its
immediate neighbours by more than one standard error — treat the whole
parameter as unreliable regardless of which value wins. A real effect is smooth
in its parameter; a spike is the sample memorising itself.

**P6 — multiple testing, counted.** The run tests 33 configurations. At a 5%
threshold roughly 1.7 of them are expected to look significant by chance alone.
The count of "wins" must be compared against that number, printed in the output,
before any of them is believed.

**P7 — sleeve disagreement is evidence against.** SOXL and SOXS run identical
logic on inverse instruments. A parameter that helps one and hurts the other is
not describing a market mechanism. Per the V1/V16 precedent this closes the
question rather than licensing a per-sleeve value.

**P8 — the output must be checkable without trusting me.** Every configuration
writes its complete trade list. `--verify` recomputes every summary number from
those trade files and fails loudly on any mismatch. A summary that cannot be
rebuilt from the raw trades is not a result.

## What is held fixed

The corrected simulator, unchanged from `backtest_as_executed.py`: the re-buy
waits one full minute, whole shares, real tick sizes, sizing off the limit, the
15:55 exit priced at the next bar's open, and a touched stop priced as a market
order rather than filling at the stop level for free.

Cost stays at 1.167 bp per fill for SOXL and 2.857 for SOXS. This is the one
input verified against reality: the IBKR statement for 2026-08-03 to 08-25 shows
$599.36 of commissions, which works out to 1.16 bp per side.

---

# RESULTS

*(appended after the run)*
