# retreat_lab — how long SOXL holds a 2% upswing before giving back 0.5%

```bash
git lfs pull                          # SOXL_1min.csv, SOXL_5min_6Years.csv
python3 retreat_lab/retreat_timing.py # report + episode ledgers -> retreat_lab/out/
python3 retreat_lab/verify.py         # re-checks every episode against the raw bars
```

Stdlib only. Measured from `SOXL_1min.csv` — 1-min OHLCV, **2019-12-31 → 2026-07-30,
642,510 bars, 1,653 sessions**, complete minute grid (zero missing minutes), no OHLC
inconsistencies, split-adjusted (largest overnight moves are real events — COVID
March-2020, 2024-08-05 — not basis breaks). Cross-checked on `SOXL_5min_6Years.csv`.

## The event

1. **Anchor** — the running trough while no episode is open.
2. **Trigger** — first bar ≥ `anchor × 1.02`. This is the *2% upswing*.
3. **Peak** — running maximum from the trigger bar onward.
4. **Retreat** — first bar ≤ `peak × 0.995`. This is the *0.5% retreat*.
   *Leg A* = trigger → peak, *Leg B* = peak → retreat. If the trigger bar is itself
   the peak, Leg A = 0 and the whole wait is Leg B.
5. **Reset** — anchor restarts at the retreat bar; hunt for the next 2% upswing.

Time is reported two ways because the file is regular-hours only: **market minutes**
(tradeable bars elapsed) and **wall-clock minutes** (calendar time, including closed
hours). For an intraday episode they are identical; they diverge only across a close.

## Answer — 7,014 episodes, ~4.2 per session

| leg | median | mean | p90 | p99 | max |
|---|---|---|---|---|---|
| A · 2% trigger → peak | **3 min** | 7.0 | 18 | 64 | 185 |
| B · peak → 0.5% retreat | **3 min** | 4.1 | 9 | 23 | 84 |
| **Total · trigger → retreat** | **6 min** | 11.1 | 26 | 73 | 191 |

All in market minutes. 45.3% resolve within 5 minutes, 68.4% within 10, 92.7% within
30, 98.2% within an hour. **No episode in 6.6 years survived a full session** (worst
was 191 market minutes, about half a session), and none ever crossed more than one
close.

**The 2% line is not where it stops.** In 26.6% of episodes the trigger bar *is* the
peak — the upswing dies the moment it prints 2%. Otherwise it keeps going: median
run-up past the 2% line is 0.40%, p90 1.90%, max 19.9%. The full anchor→peak upswing
runs a median 2.70% (p90 4.79%, max 28.3%).

## Overnight and weekend — 236 of 7,014 (3.4%)

| span | count | share |
|---|---|---|
| intraday (all three stamps in one session) | 6,778 | 96.6% |
| **overnight** (one weeknight close) | **189** | 2.7% |
| **weekend** (Fri → Mon) | **45** | 0.6% |
| **holiday** (a weekday market holiday) | **2** | 0.0% |
| **any close** | **236** | **3.4%** |

Splitting by which leg crossed the bell:

* **129 (1.8%)** had the *retreat itself* cross a close — peaked in one session,
  breached 0.5% in a later one, with the market shut in between (107 overnight,
  20 weekend, 2 holiday). **123 of those breached on the very first bar back.**
* **107 (1.5%)** were still *climbing* into the close and peaked the next session.

**This is a clock artifact, not a market regime.** 197 of the 236 spanning episodes
were triggered in the last 30 minutes of the session — the episode ran out of session,
not out of momentum:

| trigger window | n | median | spans a close | gap completed the retreat |
|---|---|---|---|---|
| 09:30–10:00 | 1,672 | 4 min | 0.0% | 0.0% |
| 11:00–12:00 | 951 | 8 min | 0.0% | 0.0% |
| 14:00–15:00 | 693 | 8 min | 1.4% | 0.3% |
| 15:00–15:30 | 403 | 8 min | 6.0% | 2.7% |
| **15:30–16:00** | **464** | **5 min** | **42.5%** | **23.1%** |

### The part that matters for trading

