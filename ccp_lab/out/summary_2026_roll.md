# SOXL covered call + 90-day protective put — 2026 · rolling, never assigned

Start $100,000 on 2026-01-02 · liquidated 2026-07-30 · 11 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$136,655** | $240,771 |
| return | **+36.7%** | +140.8% |
| max drawdown | -39.5% | -69.4% |
| annualised vol | 83.7% | 153.6% |
| Sharpe | 1.31 | 1.81 |

SOXL 47.78 → 115.07 (+140.8%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $+129,496 |
| short calls | $-57,724 |
| long puts | $-34,753 |
| commissions & fees | $-364 |
| **total** | **$+36,655** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 5.42%**, mean 5.25%, range 3.12%–6.82%.
- Weeks that actually reached ~5% (≥4.5%): **91%** (10 of 11).
- The strike the rule had to pick sat **median 1.36% out of the money** (range 0.06%–9.41%).
- Gross gain if called out that week: median **6.45%**.
- Total premium collected over the year: **$67,201** (67% of starting capital).
- Median implied vol of the written call: 132%.
- Calls: **15 rolled** (bought back instead of assigned), 11 expired worthless, **5 assigned anyway** because the buyback could not be funded from cash.
- Paid **$111,538** to buy the rolled calls back; re-sold the far leg for **$67,020** (**$-44,517** net on the rolls).
- Puts: 0 exercised, 5 expired worthless.
- Protective puts bought: 6, at a median **74 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -1.3% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 12 (38%)
- nearest print inside 09:30–10:30: 5 (16%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 0 (0%)
- EOD chain mid on the expiry-day roll: 15 (47%)

## Files

- `ledger_2026_roll.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2026_roll.csv` — every fill, assignment, exercise and expiry
- `equity_2026_roll.csv` — daily marked-to-market equity
