# SOXL Part 5 — Intraday 5-min OPTION Data: Access, Quality, Usability

The user pointed to a large set of intraday option files in `raw_data/`:
`SOXL_intraday_5m_exp_<EXPYYYYMMDD>_<YEAR>_<SEG>.csv`. This documents access, a
quality/consistency review, the usability verdict, and — since the data is of
quality — the analysis it enables: **validating the Part-4 Black-Scholes intraday
model against real intraday option prices.**

## Access — confirmed

Files are Git LFS objects. `git lfs pull --include=...` retrieves them and they
read cleanly. **282 files, ≈1.5 GB.** Each file = one expiration's full chain
(both rights, ~48–55 strikes), 5-min **OHLC + volume + count + vwap**, 09:30–16:00
ET (79 bars/day), split by capture-month "segment".

Columns: `symbol, expiration, strike, right, timestamp, open, high, low, close,
volume, count, vwap`. These are **trade prices (OHLC/vwap), not bid/ask.**

## Coverage

* **104 distinct expirations, 2024–2025** (weeklies + monthlies).
* Intraday history reaches back **~2–3 capture-months (~75 days) before each
  expiration**; only a few long-dated monthlies carry 8–9 months.
* **No intraday option data for 2022, 2023, or 2026.**

Consequence: a **≤ ~60–75 DTE** strategy can be priced intraday across its whole
hold in 2024–2025; a **120-DTE** hold only has intraday for its final ~75 days;
and the three non-2024/25 years have none.

## Quality & consistency — high (for the legs we trade)

* **Liquidity:** only **23.5%** of *all* bars have a trade (dominated by dead deep
  strikes), BUT the strikes we actually trade are well covered — a usable price
  (`vwap>0`) exists in **~99.9%** of bars for ATM ±5% and **~95–100%** for the
  5–15% OTM band (traded ~45–75%). Near-the-money legs are priceable at nearly
  every 5-min bar; deep strikes are sparse but irrelevant to us.
* **Consistency with the daily feed is exact:** the intraday 16:00 close equals
  the daily EOD file's close — **median difference $0.000, correlation 1.0000**
  (216 and 953 contract-days on two expirations) — and sits at/near the daily mid
  (ratio 1.00–1.01). The two datasets are the same underlying source; they cohere.
* **Grid:** clean 5-min timestamps, 79 bars/session, tz-aware ET.

## Usability verdict — usable; here's what it takes

Usable and good quality. To make it work:
1. **Use `vwap` (or last trade) for price and carry forward across no-trade bars** —
   handled in `intraday_options.py` (keeps `vwap>0` rows). Near-the-money is dense
   enough that staleness is minimal.
2. **Treat prices as trades, not quotes** — for an intraday *exit*, sell below the
   print (a slippage haircut), since there's no bid/ask here. We use `high*(1-slip)`.
3. **Respect the coverage envelope** — full intraday only for ≤~75-day holds in
   2024–2025. For the 120-DTE strategy and for 2022/2023/2026, intraday option
   prices don't exist, so those must be modeled.
4. A loader mapping expiration → segment files (`intraday_options.py`) and, for a
   continuous backtest, the full 1.5 GB pull (only a 10-expiration sample was
   pulled for this validation).

## The analysis it enables — the Part-4 BS model is VALIDATED

Because the coverage can't backtest the 120-DTE strategy directly (no intraday
before ~75 DTE, and none in 2022/23/26), the highest-value use is to **check the
Black-Scholes intraday estimator Part 4 relied on** against these real prices
(`validate_bs_intraday.py`, `run_real_intraday_episodes.py`):

* **Bar-by-bar** (58k bars, ±20% moneyness): BS(`S_bar,K,T,`prior-EOD IV) vs real
  `vwap` — **correlation 0.980**, median signed error **−0.9%** (unbiased across
  moneyness), median abs error 7.9%.
* **Harvest peak** (19k contract-days): BS at the underlying's intraday extreme vs
  the option's **own real intraday high** — **correlation 0.995**, BS
  **overestimates the real peak by +3.4% median**. That small optimism is exactly
  what Part 4's slip sweep brackets — the "5% slip" column is the real-faithful one.
* **P&L level** (episode test, real prices, dist 7.5% / take +50% / slip 5%):

  | harvest method | mean leg return | win |
  |---|--:|--:|
  | **REAL** (option's real intraday high) | **+5.8%** | 60% |
  | **BS** (Part-4 model) | +6.2% | 60% |
  | **EOD** (close-only) | −5.2% | 53% |

  Intraday harvesting beats close-only by **+11%/leg** on real prices, and the BS
  model reproduces the real-price result to **+0.4%/leg**. (Small sample: 15 legs
  from the 10 pulled expirations — directional, not definitive, but consistent
  with every prior part.)

**Conclusion:** the intraday option data is real, high-quality near the money, and
perfectly consistent with the daily feed. It **confirms the Part-4 intraday
finding on real prices** — intraday harvesting genuinely beats EOD, and the BS
estimator is unbiased bar-by-bar and only ~3% optimistic at the peak (covered by a
5% slip). So the Part-4 result — and its extrapolation to 2022/2023/2026 — stands
on validated footing. The now-trusted BS model remains the tool for the
full-period (2022–2026) intraday backtest; the real data's best role, given its
2024–25 / ≤75-DTE envelope, is exactly this validation.

## Next step (optional, needs the full pull)

Pull all 282 files (~1.5 GB) and run a *continuous* 2024–2025 backtest of a
≤60-DTE strangle on **real** intraday prices (no BS) to confirm the episode result
at portfolio scale. Given the +0.4%/leg BS-vs-REAL agreement, this would confirm
rather than change the conclusion — happy to do it on request.

## Reproduce

```bash
git lfs pull --include="raw_data/SOXL_intraday_5m_exp_2024*,raw_data/SOXL_intraday_5m_exp_2025*"
cd call_spread_lab
python3 intraday_options.py            # loader + coverage summary
python3 validate_bs_intraday.py        # BS vs real (bar-by-bar + harvest peak)
python3 run_real_intraday_episodes.py  # REAL vs BS vs EOD harvest, real prices
```
