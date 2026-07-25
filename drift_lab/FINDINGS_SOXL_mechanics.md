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

### 5. Fees & financing drag — CONSISTENT with 0.75% + swap financing
The decay regression's intercept isolates the drag that is *not* volatility:
**≈ −5.5%/yr**. The fund's stated net expense is 0.75%/yr, so the balance (~4–5%/yr) is
**swap financing** (the cost of ~2.4× borrowed notional at 2022–26 short rates) plus
dividend/tracking terms — exactly the SAI's listed factors (c) financing, (d) expenses,
(e) dividends. (Precise split needs the index's total-return vs price definition; SOXX
here is a price series.)

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

## Tie-back to the option / "drift" work
The 111% realized vol and 3× structure are exactly why the earlier drift study measured
**~4.5× near-ATM option elasticity** and very rich premiums — the options are priced off
this 3×-leveraged underlying. Nothing in the fund mechanics changes the drift
conclusions; it explains their magnitude.

## Honest limitations / what would sharpen this
- **SOXX ≠ the index exactly.** SOXX is a faithful 1× proxy (R² 0.997 vs SOXL implies
  it), but for a to-the-basis-point fee/financing decomposition you'd want the
  **ICESEMIT total-return index series itself**, and the fund's **daily swap financing
  rate** (in the annual report), to split the ~5.5%/yr drag cleanly.
- The **close-exposure tracking** claim (§6) needs the fund's **intraday NAV / holdings**,
  not prices, to test.
- One housekeeping note: a **`.env` file was committed to `main`** in this batch — if it
  holds any keys/secrets, rotate and remove it from history; I did not open it.

## Reproduce
```bash
git lfs pull --include="SOXL_5min_6Years.csv,SOXX_5min_6Years.csv,SOXL.csv"
python3 drift_lab/verify_leverage.py
```
