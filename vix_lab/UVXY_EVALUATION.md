# UVXY — data audit and strategy fit

**Verdict: the file is excellent. The instrument is not.**

`UVXY_1min.csv` passes every quality check put to it and is the cleanest of
the three 1-minute files in this repository. Run through the locked band_lab
strategy — unchanged, same engine, same §12 constants, same 1-minute fills —
UVXY earns **16.3 gross bp/ON-day against SOXL's 42.1 and SOXS's 32.2**, and
**−1.8 bp net of the project's own cost model**. It is not an alternative
investment, not a third leg, and not a replacement for either sleeve. The
short-side VIX comparison was run too and is structurally worse.

Nothing here proposes a parameter change. §12 is untouched.

---

## 1. Is the file any good?

Yes. `vix_lab/dq_uvxy.py`.

| check | result |
|---|---|
| rows / sessions | 642,900 / **1,654** (2019-12-31 → 2026-07-31) |
| NaN cells, non-positive prices, negative volume | **0 / 0 / 0** |
| duplicate timestamps, out-of-order rows | **0 / 0** |
| `High < Low`, O or C outside `[Low, High]` | **0 / 0 / 0** |
| bars outside 09:30–15:59 | **0** |
| sessions with 390 bars | 1,642 (99.3%); the other **12 are half-days at 210**, no other count |
| intra-session minute gaps | **0** |
| calendar vs `SOXS_1min.csv` | identical, 1,654 shared sessions |

That is a better file than either sleeve's. It has no missing bars at all,
where the 5-minute files carry a source/vintage boundary at the end of 2021
(`PHASE2_PARITY.md` S12).

### 1.1 It is back-adjusted, and that matters for sizing

The series falls **1,385x** from 2019 to 2026 — an implied **−66.7%/yr**,
which is UVXY's published structural decay. A raw series would instead show
large upward jumps at each reverse split. There are only two session-boundary
jumps over 35% in six and a half years, and neither is a split:

| date | UVXY gap | VXX gap | what it was |
|---|---:|---:|---|
| 2020-03-09 | +55.3% | (no coverage) | COVID crash Monday, S&P −7.6%, circuit breaker |
| 2024-08-05 | +66.0% | **+44.1%** | yen carry unwind; VXX gapped too, so it was the market |

**Consequence, and it is the same rule SOXS already lives under
(`IMPLEMENTATION_SPEC.md` §4):** the file is usable for returns, percentage
signals and backtest fills, and must **not** be used for share sizing or
dollar levels in the pre-split era. My first pass mislabelled these two gaps
as splits by using a threshold calibrated for equities; a 1.5x VIX product
needs a wider one, and the discriminator is whether a second series gapped
with it.

### 1.2 External validation, and a real defect — in VXX, not UVXY

UVXY is 1.5x the same index VXX tracks at 1x, so the two must agree. They do,
except for one window:

| year | beta vs VXX | corr vs VXX | beta vs **VIXY** | corr vs **VIXY** |
|---|---:|---:|---:|---:|
| 2021 | 1.506 | 0.99986 | 1.523 | 0.99909 |
| **2022** | 1.529 | **0.88811** | **1.492** | **0.99910** |
| 2023 | 1.488 | 0.99945 | 1.478 | 0.99819 |
| 2024 | 1.491 | 0.99976 | 1.473 | 0.99910 |
| 2025 | 1.496 | 0.99970 | 1.505 | 0.99872 |
| 2026 | 1.493 | 0.99975 | 1.495 | 0.99844 |

The 2022 break is exactly **2022-03-14 → 2022-09-19**, 49 bad days, zero
outside that window. That is not a data error — it is the Barclays ETN
issuance suspension, and the dates match to the day:

