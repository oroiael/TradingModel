# SOXL Weekly-Income Strategy Recommendations

Evidence source: `volatility_pricing_lab.py` (this branch) — an analytical test
suite run over **both** datasets used by the other two projects:

* `SOXL_5min_3Years.csv` — 58,560 five-minute bars, 2023-07-07 → 2026-07-09
* `SOXL_Options_2024/2025/2026.csv` (via `soxl_options_loader.py`) — 919,090
  EOD option quotes with greeks/IV, 627 trade dates, 2024-01-02 → 2026-07-02

Full numbers: `qa/pricing_lab_report.txt`. Machine-readable tables:
`pricing_lab/*.csv`. Everything below is priced with the project's execution
rule (sell = bid + 0.20·spread, buy = ask − 0.20·spread; bid=0 rejected).

---

## 1. What the tests found (pricing of options relative to the underlying)

**F1 — The volatility is real and two-sided.** Annualized realized vol 115%
(close-close). 40% of days move >5%; 12.7% move >10%. Weekly Mon-10:00→Fri-15:30
moves: sd 13.9%, and the **upside tail is fatter than the downside**
(p99 +37.8% vs p01 −31.5%; weeks beyond +10%: 24% vs −10%: 21%). Overnight gaps
carry 41% of total variance — no intraday-only scheme can hedge them.

**F2 — Front-week options are the only rich tenor; long-dated options were
systematically CHEAP.** ATM implied vs subsequently-realized vol (VRP):

| tenor | mean IV | fwd realized | mean VRP | seller paid enough |
|---|---|---|---|---|
| 7d | 106% | 105% | **+0.7 pts** | 56% of weeks |
| 30d | 100% | 114% | −14 pts | 43% |
| 90d | 100% | 122% | −22 pts | 35% |
| 180d | 94% | 122% | **−29 pts** | 12% |

The market persistently under-priced long-horizon SOXL volatility. **Sell the
front, own the back** is the structural trade this surface pays for.

**F3 — The term structure is inverted 67–68% of all days** (7d ATM IV averages
6.7 pts over 30d, 9.6 pts over 180d). This is a standing disparity, not a
timing signal.

**F4 — Put skew is persistently rich.** 25Δ puts carry +10 to +12 IV points
over 25Δ calls at every tenor, on ~90% of days. The put side is where sellers
are paid; the call side is structurally cheap.

**F5 — Put-call parity shows a carry disparity.** Implied forwards price SOXL
carry at ~2%/yr vs ~4–5% T-bills — synthetic longs (long call + short put) are
priced ~2–3%/yr *cheaper* than holding shares. (Part of this gap may be SOXL's
irregular dividend — see data requests.) Executable conversion "profits" >$0.02
exist on 21% of contract pairs but are the hard-to-borrow/financing fee, not
free money. **Practical meaning: replacing stock with long calls is
structurally subsidized; classic covered calls (long decaying shares + selling
the cheap side) are structurally taxed.**

**F6 — Naked weekly premium selling LOST money in every one of the 30
permutations tested** (put/call/strangle/straddle × delta 10–50, 119 Mondays,
real fills). Example: 25Δ short put — 77% win rate, avg credit $1.11, total
**−$70.6/share**. 10Δ short call — 90% win rate, total −$34.2/share. High win
rate + 3x tails = negative expectancy. This kills "sell naked and hope" and
any covered call without upside participation.

**F7 — Losses are extremely concentrated, so tail-capping is cheap relative to
what it saves.** Ex-worst-3-weeks the 25Δ short put flips to **+$2.6**;
ex-worst-5 it's +$23.4. The whole game is 3–5 weeks per 2.5 years
(Apr-2025 tariff crash, Jun-2026 melt-up/crash). In the wing test, buying a
put wing cost 37% of credit but *improved* total P&L (−$63 vs −$112 naked) and
cut the worst week. **Protection was not a drag in this data — it was
accretive.**

