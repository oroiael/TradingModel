# V51 — What the screen assumes, and what actually needs backtesting

Eleven structures have been retired in this sequence on a volatility-point
screen: edge minus spread, and if it is negative the structure is dead. That
screen has assumptions in it, and this states them before proposing what to run.

## The screen's assumptions, worst first

**1. P&L is linear in volatility points. It is not.**
A short option's P&L is `0.5·Γ·S²·(IV² − RV²)·dt` integrated along the path, not
a difference of endpoints. V29 said so when it wrote the catalogue. **V31 then
measured the gap: the screen said +3.7 points and the backtest returned
−2.94%/cycle.** The screen was optimistic by more than its own answer. Nothing
establishes the error has the same sign for short vol, which is the whole point.

**2. You cross the full spread, every time.**
V32 measured the spread *width* from 9,066 live ticks and found 20.4 volatility
points at 09:30, worse than at the close. It did **not** measure whether a limit
resting inside that band fills. V22 flagged the same hole: *"an order priced
inside the spread may never fill, and nothing here models the unfilled case."*
Every rung between "cross the spread" and "earn the spread" is unmeasured.

**3. One median spread applies to every trade.**
Spreads vary by tenor (V48: 20.1 at 30d against 9.6 at 79d), by moneyness (V49:
the call wing widens with tenor while the put wing halves), and by regime.

**4. Positions are held to expiry with no management.**
Real short-vol books take profit near 50% of max and roll at ~21 DTE. That
changes the edge-to-spread ratio structurally, and in both directions: closing
early collects less edge for the same spread, while holding to expiry pays no
closing spread at all.

**5. Entry is unconditional.**
No IV-rank or regime gate anywhere, though implied vol predicts next-day
realised range at R² 0.25 against 0.001 for direction.

**6. A mean is a verdict.**
Short vol is many small wins and rare large losses. A mean-based screen says
nothing about the tail, the path, or the drawdown that decides whether a
positive-expectancy book is survivable.

## The data, and a defect that governs everything

Five years of quotes exist — `SOXL_Options_2022..2026.csv`, ~570 MB — not the
one year used so far. One snapshot per contract per day (mean 1.00, max 1), so
nothing intraday is testable.

**But the underlying price does not match the quote**, and the shape of the
mismatch is worse than a simple lag. Corrected audit of both files:

| | 2023 yearly | 1-year greeks |
|---|---|---|
| quote stamped `00:00:00` — a placeholder, no trade | **43.0%** | **37.7%** |
| quote stamped with a real time | 57.0% | 62.3% |
| of those, median time of day | 15:08 | 14:59 |
| `underlying_timestamp`, distinct values per day | 1 (17:16) | 1 (17:15) |
| real-stamped rows more than 60 min from the underlying | **100%** | **100%** |
| more than 240 min | 27.1% | 29.7% |

Median lag is about **two hours**, not six — an earlier draft of this file said
six, having let the midnight placeholders drag the median down and read them as
pre-market quotes. They are not quotes at all. **Roughly 40% of rows carry no
usable timestamp**, which is the harder problem: a mismatch can be repaired, a
missing stamp cannot.

Both files share this structure, so the 1-year greeks file is not the clean
end-of-day snapshot its name suggests.

`option_data.py` validates `underlying_price` against the *daily* price file, so
it confirms the value is a correct EOD close — it does not detect that the quote
beside it is from the middle of the day. `bs.py`'s own docstring names the
consequence: *"If the vendor's delta is computed against a spot price from a
different moment than its bid/ask, the hedge is wrong every single day and the
study measures nothing."*

Whether the vendor computed its greeks against the contemporaneous spot and
merely *reports* the EOD one is **unknown and testable**: recompute IV both ways
and see which reproduces the vendor's column.

## Priority

### P0 — before any backtest
**1. Repair the underlying join.** Re-match every option quote to SOXL's
1-minute price at its own timestamp, then determine which spot the vendor's IV
and delta actually used. Cheap, and every number downstream depends on it.

### P1 — never backtested, and the screen is least reliable here
**2. Short straddle and short strangle, held to expiry, with and without
management.** The largest gap in the whole project: long vol was backtested five
times (V31, V34, V36, V38, V42) and **short vol has never been backtested once.**
Its payoff shape is exactly where a mean-based screen fails.

**3. Put credit spread and broken-wing butterfly.** The screen penalised these
on leg count alone. A backtest prices whether the truncated tail pays for the
extra legs.

### P2 — screened negative, with a specific reason to distrust the screen
**4. Risk reversal at 79 days.** V49 put it at exactly 0.0. A screen cannot
resolve a sign at zero; the path decides it.

**5. The fill ladder, applied to options.** V26 ran six fill conventions on the
equity strategy and spanned +122.57 to −14.46 bp/day. Nobody has run it on an
option structure. Not a strategy — the sensitivity that says which rung each
structure dies at, and whether any survives short of earning the spread.

### P3 — after the above
**6. IV-rank conditioned short vol.** Meaningless until #2 exists.
**7. Calendar across regimes.** V49 showed its sign flips with the term
structure; only a multi-year run says which regime dominates.

### Not testable with this data
Anything intraday (one snapshot per contract per day). Liquidity provision
(needs quote-level data and a fill model that does not exist here).

## The honest expectation

The screen has been wrong once, and it was wrong in the optimistic direction.
That is a reason to backtest, not a reason to expect a different answer.
