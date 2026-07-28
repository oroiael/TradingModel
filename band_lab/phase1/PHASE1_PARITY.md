# Phase 1 — Clean-Room Backtest Parity

**Result: PASS.** A backtest engine written from `IMPLEMENTATION_SPEC.md`
§2 alone reproduces the research engine's daily P&L series exactly — 787
SOXL ON-days and 801 SOXS ON-days, worst single-day divergence
4.2 × 10⁻¹⁶ — and rebuilds all four `band_lab/out/v14_*.csv` files
byte-identically from that series.

Per §9, this is the gate on starting Phase 2. It is passed.

But passing required choosing a specific reading of **eight** clauses in §2
that a clean-room implementer cannot resolve from §2's words. Those are
listed in §3 below with the measured cost of each. **Six of them are places
where the spec and the validated research engine describe different
systems.** They are small individually, but §9's whole purpose is to surface
exactly this, so none is silently absorbed. §4 lists the decisions needed
before Phase 2.

---

## 1. What was built

| file | role |
|---|---|
| `spec_constants.py` | §12 constants, transcribed verbatim, plus the §6.8 config validator |
| `spec_engine.py` | the clean-room engine — §2 rules only, no import from the research lab |
| `parity.py` | the parity harness: A parity, B artifact rebuild, C ambiguity attribution, D §8 monitoring baselines |
| `test_spec_engine.py` | 47 acceptance tests covering §10 items 1–8, 13, 14 |
| `out/` | generated series, decision logs, trade logs, comparison tables |

`spec_engine.py` imports nothing from `transfer_test`, `spxl_scaling_test`,
`v5_corrected_rerun` or `etf_scaling_test`. Those are loaded only inside
`parity.py`, as the comparison target.

### Running it

```bash
git lfs pull --include="SOXL_5min_6Years.csv,SOXS_5min_6Years.csv"
pip install pandas numpy pytest

python3 band_lab/phase1/parity.py          # full report, exit 0 on parity
python3 -m pytest band_lab/phase1 -v       # 47 acceptance tests, ~7s
python3 -m pytest band_lab/phase1 -m "not slow"   # unit tests only
```

`parity.py` exits non-zero if parity breaks or a `v14_*.csv` stops matching,
so it works as a regression gate in CI.

---

## 2. Parity result

Clean-room engine in `RESEARCH_COMPAT` mode vs `etf_scaling_test.run_cell`
at the locked settings (gate 6.0, dip/target 1%, stop 4%):

| sleeve | research days | clean-room days | days only in one | max abs daily diff | days over 1e-12 |
|---|---|---|---|---|---|
| SOXL | 787 | 787 | 0 | 4.16e-16 | 0 |
| SOXS | 801 | 801 | 0 | 3.89e-16 | 0 |

Rebuilt from the clean-room series alone:

| table | status |
|---|---|
| `v14_costs.csv` | IDENTICAL |
| `v14_plateau.csv` | IDENTICAL |
| `v14_walkforward.csv` | IDENTICAL |
| `v14_capital_rule.csv` | IDENTICAL |

Two independent confirmations worth noting:

- The clean-room engine measures **3.17** fills/ON-day (SOXL) and **3.36**
  (SOXS) — the exact values hard-coded as `trades_per_day` in
  `v14_pair_protocol.py`'s cost model. The cost model is not circular.
- Worst day is **−8.00%** on both sleeves, i.e. exactly two 4% stops. The
  §2.7 circuit breaker is load-bearing and it holds across 1,588 ON-days.

---

## 3. The eight under-determined clauses

Each is a named switch on `EngineConfig`. `RESEARCH_COMPAT` sets them all to
the research engine's behaviour (that is what parity is measured under);
`SPEC_LITERAL` sets them to the closest reading of §2's words.

Impact is on gross bp per ON-day, measured one switch at a time from the
research baseline (SOXL 65.6 bp / 787 days, SOXS 57.7 bp / 801 days). Full
table: `out/spec_vs_research_attribution.csv`.

### S1 — `thr80` refresh cadence  ⚠️ spec and research disagree

- **§2.1:** "Recomputed **monthly** (first session of each calendar month)
  and held constant within the month." `STRATEGY_SPEC.md` §2.5 step 2 agrees.
- **Research engine:** `or30.shift(1).rolling(504, min_periods=120).quantile(.8)`
  — recomputed **every session**.
- **Impact:** SOXL 787 → 767 ON-days (−20), **+1.6 bp**; SOXS 801 → 787
  (−14), **−0.9 bp**.

This is the most consequential of the eight, not for P&L but because the
threshold decides *which days trade*. A system built to §2 will trade a
measurably different day-set from the one that was walk-forward validated.

