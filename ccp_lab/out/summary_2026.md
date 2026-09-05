# SOXL covered call + 90-day protective put — 2026

Start $100,000 on 2026-01-02 · liquidated 2026-07-30 · 26 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$88,632** | $378,759 |
| return | **-11.4%** | +278.8% |
| max drawdown | -33.0% | -43.4% |
| annualised vol | 64.4% | 148.0% |
| Sharpe | -0.27 | 2.61 |

SOXL 47.78 → 115.07 (+140.8%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $+106,157 |
| short calls | $-62,172 |
| long puts | $-54,935 |
| commissions & fees | $-418 |
| **total** | **$-11,368** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 5.01%**, mean 4.99%, range 3.12%–6.82%.
- Weeks that actually reached ~5% (≥4.5%): **85%** (22 of 26).
- The strike the rule had to pick sat **median 1.35% out of the money** (range 0.06%–9.41%).
- Gross gain if called out that week: median **6.32%**.
- Total premium collected over the year: **$121,009** (121% of starting capital).
- Median implied vol of the written call: 136%.
- Calls: **15 assigned**, 11 expired worthless (58% called away).
- Puts: 0 exercised, 4 expired worthless.
- Protective puts bought: 5, at a median **81 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -1.0% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 25 (81%)
- nearest print inside 09:30–10:30: 6 (19%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 0 (0%)

## Files

- `ledger_2026.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2026.csv` — every fill, assignment, exercise and expiry
- `equity_2026.csv` — daily marked-to-market equity
