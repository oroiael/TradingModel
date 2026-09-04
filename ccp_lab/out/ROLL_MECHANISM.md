# What rolling actually changes


## 1. It removes the whipsaw, which was the point

- Taking assignment: **107** repurchases, at a median **+9.4%** above the strike the shares were called away at.
- Rolling: only **47** repurchases (the cases where the buyback could not be funded), median **+16.2%**. Those are a funding failure, not a choice: with the reinvest-everything rule there is no cash on Friday. A 10-20% cash reserve removes almost all of them (see `SUMMARY_ROLL.md`).

Staying continuously long is the whole economic benefit. At the moment of expiry, buying the call back for its intrinsic and being assigned at the strike are worth **exactly the same**; the difference is entirely in what happens next.


## 2. The strike does ratchet up — and the roll is still a debit

- Median strike increase per roll: **+11.1%**.
- Median net cash on the roll: **$-99** per contract (30% of rolls were a credit).

The cap does move up meaningfully each time. But a roll still pays the intrinsic that assignment would have surrendered and recovers only the new week's time value, so most rolls are a net debit. It converts a realised loss into a deferred one on a position that stays capped.


## 3. Rolls compound into long chains

| year | rolls | median chain | longest chain | assigned anyway |
|---|---:|---:|---:|---:|
| 2022 | 19 | 1 | 5 | 8 |
| 2023 | 24 | 2 | 3 | 13 |
| 2024 | 23 | 1 | 3 | 10 |
| 2025 | 24 | 2 | 5 | 11 |
| 2026 | 15 | 2 | 4 | 5 |

Once the stock is above the strike, each roll re-caps it barely higher, so the next week is in the money again. The longest unbroken chain was **5 weeks**. That is the structural cost of rolling: in a sustained rally you are paying intrinsic every week to keep a position that is capped anyway.


## 4. Verdict

Rolling is worth doing — it is better than assignment in three of five years and by more than 40 points in two of them — and it does not rescue the strategy. It removes the transaction-cost whipsaw but not the two things that actually cost the money: the cap itself, and a protective put costing ~17% of spot every ~84 days.

