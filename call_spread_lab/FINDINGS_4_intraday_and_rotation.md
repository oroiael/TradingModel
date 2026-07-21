# SOXL Part 4 — Intraday Harvesting & the 2023 Vol-Regime Rotation

> ⚠️ **CORRECTION (see `FINDINGS_6_real_intraday_correction.md`).** The intraday
> harvesting result in §1 below was produced by selling at the intraday **peak**
> (BS at the underlying's extreme). With the full real intraday option data
> (2022–2026) and **realistic limit-order execution** ("sell when up +50%" fills at
> +50%, not at the peak), intraday threshold-harvesting **underperforms EOD
> close-harvesting at every tenor.** The §1 "intraday helps" conclusion does not
> survive; the §2 vol-regime rotation is unaffected. Read Part 6 for the corrected
> result. The realistic recommendation is the **120-DTE strangle harvested at the
> CLOSE** (Part 3).

Two follow-ups to the strangle harvest (Part 3):
1. **Model intraday harvesting** — SOXL's spikes happen intraday and fade by the
   close; does catching them intraday beat harvesting at EOD?
2. **A rotation to survive 2023** — the one losing year. Detect the regime and
   rotate out (or flip the trade).

Also: **2026 is confirmed real** (user). The "unverified" caveat is removed
throughout; 2026 is treated as the actual melt-up it was.

Engine additions in `strangle_harvest.py`; pricer in `bs.py`; drivers
`run_intraday.py`, `run_rotation.py`; audited by `verify_extras.py`
(**all checks pass** — incl. intraday exit prices reproduced to zero error and a
no-look-ahead check on the regime signal).

---

## 1. Intraday harvesting — it helps (model-dependent)

**Model (stated honestly):** there are no intraday *option* quotes in the data, so
on each day with 5-min *underlying* bars we take the day's **high** (calls) /
**low** (puts) and price the leg with **Black-Scholes using the contract's own
prior-EOD implied vol**; if that modeled peak clears the harvest threshold we sell
there at `peak × (1 − slip)`. Entries/rolls still use real EOD quotes. IV is held
flat intraday — *conservative*, since a real IV pop on a crash would make the put
worth **more** than modeled. `verify.py` already showed BS-with-data-IV lands
inside the quoted bid/ask ~94% of the time, so it is a validated proxy.

**Result** (best cell 120 DTE / 7.5% / take +50% / leg_frac 15%, over the 5-min
window **2023-07 → 2026-07**, 750 days):

| harvest mode | end equity | CAGR | max DD | harvests (intraday / EOD) |
|---|--:|--:|--:|--:|
| **EOD only** | $554,244 | +77% | −25% | 0 / 45 |
| intraday, slip 0% | $1,132,886 | +125% | −16% | 51 / 1 |
| intraday, slip 3% | $803,258 | +101% | −16% | 51 / 1 |
| **intraday, slip 5%** | $644,867 | **+87%** | **−16%** | 51 / 1 |
| intraday, slip 10% | $360,282 | +54% | −17% | 51 / 1 |

* **Two effects, both real:** intraday harvesting captures *more* spikes (51 vs 45)
  and captures them *higher* (at the intraday peak, not the faded close). It
  **raises return and cuts drawdown from −25% to −16%** — banking spikes intraday
  de-risks faster, so the equity path is smoother.
* **But the magnitude is an assumption.** At a plausible 3–5% exit slippage the
  edge is large (+87–101% CAGR vs +77%); at a pessimistic 10% it under-returns EOD
  on CAGR (+54%) while still holding the lower drawdown. The **drawdown benefit is
  robust across all slip levels; the return benefit is not.** Real intraday option
  liquidity determines which column is true.
* By year (EOD vs intraday-5%): the melt-up year **2026 jumps +55% → +95%** (huge
  intraday spikes), while calmer 2023–24 are slightly lower on return (slip cost on
  frequent harvests) — net higher overall and lower drawdown.

**Read:** harvest intraday, but only trust it with a realistic exit-cost
assumption. The full 5-year 5-min upload will let this run over 2022–2026 (the
current window starts 2023-07); the code already picks it up automatically.

---

## 2. The 2023 problem — diagnosis and rotation

### Diagnosis (correcting the earlier "trend" guess)

| year | realized vol | ATM IV | **VRP** | trend eff. | SOXL |
|---|--:|--:|--:|--:|--:|
| 2022 | 1.31 | 1.12 | −0.18 | 0.21 | −87% |
| **2023** | **0.83** | 0.83 | **≈0.00** | 0.24 | +240% |
| 2024 | 0.99 | 0.90 | −0.09 | 0.20 | −3% |
| 2025 | 1.07 | 0.96 | −0.11 | 0.25 | +52% |
| 2026 | 1.30 | 1.30 | −0.00 | 0.35 | +184% |

2023 had the **lowest realized vol (0.83)** — too little movement to harvest, and
the put side just bled. Crucially, **2023 and 2026 had nearly identical VRP (~0)
but opposite outcomes**, and 2026 was *more* trending (0.35) yet made +58%. So the
separator is **realized volatility, not VRP and not trend.** Your instinct — "vol
dropped" — was right.

### The rotation

Rule (all trailing, no look-ahead): when 20-day realized vol `< vol_thresh`, the
long-vol edge is gone, so rotate out of the symmetric strangle —
* **→ trend:** keep only the trend-aligned side (calls if spot > SMA50, else puts);
* **→ cash:** liquidate and sit out ("exit and wait").

Full period 2022-2026, best cell:

| system | end equity | CAGR | max DD | **2023** |
|---|--:|--:|--:|--:|
| strangle **always** (baseline) | $508,997 | **+44%** | −36% | **−14%** |
| rotate **→ trend** (vol<0.90) | $392,343 | +36% | −29% | **−0%** |
| rotate **→ cash** (vol<0.90) | $316,661 | +29% | **−26%** | **+11%** |

* **The rotation fixes 2023.** Rotating to the trend side neutralizes it (−14% →
  ~0); **rotating to cash turns it positive (+11%)** and gives the lowest drawdown.
* **It is a drawdown / consistency tool, not a return booster.** It costs ~8–15
  points of CAGR, because a trailing-vol threshold also pulls you out of *benign*
  low-vol stretches in the good years (2022 +42%→+13%, 2024 +68%→+37%). Max
  drawdown improves (−36% → −26/−29%). Whether it's worth it is a risk-preference
  choice: max raw return → stay always-on; smoother ride / no losing year →
  rotate, preferably to cash.
* Why cash beats trend for 2023 specifically: the trend rotation **whipsaws** as
  vol crosses the threshold (9 rotate-outs and re-entries in 2023), eating the
  gains; sitting in cash avoids both the whipsaw and the put bleed.

Your other two ideas — *tighten the strangle* and *write covered calls* — were
considered: tightening keeps paying for two-sided premium the low-vol regime won't
reward (the same disease), and covered calls require holding the underlying (out of
scope here); the closest no-underlying analog is the trend-side rotation above,
which is what 2023's data rewards (long the up-side of a steady bull).

---

## 3. Honest limitations

* **Intraday is modeled, not observed** (BS + day high/low + prior-EOD IV), and its
  *return* benefit is sensitive to the assumed exit slippage; only the *drawdown*
  benefit is robust. Current window is 2023-07→2026-07 pending the full 5-min file.
* **The rotation threshold (0.90) and signal (20-day rvol) are simple and not
  tuned to a single year** on purpose — tighter tuning could improve the
  return/consistency trade-off but risks curve-fitting to 2023. Treat it as a risk
  dial, not an optimized alpha.
* Everything else from Part 3 still holds: **fractional sizing is mandatory**
  (invest-100% is a −96% drawdown), and results are regime-dependent.

## 4. Reproduce / verify

```bash
git lfs pull && pip install -r call_spread_lab/requirements.txt
cd call_spread_lab
python3 run_intraday.py         # EOD vs intraday harvest + slip sweep
python3 run_rotation.py         # vol-regime rotation vs always-on
python3 verify_extras.py        # INDEPENDENT audit of BS / intraday / rotation
```
