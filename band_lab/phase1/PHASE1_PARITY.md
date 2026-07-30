# Phase 1 — Clean-Room Backtest Parity

**Result: PASS.** A backtest engine written from `IMPLEMENTATION_SPEC.md`
§2 alone reproduces the research engine's daily P&L series exactly — 787
SOXL ON-days and 801 SOXS ON-days, worst single-day divergence
4.2 × 10⁻¹⁶ — and rebuilds all four `band_lab/out/v14_*.csv` files
identically from that series.

Per §9, this is the gate on starting Phase 2. It is passed.

Reaching parity required choosing a reading for **eight** clauses of §2
that a clean-room implementer cannot resolve from §2's words. All eight are
now resolved:

- **two produced amendments to §2** — the `thr80` cadence (S1) and the
  missing anti-lookahead rule (S4) — alongside corrections to §8's
  monitoring baselines and §9's Phase 3 cost criterion;
- **two were resolved as deliberate decisions** with the text unchanged —
  the tick grid (S5) and whole-share sizing (S7);
- **four are residual differences** the live system inherits (S2, S3, S6,
  S8).

§3 has each one with its cost; §4 states what the live system inherits;
§5 is the decisions log.

---

## 1. What was built

| file | role |
|---|---|
| `spec_constants.py` | §12 constants, transcribed verbatim, plus the §6.8 config validator |
| `spec_engine.py` | the clean-room engine — §2 rules only, no import from the research lab |
| `parity.py` | A parity, B artifact rebuild, C as-built gap attribution, D §8 baseline guard |
| `test_spec_engine.py` | acceptance tests covering §10 items 1–8, 13, 14 |
| `test_published_numbers.py` | guards every figure quoted in the spec documents |
| `cost_model.py` | per-trade cost model ([COST_MODEL.md](COST_MODEL.md)) |
| `out/` | generated series, decision logs, trade logs, comparison tables |

`spec_engine.py` imports nothing from `transfer_test`, `spxl_scaling_test`,
`v5_corrected_rerun` or `etf_scaling_test`. Those are loaded only inside
`parity.py`, as the comparison target.

### Running it

```bash
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
pip install pandas numpy pytest

python3 band_lab/phase1/parity.py          # full report, exit 0 == all green
python3 -m pytest band_lab/phase1 -v       # 59 tests, ~9s
python3 -m pytest band_lab/phase1 -m "not slow"   # unit tests only
```

`parity.py` exits non-zero if parity breaks, if a `v14_*.csv` stops
matching, **or if §8's published monitoring baselines drift out of step with
the engine** — so it works as a regression gate in CI.

---

## 2. Parity result

Clean-room engine in `RESEARCH_COMPAT` mode vs `etf_scaling_test.run_cell`
at the locked settings (gate 6.0, dip/target 1%, stop 4%):

| sleeve | research days | clean-room days | days only in one | max abs daily diff | days over 1e-12 |
|---|---|---|---|---|---|
| SOXL | 787 | 787 | 0 | 4.16e-16 | 0 |
| SOXS | 801 | 801 | 0 | 3.89e-16 | 0 |

Rebuilt from the clean-room series alone: `v14_costs.csv`,
`v14_plateau.csv`, `v14_walkforward.csv`, `v14_capital_rule.csv` — all
**IDENTICAL**.

Two independent confirmations worth noting:

- The clean-room engine measures **3.17** fills/ON-day (SOXL) and **3.36**
  (SOXS) — the exact values hard-coded as `trades_per_day` in
  `v14_pair_protocol.py`'s cost model. The cost model is not circular.
- Worst day is **−8.00%** on both sleeves, i.e. exactly two 4% stops. The
  §2.7 circuit breaker is load-bearing and it holds across 1,588 ON-days.

---

## 3. The eight under-determined clauses, and how each was resolved

Each is a named switch on `EngineConfig`. `RESEARCH_COMPAT` reproduces the
research engine exactly (that is what parity is measured under);
`SPEC_LITERAL` is the specification as it now stands. Impact is gross bp per
ON-day, one switch at a time off the research baseline (SOXL 65.6 bp / 787
days, SOXS 57.7 bp / 801 days). Full table:
`out/spec_vs_research_attribution.csv`.

