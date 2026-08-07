# FAS 1-minute capture — scripts and provenance notes

Three scripts, matching what exists for SOXL:

| script | purpose |
|---|---|
| `fas_1min_fetch.py` | fetch FAS 1-minute RTH bars → `FAS_1min.csv` |
| `fas_1min_verify.py` | validate the result before anything is built on it |
| `fas_1min_selftest.py` | offline tests of the parser, formatter and resume logic |

```bash
pip install -r band_lab/live/requirements.txt   # see Dependencies below
java -jar ThetaTerminalv3.jar                   # in another shell
python3 fas_1min_fetch.py --probe               # confirm the endpoint first
python3 fas_1min_fetch.py                       # resumable; safe to Ctrl-C
python3 fas_1min_verify.py                      # integrity + cross-check
```

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

## What I found about how `SOXL_1min.csv` was actually made

You asked me to review the successful captures first. The answer is not what the
repo's own scripts imply, and it changes the recommendation.

**`band_lab/live/fetch_1min.py` was almost certainly never run.**
`band_lab/live/PHASE2_PARITY.md` says outright: *"Both 1-minute files are in, in
git-lfs, and neither needed a fetch."* The commits that added them (`37bf746`
"1min files", `075d54e` "soxs 1min") add only the CSVs — the one code change in
`37bf746` is a single line in `ibkr_intraday_fetcher.py` flipping `SYMBOL` from
SOXS to VXX, which belongs to the 5-minute VXX file added in the same commit.

**The 1-minute files are not on the same price basis as the 5-minute files.**
This is the important part:

| | `SOXL_5min_6Years.csv` | `SOXL_1min.csv` |
|---|---|---|
| built by | `ibkr_intraday_fetcher.py` (IBKR) | unknown |
| starts | 2020-07-16 at $200.01 | 2019-12-31 at **$17.94** |
| basis | **raw / unadjusted** (per `drift_lab/DATA_NOTES.md`) | **split-adjusted** |

SOXL traded near $269 on 2019-12-31. $269 / 15 = $17.9 — the 1-minute file has
the 2021-03-02 15:1 split already applied. `fas_1min_verify.py` confirms this
mechanically: aggregating `SOXL_1min.csv` to 5 minutes and dividing by
`SOXL_5min_6Years.csv` gives a ratio of exactly 1.0 after 2021-03-02 and 1/15
before it, with the step landing on **2021-03-02 09:30, factor 14.9925**.

So the two files came from different pipelines. The 1-minute data also reaches
2019-12-31, well beyond IBKR's usual 1-minute retention — `fetch_1min.py`'s own
docstring warns it "may not reach 2022".

**Most likely source: ThetaData.** `.env` holds `THETADATA_USERNAME` /
`THETADATA_PASSWORD`, several scripts here use it, and `local_fast_fetch.py`
already talks to the local Theta Terminal REST server directly — deliberately,
with the comment *"Bypasses buggy ThetaClient SDK"*. ThetaData returns
split-adjusted stock bars and has the depth. That is the pattern
`fas_1min_fetch.py` defaults to.

### Corroborated by UVXY_1min.csv

`UVXY_1min.csv` was merged into this branch from `main` after the above was
written, and it fits the same pattern exactly — which strengthens the case:

| | SOXL_1min | SOXS_1min | UVXY_1min |
|---|---|---|---|
| starts | 2019-12-31 | 2019-12-31 | **2019-12-31** |
| sessions | 1,653 | — | 1,654 |
| bars/session | 390 / 210 | — | **390 / 210** |
| split jumps | 0 | 0 | **0** |
| first close | $17.94 | $5,160,020 | **$35,125** |
| volume | integral | fractional | **fractional (68.5692)** |

Three things follow:

1. **All three start on exactly 2019-12-31.** IBKR walking backwards until it
   runs out would give ragged, symbol-specific start dates. An identical start
   across three unrelated tickers is a vendor with a fixed history depth.
2. **Fractional share volume is the decisive tell.** UVXY's first bar reports
   `68.5692` shares. IBKR returns integer share volume for stocks. A value like
   that is raw volume divided by a cumulative split factor — i.e. a feed that
   back-adjusts price *and* volume. UVXY traded near $12 in Dec 2019, not
   $35,125, so the prices are scaled up for its reverse-split history, exactly
   like SOXS.
3. **`check_tws.py`, committed alongside UVXY_1min.csv, does not fetch bars.**
   It connects, qualifies SOXL, prints the conId and NetLiquidation, and
   disconnects — a TWS connectivity smoke test, most likely for the live engine
   in `band_lab/live`, not the capture path.

I am still inferring the specific vendor, not reading it off a log. If you know
which tool produced these, tell me and I will retarget the default — the format
and validation layers are source-independent, so only the fetch function
changes.

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
