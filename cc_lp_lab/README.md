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

## Follow-up: three proposed fixes, each alone and in every combination

`factors.py` (single path) · `factor_robust.py` (14 start weeks) · `benchmarks.py`

| | fix | canonical setting |
|---|---|---|
| **F1** | early assignment on the sticky strikes | short call taken away once time value < 0.3% of spot |
| **F2** | scale-invariant strike instead of "two strikes" | fresh write at 0.20 delta |
| **F3** | ratio put instead of 1:1 | 0.5 puts per lot |

### All 8 combinations, median over 14 start weeks (realistic costs)

| config | CAGR min | **median** | max | median max DD | vs buy & hold | beat B&H | spread |
|---|---:|---:|---:|---:|---:|:--:|---:|
| baseline | +1.8% | **+5.0%** | +20.0% | −61.7% | −35.5% | **0/14** | 2.0× |
| F1 | +2.5% | **+5.6%** | +20.8% | −61.8% | −34.8% | **0/14** | 2.0× |
| F2 | +12.4% | **+16.4%** | +26.5% | −58.0% | −24.9% | **0/14** | 1.6× |
| F3 | +9.7% | **+16.2%** | +34.2% | −70.3% | −24.0% | **0/14** | 2.3× |
| F1+F2 | +12.4% | **+16.4%** | +26.5% | −58.0% | −24.9% | **0/14** | 1.6× |
| F1+F3 | +10.3% | **+17.1%** | +34.8% | −70.3% | −23.0% | **0/14** | 2.3× |
| F2+F3 | +21.7% | **+27.5%** | +40.1% | −66.4% | −14.1% | **0/14** | 1.7× |
| F1+F2+F3 | +21.7% | **+27.5%** | +40.1% | −66.4% | −14.1% | **0/14** | 1.7× |
| *buy & hold* | *+22.8%* | ***+41.2%*** | *+57.6%* | *−88.0%* | — | — | *2.7×* |

**Every combination lost to buy & hold in 0 of 14 start weeks.** F2+F3 more than
quintuples the baseline (+5.0% → +27.5%) and is still 14 points behind.

### F1 — early assignment is close to a non-event, contrary to the caveat above

The 0.1% and 0.3% threshold paths differ on **7 of 1,128 days** (max $235) and
reconverge to **exactly $0.00**. The reason is structural: **shares + a deep-ITM
short call are already locked at the strike**, so early exercise realises value
you already had. It reallocates P&L between legs (shares +145,340 / calls −77,472
becomes +154,232 / −86,364) with the sum unchanged to the cent. It only costs you
when the stock falls back below the strike afterwards — 3 of 13 cases here, never
enough to change the integer lot count. Median effect: **+0.6pp of CAGR.**

### F2 — it works mechanically, but delta is not the reason it helps

Delta targeting hits its mark: realised delta **median 0.196, 100% of writes in
0.12–0.30**, holding **8–14% OTM every year** where "two strikes" drifts from 4.7%
OTM (2022) to 1.5% (2026). But isolating the strike rule shows delta is *not* the
best choice — **distance is the only dial that matters**:

| fresh-strike rule | CAGR median | median max DD | return / DD |
|---|---:|---:|---:|
| 2 strikes (as specified) | +5.0% | −61.7% | 0.08 |
| 0.20 delta | +16.4% | −58.0% | 0.28 |
| 6 listed strikes | +23.7% | −72.0% | 0.33 |
| 10% fixed OTM | **+27.9%** | −59.6% | 0.47 |
| *buy & hold* | *+41.2%* | *−88.0%* | *0.47* |

Delta *tightens in calm markets*, which cost it 2023. Every one of these rules is
just a different amount of upside surrendered; the limit of the dial is writing no
calls at all.

### The benchmark that settles it — could you just hold less?

A covered call trades upside for a smaller drawdown. So can a static allocation,
with no options at all (w × SOXL + cash, rebalanced weekly, same 14 windows):

| w | CAGR median | median max DD | return / DD |
|---|---:|---:|---:|
| 0.25 | +21.9% | −34.1% | **0.64** |
| 0.35 | +29.2% | −45.3% | **0.64** |
| **0.45** | **+35.3%** | **−55.1%** | **0.64** |
| 0.55 | +40.1% | −63.6% | 0.63 |
| 0.65 | +43.4% | −70.8% | 0.61 |
| 1.00 | +41.2% | −88.0% | 0.47 |

**Static 45% SOXL / 55% cash returns +35.3% at −55.1% drawdown — more return AND
less drawdown than the best call-writing variant (+27.9% at −59.6%), and than the
best full combination F2+F3 (+27.5% at −66.4%).** The option overlay is dominated
on both axes by a position you can hold with no options, no assignments and no
spread. Every static weight from 0.25 to 0.65 scores 0.61–0.64 on return-per-
drawdown; no call-writing variant tested exceeds 0.47.

