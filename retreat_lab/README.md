# retreat_lab — how long SOXL holds an upswing before giving it back

```bash
git lfs pull                                # SOXL_1min.csv, SOXL_5min_6Years.csv
python3 retreat_lab/retreat_timing.py       # both configs -> retreat_lab/out/
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

## Answer — both thresholds

| | **2% up / 0.5% back** | **1% up / 0.25% back** |
|---|---|---|
| episodes | 7,014 (4.2 / session) | 18,166 (11.0 / session) |
| Leg A · trigger → peak | median **3 min** | median **1 min** |
| Leg B · peak → retreat | median **3 min** | median **2 min** |
| **Total · trigger → retreat** | median **6 min** | median **4 min** |
| mean / p90 / p99 / max | 11.1 / 26 / 73 / 191 | 5.6 / 12 / 32 / 122 |
| resolved ≤ 5 min | 45.3% | 67.6% |
| resolved ≤ 15 min | 79.4% | 94.0% |
| resolved ≤ 30 min | 92.7% | 98.9% |
| peak *is* the trigger bar | 26.6% | 34.6% |
| run-up past the line | med 0.40%, p90 1.90%, max 19.9% | med 0.22%, p90 1.32%, max 18.8% |
| full upswing anchor → peak | med 2.70%, p90 4.79%, max 28.3% | med 1.45%, p90 2.81%, max 26.0% |
| **spans a close** | **236 (3.4%)** | **332 (1.8%)** |
| — overnight / weekend / holiday | 189 / 45 / 2 | 267 / 60 / 5 |
| retreat itself crossed the gap | 129 (1.8%) | 169 (0.9%) |
| — of those, breached on first bar back | 123 | 164 |
| give-back on that first bar back | med **2.74%**, max 31.5% | med **2.47%**, max 31.5% |

All durations in market minutes. **Neither threshold ever produced an episode that
survived a full session** (worst 191 and 122 minutes), and **no episode at either
threshold ever crossed more than one close.**

### Halving both thresholds does not halve the wait

7,014 → 18,166 episodes (2.6×), but the median wait only drops 6 → 4 minutes, and
**Leg B barely moves at all: 3 → 2 minutes.** The retreat leg is near its floor
because 0.25% is not a meaningful move for this instrument at 1-minute resolution.
Measured on the same file, the median absolute 1-minute return is **0.119%**, so:

* **0.25% is 2.1× a median minute — 22.6% of individual minutes clear it on their own.**
* 0.5% is 4.2× a median minute — 6.1% of minutes clear it on their own.

At 0.25% you are not measuring a retreat, you are measuring how long until any wiggle
shows up: roughly one to two bars, almost regardless of what preceded it. What the
tighter threshold really buys is **more, shorter episodes**, not earlier warning
inside a given one. The leg that actually responds to the threshold is Leg A, the
run-up (3 → 1 min), because a 1% trigger fires earlier in a move that a 2% trigger
would have caught later.

## Overnight and weekend

Same shape at both thresholds, and it is **a clock artifact, not a market regime** —
83% (2%/0.5%) and 96% (1%/0.25%) of all spanning episodes were triggered in the last
30 minutes of the session. The episode ran out of session, not out of momentum:

| trigger window | 2%/0.5% n | spans close | 1%/0.25% n | spans close |
|---|---|---|---|---|
| 09:30–10:00 | 1,672 | 0.0% | 3,420 | 0.0% |
| 11:00–12:00 | 951 | 0.0% | 2,697 | 0.0% |
| 14:00–15:00 | 693 | 1.4% | 1,961 | 0.1% |
| 15:00–15:30 | 403 | 6.0% | 1,013 | 0.6% |
| **15:30–16:00** | **464** | **42.5%** | **1,265** | **25.3%** |

The tighter threshold spans a close *less* often (1.8% vs 3.4%) precisely because it
resolves faster — fewer episodes are still open when the bell rings.

### The part that matters for trading

At both thresholds the gap-completed retreats did not give back the threshold — **they
gave back a median 2.47–2.74% below the peak on the first bar back, worst 31.5%**
(2020-03-13 → 03-16). Tightening the retreat from 0.5% to 0.25% does not help here:
across a close neither is a level you get filled at, and the give-back you actually
eat is the same ~2.5% either way. It only makes the exposure more frequent — 60
weekend episodes instead of 45 (9.1/yr vs 6.8/yr), every one of them a Friday-late
trigger.

## By year (market minutes, trigger → retreat)

| year | 2%/0.5% n | med | p90 | max | spans | 1%/0.25% n | med | p90 | max | spans |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020 | 1,171 | 5 | 27 | 162 | 3% | 2,938 | 3 | 12 | 122 | 2% |
| 2021 | 784 | 9 | 38 | 187 | 5% | 2,113 | 5 | 16 | 91 | 3% |
| 2022 | 1,458 | 5 | 18 | 114 | 3% | 3,759 | 3 | 9 | 70 | 1% |
| 2023 | 792 | 9 | 32 | 191 | 4% | 2,182 | 4 | 13 | 61 | 2% |
| 2024 | 886 | 8 | 30 | 101 | 4% | 2,421 | 4 | 13 | 55 | 2% |
| 2025 | 990 | 6 | 25 | 185 | 3% | 2,546 | 4 | 13 | 84 | 2% |
| 2026 | 932 | 5 | 17 | 103 | 3% | 2,204 | 3 | 10 | 66 | 2% |

Stable across six years and both vol regimes at both thresholds. Slower years (2021,
2023) are the low-vol grinds; 2022 and 2026 are the fast ones.

## Robustness

| variant | 2%/0.5% | 1%/0.25% |
|---|---|---|
| **1-min closes (primary)** | 7,014 · med 6 min · 3.4% span | 18,166 · med 4 min · 1.8% span |
| 1-min intrabar (High/Low) | 11,228 · med 1 min · 1.2% | 40,510 · med 1 min · 0.5% |
| 5-min closes (separate file) | 3,945 · med 15 min · 6.8% | 8,467 · med 10 min · 4.8% |

The three disagree exactly as sampling says they must, and none reverses the finding.
Intrabar High/Low is the *earliest-possible* reading and is optimistic: a single 1-min
bar whose High clears the trigger and whose Low is the retreat below that High scores
as a complete 0-minute episode, though the within-bar sequence is unknowable at this
resolution — and it degenerates at 1%/0.25%, where the median episode is one bar.
5-min bars cannot resolve anything faster than 5 minutes and skip the wiggles that end
an episode, so they overstate duration; that bites harder at 0.25%, whose true median
Leg B (2 min) is below their resolution entirely. **Closes on 1-min bars are the
primary read: unambiguous, and every level in them is one you could have transacted
at.**

## Limitations

* **Regular hours only.** The file is 09:30–15:59; there is no pre/post-market data.
  A retreat that truly occurred at 16:30 is recorded at the next open, so the
  "spans a close" counts are an upper bound on *market-hours* duration and the
  overnight/weekend split is a statement about the RTH session grid.
* **Trades, not quotes**, and closes are bar-end marks — no bid/ask, so nothing here
  is net of spread or slippage. This matters much more at 0.25%: a threshold roughly
  two ticks wide on a $100 stock is inside the round-trip cost of acting on it.
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
**7,014 / 7,014 and 18,166 / 18,166 pass, 0 failures.**

That check earned its keep. The first engine tested thresholds in floating point and
silently dropped **9 genuine triggers** sitting exactly on +2.000%: `14.00 * 1.02`
evaluates to `14.280000000000001`, so a real move to `14.28` failed `>=`. Every price
in both files is exactly 2 decimals, so the engine carries prices as **integer cents**
and thresholds as **integer basis points**, testing `px*10000 >= trough*(10000+up_bps)`
and `px*10000 <= peak*(10000−dn_bps)`. No tolerance, no boundary class of bug, and any
threshold pair expressible in bps stays exact.

## Output

Files are tagged `up<bps>_dn<bps>` — `up200_dn50` is 2%/0.5%, `up100_dn25` is 1%/0.25%.

| file | what |
|---|---|
| `out/retreat_report_<tag>.txt` | full report — primary plus both sensitivities |
| `out/retreat_episodes_1min_<tag>.csv` | every episode: anchor/trigger/peak/retreat stamps and prices, both leg durations on both clocks, run-up, span label, gap flag |
| `out/retreat_episodes_1min_intrabar_<tag>.csv` | same for the intrabar variant |
