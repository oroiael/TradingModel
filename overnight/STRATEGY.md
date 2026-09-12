# Overnight SOXL — strategy, trading instructions, and the build plan

**Status: research complete, nothing built, nothing traded.** This document is the
specification for a paper deployment. It contains the strategy, the exact orders,
what is verified against what is assumed, the code plan, and the gates that have to
pass before the words "set and forget" are allowed.

Research lives in [`../retreat_lab/`](../retreat_lab/README.md) — every number below
is reproducible from a named script.

---

## 1. What the strategy is, in one paragraph

Hold a leveraged semiconductor ETF **overnight only** — buy at the closing auction,
sell at the next opening auction — and only on nights when trailing realised
volatility is in the lower 60% of its own history. On the nights that filter benches
SOXL, hold **3× notional of XLU** (utilities) instead, subject to the same filter on
XLU's own volatility. Never hold anything through a trading session.

It is not a market anomaly. It is **levered sector beta, collected overnight, gated
by a volatility filter** — see §4.

---

## 2. The specification

### 2.1 Instruments

| leg | instrument | notional | why |
|---|---|---|---|
| primary | **SOXL** | 1.0 × equity | 3× semiconductors; the overnight premium lives here |
| cover | **XLU** | 3.0 × equity | 1× utilities at 3× notional; covers SOXL's benched nights |

XLU rather than UTSL (3× utilities) despite UTSL's better backtest: UTSL has **$43M
AUM and a $5M daily tape**, which caps the whole strategy near six figures. XLU is
$21.8B and $852M/day. XLU also carries the signal more cleanly — t 3.25 against
UTSL's 2.80, correlation with SOXL 0.21 against 0.26.

### 2.2 The signal

For each instrument independently, on decision day **D**:

```
RV20(D) = stdev( close-to-close returns over the 20 sessions ending at D-1 )
          × sqrt(252) × 100

threshold(D) = 60th percentile of that instrument's OWN RV20 history,
               over every session strictly before D
               (requires ≥ 60 prior observations; flat until then)

eligible(D) = RV20(D) < threshold(D)
```

**RV20 ends at D−1, not D.** An MOC order must be submitted before the close, so day
D's close is not known when the decision is made. The backtest was re-run on the
D−1 signal and is unaffected — see §4.3.

The threshold is **walk-forward**: recomputed each day from prior history only. It is
not a fixed number. As of the last research run the SOXL cut sits near 107% annualised
and the XLU cut near 21%, but the engine must compute them, never hardcode them.

### 2.3 The decision rule

```
if eligible(SOXL, D):            hold 1.0 × equity of SOXL overnight
elif eligible(XLU, D):           hold 3.0 × equity of XLU overnight
else:                            hold nothing
```

The two legs are **mutually exclusive** — never both. Gross notional is 1.0× on a
SOXL night and 3.0× on an XLU night.

### 2.4 Sizing

**f = 1.00.** One unit of equity per unit of equity on the SOXL leg. No leverage on
the primary leg.

The XLU leg's 3× notional requires margin, but only on ~23% of nights, and 3:1 on a
1× sector ETF sits well inside a portfolio-margin account. **Do not raise f.** At
f = 2.0 the 2020-03-16 gap would have forced liquidation, and the filtered backtests
start after a burn-in that excludes March 2020 entirely — the reassuring numbers have
the worst event structurally removed.

### 2.5 Cash management

Sweep **25% of any new high-water mark** in trading equity to a separate
interest-bearing account, weekly. High-water mark on the **trading account only**, set
*after* the sweep. See [`../retreat_lab/hwm.py`](../retreat_lab/hwm.py).

Not for the paper run. Turn it on with real money.

---

## 3. Trading instructions

### 3.1 The daily procedure

| when | what |
|---|---|
| after the close on D−1 | compute RV20 and the walk-forward threshold for SOXL and XLU |
| before the MOC cutoff on D | submit **MOC BUY** for the eligible leg, sized to target |
| at the close on D | position established at the official closing price |
| before the open on D+1 | submit **MOO SELL** for the full position |
| at the open on D+1 | position closed at the official opening price |
| after the open on D+1 | record the fill, reconcile, publish the report |

