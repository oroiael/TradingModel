# retreat_lab — how long SOXL holds an upswing before giving it back

```bash
git lfs pull                                # SOXL_1min.csv, SOXL_5min_6Years.csv
python3 retreat_lab/retreat_timing.py       # all five configs -> retreat_lab/out/
python3 retreat_lab/retreat_timing.py 150 40   # or any (up_bps, dn_bps) pair
python3 retreat_lab/verify.py               # re-checks every episode against raw bars
```

Stdlib only. Measured from `SOXL_1min.csv` — 1-min OHLCV, **2019-12-31 → 2026-07-30,
642,510 bars, 1,653 sessions**, complete minute grid (zero missing minutes), no OHLC
inconsistencies, split-adjusted (largest overnight moves are real events — COVID
March-2020, 2024-08-05 — not basis breaks). Cross-checked on `SOXL_5min_6Years.csv`.

## The event

1. **Anchor** — the running trough while no episode is open.
2. **Trigger** — first bar ≥ `anchor × (1 + up)`. This is the *upswing*.
3. **Peak** — running maximum from the trigger bar onward.
4. **Retreat** — first bar ≤ `peak × (1 − down)`. This is the *retreat*.
   *Leg A* = trigger → peak, *Leg B* = peak → retreat. If the trigger bar is itself
   the peak, Leg A = 0 and the whole wait is Leg B.
5. **Reset** — anchor restarts at the retreat bar; hunt for the next upswing.

Time is reported two ways because the file is regular-hours only: **market minutes**
(tradeable bars elapsed) and **wall-clock minutes** (calendar time, including closed
hours). For an intraday episode they are identical; they diverge only across a close.

### Scope: any minute, not the day's open — and one episode at a time

**The series is one continuous stream, never reset at the open.** The anchor is the
running trough carried forward across days; the calendar is used only to *label*
whether an episode spanned a close. So a trigger can fire on any of the 390 minutes of
a session, measured against a low that may sit hours or days earlier:

| | 2%/0.5% | 5%/2% |
|---|---|---|
| anchor on a *different day* from the trigger | 10.3% | 36.4% |
| anchor age: same day / 1–3 days / 4–7 days | 6,290 / 704 / 20 | 965 / 524 / 29 |
| oldest anchor | 4 calendar days | 6 calendar days |
| anchor is a 09:30 bar (uniform would be 0.3%) | 2.0% | 3.6% |

Anchors and triggers spread across every hour of the session; the mild clustering at
09:30 is just the open often being the day's extreme, not a rule.

**Episodes are sequential and non-overlapping.** The engine holds one anchor and is
either *seeking* (hunting the next upswing) or *armed* (inside an episode, watching for
the retreat). While armed it does not start a new episode, and after a retreat the
anchor restarts at the retreat bar. So the episode count is **"how many fit end to
end", not "how many upswings occurred"** — and the wider the pair, the more of the tape
is locked inside an open episode:

| | 1%/0.25% | 2%/0.5% | 3%/1% | 4%/1.5% | 5%/2% |
|---|---|---|---|---|---|
| bars inside an open episode | 15.7% | 12.2% | 16.9% | 19.8% | **22.5%** |

`independence_check.py` tests whether those two rules drive the answer, by re-measuring
with an anchor that has no episode memory (trailing minimum over a fixed lookback) and,
separately, with overlaps allowed:

| pair | primary (event anchor, no overlap) | V2 (rolling anchor, no overlap) | V1 (rolling anchor, **overlap allowed**) |
|---|---|---|---|
| 5%/2% | n 1,518 · med **41** | n 1,789 · med **48** | n 5,054 · med **76** |
| 4%/1.5% | 2,197 · **26** | 2,517 · **29** | 5,924 · **44** |
| 3%/1% | 3,575 · **13** | 3,635 · **16** | 6,902 · **22** |
| 2%/0.5% | 7,014 · **6** | 5,554 · **7** | 7,795 · **8** |
| 1%/0.25% | 18,166 · **4** | 7,128 · **4** | 8,167 · **4** |

**The anchor rule is not what produces the answer** (primary vs V2 moves the median by
one to seven minutes, and V2 lands within a couple of minutes of primary at every
lookback tried — 78, 390 and 1,950 bars).

**The overlap rule looks like it matters, but the difference is double-counting.**
When overlaps are allowed, one rally spawns many triggers that all terminate at the
*same* retreat bar. At 5%/2%, **60% of V1's episodes are re-counts of a terminal event
already counted** — a single retreat at 2022-12-27 09:30 ends 23 of them, with start
points spread over the previous session and durations from 6 to 305 minutes for what is
one event. The inflation's size also swings with the arbitrary lookback (median 16 / 22
/ 17 at L = 78 / 390 / 1,950), which is what an artifact looks like.

So the non-overlapping count is the right one for *"if I traded this rule, re-arming
after each exit, how long would each round trip last?"* — the question these numbers
answer. It is **not** the answer to *"SOXL is 5% off its low right now, how long have
I got?"*, which conditions on a moment rather than on a completed prior episode; V1's
column is the loose upper bound for that reading, inflated by the re-counting above.

### Start time matters a great deal

The engine treats every minute identically, but the *outcome* depends strongly on when
the episode starts — median market minutes to the retreat, by trigger clock time:

| trigger window | 1%/0.25% | 2%/0.5% | 3%/1% | 4%/1.5% | 5%/2% |
|---|---|---|---|---|---|
| 09:30–10:00 | 3 | 4 | 8 | 16 | **29** |
| 11:00–12:00 | 4 | 8 | 19 | 43 | **76** |
| 13:00–14:00 | 5 | 10 | 29 | 55 | **76** |
| 15:00–15:30 | 4 | 8 | 17 | 37 | **41** |
| 15:30–16:00 | 3 | 5 | 9 | 12 | **16** |

At 5%/2% a midday trigger runs a median 76 minutes and a 9:30 trigger 29 — the opening
half hour is the fastest tape, so upswings there are given back quickest. The late
buckets are **truncated, not fast**: a 15:45 trigger has 15 minutes of session left, so
it either resolves inside them or spans a close, which is exactly the 15:30–16:00 row
of the spanning table above. Read those two rows together, never separately.

## Answer — all five thresholds