Those 123 gap-completed retreats did not give back 0.5% — **they gave back a median
2.74% below the peak on the first bar back, worst 31.5%** (2020-03-13 → 03-16). The
0.5% line is not a level you get filled at across a close; it is a level the open
prints straight past. Every one of the 45 weekend episodes is a Friday-late trigger:
carrying an un-exited 2% upswing over a weekend is a distinct, five-times-costlier
event from the intraday case, and it happens ~7 times a year.

## By year (market minutes, trigger → retreat)

| year | n | median | mean | p90 | max | spans a close | weekend |
|---|---|---|---|---|---|---|---|
| 2020 | 1,171 | 5 | 10.8 | 27 | 162 | 34 (3%) | 9 |
| 2021 | 784 | 9 | 16.0 | 38 | 187 | 39 (5%) | 8 |
| 2022 | 1,458 | 5 | 8.1 | 18 | 114 | 40 (3%) | 11 |
| 2023 | 792 | 9 | 14.7 | 32 | 191 | 30 (4%) | 2 |
| 2024 | 886 | 8 | 12.4 | 30 | 101 | 34 (4%) | 5 |
| 2025 | 990 | 6 | 11.2 | 25 | 185 | 32 (3%) | 5 |
| 2026 | 932 | 5 | 8.0 | 17 | 103 | 27 (3%) | 5 |

Stable across six years and both vol regimes. Slower years (2021, 2023) are the
low-vol grinds; 2022 and 2026 are the fast ones.

## Robustness

| variant | episodes | median total | spans a close |
|---|---|---|---|
| **1-min closes (primary)** | 7,014 | 6 min | 3.4% |
| 1-min intrabar (High/Low) | 11,228 | 1 min | 1.2% |
| 5-min closes (separate file, 2020-07→2026-07) | 3,945 | 15 min | 3.4% |

The three disagree exactly as sampling says they must, and none reverses the finding.
Intrabar High/Low is the *earliest-possible* reading and is optimistic: a single 1-min
bar whose High is +2% and whose Low is −0.5% off that High scores as a complete
0-minute episode, though the within-bar sequence is unknowable at this resolution.
5-min bars cannot resolve anything faster than 5 minutes and skip the wiggles that end
an episode, so they overstate duration. **Closes on 1-min bars are the primary read:
unambiguous, and every level in them is one you could actually have transacted at.**

## Limitations

* **Regular hours only.** The file is 09:30–15:59; there is no pre/post-market data.
  A retreat that truly occurred at 16:30 is recorded at the next open, so the 236
  "spans a close" episodes are an upper bound on *market-hours* duration and the
  overnight/weekend split is a statement about the RTH session grid.
* **Trades, not quotes**, and closes are bar-end marks — no bid/ask, so nothing here
  is net of spread or slippage.
* The anchor is a *running trough with no minimum dwell*, so a 2% upswing off a
  one-minute spike low counts the same as one off a multi-day base. That is the
  question as posed; a swing-confirmation filter would cut the episode count and
  lengthen the median.
* Episode boundaries are sequential and non-overlapping: a new 2% upswing is only
  hunted after the prior episode's 0.5% retreat completes.

## Correctness

`verify.py` re-derives every claim in the ledger straight from `SOXL_1min.csv` without
reusing the state machine — ordering, ledger prices against the file, the trigger
being ≥2% *and the first such bar*, the anchor being the true running trough, the peak
being the true running max, the retreat being ≥0.5% *and the first breach*, both legs
summing to the total, market/wall minutes against the grid, the span labels against
the actual dates, and non-overlap. **7,014 / 7,014 pass, 0 failures.**

That check earned its keep. The first engine tested thresholds in floating point and
silently dropped **9 genuine triggers** sitting exactly on +2.000%: `14.00 * 1.02`
evaluates to `14.280000000000001`, so a real move to `14.28` failed `>=`. Every price
in both files is exactly 2 decimals, so the engine now carries prices as **integer
cents** and tests both thresholds as exact integer ratios (102/100 and 995/1000). No
tolerance, no boundary class of bug.

## Output

| file | what |
|---|---|
| `out/retreat_report.txt` | full report — primary plus both sensitivities |
| `out/retreat_episodes_1min.csv` | all 7,014 episodes: anchor/trigger/peak/retreat stamps and prices, both leg durations on both clocks, run-up, span label, gap flag |
| `out/retreat_episodes_1min_intrabar.csv` | same for the intrabar variant |
