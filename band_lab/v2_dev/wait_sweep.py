"""
Is it the WAITING that killed the strategy, or the PRICE it re-bought at?

The published backtest sold and re-bought inside the same minute, and priced the
re-buy at that minute's OPEN. When the sell happened at the target — near the
top of the minute — the open had already traded, earlier, before the sell. The
simulator was buying at a price that was in the past.

There are two different fixes and they are not the same thing:

  A. Make it WAIT. No re-buy until the next minute (or the one after that).
  B. Let it re-buy in the SAME minute, but forbid a price better than the one
     it just sold at. Price = min(limit, max(open, exit_price)). No waiting at
     all — just no time machine.

If fix B alone destroys the edge, then waiting was never the issue and the
"one minute is too slow" story is wrong. This script runs both, plus a sweep of
how long the wait is, so the two effects can be told apart.

    python3 band_lab/v2_dev/wait_sweep.py
"""

from __future__ import annotations

import dataclasses
import math
import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from backtest_as_executed import (COST_BP_PER_FILL, ROOT, SLEEVES, START, W,  # noqa: E402
                                  stats_line)
from intrabar import load_1min_sessions                            # noqa: E402
from replay import backtest_config, load_sessions                  # noqa: E402
from sleeve import SleeveStateMachine                              # noqa: E402
from strategy_core import FeatureHistory, session_stats            # noqa: E402