| | **5% / 2%** | **4% / 1.5%** | **3% / 1%** | **2% / 0.5%** | **1% / 0.25%** |
|---|---|---|---|---|---|
| up : down ratio | 2.5 : 1 | 2.67 : 1 | 3 : 1 | 4 : 1 | 4 : 1 |
| episodes | 1,518 (0.9/session) | 2,197 (1.3) | 3,575 (2.2) | 7,014 (4.2) | 18,166 (11.0) |
| Leg A · trigger → peak | median **17 min** | **11** | **6** | **3** | **1** |
| Leg B · peak → retreat | median **15 min** | **9** | **5** | **3** | **2** |
| **Total · trigger → retreat** | median **41 min** | **26** | **13** | **6** | **4** |
| mean / p90 / p99 | 95.3 / 276 / 608 | 57.9 / 158 / 386 | 30.4 / 75 / 253 | 11.1 / 26 / 73 | 5.6 / 12 / 32 |
| resolved ≤ 15 min | 25.6% | 36.4% | 54.2% | 79.4% | 94.0% |
| resolved ≤ 30 min | 42.2% | 54.3% | 71.9% | 92.7% | 98.9% |
| resolved ≤ 60 min | 59.7% | 72.5% | 86.7% | 98.2% | 99.9% |
| **survived a full session** | **74 (4.9%)** | 20 (0.9%) | 4 (0.1%) | 0 | 0 |
| **survived two sessions** | **7** | 2 | 0 | 0 | 0 |
| longest | **1,101 min (2.8 sessions)** | 908 (2.3) | 675 (1.7) | 191 (0.5) | 122 (0.3) |
| peak *is* the trigger bar | 13.1% | 14.8% | 19.3% | 26.6% | 34.6% |
| run-up past the line | med 1.54%, p90 6.49% | 1.22%, 4.91% | 0.73%, 3.43% | 0.40%, 1.90% | 0.22%, 1.32% |
| full upswing anchor → peak | med 7.33%, p90 13.23% | 5.76%, 10.53% | 4.22%, 7.75% | 2.70%, 4.79% | 1.45%, 2.81% |
| **spans a close** | **345 (22.7%)** | **309 (14.1%)** | **291 (8.1%)** | **236 (3.4%)** | **332 (1.8%)** |
| — overnight / weekend / holiday | 269 / 72 / 4 | 246 / 60 / 3 | 234 / 54 / 3 | 189 / 45 / 2 | 267 / 60 / 5 |
| — crossed ≥2 closes | **24** (one crossed 3) | 4 | 1 | 0 | 0 |
| — of spanning, triggered 15:30–16:00 | **22%** | 34% | 57% | 83% | 96% |
| retreat itself crossed the gap | 163 (10.7%) | 134 (6.1%) | 139 (3.9%) | 129 (1.8%) | 169 (0.9%) |
| — of those, **survived the open** | **33%** | 19% | 12% | 5% | 3% |
| give-back when the gap did complete it | med **3.96%** | 3.59% | 3.05% | 2.74% | 2.47% |
| weekend episodes per year | 10.9 | 9.1 | 8.2 | 6.8 | 9.1 |

All durations in market minutes; max give-back is 31.5% at every threshold (the same
event, 2020-03-13 → 03-16). The ratios differ across configs — 4:1, 4:1, 3:1, 2.67:1,
2.5:1 — so this is not a clean scaling of one shape: as the upswing grows the retreat
is proportionally deeper too.

## Every column is monotone, and the crossover sits between 2% and 3%

**At 1% and 2% this is an intraday noise event.** Median 4–6 minutes, 93–99% resolved
inside half an hour, nothing ever survived a session, nothing ever crossed more than
one close. The handful that spanned a close did so almost entirely because the bell
arrived first — 83–96% of them were triggered in the final 30 minutes.

**At 3% and above it is a multi-session position, and by 5%/2% that is the norm.**
Only 25.6% of 5%/2% episodes resolve within 15 minutes and **40.3% are still open
after a full hour**; 74 survived a whole session, 7 survived two, 24 crossed two or
more closes (one crossed three), and the longest ran 1,101 market minutes — 2.8
sessions, triggered 2020-12-04 10:39, peaked 2020-12-08 14:24 after a 7.2% run-up,
broke 2% at the 12-09 open. In wall-clock terms the p90 episode lasts 1,402 minutes
(about a day) and the longest 7,460 (5.2 days).

The clearest single indicator is where the spanning episodes come from:

| trigger window | 5%/2% spans | 4%/1.5% | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|---|
| 09:30–10:00 | **11.0%** | 3.2% | 0.4% | 0.0% | 0.0% |
| 11:00–12:00 | **16.3%** | 8.5% | 3.3% | 0.0% | 0.0% |
| 13:00–14:00 | **27.9%** | 21.3% | 6.8% | 0.0% | 0.0% |
| 14:00–15:00 | **39.7%** | 20.7% | 11.6% | 1.4% | 0.1% |
| 15:00–15:30 | **56.2%** | 43.3% | 19.7% | 6.0% | 0.6% |
| 15:30–16:00 | 82.4% | 77.4% | 66.1% | 42.5% | 25.3% |
| *share of all spanning triggered 15:30–16:00* | **22%** | 34% | 57% | 83% | 96% |

At 5%/2% a **9:30 trigger spans a close 11% of the time** and a 1pm trigger 27.9%.
Overnight risk here is not an artifact of running out of session — it is what the
position is.

## A new behaviour at 2%: the gap stops being decisive

At the tight thresholds, a retreat that crossed a close was essentially always
completed by the gap itself — 97% at 1%/0.25%, 95% at 2%/0.5%. That fraction falls
steadily, and at 5%/2% **a third of gap-crossing retreats survive the open**: the
2% band is wide enough that the overnight gap does not clear it, and the position
lives on into the next session before breaking.

So the two overnight risks separate as the threshold widens. The *un-actionable* one
(gap prints straight through your level) grows in severity — median give-back 2.47 →
3.96% — but shrinks as a share of gap-crossings. The *duration* one (you are simply
still holding, days later) grows without bound.

## The thresholds do not scale linearly

Going 1% → 5% on the upswing:

* Episodes fall **18,166 → 7,014 → 3,575 → 2,197 → 1,518** — halving, halving, then
  −39%, then −31%.
* The median wait rises **4 → 6 → 13 → 26 → 41 min** — flat, then roughly doubling.
* Leg B (the retreat itself) rises **2 → 3 → 5 → 9 → 15 min**.

The retreat leg is compressed at the bottom because small retreats sit near SOXL's
noise floor. Measured on the same file, the **median absolute 1-minute return is
0.119%**, so 0.25% is 2.1× a typical minute (22.6% of individual minutes clear it
unaided), 0.5% is 4.2× (6.1%), 1% is 8.4× (0.9%), 1.5% is 12.6× (0.2%) and 2% is
16.8× (0.06%). A 0.25% "retreat" is really just the next wiggle; a 2% one is an event.

## The part that matters for trading

At **every** threshold the gap-completed retreats gave back far more than the
threshold — **median 2.47 / 2.74 / 3.05 / 3.59 / 3.96% below the peak on the first bar
back**, worst 31.5% in all five. Across a close, none of these is a level you get
filled at; the open prints straight past it. Neither widening nor tightening the
retreat protects you there.

What the threshold really chooses is **how much overnight exposure you take on**:
1.8% → 3.4% → 8.1% → 14.1% → **22.7%** of episodes span a close. At 5%/2% roughly
**one episode in four is carried through a close**, one in nine has its retreat
completed by a gap you cannot trade, 72 (10.9/yr) run over a weekend, and 74 are still
open a full session later.

## By year — median market minutes (and % spanning a close)

| year | 5%/2% | 4%/1.5% | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|---|
| 2020 | 28 (21%) | 19 (15%) | 11 (8%) | 5 (3%) | 3 (2%) |
| 2021 | 83 (35%) | 44 (22%) | 20 (10%) | 9 (5%) | 5 (3%) |
| 2022 | 35 (19%) | 20 (11%) | 11 (5%) | 5 (3%) | 3 (1%) |
| 2023 | 100 (38%) | 56 (20%) | 27 (12%) | 9 (4%) | 4 (2%) |
| 2024 | 44 (17%) | 30 (12%) | 18 (7%) | 8 (4%) | 4 (2%) |
| 2025 | 47 (25%) | 27 (12%) | 15 (11%) | 6 (3%) | 4 (2%) |
| 2026 | 27 (13%) | 16 (10%) | 8 (7%) | 5 (3%) | 3 (2%) |

The year ordering is identical at every threshold — 2021 and 2023 are the slow low-vol
grinds, 2022 and 2026 the fast ones — so the ranking is a property of the tape, not of
the threshold. **Read the 5%/2% row-to-row spread with care**: at 144–312 episodes per
year the per-year medians swing 27 → 100 minutes, which is real dispersion but on
samples an order of magnitude thinner than the 1%/0.25% column. Full per-year
n / mean / p90 / max are in each report file.