### Verdict

The fixes work in the direction predicted — F2 and F3 are each worth ~11pp of CAGR
and are close to additive — but they improve a structure that should not be run on
this instrument over this window. F1 is a non-event and can be dropped from the
risk list. The honest summary: **on 2022–2026 SOXL, selling calls against the
position never paid, at any strike rule, any put ratio, or any start week.**

## Follow-up 2: re-strike the call every Monday instead of holding the strike

`reset_rule.py`

Rule tested: when the call expires worthless the shares are kept, but the next
week's call is written **two listed strikes above Monday's 10:00 spot** rather
than at the old strike. Put leg unchanged. This removes the sticky behaviour
entirely — every week's strike is re-based to the market.

**It is the single worst variant tested anywhere in this lab.**

| single path, realistic costs | final | CAGR | max DD | assigned | median %OTM | premium | intrinsic paid | whipsaw | days flat |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 strikes, **STICKY** (original spec) | 122,994 | +4.39% | −62.8% | 47 (20%) | 13.9% | 253,641 | 285,748 | +7.1% | 52 |
| 2 strikes, **RESET** (this rule) | **26,752** | **−25.66%** | −84.9% | **95 (41%)** | 3.4% | 255,423 | 305,620 | +10.0% | **108** |
| RESET at 3 strikes | 39,175 | −19.11% | −78.5% | 80 (34%) | 5.5% | 234,014 | 294,648 | +8.4% | 84 |
| RESET at 4 strikes | 59,426 | −11.40% | −71.8% | 64 (27%) | 7.9% | 230,060 | 294,694 | +8.7% | 69 |
| RESET at 6 strikes | 102,056 | −0.10% | −68.8% | 44 (19%) | 12.5% | 201,786 | 264,729 | +7.3% | 48 |
| RESET at 10% fixed OTM | 73,913 | −6.87% | −72.7% | 52 (22%) | 10.1% | 164,101 | 213,106 | +8.1% | 57 |
| RESET at 0.20 delta | 98,765 | −0.66% | −62.6% | 53 (23%) | 10.1% | 167,583 | 211,680 | +6.6% | 58 |

### Over 14 start weeks — sticky beats reset at every matched distance

| config | CAGR min | **median** | max | median max DD | return / DD |
|---|---:|---:|---:|---:|---:|
| 2 strikes RESET | −29.4% | **−24.7%** | −22.8% | −85.0% | −0.29 |
| 10% OTM RESET | −6.9% | **−5.9%** | +2.2% | −72.7% | −0.08 |
| 6 strikes RESET | −0.1% | **+3.3%** | +9.7% | −66.1% | 0.05 |
| 2 strikes STICKY | +1.8% | **+5.0%** | +20.0% | −61.7% | 0.08 |
| 6 strikes STICKY | +17.6% | **+23.7%** | +30.5% | −72.0% | 0.33 |
| 10% OTM STICKY | +23.2% | **+27.9%** | +44.0% | −59.6% | 0.47 |

The 2-strike reset loses money in **all 14 start weeks**, in a tight band
(−29.4% to −22.8%). That tightness matters: unlike most results in this lab, this
one is *not* path luck — it is a systematic, repeatable loss.

### Why it fails — the sticky rule was doing hidden work

Re-striking collects **no more premium in total** ($255,423 vs $253,641) despite
writing four times closer to the money (3.4% vs 13.9% OTM), while paying **7% more
intrinsic** on assignment and being called away **twice as often (41% vs 20% of
weeks)**. Time spent with no share position **doubles, 52 → 108 days.** The share
leg itself flips from **+$100,378 to −$9,258 — negative, over a window in which
SOXL rose 2.6×** — purely from churn: sold at the strike on Friday, rebought a
median +10.0% higher on Monday, 95 times.

The mechanism is that **the sticky strike is accidentally a "stop capping after a
decline" rule.** Once the stock falls away from the old strike, the call is nearly
worthless — you collect almost nothing, but you also keep the entire rebound up to
that stranded strike. Re-striking every Monday re-caps at the *depressed* price and
therefore sells the recovery, week after week. On an instrument that fell 87% and
then rose 224%, and later 330%, that is the most expensive thing the rule could do.

This also sharpens the earlier finding: the sticky rule looks bad in isolation
because it stops earning premium, but that same property is what protects the
rebound. Distance is still the dominant dial — RESET improves monotonically from
−25.7% to −0.1% as you move 2 → 6 strikes out — but at every distance, holding the
old strike beats re-basing it by 20–34 points of CAGR.

## Follow-up 3: "but you bank cash every time you're called out"

`restrike_grid.csv` — and the assignment-cycle decomposition below.