A monthly hold also creates a startup dead zone the spec does not mention:
the threshold only becomes available at the first session of the first month
*after* 120 prior observations exist, so the sleeve stays dark for up to a
month longer than "≥120 observations" implies. The engine implements this
literally.

### S2 — scheduled half-days  ⚠️ spec and research disagree

- **§2.2:** "do not trade if … the session is a scheduled half-day (early
  close)." `STRATEGY_SPEC.md` §2.5 step 1: "Scheduled half-days (early
  closes): treat as OFF."
- **Research engine:** has no half-day rule; its only length guard is
  `len(gb) < 20`, which never fires (the 12 half-days per file have 42 bars).
- **Impact:** SOXL 787 → 779 ON-days (−8), **+0.4 bp**; SOXS 801 → 793 (−8),
  **+1.2 bp**.

Unambiguous: both prose documents say OFF and the engine trades them. The
spec is right; the research engine has a small unimplemented rule. Adopting
it costs 8 ON-days per sleeve and improves bp/day slightly.

### S3 — flatten time  ⚠️ spec and research disagree

- **§2.8:** flatten at **15:55**; §2.5: the entry rests "from 11:00 until the
  flatten time."
- **Research engine:** rides the final bar to the **16:00** close
  (`c[-1]`) and still allows an entry during the 15:55 bar.
- **Impact:** no change in ON-days; SOXL **−0.1 bp** (Sharpe 3.09 → 3.13),
  SOXS **+2.3 bp** (Sharpe 2.63 → 2.79).

The backtest books its EOD exit five minutes later than the live system will
be able to. Small, but it is a systematic five-minute lookahead on every
flattened trade (18.8% of all exits).

### S4 — is the target live on the entry bar?  ⚠️ §2 is silent on the most dangerous point

- **§2.6, literally:** "The instant an entry fills at price E, place a
  one-cancels-all group" — so the +1% limit is live immediately and could
  fill on the entry bar.
- **Research engine:** the target may fill only from the bar *after* entry;
  only the stop may fire on the entry bar. This is stated in
  `STRATEGY_SPEC.md` §2.5 step 4 and is the fix for the v5 lookahead bug
  documented in `v5_corrected_rerun.py`'s header — the bug that had inflated
  earlier results substantially.
- **Impact of taking §2 literally:** SOXL **−0.5 bp**, SOXS **+2.3 bp**.

**`IMPLEMENTATION_SPEC.md` §2 does not mention this rule anywhere.** An
implementer handed only this file — which §1 of the spec explicitly promises
is sufficient — would reintroduce the exact class of bug the research
programme spent a version fixing. The measured impact here is small only
because the rest of the engine is correct; the general failure mode is not.
This is the single most important documentation gap Phase 1 found.

### S5 — `round_to_tick`  ⚠️ largest measured divergence

- **§2.5/§2.6:** the entry limit and both exit legs are placed at
  `round_to_tick(...)`.
