# retreat_lab — how long SOXL holds an upswing before giving it back

```bash
git lfs pull                                # SOXL_1min.csv, SOXL_5min_6Years.csv
python3 retreat_lab/retreat_timing.py       # all three configs -> retreat_lab/out/
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

## Answer — all three thresholds

| | **3% up / 1% back** | **2% up / 0.5% back** | **1% up / 0.25% back** |
|---|---|---|---|
| episodes | 3,575 (2.2 / session) | 7,014 (4.2 / session) | 18,166 (11.0 / session) |
| Leg A · trigger → peak | median **6 min** | median **3 min** | median **1 min** |
| Leg B · peak → retreat | median **5 min** | median **3 min** | median **2 min** |
| **Total · trigger → retreat** | median **13 min** | median **6 min** | median **4 min** |
| mean / p90 / p99 / max | 30.4 / 75 / 253 / 675 | 11.1 / 26 / 73 / 191 | 5.6 / 12 / 32 / 122 |
| resolved ≤ 5 min | 23.9% | 45.3% | 67.6% |
| resolved ≤ 15 min | 54.2% | 79.4% | 94.0% |
| resolved ≤ 30 min | 71.9% | 92.7% | 98.9% |
| resolved ≤ 60 min | 86.7% | 98.2% | 99.9% |
| **survived a full session** | **4** | 0 | 0 |
| **max closes crossed by one episode** | **2** | 1 | 1 |
| peak *is* the trigger bar | 19.3% | 26.6% | 34.6% |
| run-up past the line | med 0.73%, p90 3.43% | med 0.40%, p90 1.90% | med 0.22%, p90 1.32% |
| full upswing anchor → peak | med 4.22%, p90 7.75% | med 2.70%, p90 4.79% | med 1.45%, p90 2.81% |
| **spans a close** | **291 (8.1%)** | **236 (3.4%)** | **332 (1.8%)** |
| — overnight / weekend / holiday | 234 / 54 / 3 | 189 / 45 / 2 | 267 / 60 / 5 |
| — of spanning, triggered 15:30–16:00 | **57%** | 83% | 96% |
| retreat itself crossed the gap | 139 (3.9%) | 129 (1.8%) | 169 (0.9%) |
| — of those, breached on first bar back | 122 | 123 | 164 |
| give-back on that first bar back | med **3.05%**, max 31.5% | med **2.74%**, max 31.5% | med **2.47%**, max 31.5% |
| weekend episodes per year | 8.2 | 6.8 | 9.1 |

All durations in market minutes. Note 3%/1% is a **3:1** up:down ratio where the other
two are **4:1**, so this is not a clean scaling of one shape — the retreat is
proportionally deeper as well as absolutely deeper.

### 3%/1% is where the behaviour changes kind, not just degree

At 1% and 2% the story was the same: a fast intraday event, and the handful that span
a close do so only because the bell arrived first. At 3%/1% that stops being true.

* **Duration becomes comparable to the session.** Median 13 minutes, but p90 is 75 and
  p99 is 253 — over half a session. **Four episodes survived a full session** (worst
  675 market minutes, 1.7 sessions: triggered 2021-10-18 09:48, peaked 2021-10-19
  13:00 after a 6.4% run-up, broke 1% at 14:33). Neither tighter threshold produced a
  single one.
* **One episode crossed two closes** — 2025-12-23 11:54 → 2025-12-26 09:50, over
  Christmas. At 1% and 2% no episode ever crossed more than one.
* **The clock-artifact explanation weakens.** Only 57% of spanning episodes were
  triggered in the last 30 minutes, against 83% at 2%/0.5% and 96% at 1%/0.25%.
  Midday triggers now span too: 6.8% of 13:00–14:00 triggers and 11.6% of 14:00–15:00
  triggers reach the next session, where at 2%/0.5% those buckets were 0.0% and 1.4%.

| trigger window | 3%/1% n | spans | 2%/0.5% n | spans | 1%/0.25% n | spans |
|---|---|---|---|---|---|---|
| 09:30–10:00 | 1,007 | 0.4% | 1,672 | 0.0% | 3,420 | 0.0% |
| 11:00–12:00 | 450 | 3.3% | 951 | 0.0% | 2,697 | 0.0% |
| 13:00–14:00 | 322 | 6.8% | 656 | 0.0% | 1,851 | 0.0% |
| 14:00–15:00 | 329 | 11.6% | 693 | 1.4% | 1,961 | 0.1% |
| 15:00–15:30 | 178 | 19.7% | 403 | 6.0% | 1,013 | 0.6% |
| **15:30–16:00** | **251** | **66.1%** | **464** | **42.5%** | **1,265** | **25.3%** |

So overnight exposure at 3%/1% is **structural, not an edge effect**: a 3% upswing that
has not yet given back 1% is a genuinely multi-session position, and 8.1% of them are.

### The thresholds do not scale linearly

Going 1% → 2% → 3% on the upswing (with the retreat at a quarter, a quarter, a third):

* Episodes fall **18,166 → 7,014 → 3,575** — roughly halving each step.
* The median wait rises **4 → 6 → 13 min** — flat, then more than doubling.
* Leg B (the retreat itself) rises **2 → 3 → 5 min**, far less than proportionally.

The retreat leg is compressed at the bottom because small retreats are near SOXL's
noise floor. Measured on the same file, the **median absolute 1-minute return is
0.119%**, so 0.25% is 2.1× a typical minute (22.6% of individual minutes clear it
unaided), 0.5% is 4.2× (6.1% of minutes), and 1% is 8.4× (0.9% of minutes). Only at
1% does the retreat threshold clear the noise enough that waiting for one is really
waiting for a move rather than for the next wiggle — which is exactly why leg B finally
grows and why episodes start outliving the session.

## The part that matters for trading

At **all three** thresholds the gap-completed retreats gave back far more than the
threshold: **a median 2.47% / 2.74% / 3.05% below the peak on the first bar back**,
worst 31.5% in every case (2020-03-13 → 03-16). Across a close, none of these is a
level you get filled at — the open prints straight past it, and the give-back you
actually eat is ~2.5–3% regardless of which threshold you set.

What the threshold *does* change is how often you are exposed and for how long.
3%/1% has the fewest weekend episodes per year of the three by count-per-episode
(8.2/yr on 3,575 episodes = 1 in 66) but the longest tail, and it is the only setting
that leaves a position open across two closes or through a whole session.

## By year (market minutes, trigger → retreat)

| year | 3%/1% n | med | p90 | max | spans | 2%/0.5% n | med | p90 | max | spans | 1%/0.25% n | med | p90 | max | spans |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2020 | 623 | 11 | 71 | 474 | 8% | 1,171 | 5 | 27 | 162 | 3% | 2,938 | 3 | 12 | 122 | 2% |
| 2021 | 392 | 20 | 99 | 675 | 10% | 784 | 9 | 38 | 187 | 5% | 2,113 | 5 | 16 | 91 | 3% |
| 2022 | 747 | 11 | 45 | 270 | 5% | 1,458 | 5 | 18 | 114 | 3% | 3,759 | 3 | 9 | 70 | 1% |
| 2023 | 381 | 27 | 113 | 314 | 12% | 792 | 9 | 32 | 191 | 4% | 2,182 | 4 | 13 | 61 | 2% |
| 2024 | 442 | 18 | 83 | 352 | 7% | 886 | 8 | 30 | 101 | 4% | 2,421 | 4 | 13 | 55 | 2% |
| 2025 | 505 | 15 | 82 | 476 | 11% | 990 | 6 | 25 | 185 | 3% | 2,546 | 4 | 13 | 84 | 2% |
| 2026 | 485 | 8 | 52 | 294 | 7% | 932 | 5 | 17 | 103 | 3% | 2,204 | 3 | 10 | 66 | 2% |

The year-to-year ordering is the same at every threshold — 2021 and 2023 are the slow
low-vol grinds, 2022 and 2026 the fast ones — so the ranking is a property of the tape,
not of the threshold.

## Robustness

| variant | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|
| **1-min closes (primary)** | 3,575 · med 13 min · 8.1% span | 7,014 · med 6 min · 3.4% | 18,166 · med 4 min · 1.8% |
| 1-min intrabar (High/Low) | 5,003 · med 5 min · 4.9% | 11,228 · med 1 min · 1.2% | 40,510 · med 1 min · 0.5% |
| 5-min closes (separate file) | 2,205 · med 30 min · 14.1% | 3,945 · med 15 min · 6.8% | 8,467 · med 10 min · 4.8% |

The three disagree exactly as sampling says they must, and none reverses the finding.
Intrabar High/Low is the *earliest-possible* reading and is optimistic: a single 1-min
bar whose High clears the trigger and whose Low is the retreat below that High scores
as a complete 0-minute episode, though the within-bar sequence is unknowable at this
resolution — it degenerates at 1%/0.25%, where the median episode is one bar, and is
most informative at 3%/1%, where it still gives a 5-minute median. 5-min bars cannot
resolve anything faster than 5 minutes and skip the wiggles that end an episode, so
they overstate duration at every threshold. **Closes on 1-min bars are the primary
read: unambiguous, and every level in them is one you could have transacted at.**

## Limitations

* **Regular hours only.** The file is 09:30–15:59; there is no pre/post-market data.
  A retreat that truly occurred at 16:30 is recorded at the next open, so the
  "spans a close" counts are an upper bound on *market-hours* duration and the
  overnight/weekend split is a statement about the RTH session grid. This caveat binds
  hardest at 3%/1%, which has the most spanning episodes.
* **Trades, not quotes**, and closes are bar-end marks — no bid/ask, so nothing here
  is net of spread or slippage. This matters most at 0.25%: a threshold roughly two
  ticks wide on a $100 stock is inside the round-trip cost of acting on it.
* The anchor is a *running trough with no minimum dwell*, so an upswing off a
  one-minute spike low counts the same as one off a multi-day base. That is the
  question as posed; a swing-confirmation filter would cut the episode count and
  lengthen the median.
* Episode boundaries are sequential and non-overlapping: a new upswing is only hunted
  after the prior episode's retreat completes.

## Correctness

`verify.py` re-derives every claim in every ledger straight from `SOXL_1min.csv`
without reusing the state machine — ordering, ledger prices against the file, the
trigger clearing the threshold *and being the first such bar*, the anchor being the
true running trough, the peak being the true running max, the retreat clearing its
threshold *and being the first breach*, both legs summing to the total, market/wall
minutes against the grid, the span labels against the actual dates, and non-overlap.
**3,575 / 3,575, 7,014 / 7,014 and 18,166 / 18,166 pass, 0 failures.**

That check earned its keep. The first engine tested thresholds in floating point and
silently dropped **9 genuine triggers** sitting exactly on +2.000%: `14.00 * 1.02`
evaluates to `14.280000000000001`, so a real move to `14.28` failed `>=`. Every price
in both files is exactly 2 decimals, so the engine carries prices as **integer cents**
and thresholds as **integer basis points**, testing `px*10000 >= trough*(10000+up_bps)`
and `px*10000 <= peak*(10000−dn_bps)`. No tolerance, no boundary class of bug, and any
threshold pair expressible in bps stays exact.

## Output

Files are tagged `up<bps>_dn<bps>` — `up300_dn100` is 3%/1%, `up200_dn50` is 2%/0.5%,
`up100_dn25` is 1%/0.25%.

| file | what |
|---|---|
| `out/retreat_report_<tag>.txt` | full report — primary plus both sensitivities |
| `out/retreat_episodes_1min_<tag>.csv` | every episode: anchor/trigger/peak/retreat stamps and prices, both leg durations on both clocks, run-up, span label, gap flag |
| `out/retreat_episodes_1min_intrabar_<tag>.csv` | same for the intrabar variant |
