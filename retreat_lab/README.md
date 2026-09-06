# retreat_lab — how long SOXL holds an upswing before giving it back

```bash
git lfs pull                                # SOXL_1min.csv, SOXL_5min_6Years.csv
python3 retreat_lab/retreat_timing.py       # all four configs -> retreat_lab/out/
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

## Answer — all four thresholds

| | **4% / 1.5%** | **3% / 1%** | **2% / 0.5%** | **1% / 0.25%** |
|---|---|---|---|---|
| up : down ratio | 2.67 : 1 | 3 : 1 | 4 : 1 | 4 : 1 |
| episodes | 2,197 (1.3 / session) | 3,575 (2.2) | 7,014 (4.2) | 18,166 (11.0) |
| Leg A · trigger → peak | median **11 min** | **6 min** | **3 min** | **1 min** |
| Leg B · peak → retreat | median **9 min** | **5 min** | **3 min** | **2 min** |
| **Total · trigger → retreat** | median **26 min** | **13 min** | **6 min** | **4 min** |
| mean / p90 / p99 / max | 57.9 / 158 / 386 / 908 | 30.4 / 75 / 253 / 675 | 11.1 / 26 / 73 / 191 | 5.6 / 12 / 32 / 122 |
| resolved ≤ 5 min | 14.2% | 23.9% | 45.3% | 67.6% |
| resolved ≤ 15 min | 36.4% | 54.2% | 79.4% | 94.0% |
| resolved ≤ 30 min | 54.3% | 71.9% | 92.7% | 98.9% |
| resolved ≤ 60 min | 72.5% | 86.7% | 98.2% | 99.9% |
| **survived a full session** | **20** | **4** | 0 | 0 |
| **survived two sessions** | **2** | 0 | 0 | 0 |
| longest | **908 min (2.3 sessions)** | 675 (1.7) | 191 (0.5) | 122 (0.3) |
| peak *is* the trigger bar | 14.8% | 19.3% | 26.6% | 34.6% |
| run-up past the line | med 1.22%, p90 4.91% | 0.73%, 3.43% | 0.40%, 1.90% | 0.22%, 1.32% |
| full upswing anchor → peak | med 5.76%, p90 10.53% | 4.22%, 7.75% | 2.70%, 4.79% | 1.45%, 2.81% |
| **spans a close** | **309 (14.1%)** | **291 (8.1%)** | **236 (3.4%)** | **332 (1.8%)** |
| — overnight / weekend / holiday | 246 / 60 / 3 | 234 / 54 / 3 | 189 / 45 / 2 | 267 / 60 / 5 |
| — max closes one episode crossed | **2** (4 episodes) | **2** (1 episode) | 1 | 1 |
| — of spanning, triggered 15:30–16:00 | **34%** | 57% | 83% | 96% |
| retreat itself crossed the gap | 134 (6.1%) | 139 (3.9%) | 129 (1.8%) | 169 (0.9%) |
| — breached on first bar back | 108 (4.9%) | 122 (3.4%) | 123 (1.8%) | 164 (0.9%) |
| give-back on that first bar back | med **3.59%** | **3.05%** | **2.74%** | **2.47%** |
| weekend episodes per year | 9.1 | 8.2 | 6.8 | 9.1 |

All durations in market minutes; max give-back is 31.5% at every threshold (the same
event, 2020-03-13 → 03-16). The ratios differ across configs — 4:1, 4:1, 3:1, 2.67:1 —
so this is not a clean scaling of one shape: as the upswing grows the retreat is
proportionally deeper too.

## There is a crossover between 2% and 3%

Every column above moves monotonically, and the change is not just "bigger threshold,
longer wait." It is a change in **what kind of event this is**.

**At 1% and 2% it is an intraday noise event.** Median 4–6 minutes, 93–99% resolved
inside half an hour, nothing ever survived a session, nothing ever crossed more than
one close. The handful that spanned a close did so almost entirely because the bell
arrived first: 96% and 83% of those were triggered in the final 30 minutes.

**At 3% and 4% it is a multi-session position.** At 4%/1.5% the median is 26 minutes
but **45.7% are still open after half an hour and 27.5% after a full hour**; 20
episodes survived a whole session, 2 survived two, and the longest ran 908 market
minutes — triggered 2021-10-18 11:00, peaked 2021-10-20 10:34 after a 6.2% run-up,
broke 1.5% at 13:08. Four episodes crossed two closes.

The clearest single indicator is where the spanning episodes come from:

| trigger window | 4%/1.5% spans | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|
| 09:30–10:00 | **3.2%** | 0.4% | 0.0% | 0.0% |
| 11:00–12:00 | **8.5%** | 3.3% | 0.0% | 0.0% |
| 13:00–14:00 | **21.3%** | 6.8% | 0.0% | 0.0% |
| 14:00–15:00 | **20.7%** | 11.6% | 1.4% | 0.1% |
| 15:00–15:30 | **43.3%** | 19.7% | 6.0% | 0.6% |
| 15:30–16:00 | 77.4% | 66.1% | 42.5% | 25.3% |
| *share of all spanning episodes triggered 15:30–16:00* | **34%** | 57% | 83% | 96% |

At 4%/1.5% even a **9:30 trigger spans a close 3.2% of the time**, and a 1pm trigger
does so 21.3% of the time. Overnight risk is no longer an artifact of running out of
session — it is the normal life of the position.

## The thresholds do not scale linearly

Going 1% → 2% → 3% → 4% on the upswing:

* Episodes fall **18,166 → 7,014 → 3,575 → 2,197** — halving, halving, then only −39%.
* The median wait rises **4 → 6 → 13 → 26 min** — flat, then doubling each step.
* Leg B (the retreat itself) rises **2 → 3 → 5 → 9 min**.

The retreat leg is compressed at the bottom because small retreats sit near SOXL's
noise floor. Measured on the same file, the **median absolute 1-minute return is
0.119%**, so 0.25% is 2.1× a typical minute (22.6% of individual minutes clear it
unaided), 0.5% is 4.2× (6.1%), 1% is 8.4× (0.9%), and 1.5% is 12.6× (0.2%). A 0.25%
"retreat" is really just the next wiggle; a 1.5% one is a move you have to wait for.

## The part that matters for trading

At **every** threshold the gap-completed retreats gave back far more than the
threshold — **median 2.47% / 2.74% / 3.05% / 3.59% below the peak on the first bar
back**, worst 31.5% in all four. Across a close, none of these is a level you get
filled at; the open prints straight past it. Setting a wider retreat does not protect
you there, and setting a tighter one does not help either — you eat ~2.5–3.6% either
way.

What the threshold changes is **how much overnight exposure you sign up for**:
1.8% → 3.4% → 8.1% → **14.1%** of episodes span a close. At 4%/1.5% roughly one
episode in seven is carried through a close, one in sixteen has its retreat completed
by a gap you cannot trade, and 60 of them (9.1/yr) run over a weekend.

## By year — median market minutes (and % spanning a close)

| year | 4%/1.5% | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|
| 2020 | 19 (15%) | 11 (8%) | 5 (3%) | 3 (2%) |
| 2021 | 44 (22%) | 20 (10%) | 9 (5%) | 5 (3%) |
| 2022 | 20 (11%) | 11 (5%) | 5 (3%) | 3 (1%) |
| 2023 | 56 (20%) | 27 (12%) | 9 (4%) | 4 (2%) |
| 2024 | 30 (12%) | 18 (7%) | 8 (4%) | 4 (2%) |
| 2025 | 27 (12%) | 15 (11%) | 6 (3%) | 4 (2%) |
| 2026 | 16 (10%) | 8 (7%) | 5 (3%) | 3 (2%) |

The year ordering is identical at every threshold — 2021 and 2023 are the slow low-vol
grinds, 2022 and 2026 the fast ones — so the ranking is a property of the tape, not of
the threshold. Full per-year n / mean / p90 / max are in each report file.

## Robustness

| variant | 4%/1.5% | 3%/1% | 2%/0.5% | 1%/0.25% |
|---|---|---|---|---|
| **1-min closes (primary)** | 2,197 · med 26 min · 14.1% span | 3,575 · 13 min · 8.1% | 7,014 · 6 min · 3.4% | 18,166 · 4 min · 1.8% |
| 1-min intrabar (High/Low) | 2,880 · 12 min · 9.8% | 5,003 · 5 min · 4.9% | 11,228 · 1 min · 1.2% | 40,510 · 1 min · 0.5% |
| 5-min closes (separate file) | 1,450 · 55 min · 21.4% | 2,205 · 30 min · 14.1% | 3,945 · 15 min · 6.8% | 8,467 · 10 min · 4.8% |

The three disagree exactly as sampling says they must, and none reverses the finding
at any threshold. Intrabar High/Low is the *earliest-possible* reading and is
optimistic: a single 1-min bar whose High clears the trigger and whose Low is the
retreat below that High scores as a complete 0-minute episode, though the within-bar
sequence is unknowable at this resolution — it degenerates at 1%/0.25%, where the
median episode is one bar, and is most informative at 4%/1.5%, where it still gives a
12-minute median. 5-min bars cannot resolve anything faster than 5 minutes and skip
the wiggles that end an episode, so they overstate duration everywhere. **Closes on
1-min bars are the primary read: unambiguous, and every level in them is one you could
have transacted at.**

## Limitations

* **Regular hours only.** The file is 09:30–15:59; there is no pre/post-market data.
  A retreat that truly occurred at 16:30 is recorded at the next open, so the
  "spans a close" counts are an upper bound on *market-hours* duration and the
  overnight/weekend split is a statement about the RTH session grid. **This caveat
  binds hardest at 4%/1.5%**, where 14.1% of episodes span a close — the wider the
  threshold, the more of the answer depends on hours this file cannot see.
* **Trades, not quotes**, and closes are bar-end marks — no bid/ask, so nothing here
  is net of spread or slippage. That matters most at 0.25%: a threshold roughly two
  ticks wide on a $100 stock is inside the round-trip cost of acting on it.
* The anchor is a *running trough with no minimum dwell*, so an upswing off a
  one-minute spike low counts the same as one off a multi-day base. That is the
  question as posed; a swing-confirmation filter would cut the episode count and
  lengthen the median.
* Episode boundaries are sequential and non-overlapping: a new upswing is only hunted
  after the prior episode's retreat completes. At 4%/1.5% episodes are long enough
  that this materially reduces the count — the tape spends a real share of its time
  inside an open episode.

## Correctness

`verify.py` re-derives every claim in every ledger straight from `SOXL_1min.csv`
without reusing the state machine — ordering, ledger prices against the file, the
trigger clearing the threshold *and being the first such bar*, the anchor being the
true running trough, the peak being the true running max, the retreat clearing its
threshold *and being the first breach*, both legs summing to the total, market/wall
minutes against the grid, the span labels against the actual dates, and non-overlap.
**2,197 / 2,197, 3,575 / 3,575, 7,014 / 7,014 and 18,166 / 18,166 pass, 0 failures.**

That check earned its keep. The first engine tested thresholds in floating point and
silently dropped **9 genuine triggers** sitting exactly on +2.000%: `14.00 * 1.02`
evaluates to `14.280000000000001`, so a real move to `14.28` failed `>=`. Every price
in both files is exactly 2 decimals, so the engine carries prices as **integer cents**
and thresholds as **integer basis points**, testing `px*10000 >= trough*(10000+up_bps)`
and `px*10000 <= peak*(10000−dn_bps)`. No tolerance, no boundary class of bug, and any
threshold pair expressible in bps stays exact — 1.5% is 150 bps, not 0.015.

## Output

Files are tagged `up<bps>_dn<bps>` — `up400_dn150` is 4%/1.5%, `up300_dn100` is 3%/1%,
`up200_dn50` is 2%/0.5%, `up100_dn25` is 1%/0.25%.

| file | what |
|---|---|
| `out/retreat_report_<tag>.txt` | full report — primary plus both sensitivities |
| `out/retreat_episodes_1min_<tag>.csv` | every episode: anchor/trigger/peak/retreat stamps and prices, both leg durations on both clocks, run-up, span label, gap flag |
| `out/retreat_episodes_1min_intrabar_<tag>.csv` | same for the intrabar variant |
