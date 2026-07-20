# SOXL Part 2 — Long / Put Side, Debit Calls, and Regime Indicators

Follow-up to the bear-call study (`README.md`). Two questions:

1. **Test the mirror structures** the first study pointed to — the *long / put side*
   (`bull_put` put-credit spread, plus `long_put`) and a *debit call structure*
   (`bull_call` debit spread, plus `long_call`).
2. **Find indicators that flag when a trade is going against us**, so we can either
   *exit and wait* or *invert the trade*.

Same data, same conventions (whole-strike, daily EOD marks, 20% fill rule,
intrinsic settlement). New engine `verticals.py` is legs-based and **reproduces
the original `backtest.py` bear-call numbers exactly** (verified — two independent
engines, identical P&L), so bear_call is a built-in control.

---

## Verdict (data only)

* **The long side works; the credit put side does not.** Being *long* SOXL's
  upside — `long_call` (12/12 configs positive, mean **+11% … +83%** per $ risked)
  and `bull_call` debit spreads (45/72 positive, best **+34%**) — has strong
  positive expectancy. The put-credit spread `bull_put` mostly bleeds (only
  **17/84** positive, best **+4.0%**), exactly mirroring the bear-call result.
* **The reason is measurable: SOXL's volatility risk premium is negative.** Mean
  implied − realized vol = **−0.084** (median −0.039). Options are, on average,
  *cheap* relative to what SOXL actually moves. Selling premium (either side)
  fights a negative VRP plus execution cost; buying premium harvests it.
* **But this is not free money, and three honest caveats dominate:**
  1. **It's a fat-tail / regime bet.** `long_call`'s +83% headline is driven by
     2023 (+125%/trade) and the **2026 melt-up (+482%/trade, confirmed real)**; the
     same structure was **−49%/trade in the 2022 bear.** Win rates are **25–45%** —
     you lose small often and win huge rarely.
  2. **"Invest 100%" is ruin, again.** A long-premium trade loses 100% of premium
     when it expires worthless, which is *the majority* of the time, so full-size
     sizing is **functionally wiped out on trade #1.** The big compounding numbers
     below require *fractional* sizing to survive the frequent total losses.
  3. **Drawdowns are enormous even when it "works":** −49% to −91%.
* **On indicators (Q2), the data overturns the intuitive playbook:**
  * A naive **trend filter is backwards** — buying calls does *better* after
    weakness (below SMA50 / low RSI: **+18–21%**) than in uptrends (**+5%**),
    because SOXL's biggest up-moves are violent rebounds *out of* downtrends.
  * **Gating on the trend hurts the winners** and **inverting on the trend hurts
    more** ($153k → $25–31k).
  * **Stops make the defined-risk spreads worse** (worst trade −100% → **−179%**).
  * The only robust, non-overfit signal is **VRP / IV level** (buy when options
    are cheap — which on SOXL is chronic). The real risk control is **position
    sizing and entering on weakness, not timing exits.**

---

## 1. Structures tested — expectancy sweep (`verticals_scoreboard.csv`, 174 configs)

`mean_ror` = mean return per $ at risk per trade (sizing-independent edge).
`frac10_end` = ending equity of $100k compounded at **risk 10%/trade**.

| structure | best config | trades | win% | **mean_ror** | frac10 end | frac10 maxDD | invest-100% |
|---|---|--:|--:|--:|--:|--:|---|
| **long_call** (debit, 1 leg) | monthly, 0.30Δ | 47 | 30% | **+83.1%** | $552k | −54% | ruin trade #1 |
| **long_call** (max compounding) | two-week, 0.30Δ | 113 | 29% | +59.7% | **$2.09M** | −74% | ruin trade #1 |
| **bull_call** (debit spread) | monthly, 0.40Δ, w5 | 47 | 34% | **+34.3%** | $206k | −57% | ruin trade #1 |
| **bull_put** (put credit) | two-week, 0.30Δ, w1 | 107 | 78% | **+4.0%** | $131k | −36% | ruin trade #1 |
| **long_put** (bearish ref) | weekly, 0.30Δ | 211 | 26% | +15.9% | $45k | — | ruin trade #2 |
| bear_call (control) | weekly, 1-OTM, w1 | 207 | 59% | −8.1% | $12k | −92% | ruin trade #2 |

Positive-expectancy counts: **long_call 12/12, bull_call 45/72, bull_put 17/84,
long_put 2/6.** The long/debit side wins broadly; the credit side is a coin-flip
at best and negative on average.

**`bull_call` is the most *robust* winner — positive in every single year:**

| year | SOXL regime | bull_call mean_ror | long_call mean_ror |
|---|---|--:|--:|
| 2022 | −87% bear | **+35%** (bear-rally months) | **−49%** |
| 2023 | +240% bull | +10% | +125% |
| 2024 | round-trip | +18% | +64% |
| 2025 | crash+recover | +74% | +8% |
| 2026 | melt-up* | +39% | +482% |

Defined risk (max loss = the debit) caps the frequent misses, so the debit spread
survives the bear that destroys the naked long call — while still capturing the
up-tail. *2026 is the melt-up regime (confirmed real by the user); see `README.md` §2.

---

## 2. Why — the volatility risk premium is negative (`signals.py`)

Averaged over 2022–2026: ATM implied vol ≈ **99%**, 20-day realized vol ≈ **107%**,
so **VRP = implied − realized ≈ −8 vol points**, negative most of the time (only
the top quartile of days is positive). On a normal underlying the VRP is positive
and selling premium pays; **on this 3× ETF it is negative** — realized movement
routinely exceeds what the options price in. That is the single structural reason
the whole family behaves as it does:

* credit spreads (bear_call, bull_put) sell underpriced vol → lose;
* long / debit structures buy underpriced vol on a fat-tailed name → win.

