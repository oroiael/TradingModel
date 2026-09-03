# SOXL covered call + 90-day protective put — 2023 · rolling, never assigned

Start $100,000 on 2023-01-03 · liquidated 2023-12-29 · 28 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$99,959** | $327,069 |
| return | **-0.0%** | +227.1% |
| max drawdown | -35.3% | -49.2% |
| annualised vol | 45.6% | 85.2% |
| Sharpe | 0.19 | 1.86 |

SOXL 9.60 → 31.40 (+227.1%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $+139,689 |
| short calls | $-69,806 |
| long puts | $-67,165 |
| commissions & fees | $-2,758 |
| **total** | **$-41** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 3.27%**, mean 3.34%, range 1.84%–5.32%.
- Weeks that actually reached ~5% (≥4.5%): **7%** (2 of 28).
- The strike the rule had to pick sat **median 1.05% out of the money** (range 0.09%–4.17%).
- Gross gain if called out that week: median **4.52%**.
- Total premium collected over the year: **$93,185** (93% of starting capital).
- Median implied vol of the written call: 85%.
- Calls: **24 rolled** (bought back instead of assigned), 28 expired worthless, **13 assigned anyway** because the buyback could not be funded from cash.
- Paid **$90,978** to buy the rolled calls back; re-sold the far leg for **$56,684** (**$-34,294** net on the rolls).
- Puts: 0 exercised, 11 expired worthless.
- Protective puts bought: 18, at a median **88 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -2.8% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 30 (43%)
- nearest print inside 09:30–10:30: 8 (11%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 8 (11%)
- EOD chain mid on the expiry-day roll: 24 (34%)

## Files

- `ledger_2023_roll.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2023_roll.csv` — every fill, assignment, exercise and expiry
- `equity_2023_roll.csv` — daily marked-to-market equity
