# SOXL Part 3 — Active Long-Strangle Volatility Harvesting

Your idea: hold a long OTM **call** *and* long OTM **put** (both long-dated), and
**actively harvest** whichever leg the move inflates — sell the profitable side,
re-arm it around the new price, leave the stale side as a floor/ceiling, and add a
new floor/ceiling when price runs >30% away. "True harvesting," not buy-and-hold.

This is the natural way to monetize the Part-2 finding that **SOXL's volatility
risk premium is negative** — options are chronically *cheap* vs. how far it
actually moves. Tested exactly on your matrix: **expirations {30, 60, 90, 120,
150, 180} × strike distances {2, 5, 7.5, 10, 12.5, 15%}.**

Engine: `strangle_harvest.py` (daily EOD marks, 20% fill rule, real cash account).
Independently audited by `verify_strangle.py` — **all checks pass** (engine fills
match the raw CSVs to zero error; end cash/equity reconcile to the penny from the
trade log; harvesting confirmed to cut drawdown).

---

## Verdict (data only)

**This is the first structure in the project with a genuinely attractive
risk/reward — because it is *long* SOXL's underpriced volatility and actively
banks the spikes before they decay.** With survivable sizing:

* Best region is **120–150 DTE at 2–12.5% strikes** — *positive in every cell*.
  Best single cell **120 DTE / 7.5% OTM: +44% CAGR, −36% max drawdown**, $100k →
  $509k over 4.5 years (63 harvests). The 120- and 150-DTE **rows are uniformly
  green**, so this is a robust region, not one lucky cell.
* **Active harvesting genuinely beats buy-and-hold:** no-harvest = +27% CAGR /
  **−67%** DD; harvest at +50% = +44% CAGR / **−36%** DD. Harvesting nearly halves
  the drawdown *and* raises return — and it turns the 2024 chop (which *destroys*
  a passive strangle, −75% in the probe) into **+68%** by banking the round-trip
  swings.
* **Your instinct on frequent harvesting is right for risk control.** A low
  harvest trigger (your +2–5%) gives the *smoothest* ride (−25% DD) at a lower
  return (+28% CAGR); harvesting at bigger spikes (+50%) maximizes return (+44%)
  at a somewhat deeper DD. It's a return↔drawdown dial, not right-vs-wrong.

**Two hard caveats, same as every other structure here:**
1. **"Invest 100%" is still ruinous.** At full deployment (≈100% of capital in
   premium) the best cell shows a **−96% drawdown** even though it ends high —
   fully-deployed long premium gets shredded in low-movement stretches. The
   attractive numbers above require **fractional sizing (~10–15% of equity per
   leg).** Sizing dominates survival, again.
2. **Regime-dependent and partly on unverified data.** The edge leans on
   2024–2026 (and 2026 is the unverified melt-up, see `README.md` §2), and the one
   steady bull year (2023) was **negative (−14%)** — a strangle needs *movement /
   reversals*, and a smooth grind gives it little to harvest.

---

## 1. The grid — expiration × strike distance (`strangle_scoreboard.csv`)

CAGR, take +50%, leg_frac 15% (survivable), 2022-01 → 2026-07:

| DTE \ dist | 2.0% | 5.0% | 7.5% | 10% | 12.5% | 15% |
|---|--:|--:|--:|--:|--:|--:|
| **30** | −13% | −2% | −15% | −20% | +20% | +19% |
| **60** | −9% | −3% | +8% | −15% | −16% | +4% |
| **90** | +15% | +19% | +2% | +3% | +3% | +24% |
| **120** | +29% | +31% | **+44%** | +22% | +37% | +21% |
| **150** | +18% | +20% | +17% | +24% | +22% | +16% |
| **180** | +8% | +5% | −0% | −13% | −13% | −13% |

Max drawdown is *also* best in the 120–150 band (−31% to −47%) and worst at 30 DTE
(−72% to −87%). **Short tenors bleed** (theta decays the premium before SOXL
moves); **very long/very far** legs are too expensive to compound. The
**120–150-day, 5–10%-OTM** pocket is the sweet spot on both return and drawdown.

## 2. Sizing — the "invest 100%" answer (90 DTE, 10% dist, take +50%)

