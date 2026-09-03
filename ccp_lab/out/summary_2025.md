# SOXL covered call + 90-day protective put — 2025

Start $100,000 on 2025-01-02 · liquidated 2025-12-31 · 53 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$62,382** | $145,382 |
| return | **-37.6%** | +45.4% |
| max drawdown | -47.3% | -76.5% |
| annualised vol | 52.6% | 119.6% |
| Sharpe | -0.89 | 0.94 |

SOXL 28.91 → 42.03 (+45.4%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $-16,940 |
| short calls | $+9,487 |
| long puts | $-28,750 |
| commissions & fees | $-1,415 |
| **total** | **$-37,618** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 3.91%**, mean 3.92%, range 1.63%–6.82%.
- Weeks that actually reached ~5% (≥4.5%): **34%** (18 of 53).
- The strike the rule had to pick sat **median 0.92% out of the money** (range 0.06%–46.20%).
- Gross gain if called out that week: median **4.96%**.
- Total premium collected over the year: **$116,971** (117% of starting capital).
- Median implied vol of the written call: 105%.
- Calls: **25 assigned**, 27 expired worthless (48% called away).
- Puts: 0 exercised, 10 expired worthless.
- Protective puts bought: 16, at a median **80 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -2.8% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 56 (81%)
- nearest print inside 09:30–10:30: 9 (13%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 4 (6%)

## Files

- `ledger_2025.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2025.csv` — every fill, assignment, exercise and expiry
- `equity_2025.csv` — daily marked-to-market equity
