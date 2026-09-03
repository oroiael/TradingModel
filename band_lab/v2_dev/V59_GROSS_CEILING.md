# V59 — The 1-minute data stands as is, without spreads. Recorded as a decision.

    python3 band_lab/v2_dev/v59_gross_ceiling.py

## The decision

**The SOXL 1-minute file is taken at face value, with no spread charged.** The
gross surface is treated as a *ceiling* on what the equity strategy could ever
have earned, not as a result.

This is written down because it is an assumption, and the alternative to writing
it down is not "no assumption" — it is the same assumption, unstated. Every
equity cost figure in this project so far (the half-cent per side, the one-cent
tick) was an estimate nobody measured, because **there is nothing in the data to
measure it against.**

## Why it cannot be measured from what we hold

`SOXL_1min.csv` is:

    Date,Open,High,Low,Close,Volume
    20191231 09:30:00 America/New_York,17.94,17.96,17.9,17.92,170640.0

Trade prices and size. **No bid, no ask, no quote sizes, no NBBO.** 642,510 bars
and not one of them says what it would have cost to cross. The spread is not
understated or overstated in this file; it is absent.

This is the opposite of the option side, and the two have been easy to confuse.
See half 2.

## The ceiling

The fine grid's `ev` column already is this number — it charges nothing at all.
900 barrier pairs, 44,307 candidate entries each.

| | |
|---|---|
| cells with a positive gross edge | **579 of 900** (64%) |
| best gross EV per trade | **+0.0450%** = **1.27 ticks** |
| — where | up 3.0% / down 1.7%, 3.6 SE, 31% of starts unresolved |
| median gross EV per trade | +0.0098% = 0.28 ticks |
| gross edge larger than one tick | 55 of 900 |
| gross edge larger than half a tick | 313 of 900 |

So the honest headline is: **with transaction costs set to zero, the best
barrier pair on a 900-cell grid earns 1.27 cents a trade.** That is the ceiling.
Nothing this strategy does on this data can beat it.

## Two reasons the ceiling is not a result

**1. It is drift, not a harvest.** Rank correlation of gross EV with the
**up**-barrier width is **+0.937**; with the down-barrier, −0.175. SOXL rose 540%
across the sample. A wider up-barrier is simply a longer hold on an asset that
went up, so a gross surface that tracks the up-barrier that tightly is measuring
the rise. The best cell — up 3.0% / down 1.7%, the widest up-barrier on the grid
with 31% of its starts never resolving — is the corner where that effect is
strongest, which is exactly where a drift artifact should sit.

**2. Removing the spread removes the smaller of the two problems.** V26 ran six
fill conventions on this strategy with costs held constant and spanned
**+122.57 to −126.94 bp/day** — a 250 bp band, the range of what could have
happened inside a minute that 1-minute bars cannot see. The edge being sought is
about 3 bp/day. Setting the spread to zero removes a ~3.6 bp-per-trade cost and
leaves a **±125 bp/day ambiguity roughly 80× the signal.** The resolution
problem was never the spread; it is the bar.

## What "gross" does not mean

Gross is not free. It means one named cost is set to zero. Still live and still
assumptions: commissions, the fill convention (which minute, which price within
it), and the marking of unresolved starts at the 15:55 close. V58 is the
companion piece on the option side — the fill convention alone was worth 4.6
points of joint P&L there.

## Half 2 — the option side is unaffected, because its spread is real

The `SOXL_Options_YYYY.csv` files carry `bid`, `ask`, `bid_size`, `ask_size`,
`bid_exchange`, `ask_exchange`, `bid_condition` and `ask_condition`. Those are
quotes, not estimates, so **V54, V56, V57 and V58 are charged a measured spread
and none of them rests on the decision above.**

V52 established what those columns are: each row joins a *trade* record
(`open, high, low, close, volume, count, timestamp`) to an **end-of-day quote**
(`bid, ask, bid_size, ask_size`). The `timestamp` is a last-trade time and
belongs to the trade half of the row, not to the quote — reading it as a quote
time is what produced two retracted alarms, and it should not produce a third.

New measurement — the end-of-day quoted straddle spread the option backtests
actually pay, on V32's own 35–39 DTE ATM selection rule:

| year | n | mean | median | p90 | mean $ | mean spot |
|---|---|---|---|---|---|---|
| 2022 | 250 | 5.6% | 4.8% | 8.1% | 0.39 | 23.12 |
| 2023 | 249 | 4.2% | 3.4% | 6.4% | 0.17 | 19.61 |
| 2024 | 251 | 13.9% | 8.8% | 31.8% | 1.25 | 39.41 |
| 2025 | 248 | 19.0% | 12.2% | 42.6% | 1.36 | 27.95 |
| 2026 | 122 | 19.2% | 15.7% | 38.0% | 5.65 | 114.12 |
| **ALL** | **1,120** | **11.6%** | **5.9%** | **28.4%** | **1.32** | **36.97** |

**The spread varies by a factor of four across regimes** — 4.2% in 2023 against
19.2% in 2026. That is the finding worth keeping: any single flat spread
assumption is wrong in both directions depending on the year, which is precisely
why V58's ladder is parameterised rather than pinned.

### On V32's live measurement

V32 measured 14.6% of mid (17.8 vol points) from live IBKR `BID_ASK` ticks over
9 sessions in August 2026, and concluded the vendor end-of-day figure understated
it. Two limits on how far that carries, stated plainly:

- **The samples do not overlap in time.** The option files end 2026-07-02; the
  ticks start 2026-08-17. There is no date on which both exist.
- **14.6% sits inside the file's own year-to-year range** (4.2%–19.2%), and
  above the file's 2026 figure by less than the gap between the file's 2023 and
  2024. So the live sample is consistent with the file being right and August
  2026 being a wide-spread month — V32 itself notes its 9 sessions were a period
  of 110–125% implied vol.

The raw tick file is not in this repository, so the 17.8 figure could not be
re-verified here; it is carried on V32's authority, with the caveat above.

## What would change any of this

For the equity side, one thing and only one: **NBBO or bid/ask bars for SOXL
shares across 2019–2026.** Nothing else substitutes. IBKR can serve recent
months through `reqHistoricalTicks(whatToShow="BID_ASK")` — the mechanism
`option_spread_probe.py` already uses, and it needs TWS, so it runs on the
trading machine and not in this container. The full window needs a quote vendor.

Until then the ceiling stands as the ceiling, and it is 1.27 ticks.