| leg_frac (per leg) | end equity | CAGR | **max DD** | peak deployment |
|---|--:|--:|--:|--:|
| 5% | $100,763 | +0% | **−22%** | 19% |
| 10% | $109,555 | +2% | −42% | 39% |
| 15% | $113,904 | +3% | −57% | 62% |
| 25% | $99,922 | −0% | −80% | 99% |
| **50% (invest ≈100%)** | $209,160 | +18% | **−96%** | 100% |

Invest-100% ends higher only by riding a −96% drawdown that no real account
survives. The strategy is viable **only** de-levered. (This cell — 90/10% — is not
the best; at the best cell 120/7.5% the same fractional sizing produces the +44%
CAGR / −36% DD above.)

## 3. Harvest trigger sweep (best cell 120 DTE, 7.5%, leg_frac 15%)

| harvest when leg up… | end equity | CAGR | max DD | # harvests | avg harvest gain |
|---|--:|--:|--:|--:|--:|
| +5% (your floor) | $298,377 | +28% | **−25%** | 189 | +18% |
| +10% | $293,913 | +27% | −40% | 144 | +25% |
| +25% | $327,892 | +30% | −25% | 98 | +36% |
| **+50%** | **$508,997** | **+44%** | −36% | 63 | +66% |
| +100% | $326,571 | +30% | −56% | 33 | +123% |
| +200% | $447,149 | +40% | −60% | 20 | +227% |
| no-harvest (hold to expiry) | $294,569 | +27% | −67% | 0 | — |

Every harvesting variant beats never harvesting. Harvest often → lower return,
much lower drawdown; harvest on bigger spikes → higher return, deeper drawdown.
**Note:** commissions are not modeled — the +5% variant makes 189 harvests (plus
opens/rolls), so per-contract commissions would erode the high-frequency triggers
most; the 20% fill rule already charges the bid/ask cost on every trade.

## 4. By year (best cell 120 DTE, 7.5%, take +50%, leg_frac 15%)

| year | SOXL regime | strategy return |
|---|---|--:|
| 2022 | −87% bear | **+42%** (put side spikes, harvested) |
| 2023 | +240% steady bull | **−14%** (smooth grind = little to harvest) |
| 2024 | flat round-trip to $68 and back | **+68%** (harvesting banks the swings) |
| 2025 | crash to $8 + recovery | +59% |
| 2026 | melt-up* | +58% |

The single most important line is **2024**: a passive strangle *loses ~75%* there
(the probe), but the active harvest *makes +68%* — direct evidence that harvesting,
not just being long vol, is where the value is. *2026 is unverified.

---

## 5. Why it works (and when it won't)

* **Long the underpriced tail.** Mean implied − realized vol on SOXL is **−8 vol
  points** (Part 2). A long strangle buys that cheap vol; the harvest converts the
  frequent large intra-life spikes (best leg peaks ≥+100% in 75% of windows) into
  realized cash before theta reclaims them.
* **It needs movement, not direction.** It profits from *volatility and
  reversals* (2022 crash, 2024 round-trip, 2025 V), and struggles in a smooth
  one-way grind (2023) where one side just decays.
* **It is long-gamma/long-vega**, the exact opposite of the credit spreads in
  Parts 1–2 that were short the tail and lost. Same instrument, right side of the
  trade.

## 6. Honest limitations

* **Fractional sizing is mandatory** — "invest 100%" is a −96% drawdown. Even the
  recommended sizing carries −25% to −57% drawdowns; this is an aggressive,
  high-variance strategy.
* **In-sample grid.** 120/7.5% is the best *cell* in this sample; trust the
  *region* (120–150 DTE) more than the exact cell. Forward results will differ.
* **Regime + 2026.** Leans on 2024–2026; 2026 is unverified; 2023 was negative.
  Do not annualize +44% as a durable expectation.
* **Daily EOD marks only.** Real harvesting is intraday — spikes that appear and
  fade within a day are neither captured nor charged here. No commissions/taxes;
  early assignment on the (long) legs is not a risk since we are the holder.

## 7. Reproduce / verify

```bash
git lfs pull && pip install -r call_spread_lab/requirements.txt
cd call_spread_lab
python3 probe_strangle.py       # grounding: strangle economics & harvest fuel
python3 run_strangle.py         # grid + sizing + trigger sweeps -> strangle_*.png/csv
python3 verify_strangle.py      # INDEPENDENT audit -- all checks PASS
```
