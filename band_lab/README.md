# Band Lab — SOXL daily band, excursions, and the churn-harvest playbook

Deep dive on SOXL's intraday structure (5-min bars, 2020-07 → 2026-07,
split-adjusted) aimed at active/automated trading: what band does SOXL churn
in each day, what tells you the band width early, when do the steep
drops/climbs come, and how to harvest the churn while staying neutral to
breakouts.

Scripts (run in order, outputs land in `band_lab/out/`):
- `band_analysis.py` — band stats, signals, excursion clustering, naive
  fade prototype (fails, kept as the control). Full text in `out/report.txt`.
- `churn_harvest.py` — dip-buy harvester grid (params × filters).
- `regime_gate.py` — volatility-regime gate on the best harvester configs.

## 1. The daily band

- Median day range **6.7%** of the open (IQR 4.9–9.1%, 90th pct 12.2%).
  At a $158 close that's an **~$11-wide band on a median day, ~$19 on a
  wild one**. By year: 5–6% in calm years, 9.3% (2022), 8.5% (2026).
- The churn inside the band is enormous: **15 completed ≥1% swings per day
  on average** (median 14; there has never been a 0-swing day in 6 years),
  and ~6 completed ≥2% swings per day.
- The band is built early: **56% of the day's final range is set by 10:00,
  68% by 10:30, 82% by 11:30**. The four most volatile 5-min buckets of the
  day are 09:35–10:00. After 13:00 the band is ~93% final.

## 2. Signals for today's band width

| signal | available | corr with day range |
|---|---|---:|
| opening 30-min range (OR30) | 10:00 | **0.62** |
| trailing 5-day avg range (ATR5) | before open | 0.51 |
| overnight gap size | 09:30 | 0.30 |

- Rule of thumb: **day range ≈ 1.9 × OR30** (median multiplier; 2.3× when
  OR30 is small, 1.7× when it's huge — see `out/or30_quintiles.csv`).
- Top-quartile |gap| (≈5.8% median) days run an 8.1% range with ~19 swings
  vs 6.1% / 13 swings on no-gap days.

## 3. Excursions (steep drops/climbs) and their clustering

Defining an excursion day as a ≥5.5% move inside 30 minutes (top decile):

- **Timing: 58% of excursions start in the 09:30–11:00 hour**, another 16%
  in the last hour. Middles of days are quiet.
- **They cluster hard**: P(excursion) is 10% on a random day but **32% the
  day after one**. High-vol days (range >1.5× trailing median) run 17%
  base rate but 38% after a high-vol day; bursts last up to **11 straight
  sessions**. Densest bursts in the data: Mar 2021, Dec 2021, Jan 2022,
  Mar 2025, Apr 2025 (tariff shock), Nov 2025 — i.e., your "week or two"
  intuition is exactly what the data shows.
- **The morning signature gives them away**: excursion days open with a
  median 3.1% gap (vs 2.2%) and a 5.7% OR30 (vs 3.3%). You usually know by
  10:00 whether today is an excursion candidate.

## 4. Harvesting the churn while neutral to breakouts

**What fails:** the classic "fade the opening-range low" (buy OR low,
target mid, stop below) loses **−1.1%/day** across 6 years — knife-catching
a 3x ETF at the band edge is negative in every single year. Kept in
`band_analysis.py` §4 as the control.

**What works** (`churn_harvest.py` + `regime_gate.py`):

> From 10:30 (band ~68% known), buy each **1% dip off the intraday rolling
> high**; sell **+1%**; stop **−4%**; max 5 trades; **flat at the close**;
> skip days whose OR30 is in the top quintile; trade only when **ATR5 ≥ 6%**.

| version | days traded | mean/day | Sharpe | worst day | years positive |
|---|---:|---:|---:|---:|---|
| ungated | 1,168 | +23 bp | 1.25 | −11.4% | 5/7 (2020, 2021, 2025 ≈ flat/neg) |
| **ATR5 ≥ 6% gate** | 746 | **+43.5 bp** | **2.14** | −11.4% | **7/7** |
| aggressive (dip 2%, gap filter, ATR5 ≥ 8%) | 168 | +89 bp | 4.12 | −10.0% | 5/7 — thin sample, treat as overfit-prone |

Why this is breakout-neutral by construction:
1. **Flat overnight** — the gap (the single biggest excursion channel) can't
   touch you.
2. **No trading before 10:30** — 58% of intraday excursions fire in the
   first hour, and the OR30 top-quintile skip removes the days with the
   excursion signature.
3. **The −4% stop** caps the one remaining tail (an afternoon collapse).
4. The vol gate is not a risk-avoidance trick — it's where the edge lives:
   ATR5 quartile 1 days lose −9 bp/day; quartile 4 days make +51 bp/day.
   Churn income and vol bursts are the same phenomenon.

### How this fits with the cycle strategy (cycle_lab)

The round-3 compounding cycle (2%/4d/no-hedge) already harvests multi-day
vol and holds through breakouts — it *is* the breakout participation. This
intraday harvester is the complementary sleeve: it makes its money inside
the day, in exactly the high-vol bursts that hurt the cycle sleeve's open
lots, and carries zero overnight exposure. Running both = long the breakout
(cycle lots) + paid for the churn (day sleeve), with the ATR5 ≥ 6% gate
turning the day sleeve on precisely when the cycle sleeve is stalling.

## Caveats

- No commissions/slippage; dip entries assume a resting limit at the
  trigger fills at the trigger (gap-throughs fill at the bar open, which is
  modeled). At ~1.4 trades/day, a $1–2 round trip cost needs >$5k/trade
  sizing to stay negligible.
- ATR5/OR30 thresholds were chosen on the full sample — a walk-forward
  split has NOT been run on this sleeve yet.
- 5-min bars can't see sub-bar sequencing: when a bar touches both target
  and stop, the sim takes the stop only if the bar's low was hit first at
  the open (conservative in gaps, optimistic in fast reversals).