def replay_session(decision_bars, fill_bars, sm, step, *, wait_bars: int,
                   honest_same_bar: bool, flatten_at_open_of_next: bool):
    """Same as `backtest_as_executed.replay_session` plus `honest_same_bar`.

    `honest_same_bar` only changes the price of a re-buy that happens in the
    very minute an exit happened: instead of the bar's open, it pays at worst
    the exit price. Every other fill in the file is untouched.
    """
    start, stop = sm.cfg.start_idx, sm.cfg.last_holding_idx
    by_decision: dict[int, list] = {}
    for b in fill_bars:
        by_decision.setdefault(b.idx // step, []).append(b)

    seq = 0
    entry_seq = -1
    blocked_until = -1
    exit_px_this_bar = None
    exit_seq = -1

    for dbar in decision_bars:
        sm.on_bar_open(dbar.idx)
        if start <= dbar.idx <= stop:
            inner = sorted(by_decision.get(dbar.idx, [dbar]), key=lambda b: b.idx)
            for fb in inner:
                seq += 1
                exited = False
                if sm.in_position:
                    br = sm.bracket
                    if fb.low <= br.stop_px:
                        px = min(fb.open, br.stop_px)
                        sm.on_exit_fill(px, dbar.idx, "stop")
                        exited, exit_px_this_bar, exit_seq = True, px, seq
                    elif seq > entry_seq and fb.high >= br.target_px:
                        px = max(fb.open, br.target_px)
                        sm.on_exit_fill(px, dbar.idx, "target")
                        exited, exit_px_this_bar, exit_seq = True, px, seq
                if exited:
                    blocked_until = seq + wait_bars

                entry = sm.working_entry
                if (entry is not None and seq >= blocked_until
                        and fb.low <= entry.limit_px):
                    px = min(entry.limit_px, fb.open)
                    if (honest_same_bar and seq == exit_seq
                            and exit_px_this_bar is not None):
                        px = min(entry.limit_px, max(fb.open, exit_px_this_bar))
                    sm.on_entry_fill(px, dbar.idx)
                    entry_seq = seq
                    if fb.low <= sm.bracket.stop_px:
                        sm.on_exit_fill(min(fb.open, sm.bracket.stop_px),
                                        dbar.idx, "stop")
                        blocked_until = seq + wait_bars
        sm.on_bar_close(dbar)

    if sm.in_position:
        tradable = [b for b in decision_bars if start <= b.idx <= stop]
        if not tradable:
            return
        if flatten_at_open_of_next:
            nxt = [b for b in decision_bars if b.idx == stop + 1]
            if nxt:
                sm.flatten(nxt[0].open, nxt[0].idx)
                return
        sm.flatten(tradable[-1].close, tradable[-1].idx)


def run(symbol, sessions, fine, dates, cfg, **kw):
    history = FeatureHistory()
    returns, n_fills = {}, {}
    for date, dbars in sessions:
        stats = session_stats(dbars)
        atr5, thr80 = history.atr5(), history.thr80()
        if date in dates:
            fbars = fine.get(date, dbars)
            step = 5 if date in fine else 1
            sm = SleeveStateMachine(cfg)
            gate = sm.begin_session(date, atr5, stats.is_half_day, stats.late_open)
            if gate.ok and sm.apply_morning_filter(stats.or30, thr80,
                                                   stats.pos10).ok:
                replay_session(dbars, fbars, sm, step, **kw)
                returns[date] = sm.pnl
                n_fills[date] = len(sm.trades)
        history.append(stats)
    on = pd.Series(returns, dtype=float).sort_index()
    f = pd.Series(n_fills, dtype=float).reindex(on.index).fillna(0.0)
    return on - f * COST_BP_PER_FILL[symbol] / 1e4, f


def main() -> int:
    data = {}
    for s in SLEEVES:
        fine = dict(load_1min_sessions(s, ROOT))
        sessions = load_sessions(s, ROOT)
        dates = {d for d, _ in sessions} & set(fine)
        data[s] = (sessions, fine, {d for d in dates if d >= START})

    CASES = [
        ("published: same minute, priced at the bar's OPEN",
         dict(wait_bars=0, honest_same_bar=False)),
        ("same minute, but never better than the sell price",
         dict(wait_bars=0, honest_same_bar=True)),
        ("wait 1 minute", dict(wait_bars=1, honest_same_bar=False)),
        ("wait 2 minutes", dict(wait_bars=2, honest_same_bar=False)),
        ("wait 3 minutes", dict(wait_bars=3, honest_same_bar=False)),
        ("wait 5 minutes", dict(wait_bars=5, honest_same_bar=False)),
        ("wait 10 minutes", dict(wait_bars=10, honest_same_bar=False)),
        ("wait 30 minutes", dict(wait_bars=30, honest_same_bar=False)),
    ]

    w = 96
    print("=" * w)
    print("WAITING vs PRICING — which one actually killed it?")
    print("   net bp per ON-day, after costs, 1-minute fills, 2022+, "
          "fractional shares as published")
    print("=" * w)
    print(f"{'case':<52}{'SOXL':>9}{'SOXS':>9}{'account':>10}{'t':>7}"
          f"{'trades/day':>12}")
    print("-" * w)

    for label, kw in CASES:
        nets, fills = {}, {}
        for s in SLEEVES:
            sessions, fine, dates = data[s]
            cfg = backtest_config(s)
            nets[s], fills[s] = run(s, sessions, fine, dates, cfg,
                                    flatten_at_open_of_next=False, **kw)
        cal = pd.DatetimeIndex(sorted(set(nets["SOXL"].index)
                                      | set(nets["SOXS"].index)))
        acct = sum(W * nets[s].reindex(cal).fillna(0.0) for s in SLEEVES)
        m, sd, sem, t = stats_line(acct)
        tpd = sum(f.mean() for f in fills.values())
        print(f"{label:<52}{nets['SOXL'].mean()*1e4:>+9.2f}"
              f"{nets['SOXS'].mean()*1e4:>+9.2f}{m:>+10.2f}{t:>7.2f}"
              f"{tpd:>12.2f}")

    print("-" * w)
    print("""
  Row 1 is the published backtest. Row 2 changes ONE thing: a re-buy in the same
  minute as the sell may not be cheaper than the sell. It still re-buys in the
  same minute. No waiting is introduced at all.

  If row 2 falls as far as row 3, then the wait was never the point, and neither
  is the length of the wait. The number was coming from the price.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
