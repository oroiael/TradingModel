# Data QA/QC — SOXL covered call + long-dated put

Every number below was measured from the files in this repo, not assumed.
Reproduce with `python3 ccp_lab/qa_data.py`.


## 1. Can the data actually be read?

Yes. The CSVs are Git LFS objects; `git-lfs` is not installed in a bare
container, so an un-pulled checkout leaves 130-byte pointer files. After
`apt-get install git-lfs && git lfs install && git lfs pull` they are real:

| file | bytes | what it is |
|---|---:|---|
| `SOXL_1min.csv` | 42,917,855 | 1-minute underlying OHLCV |
| `SOXL_Options_2022.csv` | 147,624,682 | EOD option chain, 2022 |
| `SOXL_Options_2023.csv` | 94,074,669 | EOD option chain, 2023 |
| `SOXL_Options_2024.csv` | 128,451,410 | EOD option chain, 2024 |
| `SOXL_Options_2025.csv` | 77,665,666 | EOD option chain, 2025 |
| `SOXL_Options_2026.csv` | 122,332,800 | EOD option chain, 2026 (partial) |
| `raw_data/SOXL_intraday_5m_exp_*.csv` | 736 files | 5-min option TRADE bars |

## 2. Underlying — the 10:00 entry mark

- `SOXL_1min.csv`: **1,653 sessions**, 2019-12-31 → 2026-07-30.
- A **10:00 one-minute bar exists on 1,653 of 1,653 sessions (100.0%)** — the entry mark the rule asks for is never missing.
- No NaNs in O/H/L/C; 0 sessions with high < low (inconsistent bars).
- 0 of the 10:00 bars are internally inconsistent.
- The rule buys at the **high of the 10:00 bar**. Across all sessions that high sits a median **0.24%** above that minute's open — a deliberately conservative fill.
- One corporate action in the tape, a **15:1 split on 2021-03-02**, which is
  before the option data starts, so 2022–2026 sits on one price basis.

## 3. Option chains — coverage and shape

| year | contract-days | trading dates | span | with a two-sided quote |
|---|---:|---:|---|---:|
| 2022 | 279,810 | 251 | 2022-01-03 → 2022-12-30 | 90.0% |
| 2023 | 217,266 | 250 | 2023-01-03 → 2023-12-29 | 91.0% |
| 2024 | 299,477 | 252 | 2024-01-02 → 2024-12-31 | 95.7% |
| 2025 | 277,778 | 250 | 2025-01-02 → 2025-12-31 | 91.0% |
| 2026 | 286,359 | 125 | 2026-01-02 → 2026-07-02 | 95.2% |

Total **1,360,690 contract-days** after filtering to a usable implied vol.

These files are **one row per contract per day** — an end-of-day chain
snapshot, not an intraday series. Verified: zero duplicate
(expiration, strike, right, trade_date) keys in any year.

**Strike hygiene.** The rule only trades whole or half-dollar strikes. 2022 carries **20.0% non-standard strikes** (e.g. 37.67) — adjusted contracts left over from a corporate action. 2023 has 1.5%; 2024-2026 have none. They are filtered out everywhere.

**Vendor format drift.** 2025 is written in a different dialect from the other
four years — `1/24/25` instead of `2025-01-24`, and bare integer strikes. A
loader that assumes ISO dates silently drops the whole year. The cache builder
handles both.


## 4. Is a 5% weekly premium actually available?

This is the single most important QA result, because the rule is defined by it.

Best premium obtainable from **any** at-or-out-of-the-money weekly call, as a
percentage of spot (EOD mids, all listed weekly strikes):

| year | trading days | median best premium | days ≥5% reachable | days ≥4% |
|---|---:|---:|---:|---:|
| 2022 | 200 | 4.44% | **31%** | 64% |
| 2023 | 199 | 2.84% | **5%** | 17% |
| 2024 | 202 | 3.52% | **12%** | 35% |
| 2025 | 202 | 3.57% | **17%** | 38% |
| 2026 | 99 | 5.34% | **60%** | 83% |

**On most weeks a 5% premium does not exist** without selling a strike below
spot. An at-the-money weekly call is worth roughly `0.055 × IV × spot`, so 5%
needs about **90% implied vol**. SOXL trades there only in stressed regimes —
which is why 2026 (59% of days) and 2022 (31%) clear the bar and 2023 (5%)
does not. The backtest therefore writes the strike whose premium is *closest*
to 5% and records the shortfall every week.


## 5. Is a 90-day put available?

Nearest listed expiry to 90 DTE, measured on every Monday the backtest trades:

| year | Mondays | median DTE picked | within 15d of 90 | within 30d | worst |
|---|---:|---:|---:|---:|---:|
| 2022 | 52 | 88 | 38% | 79% | 45d |
| 2023 | 52 | 88 | 38% | 75% | 45d |
| 2024 | 53 | 88 | 43% | 77% | 45d |
| 2025 | 53 | 88 | 38% | 77% | 44d |
| 2026 | 27 | 88 | 59% | 81% | 44d |

Median pick is **88 DTE** — on target. The ladder is
monthly, so an exact 90 rarely exists, and there are occasional holes (on
2024-01-02 the listed expiries jump straight from 45 to 136 DTE). Those weeks
get a shorter put than the rule wants; the realised DTE is logged per trade.


## 6. How much of the pricing is real, and how much is modelled?

- `prints_1000.parquet`: **2,016,186 traded 5-min option bars** in the
  09:30–10:30 window, 2021-01-04 → 2026-07-17.
- Of those, **153,073** are stamped exactly 10:00.

Strike **selection** is always done on the model, because a premium is needed
for every candidate strike and real prints only exist where somebody traded.
Once the strike is picked, the **fill** uses a real 10:00 trade print when one
exists, the nearest print inside 09:30–10:30 otherwise, and Black-Scholes off
that contract's own EOD implied vol repriced to the 10:00 spot as the last
resort. Every summary reports that mix. Carry is `r−q = 0.04`, which prior work
in this repo validated against the vendor's own EOD mids to 0.67% MAE.


## 7. What this means for the backtest

| question | answer |
|---|---|
| Can I read the option files? | Yes — 1.5M contract-days, 2022 → 2026-07-02. |
| Can I get the 10:00 Monday entry? | Yes — a 10:00 1-min bar on 100% of sessions. |
| Is a 5% weekly premium available? | **Usually not.** Median best is 2.8–5.3%/yr. |
| Is a 90-day put available? | Yes, median 88 DTE; monthly ladder, occasional holes. |
| Are bid/ask spreads known? | Yes, EOD two-sided quotes on ~97% of contract-days. |
| Biggest data limitation | Option chains are **EOD snapshots**; the 10:00 mark is a print when one exists and a model otherwise. |
| Biggest strategy limitation | 2022–2026 is one −87% year and one +330% half-year. Five years of a 3× ETF is a small sample of regimes. |
