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

---

## Addendum — throttling for lower-volatility instruments, and currencies

Two follow-up questions. Both have partial answers already in the record.

### 1. "Can the triggers be throttled for less return on lower-vol instruments?"

**Yes, and it was tested — `MASTER_STRATEGY_DOCUMENT.md` §9.1 is exactly this
experiment.** SPXL, scaled by its own range ratio (2.92% / 6.67% = 0.44):

| cell | gate | dip/tgt | ON days | trades/day | bp/ON-day | Sharpe | maxDD |
|---|---:|---:|---:|---:|---:|---:|---:|
| A — locked, unscaled | 6.00 | 1.0% | 63 | 2.84 | 30.5 | 1.34 | −17.0% |
| B — gate scaled only | 2.94 | 1.0% | 549 | **1.73** | **4.5** | 0.33 | −31.1% |
| **C — gate + dip scaled** | 2.94 | **0.5%** | 549 | **3.07** | **14.1** | 1.03 | −25.4% |
| D — fully scaled (stop 2%) | 2.94 | 0.5% | 549 | 3.31 | 12.9 | 1.05 | −25.4% |
| SOXL reference | 6.00 | 1.0% | 787 | 3.17 | **65.6** | **3.09** | −36.5% |

**The throttling works mechanically and still does not pay.** Cell C restored
cadence to 3.07 trades/day against SOXL's 3.17 — the machinery does exactly
what it should. But the edge came back at **14.1 bp against 65.6**.

The important number is the ratio: **range scaled by 0.44×, edge scaled by
0.21×.** Return falls roughly with the *square* of the range ratio, not
linearly. Costs are the visible part of why — they do not scale down with the
levels. SOXL's 3.7 bp/ON-day of cost is 5.6% of a 65.6 bp gross edge; the same
cost against a halved gross is ~11%. Win rate also degrades (59.2% for cell C
against SOXL's 63.7%) as the levels shrink toward the noise.

**New, measured here (2026-08):** whether throttling *also* degrades under
1-minute fills. Scaling dip and target together on SOXL, where both
resolutions exist:

| levels | 5-min bp | 1-min bp | retained | same-bar | trades/day |
|---|---:|---:|---:|---:|---:|
| 1.00% (locked) | 63.0 | 39.3 | 62% | 66% | 3.18 |
| 0.75% | 69.6 | 50.3 | 72% | 75% | 3.76 |
| 0.50% | 83.6 | 53.8 | 64% | 85% | 4.34 |
| 0.25% | 77.9 | 49.3 | 63% | 91% | 4.80 |

**Retention is flat at 62–72% — throttled levels are not disproportionately
damaged by finer data.** That is worth recording because the opposite was the
natural assumption. What does change is composition: same-bar reliance climbs
**66% → 91%**, so a throttled sleeve's edge is almost entirely the mechanism
that only live fills can verify.

**Verdict on throttling.** It is a real option, not a dead end — but §9.1's
cells B–D are labelled *"EXPLORATORY, NOT ADOPTED"*, and rightly: a rescaled
variant is a different parameter set that would need its own full validation
(V14-style), while contributing on the order of a sixth of a SOXL sleeve for
the same capital and the same operational burden. If a *third* sleeve is ever
wanted, throttled SPXL is the least-bad known candidate. It is not a way to
make a low-volatility instrument perform like SOXL.

### 2. Currencies

The screen can now **measure** FX rather than have anyone assert anything
about it — `IBBroker.contract()` handles `CASH` contracts, RTH bars, MIDPOINT
(FX has no consolidated trade tape):

```bash
python3 band_lab/v2_dev/instrument_screen.py --ib --fx \
        --symbols EURUSD,GBPUSD,USDJPY,AUDUSD,GBPJPY
```

**Run it — but here is what to expect and why.** The screen's first criterion
is median daily range ≥ 0.50 × SOXL's 6.67%, i.e. **≥ 3.3%**. Major FX pairs
run well under 1% on a normal day, roughly an order of magnitude short. That
is a checkable claim and the command above checks it; it is not something to
take on faith.

**The structural objection is the harder one, and no throttling fixes it.**
The strategy's skeleton is a *US equity session*:

| variable | what it depends on |
|---|---|
| V5 start time 11:00 | 90 minutes after a 09:30 open |
| V9 morning filter | the **opening 30-minute range**, 09:30–10:00 |
| V6 flat at close | a 15:55 close — and overnight holding was tested and **rejected on role** |
| V10 vol gate | daily range, which needs a defined session |

Spot FX trades 24/5. There is no open, no close, no opening range, and every
position is an overnight position — the exact thing V6's program rejected.
V5, V6, V9 and V10 would not be re-tuned for FX; they would have **no
referent**. That is not a transfer test, it is a new strategy that happens to
share an idea.

If currencies are genuinely interesting, the honest routes are **currency
futures** (6E, 6J — they have a settlement and a defined session, so the
skeleton at least exists) or a leveraged FX ETF. Both would still have to
clear the range criterion, and that is where the arithmetic above bites.
