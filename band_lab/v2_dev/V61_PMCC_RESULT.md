# V61 — The PMCC, measured against V60's bar. Not adopted.

Tested against `V60_PMCC_BAR.md`, committed before the code existed.

    python3 band_lab/v2_dev/pmcc_backtest.py
    python3 band_lab/v2_dev/pmcc_backtest.py --since 2024-01-02     # V22's window
    python3 band_lab/v2_dev/pmcc_backtest.py --cash-apy 0.045       # sensitivity

Full option chain, 2022-01-03 → 2026-07-02, 1,128 trade dates. Delta-matched
sizing, full spread crossed on every leg, $0.65 a contract a side, idle cash at
0%. 15 configurations: 9 PMCC cells and 6 controls.

## Verdict

**Not adopted. 4 of 8 gates pass; V60 requires all eight. 0 of 9 cells beat
buy-and-hold on MAR.**

Headline cell `pmcc L0.80/S0.100`: total **+124%**, CAGR **+19.7%**, max drawdown
**−84.7%**, **MAR 0.23**.
Benchmark buy-and-hold SOXL: CAGR **+22.8%**, max drawdown **−90.3%**,
**MAR 0.25**.

| bar | test | result | |
|---|---|---|---|
| B1 | beats buy-and-hold on MAR | **0.23 vs 0.25** | **FAIL** |
| B2 | beats BH on MAR in ≥ 4 of 5 years | **0 of 5** | **FAIL** |
| B3 | every cost charged, in the ledger | $35,964 across 15 configs | PASS |
| B4 | ≥ 7 of 9 cells beat BH on MAR | **0 of 9** | **FAIL** |
| B5 | headline within 1 SE of grid median | 0.28 SE | PASS |
| B6 | max drawdown strictly lower than BH | −84.7% vs −90.3% | **PASS** |
| B7 | beats the `long_only` control on MAR | 0.23 vs 0.20 | **PASS** |
| B8 | no quarter > 50% of P&L | 239% | **invalid — see below** |

## The two claims that were true, and still lost

This is not a structure that does nothing. **Both of its mechanical claims hold.**

**B6 passes.** The drawdown really is lower — −84.7% against the shares' −90.3%,
and every one of the nine cells is below the benchmark. Owning a floored call
instead of shares does reduce the loss.

**B7 passes, and I predicted it would fail.** V60 recorded the expectation that
the short leg would add nothing and the honest conclusion would be "hold a
deep-ITM call instead of shares." Wrong: the PMCC beats `long_only` on MAR at
every long delta tested (0.23 vs 0.20 at the headline). The covered-call overlay
earns its place.

They lose anyway, because the return given up is larger than the drawdown saved.
19.7% CAGR against 22.8% is −3.1 points of return to buy 5.6 points of
drawdown, and at these drawdown levels that trade is not worth making.

## The decomposition, which is the useful part

| structure | CAGR | maxDD | MAR |
|---|---|---|---|
| buy-and-hold shares | **+22.8%** | −90.3% | **0.25** |
| `covered_call` — shares + the same short calls | +19.5% | −85.6% | 0.23 |
| `pmcc` — long call + the same short calls | +19.7% | −84.7% | 0.23 |
| `long_only` — the deep-ITM call alone | +17.4% | −86.6% | 0.20 |

**Replacing the shares with a deep-ITM call buys almost nothing.** `covered_call`
and `pmcc` land on the same MAR to two decimals. The call-replacement leg — the
whole "stock replacement" thesis, and the reason R2 was recommended — contributes
0.00. What little the structure does is done by the short-call overlay, and the
overlay applied to plain shares does it just as well and with less machinery.

## A structural failure worth naming

**On 13% of days the PMCC cannot sell a covered call at all.**

The short leg's strike sits at a stable 1.11–1.18× spot across every year in the
sample. The long leg's strike was fixed 120–180 days earlier at the *then*
prevailing price. So whenever SOXL has fallen more than roughly 15% since the
long leg was opened, **every strike at the target short delta lies below the long
strike**, and selling one would invert the diagonal rather than cover it. The
engine refuses those — 144 of 1,128 dates on the headline config, 1,326 across
all configs.

