# How SOXL's stated mechanics show up in the data

**Documents reviewed** (uploaded to `main`): `SOXL-SOXS-Fact-Sheet.pdf` and
`SAI_Combined3XShares.pdf` (Statement of Additional Information, supplement dated
2026-06-26). **Reference data added:** `SOXX_5min_6Years.csv` (the 1× iShares
Semiconductor ETF on the same index) and `SOXL.csv` (SOXL holdings, 2026-07-23).
Every number below is reproduced by `drift_lab/verify_leverage.py`.

The short version: **the fund does exactly what the documents say, and the data
confirms it to within a few percent on every testable claim.**

## What the documents state

- **Objective:** *"daily investment results, before fees and expenses, of 300% … of
  the performance of the NYSE Semiconductor Index (ICESEMIT)"* — the 30 largest
  U.S.-listed semis. Explicitly **daily**: *"should not be expected to provide three
  times … the benchmark's cumulative return for periods greater than a day."*
- **Structure:** exposure obtained via **swaps and futures** (a "short-term trading
  vehicle"); **net expense 0.75%/yr** (gross 0.91%).
- **Path-dependence:** an *"Effects of Compounding"* one-year table — at 0% index
  return the fund returns **−3.0% at 10% vol, −17.1% at 25% vol** — driven by
  *"a) index performance b) index volatility c) financing rates d) fund expenses
  e) dividends f) time."*
- **Intraday risk:** *"unlikely the Fund will be perfectly exposed to the Index at the
  end of each day … over- or under-exposure increases on days when the Index is
  volatile near the close."*

## Claim-by-claim, against the data

### 1. "300% of the daily return" — CONFIRMED (2.99×)
Regressing SOXL's daily return on SOXX's (2020-07 → 2026-07, the 2021-03-02 15:1
split day dropped):

```
r_SOXL = −19bp + 2.988 · r_SOXX     R² = 0.9969     n = 1,503
```
Realized daily leverage **median 2.965**, IQR [2.88, 3.08]. **Every single year** is
on-target: β = 2.98 (’20), 2.99 (’21), 2.99 (’22), 2.96 (’23), 3.02 (’24), 2.97 (’25),
2.99 (’26), R² ≥ 0.993 throughout. Realized vol scales the same way: **SOXX 37% → SOXL
111% (×2.99).** The 3× is not approximate — it is delivered day in, day out across the
2022 crash, the 2023–24 recovery, and the 2026 melt-up.

### 2. The 3× holds intraday too — CONFIRMED (2.98×)
Bar-by-bar on 5-minute data: `r_SOXL = 2.976 · r_SOXX`, **R² = 0.962** (n = 115k). The
lower R² vs daily is microstructure noise (non-synchronous prints between two ETFs),
not leverage drift — the slope is still 3.0. So the leverage is maintained
continuously through the session, exactly as a swap-based structure implies.

### 3. "Not 3× for periods > 1 day" / compounding — CONFIRMED, law recovered
This is the single most important mechanic and the data reproduces its **exact law.**
Regressing the multi-day shortfall on realized variance (SOXX is an independent 1×, so
this is **not** circular):

```
(ln SOXL − 3·ln SOXX) = −46bp + (−3.10) · RealizedVariance_SOXX   per 21-day window
```
Theory for an L× daily-reset fund is a slope of **−L(L−1)/2 = −3.00**; the data gives
**−3.10.** This is the same −3σ² law behind the SAI's own table (0% index @ 10% vol →
−3σ² = −3.0%, matching their −3.0%). The consequence is visible at horizon: over the
full 6 years SOXX returned **+509%**, and SOXL returned **+1,156% — only 2.27×, not 3×**
(3× the cumulative would have been +1,527%). In *single* trending years SOXL *beats* 3×
(2023: +224% vs 3×index +144%); over multi-year windows containing the 2022 crash the
variance drag dominates. This is precisely the daily-reset path-dependence, and it is
**why the fund reverse/forward-splits** (the 15:1 on 2021-03-02 is in the data) and is
labelled a short-term vehicle.

### 4. "Obtained via swaps" — CONFIRMED on the balance sheet
The holdings sheet decomposes the 300% exactly:

