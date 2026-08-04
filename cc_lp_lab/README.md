# cc_lp_lab — Covered call + long-dated protective put on SOXL

A literal backtest of the specified rule set on real 5-minute SOXL bars and real
5-minute option trade prints. **2022-01-03 → 2026-07-02, 235 weekly cycles,
$100,000 start, reinvested weekly.**

```bash
git lfs pull                                    # underlying + option data
pip install pandas numpy scipy pyarrow matplotlib openpyxl
python3 cc_lp_lab/build_option_cache.py         # 736 raw files -> 8.0M trade bars
python3 cc_lp_lab/build_eod_cache.py            # EOD chains -> strike ladder + IV
python3 cc_lp_lab/validate_pricing.py           # how good are the marks?
python3 cc_lp_lab/analyze.py                    # headline + controls + mechanism
python3 cc_lp_lab/variants.py                   # cost sensitivity + rule variants
python3 cc_lp_lab/robustness.py                 # start-week dispersion
python3 cc_lp_lab/chart.py                      # out/cc_long_put.png
```

## The rules as implemented

| Spec | Implementation |
|---|---|
| Sell weekly call 2 strikes OTM at 10:00 Monday | 10:00 ET 5-min bar of the **first trading day of each ISO week** (26 of 235 are Tuesdays — Monday holidays). Strike = 2nd **listed** strike above spot on that day's chain. Expiry = last listed expiration inside that week (Thursday in the 8 holiday weeks). |
| Hold the underlying | Long SOXL in 100-share lots, one short call per lot. |
| Buy a proportionate number of puts ~3 months out | Listed expiration nearest 91 DTE (median realised **88 DTE**), 2nd listed strike **below** spot. One put per lot. |
| Rewrite at the same strike if not called out | Strike is **sticky** across weeks; resets only when the share position is re-established (assignment or put exercise). |
| Put stays until expiry; exercise if ITM | Settled at the close of its expiry date. ITM ⇒ shares delivered at the put strike; new put bought the following Monday. |
| Start $100,000, reinvest weekly | Lots recomputed every Monday: `L = floor(liquid equity / (100·S + 100·put))`. Never levered — cash never goes negative. |

## Data and pricing — what is real and what is modelled

| Input | Source | Coverage |
|---|---|---|
| Underlying at 10:00 and at the close | `SOXL_5min_6Years.csv` | 1,510 sessions, **zero intraday gaps**. |
| Listed strike ladder, bid/ask, implied vol | `SOXL_Options_2022..2026.csv` EOD chains | 1.52M contract-days, 100% of the contracts traded. |
| Option price at 10:00 | `raw_data/SOXL_intraday_5m_exp_*.csv`, 5-min **trade** bars | 8.0M trade bars. Uses `close`; `vwap` is a carried-forward last value and is ignored (per `drift_lab/DATA_NOTES.md`). |

Mark priority per trade: **real 10:00 print → real print within ±30 min → Black-Scholes
repriced from that day's EOD implied vol to the 10:00 spot.** Of the 470 executed option
trades: **45.7% exact 10:00 print, 33.8% nearby print, 20.4% model.**

The model leg is validated, not assumed (`validate_pricing.py`, 131,647 paired
10:00-print × EOD-chain observations). Carry `r−q = 0.04` reproduces the vendor's
own EOD mid to **0.67% MAE**. Repriced to the 10:00 spot:

| contract | median error | MAE | within 10% |
|---|---|---|---|
| ~90d put, 2 strikes OTM (**where the model is used**) | +1.2% | 3.4% | **95.7%** |
| weekly call, 2 strikes OTM (**where real prints cover 97.9%**) | +8.5% | 25.4% | 38.1% |

The model is accurate exactly where it carries weight and weak exactly where it
barely matters. Short-dated cheap options are the hard case, and 97.9% of weekly
2-OTM calls had a genuine 10:00 print.

Two independent sources confirm the extraordinary 2026 tape (SOXL $48 → $267,
Mar–Jun): the 5-min feed and the option vendor's own `underlying_price` field agree
to **corr 0.999998**, and there is no overnight gap > 25% anywhere in 2022–2026, so
the whole window sits on one price basis.

## Results

Costs = $0.65/contract + $0.005/share + the **measured** half-spread (5.5% of price
on the weekly 2-OTM call, 1.9% on the ~90d put — taken from the EOD quotes).

| | final $ | total | CAGR | max DD | Sharpe |
|---|---:|---:|---:|---:|---:|
| **Strategy: CC + long put** (frictionless) | 169,144 | +66.2% | +11.98% | −60.5% | 0.48 |
| **Strategy: CC + long put** (with costs) | **122,994** | **+21.3%** | **+4.39%** | **−62.8%** | 0.34 |
| Control: covered call only | 143,261 | +39.0% | +7.61% | −87.3% | 0.57 |
| Control: shares + long put only | 204,176 | +100.0% | +16.69% | −66.9% | 0.57 |
| Benchmark: buy & hold SOXL | 261,057 | +151.2% | +22.76% | −90.4% | 0.76 |

