# SOXL Bear Call (Call-Credit) Spread — Analytical Lab & Findings

**Question asked:** find the *optimal* call-credit spread on SOXL — **sell** a call
just out-of-the-money, **buy** a call one or more strikes higher (defined risk,
**no underlying held**) — tested at **weekly, two-week and monthly** expirations.
Start with **$100,000, invest 100%, reinvest winnings**, no commissions/taxes.
Determine whether the data supports the trade without massive drawdown, and if
there are drawdowns, **how and why**.

**Answer, from the data only: the data does not support this trade on SOXL.**
Across **96 configurations** (3 tenors × 8 strike rules × 4 widths) **zero** had
positive expectancy under realistic fills. The structure is a systematic short
position on the upside of a 3× leveraged *bull* ETF; SOXL's up-moves breach the
short strike far more often than the premium collected can pay for. Under the
literal "invest 100%" rule the account is **functionally wiped out within the
first 2–6 trades.** Details, mechanism, and the one real nuance (the entire
theoretical edge lives *inside the bid/ask spread*) are below.

> **Part 2 — the mirror image** (`FINDINGS_2_long_side_and_signals.md`): tests the
> *long / put side*, a *debit call structure*, and *regime indicators*. Short version:
> being **long** SOXL's upside (`long_call`, `bull_call` debit spreads) has strong
> positive expectancy because SOXL's volatility risk premium is **negative** (options
> are chronically cheap vs. realized); the put-credit spread mostly bleeds like the
> call-credit spread; and the intuitive timing playbook is backwards — trend-gating
> and mid-trade stops *hurt*, while buying *weakness* and sizing small are what
> actually control the (still very large) drawdowns.