## Robustness

| variant | 5%/2% | 4%/1.5% | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|---|
| **1-min closes (primary)** | 1,518 · 41 min · 22.7% | 2,197 · 26 · 14.1% | 3,575 · 13 · 8.1% | 7,014 · 6 · 3.4% | 18,166 · 4 · 1.8% |
| 1-min intrabar (High/Low) | 1,869 · 25 min · 16.2% | 2,880 · 12 · 9.8% | 5,003 · 5 · 4.9% | 11,228 · 1 · 1.2% | 40,510 · 1 · 0.5% |
| 5-min closes (separate file) | 1,027 · 85 min · 32.5% | 1,450 · 55 · 21.4% | 2,205 · 30 · 14.1% | 3,945 · 15 · 6.8% | 8,467 · 10 · 4.8% |

The three disagree exactly as sampling says they must, and none reverses the finding
at any threshold. Intrabar High/Low is the *earliest-possible* reading and is
optimistic: a single 1-min bar whose High clears the trigger and whose Low is the
retreat below that High scores as a complete 0-minute episode, though the within-bar
sequence is unknowable at this resolution — it degenerates at 1%/0.25%, where the
median episode is one bar, and is most informative at the wide pairs, where it still
gives a 25-minute median. 5-min bars cannot resolve anything faster than 5 minutes and
skip the wiggles that end an episode, so they overstate duration everywhere. **Closes
on 1-min bars are the primary read: unambiguous, and every level in them is one you
could have transacted at.**

## Is it tradeable? — measured, and mostly no

`tradeability.py` turns each ledger into a trade log; `edge_test.py` asks whether the
events carry information at all. Both were run before any strategy was proposed, and
they rule most of them out.

**The mechanical trade is zero-mean.** Buy at the trigger, sell at the retreat, over
6.6 years, no costs:

| pair | n | win% | mean/trade | median/trade | time in market |
|---|---|---|---|---|---|
| 5%/2% | 1,518 | 37.0% | +0.039% | −0.819% | 22.5% |
| 3%/1% | 3,575 | 36.0% | +0.019% | −0.472% | 16.9% |
| 2%/0.5% | 7,014 | 34.4% | **−0.042%** | −0.303% | 12.2% |
| 1%/0.25% | 18,166 | 35.4% | **−0.002%** | −0.195% | 15.7% |

Mean per trade is within a rounding error of zero and **flips sign** with the threshold
and with a one-bar execution lag. Compounded outcomes swing wildly (−97% to +898%)
because a near-zero mean with 2–4% per-trade dispersion is all volatility drag, not
edge. Buy-and-hold over the same window returned **542%**. The mirror trade (short the
trigger, cover the retreat) is the same series negated and is not a strategy either.

**The trigger and the retreat carry no information.** Forward returns after each event
versus an unconditional random bar, Welch t:

| horizon | after trigger | after retreat | after peak |
|---|---|---|---|
| +15 min | t −0.9 … +0.8 | t +0.2 … +0.8 | **t −32** |
| +60 min | t −1.1 … +0.4 | t +0.2 … +0.9 | **t −26** |

Trigger and retreat are indistinguishable from noise at every threshold and horizon.
The peak looks enormously predictive and is **not tradeable**: it is defined
retrospectively as the running maximum, so price falls after it by construction. That
row is a look-ahead-bias check, not a signal.

**The one candidate edge does not survive a split sample.** Overnight return when an
episode was open at the close looked negative (2%/0.5%: −0.54% vs +0.44%, t −2.64).
Split at 2023-04-13 it is a first-half-only effect — 3%/1% goes −1.22% (t −2.87) then
+0.30% (t +0.64); 1%/0.25% goes −0.89% then −0.01%. It is COVID-era volatility, not
structure, and five thresholds were tested to find one t past 2.

### What the data does establish: the cost of a stop

Slippage against the level the stop was aiming at (`peak × (1 − down)`):

| pair | avg slip/episode | p99 | max | share of total drag from the ~1–11% of episodes crossing a close |
|---|---|---|---|---|
| 5%/2% | 0.486% | 5.86% | 30.1% | **52%** |
| 4%/1.5% | 0.398% | 4.37% | 30.4% | 40% |
| 3%/1% | 0.344% | 3.56% | 30.8% | 33% |
| 2%/0.5% | 0.296% | 2.31% | 31.1% | 21% |
| 1%/0.25% | 0.251% | 1.62% | 31.3% | 12% |

A 0.5% stop costs 0.80% to execute — a **59% overshoot** — and at 5%/2% **half the
total slippage comes from one episode in nine**, the ones that cross a close. That
concentration, not any directional signal, is the durable, actionable finding here.

## What overnight protection actually costs

`protection_cost.py` prices the hedge the slippage finding implies, from
`raw_data/SOXL_intraday_5m_exp_*.csv` (736 files, 5-min option **trade
aggregates**). Buy a put at the last print of the session, sell at the first
print of the next: **37,586 paired trades over 1,353 overnights, 2021-01 → 2026-07.**

Two data facts had to be established first. The **16:00 option bar never carries a
trade** — the last print of the session is 15:55, so that is the entry stamp. And
trade density collapses with tenor: 26% of bars at 0–4 DTE, 5% at 35–39, so only
short-dated contracts support this measurement at all.

### Cost of one night, in bp of the SOXL notional protected

| tenor / strike | median premium | median cost/night | **mean cost/night** | paid off |
|---|---|---|---|---|
| 3–7 DTE, ATM ±1% | 446 bp | 39.2 bp | **14.0 bp** | 40.2% |
| 3–7 DTE, 3–7% OTM | 238 bp | 23.6 bp | **3.6 bp** | 40.3% |
| 8–14 DTE, ATM ±1% | 613 bp | 27.8 bp | **10.5 bp** | 42.4% |
| 1–2 DTE, ATM ±1% | 278 bp | 52.2 bp | **−1.7 bp** | 37.9% |

**Mean far below median is the insurance signature** — you lose a little on most
nights and get paid on the bad ones. Splitting 3–7 DTE ATM by what the night did
shows the payoff working exactly as intended: gap down >2% returns **−241 bp**
(paid off 94.3% of the time), gap up >2% costs **+218 bp** (paid off 0.5%).

### But prints are not quotes

These are trade prints, so the measured cost is a **lower bound** — you buy nearer
the ask and sell nearer the bid. On the 3–7 DTE, 0 to −7% population (n=2,695,
median premium 327 bp):

| round-trip spread | cost/night |
|---|---|
| 0% (measured) | 6.6 bp |
| 5% | 23.0 bp |
| 10% | 39.3 bp |
| 20% | 72.0 bp |

SOXL weekly spreads are realistically 5–15% of premium, so **~25–50 bp/night** is
the honest planning number, not 6.6.

### Head to head with the slippage it prevents

| pair | nights exposed | gap slippage per exposed night | hedge cost/night (5–15% spread) |
|---|---|---|---|
| 5%/2% | 370 | **103 bp** | 23–50 bp |
| 3%/1% | 292 | **137 bp** | 23–50 bp |
| 2%/0.5% | 236 | **188 bp** | 23–50 bp |

The benefit exceeds the cost at every realistic spread. **Three caveats keep this
from being a free lunch**, and they are large:

1. **Delta.** An ATM put is ~0.5 delta, so one put per 100 shares hedges about half
   the initial move; full coverage roughly doubles the cost. Delta rises toward 1 as
   a gap goes ITM, so the tail is better hedged than the median — but the median
   night is over-counted above.
2. **The put and the stop do not target the same level.** "Gap slippage" is measured
   against `peak × (1 − down)`; a put pays below its strike. They overlap, they are
   not the same quantity, so this is an order-of-magnitude comparison, not a P&L.
