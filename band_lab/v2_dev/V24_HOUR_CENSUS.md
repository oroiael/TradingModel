# V24 — Time-of-day census: buy the top of the hour, sell the 59th minute

Question, as asked: trading on a **time** basis rather than a percentage basis —
for each trading hour of each weekday, what is the average positive movement and
the average negative movement, entering at the first minute of the hour and
exiting at the 59th?

    python3 band_lab/v2_dev/hour_census.py
    python3 band_lab/v2_dev/hour_census.py --cc          # skip the first minute
    python3 band_lab/v2_dev/hour_census.py --drill Mon,9

No band, no gate, no anchor, no stop, no target, no fill model. Nothing from the
strategy is imported. The only decision is a clock.

## What was measured

| | |
|---|---|
| data | `SOXL_1min.csv`, `SOXS_1min.csv`, regular hours only |
| window | 2019-12-31 → 2026-07-30, 1,653 sessions, 11,535 hour-slots per symbol |
| entry | **open** of the `:00` bar |
| exit | **close** of the `:59` bar |
| return | `exit_close / entry_open − 1` |
| avg positive | mean of the hours that ended positive |
| avg negative | mean of the hours that ended negative |
| MFE / MAE | average best and worst reached *during* the hour, from bar highs/lows |
| friction | 6.70 bp SOXL, 8.18 bp SOXS per round trip, measured (`research_kit`) |

The 09:00 hour is **09:30–09:59** — a 30-minute hold, not 60. It is flagged with
`*` everywhere and never pooled with the full hours.

## Result

**Not one cell out of 35 survives correction for having looked at 35 cells.**
One cell per symbol has a raw p below 0.05; 1.75 are expected by chance. Zero
survive Benjamini-Hochberg.

The average full hour is worth **+1.0 bp gross on SOXL** and **−2.4 bp on SOXS**,
against friction of 6.70 and 8.18 bp. Trading every hour of every day is
−34.2 bp/day on SOXL and −63.4 bp/day on SOXS. Annualised, that is total loss.

Two effects are large enough to describe:

| | SOXL | SOXS | implied SOX |
|---|---|---|---|
| Monday 09:30–09:59 | **+44.1 bp** (t 2.76) | **−41.5 bp** (t −2.61) | +14.3 bp |
| 11:00–11:59, all days | +8.2 bp (t 1.76) | −10.9 bp (t −2.35) | +4.5 bp |

Every other cell is inside noise.

## Monday morning, taken apart

| check | result |
|---|---|
| split-half | +45.5 bp first half, +42.7 bp second — stable |
| by year | positive in 5 of 7 calendar years; **−4.9 bp in 2022, −41.9 bp in 2026 YTD** |
| outliers | median +38.3, symmetric 5% trim +45.5 — not carried by a few days |
| first minute | +44.1 open→close vs **+31.3 close→close**: 29% of it is the opening print |
| cross-symbol | SOXS shows −41.5 bp, correlation of all 35 cells −0.985, 32/35 opposite signs |
| spread ×2 | net +31.7 bp; ×3 → +26.0; ×5 → +14.6; ×10 → −14.0 |

The measured spread comes from live fills between 11:00 and 15:55. **The opening
minute is not that**, and nobody here has measured it. The sensitivity row set
above is a range, not a measurement.

## What this does not license

Monday 09:30 is the best of 35 cells, chosen after seeing all 35. Its number is
an upper bound on an honest out-of-sample version, not an estimate of it. It
compounds to +244% gross against SOXL's −22.4% over the same window — a figure
whose only honest use is as a ceiling.

The two negative years are the specific problem: 2022 (the bear) and 2026 (now).
A calendar effect that stops working in the regime you are currently trading is
not a calendar effect you can trade.

Correlation −0.985 between SOXL and SOXS across the 35 cells proves the pattern
is in the semiconductor index rather than in one CSV. It is **one** piece of
evidence counted once, not two — the two funds are the same bet inverted.

The t-statistics assume the hours are independent. They are not. Treat them as a
screen, not as a p-value anyone would publish.

## Relation to the band strategy

None of this rescues the band. The band's problem is that the dip carries no
information (48.3% vs a 48.5% baseline) and the raw per-bet expectancy is
negative. A time-of-day tilt does not change either. What this census does say is
that if there is anything at all in this instrument at this granularity, it is a
**Monday-morning drift**, not a mean-reversion band — and it is worth roughly
14 bp on the underlying, before the hardest fill of the day.