### Yes. Every single assignment cycle is profitable. That is not the question.

Across the 47 called-out cycles, measuring from the share purchase price P:

| | median | mean |
|---|---:|---:|
| covered-call outcome (strike + premium) / P | **+7.41%** | +9.25% |
| just holding the shares (Friday close) / P | **+12.24%** | +14.22% |
| **upside handed to the option buyer** (C−K)/P | **+5.32%** | +8.19% |

**96% of assignment cycles made money.** Compounded across the 47 cycles the
covered call returned **+3,534%** and simply holding returned **+28,548%** — a
gap of **−4.85% per cycle**, compounded 47 times. You bank a gain every time; it
is just a smaller gain than doing nothing.

### Why 80% winners still loses

| | weeks | mean call-leg P&L (% of spot) |
|---|---:|---:|
| call expired worthless | 188 | **+1.07%** |
| call assigned | 47 | **−5.22%** |
| **all weeks** | 235 | **−0.19%** |

The five worst weeks alone cost **−133.9% of spot**, against **+201.4%** earned by
all 188 winning weeks combined. Five weeks ate two-thirds of every premium ever
collected:

| week | stock | strike vs spot | premium | call P&L |
|---|---:|---:|---:|---:|
| 2022-11-07 | **+46.9%** | 9.50 vs 8.98 | +4.84% | **−36.25%** |
| 2026-04-20 | +34.9% | 97.00 vs 95.07 | +3.93% | −28.94% |
| 2026-05-04 | +33.5% | 134.00 vs 132.91 | +5.23% | −27.46% |
| 2023-05-22 | +31.1% | 18.50 vs 17.48 | +1.46% | −23.77% |
| 2022-05-23 | +26.3% | 21.00 vs 20.02 | +3.97% | −17.46% |

This is what `vol_anatomy` predicted: SOXL's 7-day variance risk premium is
**+2.6%** of implied — i.e. ~zero. The premium is *fair payment* for the liability
you took on. Selling a call converts an uncertain future gain into certain cash
now, **at fair value, not at a profit.** Cash flow is not profit.

### Re-striking every week makes it worse, not better — at every setting

The natural fix is to stop leaving the strike stranded and re-anchor it weekly.
Tested literally, and then in a smarter "only re-strike when stranded, and
re-strike wide" form. Full sample, realistic costs, put leg unchanged:

| rule | final | CAGR | max DD | call leg | assigned | median premium |
|---|---:|---:|---:|---:|---:|---:|
| **A. sticky, 2 strikes (the spec)** | **122,994** | **+4.39%** | −62.8% | −35,264 | 47 | 0.51% |
| B. reset to 2 strikes weekly | 26,752 | −25.66% | −84.9% | −52,519 | 95 | 3.07% |
| C. re-strike >10% OTM → 5% OTM | 28,653 | −24.52% | −82.7% | −50,793 | 98 | 3.05% |
| C. re-strike >10% OTM → 15% OTM | 57,596 | −11.83% | −77.3% | −59,320 | 78 | 1.95% |
| C. re-strike >20% OTM → 5% OTM | 47,851 | −15.39% | −75.5% | −64,958 | 84 | 2.71% |
| C. re-strike >20% OTM → 15% OTM | **58,321** | **−11.58%** | −77.5% | −53,669 | 80 | 1.96% |
| C. re-strike >30% OTM → 15% OTM | 47,569 | −15.50% | −79.4% | −52,167 | 76 | 1.88% |

**All 13 re-strike variants lose, and the best is still 16 points of CAGR below
doing nothing.** The result is monotone in re-strike distance — re-striking to 15%
beats 10% beats 5% — and "never re-strike" beats all of them.

The decisive column is the last two together. Re-striking multiplies the premium
collected by **4–6×** (0.51% → 3.07% of spot per week) and the call leg gets
**50% worse** (−35,264 → −52,519). **More cash in, worse result out.** That is the
cleanest available proof that the premium is fair compensation rather than income:
collecting more of it simply means you sold something more valuable.

The sticky strike survives not because it earns but because after a decline it
stops capping. Re-striking re-arms the cap onto exactly the recovery you needed.

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
  **This is the binding limitation on the follow-up too**: SOXL rose ~2.6× over the
  window, so any rule that caps upside loses, and "write further out" wins by
  construction. A flat or choppy regime would rank these differently.
- The static-allocation ladder holds cash at 0%, matching the backtest. At 4% it
  would look better still, not worse.
- Early assignment is modelled as a threshold on time value, not from an actual
  SOXL dividend calendar (not present in the repo). The threshold was swept from
  0.1% to 1.0% of spot; the conclusion is stable below ~0.5%, above which the rule
  stops modelling assignment risk and becomes an early-exit tactic.
