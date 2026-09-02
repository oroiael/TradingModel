# V52 — P0: which spot the greeks used. There is no defect.

V51 raised an alarm: the option files carry an `underlying_price` that is a
single end-of-day value per date, sitting beside quote timestamps scattered
across the session, and concluded every implied vol and delta might be computed
against a spot from the wrong moment. **The alarm was wrong**, and this records
why, because the reasoning that produced it was superficially sound.

## Gates, written before the run

| | condition | meaning |
|---|---|---|
| G1 | EOD spot reproduces vendor IV within 1.0 vol pt | vendor used EOD |
| G2 | contemporaneous spot reproduces it instead | vendor used the live spot |
| G3 | neither | stop, something else is wrong |
| G4 | parity residual shrinks under whichever G1/G2 picks | confirms the join |

## Result — SOXL 2023, 31,408 usable quotes, 250 dates

The minute-bar join matched 100% of quotes. Median drift between the spot at
the stamped time and the reported EOD spot is 0.000% with a mean absolute of
0.692%, so the two are genuinely different numbers and the test has power.

| hypothesis | median abs error vs vendor `implied_vol` | within 1.0 pt |
|---|---|---|
| **EOD — the vendor's own column** | **0.167 vol pts** | **95.4%** |
| LIVE — spot at the stamped time | 1.666 vol pts | 36.2% |

**G1 PASS, G2 fail.** G4 agrees independently: put-call parity residuals are
$0.0330 under EOD against $0.0797 under LIVE, and EOD still wins on the 3,415
pairs whose legs are stamped within five minutes of each other ($0.0251 against
$0.0305).

## Why the alarm was wrong

`timestamp` is the **last-trade** time, not the quote time. The separation is
total:

| | rows | volume = 0 | count = 0 | close = 0 |
|---|---|---|---|---|
| stamped `00:00:00` | 100,630 | **100.0%** | 100.0% | 100.0% |
| stamped with a real time | 133,196 | **0.0%** | 0.0% | 0.0% |

Every midnight stamp is a contract that did not trade that day. Every real stamp
is one that did. And 84.7% of the zero-volume rows still carry a live bid, so
the quote exists independently of whether anything traded against it.

The row is two things joined: a **trade** record (`open, high, low, close,
volume, count, timestamp`) and an **end-of-day quote** (`bid, ask, bid_size,
ask_size`) with greeks computed against the end-of-day spot. Reading the trade
timestamp as the quote timestamp is what produced the alarm.

## What this changes

Nothing needs repairing. The five yearly files are usable in full — **not
restricted to the 57-62% that carry a real timestamp**, because the untraded
rows still carry valid quotes. V49 and V50's use of this data stands.

`option_data.py`'s existing check — that `underlying_price` matches the daily
price file — was already the right check for the data's actual shape.

## What it does not establish

One year tested. The 2022, 2024, 2025 and 2026 files are assumed to share the
structure and have not been audited. The greeks are internally consistent with
an end-of-day quote; that is a different claim from their being *correct*, and
`bs.py`'s agreement check is the tool for the latter.