Flat during every trading session. Flat over any night where neither leg is eligible.

### 3.2 Order types — verified from the TWS API source in this repo

| order | construction | source |
|---|---|---|
| MOC buy | `orderType = "MOC"` | `TWS API/samples/Python/Testbed/OrderSamples.py:100` |
| MOO sell | `orderType = "MKT"`, `tif = "OPG"` | `TWS API/samples/Python/Testbed/OrderSamples.py:117` |

`MOC` is a real order type: `TWS API/source/JavaClient/com/ib/client/OrderType.java:25`
— `MOC( Arrays.asList("MOC", "MKT CLS", "MKTCLS") )`.

### 3.3 Why auctions and not market orders

The backtest fills at the official close and the official open. An auction order fills
*at those prints* and crosses no spread, so its cost is commission only.

| route | commission | half-spread | **bp of equity, round trip** |
|---|---|---|---|
| SOXL leg — auction | 0.29 | — | **0.58** |
| SOXL leg — marketable | 0.29 | 0.41 | 1.40 |
| XLU leg — auction | 0.83 | — | **4.98** |
| XLU leg — marketable | 0.83 | 1.18 | **12.06** |

XLU's spread is **tick-constrained**: $0.01 on a $42 share is 2.36 bp, nearly 3× SOXL's
0.82 bp at $122, and it is paid on 3× the notional. The edge disappears entirely at
5 bp/side on the XLU leg. Auction execution is worth **0.12 of Sharpe and ~10 pp of
CAGR** — it is the single most important implementation choice in this document.

The 09:30 one-minute bar ranges **31.4 bp**. A market order sent at 09:30:00 lands
somewhere inside that; MOO gets the auction print.

### 3.4 Liquidity — there is no capacity problem at paper scale

| | AUM | 90-day $ volume/day | 15:59 bar | 09:30 bar |
|---|---|---|---|---|
| SOXL | — | $7,568M | — | — |
| XLU | $21.8B | $852M | $26–38M | $10–16M |

(15:59/09:30 figures from 1-minute bars; the 16:00 closing-auction print is additional.)

---

## 4. What is true, what is assumed, and what is not known

### 4.1 The honest description of the edge

**SOXS settles what this is.** SOXS is −3× the *same* underlying as SOXL. Its overnight
mean is −0.266%/night against SOXL's +0.291% — a near-exact mirror, in every volatility
bucket, summing to +0.024%. A structural close-to-open effect would have *added*. It
cancels. **The return is directional semiconductor beta, not an overnight premium.**

The *filter*, separately, does replicate: RV20 < p60 gives t 2.50 (SOXL), 2.65 (TQQQ),
2.26 (SPXL) on a common window, and survives walk-forward on SOXL (2.53) and TQQQ (2.15).
It fails on FAS. It is a volatility signal, not a trend proxy — trailing-return
conditioning gives Sharpe 0.33 on SPXL and 0.37 on TQQQ where the vol cut gives 0.97
and 1.24.

### 4.2 Backtested performance of exactly this configuration

[`../retreat_lab/final_config.py`](../retreat_lab/final_config.py), 2023-01-03 →
2026-07-29, 895 sessions, measured auction costs, D−1 signal, walk-forward thresholds:

| | |
|---|---|
| total | **+1,233%** |
| CAGR | **106.7%** |
| max drawdown | **−28.9%** |
| Sharpe | **1.85** |
| t | 3.50 |
| nights: SOXL / XLU / flat | 580 (65%) / 204 (23%) / 111 (12%) |
| trades | 784, win rate 58% |
| mean / median per trade | +0.376% / +0.320% |
| best / worst night | +13.42% / **−15.50%** |
| nights worse than −8% | 5 |
| weekend or holiday holds | 163 of 784 (21%) |

| year | sessions | SOXL | XLU | flat | return |
|---|---|---|---|---|---|
| 2023 | 250 | 223 | 26 | 1 | +14.6% |
| 2024 | 252 | 185 | 63 | 4 | **+213.5%** |
| 2025 | 250 | 139 | 62 | 49 | +100.1% |
| 2026 (to 07-29) | 143 | 33 | 53 | 57 | +85.3% |