3. **The benefit only exists if you run the stop strategy** — and the section above
   shows that strategy is zero-mean. Hedging a no-edge strategy does not create edge;
   the cheaper fix is not to trade it.

A conditional test — does the hedge cost less on nights an episode was open? — is
negative at four of five thresholds (t between −0.16 and +0.24). Only 2%/0.5% shows
an effect (−31.2 bp vs +12.8 bp, t −3.01) and it does survive a split sample, but
with no monotone pattern across thresholds and one hit in five tests it should be
read as multiple comparisons, not a finding.

## Selling that premium instead

`premium_selling.py` takes the other side: sell the put at 15:55, buy it back at
the next 09:30. Same 37,586 paired trades. The seller's P&L is the buyer's cost
with the sign flipped, but the two sides are **not** mirror images, because the
spread is paid by whoever crosses and the tail sits entirely on the seller.

### The seller wins most nights and still loses

| tenor / strike | premium | mean | median | win rate | p1 | worst | worst ÷ mean |
|---|---|---|---|---|---|---|---|
| 3–7 DTE, ATM ±1% | 446 bp | **+14.0 bp** | +39.2 | 58.7% | −801 | **−1,497 bp** | 107× |
| 3–7 DTE, 3–7% OTM | 238 bp | **+3.6 bp** | +23.6 | 57.9% | −656 | −1,249 bp | 346× |
| 1–2 DTE, ATM ±1% | 278 bp | **−1.7 bp** | +52.2 | 61.5% | −884 | −1,243 bp | mean ≤ 0 |
| 1–2 DTE, 1–3% OTM | 190 bp | **−16.1 bp** | +36.6 | 59.7% | −838 | −1,086 bp | mean ≤ 0 |

Win rates of 57–63% with a mean near zero or negative is the short-vol signature.
Note the **1–2 DTE rows are already negative before any costs** — the tenor where
theta looks richest is the one where an overnight gap most outruns the premium.

### The equity curve says it plainly

One sale per night, the 3–7 DTE contract nearest 3% OTM, 717 nights 2021-03 → 2026-07:

| round-trip spread | mean/night | total | max drawdown | Sharpe (ann) |
|---|---|---|---|---|
| 0% (prints) | +5.8 bp | +4,172 bp | −3,592 bp | 0.51 |
| **2%** | **−1.2 bp** | −830 bp | −7,049 bp | −0.10 |
| 5% | −11.6 bp | −8,331 bp | −12,236 bp | −1.03 |
| 10% | −29.1 bp | −20,834 bp | −21,283 bp | −2.56 |

**Break-even round-trip spread: 1.8% of premium.** SOXL weeklies realistically run
5–15%, so the seller loses at any spread you can actually trade. And even at a
fictional zero spread the max drawdown is 86% of the entire profit.

The five worst nights are all overnight gaps the study already flagged:

| night | spot | gap | premium | P&L |
|---|---|---|---|---|
| 2026-06-22 | 300.89 | **−21.6%** | 785 bp | **−1,212 bp** |
| 2025-01-24 | 32.73 | −15.5% | 278 bp | −1,057 bp |
| 2024-08-02 | 29.32 | −19.8% | 716 bp | −989 bp |

**One worst night = 208 nights of average income** — and that income is already
negative once you pay the spread. By year the mean is negative in 2021, 2022 and
2024 and positive in 2023, 2025, 2026; the two best years (+24, +30 bp) carry the
two worst tails (−1,057, −1,212 bp).

Conditioning on the retreat study does not rescue it: selling only on nights with no
open episode gives t between 0.00 and 0.46 at four of five thresholds. Only 2%/0.5%
separates (quiet +13.1 bp vs episode-open −36.2 bp, t 1.99) — the same lone threshold
that keeps surfacing across every test here, still short of significance, still one
hit in five.

### Both sides lose to the spread — which is the real finding

| | buyer | seller |
|---|---|---|
| at zero spread | −6.6 bp/night | +5.8 bp/night |
| at 5% spread | −23.0 bp/night | −11.6 bp/night |
| at 10% spread | −39.3 bp/night | −29.1 bp/night |

The mid-market edge either way is ~6 bp; crossing costs 16–33 bp. **The spread is
larger than the entire directional edge**, which is what a well-functioning options
market looks like — the market maker holds the edge, and neither side of this trade
is a strategy.

The asymmetry that remains is one of *purpose*, not expectancy. The buyer is
purchasing insurance: the mean is not the point, the truncation of a 31.5% tail is,
and paying a fair-to-slightly-rich price for that can still be rational. The seller
has no such defence — they take a fat tail for a mean that is negative after costs.

## Selling the spread instead of the naked put

`put_spread.py` replaces the naked short put with a vertical: sell a put ~3% OTM,
buy one below it, same expiration, both legs at the 15:55 print and out at the next
09:30. A naked round trip crosses the market twice; a vertical crosses **four**
times, and the cost knob charges each leg's own premium on every crossing.

### The tail cap works. The economics get worse.

Short leg 3% OTM, 3–7 DTE, width 5% of spot — 654 nights, 2021-03 → 2026-07,
median credit 146 bp of spot against a median max loss of 352 bp:

| per-leg spread | mean/night | total | max DD | win | Sharpe | worst night |
|---|---|---|---|---|---|---|
| 0% (prints) | +2.2 bp | +1,424 bp | −1,871 bp | 54.1% | 0.52 | −336 bp |
| **2%** | **−19.6 bp** | −12,821 bp | −12,907 bp | 44.2% | −4.65 | −401 bp |
| 5% | −52.3 bp | −34,190 bp | −34,190 bp | 23.2% | −11.71 | −499 bp |
| 10% | −106.7 bp | −69,803 bp | −69,803 bp | 6.9% | −20.03 | −661 bp |

**Break-even per-leg spread: 0.2% of premium**, against 1.8% for the naked put.

So the vertical does exactly what it is supposed to do on the tail — worst night
**−336 bp against −1,212 bp naked, a 3.6× reduction**, and the cap binds: on
2026-06-25 (−10.8% gap) the loss stopped at −336 bp against a −336 bp maximum. Two
of the five worst nights finished *inside* the cap because the long leg went ITM too.

But it pays for that with a **9× harder cost hurdle**. The credit is roughly half the
naked premium while the crossings double, so the same real-world spread that merely
erases the naked seller's edge buries the vertical. At a realistic 5% per-leg spread
the naked seller loses 11.6 bp/night and the vertical loses 52.3.

### Width is a dial between the two, not an escape

| width | credit / max loss | mean @ 0 spread | worst night |
|---|---|---|---|
| 2% of spot | 52% | +0.3 bp | −234 bp |
| 5% of spot | 43% | +2.2 bp | −336 bp |
| 10% of spot | 31% | +3.4 bp | −571 bp |

Mean rises and the tail widens monotonically as the long leg moves away — the
structure walks continuously from vertical toward naked, and the expectancy you gain
is exactly the tail you take back on. There is no width at which it becomes a trade.

### Where this leaves all four structures

| structure | mean @ 0 spread | break-even spread | worst night |
|---|---|---|---|
| long put (protection) | −6.6 bp | n/a — it is insurance | +payoff |
| naked short put | +5.8 bp | 1.8% | **−1,212 bp** |
| short 5%-wide vertical | +2.2 bp | **0.2%** | −336 bp |

Every structure here is priced through the spread. The mid-market edge is a few bp in
either direction; crossing costs 16–33 bp naked and roughly double that for a
vertical. Defining the risk does not create edge — it buys a smaller tail at a
strictly worse expectancy, and in this market that trade is not close.