| event | published | this data |
|---|---|---|
| Barclays suspends VXX issuance | [2022-03-14](https://www.businesswire.com/news/home/20220314005483/en/Barclays-Suspends-Until-Further-Notice-Further-Sales-and-Issuances-of-Two-Series-of-iPath%C2%AE-ETNs-the-%E2%80%9CETNs%E2%80%9D) | first bad day **2022-03-14** |
| record 33% premium to NAV | [mid-Aug 2022](https://news.bloomberglaw.com/securities-law/broken-barclays-etn-soars-to-33-premium-with-issuance-halted) | residual trough **−35.2% on 2022-08-15** |
| full resumption announced | [2022-09-19](https://www.businesswire.com/news/home/20220919005454/en/Barclays-Resumes-Further-Issuances-and-Sales-of-Certain-iPath-ETNs) | last bad day **2022-09-19** |

Confirmed against a third series: **VIXY** (a ProShares *ETF*, so creation and
redemption never stopped), fetched independently from IBKR. In the suspension
window UVXY vs VIXY reads **beta 1.4855, corr 0.99910**, while VIXY vs VXX
reads **0.79017**. VXX disagrees with *both* VIX products; UVXY agrees with
the one that was never broken.

**UVXY is clean. `VXX_5min_6Years.csv` has a six-month hole and should not be
used as a volatility reference over 2022-03-14 → 2022-09-19.**

---

## 2. The strategy on UVXY, unchanged

`vix_lab/uvxy_strategy.py`. Window 2022-01-03+ (the window S11/S12 validated),
1-minute fills, `spec` fill model, decision bars aggregated 5:1 from the
1-minute file for **all three symbols** so the rows differ only in the
security. That substitution is validated, not assumed — the 5-minute files
reproduce the published 42.5 / 34.2 exactly, and re-running the same days off
aggregated 1-minute bars costs **−0.40 bp** on SOXL and **−2.09 bp** on SOXS.

That −2.09 is not nothing, and UVXY has no 5-minute file to measure its own
substitution error against. But it is ~2 bp against a 16.3-vs-42.1 gap, so it
cannot account for the result either way.

| sleeve | ON days | ON rate | gross bp/ON-day | Sharpe | trades | win% | worst day |
|---|---:|---:|---:|---:|---:|---:|---:|
| SOXL | 685 | 59.7% | **42.1** | **2.11** | 2,157 | 69.1% | −8.00% |
| SOXS | 697 | 60.7% | **32.2** | **1.59** | 2,291 | 69.6% | −8.00% |
| **UVXY** | 488 | 42.5% | **16.3** | **0.73** | 1,671 | 70.7% | −8.00% |

Per calendar session — the number that matters for capital allocation —
SOXL delivers 25.2 bp, SOXS 19.5, **UVXY 6.9**.

Year by year, UVXY is also the least stable:

| sleeve | 2022 | 2023 | 2024 | 2025 | 2026 | yrs +ve |
|---|---:|---:|---:|---:|---:|---|
| SOXL | 50.9 | 52.3 | 38.0 | 18.8 | 48.7 | 5/5 |
| SOXS | 44.4 | −6.5 | 18.4 | 58.8 | 61.1 | 4/5 |
| UVXY | 26.9 | **−37.6** | 0.4 | 48.5 | 71.3 | 4/5 |

### 2.1 Why — three findings, two of which contradicted my expectation

**A VIX product is not the wildest thing in the room.** The gate is *more*
binding on UVXY, not less:

| symbol | median band % | ≥1% swings/day | median ATR5 | ATR5 ≥ 6 |
|---|---:|---:|---:|---:|
| SOXL | 7.10 | 7.3 | 7.35 | 74.3% |
| SOXS | 7.16 | 7.3 | 7.37 | 75.7% |
| UVXY | **5.78** | **5.6** | 6.11 | **51.5%** |

UVXY is 1.5x VIX *futures*, not 1.5x spot VIX, and the front future moves far
less than the index it settles to. It has the narrowest band and the fewest
1% swings of the three — less of exactly the raw material the strategy eats.

**The sleeve is directional, not market-neutral.** Correlation between a day's
intraday drift and that day's sleeve P&L: **SOXL +0.553, SOXS +0.620,
UVXY +0.580**. All three are long bets that pay when the instrument rises
during the session. This is *why* SOXL and SOXS are run as a pair — the pair
is what nets out direction — and it is the key to the third-leg question
below.

**UVXY's intraday drift is structurally negative.** Splitting the decay into
the part a flat-overnight sleeve escapes and the part it pays:

| symbol | overnight bp/day | **intraday bp/day** | total |
|---|---:|---:|---:|
| SOXL | +11.2 | −6.8 | +4.1 |
| SOXS | −29.9 | −32.6 | −62.2 |
| UVXY | −17.4 | **−25.1** | −42.2 |

59% of UVXY's decay is realised inside the session. A long-only intraday
sleeve pays it. 2023 is the demonstration: ON-day intraday drift −67.3 bp,
sleeve −37.6 bp/ON-day.

---

## 3. Costs — and this is what actually kills it

`vix_lab/uvxy_portfolio.py`, using `band_lab/phase1/cost_model.py` unchanged.
IBKR Pro Fixed bills **per share**, so a cheap instrument is an expensive one
to trade. UVXY closed at **$23.26**; $150K buys 6,448 shares.

| sleeve | price | shares | target exit | stop exit |
|---|---:|---:|---:|---:|
| SOXL | $158.41 | 946 | 0.92 bp | 1.24 bp |
| SOXS | $51.61 | 2,906 | 2.25 bp | 3.22 bp |
| **UVXY** | **$23.26** | **6,448** | **4.65 bp** | **6.80 bp** |

At 3.42 trades/ON-day:

| sleeve | gross bp | cost bp | **NET bp** | net Sharpe |
|---|---:|---:|---:|---:|
| SOXL | 42.1 | 3.2 | **38.9** | 1.95 |
| SOXS | 32.2 | 8.4 | **23.8** | 1.18 |
| **UVXY** | 16.3 | **18.1** | **−1.8** | **−0.08** |

**Costs exceed the entire gross edge.**

### 3.1 The obvious rebuttal, tested

The cost objection is an artifact of a $23 share price, and UVXY
reverse-splits every year or two. Does a split rescue it? `vix_lab/uvxy_stress.py`:

| UVXY price | cost bp | net bp | net Sharpe | |
|---:|---:|---:|---:|---|
| $23.26 | 18.1 | −1.8 | −0.08 | today |
| $116.30 | 4.4 | 11.9 | 0.54 | after 1:5 |
| $232.60 | 2.7 | 13.6 | 0.61 | after 1:10 |
| $465.20 | 1.8 | 14.5 | 0.65 | ceiling |

The costs do vanish. What they uncover is the 16.3 bp gross edge. **Even with
trading made free, UVXY is the weakest of the three by a factor of 2.6 on
edge and 2.9 on Sharpe.** The cost is what makes it negative; the edge is what
makes it uninteresting.

---

## 4. Is it a third leg? No — it duplicates SOXS

Sleeve P&L correlation (gross, shared ON-days):

| | SOXL | SOXS | UVXY |
|---|---:|---:|---:|
| SOXL | 1.000 | −0.755 | −0.631 |
| SOXS | −0.755 | 1.000 | **+0.585** |
| UVXY | −0.631 | +0.585 | 1.000 |

UVXY is long volatility; SOXS is short semiconductors. Both rise when risk
appetite falls, so a dip-buying sleeve on each wins on the same days. Adding
UVXY leans the book further onto the side SOXS already covers.

Regressing the UVXY sleeve on the two incumbents:

```
UVXY = +0.96 bp  −0.212*SOXL  +0.236*SOXS      R² = 0.186
alpha = +0.96 bp/session,  t = +0.12
```

**The marginal alpha is indistinguishable from zero.** Every portfolio
containing UVXY is worse than the incumbent pair, net of costs:

| portfolio | bp/session | ann % | Sharpe | max DD | worst day |
|---|---:|---:|---:|---:|---:|
| **SOXL+SOXS (incumbent)** | **24.2** | **80.0** | **2.98** | **−14.3** | −4.65 |
| SOXL+SOXS+UVXY, ⅓ each | 15.8 | 46.1 | 2.04 | −15.4 | −4.76 |
| SOXL+SOXS+UVXY, .4/.4/.2 | 19.2 | 59.2 | 2.61 | −12.9 | −4.27 |
| SOXL+UVXY (UVXY replaces SOXS) | 14.4 | 39.8 | 1.53 | −26.8 | −4.05 |
| SOXS+UVXY (UVXY replaces SOXL) | 8.8 | 17.0 | 0.62 | −46.3 | −7.49 |
| UVXY alone | −0.5 | −3.3 | −0.06 | −38.5 | −4.07 |

The one row that beats the incumbent on anything is the 20% allocation, on max
drawdown (−12.9 vs −14.3) — bought with a third of the return. Nothing here
justifies the operational cost of a third sleeve.

---

## 5. The short-side VIX question

`vix_lab/short_vol.py`. Asked properly, and it does **not** need 1-minute
data: the gate is defined on daily bars, so daily bars settle it. SVXY, SVIX
and VIXY daily history fetched from IBKR.

| symbol | multiplier | median band % | **ATR5 ≥ 6** | band < 2% |
|---|---:|---:|---:|---:|
| SOXL | 3x semis | 7.10 | 74.3% | 0.3% |
| SOXS | −3x semis | 7.16 | 75.7% | 0.3% |
| UVXY | +1.5x VIX | 5.78 | 51.5% | 1.7% |
| VIXY | +1.0x VIX | 3.87 | 20.6% | 11.4% |
| **SVXY** | **−0.5x VIX** | **1.91** | **1.9%** | **53.3%** |
| SVIX | −1.0x VIX | 3.66 | 16.3% | 13.2% |

**SVXY is structurally disqualified.** The gate turns on 1.9% of sessions and
over half its sessions spend the whole day inside a 2% band — a 1% dip and a
subsequent 1% recovery cannot fit. SVIX (−1x) at least has a real band but
still clears the gate less than a quarter as often as SOXL.

The reason is mechanical. Divide each product's median band by its
multiplier: **3.86, 3.87, 3.82, 3.66**. It is the same number four times —
they are one index at four gearings. **There is no short-vol product with
UVXY's band**, because the leveraged short-vol ETFs are deliberately built at
−0.5x and −1x. The 3x semiconductor pair has no symmetric equivalent in
volatility.

### 5.1 One argument I had to discard

The tempting objection — "a short-vol leg is just the mirror of the long-vol
leg" — is **wrong**, and the existing pair proves it:

```
SOXL vs SOXS (the APPROVED pair):  corr -0.9995
UVXY vs SVXY:                      corr -0.9984
```

The approved pair is *already* anti-correlated at −0.9995. The strategy
harvests churn, and churn is direction-free. A short-vol leg is not rejected
for being a mirror; it is rejected for not having a wide enough band.

---

## 6. What I would do with the file

1. **Keep it.** It is the best-conditioned price file in the repository and it
   cost nothing to validate. It is the natural reference series for any future
   volatility-regime work.
2. **Do not trade it, and do not add a third sleeve.** Not at $23, where it is
   net negative; not after a reverse split, where it is still the weakest of
   three and adds no marginal alpha.
3. **Fix the VXX reference.** `VXX_5min_6Years.csv` is unusable over
   2022-03-14 → 2022-09-19 through no fault of the fetch. If a VIX reference
   is wanted, **UVXY or VIXY, not VXX.**
4. **The finding that generalises** is not about UVXY. It is that the sleeve
   P&L is directional (+0.55 to +0.62 against intraday drift), so a candidate
   leg should be judged on *what it leans against*, not on whether it is a
   different asset class. On that test UVXY fails: it leans the same way as
   SOXS.

### Not done

- No walk-forward. UVXY's net edge is negative in-sample, so an out-of-sample
  test would only refine a number that has already failed.
- No 1-minute backtest of SVXY or SVIX. The daily gate analysis disqualifies
  SVXY outright; SVIX (−1x) is the only candidate a 1-minute study could
  still say something about, and it would need a data fetch that has not been
  run.
- The `spec` fill model carries the same same-bar optimism S10 flagged, now
  over a 60-second window. It is applied identically to all three symbols, so
  the comparison is fair even though each level is an upper bound.

---

## Reproducing

```bash
git lfs pull --include="UVXY_1min.csv,SOXL_1min.csv,SOXS_1min.csv,SOXL_5min_6Years.csv,SOXS_5min_6Years.csv,VXX_5min_6Years.csv"
python3 vix_lab/dq_uvxy.py         # §1  data audit
python3 vix_lab/dq_dig.py          # §1.2 the 2022 window
python3 vix_lab/uvxy_strategy.py   # §2  the strategy, all three symbols
python3 vix_lab/uvxy_portfolio.py  # §3,4 costs and portfolio
python3 vix_lab/uvxy_stress.py     # §3.1 price sensitivity, gate quintiles
python3 vix_lab/short_vol.py       # §5  the short-side VIX question
```

`uvxy_portfolio.py` and `uvxy_stress.py` read the trade logs
`uvxy_strategy.py` writes, so run that one first. Outputs land in
`vix_lab/out/`.
