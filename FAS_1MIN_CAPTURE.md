# FAS 1-minute capture — scripts and provenance notes

Three scripts, matching what exists for SOXL:

| script | purpose |
|---|---|
| `fas_1min_fetch.py` | fetch FAS 1-minute RTH bars → `FAS_1min.csv` |
| `fas_1min_verify.py` | validate the result before anything is built on it |
| `fas_1min_selftest.py` | offline tests of the parser, formatter and resume logic |

```bash
# IBKR is the default source, matching the 5-minute ETF files.
# Start TWS/Gateway first (paper port 7497), then:
python3 check_tws.py                                 # connectivity smoke test
python3 fas_1min_fetch.py --duration "1 W" --normalize-splits   # resumable
python3 fas_1min_verify.py                           # integrity + cross-check

# ThetaData remains available if IBKR's 1-minute depth falls short:
#   pip install -r band_lab/live/requirements.txt
#   java -jar ThetaTerminalv3.jar
#   python3 fas_1min_fetch.py --source theta --probe
```

## Known failures fixed after first live run

Two things broke on the first real run against TWS. Both are fixed and covered
by `fas_1min_selftest.py` (34/34 passing).

**1. `ModuleNotFoundError: No module named 'requests'`** — see Dependencies below.

**2. `TypeError: can't compare offset-naive and offset-aware datetimes`**, after
the first session came back cleanly (`20260807: +390 bars`). `ib_async` returns
a timezone-**aware** datetime for intraday bars; my code only stripped a literal
`" America/New_York"` *string* suffix, so the tzinfo survived into the loop
cursor and the backwards-walk comparison blew up on the second iteration.

Fixed with a single `bar_datetime()` funnel that normalizes every shape
ib_async can return — tz-aware datetime, naive datetime, `date`, and the string
forms — to naive New York wall-clock time, plus a defensive tz-strip on the
DataFrame column. A UTC-stamped bar is *converted* to New York rather than
merely stripped, which the tests check explicitly.

The 390-bar first session is worth noting on its own: **IBKR's grid matches the
`SOXL_1min.csv` spec exactly** (390 bars, 09:30–15:59), so the format assumption
was right.

**Speed.** The `1 D` default is one session per request: ~1,650 requests at 11s
pacing is roughly 5 hours. `--duration "1 W"` is about 5x faster and generally
works for 1-minute bars. Resume is safe, so interrupting costs at most one chunk.

## Dependencies

`.venv-live` is built from `band_lab/live/requirements.txt`, which listed
pandas, numpy, pytest, ib_async and tzdata — but **not `requests`**, so the
first run of `--probe` died with `ModuleNotFoundError: No module named
'requests'`. `local_fast_fetch.py` had the same latent dependency and would
have failed the same way.

Fixed two ways:

- `requests>=2.31` is now listed in `band_lab/live/requirements.txt`.
- `fas_1min_fetch.py` imports it softly. The ThetaData path needs it; the IBKR
  path (ib_async) and `fas_1min_selftest.py` do not, so those still run without
  it, and the Theta path prints an install instruction and exits 1 rather than
  throwing a traceback:

```
[!] the ThetaData path needs the 'requests' package, which is not installed...
    Install it:  python3 -m pip install requests
    Or use the broker instead:  --source ibkr
```

Quick fix if you just want to get going: `pip install requests`.

---

## Source: IBKR — correcting an earlier claim

**An earlier version of this document argued the 1-minute files came from
ThetaData rather than IBKR. That was wrong, and the reasoning was wrong.**

The claim rested on three things: the files are split-adjusted while the 5-minute
files are raw; all three start on exactly 2019-12-31; and UVXY reports fractional
share volume (68.5692), which I asserted "cannot come from IBKR". That last point
is simply false — IBKR split-adjusts volume as well as price. UVXY's cumulative
reverse-split factor is roughly 2,900x, so 68.5692 x 2,900 is about 200,000
shares, an ordinary opening minute. The identical start dates are equally well
explained by the same `--start` being passed each time.

The decisive evidence is that the two SOXL files are the *same data*:

