# SOXL covered call + 90-day protective put — 2025 · rolling, never assigned

Start $100,000 on 2025-01-02 · liquidated 2025-12-31 · 29 weekly writes


## Result

| | strategy | buy & hold SOXL |
|---|---:|---:|
| final equity | **$100,323** | $145,382 |
| return | **+0.3%** | +45.4% |
| max drawdown | -32.3% | -76.5% |
| annualised vol | 50.5% | 119.6% |
| Sharpe | 0.26 | 0.94 |

SOXL 28.91 → 42.03 (+45.4%) over the same window.


## Where the money came from

| leg | P&L |
|---|---:|
| shares | $+40,016 |
| short calls | $+280 |
| long puts | $-38,537 |
| commissions & fees | $-1,436 |
| **total** | **$+323** |

Legs reconcile to the final equity exactly.


## Did the 5% rule actually work?

- Premium collected, as a share of the underlying it was written against: **median 4.29%**, mean 4.06%, range 1.63%–5.48%.
- Weeks that actually reached ~5% (≥4.5%): **38%** (11 of 29).
- The strike the rule had to pick sat **median 0.91% out of the money** (range 0.06%–22.36%).
- Gross gain if called out that week: median **5.27%**.
- Total premium collected over the year: **$84,544** (85% of starting capital).
- Median implied vol of the written call: 108%.
- Calls: **24 rolled** (bought back instead of assigned), 26 expired worthless, **11 assigned anyway** because the buyback could not be funded from cash.
- Paid **$81,914** to buy the rolled calls back; re-sold the far leg for **$52,150** (**$-29,765** net on the rolls).
- Puts: 1 exercised, 10 expired worthless.
- Protective puts bought: 16, at a median **80 DTE** (target 90; the listed ladder is monthly so an exact 90 rarely exists), struck a median -3.3% out of the money.

## How the option marks were obtained

- real 10:00 trade print: 33 (48%)
- nearest print inside 09:30–10:30: 10 (14%)
- Black-Scholes off that contract's own EOD implied vol, repriced to the 10:00 spot: 2 (3%)
- EOD chain mid on the expiry-day roll: 24 (35%)

## Files

- `ledger_2025_roll.csv` — one row per Monday: spot, lots, strike chosen, premium, moneyness
- `events_2025_roll.csv` — every fill, assignment, exercise and expiry
- `equity_2025_roll.csv` — daily marked-to-market equity
