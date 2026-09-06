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

`independence_check.py`, `tradeability.py`, `edge_test.py` and `protection_cost.py`
print to stdout and write nothing. `protection_cost.py` needs the option files
(`git lfs pull --include="raw_data/SOXL_intraday_5m_exp_*.csv"`, ~4 GB) and a cached
extract of put prints at the 15:55 / 09:30 stamps. `independence_check.py` takes an optional lookback in bars; `tradeability.py`
takes an optional per-side cost in bps (`python3 retreat_lab/tradeability.py 5`).