| | 2021-02-26 | 2021-03-01 | 2021-03-02 | 2021-03-03 |
|---|---|---|---|---|
| `SOXL_5min_6Years.csv` (IBKR) | 579.77 | **636.49** | 38.55 | 34.98 |
| `SOXL_1min.csv` | 38.65 | **42.43** | 38.55 | 34.98 |

Identical after the 2021-03-02 split, and exactly 15x apart before it
(636.49 / 15 = 42.43). One vendor, one dataset, two adjustment anchors.

IBKR adjusts historical bars for corporate actions relative to each request's
`endDateTime`, not to today. `ibkr_intraday_fetcher.py` walks backwards in
one-week chunks with `endDateTime` in the past, so pre-split chunks come back on
the basis that was current then — which is precisely the visible 15:1 jump
`drift_lab/DATA_NOTES.md` records. A fetch anchored differently returns the same
data already adjusted. **The basis is a property of how the fetch was chunked,
not of who supplied the data.**

So: `--source ibkr` is now the default, matching the 5-minute ETF files.
ThetaData remains available as `--source theta` but is no longer the assumption.

## Getting a consistent basis, deliberately

Since the anchor depends on chunking, the script no longer leaves it to chance.
`--normalize-splits` re-anchors the finished file onto its most recent split era:
it finds overnight jumps outside [0.60, 1.70], snaps each to a clean split factor
(the observed ratio also contains that night's real price move, so it never lands
exactly on 1/15), multiplies earlier prices by the factor and divides earlier
volumes by it, preserving notional.

**Validated against the known-good pair.** Running the normalizer on the raw
`SOXL_5min_6Years.csv` and comparing against `SOXL_1min.csv` aggregated to five
minutes, over all 117,348 overlapping bars:

```
  2021-03-02: observed ratio 0.0675 -> snapped to 0.066667 (1-for-15)

  close ratio: median 1.000000   min 0.999639   max 1.000350
  pre-split  bars  12,174: ratio median 1.000000
  post-split bars 105,174: ratio median 1.000000
  max |ratio-1| across ALL bars: 0.000361
  volume ratio: median 1.000000  (pre-split median 1.000000)
```

The normalizer turns the raw IBKR basis into exactly the `SOXL_1min.csv`
convention, to within 0.036% — residual rounding from two-decimal source prices
divided by 15.

### Which basis to pick

The repo already contains both conventions, and `band_lab/live/intrabar.py` has a
`needs_split_adjustment()` heuristic that exists solely to paper over the
mismatch. Two defensible choices:

- **Match the other 1-minute files** (`--normalize-splits`): `FAS_1min.csv` lines
  up with `SOXL_1min.csv`, `SOXS_1min.csv` and `UVXY_1min.csv`, which is what any
  cross-sectional 1-minute work needs. **Recommended** — a 1-minute file's job is
  to sit alongside the other 1-minute files.
- **Match the 5-minute files** (omit the flag): raw, era-relative, consistent with
  `FAS_5min_6Years.csv`, and split adjustment stays a read-time concern.

Either way the verifier reports which basis you ended up on, so it is never a
silent property.

## The exact spec being matched

Measured from `SOXL_1min.csv`, not assumed:

- `Date,Open,High,Low,Close,Volume`, timestamps `YYYYMMDD HH:MM:SS America/New_York`
- 642,510 rows across 1,653 sessions, 2019-12-31 → 2026-07-30
- **390 bars per full session, 09:30 through 15:59** — the 16:00 stamp is absent
- 210 bars on the 12 early-close half-days (09:30 → 12:59)
- RTH only; zero duplicate timestamps; zero NaN; zero OHLC violations
- volume written as float, values integral; 8,080 zero-volume bars (1.26%)

Note this differs from the 5-minute grid, which is 78 bars ending at **15:55**.
390 = 78 × 5 exactly, so 1-minute bars aggregate cleanly onto the 5-minute grid —
which is what makes the cross-check in step 5 of the verifier possible.