## Buying the spread instead

The same `put_spread.py` also prices the debit side: long a put ~1% OTM, short one
below it — capped protection, bought cheaper than the naked put. It is cheaper. It
also stops working exactly where it is needed.

### Coverage runs backwards

Realised option P&L as a share of the underlying's loss that night, 562 nights with
both structures priced, 5%-wide spread:

| gap bucket | n | underlying loss | naked put | cover | **spread** | **cover** |
|---|---|---|---|---|---|---|
| 0 to −1% | 57 | 51 bp | 14 bp | 27% | 11 bp | 23% |
| −1 to −3% | 108 | 190 bp | 70 bp | 37% | 31 bp | **17%** |
| −3 to −6% | 73 | 419 bp | 187 bp | 45% | 71 bp | **17%** |
| **worse than −6%** | 24 | 986 bp | 571 bp | **58%** | 123 bp | **12%** |

**The naked put's coverage rises with the size of the gap — 27% → 58% — which is what
insurance is supposed to do. The spread's coverage falls, 23% → 12%.** The short leg
is a promise to stop protecting you, and it comes due precisely on the nights the
position exists for.

Night by night on the five worst gaps:

| night | gap | underlying loss | naked put | spread | spread's cap |
|---|---|---|---|---|---|
| 2026-06-22 | −21.6% | 2,157 bp | **1,497 bp** | 248 bp | 157 bp |
| 2024-08-02 | −19.8% | 1,978 bp | **1,177 bp** | 188 bp | 153 bp |
| 2025-01-24 | −15.5% | 1,549 bp | **1,210 bp** | 217 bp | 165 bp |
| 2026-03-02 | −12.0% | 1,203 bp | 614 bp | **−69 bp** | 220 bp |

On 2026-03-02 the "protection" **lost money on a 12% adverse gap**.

### And it costs more to run

| per-leg spread | long naked put | long 5%-wide vertical |
|---|---|---|
| 0% (prints) | −6.6 bp | **−3.1 bp** |
| 5% | −23.0 bp | **−70.6 bp** |
| 10% | −39.3 bp | **−138.0 bp** |

Cheaper at a fictional zero spread, three times dearer at a realistic one, because
two legs cross the market twice as often. So the debit spread buys you a lower
premium in exchange for **5× less tail coverage and 3× the friction**.

### All four structures, together

| structure | mean @ 0 spread | @ 5% spread | tail behaviour |
|---|---|---|---|
| **long put** | −6.6 bp | −23.0 bp | covers **58%** of a >6% gap |
| long vertical | −3.1 bp | −70.6 bp | covers 12%; can lose on a −12% night |
| short put | +5.8 bp | −11.6 bp | worst night −1,212 bp |
| short vertical | +2.2 bp | −52.3 bp | worst night −336 bp |

Both two-leg structures are dominated by their one-leg counterparts once real spreads
are paid. Selling the vertical caps a tail but moves break-even from a 1.8% spread to
0.2%; buying it lowers the premium but guts the coverage. The second leg always pays
for itself in something you wanted.

**The only structure here that does its job is the naked long put, and only as
insurance** — its expectancy is negative by construction, the point is that it is the
one thing measured in this lab whose protection gets *better* as the night gets worse.

## Buying the put and selling a call against it — the collar

`collar.py` puts the second leg on the *other* side: keep the put whole, sell a call
to pay for it, give up upside instead of downside. That is a different trade-off from
the debit spread, and it measures very differently. Uses `raw_data/SOXL_intraday_5m_exp_*.csv`
for both rights — 187,032 call prints alongside the 161,613 put prints.

### The risk transformation is real, and the coverage is right way up

3% OTM put / 3% OTM call, 3–7 DTE, 634 nights, holding 100 shares through the night:

| position | mean | sd | worst | best | Sharpe |
|---|---|---|---|---|---|
| stock alone | 27.5 bp | 419.7 bp | −2,157 bp | 1,987 bp | 1.04 |
| stock + collar @ 0% spread | 1.7 bp | **135.8 bp** | **−592 bp** | 477 bp | 0.20 |

Volatility falls **3.1×** and the worst night **3.6×**. Unlike the debit spread,
coverage *rises* with the size of the gap — 71% on −3 to 0%, 75% on −6 to −3%,
**86% worse than −6%** — because on a down gap the put gains **and** the short call
also gains. Both legs pull the same way. That is the structural difference from the
put spread, where the short leg fought you exactly when it mattered.

The median net debit is **0 bp**: at 3%/3% the call fully finances the put.

### But the call costs 2.5× more than the put it finances

Leg attribution over the same 634 nights, zero spread:

| | bp/night |
|---|---|
| stock overnight drift | **+27.5** |
| long put leg | −7.4 |
| **short call leg** | **−18.4** |
| collar net | +1.7 |

| leg | 335 up nights | 299 down nights |
|---|---|---|
| call | **−135.2 bp** | +112.5 bp |
| put | −117.2 bp | +115.6 bp |

On a >6% up gap the collar surrenders 747 bp of a 931 bp rally — you keep 20%.

### Vol-matched, the protective put alone beats both

A structure that cuts volatility must be compared at equal risk:

| position | mean | sd | Sharpe | **vol-matched mean** |
|---|---|---|---|---|
| stock alone | 27.5 bp | 419.7 bp | 1.04 | 27.5 bp |
| **stock + long put only** | 20.1 bp | 269.3 bp | **1.18** | **31.3 bp** |
| stock + collar | 1.7 bp | 135.8 bp | 0.20 | 5.3 bp |

**At zero spread the protective put alone is the only overlay in this lab that beats
holding the stock** — Sharpe 1.18 against 1.04, and 31.3 bp against 27.5 bp once
levered to equal volatility. Adding the call takes that to 5.3 bp. At a realistic 5%
per-leg spread everything is negative again: put-only −14.0 bp/night, collar −66.4.

### The caveat that matters most

SOXL's overnight drift over this sample is **+27.5 bp/night — about +69%/yr from gaps
alone.** A short call is structurally punished in that regime, so **the call-leg
result is the most sample-dependent number in this lab.** In a flat or falling market
the collar would look materially better, and nothing measured here rules that out.
The put-leg and coverage results do not depend on the drift the same way; the −18.4
bp/night call cost does.

### Every structure measured, together

| structure | mean @ 0 spread | @ 5% spread | tail behaviour |
|---|---|---|---|
| **long put** | −6.6 bp overlay / **+31.3 bp vol-matched** | −23.0 bp | covers 58–86% of a big gap |
| **collar** | +1.7 bp / +5.3 vol-matched | −66.4 bp | covers 86%, keeps 20% of a big rally |
| long vertical | −3.1 bp | −70.6 bp | covers 12%; can lose on a −12% night |
| short put | +5.8 bp | −11.6 bp | worst night −1,212 bp |
| short vertical | +2.2 bp | −52.3 bp | worst night −336 bp |

The collar is the first two-leg structure here that is not dominated on risk — it
genuinely converts a fat-tailed holding into a narrow one, with coverage that improves
as the night gets worse. What it cannot do is survive the spread, and in this sample
it pays for its protection with more upside than the protection is worth.

## The three underlying-only claims, tested

This lab asserted three risk-management claims and did not check them.
`exit_rules.py` does. Entry is always the same +2% trigger (7,014 of them, no
directional edge), so only the exit rule varies — these are exit-quality questions,
judged on dispersion, tail and execution slippage, not on profit.

### Claim 1 — "time stops beat price stops": **supported, but "beats" is too strong**

At matched holding periods:

| exit rule | median hold | mean | sd | p1 | slippage |
|---|---|---|---|---|---|
| trailing stop 0.50% | 6 min | −4.21 bp | 136.2 | −225 bp | **29.6 bp** |
| time stop 5 min | 5 min | **−1.51 bp** | **123.1** | **−336 bp** | **0** |
| trailing stop 1.00% | 15 min | −2.43 bp | 201.3 | −386 bp | 33.9 bp |
| time stop 15 min | 15 min | −2.01 bp | 209.1 | −549 bp | **0** |

The clock exit gives an equal-or-better mean and **eliminates the 26–34 bp of
slippage entirely** — a stop has to be filled, a clock does not. But it has a
*fatter left tail* (p1 −336 vs −225), because it never cuts a loser. So it is a
trade, not a free win: you swap guaranteed slippage for an uncapped tail.

### Claim 2 — "don't set a stop tighter than ~0.5%": **not supported**

| trailing stop | mean | sd | worst | slippage | spans a close |
|---|---|---|---|---|---|
| **0.25%** | **−1.74 bp** | **106.9** | −2,799 | **28.3 bp** | **1.9%** |
| 0.50% | −4.21 bp | 136.2 | −2,799 | 29.6 bp | 3.4% |
| 1.00% | −2.43 bp | 201.3 | −2,799 | 33.9 bp | 8.5% |
| 3.00% | +22.48 bp | 493.9 | −2,799 | 60.6 bp | 43.2% |

The claim was that below ~0.5% you stop on noise and it costs you. **It does not.**
The 0.25% stop has the *lowest* dispersion, the *lowest* slippage and the *least*
overnight exposure, with a mean no worse than 0.5%. The reasoning was wrong:
stopping on noise costs nothing when there is no edge to protect. The rising mean at
wider stops (+22 bp at 3%) is not stop quality — it is holding longer and collecting
more of SOXL's drift, bought with 4.6× the dispersion.

The real argument against a very tight stop is **turnover** — more round trips, more
commission and spread — and this test does not price that. It is a cost question, not
a noise question.

### Claim 3 — "don't open a stop-managed position in the last 30 minutes": **strongly supported**

Trailing stop 0.50%, split by entry time:

| entries | n | mean | sd | worst | spans a close | slippage |
|---|---|---|---|---|---|---|
| before 15:30 | 6,550 | −2.59 bp | 98.1 | −436 | 0.6% | 23.9 bp |
| **15:30–16:00** | 464 | **−27.07 bp** | 379.6 | **−2,799** | 42.5% | **110.7 bp** |
| late, forced flat at the bell | 464 | **+8.84 bp** | 95.9 | −226 | 0% | 27.4 bp |

Late entries are **10× worse in mean, 4× the dispersion, 6× the worst case and 4.6×
the slippage.** At a 1% stop it is starker still: −53.75 bp and 156.9 bp of slippage.

But the fix is better than the claim. **Do not avoid the entry — force the exit.**

### The finding none of the three claims made

Flattening at the bell rather than holding the stop overnight improves **every metric
at every stop width**, and costs nothing:

| rule | mean | sd | worst | spans |
|---|---|---|---|---|
| stop 0.50%, hold overnight | −4.21 bp | 136.2 | −2,799 | 3.4% |
| **stop 0.50%, flat at bell** | **−1.86 bp** | **95.4** | **−435** | 0% |
| stop 1.00%, hold overnight | −2.43 bp | 201.3 | −2,799 | 8.5% |
| **stop 1.00%, flat at bell** | **+0.55 bp** | **143.5** | **−435** | 0% |
| stop 2.00%, hold overnight | +1.64 bp | 331.8 | −2,799 | 25.7% |
| **stop 2.00%, flat at bell** | **+4.03 bp** | **222.1** | **−548** | 0% |

Mean improves, dispersion falls ~30%, and the worst case falls **6×** — from −2,799 bp
to −435. No premium, no second leg, no options account. The whole options investigation
above was chasing a way to survive the overnight gap; **the cheapest way to survive it
is not to be there.** That only costs the overnight drift, which the entry signal does
not earn anyway.

## Backtesting the underlying-only rules — and a correction

`exit_rules.py` compared exits per-trade. Per-trade means hide compounding and
turnover, so `backtest.py` runs each rule as a full strategy: compounded equity,
costs per side, drawdown, against buy-and-hold over the same 6.6 years. All-in /
all-out, never levered, no overlapping trades.

### Every variant loses, most of them catastrophically

At 1 bp per side (2 bp round trip):

| strategy | total | CAGR | max DD | Sharpe | trades | in market |
|---|---|---|---|---|---|---|
| **buy and hold** | **+542%** | **+32.7%** | | | 1 | 100% |
| trail 2%, flat at bell | −42% | −7.9% | −71.2% | 0.15 | 4,409 | 56.8% |
| flat at bell only (no stop) | −73% | −18.2% | −83.1% | 0.16 | 1,658 | 90.0% |
| trail 1%, flat at bell | −79% | −20.9% | −87.1% | −0.31 | 6,083 | 29.2% |
| time 30m, flat at bell | −82% | −22.9% | −93.8% | −0.18 | 5,528 | 24.7% |
| trail 0.5%, flat at bell | −95% | −36.9% | −96.4% | −1.32 | 7,014 | 12.1% |
| trail 0.5%, hold overnight | −99% | −53.3% | −99.4% | −1.49 | 7,014 | 12.2% |

Set costs to zero and only one variant turns positive — trail 2% flat at bell,
**+40% against buy-and-hold's +542%.** The per-trade improvements were real and they
do not survive contact with turnover: **1,066 round trips a year is 21.3%/yr of pure
friction at 1 bp per side, 42.6%/yr at 2 bp.**

### The entry is worse than random

| rule | trigger entry | random entry, same count |
|---|---|---|
| trail 1%, flat at bell | **−79%** | −22% |
| time 30m, flat at bell | −82% | −85% |

Entering on a +2% upswing is *actively worse* than entering at a random minute. This
does not contradict the earlier finding that the trigger has no directional edge
(t −1.1 to +1.0) — it explains it. The trigger is not predictive of direction, but it
is systematically bad for a **trailing stop**, because you enter at a local extreme
where the stop sits immediately under a fresh peak. Recall 26.6% of triggers *are*
the peak.

### The correction: what "flat at the bell" actually costs

Decomposing SOXL's 6.6 years into the two legs:

| leg | total | annualised |
|---|---|---|
| **overnight (close → next open), 1,652 nights** | **+2,320%** | **+62.3%/yr** |
| **intraday (open → close), 1,652 sessions** | **−75%** | **−19.1%/yr** |

**SOXL's entire return is overnight. The intraday session is a persistent −19.1%/yr
headwind.** Buy-and-hold's +542% is the product of the two.

This overturns the recommendation this lab made one section earlier. "Flat at the
bell" was offered as a free improvement because it improved every per-trade metric —
mean, dispersion, worst case. It improved them **by removing exposure to the only
part of the day that makes money.** The claim that it "costs only the overnight
drift, which this entry signal does not earn anyway" was right about the signal and
badly wrong about the magnitude: that drift is +62.3%/yr, the whole instrument.

So the per-trade table was not measuring a better rule. It was measuring the risk
reduction you get from being flat — which you can obtain more cheaply and completely
by not trading at all.

### What survives

Nothing, as a strategy. Any intraday long on SOXL fights a −19.1%/yr drift before
costs, and this entry adds 1,066 round trips a year of friction on top. The three
exit-rule claims tested in the previous section remain correct **as statements about
exits** — a clock exit really does eliminate slippage, late entries really are far
worse, tight stops really do have the lowest dispersion — but they are refinements to
a position that should not be opened. **The measured conclusion of this lab is that
the tradeable content of the retreat timing study is zero, and the one durable fact
it surfaced is about when SOXL earns its return, not about upswings and retreats.**