Calendar years (2022 from 01-03, 2026 through 07-02):

| | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| CC + long put | −61.9% | +62.9% | −0.6% | +11.5% | +76.1% |
| Buy & hold | −86.6% | +224.2% | −13.1% | +53.9% | +330.7% |

P&L attribution (legs sum exactly to final − 100,000):

| | shares | calls | puts | total |
|---|---:|---:|---:|---:|
| CC + long put (with costs) | +100,378 | **−35,264** | **−42,120** | +22,994 |

**Both option legs lost money.** Together they cost $77,384 — 77% of starting capital.

## Why — the four mechanisms

**1. The sticky strike switches the income engine off.** Only 55 of 235 weeks were
"fresh" writes (median **+3.4% OTM, 3.10% of spot in premium**). The other **180 weeks
were sticky re-writes at a strike the stock had already fallen away from — median
+21.8% OTM, premium 0.26% of spot**. Median run stuck on one strike: 3 weeks; max 24.
In 2022 the median write sat **+46% OTM for 0.19% premium**. The rule collects almost
nothing precisely in the drawdowns where income is supposed to help.

**2. 80% of calls expired worthless and the leg still lost $35k.** Short gamma:
$253,641 of premium collected, $285,748 of intrinsic paid on the 47 assignments.
The 20% that finished ITM finished *far* ITM (median 5.1%, mean 8.1% past the strike).

**3. The whipsaw is structural.** Called out at strike K on Friday, rebought Monday at
market: **median +7.1% higher, and higher in 41 of 47 events (87%)**. Decomposed:
+5.1% surrendered at expiry, +0.4% weekend gap. The rule sells low and rebuys high
by construction whenever the stock trends up.

**4. The put was expensive insurance.** 19 cycles, $163,210 paid, $121,090 received,
**net −$42,120 (−42% of starting capital)**. It did its job on risk — max drawdown
−62.8% vs −87.3% without it — but on a 3× ETF at 80–110% IV, a 5%-OTM 3-month put
costs roughly 4–6% of notional per quarter, ~20% a year.

**"Two strikes" is a fixed-dollar rule on a moving stock.** The ladder is $0.50 wide
near the money (→$1.00 when spot is high), so 2 strikes meant **4.7% OTM in 2022 at
spot $19 but 1.5% OTM in 2026 at spot $65**. The rule silently tightens as the stock
rises — it caps the hardest exactly when the upside is biggest.

## Robustness — this number is not reliable, but the ranking is

Same rules, same data, only the **first Monday** changes (14 consecutive start weeks):

| | min | median | max |
|---|---:|---:|---:|
| final equity | $106,802 | $123,546 | $217,952 |
| CAGR | +1.77% | +5.00% | +19.99% |
| excess vs buy & hold over the same window | −52.8% | **−35.5%** | −18.4% |

**Final equity swings 2.0× on the start week alone, and the strategy lost to buy &
hold in 0 of 14.** The level is luck; the underperformance is not.

Put tenor is likewise non-monotonic (30d +5.0%, 60d +27.7%, 91d +4.4%, 180d +24.3%,
270d +11.0% CAGR) — differences driven by whether a given put's expiry calendar
happened to straddle the 2022 crash, not by edge.

Cost sensitivity — the whole result lives inside the spread:

| | final $ | CAGR |
|---|---:|---:|
| frictionless | 169,144 | +11.98% |
| + commissions | 152,257 | +9.39% |
| + measured half-spread | 122,994 | +4.39% |
| + double half-spread | 98,152 | **−0.65%** |

Rule variants (at realistic cost): resetting the strike to 2-OTM every week instead
of keeping it sticky is **far worse** (−25.7% CAGR, 95 assignments) — the sticky rule
is the only thing standing between this structure and being called out every week of
the 2026 melt-up. Writing further out (6 strikes, sticky) gives +17.6% CAGR.

## Caveats

- **Assignment is modelled at expiry only.** American calls can be assigned early,
  especially deep ITM around SOXL's quarterly ex-dividend. Sticky strikes go deep ITM
  here, so real-world results would be *worse*, not better.
- Cash earns 0% in the base case (a +4% variant changes CAGR by +0.16pp).
- No taxes. Assignments are short-term gains; 47 of them in 4.5 years.
- Option marks are trade prints, not quotes — a fill at the print is optimistic on
  size. The measured-half-spread column is the honest read.
- The window contains one −87% year and one +330% half-year. Four and a half years
  of a 3× ETF is a small sample of regimes, whatever the number of weekly cycles.
