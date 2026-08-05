# Instrument screen — choosing candidates worth a transfer test

**Line:** v2.0-dev (DEVELOPMENT). Passing this screen adopts nothing.

`band_lab/transfer_test.py` already runs the **locked** core on a candidate
ETF, settings untouched. It is the validation step and it is not cheap — six
years of 5-minute bars per symbol. This screen is the step *before*: a fast
filter that decides which symbols deserve that run.

## What the strategy actually needs

Not "a volatile stock". `MASTER_STRATEGY_DOCUMENT.md` §9.1 diagnosed the SPXL
failure precisely enough to turn into a test:

> SPXL median range **2.92%** / SOXL **6.67%** = **0.44** scaling factor.
> Rescaling only the *gate* gave **4.5 bp/ON-day** because the 1% dip starved
> cadence to **1.73 trades/day**. Rescaling the *dip* too restored **3.07
> trades/day** and tripled the edge to **14.1 bp** — still a fifth of SOXL's
> 65.6.

So the binding constraint is **churn density**: how often price falls 1% below
the running session high, often enough to feed a 5-trade cap, with each swing
large enough to clear costs. The screen measures that directly — it counts the
actual V1 trigger on real bars rather than using a volatility proxy.

## Criteria, and what each one is anchored to

| # | threshold | why this number |
|---|---|---|
| range ≥ **0.50×** SOXL | SPXL at 0.44× needed every level rescaled and still reached a fifth of SOXL (§9.1). Below half, the locked 1% levels cannot work and a rescaled variant is a different strategy needing its own validation. |
| ≥ **2.5** triggers/day | §9.1 cell B: 1.73 triggers/day produced 4.5 bp. SOXL runs 3.17 fills/day against a cap of 5. |
| gate fires ≥ **25%** of days | The ATR5 ≥ 6% gate is **absolute**, not rescaled (`transfer_test.py` header). A candidate that rarely passes it rarely trades. |
| ≤ **6 bp** commission/round trip | IBKR Fixed is per *share*, so cheap instruments cost more in bp for identical share logic — the V14 T1 derivation, and why SOXS costs 2.86 bp/fill against SOXL's 1.17. Computed from the **most recent** close, never a long-run median: SOXS's file is back-adjusted to $1.07M/share and a median would understate its cost ~6×. |
| ≥ **$15M** median daily volume | $75k per sleeve at ≤0.5% of daily volume. |

## Validation — it reproduces the known answers

Run offline against the six 5-minute files already in the repo:

| symbol | range% | ×SOXL | gate% | trig/day | cost bp | verdict | known outcome |
|---|---:|---:|---:|---:|---:|---|---|
| **SOXS** | 6.79 | 1.02 | 69% | 14.22 | 2.29 | **PASS** | adopted (V14) ✓ |
| **SOXL** | 6.67 | 1.00 | 67% | 13.23 | 0.98 | **PASS** | the core ✓ |
| FAS | 3.69 | 0.55 | 12% | 4.58 | 0.95 | fail — gate 12% | rejected §9 ✓ |
| SPXL | 2.92 | **0.44** | 8% | 4.41 | 0.72 | fail — range, gate | rejected §9 ✓ |
| VXX | 3.93 | 0.59 | 22% | 8.08 | 4.85 | fail — gate 22% | never adopted ✓ |
| SOXX | 2.22 | 0.33 | 1% | 1.80 | 0.53 | fail — all three | unlevered index ✓ |

Three documented figures reproduced independently — **SOXL 6.67%, SPXL 2.92%,
and the 0.44 ratio** all match §9.1 exactly — and **all four known verdicts
come out right**. The screen was calibrated against outcomes that were already
decided, before being pointed at anything new.

VXX is the near miss worth noting: it clears range and cadence and fails only
the gate (22% vs 25%), but its 4.85 bp cost is the second worst here and it is
a volatility product with structural decay very different from a leveraged
equity ETF. It is not a free candidate.

## Running it

```bash
# offline — screens every <SYM>_5min_6Years.csv in the repo
python3 band_lab/v2_dev/instrument_screen.py

# with IBKR (TWS running, read-only)
python3 band_lab/v2_dev/instrument_screen.py --ib --universe
python3 band_lab/v2_dev/instrument_screen.py --ib --symbols TQQQ,TNA,LABU,GDXU
```

The IB path fetches 250 sessions of 5-minute RTH bars per symbol in 30-day
slices (§6.4, duration limits, is still unverified — the request is
deliberately small rather than clever), connects **read-only**, and applies
the identical scoring code as the offline path. `DEFAULT_UNIVERSE` is a
starting list of US-listed leveraged ETFs to edit, not a claim about what
exists.

## What the screen deliberately does not do

- **It does not measure the spread.** `phase1/COST_MODEL.md` §4 (G3): the
  repository holds no quote data. The IB path could add a snapshot quote, but
  one snapshot is not a spread distribution — that needs the paper run.
- **It does not measure sleeve correlation.** The `inst corr` column is the
  correlation of the *instruments'* daily returns. V14's "−0.70 correlated
  SOXS sleeve" is the correlation of the two *strategies'* daily P&L, a
  different and smaller number that only exists once a transfer test has run.
- **It does not adopt anything.** A PASS earns a `transfer_test.py` run.
  Adoption needs a prespecified protocol (`V14_PAIR_PROTOCOL.md` is the
  template) and, per `IMPLEMENTATION_SPEC.md` §11, a deliberate documented
  decision.

## Honest expectation

SOXL and SOXS are 3× semiconductor ETFs, the most volatile liquid US equity
products in normal conditions. The screen's own numbers show why nothing else
in the repo comes close: the next best candidate has 55% of SOXL's range and
fires the gate on 12% of days against SOXL's 67%. A new candidate would need
to be a 3× ETF on a sector at least as volatile as semis. That set is small,
and §9 already tested the obvious members.
