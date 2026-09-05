# SOXL covered call + 90-day protective put — 2024 · rolling, never assigned

Start $100,000 on 2024-01-02 · liquidated 2024-12-31 · 30 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$59,306** | $93,494 |
| return | **-40.7%** | -6.5% |
| max drawdown | -48.0% | -62.2% |
| annualised vol | 43.7% | 103.1% |
| Sharpe | -1.21 | 0.50 |

SOXL 29.20 → 27.30 (-6.5%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $+22,204 |
| short calls | $-38,237 |
| long puts | $-23,659 |
| commissions & fees | $-1,002 |
| **total** | **$-40,694** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 3.87%**, mean 3.98%, range 2.60%–6.35%.
- Weeks that actually reached ~5% (≥4.5%): **33%** (10 of 30).
- The strike the rule had to pick sat **median 0.89% out of the money** (range 0.05%–10.52%).
- Gross gain if called out that week: median **4.77%**.
- Total premium collected over the year: **$79,860** (80% of starting capital).
- Median implied vol of the written call: 98%.
- Calls: **23 rolled** (bought back instead of assigned), 29 expired worthless, **10 assigned anyway** because the buyback could not be funded from cash.
- Paid **$83,871** in real cash to buy the rolled calls back; re-sold the far leg for **$46,810** (**$-37,062** net on the rolls).
- Puts: 2 exercised, 4 expired worthless.
- Protective puts bought: 10, at a median **88 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -1.1% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 32 (51%)
- nearest print inside 09:30–10:30: 3 (5%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 5 (8%)
- EOD chain mid on the expiry-day roll: 23 (37%)

## Files

- `ledger_2024_roll.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2024_roll.csv` — every fill, assignment, exercise and expiry
- `equity_2024_roll.csv` — daily marked-to-market equity