The income engine switches itself off in drawdowns, which is exactly when the
income was supposed to help. That is not a tuning problem; it follows from
pairing a slow-moving long strike with a fast-moving short one.

## Reconciling with V22, which is why this test existed

V22 reported R2 at **MAR 1.61 against a benchmark of 0.98** and observed the
benchmark had never been computed. Three things separate that from what is above,
and the first is measurable to the digit.

**1. The endpoint.** V22's window ends 2026-07-17. The option chain ends
2026-07-02. In those two weeks SOXL fell **−25.3%**, from $181.03 to $135.29:

| window from 2024-01-02 | SOXL total | benchmark MAR |
|---|---|---|
| to 2026-07-17 — V22's endpoint | **+383%** | **0.98** |
| to 2026-07-02 — where the chain ends | +546% | **1.26** |

V22's +383% reproduces exactly, so the harness agrees with V22 on the benchmark.
But the benchmark's own MAR moves from 0.98 to 1.26 on a two-week shift. **Part
of "R2 beats buy-and-hold" was where the window stopped.**

**2. Fill.** V22's audit found the prior engine charged 0.6× the spread. That is
rung D of the V58 ladder. This charges the full quote.

**3. Sizing.** V22's R2 held the same *notional* as a 75% share position, so it
carried **0.75× the share delta** and part of its lower drawdown was simply a
smaller position. V60 delta-matched it for exactly this reason.

On V22's own start date, run to where the chain ends: **best PMCC 1.19 against a
benchmark of 1.26 — 0 of 9 cells beat it.** The +0.63 advantage becomes −0.07.

**What this does not establish:** I cannot run the PMCC to V22's 2026-07-17
endpoint, because the option chain ends two weeks earlier. So I cannot say
whether R2 would have beaten a 0.98 benchmark under full spread crossing and
delta-matched sizing. What is established is that on every window this data can
actually test, it does not.

## A gate of my own that was badly written

**B8 is invalid and I am striking it rather than counting it.** It required no
calendar quarter to contribute more than 50% of total P&L. The headline cell
scores 239% — but **buy-and-hold itself scores 200%**, and `long_only` 243%.

When total P&L is modest and quarterly swings are enormous, max-quarter over
total exceeds 100% for anything holding this underlying. The gate measures
SOXL's own P&L concentration, not a defect in the structure, and no structure
tradeable on this instrument could pass it. It should have been written against
the benchmark's concentration rather than an absolute 50%.

The verdict does not depend on it: B1, B2 and B4 fail on their own.

## Sensitivity: idle cash at 4.5%

Delta-matched sizing leaves most of the capital uninvested, so this matters and
V60 named it in advance as a sensitivity rather than a headline.

Best cell rises to **MAR 0.28 against the benchmark's 0.25** — a single cell
passing B1. It changes nothing: **1 of 9 cells** clears the benchmark against
B4's requirement of 7, and the best year-count is **1 of 5** against B2's 4.
A structure that needs T-bill income on its unspent cash to edge past the
benchmark in one corner of a nine-cell grid has not produced an edge.

## What this settles

The only benchmark-beating number in this repository has now been tested and it
does not survive. That closes V22's open item.

The residue worth keeping is narrow and real: **a short-call overlay on SOXL
shares recovers about 5 points of drawdown for about 3 points of CAGR.** It does
not beat holding on MAR here, but it is the only structure in this project whose
two component claims both measured true. If anything in this sequence deserves a
further look it is `covered_call`, on its own terms, not the PMCC — and not on
this sample, which contains one bear and one melt-up.

## Known omissions, as named in V60

Early assignment on the short call is not modelled and SOXL pays dividends —
still the largest unmodelled risk. EOD quotes only, so no intraday roll or
defense; this is the set-and-forget version of R2 and weaker than the strategy as
written. 4,066 stale marks across 15 configs where a quote vanished and the last
mark was carried. Whole-contract rounding at $100,000. One underlying, one
window, one bear regime.
