# Launch — one page

**Account:** IBKR **paper**, $140,000, portfolio margin. **Port 7497.**
**Tomorrow — Monday 2026-09-14 — this places real paper orders.** Not a rehearsal.

---

## Pre-flight — run this tonight

On the machine running TWS/Gateway, with it logged in to the paper account:

```bash
cd /path/to/TradingModel
git pull
python3 overnight/run.py --job enter --rehearse-now
```

`--rehearse-now` is what lets this run at 8pm instead of only between 15:30 and
15:50. It **refuses to run with `--transmit`** — the clock guards it removes are
the only thing standing between a late run and a rejected auction order — so it
cannot send anything, ever.

Expect roughly:

```
  OUT-OF-HOURS REHEARSAL — the 15:30:00-15:50:00 MOC window is not enforced.
  SOXL: 1002 dates overlap ...; worst close mismatch 0.0xx% on ...
  XLU:  1002 dates overlap ...; worst close mismatch 0.0xx% on ...
  newest session 2026-09-11 (D-1) | SOXL rv 98.68% vs cut 106.27% | XLU rv 13.82% vs cut 16.81%
  SOXL at 1.00x
  no live quote for SOXL out of hours; sizing this rehearsal off the ... close
  BUY MOC 1149 SOXL @ ~$121.82 = $140,000 (1.00x on $140,000)
  rehearsal — nothing to confirm
  RESULT: MOC 1149 SOXL id=-1 acknowledged
```

A negative order id means synthetic: nothing reached IBKR.

### Check it against this

Computed here from the committed research dailies, which run through Friday
2026-09-11 — the same D−1 the live fetch will see:

| | RV20 | p60 cut | |
|---|---|---|---|
| **SOXL** | 98.68% | 106.27% | eligible by 7.6pp |
| **XLU** | 13.82% | 16.81% | eligible by 3.0pp |

**Expect SOXL at 1.00×, about 1,149 shares near $121.82.** SOXL is eligible so it
wins outright; XLU is only ever the fallback. The margin is wide enough that the
answer does not depend on the history length — 5 years gives the same leg.

If the rehearsal prints something else, **stop and read why** before tomorrow.
A few tenths of a percent on the RV is normal (the live feed is the closing
auction print; the research file is too, but they are fetched separately). A
different *leg* is not.

The two `worst close mismatch` lines are a basis check: the live feed has to be
the same price series the threshold was fitted on. Anything under 0.2% is fine.
A number in the percent range means the feed is dividend-adjusted and the whole
volatility history is on a different footing — the run says so explicitly.

**If it errors, do not run the live one.** Most likely causes: TWS not running,
API not enabled, wrong port, or `ib_async` missing from the Python you used.

---

## The four jobs

| ET | command | what happens |
|---|---|---|
| **15:45** | `python3 overnight/run.py --job enter --transmit` | buys SOXL or XLU **market-on-close** |
| **16:05** | `python3 overnight/run.py --job confirm` | records the fill price |
| **09:15** | `python3 overnight/run.py --job exit --transmit` | sells **market-on-open** |
| **09:40** | `python3 overnight/run.py --job report` | writes the P&L row |

Run them by hand tomorrow. Once you've seen a clean round trip, put them in cron
(lines are in `run.py`'s docstring).

**`--transmit` is required to send anything.** Without it, nothing reaches the market.
**Never pass `--rehearse-now` to a real run** — it is rejected if you try.

---

## What to expect tomorrow

One of three outcomes at 15:45, and all three are correct behaviour:

| | |
|---|---|
| **SOXL** | ~1,144 shares, ~$140,000. Happens ~65% of nights |
| **XLU** | ~8,258 shares, ~$350,000 (2.5× on margin). ~23% of nights |
| **FLAT** | no order at all. ~12% of nights |

Overnight P&L on a traded night is typically **±1–3%**, mean about **+0.38%**.
A bad night can be **−5% or worse**; the worst in the backtest was −15.5%.

Backtested at this configuration (2023→2026, 895 sessions): +1,233% total,
106.7%/yr, max drawdown −28.9%, 58% of nights positive.
**Do not expect that live** — it is the best of a long search. See `STRATEGY.md` §4.3.

---

## Where the money and the numbers are

- `overnight/out/ledger.csv` — one row per completed trade, inception to date
- `overnight/out/state.json` — tonight's intent
- `overnight/out/overnight.db` — event log

---

## If something goes wrong

**The only state that matters: holding a position after 09:30.** If `exit` fails
or you miss the 09:29 deadline, **sell it manually in TWS**. Everything else can
wait; that cannot.

Any job refusing is safe by design — it leaves the account flat or unchanged.
A refusal prints `REFUSED:` and the reason.

**There is no watchdog yet.** Nothing will flatten you automatically if `exit`
does not run. That is P4, and until it exists, check at 09:40 that the account
is flat.
