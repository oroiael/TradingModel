# V29 — Every way to own gamma on SOXL, with the arithmetic attached

Fourteen structures, sorted by whether the numbers we already have kill them.

Nothing here is a backtest. Each entry states what it is, how it owns gamma,
what it costs, what the edge is, and which number is missing. Where a figure is
measured it says so; where it is not, it says that instead of guessing.

## The measured inputs everything below uses

| input | value | where |
|---|---|---|
| ATM 30-day implied vol | **98.6%** mean, 95.4% median | V27 |
| realised vol, close-to-close, next 30 sessions | **110.4%** | V27 |
| realised vol, intraday 1-minute path only | **81.0%** | V27 |
| overnight share of total variance | **48%** | V27 |
| edge: total realised − implied | **+11.8 vol pts**, positive on 63% of dates | V27 |
| edge: intraday realised − implied | **−17.6 vol pts**, positive on 12% of dates | V27 |
| option round trip, ATM 22–45 DTE | **8.1 vol pts** | V28 |
| option round trip, ATM 8–21 DTE | 7.3 vol pts | V28 |
| option round trip, ATM 2–7 DTE | 9.3 vol pts | V28 |
| option round trip, ATM 0–1 DTE | **28.5 vol pts** | V28 |
| option round trip, ATM 91–365 DTE | **4.9 vol pts** | V28 |
| term structure: 2–7 DTE ATM IV | 112.8% (**+13.4** vs 30-day) | V28 |
| term structure: 91–365 DTE ATM IV | 95.4% (−3.9 vs 30-day) | V28 |
| skew: 25-delta put − 25-delta call | **+11.6 vol pts** | V28 |
| ATM quoted depth | 28 bid / 30 ask contracts | V28 |
| stock friction, round trip | 6.70 bp SOXL, 8.18 bp SOXS | IBKR statement |
| delta hedging cost | 1×/day = 8%/yr, 4×/day = 34%/yr on hedged notional | V27 |

**The one unit that makes this comparable.** Both the edge and the option spread
are expressed in volatility points, so they subtract directly. Both are
per-position quantities: a monthly roll pays its own spread and collects its own
month of edge, so the ratio holds and does not compound away.

---

# TIER 1 — the arithmetic clears, worth building a test for

### 1. Long ATM straddle, 30–45 DTE, delta-hedged once daily at the close

**How it owns gamma.** You are long two options. Hedging once a day at the close
means your P&L tracks close-to-close realised variance — including the overnight
gap, which is where 48% of the variance is.

| | vol pts |
|---|---|
| edge (110.4 realised − 98.6 implied) | **+11.8** |
| option round-trip spread, 2 legs at 22–45 DTE | **−8.1** |
| **net** | **+3.7** |

The spread takes **69% of the edge**. What is left is positive, on 63% of start
dates, at 12 rolls a year. Daily hedging costs 8%/yr on hedged notional, which
for an ATM straddle is a fraction of the position.

**Effectiveness: positive but thin, and regime-dependent.** By year the edge was
+18.1 (2022), −1.4 (2023), +12.2 (2024), +12.6 (2025), +24.5 (2026 partial). One
of five years was negative. This is the best-supported structure in the list and
it still loses in a calm year.

**What's missing:** an actual path-dependent backtest. The vol-point arithmetic
is first-order; straddle P&L is `0.5·Γ·S²·(RV² − IV²)·T` and depends on the path,
not just the endpoint.

---

### 2. Long straddle, held to expiry, no hedging at all

Same edge, no hedging bill, but the payoff is a bet on the size of one move
rather than an accumulation of variance. Cheaper to run, far noisier.

**Effectiveness: same +3.7 vol pts of expected edge, much wider distribution.**
Worth including in the same test as #1 as the zero-hedge end of a frequency
sweep — the sweep is the experiment, not two separate studies.

---

### 3. Long call backspread — buy two 25-delta calls, sell one ATM call

**How it owns gamma.** Net long two options against one, so long convexity, part
financed by the short leg.

**Why it is here and the put version is not.** Skew: the 25-delta call trades at
**94.2%** while ATM is **95.0%**. You are buying vol 0.8 points *cheaper* than
the vol you sell. On the put side the same structure buys the 25-delta put at
**105.8%** against ATM at 95.0% — paying 10.8 points over for the wing.

**Effectiveness: unmeasured, structurally favourable on the call side only.**
The skew works for you by ~0.8 vol pts and the financing reduces the premium at
risk. Three legs means roughly 1.5× the spread of a straddle.

---

# TIER 2 — plausible, but one input is missing

### 4. Long-dated straddle, 91–365 DTE

Cheapest options to trade in the whole surface: **4.9 vol pts** round trip, and
the cheapest implied vol at **95.4%**. Low gamma per dollar — mostly a vega
position.

**Missing:** V27 compared 30-day implied against the following 30 sessions. The
matched comparison for a 180-day option against the following 180 sessions has
not been run. **Cheap to fix** — one parameter change to `vol_premium.py`.

---

### 5. Long both SOXL and SOXS, unrebalanced