## Backtesting the overnight-only strategy

`overnight.py` turns the decomposition into a strategy and charges it: buy at the
session close, sell at the next open, flat all day. 251 round trips a year against
the trigger strategy's 1,066, so friction is ~4× lighter — 5.0%/yr at 1 bp per side.

### It beats buy-and-hold, and survives realistic costs

| strategy | total | CAGR | max DD | Sharpe | win |
|---|---|---|---|---|---|
| buy and hold | +542% | 32.7% | −90.5% | 0.78 | |
| **sell at the 09:30 open print** | **+1,586%** | **53.6%** | −78.2% | **0.97** | 54.8% |
| sell 5 min after the open | +1,214% | 47.9% | −85.6% | 0.91 | 53.0% |
| sell 30 min after the open | +886% | 41.6% | −85.8% | 0.84 | 52.1% |

Cost sensitivity, selling at the open print: **+2,245% at 0 bp, +1,586% at 1, +1,112%
at 2, +350% at 5, and −14% at 10 bp per side.** It needs sub-5-bp execution — plausible
in SOXL with MOC/MOO orders, fatal if you cross a spread.

The edge decays the longer you hold past the open (53.6% → 47.9% → 41.6% CAGR), which
is consistent with a genuine open-print effect rather than a data artifact.

### But the return is 20 nights out of 1,652

| | total |
|---|---|
| all 1,652 nights | +1,586% |
| drop the best 5 | +624% |
| drop the best 10 | +249% |
| **drop the best 20 (1.2% of nights)** | **−0%** |
| drop the best 50 | −95% |

**The entire six-year return comes from twenty nights.** That is not a drift you
harvest; it is a lottery-ticket portfolio that happened to hit. And the nights that
pay are the volatile ones — precisely where your fill is least likely to match a print
in a 5-minute aggregate.

### And it is not stable

| year | overnight | buy & hold | intraday |
|---|---|---|---|
| 2020 | **+134.8%** | +61.3% | −32.5% |
| 2021 | +140.0% | +127.5% | −13.6% |
| 2022 | −69.7% | −86.5% | −53.8% |
| **2023** | **−0.2%** | **+175.4%** | **+180.1%** |
| 2024 | **+207.1%** | −7.3% | −70.9% |
| 2025 | +54.5% | +68.0% | −1.2% |
| 2026 | +100.9% | +155.0% | +15.1% |

**2023 reverses the thesis completely** — the overnight leg made nothing while the
intraday leg made +180%. Leave-one-year-out spans +449% (excluding 2024) to +5,457%
(excluding 2022). Split-half: +53% then +998%, Sharpe 0.54 then 1.36.

The mean is **0.272%/night, sd 4.46%, t = 2.48** — marginal for a single test, and
this was not an independent test: the effect was found by looking, then measured on
the same data.

### The tail is the point

Worst nights: −31.2% (2020-03-13), −23.3%, −22.2%, −21.6% (2026-06-22), −20.5%.
**147 nights worse than −5%, 31 worse than −10%**, against a best night of +19.9%.
Max drawdown −78.2%.

So the honest description is not "SOXL drifts up overnight." It is: **SOXL's largest
gaps in both directions happen overnight, and over this particular sample the up-gaps
won, by a margin concentrated in twenty nights.** You are being paid to hold
event risk through the close — which is the same risk the protective-put section was
trying to hedge, and hedging it would cost more than the 0.272%/night it pays.

### Verdict

Better risk-adjusted than buy-and-hold on this sample (Sharpe 0.97 vs 0.78) and the
only structure in this lab that beats it at all. But it is a concentrated, unstable,
cost-fragile bet on a regime that fully reversed in 2023, with a −78% drawdown and a
−31% single night. It is a real finding about **where SOXL's return lives**, and a
weak basis for a strategy.

## The intraday short — and a correction to how the decomposition was described

`intraday_short.py` trades the other leg: short at the open, cover at the close, flat
overnight. An intraday-only short is flat at settlement so it typically avoids the
overnight borrow charge, but borrow is a parameter here rather than an assumption.

### It loses catastrophically — and so does the long

| strategy | total | CAGR | max DD | Sharpe | worst day |
|---|---|---|---|---|---|
| buy and hold | +528% | 32.2% | | | |
| intraday **long** (open→close) | −80% | −21.9% | −92.6% | 0.16 | −21.1% |
| **intraday SHORT (open→close)** | **−99%** | **−47.6%** | −99.4% | −0.28 | **−51.7%** |
| overnight long (close→open) | +1,586% | 53.6% | −78.2% | 0.97 | −31.2% |
| short the day + long the night | −74% | −18.6% | −98.5% | 0.40 | −51.7% |

Costs and borrow barely matter — at **zero** cost and zero borrow the short still
returns −98%. It loses in six of seven years, in both sample halves (−88% / −88%),
and **t = −0.71** on the daily mean. There is no intraday edge in either direction.

### Why: it is variance drag, not drift

| leg | arithmetic mean | geometric mean | daily sd | variance drag |
|---|---|---|---|---|
| **intraday** | **+0.0770%/day (+21.4%/yr)** | −0.0784%/day (**−17.9%/yr**) | 5.58% | **39%/yr** |
| overnight | +0.2919%/day (+108.5%/yr) | +0.1912%/day (+61.8%/yr) | 4.46% | 25%/yr |

**The intraday leg's arithmetic mean is positive.** Its −17.9%/yr compounded result is
entirely the ½σ² penalty of compounding a 5.58%-a-day series — 39%/yr of pure drag on
a 3× levered ETF.

This corrects how the previous section described it. Calling intraday "a persistent
−19.1%/yr headwind" implies a drift you can short. **You cannot short variance drag.**
Shorting flips the sign of the mean — turning +0.077%/day into −0.097%/day after
costs — while the drag stays exactly where it was, because drag is symmetric. The
short is charged twice and compounds to −99%.

The overnight leg is different in kind, not just in sign: its arithmetic mean
(+108.5%/yr) is large enough to survive its own 25%/yr drag. That, not a directional
tilt, is why one leg works and the other cannot.

### The tail closes the case

Worst days for the short: **−51.7%**, −25.3%, −24.0%, −19.0%, −18.6%. **262 days worse
than −5%, 47 worse than −10%.** A single 2025 session took more than half the account.
Dropping the best 5, 10, 20 or 50 days changes nothing — it is already −99%.

### Where the whole investigation lands

| | arithmetic | geometric | verdict |
|---|---|---|---|
| overnight long | +108.5%/yr | **+61.8%/yr** | works, but 20 nights carry it and 2023 reversed it |
| intraday long | +21.4%/yr | −17.9%/yr | positive edge, eaten by drag |
| intraday short | −21.4%/yr | −47.6%/yr | drag *and* negative mean |

The only leg with a mean big enough to beat its own compounding penalty is the
overnight one, and the previous section already showed that leg is 20 nights of luck
in a 1,652-night sample. Everything else in this lab is a way of paying friction to
hold a zero-mean exposure.

## Holding overnight only when volatility is low

`overnight_vol_filter.py` conditions the overnight leg on volatility. **Data note:**
the VIX index itself was not obtainable — it is absent from the repo, and IBKR
returns "Details currently unavailable" for contract 13455763 (index subscription).
Two substitutes are used and reported side by side, both computed strictly through
the close of day D so there is no look-ahead:

* **RV20** — SOXL's own trailing 20-session realised volatility, annualised.
* **VXXr** — VXX over its own 60-day average. VXX's *level* is useless across time
  (roll decay and reverse splits put 2026's maximum below 2020's minimum), but the
  ratio to its own recent average detrends that and tracks the vol regime.

### On SOXL's own realised vol, the filter improves everything

| filter | nights | total | CAGR | max DD | Sharpe | worst night |
|---|---|---|---|---|---|---|
| all nights | 1,632 | +1,482% | 52.1% | **−78.2%** | 0.95 | **−31.2%** |
| **RV20 below p60** | 979 | **+2,248%** | **61.6%** | **−29.5%** | **1.38** | −15.5% |
| RV20 below p80 | 1,305 | +2,729% | 66.2% | −59.2% | 1.24 | −15.5% |

By quintile, and it is close to monotone:

| RV20 quintile | nights | total | Sharpe | worst | mean/night |
|---|---|---|---|---|---|
| 1 (lowest vol) | 326 | +144% | 0.79 | −7.5% | 0.312% |
| 2 | 326 | +278% | 1.01 | −15.5% | **0.461%** |
| 3 | 327 | +155% | 0.65 | −13.7% | 0.364% |
| 4 | 326 | +20% | 0.25 | −15.0% | 0.157% |
| **5 (highest vol)** | 327 | **−44%** | 0.06 | **−31.2%** | 0.060% |

**The top vol quintile loses money outright.** Excluding the top two takes the whole
strategy from +1,482% to +2,248% while cutting the drawdown from −78.2% to −29.5%.

### It is not keeping the big winners — it is dropping the big losers

The 20 best nights sit at a **median RV20 percentile of 95**; the 20 worst at **93**.
Only 1 of the best 20 is in the lowest vol quintile, and 0 of the worst 20. High vol
produces both tails. The filter gives up most of the biggest up-nights and still ends
ahead, because in that bucket the losses outweigh the wins.

That also fixes the fragility. Unfiltered, dropping the best 20 nights took the
strategy to **−6%**. Filtered, it still returns **+271%**:

| | unfiltered | RV20 below p60 |
|---|---|---|
| full | +1,482% | +2,248% |
| drop best 20 | **−6%** | **+271%** |
| drop best 50 | −95% | −42% |

### Robustness

| test | result |
|---|---|
| by year | positive in **6 of 7** (2022 −19.0% against −69.7% unfiltered; 2023 **+23.0%** against −0.2%) |
| split halves | +232% (t 2.09) then +607% (t 2.86) — both positive, both significant |
| worst night per year | −6.8% to −15.5%, against −31.2% unfiltered |
| t on the mean | **3.53** (0.379%/night, sd 3.36%), against 2.48 unfiltered |

This is the only result in this lab that survived every robustness test applied to it.

### Three caveats that matter

1. **The VIX-like proxy does not confirm it.** On VXX/MA60 the quintiles are
   non-monotone and the *lowest* bucket is the worst: −56% total, Sharpe −0.38.
   Trading below its p20 loses money. So this is a **SOXL-realised-vol** effect, not a
   "VIX is low" effect — the two measure different things, and the question as asked
   ("when VIX is low") is answered **no** by the closest proxy available here.
2. **"Low vol" here is not calm.** The p60 threshold is **107.6% annualised**. This
   filter does not select quiet markets; it selects SOXL below its own median chaos.
3. **The threshold was chosen from the same data.** p20/p40/p60/p80 were all tested
   and p60 reported. p40 (+822%) and p80 (+2,729%) also beat unfiltered, so it is not
   a knife-edge, but the exact cut is fitted and should be expected to degrade
   out of sample.

## Limitations

* **Regular hours only.** The file is 09:30–15:59; there is no pre/post-market data.
  A retreat that truly occurred at 16:30 is recorded at the next open, so the
  "spans a close" counts are an upper bound on *market-hours* duration and the
  overnight/weekend split is a statement about the RTH session grid. **This caveat
  binds hardest at 5%/2%**, where 22.7% of episodes span a close and 24 cross two or
  more — nearly a quarter of the answer depends on hours this file cannot see, against
  1.8% at 1%/0.25%.
* **Trades, not quotes**, and closes are bar-end marks — no bid/ask, so nothing here
  is net of spread or slippage. That matters most at 0.25%: a threshold roughly two
  ticks wide on a $100 stock is inside the round-trip cost of acting on it.
* The anchor is a *running trough with no minimum dwell*, so an upswing off a
  one-minute spike low counts the same as one off a multi-day base. That is the
  question as posed; a swing-confirmation filter would cut the episode count and
  lengthen the median.
* Episode boundaries are sequential and non-overlapping: a new upswing is only hunted
  after the prior episode's retreat completes. At the wide pairs this materially
  reduces the count — at 5%/2% the tape spends a large share of its time inside an
  open episode, so 1,518 is "how many fit end-to-end", not "how many 5% upswings
  occurred".

## Correctness

`verify.py` re-derives every claim in every ledger straight from `SOXL_1min.csv`
without reusing the state machine — ordering, ledger prices against the file, the
trigger clearing the threshold *and being the first such bar*, the anchor being the
true running trough, the peak being the true running max, the retreat clearing its
threshold *and being the first breach*, both legs summing to the total, market/wall
minutes against the grid, the span labels against the actual dates, and non-overlap.
**1,518 / 1,518, 2,197 / 2,197, 3,575 / 3,575, 7,014 / 7,014 and 18,166 / 18,166
pass, 0 failures.**

That check earned its keep. The first engine tested thresholds in floating point and
silently dropped **9 genuine triggers** sitting exactly on +2.000%: `14.00 * 1.02`
evaluates to `14.280000000000001`, so a real move to `14.28` failed `>=`. Every price
in both files is exactly 2 decimals, so the engine carries prices as **integer cents**
and thresholds as **integer basis points**, testing `px*10000 >= trough*(10000+up_bps)`
and `px*10000 <= peak*(10000−dn_bps)`. No tolerance, no boundary class of bug, and any
threshold pair expressible in bps stays exact.

## Output

Files are tagged `up<bps>_dn<bps>` — `up500_dn200` is 5%/2%, `up400_dn150` is 4%/1.5%,
`up300_dn100` is 3%/1%, `up200_dn50` is 2%/0.5%, `up100_dn25` is 1%/0.25%.

| file | what |
|---|---|
| `out/retreat_report_<tag>.txt` | full report — primary plus both sensitivities |
| `out/retreat_episodes_1min_<tag>.csv` | every episode: anchor/trigger/peak/retreat stamps and prices, both leg durations on both clocks, run-up, span label, gap flag |
| `out/retreat_episodes_1min_intrabar_<tag>.csv` | same for the intrabar variant |

`independence_check.py`, `tradeability.py`, `edge_test.py`, `protection_cost.py` and
`premium_selling.py`, `put_spread.py`, `collar.py`, `exit_rules.py`, `backtest.py` and `overnight.py` print to stdout and write nothing;
`backtest.py`, `overnight.py` and `intraday_short.py` take an optional cost in bps
per side; `intraday_short.py` also takes an annual borrow rate. `overnight_vol_filter.py`
takes an optional cost in bps per side. `collar.py` needs cached extracts of both put and call prints at the
15:55 / 09:30 stamps. `protection_cost.py` needs the option files
(`git lfs pull --include="raw_data/SOXL_intraday_5m_exp_*.csv"`, ~4 GB) and a cached
extract of put prints at the 15:55 / 09:30 stamps. `independence_check.py` takes an optional lookback in bars; `tradeability.py`
takes an optional per-side cost in bps (`python3 retreat_lab/tradeability.py 5`).
