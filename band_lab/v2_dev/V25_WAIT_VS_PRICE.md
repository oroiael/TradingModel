# V25 — It was never the waiting. It was the price.

## The claim being tested

I have said, more than once, that the band strategy collapsed because the
re-buy had to wait a minute. **That framing is wrong**, and this test is what
shows it. Waiting a minute is not what removed the edge. Removing a re-buy price
that had already traded is what removed the edge — and it removes it whether you
wait or not.

    python3 band_lab/v2_dev/wait_sweep.py
    python3 band_lab/v2_dev/same_minute_examples.py SOXL

## The two fixes, which are not the same fix

The published backtest sold and re-bought inside one minute, pricing the re-buy
at that minute's **open**. When the sell was a target hit — near the top of the
minute — the open had already traded, before the sell.

- **Fix A: make it wait.** No re-buy until the next 1-minute bar, or later.
- **Fix B: let it re-buy in the same minute, at an honest price.**
  `price = min(limit, max(open, sell price))`. Zero waiting. Just no time machine.

## Result — net bp per active day, after costs, 1-minute fills, 2022+

| case | SOXL | SOXS | account | t |
|---|---|---|---|---|
| published: same minute, priced at the bar's OPEN | +39.34 | +30.29 | **+29.12** | 6.35 |
| **same minute, but never better than the sell price** | +8.95 | −10.64 | **−0.78** | −0.18 |
| wait 1 minute | +13.65 | −5.64 | +3.28 | 0.76 |
| wait 2 minutes | +16.09 | −1.28 | +6.14 | 1.41 |
| wait 3 minutes | +18.38 | −2.67 | +6.50 | 1.48 |
| wait 5 minutes | +22.22 | −1.53 | +8.57 | 1.92 |
| wait 10 minutes | +15.36 | −7.65 | +3.14 | 0.71 |
| wait 30 minutes | +11.60 | −9.97 | +0.60 | 0.13 |

Row 2 introduces **no delay whatsoever** and the edge is gone: +29.12 → −0.78.

Waiting is, if anything, mildly *better* than not waiting. Waiting **two** minutes
beats waiting one. Waiting **five** beats waiting two. Waiting thirty still beats
the honest same-minute case. None of it is significant — every t from 0.13 to
1.92, across eight variants — but the direction is unambiguous and it is the
opposite of "the value evaporates in sixty seconds."

## Where the +29 bp came from, in one line of arithmetic

| | SOXL | SOXS |
|---|---|---|
| same-minute re-buys after a target sell | 813 over 679 days | 860 over 691 days |
| per active day | 1.20 | 1.24 |
| the open was below the sell price | 770 of 813 (95%) | 802 of 860 (93%) |
| mean discount taken | 0.265% | 0.294% |
| **phantom return per day** | **31.8 bp** | **36.5 bp** |
| published gross return per day | 43.0 bp | 39.8 bp |

74% of SOXL's published edge and 92% of SOXS's is one arithmetic error repeated
about 1.2 times a day for four and a half years.

## One real minute

SOXL, 2 July 2026, 11:09. Straight from `SOXL_1min.csv`:

    open 191.76   high 192.93   low 191.15   close 192.18

    SOLD at 192.1727  — the target, hit on the way up
    BOUGHT at 191.76  — that minute's open

191.76 traded *before* the sell at 192.1727. Once you have sold near the high of
a minute, the low of that same minute is behind you. The cheapest price still on
offer was 192.1727 — you would have bought back at what you just sold at, for
nothing. The backtest booked 0.22%.

The bar is real. The sell is real. Only the re-buy price is a time machine.

## What this does and does not change

It does not rescue the strategy — row 2 is −0.78 bp/day and every wait length is
inside noise. It changes the **story**: the strategy did not have a real edge
that a one-minute delay destroyed. It never had the edge. The number was an
artifact of pricing a purchase at a moment that had already passed.

It also means "trade faster" is not a fix worth pursuing. There is nothing at
the far end of faster execution to go and get.