**F8 — The long-dated anchor put is cheap insurance.** A ~150-DTE ATM put cost
~25% of spot, bled only ~$0.21/week on average (~$0.38 in flat weeks) while
paying +$4.23 average in crash weeks (23 crash weeks in sample). One weekly
20-25Δ put credit (~$0.85–1.11) covers 2–5× the bleed.

**F9 — Liquidity boundary.** Median spreads: 12–16% of mid at 20–40Δ weekly,
66% at 0–10Δ (weekly wings are expensive to trade), tightening to 6–9% at
100+ DTE. 27% of ≤9-DTE 0–10Δ quotes have no bid at all. Strategies must live
in the 15–40Δ band for weeklies; far wings should be placed where strikes are
liquid, not at fixed deltas.

**Irregularities checked and dismissed:** 6% of rows have IV=0 with live
quotes (IV column artifact — quotes usable); 0.4–0.9% of ITM quotes sit below
intrinsic (stale-quote artifacts, not harvestable); zero crossed markets.

---

## 2. Recommended strategies (pick one; I'll then build its backtest)

Ranked by fit to the evidence. "Income" = weekly realized credits; every
structure below has a defined or hedged tail, per F6/F7.

### R1. Put Diagonal Income Engine — *sell the rich front, own the cheap back* ⭐ best evidence fit
- **Structure:** Own 1 put, 120–180 DTE, ATM-ish (the anchor). Sell 1 put
  weekly at 20–25Δ against it. Roll the anchor at ≤45 DTE or after ±10% spot
  drift; re-sell the weekly every Monday.
- **Why it fits:** Simultaneously harvests F2 (short the only positive-VRP
  tenor), F3 (inversion), F4 (rich put skew) while long the under-priced tenor
  (F2 back-end, F8). Defined risk (strike width), so IBKR margin is the width,
  not cash-securing the put.
- **Cash mechanics:** ~$0.85–1.11/share weekly credit vs ~$0.21–0.38 anchor
  bleed → positive weekly carry, with the anchor exploding in exactly the
  weeks that killed every naked structure (F7).
- **Mode:** Set-and-forget-ish (one Monday order, one Friday check) or active
  (delta-triggered roll of the short leg via IBKR).

### R2. Call Diagonal / "Poor Man's Covered Call" — *stock replacement*
- **Structure:** Replace shares with a deep-ITM (70–80Δ) call, 120–180 DTE.
  Sell weekly 15–20Δ calls against it. Roll the long at ≤45 DTE.
- **Why it fits:** F5 says synthetic long exposure via calls is priced
  ~2–3%/yr cheaper than shares; F2 says the long-dated option you own is
  cheap vol; F1 says the up-tail is the fat one — the long call participates
  where a covered call (or short call) gets destroyed (F6). Capital outlay is
  ~⅓ of shares, and max loss is the (cheap) call premium instead of 3x-ETF
  drawdown.
- **Cash mechanics:** weekly call credit ($0.26–0.63 at 10–25Δ) against a slow
  long-leg bleed; upside capped only for the week, re-struck every Monday.
- **Mode:** Set-and-forget. This is the direct, evidence-backed replacement
  for the covered-call leg of the original project.

### R3. Asymmetric Weekly Iron Condor — *pure defined-risk income*
- **Structure:** Every Monday sell 20–25Δ put + 10–15Δ call, buy a put wing
  $2–4 lower and a call wing at the nearest liquid strike above. Hold to
  Friday. No overnight-tail exposure beyond the width — margin = width−credit.
- **Why it fits:** F7 — wings *added* P&L in this window while capping the
  exact 3–5 weeks that sank everything; F4 pays the put side, and capping the
  call side is essential because the up-tail is fatter (F1). F9: keep wings at
  liquid strikes, not fixed deltas.