`--start` defaults to **2019-12-31** to match SOXL rather than to "today minus
six years", so the two files line up. Use `--years 6` if you want the literal
six-year window instead.

## Validation

`fas_1min_verify.py` runs six checks; the fifth is the one that matters.

It aggregates the new 1-minute file up to 5 minutes and compares it against the
existing `FAS_5min_6Years.csv` over the ~6-year overlap. Two independently
sourced captures of the same instrument agreeing bar-for-bar is much stronger
evidence than any internal consistency check.

**I validated the verifier itself against the known-good SOXL pair:**

```
overlapping 5-minute bars: 117,348
|5-min return difference|: median 0.0000 bp, p95 1.2502 bp, max 7.01 bp
bars differing by more than 25 bp: 0 (0.000%)
volume ratio: median 1.0000
sessions missing from the 1-min file within the overlap: 0
```

Returns are compared rather than price levels, so the check is unaffected by the
split-basis difference — and the basis difference is separately detected and
reported with its date and factor.

Run `python3 fas_1min_verify.py --symbol SOXL` to reproduce that.

## What to watch for with FAS specifically

**Splits between 2019-12-31 and 2020-07-23 are unverified.** My earlier
integrity scan found zero split discontinuities in `FAS_5min_6Years.csv`, but
that file only starts 2020-07-23. The requested window reaches back through the
COVID crash, when Direxion reverse-split a number of its leveraged funds. I am
not going to assert FAS's corporate-action history from memory — the verifier's
step 4 scans for it and will name the date and factor if one is there. If it
finds one, add it to `SPLIT_ADJUSTMENTS` in `band_lab/live/replay.py`, which
currently contains only SOXL.

**FAS is the thin one.** From the earlier liquidity work: median 5-minute bar
notional of $528K against SPXL's $3.76M, and 348 zero-volume 5-minute bars
versus SPXL's 22. Expect materially more zero-volume 1-minute bars than SOXL's
1.26%, especially in 2020. That is real, not a capture defect — but if the rate
is very high, per-minute fill assumptions built on this file need care.

**Expect a volume mismatch if FAS turns out to be split-adjusted.** If FAS had
a corporate action before 2020-07-23 and the 1-minute feed back-adjusts like
SOXS and UVXY, then its volume will be scaled too, while `FAS_5min_6Years.csv`
carries raw share counts. Step 5 of the verifier compares the two and will warn
that "volume differs materially". On this evidence that is expected behaviour,
not a defect — the return comparison in the same step is the check that decides
whether the capture is sound.

**Two sources in one file is a trap.** If you fetch part of the range from Theta
and part from IBKR, you can end up with a split-basis seam mid-file. The verifier
would catch it as a basis change, but it is easier not to create one: pick a
source, and if you must mix, verify immediately.

## What I could and could not test

**Tested offline, 19/19 passing (`fas_1min_selftest.py`):** the Theta response
parser against a payload with deliberately shuffled header order (it maps
columns by name, not position), pre-market and all-zero padding rows being
dropped, byte-exact CSV output against the real SOXL reference line, and
merge/resume behaviour — dedupe on re-fetch, out-of-order chunks sorting
correctly, corrected bars overwriting stale ones, atomic replace leaving no
partial file.

**Not tested — no live source reachable from here:** the Theta HTTP endpoint
path and its pagination header, and the IBKR/TWS connection. The exact Theta
stock-OHLC route is the one thing I could not confirm, which is why `--probe`
exists: it tries both `/v2/hist/stock/ohlc` and `/v3/hist/stock/ohlc`, prints
the raw payload, and tells you which one works. **Run it before the full pull.**
If the payload shape differs from what the parser expects, it maps by name from
the response's own header, so it should adapt; if it cannot, it raises rather
than silently guessing column positions.

## One thing to fix separately

`collect_options_data.py` and `soxl_historical.py` contain a **ThetaData email
and password in plaintext**, committed to the repository. The same credentials
are in `.env`. Since they are already in git history, rotating the password is
the only real remedy; after that, have those scripts read from the environment
the way the new ones do. I have not touched those files — flagging, not
fixing, since it is outside what you asked for.
