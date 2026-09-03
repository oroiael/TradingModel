# V63 — What can be said about FAS before the chains arrive. Not a result.

V62 established the four tests cannot run on FAS: they are option tests and no
FAS option chains exist. This records what *is* measurable tonight, and is
explicit that none of it is a backtest.

**V31 is the standing proof in this repository that a screen can be wrong by
more than its own answer** — it said +3.7 volatility points and the backtest
returned −2.94%/cycle. Everything below is a screen. It is a reason to expect
something, which is exactly what a backtest exists to check.

## What could not be measured, and why it is not worked around

The FAS option spread. Attempted 2026-09-02 23:42 ET, after the close:

    FAS  bid-ask {}   volume 0   last.is_close true
    SOXL bid-ask {}   volume 56,134

Both quotes come back **empty**. `top_status` reads REALTIME, which is why it
cannot be relied on alone — there is no two-sided quote behind it. V32 built a
"bid size 1" alarm on a frozen weekend quote and had to retract it; that mistake
is not repeated here. **The FAS option spread is unmeasured, and the four tests
are spread-dominated, so the most decision-relevant number is the one missing.**

It needs a session during regular trading hours.

## What was measured: realised volatility, from the bars

Computed from `FAS_5min_6Years.csv` and `SOXL_1min.csv` over their common
window, 2020-07-23 → 2026-07-22, 1,506 sessions. No options, no vendor, no API.

| | FAS | SOXL | SOXL/FAS |
|---|---|---|---|
| annualised realised vol | **56.4%** | **111.0%** | **1.97×** |
| total return | +378% | +1,059% | |
| worst single day | −24.8% | −36.7% | |
| max drawdown | −67.7% | −90.5% | |

Trailing 30-session realised at each year end:

| | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| FAS | 51.9% | 65.6% | 49.3% | 29.0% | 42.9% | 34.9% | 39.7% |
| SOXL | 52.8% | 100.6% | 104.1% | 65.0% | 81.0% | 101.9% | 206.1% |

**FAS is a materially calmer instrument than SOXL** — about half the volatility,
a third less drawdown — despite both being 3× funds. The leverage is the same;
the underlying sector is not.

## One live implied-vol snapshot, with the control that makes it readable

Taken the same moment, from IBKR's `implied_vol_underlying` and `historical_vol`.

**The control first.** V47 found IBKR's raw volatility series wrong by a factor
of 16 for SOXL, so the SOXL reading is checked against this project's own
independent measurements before the FAS reading is given any weight:

| | IBKR tonight | this project, independently |
|---|---|---|
| SOXL implied | **104.6%** | **106.07%** at 30d, V49, live quotes 2026-09-02 |

Agreement to 1.5 points on an unrelated path through the API. The field is
sound here — the V47 failure was reading a *daily* sigma as annual, and this
tool returns `daily_iv` and `annual_iv` separately, so the ambiguity is gone.

| tonight | implied | realised (30d) | implied − realised |
|---|---|---|---|
| SOXL | 104.6% | 150.2% | **−45.6** |
| FAS | 41.9% | 34.3% | **+7.6** |

## The finding that reverses if you pick the other reference

Read against trailing-30-day realised, FAS's variance risk premium is **positive
+7.6**, where SOXL's is deeply negative. That would be the first positive
short-vol signal in this entire sequence, and it is the reason this note exists.

**It does not survive the longer window.** FAS's implied 41.9% sits against a
six-year realised of **56.4%**, not 34.3%:

| FAS implied 41.9% vs | | VRP |
|---|---|---|
| trailing 30-day realised 34.3% | a currently calm month | **+7.6** |
| **six-year realised 56.4%** | the sample a backtest would use | **−14.5** |

The positive number is an artifact of comparing a forward-looking IV to an
unusually quiet trailing month. On the horizon a backtest would actually run,
**FAS shows the same negative-VRP configuration that killed short vol on SOXL** —
V27 measured SOXL implied 98.6% against realised 110–116%, and −14.5 is the same
sign and a comparable size.

I have one IV observation for FAS and no history, so this cannot be resolved
further without the chains. Both readings are reported rather than the
convenient one.

## What this predicts for the four tests, and why it is still worth running them

Two independent reasons to expect FAS to fail at least as badly as SOXL:

1. **Lower volatility means less premium against the same frictions.** FAS's IV
   is roughly 40% of SOXL's. Premium scales with σ√T, so there is proportionally
   less of it for a spread to eat through.
2. **FAS is the thinner book.** `fas_lab` already charges FAS 3 bp against
   SOXL's 2 bp on the *equity* side for this reason. There is no reason its
   option quotes would be tighter, and every reason they would be wider.

Both push the same way. Set against that, one reason to run them anyway: the
whole point of V53→V54 was that a screen had been wrong before, and the sign of
the FAS VRP genuinely depends on a window choice that only a backtest settles.

**Recommended order when the chains land, which is not the order these were
built in.** Run `option_fill_ladder.py --symbol FAS` **first**, not last. V58
established the fill convention is worth 4.6 points of joint P&L on SOXL and is
the assumption that dominates all four tests. If FAS's ladder shows the spread
consuming the premium at the published rung, the other three are decided before
they are run, and that is worth knowing in one run rather than four.

## Status

| test | on FAS |
|---|---|
| V53/V54 short vol | blocked — no chains |
| V55/V56 credit spreads | blocked — no chains |
| V57/V58 long vol + fill ladder | blocked — no chains |
| V60/V61 PMCC | blocked — no chains |
| option spread | unmeasured — needs a session during market hours |
| realised vol | **measured, above** |
| implied vol | one snapshot, control passed, no history |

`fetch_option_chains.py --symbol FAS --years 2022 2023 2024 2025 2026`, run where
the Theta Terminal lives, unblocks all four.
