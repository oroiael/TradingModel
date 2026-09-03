# SOXL covered call + 90-day protective put — 2023

Start $100,000 on 2023-01-03 · liquidated 2023-12-29 · 52 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$83,432** | $327,069 |
| return | **-16.6%** | +227.1% |
| max drawdown | -42.7% | -49.2% |
| annualised vol | 38.6% | 85.2% |
| Sharpe | -0.45 | 1.86 |

SOXL 9.60 → 31.40 (+227.1%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $+113,894 |
| short calls | $-62,670 |
| long puts | $-64,495 |
| commissions & fees | $-3,297 |
| **total** | **$-16,568** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 3.27%**, mean 3.40%, range 1.84%–6.07%.
- Weeks that actually reached ~5% (≥4.5%): **12%** (6 of 52).
- The strike the rule had to pick sat **median 1.38% out of the money** (range 0.00%–4.17%).
- Gross gain if called out that week: median **4.62%**.
- Total premium collected over the year: **$171,750** (172% of starting capital).
- Median implied vol of the written call: 86%.
- Calls: **23 assigned**, 29 expired worthless (44% called away).
- Puts: 0 exercised, 11 expired worthless.
- Protective puts bought: 18, at a median **88 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -3.4% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 54 (77%)
- nearest print inside 09:30–10:30: 8 (11%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 8 (11%)

## Files

- `ledger_2023.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2023.csv` — every fill, assignment, exercise and expiry
- `equity_2023.csv` — daily marked-to-market equity
