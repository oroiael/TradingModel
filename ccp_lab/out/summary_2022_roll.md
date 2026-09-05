# SOXL covered call + 90-day protective put — 2022 · rolling, never assigned

Start $100,000 on 2022-01-03 · liquidated 2022-12-30 · 34 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$62,549** | $13,816 |
| return | **-37.5%** | -86.2% |
| max drawdown | -40.2% | -90.4% |
| annualised vol | 40.5% | 131.6% |
| Sharpe | -1.29 | -0.87 |

SOXL 70.16 → 9.68 (-86.2%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $-96,455 |
| short calls | $+18,217 |
| long puts | $+42,442 |
| commissions & fees | $-1,655 |
| **total** | **$-37,451** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 4.87%**, mean 4.65%, range 2.40%–5.86%.
- Weeks that actually reached ~5% (≥4.5%): **71%** (24 of 34).
- The strike the rule had to pick sat **median 2.66% out of the money** (range 0.20%–7.00%).
- Gross gain if called out that week: median **7.13%**.
- Total premium collected over the year: **$91,975** (92% of starting capital).
- Median implied vol of the written call: 143%.
- Calls: **19 rolled** (bought back instead of assigned), 33 expired worthless, **8 assigned anyway** because the buyback could not be funded from cash.
- Paid **$51,496** in real cash to buy the rolled calls back; re-sold the far leg for **$32,110** (**$-19,386** net on the rolls).
- Puts: 11 exercised, 2 expired worthless.
- Protective puts bought: 24, at a median **88 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -2.8% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 37 (48%)
- nearest print inside 09:30–10:30: 9 (12%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 12 (16%)
- EOD chain mid on the expiry-day roll: 19 (25%)

## Files

- `ledger_2022_roll.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2022_roll.csv` — every fill, assignment, exercise and expiry
- `equity_2022_roll.csv` — daily marked-to-market equity
