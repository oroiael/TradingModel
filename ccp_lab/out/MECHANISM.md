# Why the rule loses — the mechanisms, measured


## 1. The short call: premium collected vs upside given up

The 'upside given up' column is **not a cash outflow**. Assignment delivers the shares at the strike — cash comes in, never out. It is the difference between the strike and where the stock actually finished, i.e. the gain the cap prevented. See `CASHFLOW.md` for the same year with no attribution at all, only cash that moved.

| year | writes | premium collected | assigned | upside given up at the strike | net call P&L |
|---|---:|---:|---:|---:|---:|
| 2022 | 52 | $142,660 | 20 | $133,577 | $+9,083 |
| 2023 | 52 | $171,750 | 23 | $234,420 | $-62,670 |
| 2024 | 53 | $145,637 | 25 | $161,496 | $-15,859 |
| 2025 | 53 | $116,971 | 25 | $107,484 | $+9,487 |
| 2026 | 26 | $121,009 | 15 | $183,181 | $-62,172 |
| **all** | 236 | **$698,027** | 108 | **$820,158** | **$-122,131** |

The premium is enormous — and it is not enough. Writing at or barely above the money means roughly half of all weeks finish in the money, and the weeks that do finish far in the money.


In pure cash terms the call leg only ever takes money **in**. The loss shows up on the **stock**: the strike is set above *that Monday's* spot, not above what the shares cost, so after a decline you are called away at a strike far below your basis. In 2025 the share leg realised **-$124,424** that way while the calls brought in **+$116,971**.


## 2. The protective put: what the insurance costs

| year | puts bought | premium paid | median cost, % of spot | median DTE | net put P&L |
|---|---:|---:|---:|---:|---:|
| 2022 | 26 | $70,775 | 19.7% | 84 | $+41,973 |
| 2023 | 18 | $64,495 | 15.0% | 88 | $-64,495 |
| 2024 | 11 | $55,093 | 16.8% | 87 | $-26,197 |
| 2025 | 16 | $47,936 | 15.7% | 80 | $-28,750 |
| 2026 | 5 | $54,935 | 22.2% | 81 | $-34,970 |
| **all** | 76 | **$293,234** | 16.8% | 84 | **$-112,439** |

A just-out-of-the-money put on a 3× semiconductor ETF costs a median **16.8% of spot per ~84 days**. Reloaded roughly four times a year, that is on the order of **50-60% of the position's value per year** in insurance premium alone.


## 3. The whipsaw: called away low, bought back high

- 107 assignments were followed by a repurchase.
- The shares went back on at a **median +9.4%** above the strike they were called away at.
- The repurchase was higher than the strike in **94%** of cases.

| year | assignments repurchased | median repurchase vs strike |
|---|---:|---:|
| 2022 | 19 | +7.1% |
| 2023 | 23 | +10.7% |
| 2024 | 25 | +8.1% |
| 2025 | 25 | +8.7% |
| 2026 | 15 | +18.8% |

Selling at a fixed strike on Friday and rebuying at the market on Monday is a sell-low/buy-high rule by construction whenever the stock is trending up.


## 4. Was the 5% premium ever actually collected?

| year | median premium, % of underlying | median strike vs spot |
|---|---:|---:|
| 2022 | 4.75% | +2.16% |
| 2023 | 3.27% | +1.38% |
| 2024 | 3.87% | +0.92% |
| 2025 | 3.91% | +0.92% |
| 2026 | 5.01% | +1.35% |

The rule asks for 5%. Outside the highest-volatility stretches the market does not offer it at any strike at or above spot, so the engine writes the closest it can find — which is essentially at the money, and that is what drives the assignment rate.


## 5. Why a live trader may report something very different

Nothing here says the traders are wrong. It says the rule *as written* is not the rule they are running. The measured gaps, in order of size:

**a. They roll; this rule does not.** The rule holds the call to expiry and takes assignment. That happened 108 times in five years and cost $820,158 in intrinsic. A trader who rolls a threatened call up and out never books that, never sells the shares, and never pays the repurchase gap measured in section 3 (median +9.4%). Rolling is a different strategy with a different risk profile — it converts a capped position into a deferred loss — but it will not show these numbers.

**b. 5% is a target, not an outcome.** The market offered a 5% premium at or above spot on a minority of days in four of the five years. A trader who writes 'about 5%' when volatility allows and less otherwise is running a variable-distance rule, not this one.

**c. The put may not be reloaded at the money.** Reloading a just-OTM 90-day put costs a median 16.8% of spot each time. Traders often carry a much further out-of-the-money put, a put spread, or no standing hedge at all. `out/CONTROLS.md` shows removing the put alone turns 2023 from −17% to +63%.

**d. Short windows flatter this structure.** Any stretch in which the stock drifts sideways to slightly up pays the premium without triggering assignment. Judged quarter by quarter this rule has good quarters. It is the full-year path — the assignments and the four put reloads — that produces the numbers above.

**e. Prior backtests in this repo disagreed with each other.** `A2_Backtest_CCLDP_Strat_v1.py` read '5%' as a strike 5% above spot and multiplies premium by 100× the share count (`exec_price * 100 * portfolio['shares']`, line 121). `cc_lp_lab` used '2 strikes out, sticky'. Neither is the 5%-premium rule. The two QA reports at the repo root document double-counted premium, missing roll costs and clamped losses in the older engines. Inconsistent answers came from inconsistent questions.