- **Mode:** Truly set-and-forget; the easiest to automate as one atomic BAG
  order in IBKR. Lowest capital of the five.

### R4. Weekly Jade Lizard — *income with zero upside risk*
- **Structure:** Sell 20–25Δ put + sell a call vertical (short 15–20Δ call,
  long next liquid strike up) such that total credit ≥ call-spread width. If
  the credit test fails that week, fall back to R3 or skip the call side.
- **Why it fits:** Removes the up-tail entirely (the fatter tail, F1/F6 —
  short calls alone lost −$34/share) while keeping the rich put-skew premium
  (F4). Scan says the strict no-upside-risk version priced on ~21% of weeks;
  a near-lizard (credit ≥ 80% of width) prices far more often — the backtest
  would quantify the ladder.
- **Mode:** Active-lite; rule-based enough for IBKR automation (one combo
  order + one conditional).

### R5. ATM Put Calendar / Double Calendar — *harvest the inversion itself*
- **Structure:** Sell 7-DTE ATM put, buy 30–45-DTE put at the same strike
  (calendar). Double version adds the call calendar. Close/re-strike each
  Friday; the long leg is rolled monthly.
- **Why it fits:** The purest expression of F3 (sell 107% IV, own 101%) and
  F2 (the leg you own is the under-priced one). Net long vega — it *makes*
  money in the IV spikes that hurt R3/R4, so it's the natural diversifier or
  regime-switch partner.
- **Mode:** Active; needs weekly re-pricing of the long leg. Good candidate
  for automation, but the most path-dependent of the five — the backtest
  matters most here.

### R6. Hedged Wheel 2.0 (upgrade of the original project's trade)
- **Structure:** The original covered-call + 6-month anchor put, with two
  evidence-driven amendments: (a) hold the anchor put per F8 rules (roll on
  drift, not calendar only); (b) sell the weekly call only when short-tenor
  IV is above its 30d level AND spot is not in a melt-up (e.g., above its
  20-day high) — otherwise skip the call and keep upside, because F5/F6 show
  the call side is the cheap side and the up-tail is what covered calls lose.
- **Why it's listed:** Continuity with the two existing backtests; honest
  verdict from the data is that R1/R2 dominate it (same income engines
  without holding the decaying 3x shares), but it's the minimal-change path.

**What the data says NOT to do:** naked short puts/strangles/straddles at any
delta (F6), classic always-on covered calls (F5+F6), anything unhedged held
over gaps (F1), and weekly far-OTM wings bought at 0–10Δ market prices (F9 —
place wings at liquid strikes instead).

---

## 3. Additional data worth requesting (in priority order)

1. **SOXL option chains 2021–2023** (incl. the 2022 −85% bear) — the current
   window has only two crash regimes; R1–R5 need a third, different one.
2. **Intraday option quotes** (even hourly) for 2024–2026 — the strategy docs
   specify Monday 10:00 entries and delta-triggered mid-week rolls; EOD
   snapshots force an EOD proxy today (flagged inside the lab).
3. **T-bill / SOFR daily series** — turns the F5 carry gap into a precise
   borrow-fee estimate.
4. **SOXL dividend history** — needed to split the F5 parity gap between
   financing and dividends.
5. **SOXX/SMH + VIX/VXN daily** — external regime gates (the internal
   term-slope gate is too weakly discriminating: inverted 90% of Mondays).
6. **SOXL borrow-fee history (IBKR)** — validates the conversion-scan finding.

## 4. How to reproduce

```bash
git lfs pull                       # materialize the CSVs
pip install pandas numpy scipy
python3 volatility_pricing_lab.py  # ~2 min; writes qa/pricing_lab_report.txt
                                   # and pricing_lab/*.csv
```

**Next step:** pick one of R1–R6 and I will build its dedicated backtest
(weekly ledger CSV in the same format as the existing projects: per-leg
prices, costs, units, outcomes, capital/sweep accounting).
