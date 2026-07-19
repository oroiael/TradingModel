# Short-Strangle ("Asymmetric Diagonal Yield Engine") — Backtest Results

*Run 2026-07-19. Strategy adopted by the user as the go-forward **active**
strategy (replacing the covered-call collar). Implemented in
`soxl_short_strangle_backtest.py`, priced on 100% real bid/ask + real delta
from `SOXL_Options_2024/2025/2026.csv` over 2024-01-02 → 2026-07-02 (131
weeks). No Black-Scholes, no invented quotes. Accounting is reconciled to
the penny (see "Verification").*

---

## Headline

| Metric | Value |
|---|---|
| **Final equity (fully liquidated)** | **$25,213** |
| **Total return** | **−83.2%** |
| Start capital | $150,000 |
| Max drawdown (MtM equity curve) | −83.2% |
| Peak modeled naked-call margin | $45,500 |
| SOXL over the window (10:00 spot) | 29.04 → 297.94 peak → 8.42 trough |

**The strategy as specified lost ~83% of capital over a window in which
SOXL itself finished sharply higher.** This is not a tuning problem — see the
sensitivity section: every variant tested loses ~80%.

## Per-leg attribution (exact per-leg cash — sums to the total, verified)

| Leg | Net cash | What happened |
|---|---|---|
| **Leg 1 — long ATM put anchor** | **−$54,181** | Insurance premium in a net-up market. It *did* go deep ITM at the April-2025 crash (~$74k intrinsic at the trough), but the spec's hold-to-DTE≤30 / roll-up rules never monetized it; SOXL recovered to $297 and the anchor decayed back to near-zero. |
| **Leg 2 — weekly short put** | **−$46,658** | Gross premium was **+$60,088**, but the mandated −0.50 delta-defense rolling cost ~$107k (buy-to-close at losses + reopen). Net negative. Sold in only 52/131 weeks (protected-strike constraint). |
| **Leg 3 — weekly NAKED call** | **−$23,948** | Collected $43,149; lost $66,933 to assignment across 18 ITM weeks. Worst single week −$26,390 (2024-01-16: sold 32-strike calls at spot 28.23; SOXL closed the week at 34.90). The uncapped up-gap tail the spec's "cannot lose on both legs" framing hides. |
| **Total** | **−$124,787** | |

## The delta-defense roll is structurally broken on this instrument

The spec (§3.2) requires rolling the tested short put "down and out … for a
net credit or at breakeven." On real quotes:

* Delta-defense fired in **25 weeks**.
* **19 of those 25 rolls (76%) were net *debits*** — a credit roll simply
  did not exist. The engine took the least-bad debit and flagged each row
  `ROLL_NET_DEBIT` rather than pretend a credit was available.

This is the exact failure mode called out in `REVIEW_Active_Version.md` §2.5:
on a fast-moving 3x ETF you cannot roll a tested put far enough down to
de-risk *and* collect a credit; you pay to keep re-arming a losing position.

## Sensitivity (is it just bad tuning? No.)

| Variant | Final | Return | Leg1 anchor | Leg2 put | Leg3 call | Max DD |
|---|---|---|---|---|---|---|
| Spec as written (roll at −0.50) | $25,213 | −83.2% | −$54,181 | −$46,658 | −$23,948 | −83.2% |
| Delta-defense OFF (hold put to expiry) | $31,157 | −79.2% | −$60,698 | −$34,086 | −$24,058 | −79.2% |
| First run, no anchor roll-up | ~$32,600 | −78.3% | (large) | (skipped 62 wks) | — | — |

Disabling the roll improves the put leg (−$47k → −$34k, matching the collar
roadmap §7 finding that *holding beats rolling*) but the strategy is still
deeply negative because **all three legs are net losers** in this regime.
Sizing scales every leg together, so the percentage result is roughly
size-invariant; the sign is structural, not a knob.

## Why every leg loses (the structural read)

The three legs are supposed to be an income engine (short put) + a yield
booster (short call) + cheap catastrophe insurance (long put). On 2024-2026
SOXL:

1. **The market trended up**, so the ATM put anchor was pure cost and the
   naked call was repeatedly run over by rallies.
2. **The one big crash (Apr-2025) did make the anchor valuable**, but the
   hold rules never harvested it, and the recovery gave it all back.
3. **The short put's income was consumed by its own defense** — the −0.50
   roll on a gap-prone 3x ETF locks losses 76% of the time.

A short-vol strategy needs a range-bound or mean-reverting underlying. A 3x
leveraged ETF is the opposite: it trends hard and gaps, punishing both short
legs, while the long-put insurance is expensive and only pays in a crash you
have to *sell into* to realize. The structure fights its own instrument.

## Data / listing findings (honest limitations)

* **120-180 DTE anchor listing gaps.** Several weeks (early 2024, parts of
  2025) had **no** listed expiration in the 120-180 DTE whole-strike window,
  so the anchor could not be (re)established and those weeks were skipped
  (no unhedged trading). The spec's fixed 120-180 tenor collides with SOXL's
  actual LEAPS/quarterly listing schedule.
* **End-of-day option data.** The file carries one quote+greeks snapshot per
  contract per day (evening `underlying_timestamp`). There are **no intraday
  option quotes**, so entries are priced at Monday EOD and the −0.50
  delta-defense trigger is evaluated on daily EOD delta, not live intraday.
  This is the single largest modeling limitation. Intraday data could move
  the defense outcomes either way; it would not plausibly turn a −83% result
  positive given every leg's sign.
* Delta, IV and both quote sides are real and fully populated (checked in
  `data_evaluation.py` / confirmed here: delta non-null = 100%).

## Verification (the project's "double-check" mandate)

* **Reconciliation gap = $0.00**: Σ(weekly true cash flow) exactly equals
  final(cash+side) − start.
* **Per-leg cash is airtight**: an in-code assertion enforces
  `cf_anchor + cf_put + cf_call == weekly cash flow` every week; the three
  leg totals sum to −$124,787 = the total change.
* **Fully liquidated end state**: all open legs are marked to their real
  Friday quotes and closed in the final week, so the headline number is
  realized, not paper.
* Every priced leg uses a concrete real quote row; illiquid (bid=0 or
  inverted) strikes are rejected per spec §1.3, never imputed.

## Recommendation

On the available real data the "Asymmetric Diagonal Yield Engine" is **not a
viable strategy** — it loses ~80% of capital in every tested configuration
and every leg is a net loser. Before investing further engineering:

1. **The premise should be reconsidered.** Short premium on a hard-trending,
   gap-prone 3x ETF is structurally adverse. The covered-call collar this
   replaced returned **+180% to +235%** on the *same* real quotes
   (`OPTIMIZATION_ROADMAP.md`) precisely because it is *long* the underlying.
2. If the short-strangle is still wanted, the honest next tests are: (a)
   **define the call risk** (buy a long call above Leg 3 → a real iron
   condor), (b) **retire the −0.50 credit-roll** (hold or take defined
   losses), (c) **harvest the anchor at crash extremes** instead of holding,
   and (d) re-run on 2020-2023 to see any non-trending regime. None of these
   is likely to overcome the trend/gap problem, but each is cheap to test and
   removes a known defect.

*No performance number here is projected or hand-tuned; all are produced by
`python3 soxl_short_strangle_backtest.py` on the committed real data.*
