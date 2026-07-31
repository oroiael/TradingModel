# V16 — Joint re-test of the churn-rate parameters (V1 × V3 × V7)

**Line:** v2.0-dev (DEVELOPMENT). Nothing here changes v1.0 production.

**Status: adoption bar prespecified below. Results appended after the run,
below the rule. The bar is not edited after seeing results.**

---

## 1. Why these three, and why jointly

`PHASE2_PARITY.md` S10–S11 showed the 5-minute engine booked ~half its edge on
re-entries priced at levels that had already traded. Three locked parameters
directly control how often the strategy exits and re-enters — i.e. how often
the biased mechanism fired during their original sweeps:

| var | locked | what it controls | why its verdict is suspect |
|---|---|---|---|
| **V1** dip depth | 1% | how far price must fall below the session high to trigger a buy | a shallower dip makes re-entry easier and more frequent. Swept 1–3%; 1% won — plausibly *because* it maximised phantom re-entries |
| **V3** profit target | +1% | how quickly a position is closed, freeing the next entry | the tightest control on round-trip count. Swept 1–2%; 1% won, same concern |
| **V7** trade cap | 5/day | how many round trips a day may run | "Sharpe peaked at 5" was measured when late-in-day trades were disproportionately phantom |

**They are tested jointly because they are not independent.** All three set the
same quantity — round trips per day. Sweeping them one at a time holds the
other two at values that were themselves chosen under the bias, so each
one-dimensional sweep would be conditioned on a contaminated baseline. A joint
grid is the only way to see the surface.

V4 (stop, −4%) is deliberately **not** under test. The evidence that it is
uncontaminated is in the risk column: correcting the fill model left MaxDD
essentially unchanged (SOXL −39.9% → −41.3%) and the worst day identical to
the cent. Losses were always real, so anything calibrated on the loss side was
calibrated on clean data.

## 2. Data and engine

- **Fill data:** 1-minute, `SOXL_1min.csv` / `SOXS_1min.csv`, window 2022-01-03
  onward (S12: 2020–21 fails the data-quality gate in both sleeves).
- **Decision clock:** unchanged 5-minute bars. §2.5's anchor ratchet, the 11:00
  activation and the counters are defined on that cadence and are not under test.
- **Features:** ATR5 / thr80 / OR30 always computed from the **full** 5-minute
  record, never from the test window, so no early session is stood down.
- **Fill model:** `spec` at 1-minute resolution, `target_delay=fill_bar`
  (S11: the target is a resting limit order; making it wait a full 5-minute bar
  is an artifact of coarse data, not a strategy rule).
- **Engine:** `band_lab/live/sleeve.py`, driven by config. Not a fork.

## 3. Grid

| variable | values | cells |
|---|---|---|
| V1 `dip_pct` | 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50, 3.00 % | 8 |
| V3 `target_pct` | 0.50, 0.75, 1.00, 1.25, 1.50, 2.00 % | 6 |
| V7 `max_fills` | 2, 3, 4, 5, 6, 8, 10 | 7 |

336 cells per sleeve, 672 runs. Incumbent = (1.00, 1.00, 5).

## 4. Costs — not optional here

Costs are applied per fill, at the rate implied by `IMPLEMENTATION_SPEC.md` §8
(gross vs net ÷ fills per ON-day): **SOXL 1.167 bp/fill, SOXS 2.857 bp/fill.**

This matters more than usual: V7 and V3 both change trade count directly, so a
gross-only comparison would systematically favour high-churn cells. Every
figure below is net.

## 5. Adoption bar — PRESPECIFIED, fixed before running

A cell is adopted only if it clears **all six**:

| # | criterion |
|---|---|
| **B1** | **Out-of-sample.** Beats the incumbent on net bp/ON-day in **≥4 of 5** walk-forward years. Each year is held out in turn; the candidate is selected on the other four and scored on the held-out year. (V14's bar, same shape.) |
| **B2** | **Plateau.** The full-sample winner's immediate neighbours (±1 grid step in each dimension) must average **≥90%** of its net edge. An isolated spike is a fitting artifact, not a parameter. |
| **B3** | **Both sleeves.** The same direction of change must hold in SOXL and SOXS. A one-sleeve-only change requires separate written justification. |
| **B4** | **Costs.** All comparisons net (§4). A cell that wins gross and loses net is rejected. |
| **B5** | **Risk.** MaxDD must not worsen by more than **2 percentage points** against the incumbent on the same window. |
| **B6** | **Mechanism.** The winner must **not** increase reliance on same-bar re-entry versus the incumbent. A cell that wins by generating more same-*minute* re-entries is re-acquiring the S10 artifact one resolution down, and is rejected regardless of B1–B5. |

**B6 is the one that matters most** and is specific to this program. Without
it, the grid search would happily rediscover the bias at 1-minute resolution —
which is precisely how the original problem was created.

**If no cell clears the bar, the locked values stand.** That is a valid and
expected outcome, not a failed test.

## 6. What this program cannot establish

Same-minute sequencing is still unresolved, so every figure here inherits the
S11 caveat: real fills should land below these numbers, and the residual error
runs one direction. This program can say *which parameters are better relative
to each other* on cleaner data. It cannot say the resulting bp figure is
achievable.

---
---

# RESULTS

*(appended after the run; the bar above was not edited)*

## VERDICT: **NOT ADOPTED.** The locked V1 = 1%, V3 = +1%, V7 = 5 stand.

672 cells run. Nothing cleared the six-criterion bar. Per §5 that is a valid
outcome, and the reason it happened is the most useful thing in this document.

---

## R1. The naive winner — and why the bar rejected it

Ranking all 336 cells per sleeve by net bp/ON-day gives the **same** answer in
both sleeves: dip 0.50%, target 0.50%, cap 10.

| | SOXL | SOXS |
|---|---:|---:|
| net bp/ON-day | **93.1** vs incumbent 39.3 (**+53.8**) | **73.8** vs 30.3 (**+43.5**) |
| walk-forward (B1) | **5 of 5 years** | **5 of 5 years** |
| MaxDD (B5) | −34.9% vs −40.6% — *better* | −32.6% vs −36.5% — *better* |

On the first three criteria it looks overwhelming: it more than doubles the
edge, wins out-of-sample in every single year, in both sleeves, with a
*smaller* drawdown. Under the old process this would have been adopted.

It fails anyway:

| criterion | SOXL | SOXS |
|---|---|---|
| **B2 plateau** | neighbours avg **82%** of the cell (needs ≥90%) — **FAIL** | **73%** — **FAIL** |
| **B6 mechanism** | same-bar share **66% → 85%** — **FAIL** | **102% → 104%** — **FAIL** |
| grid position | corner cell (min dip, min target, max cap) | corner cell |

**This is the whole point of the program.** The grid found more return by
cutting the target in half and doubling the trade cap — i.e. by **churning
harder**, which is precisely the behaviour that manufactures same-bar
re-entries. SOXL's reliance on the mechanism we know is still mismeasured rose
from 66% to 85% of P&L. The search rediscovered the S10 artifact one
resolution down, exactly as B6 anticipated, and did so while passing a
5-of-5 walk-forward — which is the sobering part.

It also sits in a corner of the grid, so the "optimum" is unresolved rather
than located.

## R2. Applying the bar as a filter, not a final check

Checking only the top cell is the wrong procedure. Filtering all 336 cells on
B2 + B5 + B6 + interior first, then ranking:

| | qualifying cells |
|---|---|
| SOXL | 43 of 336 |
| SOXS | 7 of 336 |
| **both sleeves (B3)** | **2** |

The two that qualify in both sleeves are dip 2.50% / target 1.25% / cap 5 and
cap 4 — and **both are worse than the incumbent** (SOXL 28.0 and 25.4 vs 39.3;
SOXS 15.2 and 13.6 vs 30.3). There is no cell that is simultaneously better,
plateau-supported, risk-neutral, mechanism-neutral, and valid in both sleeves.

Best qualifying cell per sleeve, for the record — note they disagree:

| sleeve | dip | target | cap | net bp | vs inc | MaxDD | plateau | same-bar |
|---|---|---|---|---:|---:|---:|---:|---:|
| SOXL | 1.50% | 1.00% | 8 | 49.5 | +10.2 | −39.1% | 94% | 63% |
| SOXS | 2.50% | 0.75% | 8 | 36.2 | +5.9 | −32.3% | 93% | 86% |

Both want a **deeper** dip and a **higher** cap — the opposite dip direction
from the naive winner. But they disagree on how deep and on the target, and
neither survives on the other sleeve, so B3 is not met.

## R3. Each variable on its own, others held locked

The marginal views, which are the clearest read on what each parameter does.

**V1 dip depth** (locked 1.00%)

| dip | SOXL net | SOXL MaxDD | SOXL same-bar | SOXS net | SOXS same-bar |
|---|---:|---:|---:|---:|---:|
| 0.50% | 50.4 (+11.1) | −43.1% ✗B5 | 60% ✓ | 25.8 (−4.5) | 123% ✗ |
| 0.75% | 43.6 (+4.3) | −42.9% ✗B5 | 62% ✓ | 28.1 (−2.2) | 111% ✗ |
| **1.00%** | **39.3** | −40.6% | 66% | **30.3** | 102% |
| 1.50% | 39.1 (−0.3) | −39.6% | 57% ✓ | 22.3 (−8.0) | 102% |
| 2.00% | 33.2 (−6.1) | −33.1% | 58% ✓ | 22.8 (−7.5) | 97% ✓ |
| 3.00% | 25.3 (−14.0) | −39.4% | 55% ✓ | 20.4 (−9.9) | 81% ✓ |

SOXL wants it shallower, SOXS wants it exactly where it is. **The sleeves
disagree in direction — B3 fails outright.** SOXL's shallower settings also
breach the drawdown limit.

**V3 profit target** (locked +1.00%)

| target | SOXL net | SOXL same-bar | SOXS net | SOXS MaxDD |
|---|---:|---:|---:|---:|
| 0.50% | 45.8 (+6.5) | 85% ✗B6 | 30.1 (−0.2) | −30.6% |
| 0.75% | 47.1 (+7.8) | 75% ✗B6 | 25.6 (−4.7) | −34.3% |
| **1.00%** | **39.3** | 66% | **30.3** | −36.5% |
| 1.25% | 35.1 (−4.2) | 53% ✓ | 18.8 (−11.5) | −45.9% ✗B5 |
| 2.00% | 26.8 (−12.5) | 17% ✓ | 6.4 (−23.9) | −64.1% ✗B5 |

Every tighter target that earns more does so by raising same-bar reliance;
every looser target that lowers reliance earns less. **The trade-off is
monotonic and it runs straight through B6.** SOXS's incumbent is already at
its own optimum.

**V7 trade cap** (locked 5) — the strongest single signal, and the closest call

| cap | SOXL net | SOXL same-bar | SOXS net | SOXS MaxDD |
|---|---:|---:|---:|---:|
| 3 | 32.2 (−7.1) | 69% ✗B6 | 11.4 (−18.9) | −43.4% |
| 4 | 36.6 (−2.7) | 64% ✓ | 23.5 (−6.8) | −39.7% |
| **5** | **39.3** | 66% | **30.3** | −36.5% |
| 6 | 47.0 (**+7.6**) | 70% ✗B6 | 38.0 (**+7.7**) | −38.8% |
| 8 | 49.3 (**+10.0**) | 67% ✗B6 | 35.8 (+5.5) | −42.6% ✗B5 |
| 10 | 51.8 (**+12.5**) | 68% ✗B6 | 41.4 (**+11.1**) | −42.6% ✗B5 |

This is the one lever that is large, monotonic, and points the **same way in
both sleeves** — raising the cap is worth +7.6 to +12.5 bp/ON-day. It still
fails, on different criteria in each sleeve: on SOXL every raised cap
increases same-bar reliance (66% → 67–70%, **B6**), and on SOXS caps 8 and 10
breach the drawdown limit (−42.6% against a −38.5% floor, **B5**). Cap 6 fails
B6 in both.

**V7 is the strongest candidate for a follow-up program** — the failures are
narrow (1–4 points of same-bar share on SOXL; 4 points of drawdown on SOXS)
rather than structural. It should not be adopted on this evidence.

## R4. What this program actually established

1. **The locked values are defensible.** Not optimal on the new data, but no
   alternative survives honest scrutiny. V1 = 1% is SOXS's own optimum; V3 = 1%
   sits at the point where the return/mechanism trade-off turns.
2. **Walk-forward is not sufficient protection here.** The rejected winner
   passed 5 of 5 years in both sleeves. A bias that is present in every year of
   the data cannot be detected by holding years out — every fold is
   contaminated identically. This is worth carrying into every future program
   on this dataset.
3. **Every direction that raises returns raises churn**, and churn is what
   the remaining measurement error feeds on. Until sub-minute data resolves
   S11's residual, any parameter change that increases trade frequency is
   buying unverifiable return.
4. **The sleeves genuinely differ.** On V1 they want opposite directions. The
   assumption that one parameter set fits both is not supported.

## R5. Recommended next steps (not run here)

- **V17 — the trade cap, alone, with sub-minute validation.** V7 is the only
  lever worth revisiting, and B6 is exactly what sub-minute data would settle.
- **Do not re-run this grid on the same window.** It has now been seen; a
  second pass would be fitting to the same 679/691 days.
- Adopt nothing from V16.

