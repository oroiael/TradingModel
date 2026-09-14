"""The entrypoint. Three short jobs a day, each started by a scheduler.

    python3 overnight/run.py --job enter    --transmit   # 15:45 ET — place the MOC
    python3 overnight/run.py --job confirm               # 16:05 ET — record the fill
    python3 overnight/run.py --job exit     --transmit   # 09:15 ET — place the MOO
    python3 overnight/run.py --job report                # 09:40 ET — ledger row

`confirm` is not optional bookkeeping. `executions()` reads `ib.fills()`, which
covers the CURRENT session only, so the 16:00 MOC print cannot be read the next
morning. Capture it the same evening or the entry price is lost.

Nothing here loops or sleeps for long. Each job connects, acts once, confirms,
disconnects — so the IB nightly server reset, which falls between `enter` and
`exit`, happens while nothing is connected and has nothing to interrupt.
STRATEGY.md §5.4.

**`--transmit` is the default OFF.** Pass `--transmit` to send real orders.
`readonly` in ib_async does not stop `placeOrder`; the adapter enforces this.

**`--rehearse-now` runs a job outside its clock window**, for a pre-flight of
the data path — connect, fetch 4 years of daily bars, compute RV and the
walk-forward cut, decide, size. It refuses to run alongside `--transmit`,
because the clock guards it removes are the only thing standing between a late
run and a REJECTED auction order:

    python3 overnight/run.py --job enter --rehearse-now    # any time, sends nothing

cron (ET; adjust for the host's timezone):

    45 15 * * 1-5  cd /path/to/TradingModel && python3 overnight/run.py --job enter --transmit >> overnight/out/enter.log   2>&1
     5 16 * * 1-5  cd /path/to/TradingModel && python3 overnight/run.py --job confirm           >> overnight/out/confirm.log 2>&1
    15  9 * * 1-5  cd /path/to/TradingModel && python3 overnight/run.py --job exit  --transmit  >> overnight/out/exit.log    2>&1
    40  9 * * 1-5  cd /path/to/TradingModel && python3 overnight/run.py --job report            >> overnight/out/report.log  2>&1
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import bandlab                                                # noqa: E402

import schedule                                               # noqa: E402
import state as state_mod                                     # noqa: E402
from broker_ext import AuctionBroker                          # noqa: E402
from config import OvernightConfig                            # noqa: E402
from constants import PRIMARY_COST_BPS, COVER_COST_BPS, PRIMARY_SYMBOL  # noqa: E402
Store = bandlab.load("store").Store


def _revision() -> str:
    """The commit this code is actually running from, for the banner.

    Added after a pre-flight failed twice on a traceback from a line that had
    already been deleted upstream: the checkout was stale and nothing on screen
    said so. A `git pull` that reports "Already up to date" while the branch it
    fetched moved is indistinguishable from a successful one unless the running
    code names itself. Never raises — a missing git is not a reason to refuse
    to trade.
    """
    import subprocess
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=_HERE, capture_output=True, text=True,
                              timeout=5)
        if head.returncode != 0:
            return "unknown"
        rev = head.stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=_HERE, capture_output=True, text=True, timeout=5)
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                cwd=_HERE, capture_output=True, text=True, timeout=5)
        out = f"{branch.stdout.strip() or '?'}@{rev}"
        return out + (" +local-edits" if dirty.stdout.strip() else "")
    except Exception:                                         # noqa: BLE001
        return "unknown"


def _banner(cfg: OvernightConfig, job: str, when: dt.datetime) -> None:
    print("=" * 78)
    print(f"  overnight · {job.upper()} · {when:%Y-%m-%d %H:%M:%S %Z}")
    print(f"  {cfg.summary()}")
    print(f"  code: {_revision()}")
    print("=" * 78)


def _make_broker(cfg: OvernightConfig, store) -> AuctionBroker:
    def on_event(level, msg):
        try:
            store.event(level, "broker", msg)
        except Exception:                                     # noqa: BLE001
            pass
        print(f"  [{level}] {msg}", flush=True)

    return AuctionBroker(host=cfg.host, port=cfg.port, client_id=cfg.client_id,
                         account=cfg.account, exchange=cfg.exchange,
                         primary=cfg.primary_exchange,
                         dry_run=not cfg.transmit, on_event=on_event)


def job_report(broker, cfg: OvernightConfig, store) -> int:
    """After the opening auction: reconcile the round trip and write the ledger.

    Reads `executions()` rather than assuming one order made one fill — IBKR
    settles an order in as many executions as the book required.
    """
    intent = state_mod.read_intent(cfg.state_path)
    if intent is None or intent.is_flat:
        print("  no trade to report (flat night)")
        return 0

    if not intent.entry_confirmed:
        print(f"  no confirmed entry fill on file. The `confirm` job must run "
              f"after 16:00 ET — yesterday's MOC print is not readable today, "
              f"because executions() reads the current session only.")
        return 1

    sells = [e for e in broker.executions(intent.leg)
             if str(e.side).upper() == schedule.SOLD]
    if not sells:
        print(f"  no SELL execution for {intent.leg} yet. The opening auction "
              f"prints at 09:30; run this after it. Not writing a ledger row.")
        return 1

    def vwap(rows):
        q = sum(float(r.qty) for r in rows)
        return (sum(float(r.qty) * float(r.price) for r in rows) / q) if q else 0.0

    entry = intent.fill_price
    exit_px = vwap(sells)
    qty = sum(float(r.qty) for r in sells)
    gross = exit_px / entry - 1.0
    cost_bps = PRIMARY_COST_BPS if intent.leg == PRIMARY_SYMBOL else COVER_COST_BPS
    net = intent.multiple * gross - intent.multiple * 2 * cost_bps / 1e4
    equity_after = broker.net_liquidation()

    totals = state_mod.running_totals(cfg.ledger_path, intent.equity_at_entry)
    row = dict(decision_date=intent.decision_date, leg=intent.leg, shares=int(qty),
               entry_price=round(entry, 4), exit_price=round(exit_px, 4),
               gross_pct=round(intent.multiple * gross * 100, 4),
               cost_pct=round(intent.multiple * 2 * cost_bps / 100, 4),
               net_pct=round(net * 100, 4),
               pnl_dollars=round(net * intent.equity_at_entry, 2),
               equity_before=round(intent.equity_at_entry, 2),
               equity_after=round(equity_after, 2),
               peak_equity=round(max(totals["peak"], equity_after), 2),
               drawdown_pct=round(totals["drawdown_pct"], 3),
               primary_rv=intent.primary_rv, primary_threshold=intent.primary_threshold,
               cover_rv=intent.cover_rv, cover_threshold=intent.cover_threshold,
               hold_days="", note="")
    state_mod.append_ledger(cfg.ledger_path, row)

    after = state_mod.running_totals(cfg.ledger_path, intent.equity_at_entry)
    print(f"\n  {intent.decision_date}  {intent.leg}  "
          f"BUY {int(qty)} @ {entry:.2f} (MOC) -> SELL @ {exit_px:.2f} (MOO)")
    print(f"    gross {intent.multiple*gross*100:+.3f}%   "
          f"costs {-intent.multiple*2*cost_bps/100:+.3f}%   "
          f"net {net*100:+.3f}%   ${net*intent.equity_at_entry:+,.0f}")
    print(f"    since inception: {after['trades']} trades, {after['wins']} wins "
          f"({after['win_rate']:.0f}%), {after['total_pct']:+.1f}%, "
          f"max DD {after['drawdown_pct']:.1f}%")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="overnight SOXL/XLU")
    ap.add_argument("--job", required=True,
                    choices=("enter", "confirm", "exit", "report"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--transmit", action="store_true",
                    help="send real orders. Default is a rehearsal.")
    ap.add_argument("--rehearse-now", action="store_true", dest="rehearse_now",
                    help="ignore the clock window, for a pre-flight of the data "
                         "path. Cannot be combined with --transmit.")
    ap.add_argument("--account", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)

    if args.rehearse_now and args.transmit:
        ap.error("--rehearse-now cannot be combined with --transmit. The window "
                 "guards it removes exist because a late auction order is "
                 "rejected, not queued.")

    cfg = OvernightConfig.load(args.config)
    if args.transmit:
        cfg.transmit = True
    if args.rehearse_now:
        cfg.rehearse_now = True
    if args.account:
        cfg.account = args.account
    if args.port:
        cfg.port = args.port
    cfg.validate()

    when = schedule.now_et()
    _banner(cfg, args.job, when)

    os.makedirs(os.path.dirname(cfg.db_path), exist_ok=True)
    store = Store(cfg.db_path)
    broker = _make_broker(cfg, store)
    rc = 0
    try:
        broker.connect()
        if args.job == "enter":
            r = schedule.enter(broker, cfg, asof=when,
                               events=lambda l, m: store.event(l, "enter", m))
            print(f"\n  RESULT: {r.detail}")
        elif args.job == "confirm":
            r = schedule.confirm(broker, cfg, asof=when,
                                 events=lambda l, m: store.event(l, "confirm", m))
            print(f"\n  RESULT: {r.detail}")
        elif args.job == "exit":
            r = schedule.exit_(broker, cfg, asof=when,
                               events=lambda l, m: store.event(l, "exit", m))
            print(f"\n  RESULT: {r.detail}")
        else:
            rc = job_report(broker, cfg, store)
    except schedule.Refused as e:
        print(f"\n  REFUSED: {e}")
        store.event("warn", args.job, f"refused: {e}")
        rc = 2
    except Exception as e:                                    # noqa: BLE001
        print(f"\n  FAILED: {e}")
        traceback.print_exc()
        store.event("error", args.job, f"failed: {e}")
        rc = 1
    finally:
        try:
            broker.disconnect()
        finally:
            store.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