| sleeve | % of NAV |
|---|--:|
| physical semiconductor stocks (AMD, NVDA, MU, AVGO, …) | **63.3%** |
| **ICE Semiconductor Index total-return swaps** | **236.7%** |
| **= total index exposure** | **300.0%** |
| cash / Treasury money-market (swap collateral) | 54.4% |

The swaps are literally line-itemed *"ICE SEMICONDUCTOR INDEX SWAP"* — the same index as
SOXX and the fact sheet — and physical + swap sums to **exactly 300%.** The large cash
block is collateral, not a directional position (my first pass mis-labelled it as cash
exposure; corrected here).

### 5. Fees & financing drag — DECOMPOSED, and the financing identified by the rate cycle
SOXL's shortfall vs "3× the index" has two parts. The big one is the **volatility
decay** above (−3σ², tens of %/yr in volatile years). What's left after removing it is a
**structural residual**, and its *time profile* proves what it is:

| year | volatility decay | structural residual | ~avg fed funds |
|--:|--:|--:|--:|
| 2020 | −10.4% | **+2.0%** | 0.1% |
| 2021 | −27.4% | **−1.7%** | 0.1% |
| 2022 | −58.1% | −3.7% | 1.9% |
| 2023 | −24.3% | −9.1% | 5.0% |
| 2024 | −36.4% | **−12.4%** | 5.1% |
| 2025 | −47.2% | −10.0% | 4.4% |

The residual is **≈0 in the 2020–21 ZIRP years and grows to −10…−12%/yr once rates hit
~5%.** Across 2021–25 it correlates with the fed funds rate at **−0.96**, with a slope of
**−1.96 ≈ −(L−1) = −2** — i.e. **≈ 2× the short rate.** That is exactly swap financing on
the ~2× borrowed notional a 3× fund carries. So the drag decomposes as:

- **volatility decay** = −3σ² (measured −3.10; the SAI's own compounding table), *plus*
- **swap financing** ≈ 2 × the short-term funding rate (0% at ZIRP → ~10–12%/yr at 5%), *plus*
- **expense** 0.75%/yr (stated; it's the small piece left at ZIRP).

These are precisely the SAI's listed factors (b) volatility, (c) financing, (d) expenses.
The financing is no longer a guess — its −0.96 correlation with the rate cycle and its
−2 slope pin its identity from the data alone.

### 6. "Over-/under-exposed when volatile near the close" — NOT visible in price
The one claim the data does **not** corroborate at the price level: realized
open→close leverage stays centered on 3.0 on both calm and volatile days, and
|leverage − 3| shows **no correlation with intraday volatility (corr −0.01).** This is a
statement about the fund's *NAV exposure vs the index at the 4pm mark* — a
holdings/tracking quantity that price data cannot isolate — so this is a limit of the
data, not a contradiction. Relatedly, the end-of-day rebalance leaves only a faint,
untradable footprint in SOXL's own price: last-15-min drift ~+8bp on up-days and ~−7bp
on big down-days (corr +0.06 on big-move days), with close-bar volume 2.4× an average
bar — within the normal U-shape, not a distinct rebalance spike.

## Can you trade these mechanics? (rebalance predictability + leading indicators)

**Is the daily rebalance predictable? Yes — deterministically.** A 3× fund must trade
`L(L−1)·AUM·r = 6·AUM·r` of index exposure at the close to reset for tomorrow — **buy on
up days, sell on down days.** At SOXL's ~$23B NAV that's **~$1.4B per 1% index move
(~$4B on a 3% day)**, plus SOXS in the same direction. **Timing is fixed** (at/near the
16:00 close); **size and sign are situational** — a known function of *that day's* index
move, readable in real time from SOXX. So it is both time-based *and* situational, and
predictable in principle.

**Does the index lead? Mechanically yes, tradeably no.** SOXX leads SOXL only in the
trivial 3× sense (the reverse lead-lag is ~0; the forward edge is sub-tick — see the
drift work). The one genuine leading indicator is that the intraday SOXX move tells you
the close rebalance flow in advance — but its **price impact is not monetizable in this
data:**

- **No end-of-day momentum in the index:** open→15:30 predicts 15:30→close at corr
  **+0.02** (nil). The ~$4B flow is smoothed by swap-dealer pre-hedging and doesn't push
  SOXX in a tradeable way.
- **A weak overnight reversal exists** (close run-up → overnight, corr **−0.087**; strong
  up-closes fade −9bp, weak closes bounce +30bp) — but it tracks the **last-25-min** move,
  **not the day's move**, so it is generic close-print mean-reversion, *not* an LETF-flow
  signature. Traded ("fade the close overnight" on SOXX) it is ~Sharpe 1 gross but **52%
  hit, ~+10bp/trade against 77bp median overnight risk**, degrading to ~0.7 after spread
  and fat overnight tails — marginal and fragile, and not actually the rebalance.
- **Data gap:** the underlying 5-min series ends 15:55, so the **16:00 closing auction —
  where the MOC rebalance actually prints — is not captured.** Testing the LETF impact
  seriously needs closing-auction / MOC-imbalance data.

**The one mechanic that is genuinely a trade is the volatility decay — but it's short
vol, not free money.** The −3σ² decay is large (~−40%/yr at 37% index vol; measured
−3.10), harvestable by shorting the fund (or delta-neutral shorting the SOXL/SOXS pair).
But borrow costs eat it, and you are short gamma: the 2023 (+224%) and 2026 (+277%)
trends would obliterate a naive short. It pays in chop and blows up in trends. The
financing (~2× rates) you simply pay as a holder — the actionable takeaway is the SAI's:
**SOXL is a short-term vehicle; don't carry it.** Reproduce: `rebalance_tradability.py`.

**The decay/carry harvest, measured (short-SOXL / long-3×SOXX, daily-rebalanced, real
data).** Gross it looks like a goldmine — **~8%/yr, Sharpe 2.46**, worst day −1.8%, and it
*rises with rates* (Sharpe 4–5 in 2023–25). But that gross carry **is SOXL's financing
drag**, and to hold the leveraged hedge you must fund $2 at ~the same short rate — which
offsets it almost exactly: 2023 net −0.6%, 2024 +1.5%, 2025 +1.8%, 2026 −1.0%. **Net ≈
breakeven** (−1%…+2%/yr) before daily-rebalance costs — you can't harvest the financing
because replicating the position pays it back. Daily rebalancing also does **not** capture
the σ² decay (it resets with the fund); capturing that means *not* rebalancing, which
reintroduces the naive-short blow-up (short SOXL unhedged: **−224% in 2023, −277% in
2026**). Reproduce: `decay_harvest.py`.

*The SOXL/SOXS pair is the one genuinely-different case and is still open:* shorting both
funds needs **no leveraged long to fund** (you hold the short proceeds as cash), collects
**both expense ratios** (0.75% + 1.00%), and hinges on **SOXS's rate sensitivity** (an
inverse fund can *earn* on its cash in high-rate regimes) and **borrow on both legs**.
Those are real frictions a synthetic SOXS would fabricate, so settling it needs **actual
SOXS 5-min data** (not yet in the repo).

## Tie-back to the option / "drift" work
The 111% realized vol and 3× structure are exactly why the earlier drift study measured
**~4.5× near-ATM option elasticity** and very rich premiums — the options are priced off
this 3×-leveraged underlying. Nothing in the fund mechanics changes the drift
conclusions; it explains their magnitude.

## Honest limitations / what would sharpen this
- **SOXX vs the index.** SOXX is validated as a faithful proxy against the fact sheet's
  *own* published ICESEMIT returns — SOXX price runs ~1.5%/yr under ICESEMIT-TR (its
  0.35% fee + dividend payout), and matches YTD/1Y/3Y/5Y to within ~1–2%/yr. I tried to
  pull the raw index (`^ICESEMIT` total return is on Yahoo Finance) for a per-basis-point
  cross-check, but **this session's egress policy blocks financial-data hosts**
  (query1.finance.yahoo.com → 403), so it is not fetchable from here. It isn't needed for
  the decomposition — the rate-cycle identification (§5) resolves the financing without
  it — but if you upload `^ICESEMIT` daily TR levels I can add the pure-index version, and
  the fund's **annual report** would give the exact *contractual* swap financing rate.
- The **close-exposure tracking** claim (§6) needs the fund's **intraday NAV / holdings**,
  not prices, to test.
- One housekeeping note: a **`.env` file was committed to `main`** in this batch — if it
  holds any keys/secrets, rotate and remove it from history; I did not open it.

## Reproduce
```bash
git lfs pull --include="SOXL_5min_6Years.csv,SOXX_5min_6Years.csv,SOXL.csv"
python3 drift_lab/verify_leverage.py
```
