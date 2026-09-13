# Launch — one page

**Account:** IBKR **paper**, $140,000, portfolio margin. **Port 7497.**
**Tomorrow — Monday 2026-09-14 — this places real paper orders.** Not a rehearsal.

---

## Before the close today

On the machine running TWS/Gateway, with it logged in to the paper account:

```bash
cd /path/to/TradingModel
python3 overnight/run.py --job enter          # NO --transmit — sends nothing
```

Expect: a connect, "newest session <date>", a decision line, a share count, and
`RESULT: ...`. It exercises everything except `placeOrder`.

**If that errors, do not run the live one.** Most likely causes: TWS not running,
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
