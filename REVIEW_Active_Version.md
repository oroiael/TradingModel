# Review — "SOXL Trading Strategy - Active Version.md"

*Reviewed 2026-07-19 against the repo at branch `claude/soxl-strategy-review-r13iif`.
No-guessing basis: every claim below is checked against the spec text, the
implemented code, or standard options-margin/API facts. Where I could not
verify something in this environment, I say so explicitly rather than assume.*

---

## 0. Environment limitation (stated up front, not hidden)

The three raw option files and the two price files are **Git-LFS pointers**,
and `git lfs` is not installed in this environment:

```
SOXL_5min_3Years.csv, SOXL_Master_Cleaned.csv,
SOXL_Options_2024/2025/2026.csv  →  3-line LFS stubs, not data
```

Therefore **I did not and could not run any backtest of the Active Version
strategy here.** No performance number in this review is invented. The
non-LFS output files (`soxl_weekly_backtest_results.csv`,
`put_policy_results.csv`) are real and belong to the *other* strategy (see §1).

---

## 1. The biggest finding: the Active Version is a different strategy than the one this repo actually builds, and it is implemented nowhere

There are **two distinct strategies** in this repository:

| | `Option Trading Project for SOXL.md` (original) | `SOXL Trading Strategy - Active Version.md` (this review) |
|---|---|---|
| Core | **Long stock** + covered call + long-dated protective put | **No stock**; short weekly put + short weekly call + long-dated put anchor |
| Directional base | Long the underlying | Short volatility / premium collection |
| Weekly income leg | Short **call** vs shares | Short **put** (Leg 2) + short **call** (Leg 3) |
| Downside risk | Owns shares, hedged by long put | Naked-ish short strikes, hedged only on the put side by Leg 1 |
| Margin profile | Cash/shares + spread | Short strangle margin (see §2) |

`soxl_weekly_income_backtest.py` (52 KB, real-quote backtested, the subject of
the whole `OPTIMIZATION_ROADMAP.md`) implements the **covered-call collar** —
its own docstring says so: *"Hold long SOXL shares (75% of capital)… sell a
call… hold a long put."* Grep confirms there is **no short-put income leg, no
naked short call, no iron condor / strangle, no combo/BAG, no ib_insync/ibapi**
anywhere in the Python. The `sell...put` lines in the backtester are the
*protective put-spread hedge*, not Leg 2 income.

**Consequence:** a reader who opens the file named "Active Version" will
reasonably assume the committed code runs it. It does not. Either the title is
wrong, or Part 3 / Part 4 of this spec are unbuilt work. This needs to be
reconciled before anything else — recommendation in §7.

---

## 2. Technical / financial errors in the spec (these are wrong, not stylistic)

### 2.1 "3-Legged … Iron Condor" is a misnomer that hides a naked call
An iron condor is **four** legs and defined-risk on *both* sides (a bull put
spread **and** a bear call spread). This structure has a long put (Leg 1), a
short put (Leg 2) and a short call (Leg 3) — **there is no long call above
Leg 3.** The call side is therefore a **naked short call**. On a 3x
semiconductor ETF that can gap up 20–40% intraday, naked-call loss is
*unbounded*. Naming it an "iron condor" buries the single largest risk in the
book. Call it what it is: a *long-dated-put-anchored short strangle* (or
"put diagonal + naked call overlay").

### 2.2 "Zero additional margin for the short call" is factually false (spec §Leg 3, line 55)
> "Standard brokerage margin rules require zero additional collateral to add
> this short call overlay against your short put."

Short put + short call = **short strangle**. Under Reg-T, strangle margin is
the **greater** of the two naked single-option requirements **plus the premium
of the other side** — it is *not* free. IBKR (and portfolio margin) explicitly
stress an up-gap on the naked call and will hold collateral against it. The
entire "zero-margin yield booster" pitch rests on this false premise. The call
premium is compensation for real, uncapped, collateralized risk — not a free
cushion.

### 2.3 "A portfolio cannot lose on the short call and the short put simultaneously" is only true at Friday settlement
At *expiration* the underlying prints one price, so only one short leg finishes
ITM — true. But the spec's own **Mechanical Delta Defense is an intraday
trigger**, and intraday **both legs can be underwater at once** in a whipsaw
(gap down Tuesday → put roll booked at a loss; gap up Thursday → call tested).
Mark-to-market, both can bleed in the same week. So the claim cannot be used to
justify treating Leg 3 premium as riskless operating cash.

### 2.4 The BAG/combo composition in Part 4 is wrong for the weekly cadence (line 95)
The spec appends **all three legs** (BUY Leg 1, SELL Legs 2 & 3) into one
Combo (BAG) and routes it "to your calculated net credit limit." But Leg 1 is
a **120–180 DTE put bought once and held for months** — you do **not** re-buy it
every Monday, and a large long-dated **debit** leg cannot sit inside a
"net-credit" weekly combo. The weekly atomic combo is **Legs 2 + 3 only**
(two short legs → genuine net credit). Leg 1 is a separate, infrequent
standalone order. As written, the BAG spec would try to repurchase the anchor
every week.

### 2.5 "Roll down and out for a net credit or at breakeven" is often infeasible — and is a known trap (§3.2, line 72)
Rolling a tested short put **down** in strike *reduces* premium; rolling **out**
in time *adds* it. Forcing a net-credit constraint **caps how far down the
strike can move**, so in a fast 3x sell-off you may be unable to roll far enough
to actually de-risk — you keep rolling for tiny credits into a deepening loss
("rolling into a black hole"). The spec presents net-credit rolling as always
available; it is not. Needs a max-roll-distance and a hard stop/exit condition,
not just "must be a credit."