**How it owns gamma with no option in it.** Both funds decay; you pay that decay
daily and get paid on any large move in either direction. Genuine convexity, no
option spread, no expiry, no roll.

Measured, overlapping windows, 2022–2026:

| hold | mean | median | worst | best |
|---|---|---|---|---|
| 1 month | −0.94% | −1.92% | −29.88% | +61.22% |
| 1 quarter | −0.42% | −6.20% | −37.69% | +231.66% |
| 6 months | +2.36% | −10.28% | −44.03% | +319.98% |
| **1 year** | **+21.55%** | **−12.27%** | −60.80% | +728.91% |

Negative median, positive mean — that is exactly the long-gamma shape.

**Missing:** independence. 4.5 years contains a handful of independent large
moves and the mean rests on them. **This needs the 2019–2021 data we have and,
honestly, a longer history than this repository holds.**

---

### 6. Long straddle hedged only at the open — overnight gamma isolation

48% of variance is overnight. Hedge to flat at 09:30 and leave it, and you own
the gap without paying to chase the intraday chop.

**Missing:** the overnight-only realised vol has been computed as a residual
(80.4%) but never directly against a matched overnight implied. **Also cheap to
fix.**

---

### 7. Long strangle, call side wide / put side narrow

An asymmetric strangle that avoids buying the expensive put wing. Structurally
the same skew argument as #3, with two legs instead of three.

**Missing:** whether the call wing's realised distribution justifies its 94.2%.

---

# TIER 3 — the numbers we already have kill these

### 8. Gamma scalping: long straddle, delta-hedged intraday

The textbook version, and it is the worst one here.

| | vol pts |
|---|---|
| edge (81.0 intraday realised − 98.6 implied) | **−17.6** |
| option round-trip spread | −8.1 |
| **net** | **−25.7** |

Positive on **12% of start dates**. Hedging 4×/day adds 34%/yr of friction on
hedged notional. **You pay 98.6 for volatility and the intraday path delivers
81.** Hedging more often makes it worse, not better, because the thing you are
chasing is not there and the bill is.

---

### 9. 0DTE long gamma

Round-trip spread **28.5 vol points**, 22.2% of the option's own mid price.
Against an edge of at most 11.8. **Dead on the spread alone**, before theta, and
0DTE implied sits at 108.3% — above the 30-day.

---

### 10. Short-dated long gamma, 2–7 DTE

Implied vol here is **112.8%**, the richest point on the whole curve — 13.4
points over the 30-day. Buying gamma at the most expensive tenor, with a 9.3
vol point spread. **Backwards.**

---

### 11. Calendar spread: sell the rich front, buy the cheap back

The term structure genuinely favours this: sell 2–7 DTE at 112.8%, buy 91–365 at
95.4%, **+17.4 vol points of carry**. It fails on friction, not on edge. The
front leg must be rolled ~52×/year at 9.3 vol points a roll. **The rolls cost
more than the carry pays** by a wide margin. Rolling monthly instead removes the
carry (22–45 DTE is 99.4% against the back's 95.4%, only +4.0).

---

### 12. Sell options, delta-hedge intraday

The mirror of #8, and the measurement says it earns +17.6 vol points intraday —
which is why it is tempting and why it is in Tier 3. You cannot be short an
option intraday only. Hold it to the next session and you are short the
overnight gap, which is **48% of all the variance** and the entire reason
close-to-close realised (110.4%) exceeds implied (98.6%). This is the classic
short-gamma structure that pays every day until it does not.

---

### 13. Short SOXL + short SOXS, rebalanced daily

**Break-even combined borrow rate: 0.37%/year.** SOXL and SOXS are among the
most heavily shorted ETFs in the market. Nothing here.

The reason the harvest is absent: a 3× daily-reset fund delivers exactly 3× the
underlying's daily move *by construction*, so rebalancing every day captures no
decay at all. The +1.29% gross is expense ratios and tracking error.

---

### 14. Short SOXL + short SOXS, unrebalanced

Usually described as harvesting decay. It is not long gamma — it is **short a
large move**. Positive median at every horizon, negative mean at 6 months and 1
year, and a **−729% worst one-year window**. The convexity runs against you and
the tail is account-ending.

---

# What I would test, in order

1. **A hedge-frequency sweep on #1/#2/#6 as one experiment** — never, daily at
   the close, daily at the open, 4×, hourly. One study, one prespecified
   adoption bar, and it settles Tier 1 and #6 together.
2. **Re-run `vol_premium.py` at matched tenors** (7, 30, 90, 180 days) — one
   parameter, and it decides #4 and re-checks #1.
3. **#3, the call backspread**, against #1 as its benchmark, not against zero.
4. **#5 on the full 2019–2026 history**, with the honest statement that the mean
   rests on a handful of events.

**Before any of it:** every one of these needs `research_kit.Result` — the
benchmark column — and the friction screen. And #1's real cost is the option
spread measured at *midday*, not the late-day quotes these files carry. Those
are an upper bound; the true number is somewhere below 8.1 vol points and
nobody here knows where. **That single unknown moves #1 between "thin" and
"comfortable" and is worth pinning down first**, and the paper account can
measure it directly by quoting a straddle.
