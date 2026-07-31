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