### 4.3 Do not expect these numbers

This configuration is **the best of a long search**: five threshold variants, sixteen
cover candidates, several execution and lag choices, two window choices, and a start
year chosen to exclude 2022. Researcher degrees of freedom are large and the t-statistic
does not price them.

Specific, known haircuts:

- **2022 is excluded by instruction.** Including it costs the SOXL leg ~17 pp of CAGR.
- **The 20 best nights of 889 are the entire return** on a comparable basket variant.
  Miss them and the result is ordinary.
- **FAS fails outright** — one of four instruments the filter does not work on.
- **No instrument is monotone across RV20 quintiles**, SOXL included. The cut works by
  excluding the top two quintiles, not by a clean gradient.
- **The D−1 signal scored *higher* than the look-ahead version.** That is sample luck,
  not evidence the lag helps; it is recorded as "the look-ahead was not load-bearing".

**A reasonable prior for live is well under half the backtested CAGR, with the full
drawdown.** The paper run exists to find out, not to confirm.

### 4.4 Not verified — and not assumed

| open item | why it matters | how it gets settled |
|---|---|---|
| **MOC submission cutoff time** | the whole auction-execution case; determines when the engine must decide | four MD files the operator is adding; or one live paper session |
| **Whether IBKR routes MOC/MOO to the primary listing auction** | if it does not, costs move from the auction column to the marketable column (Sharpe 1.71 → 1.59) | same |
| **Actual commission tier** | §3.3 uses $0.0035/share; a different tier moves the XLU leg materially | the operator's IBKR statement |
| **Actual margin rate on the real account** | only matters if f > 1 or the XLU leg is financed | the operator's IBKR statement |

The four reference documents (NYSE Arca auctions, IBKR margin, IBKR order types, IBKR
commissions) are **not present in the repository** as of this writing — not on `main`,
not on any branch. Nothing below depends on them, but §4.4 stays open until they land.

---

## 5. The build plan

### 5.1 What already exists and should be reused, not rewritten

`band_lab/live/` is 8,682 lines with 6,654 lines of tests, 232 green, and five live
sessions of hard-won defect fixes against a real broker. **Reuse it.**

| module | lines | verdict |
|---|---|---|
| `broker.py` | ~1,500 | **reuse as-is** — order states, the `PendingCancel` trap, the `103`/`2102` distinction, `is_working()` |
| `orders.py` | 1,019 | **reuse most** — `ensure_flat`, execution-vs-fill discipline, sizing from `position()` not from an execution |
| `store.py` | 218 | **reuse as-is** — SQLite WAL, broker-is-the-only-source-of-truth |
| `report.py` | 1,343 | **reuse and extend** — shadow parity, slippage, trade reconstruction |
| `status.py` | 367 | **reuse and extend** — phone snapshot, secret gist, `--no-dollars` |
| `watchdog.py` | 457 | **reuse as-is** — heartbeat, stale detection |
| `config.py` | 184 | **reuse the pattern**, new fields |

### 5.2 What must be new

| module | replaces | why |
|---|---|---|
| `overnight/core.py` | `strategy_core.py` | RV20 + walk-forward percentile + two-leg selection, pure functions, no I/O |
| `overnight/features.py` | `features.py` | daily close-to-close RV20, not intraday ATR/opening-range |
| `overnight/schedule.py` | the `engine.py` poll loop | **two moments a day**, not a continuous intraday loop |
| `overnight/run.py` | `run.py` | entrypoint for the new timetable |
| `overnight/replay.py` | `replay.py` | drive `core.py` with historical daily bars for parity |

**Not needed at all:** `intrabar.py` (498 lines) — there is no intrabar stop, no
trailing, no OCA bracket.

### 5.3 The simplification worth naming

Band_lab's eight live defects were almost all in the bracket / modify / OCA path:
241 shares left unprotected, a `PendingCancel` leg holding shares through a flatten,
a rejected modify producing a ghost order. **This strategy has none of that path.**
Two orders a day, both auction, no stops, no modifies, no OCA, no re-entries. The
operational risk surface is a small fraction of band_lab's — which is the main reason
to believe a paper run can reach "set and forget" at all.