### 3.1 Resolved by amending the specification

#### S1 — `thr80` refresh cadence → **§2.1 amended to daily**

- **§2.1 previously said:** recomputed monthly, held constant within the
  calendar month. `STRATEGY_SPEC.md` §2.5 and `MASTER_STRATEGY_DOCUMENT.md`
  §8.2 agreed.
- **The research engine has always recomputed it every session**
  (`or30.shift(1).rolling(504, min_periods=120).quantile(.8)`), so the
  monthly wording described a system that was never measured.
- **Cost of the monthly reading:** SOXL 787 → 767 ON-days (−20), +1.6 bp;
  SOXS 801 → 787 (−14), −0.9 bp.

**Decision: the spec follows the engine.** §2.1, §5's 06:00 row,
`STRATEGY_SPEC.md` §2.5 step 2 and the three restatements in
`MASTER_STRATEGY_DOCUMENT.md` now all say daily. This is a documentation
correction, not a strategy change: V9 §T5 swept the cadence and found it
immaterial (monthly/quarterly/annual within 61–65 bp, Sharpe 3.03–3.21) and
daily measures 65.6 bp, inside that band. `V9_FILTER_TESTS.md` decision 4 is
left intact as the historical record of what was tested, annotated as
superseded for what is built.

The monthly reading stays runnable (`thr80_refresh="monthly"`) so the cost
of the road not taken remains a number rather than a memory.

#### S4 — is the target live on the entry bar? → **§2.6 gap closed**

- **§2.6 literally:** "The instant an entry fills at price E, place a
  one-cancels-all group" — so the +1% limit is live immediately and could
  fill on the entry bar.
- **The engine forbids it:** the target may fill only from the bar *after*
  entry, and within a bar the stop is checked first. This is stated in
  `STRATEGY_SPEC.md` §2.5 step 4 and is the fix for the v5 lookahead bug in
  `v5_corrected_rerun.py`'s header — the bug that had inflated earlier
  results substantially.
- **Cost of the literal reading:** SOXL −0.5 bp, SOXS +2.3 bp.

`IMPLEMENTATION_SPEC.md` §2 did not mention this rule anywhere, while §1
promises the file is self-contained. An implementer handed only it would
have reintroduced the exact class of bug the research programme spent a
version fixing — the measured impact is small here only because the rest of
the engine is correct. **§2.6 now carries the rule explicitly**, marked
normative for any simulator.

#### §8 — monitoring baselines → **corrected and now machine-checked**

§8's table is what a live system gets judged against, and it says to
investigate deviations >20% as structural. Two of its five rows did not
match the engine they described:

| §8 metric | §8 said | SOXL | SOXS | |
|---|---|---|---|---|
| fills per ON day | ≈ 3.2 | 3.17 | 3.36 | ✅ |
| ON-day rate | ≈ 50% | 52.1% | 53.1% | ✅ |
| worst day | never below −8% | −8.00% | −8.00% | ✅ |
| target-hit share of exits | 75–80% | **71.3%** | **71.8%** | ❌ |
| net bp per ON day | ≈ 50 bp | **61.9** | 48.1 | ⚠️ |

§8 now publishes the measured per-sleeve exit mix (target ≈71%, stop ≈10%,
15:55 flatten ≈19%) and per-sleeve net bp, and `parity.py` section D
re-measures every published number and **fails if the document drifts**.

### 3.2 Resolved as deliberate decisions, spec unchanged

#### S5 — model the $0.01 tick grid? → **no; held as unbanked conservatism**

- The **live** engine has no choice: §2.5/§2.6 say `round_to_tick` and the
  exchange enforces it. The **backtest** does not model it.