- **Research engine:** continuous prices, no tick grid.
- **Impact:** SOXL **+4.3 bp** (6.6% of the sleeve's edge), SOXS **+0.5 bp**.

Decomposed on SOXL: entry-limit rounding +2.40 bp, exit-level rounding
+1.97 bp. It is not an artifact of the pre-split adjustment — restricted to
post-2021-03-02 sessions (where prices sit exactly on a cent grid) the effect
is **+4.45 bp**; pre-split it is −0.07 bp over 26 days.

Nor is it favourable-level placement: rounding *adversely* instead (buy limit
down, target up, stop up) still gives **+3.0 bp** on SOXL. The effect comes
from discretisation changing which marginal touches fill, and its sign is
robust to rounding direction.

SOXS shows almost nothing because its back-adjusted history runs to
$1.17M/share, where a cent is noise.

**This should not be banked as edge.** The honest reading is that the
research engine's continuous-price assumption is conservative by roughly
3–4 bp/ON-day on SOXL, and paper trading (Phase 2) is what settles it.

### S6 — bar addressing

§2.1 defines bars by clock time ("bar index 0 is the 09:30 bar"). The
research engine uses position in the file (`h[:18]`, `cc[5]`). **Impact:
0.0 bp on both sleeves** — the two files start at 09:30 on every session but
one. The clean-room engine uses clock time because that is what the live
engine must do and it costs nothing.

### S7 — whole-share sizing  ⚠️ must stay OFF in the backtest

- **§2.4:** `order_qty = floor(f × sleeve_capital / limit_price)`; if
  `order_qty < 1` the sleeve does not trade.
- **Impact if applied to this data:** SOXL **−0.0 bp**; SOXS **−10.6 bp**
  (57.7 → 47.1).

SOXS's back-adjusted history reaches **$1,171,204/share**, so
`floor(150000 / price) == 0` on **248 of 1,508 sessions** and the sleeve
"cannot afford one share". This is precisely the failure §4 warns about:
*"absolute price levels from history must never be used for sizing or order
pricing."*

Share rounding is therefore a **live-engine rule only** and is off by
default in `SPEC_LITERAL`. The consequence to accept: the backtest cannot
validate share quantisation on SOXS at all. On SOXL, where the adjusted
series is tradeable throughout, it can — and the measured cost is −0.0
bp/ON-day. At the reference $150K sleeve with SOXL near $158 the order is
946 shares and the discarded fraction is under 0.1% of the position.

### S8 — incomplete session data

§4 requires pre-trade sanity checks. One SOXS session opens at 09:45 with 75
bars; the research engine silently uses its 09:45–10:10 bars as the
"opening range" and starts trading at 12:15 rather than 11:00. **Impact:
0.0 bp** — that day never passes the gate. The check is kept because it is
free and the next such day may not be so harmless.

### Combined

Taking every spec-literal reading together (S1, S2, S3, S5, S6, S8):

| sleeve | research baseline | spec-literal | Δ |
|---|---|---|---|
| SOXL | 65.6 bp / 787 days / Sharpe 3.09 | 71.4 bp / 759 days / Sharpe 3.37 | **+5.8 bp** |
| SOXS | 57.7 bp / 801 days / Sharpe 2.63 | 61.2 bp / 779 days / Sharpe 2.81 | **+3.5 bp** |

The spec-literal system is *better* on both sleeves, which is the reassuring
direction — but it is not the system that was validated, and roughly
three-quarters of the gain is S5, which I would not bank.

---

## 4. Decisions needed before Phase 2

1. **S1 (thr80 cadence)** — build the monthly hold per §2.1 and accept a
   day-set that differs from the validated one, or amend §2.1 to the daily
   refresh the research actually used? This is the only one that changes
   which days trade by a meaningful count.
2. **S4 (target on the entry bar)** — I recommend adding one sentence to
   §2.6 stating that a backtest must not book a target fill on the entry bar.
   The rule exists in `STRATEGY_SPEC.md` but not in the file §1 says is
   self-contained.
3. **S5 (`round_to_tick`)** — should the backtest model the cent grid?
   Recommendation: no, keep the research convention and treat the 3–4 bp as
   unbanked conservatism, to be measured against real fills in Phase 2.
4. **§8 monitoring baselines are wrong** — see §5. These are the numbers a
   live system will be judged against; they should be corrected before
   anything is judged against them.

S2, S3, S6, S7, S8 need no decision — the spec is right and the clean-room
engine implements it; only S2 and S3 move the numbers at all, and both by
under 2.5 bp.

---

## 5. §8 monitoring expectations vs measurement

§8 says to investigate deviations >20% from these as structural. Two of them
do not match the research engine they were meant to describe.

| §8 metric | §8 expects | SOXL measured | SOXS measured | |
|---|---|---|---|---|
| fills per ON day | ≈ 3.2 | 3.17 | 3.36 | ✅ |
| ON-day rate | ≈ 50% | 52.1% | 53.1% | ✅ |
| worst day | never below −8% | −8.00% | −8.00% | ✅ |
| target-hit share of exits | 75–80% | **71.3%** | **71.8%** | ❌ |
| net bp per ON day | ≈ 50 bp | **61.9** | 48.1 | ⚠️ |

The exit mix is target 71.3% / stop 9.9% / EOD flatten 18.8% (SOXL). §8's
75–80% matches neither the raw share nor the share excluding flattens
(87.8%). Recommend restating §8 as "target ≈71%, stop ≈10%, EOD flatten
≈19% of exits", and splitting the net bp/ON-day expectation per sleeve
(SOXL ≈62, SOXS ≈48) rather than quoting one ≈50 figure.

---

## 6. What Phase 1 does *not* cover

§10 items **9–12** (flatten verification, crash/restart reconciliation, API
disconnect, watchdog) and **15–16** (session replay, weekly report) exercise
the live IBKR engine and its persistence layer. None of them is simulable in
a bar-replay harness, so none is stubbed or faked here — they belong to
Phase 2. `test_spec_engine.py` states this in its module docstring.

Also untested by construction, and flagged in §9 of the spec as the largest
open assumption: **whether a resting 0.99× limit actually fills the way the
backtest assumes.** Every number in this document rests on it. Paper trading
is the first real evidence.
