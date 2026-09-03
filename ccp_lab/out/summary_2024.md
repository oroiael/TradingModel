# SOXL covered call + 90-day protective put — 2024

Start $100,000 on 2024-01-02 · liquidated 2024-12-31 · 53 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$66,472** | $93,494 |
| return | **-33.5%** | -6.5% |
| max drawdown | -44.2% | -62.2% |
| annualised vol | 39.0% | 103.1% |
| Sharpe | -1.04 | 0.50 |

SOXL 29.20 → 27.30 (-6.5%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $+9,779 |
| short calls | $-15,859 |
| long puts | $-26,197 |
| commissions & fees | $-1,251 |
| **total** | **$-33,528** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 3.87%**, mean 3.87%, range 2.10%–6.35%.
- Weeks that actually reached ~5% (≥4.5%): **26%** (14 of 53).
- The strike the rule had to pick sat **median 0.92% out of the money** (range 0.00%–10.52%).
- Gross gain if called out that week: median **4.62%**.
- Total premium collected over the year: **$145,637** (146% of starting capital).
- Median implied vol of the written call: 97%.
- Calls: **25 assigned**, 27 expired worthless (48% called away).
- Puts: 4 exercised, 3 expired worthless.
- Protective puts bought: 11, at a median **87 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -1.3% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 54 (84%)
- nearest print inside 09:30–10:30: 5 (8%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 5 (8%)

## Files

- `ledger_2024.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2024.csv` — every fill, assignment, exercise and expiry
- `equity_2024.csv` — daily marked-to-market equity