---

## 3. Weaker points / modeling limitations (defensible but worth flagging)

- **`strike % 1 == 0` is too blunt (line 15).** The valid concern is
  *split-adjusted, non-standard-deliverable* contracts (the "$103.33" example).
  But `% 1 == 0` also throws away normal, liquid **$X.50** strikes that are
  standard on a sub-$30 ETF, and can force nearest-neighbor onto a *worse*
  strike. Better: filter on the OCC *adjusted / non-standard-deliverable* flag
  (or the listed-increment), not on "has a decimal." *(Note: the original
  project states the same whole-number rule, so this is a deliberate user
  constraint — flagged as a modeling limitation, not a code bug.)*

- **Δ = −0.50 roll trigger vs. weekly gamma (line 71).** On a Friday-expiry
  weekly, −0.30 → −0.50 can happen in one fast move; by the time delta *prints*
  −0.50 the option may already be ATM with a blown-out spread — the exact
  condition the rule wants to pre-empt "before Gamma acceleration." A −0.40 (or
  a spot-percentage) trigger, plus a day-of-week guard, defends earlier. Tunable,
  but the current value undercuts its own stated rationale.

- **"−0.20 to −0.30 delta ≈ 5–10% below spot" (line 47)** is vol-dependent; on
  high-IV weekly SOXL a −0.20/−0.30 put is typically closer (~3–6% OTM). Minor,
  but the spec states it as if fixed.

---

## 4. Internal inconsistency: "Active Version" encodes rules the team already retired

The document titled **Active Version** still specifies, for Leg 1:
*"triggering a protective roll-up"* on +10% appreciation and a roll at
`DTE <= 30` (line 80), and a **25% sweep** (line 83).

But `OPTIMIZATION_ROADMAP.md` §7 (same July-2026 window) records the **adopted**
decision: *"buy the put and HOLD TO EXPIRATION (roll-up rule retired)"*, and the
sweep was moved **25% → 10% → 5%**. So the "Active Version" contains
**retired** parameters. Either the title is inaccurate or the content is stale.
(These retired-vs-active decisions were made for the *covered-call* strategy;
whether they even apply to the short-strangle strategy is itself unresolved,
which loops back to §1.)

---

## 5. What is actually good in the spec (credit where due)

- **The 20% spread execution rule is conservative and correct.** Sell at
  `Bid + 0.20·spread` (below mid) and buy at `Ask − 0.20·spread` (above mid)
  both cost the trader vs. midpoint — a defensible, slightly-pessimistic retail
  fill assumption. Good.
- **Nearest-neighbor `argmin |ChainStrike − Target|`** is the right way to avoid
  silent no-fills on variable strike spacing. Good.
- **Decoupled per-leg ledger** (realized cash vs. unrealized mark) is exactly
  the right auditing discipline and matches how the existing backtester is built.
- **Part 4 IBKR mechanics are largely sound**: `secType='BAG'` + `ComboLeg` with
  `conId`, `reqMktData` generic tick **106** for IV/greeks,
  `pendingTickersEvent` → `modelGreeks.delta`, and the **stateless-in-memory /
  persistent-on-disk** reconciliation via `reqPositions()`/`reqOpenOrders()` on
  reconnect. These are correct IBKR/ib_insync patterns and good engineering
  (subject to the §2.4 combo-composition fix).
- **Dynamic timestamp fallback** for missing 10:00/15:30 bars is the right call
  and is already how the implemented code handles holidays.

---

## 6. Recommendations, ranked

1. **Resolve the identity of "Active Version" (blocking).** Decide: is the
   go-forward strategy the covered-call collar that is built and tested
   (+180% to +235% on real quotes, per the roadmap), or this new
   short-strangle-with-anchor that is **unbuilt**? They are opposite exposures.
   Do not run both under one "active" label.
2. **Rename the structure and correct the margin claims (§2.1–2.3).** Stop
   calling it an iron condor; state plainly that Leg 3 is a naked short call
   carrying strangle margin and uncapped up-gap risk. If defined risk is wanted,
   add a long call above Leg 3 to make it a *true* iron condor.
3. **Fix the roll rule (§2.5):** add a max-strike-distance per roll and a hard
   stop / defined-loss exit; drop the unconditional "must be a net credit."
4. **Fix the weekly BAG to Legs 2+3 only (§2.4);** treat Leg 1 as a separate
   long-hold order.
5. **Reconcile the retired parameters (§4)** — either restore hold-to-expiration
   / 5% sweep, or justify why the strangle variant re-adopts roll-up and 25%.
6. **If this strategy is to be trusted, it must be backtested on real quotes**
   the same way the collar was — including the naked-call tail. Until then, no
   performance claim about the Active Version is supportable. *(Requires
   `git lfs pull` in an environment where the LFS data is reachable.)*

---

## 7. Bottom line

The spec is well-written as prose and gets the *execution plumbing* (nearest-
neighbor strikes, conservative fills, decoupled ledger, IBKR combo/greek/
reconnect mechanics) largely right. But it contains **one false margin claim,
one misleading structure name that hides a naked-call tail, an infeasible
roll constraint, a wrong weekly combo composition, and stale parameters** — and,
most importantly, **it is not the strategy this repository actually implements
or has ever backtested.** Fix the identity question first; the rest are
tractable edits. No numbers should be attached to this strategy until it is
run against the real option quotes.