- **Cost of modelling it:** SOXL **+4.3 bp** (~6.5% of the sleeve's edge),
  SOXS +0.5 bp.

Checked three ways before deciding, because +4.3 bp is not a rounding
detail:

- Not a split artifact — restricted to post-2021-03-02 sessions, where SOXL
  prices sit exactly on a cent grid, the effect is **+4.45 bp**; pre-split it
  is −0.07 bp over 26 days.
- Not favourable level placement — rounding *adversely* (buy limit down,
  target up, stop up) still gives **+3.0 bp**. The sign is robust to
  rounding direction, so the driver is discretisation changing which
  marginal touches fill.
- Roughly evenly split between the two legs: entry-limit rounding +2.40 bp,
  exit-level rounding +1.97 bp on SOXL.

SOXS shows almost nothing because its back-adjusted history runs to
$1.17M/share, where a cent is noise.

**Decision: do not bank it.** The research engine's continuous-price
assumption is conservative by ~3–4 bp/ON-day on SOXL. Assume it is not
there; let Phase 2's real fills settle it.

#### S7 — whole-share sizing → **live-engine rule only**

- **§2.4:** `order_qty = floor(f × sleeve_capital / limit_price)`; below one
  share the sleeve does not trade.
- **Cost of applying it to this data:** SOXL −0.0 bp; SOXS **−10.6 bp**
  (57.7 → 47.1).

SOXS's back-adjusted history reaches **$1,171,204/share**, so
`floor(150000 / price) == 0` on **248 of 1,508 sessions** and the sleeve
"cannot afford one share". This is precisely the failure §4 warns about:
*"absolute price levels from history must never be used for sizing or order
pricing."*

**Decision: off in the backtest, mandatory live.** The consequence to accept
is that the backtest cannot validate share quantisation on SOXS at all. On
SOXL, where the adjusted series is tradeable throughout, it can — and the
measured cost is −0.0 bp/ON-day. At the reference $150K sleeve with SOXL
near $158 the order is 946 shares and the discarded fraction is under 0.1%
of the position.

### 3.3 Residual: the spec is right, the engine never implemented it

These three are adopted in `SPEC_LITERAL` and are the gap the live system
starts with. See §4.

| | rule | research engine | cost of adopting |
|---|---|---|---|
| **S2** | §2.2 scheduled half-days OFF (also `STRATEGY_SPEC.md` §2.5 step 1) | trades them; its only length guard, `len(gb) < 20`, never fires because half-days carry 42 bars | −8 ON-days/sleeve; **+0.4 bp** SOXL, **+1.2 bp** SOXS |
| **S3** | §2.8 flatten at 15:55; §2.5 the entry rests "until the flatten time" | rides the final bar to the 16:00 close and still allows an entry during the 15:55 bar | 0 ON-days; **−0.1 bp** SOXL, **+2.3 bp** SOXS |
| **S6** | §2.1 bars addressed by clock time | addressed by position in the file (`h[:18]`, `cc[5]`) | **0.0 bp** both sleeves |

S3 is the one with teeth: the backtest books its EOD exit five minutes later
than the live system will be able to, on 18.8% of all exits.

S6 costs nothing on this data because both files start at 09:30 on every
session but one — the clean-room engine uses clock time anyway, because that
is what the live engine must do.

**S8 — incomplete session data (§4).** One SOXS session opens at 09:45 with
75 bars; the research engine silently treats its 09:45–10:10 bars as the
"opening range" and starts trading at 12:15 rather than 11:00. Impact
**0.0 bp** — that day never passes the gate. The check is kept because it is
free and the next such day may not be so harmless.

---

## 4. What the live system inherits

Adopting S2, S3, S6 and S8 — every case where the spec is right and the
engine simply lacked the rule — measured as one combined run, not summed
from the singles:

| sleeve | validated (research engine) | as built (spec) | Δ |
|---|---|---|---|
| SOXL | 65.6 bp / 787 days / Sharpe 3.09 | 65.9 bp / 779 days / Sharpe 3.14 | **+0.3 bp** |
| SOXS | 57.7 bp / 801 days / Sharpe 2.63 | 61.2 bp / 793 days / Sharpe 2.83 | **+3.5 bp** |

Worst day stays −8.00% on both. **This is the number to carry into the Phase
3 live-vs-backtest comparison — not zero.** A live SOXS sleeve running a few
bp above the validated series is expected, not evidence of anything.

Two further asymmetries to hold in mind when Phase 3 compares live fills
against the backtest, both pointing the same way:

- the tick grid is worth ~+3–4 bp/ON-day on SOXL and is deliberately not
  modelled (S5);
- share quantisation costs ~0.0 bp on SOXL and is not modelled at all on
  SOXS (S7).

Nothing here is a reason to expect live to *beat* backtest. The one
assumption that could move the number the other way, hard, is untested — see
§6.

---

## 5. Decisions log

| | question | resolution | date |
|---|---|---|---|
| S1 | thr80 monthly or daily? | **daily** — §2.1 amended to match the validated engine | 2026-07 |
| S2 | half-days OFF? | **yes** — spec stands, engine lacked it; +0.4/+1.2 bp | 2026-07 |
| S3 | flatten 15:55 or 16:00? | **15:55** — spec stands; −0.1/+2.3 bp | 2026-07 |
| S4 | target live on the entry bar? | **no** — §2.6 now states the anti-lookahead rule | 2026-07 |
| S5 | model the tick grid in the backtest? | **no** — held as unbanked conservatism, ~+3–4 bp SOXL | 2026-07 |
| S6 | clock or positional bar addressing? | **clock** — free, and required live | 2026-07 |
| S7 | whole-share sizing in the backtest? | **no** — live-engine rule only; §4's warning confirmed empirically | 2026-07 |
| S8 | refuse incomplete sessions? | **yes** — free, currently zero impact | 2026-07 |
| §8 | monitoring baselines | corrected to measured per-sleeve values; now machine-checked | 2026-07 |

---

## 6. Costs

Reviewed separately in **[COST_MODEL.md](COST_MODEL.md)**; `cost_model.py`
regenerates it. Summary:

- The incumbent flat charge (SOXL 3.7 bp, SOXS 9.6 bp per ON day) is **not
  wrong — it is conservative by 0.5 / 1.1 bp**, and the conservatism sits in
  its spread term rather than being named as slippage. Its `cross_frac=0.30`
  guess is confirmed almost exactly: 28.7% / 28.2% of exits actually cross.
- Per-trade costing off the Phase 1 trade logs replaces the flat charge.
  Real per-day cost spans 1.2 → 4.9 bp (SOXL) and 3.2 → 12.2 bp (SOXS)
  against a flat 3.7 / 9.6, because fill counts are bimodal and correlate
  +0.44 with the day's P&L.
- **w = 0.50 is the Sharpe argmax under every cost scenario tested**,
  including one that strips 7.3 bp off SOXS. The pair decision is not
  cost-model-dependent.
- All remaining cost uncertainty lives in **SOXS**, and it is a price-level
  effect: 7.3 bp of range across plausible spread assumptions, versus 2.3 bp
  for SOXL.
- **§9's Phase 3 cost criterion was wrong and is corrected.** It compared a
  10–20%-of-capital run against $150K cost figures; IBKR's $1.00 order
  minimum makes SOXL cost 4.0 bp/ON-day at $22.5K and 7.5 bp at $10K, versus
  3.2 bp at full size.

The spread itself **cannot be measured from this repository** — the data is
5-minute OHLCV with no quotes. Phase 2 should log the quoted spread at every
order event.

---

## 7. What Phase 1 does *not* cover

§10 items **9–12** (flatten verification, crash/restart reconciliation, API
disconnect, watchdog) and **15–16** (session replay, weekly report) exercise
the live IBKR engine and its persistence layer. None is simulable in a
bar-replay harness, so none is stubbed or faked here — they belong to Phase
2. `test_spec_engine.py` states this in its module docstring.

Also untested by construction, and flagged in §9 of the spec as the largest
open assumption: **whether a resting 0.99× limit actually fills the way the
backtest assumes.** Every number in this document rests on it. Paper trading
is the first real evidence.
