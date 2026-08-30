# V26 — Enforce a fill convention that cannot flatter itself

Proposal tested: never let a fill take the good side of a minute. Buy at the
minute's open, or worst case its high. Sell at the minute's low. Re-buy no
earlier than the next minute.

    python3 band_lab/v2_dev/fill_ladder.py
    python3 band_lab/v2_dev/fill_ladder.py --live-cfg --slip 3

## The result — net bp per active day, after costs, 1-minute fills, 2022+

Left column is the plain simulator; right column adds the engine's real
constraints (whole shares, tick rounding, size off the limit, 15:55 flatten).

| convention | account | with live constraints | band |
|---|---|---|---|
| **A  CEILING** — buy the bar's low, sell its high | +122.57 | +114.14 | 100% |
| B  published backtest (same-minute re-buy at the open) | **+29.12** | **+29.84** | 63% |
| C  no same-minute re-buy — *the V20 correction* | +3.28 | +6.16 | 52% |
| D  + stop fills at the bar's LOW | **−1.99** | **+1.55** | 50% |
| E  + must trade THROUGH the price, not just touch it | −2.17 | −4.01 | 49% |
| F  + 2 bp extra slippage on every fill | **−14.46** | **−14.90** | 45% |
| **G  FLOOR** — buy the bar's high, sell its low | −126.94 | −116.89 | 0% |
| X  force the fill AT the limit — **impossible, see below** | −321.75 | −300.46 | −78% |

`band` = where the row sits between the floor and the ceiling.

## Three things this establishes

**1. The correction was not finished.** C still assumed a stop fills at
`min(open, stop)` — that the stop price is honoured. A SELL STOP is a market
order once touched and can fill below it; the bar's low is the honest worst
case. Applying that (row D) moves the account from +3.28 to −1.99. The truth
for stops is between C and D, so the strategy's edge **straddles zero on the
stop convention alone**.

**2. Two bp of unmodelled slippage is decisive.** Row F is −14.46 bp/day at
t = −3.25. Not "inside noise" — significantly negative.

**3. The band is 250 bp/day wide.** That is the range of what could have
happened inside a minute that 1-minute bars cannot see. The question being
asked — is there a 3 bp/day edge — is two orders of magnitude smaller than the
resolution of the data being used to ask it. No amount of care with 1-minute
bars settles this. It needs tick data or live fills, and live fills are what the
paper account has been collecting.

The published backtest sat at **63% of the band**. A neutral convention lands at
50%. It was systematically taking the good side of every minute, not by a huge
margin per fill, but 6.5 times a day for four and a half years.

## The part of the proposal that cannot be done — row X

A resting BUY LIMIT at 100 in a market trading at 97.50 fills at **97.50**. It
cannot fill at 100.

Measured on this data: **64% of entry fills happen on a bar that opened BELOW
the resting limit, by a median of 2.5%** (1,354 of 2,109 SOXL entries; worst
−15.0%; 390 opened more than 4% below). Those are gaps down through a resting
order. Taking the open there is not optimism — it is the only thing that can
happen.

So "always assume the worst price in the minute" is right for a stop and wrong
for a limit. Row X applies it anyway: it buys 2.5% above the market, which puts
the position instantly through its own −4% stop, and lands at −321 bp/day —
**below the floor**, which is how you can tell a rule is not conservative but
simply wrong. It is kept in the table as a correction on the record.

The same logic mirrored: a SELL LIMIT target cannot fill below its limit, so
"sell at the bar's low" is not available to the target either. It *is* available
to the stop, and that is exactly row D.

`min(limit, open)` for the entry and `max(open, target)` for the target were
already correct. The bug was never the price rule in isolation — it was using
the bar's open for a purchase that happened *after* the bar's open, which is
what V25 covers.

## Where honest pessimism actually lives

| place | why a fill can be worse than the order | row |
|---|---|---|
| stop | market order once touched; a gap hands you the low | D |
| queue | being at a price is not being filled at it | E |
| everything else | spread capture, partial fills, order routing | F |

E is worth almost nothing on its own (−2.17 vs −1.99). D and F are worth a lot.