The risks that remain, and they are real:
- an MOC that misses the cutoff leaves the account **flat when it should be long**
- an MOO that fails to submit leaves the account **long into a session** — the one
  state this strategy must never be in
- a stale or wrong RV20 silently trades the wrong nights

### 5.4 Phases and gates

| phase | work | gate to pass |
|---|---|---|
| **P0** | port `core.py` + `features.py`; unit tests | `replay.py` reproduces `final_config.py`'s ledger **exactly**, row for row |
| **P1** | `schedule.py` + `run.py`, transmit **OFF** | 10 sessions where the engine's intended orders match the ledger, no orders sent |
| **P2** | paper, transmit ON, **attended** | 10 sessions, every fill reconciled, zero unintended session exposure |
| **P3** | reporting (§6) | per-trade report fires on 10 consecutive trades without manual help |
| **P4** | `watchdog.py` wired, unattended | 20 sessions unattended, no missed MOC, no overnight-into-session |
| **P5** | "set and forget" | all of the above, plus §4.4 closed |

**Nothing skips a gate.** Band_lab's own record is eight defects in five live sessions,
every one invisible to a green test suite, because they lived in the broker path.

---

## 6. Reporting

Three separate things, deliberately.

### 6.1 The phone check — "what is the situation right now"

`status.py` already does this and already solves the constraint that matters:

> IBKR permits one login per user, so opening TWS or the IBKR mobile app
> **disconnects the engine's session**. Checking on the run breaks the run.

So the phone must **not** run TWS or the IBKR app. `status.py` reads the engine's own
SQLite database and publishes to a **secret gist** — authenticated, unlisted, stable
URL, bookmark once. `--no-dollars` publishes states, counts and basis points with no
absolute account size, which is the version to default to on a phone.

Needs `BANDLAB_GITHUB_TOKEN` with `gist` scope. Extend it with: which leg is armed
tonight, tonight's RV20 against tonight's threshold, and whether the MOC was
acknowledged.

### 6.2 The per-trade report — "what did that trade do"

New. Fires after the MOO fill is reconciled, once per trade:

```
2026-09-15  SOXL  BUY 818 @ 122.28 (MOC)  →  SELL 818 @ 123.44 (MOO)
  gross  +0.949%    costs  -0.058%    net  +0.891%   $+891 on $100,000
  hold   1 calendar day
  signal RV20 96.3 < threshold 107.1
  since inception: 47 trades, 28 wins (60%), +18.4%, max DD -6.2%
```

Delivered to the same gist, appended to a running ledger, so the phone sees it without
any app that could disconnect the engine.

### 6.3 The running total — "how is the strategy doing"

A single CSV the engine appends to, one row per trade, from inception:
`date, leg, shares, entry, exit, gross_pct, cost_pct, net_pct, equity, peak, drawdown`.

Everything in §6.2 is derived from it, and `report.py`'s shadow-parity diff runs
against it — so the live ledger and the backtest ledger have the same shape and can be
compared row for row. That comparison is the whole reason to run on paper.

### 6.4 What to alert on, versus what to merely display

Alert (push, immediately):
- MOC cutoff approaching with no order acknowledged
- **position still open after 09:35** — the one unrecoverable state
- heartbeat stale during a decision window
- fill price more than 50 bp from the official auction print

Display only: P&L, win rate, drawdown, which leg is armed. **Never alert on P&L.**
An alert that fires on a losing night trains the operator to intervene, and the 20
best nights out of 889 are the entire return.

---

## 7. Immediate next steps

1. **Operator:** confirm the four reference documents actually pushed — they are not in
   the repository. Re-push if needed.
2. **Operator:** confirm which IBKR account is the paper account. The connected account
   currently shows **NLV $1,155.78, flat, no margin loan**, which is not the
   portfolio-margin account described earlier.
3. **Build P0** — `overnight/core.py` and `overnight/features.py`, with the parity gate
   against `final_config.py`'s ledger.

Nothing in P1–P5 should start before P0's parity gate is green.