> **Part 3 — active long-strangle harvesting** (`FINDINGS_3_strangle_harvest.md`):
> hold a long OTM call *and* put and actively harvest whichever leg the move
> inflates. This is the **first genuinely attractive risk/reward in the project** —
> being long SOXL's chronically-cheap volatility and banking the spikes. Best
> region **120–150 DTE, 5–10% OTM** (best cell +44% CAGR / −36% DD), harvesting
> beats buy-and-hold (fixes the 2024 decay that ruins passive strangles), and your
> frequent-harvest instinct is the right drawdown dial. Same two caveats hold:
> "invest 100%" is a −96% drawdown (fractional sizing mandatory) and the edge is
> regime-dependent (2023's steady grind was negative). See Part 4 for the intraday
> harvest model and the vol-regime rotation that neutralizes the 2023 loss.

> **Part 4 — intraday harvesting + the 2023 rotation** (`FINDINGS_4_intraday_and_rotation.md`):
> modeling harvests *intraday* (BS at the 5-min high/low with the contract's own IV)
> raises return and cuts the strangle's drawdown from −25% to −16% (return benefit
> is slip-sensitive, drawdown benefit is robust). And the 2023 failure is a
> **realized-vol collapse** (0.83 vs 0.99–1.31; VRP was ~0 in *both* 2023 and 2026,
> so vol — not VRP or trend — is the separator): a rvol-drop rotation to cash turns
> 2023 from −14% to **+11%** and lowers drawdown, at a cost of overall CAGR — a risk
> dial, not a free win. **2026 is confirmed real** (user), so that caveat is dropped.

---

## 1. How to run / reproduce (on any platform)

```bash
git lfs pull                         # data files are Git LFS (see §7)
pip install -r call_spread_lab/requirements.txt
cd call_spread_lab
python3 profile_data.py              # data-quality ground truth  -> outputs/underlying_path.png
python3 run_analysis.py              # sweep + headline + drawdown -> outputs/*.csv, *.png
python3 verify.py                    # INDEPENDENT audit (no import of the engine)
```

Files:

| file | purpose |
|---|---|
| `data_loader.py` | canonical ingest of the 5 yearly option files + 5-min underlying; handles the per-file date-format quirk (2025 is `M/D/YY`, others ISO); nothing imputed |
| `profile_data.py` | data-quality report: underlying path, tenor availability, strike grid, quote quality, a real sample chain |
| `investigate_2026.py` | cross-checks the 2026 underlying anomaly against the independent 5-min feed |
| `backtest.py` | the spread engine: whole-strike enforcement, 20% fill rule, nearest-neighbour / delta strike selection, hold-to-expiration intrinsic settlement |
| `capital_models.py` | sizing: `full_risk` (invest-100%) and `fractional`; drawdown/CAGR/expectancy stats |
| `run_analysis.py` | the study — parameter sweep, regime breakdown, drawdown attribution, fill sensitivity, plots |
| `verify.py` | independent re-derivation from the raw CSVs + Black-Scholes price sanity; **all checks pass** |
| `outputs/` | `scoreboard.csv`, per-tenor `ledger_*.csv`, `equity_curves.png`, `expectancy_heatmap.png` |

---

## 2. Data reality (measured, not assumed) — `profile_data.py`

* **Coverage:** `SOXL_Options_2022..2026.csv` = 1,516,524 daily EOD option rows,
  1,128 trading days, **2022-01-03 → 2026-07-02**. `SOXL_5min_3Years.csv` covers
  the underlying 2023-07-07 → 2026-07-09.
* **Granularity limit (important):** the option files are **one EOD snapshot per
  contract per day**. There are **no intraday option quotes anywhere.** So the
  "enter Monday 10:00 AM" idea from the older project specs is *not possible for
  option legs* — every leg here is priced at the **daily close** of the entry
  day. The 5-min file only helps for the *underlying* path. This is a data
  limitation, stated plainly, not a modelling choice.
* **Tenors are fully available:** an expiration in the weekly (4–10 DTE),
  two-week (11–18) and monthly (25–38) windows exists on 99.3% / 100% / 100% of
  days. Expirations are essentially all Fridays (240 Fri, 8 Thu holiday weeks).
* **Strikes:** 80.8% are whole-number; the spec's `strike % 1 == 0` filter drops
  the rest. Near-ATM whole strikes are $1-spaced even at high prices.
* **The traded band is liquid:** for slightly-OTM calls (0–15% OTM, 3–40 DTE)
  the zero-bid rate is **0.12%**, inverted 0%, zero-IV 0%, median bid/ask ≈ **10%
  of mid**. These spreads are genuinely constructable.
* **Price prices are real:** `verify.py` re-prices a random 400 slightly-OTM
  calls with Black-Scholes using **the data's own implied_vol** — **94.5% land
  inside the quoted bid/ask, 100% within 15% of mid.** The chain is internally
  consistent (quote ↔ IV ↔ greeks), so results are not a data artifact. (BS sits
  ≈$0.04 *below* mid → quotes are marginally *rich*, i.e. a small volatility risk
  premium exists — see §5.)

**2026 — confirmed real (updated).** From ~April 2026 the underlying rises from
~$47 to a peak of **$300** with repeated 20–30% single-day moves. This was flagged
for review because the magnitude is extraordinary; the **user has confirmed 2026
is actual market history — it is what happened.** It is also internally consistent
in the data: the options' `underlying_price` matches the independent 5-min close
at a ratio of **1.000** every month, and the strikes quoted (up to $425, clustered
at the ~$180–300 underlying) cohere with it (`investigate_2026.py`). It is a real,
extreme melt-up regime and is still reported separately for clarity, not because
it is doubted.

The regimes the backtest spans (this is why the dataset is a good test bed):

| Year | SOXL path | regime | result for a bear call spread |
|---|---|---|---|
| 2022 | $72 → $9 (−87%) | brutal bear | the **only** favorable year |
| 2023 | $9 → $31 (+240%) | strong bull | bleeds |
| 2024 | $28 → $27, ranged to $68 | volatile round-trip | bleeds |
| 2025 | $28 → $42, crashed to $8 in Apr | whipsaw | bleeds |
| 2026 H1 | $47 → $181 (peak $300) | extreme melt-up (confirmed real) | worst |

---

## 3. What was modelled

* **Structure:** sell 1 call (short), buy 1 call `width` whole-strikes higher
  (long). Net **credit**. No underlying.
  `max profit = credit`, `max loss = width − credit`, `breakeven = K_short + credit`.
* **Entry / exit:** serial, non-overlapping — enter at the entry-day close, hold
  to expiration, settle at **intrinsic** on the expiration-day underlying close
  (verified equal to the 5-min EOD), then re-enter the next trading day. Weekly ⇒
  ~Mon→Fri, etc.
* **Fills — the "20% spread rule"** (repo convention, models retail execution):
  `sell = bid + 0.20(ask−bid)`, `buy = ask − 0.20(ask−bid)`; a leg with `bid≤0`
  or `ask<bid` is illiquid and rejected. Midpoint is tested as a sensitivity.
* **Strike search:** whole strikes only; short = *k*-th strike above spot **or**
  nearest to a target delta; long = short + `width` strikes (nearest-neighbour).
* **"Invest 100%":** for a credit spread the true capital at risk / broker
  collateral per contract is `(width − credit)×100` = the max loss, so
  `contracts = floor(capital / max_loss_per_contract)`. Winnings compound.

Not modelled (stated honestly): intraday option fills (no data), early
assignment, dividends, commissions, taxes.

---

## 4. Headline result — does the data support it? **No.**

**Parameter sweep, all 96 configs ranked by mean return per $ risked
(`scoreboard.csv`): positive-expectancy configs = 0.** Range −26.7% … −1.7% per
trade. The best *survivable* (risk-10%/trade) equity of any config still ends at
**$87,033 (−13%)** over 4.5 years; the worst at $8,797.

User's literal structure — **sell 1st OTM strike, long +1 strike:**

| tenor | trades | win% | breach% | max-loss% | credit/width | **mean RoR/trade** | invest-100% outcome |
|---|--:|--:|--:|--:|--:|--:|---|
| Weekly  | 207 | 59.4% | 44.0% | 29.5% | 30.2% | **−8.1%** | ruined **trade #2** (2022-01-10, SOXL +7%) |
| Two-week| 110 | 56.4% | 47.3% | 40.0% | 32.2% | **−15.8%** | ruined **trade #5** (2022-03-14, SOXL +51%) |
| Monthly |  47 | 48.9% | 51.1% | 48.9% | 29.5% | **−26.7%** | ruined **trade #6** (2022-06-27, SOXL +26%) |

Equity over the full 4.5 years (compounding, `equity_curves.png`):

| sizing | weekly | two-week | monthly |
|---|--:|--:|--:|
| invest 100% | **$18** | **$3** | **$8** |
| risk 5%/trade | $38,823 (−61%) | $39,598 (−60%) | $52,290 (−48%) |
| risk 10%/trade | $11,964 (−88%) | $13,352 (−87%) | $25,036 (−75%) |
| risk 20%/trade | $742 (−99%) | $1,356 (−99%) | $4,875 (−95%) |

Longer holding is strictly worse (more time for SOXL to run through the short
strike). Every sizing loses; the only question is how fast.

---

## 5. *Why* it fails (the mechanism)

**(a) The payoff asymmetry needs a win rate the data doesn't deliver.** A credit
spread's breakeven win rate ≈ `1 − credit/width`.
* Near-ATM, 1-wide: collects ~30% of width → needs **~70%** wins; **got 59%**.
* Far-OTM (0.10Δ), wide: collects ~2.6% of width → needs **~97%** wins; **got 89%**.

Wherever you sit on the risk curve, SOXL's realized upside breaches the short
strike **more often than the premium pays for.** You cannot out-select it with
strikes or width — you only trade a "small loss often" for a "large loss rarely"
at the same negative expected value.

**(b) The loss is one-sided and it is SOXL's upside.** Weekly per-trade RoR
bucketed by the SOXL move over the hold:

| SOXL move | share of trades | mean RoR | max-loss rate |
|---|--:|--:|--:|
| < −10% | 23% | +49% | 0% |
| −10…−3% | 16% | +46% | 0% |
| flat ±3% | 20% | +33% | 0% |
| +3…+10% | 15% | −65% | 48% |
| **> +10%** | **25%** | **−95%** | **89%** |

**98% of all lost capital comes from SOXL up-moves greater than +3%** — and SOXL,
a 3× bull ETF, rises >3% in a week ~40% of the time and >10% **a quarter** of all
weeks. The strategy is structurally short exactly the fat right tail this
instrument is built to produce.

**(c) The only edge is inside the bid/ask — and execution eats it.** Fill
sensitivity, weekly:

| fill model | credit/width | mean RoR/trade |
|---|--:|--:|
| **midpoint** (optimistic) | 37.0% | **+3.7%** |
| **20% spread rule** (realistic) | 30.2% | **−8.1%** |

At true mid there *is* a thin positive edge — the volatility risk premium the BS
check detected. But paying ~20% into each leg's spread (round-trip on two legs)
costs ~12% of risk per trade and **turns the edge negative.** On weekly SOXL
spreads the VRP is real but **smaller than the cost of harvesting it.** This is
the single most important, and most easily overlooked, finding.

---

## 6. Drawdown — how and why (direct answer)

* **Under the stated rule (invest 100%, reinvest): the drawdown is total.** One
  maximum-loss expiration sizes at `floor(capital / max_loss)` contracts, so a
  spread that finishes above the long strike loses ≈ the entire account. It
  happened on **trade #2** (weekly), in **2022 — the year the strategy was net
  positive on an un-sized basis.** A favorable year still contains individual
  +7% SOXL weeks, and one is enough. `equity_curves.png` (right) shows the
  vertical wipe.
* **Under survivable sizing the drawdown is a relentless grind, not a single
  event:** −68% to −92% max drawdown at 10% risk. It is not a hedging tweak or a
  strike choice away from working — it is the strategy's expected value made
  visible.
* **Why:** §5. The drawdown is the accumulation of rare-but-huge losses on SOXL
  rallies overwhelming frequent-but-tiny credits, with realistic execution
  removing the only compensating edge.

---

## 7. Notes, limitations, and honest boundaries

* **Regime, not alpha.** The strategy made money only in 2022's −87% collapse.
  "Optimizing" it is really *timing SOXL lower*; as a repeatable weekly income
  trade the 2022–2026 data gives no support. If a user has a genuine bearish
  view, this is a defined-risk way to express it — but that is a directional bet,
  not income.
* **This is not a claim that credit spreads never work** — it is specific to
  **calls on SOXL** (a bull-biased 3× ETF) at realistic retail fills over this
  sample. (The repo's other files explore put-side/collar structures; different
  problem.)
* **Git LFS:** all `*.csv` data are LFS-tracked. Without `git lfs pull` the CSVs
  are ~130-byte pointer files and every loader raises a clear "still a Git LFS
  pointer" error.
* **Verification (`verify.py`, all PASS):** re-loads the raw files; recomputes 25
  random trades' credit and settlement P&L from scratch (match to <1e-16); prices
  400 calls with Black-Scholes from the data's own IV (94.5% inside bid/ask);
  and independently reconfirms the negative expectancy and the 98% up-move
  attribution — without importing the backtest engine.
