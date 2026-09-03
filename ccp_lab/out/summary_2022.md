# SOXL covered call + 90-day protective put — 2022

Start $100,000 on 2022-01-03 · liquidated 2022-12-30 · 52 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$60,291** | $13,816 |
| return | **-39.7%** | -86.2% |
| max drawdown | -44.8% | -90.4% |
| annualised vol | 40.3% | 131.6% |
| Sharpe | -1.41 | -0.87 |

SOXL 70.16 → 9.68 (-86.2%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $-88,753 |
| short calls | $+9,083 |
| long puts | $+41,973 |
| commissions & fees | $-2,012 |
| **total** | **$-39,709** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 4.75%**, mean 4.58%, range 2.40%–5.86%.
- Weeks that actually reached ~5% (≥4.5%): **63%** (33 of 52).
- The strike the rule had to pick sat **median 2.16% out of the money** (range 0.12%–7.00%).
- Gross gain if called out that week: median **6.71%**.
- Total premium collected over the year: **$142,660** (143% of starting capital).
- Median implied vol of the written call: 134%.
- Calls: **20 assigned**, 32 expired worthless (38% called away).
- Puts: 12 exercised, 4 expired worthless.
- Protective puts bought: 26, at a median **84 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -2.3% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 56 (72%)
- nearest print inside 09:30–10:30: 10 (13%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 12 (15%)

## Files

- `ledger_2022.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2022.csv` — every fill, assignment, exercise and expiry
- `equity_2022.csv` — daily marked-to-market equity