---

## 3. Indicators — when is the trade going against us? (`run_signals.py`)

### A. Diagnostic — mean_ror by entry-time regime (weekly)

| condition at entry | bull_call | long_call | bull_put | bear_call |
|---|--:|--:|--:|--:|
| uptrend (spot > SMA50) | +4.9% | +18.6% | −7.3% | −10.5% |
| downtrend (spot < SMA50) | **+21.2%** | **+29.8%** | −3.9% | −5.5% |
| RSI14 > 55 (extended) | −1.5% | +21.0% | −7.6% | −5.6% |
| RSI14 < 45 (oversold) | **+17.6%** | +20.4% | +1.0% | −0.8% |
| momentum(20d) > 0 | +17.9% | +36.1% | −7.0% | −14.5% |

The clean, consistent reading: **for the long side, the "warning" is being
*overbought / extended* (high RSI, well above SMA50) — that's when the long-call
trade bleeds. The best long entries are *after weakness*.** The strongest single
correlations in the data are IV / realized-vol level vs the *credit-spread*
outcome (Spearman **+0.27 … +0.30**) — high-vol entries are the ones that blow up
the short-premium trades — but they don't produce a *profitable* credit-spread
filter.

### B. "Exit and wait" — gating entries (equity of $100k, risk 10%/trade)

| structure | always | uptrend-only | **buy-weakness (RSI<50)** |
|---|--:|--:|--:|
| bull_call | $153k (DD −72%) | $63k (−68%) | $120k (**DD −67%**, 90 trades) |
| long_call | $303k (−89%) | $121k (−85%) | $62k (−65%) |
| bull_put | $30k (−70%) | $41k (−59%) | **$71k (DD −35%)** |

**Trend-gating hurts the winners.** A **buy-weakness** gate is the better idea:
it holds ~80% of bull_call's return on half the trades with lower drawdown, and it
roughly **doubles bull_put and halves its drawdown** (still a net loser, though).
"Exit and wait" only helps if "wait" means *wait for weakness to buy*, not *wait
for the trend to confirm*.

### C. "Invert the trade" — trend-following switch

| system | end equity | maxDD |
|---|--:|--:|
| bull_call always | **$153k** | −72% |
| switch: bull_call (up) / long_put (down) | $31k | −88% |
| switch: bull_call (up) / bear_call (down) | $25k | −84% |

**Inverting on the trend destroys value.** Flipping bearish when SOXL is below
trend walks straight into the rebounds that are the long side's biggest paydays.
Do not invert on a simple trend signal.

### D. Mid-trade stops on the short-premium spread (bull_put)

| rule | mean_ror | win% | **worst trade** | % stopped |
|---|--:|--:|--:|--:|
| no stop | −5.7% | 77% | −100% | 0% |
| exit when short strike breached | −6.4% | 68% | **−179%** | 28% |
| exit on SOXL −5% intra-hold | −7.8% | 51% | −132% | 47% |
| exit on SOXL −10% intra-hold | −8.1% | 66% | −179% | 29% |

**Every stop is worse than no stop**, and stops can lose *more than the defined
max loss* (−179%): closing a spread mid-life at stressed, wide bid/ask marks costs
more than letting it settle at its capped intrinsic, and you forfeit SOXL's
frequent snap-back. On a defined-risk spread, the structure *is* the stop.

---

## 4. What actually controls the risk

From the data, in priority order:

1. **Position sizing dominates everything.** Every long/debit edge here is real
   but arrives through a **25–45% win rate with fat-tailed winners**; full-size
   ("invest 100%") is ruin on trade #1, while risking a small fixed fraction turns
   the same trades into large compounding (with −50% to −90% drawdowns). Size for
   survival first.
2. **Enter the long side on weakness, not strength** (RSI < 50 / below SMA50).
   Lower drawdown, comparable return; the reverse (chasing strength) is the
   warning sign that a long trade will bleed.
3. **Prefer defined-risk debit spreads to naked long calls** if drawdown matters —
   `bull_call` is positive every year and never risks more than its debit.
4. **Do not use trend-inversion or mid-trade stops** — both destroyed value here.
5. **The only structural signal worth watching is VRP / IV level** — it is the
   thing that is actually priced wrong on SOXL, and it is wrong in the *buyer's*
   favor most of the time.

---

## 5. Honest limitations

* **In-sample, one instrument, 4.5 years, two big up-regimes.** The long-side edge
  leans on 2023 and the **2026 melt-up (confirmed real)**; treat the magnitudes as
  regime-conditional, not a stationary edge. Excluding 2026, the long side is
  still positive but far less extreme, and 2022 remains a large loss.
* **Signal thresholds are standard, not optimized** (SMA50, RSI 50, 20-day
  momentum) to avoid fitting the answer. Even so, the gating results are
  suggestive, not a validated timing model — the honest use is risk shaping, not
  a promise of alpha.
* **Daily EOD option marks only** — entries/exits and stops are priced at the
  close (no intraday option quotes exist in the data). Early assignment,
  dividends, commissions, taxes are not modeled.

---

## 6. Reproduce / verify

```bash
git lfs pull && pip install -r call_spread_lab/requirements.txt
cd call_spread_lab
python3 run_verticals.py        # structure sweep -> verticals_scoreboard.csv, vled_*.csv
python3 run_signals.py          # indicators, gating, inversion, stops -> signals_systems.png
python3 verify_verticals.py     # INDEPENDENT audit — all checks PASS
```

`verify_verticals.py` confirms: the two engines agree on bear_call to <1e-9;
sampled put-credit and call-debit trades recompute from the raw CSVs to <1e-15;
signals contain no look-ahead; and the structural claims hold (mean VRP < 0,
long_call all-positive, bull_put majority-negative).
