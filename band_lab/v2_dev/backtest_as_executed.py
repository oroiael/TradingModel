"""
The backtest, run the way the engine actually trades.

Four things the published backtest did that the live engine cannot:

  1. Sold and re-bought inside the same minute, pricing the re-buy at that
     minute's OPEN — a price that traded before the sell. Here the re-buy waits
     for the next 1-minute bar, which is the finest "next available price" the
     data supports.
  2. Bought fractional shares. The engine buys whole shares.
  3. Priced to the cent without tick rounding.
  4. Exited at the 15:50 bar close, for free. The engine sends a market order at
     15:55 and fills in the bar after. Modelled here at the 15:55 bar's open.

None of these is a strategy parameter. All four are the simulator describing a
trader who does not exist.

    python3 band_lab/v2_dev/backtest_as_executed.py
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
ROOT = os.path.dirname(_BAND_LAB)
for _p in (os.path.join(_BAND_LAB, "live"), os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intrabar import load_1min_sessions                            # noqa: E402
from replay import backtest_config, load_sessions                  # noqa: E402
from sleeve import SleeveStateMachine                              # noqa: E402
from strategy_core import FeatureHistory, session_stats            # noqa: E402

START = pd.Timestamp("2022-01-01")
COST_BP_PER_FILL = {"SOXL": (65.6 - 61.9) / 3.17, "SOXS": (57.7 - 48.1) / 3.36}
SLEEVES = ("SOXL", "SOXS")
W = 0.50
TRADING_DAYS = 252


def replay_session(decision_bars, fill_bars, sm, step, *, wait_bars: int,
                   flatten_at_open_of_next: bool):
    """One session. Decisions on 5-minute bars, fills on 1-minute bars.

    `wait_bars` is the whole point: after an exit, the resting BUY LIMIT may not
    fill for this many fill-bars. At 1-minute fills, `wait_bars=1` means the
    re-buy takes the next minute's price, never the price of the minute the sell
    happened in.

    `flatten_at_open_of_next` exits at the open of the bar AFTER the last
    holding bar — 15:55 — instead of the 15:50 close.
    """
    start, stop = sm.cfg.start_idx, sm.cfg.last_holding_idx
    by_decision: dict[int, list] = {}
    for b in fill_bars:
        by_decision.setdefault(b.idx // step, []).append(b)

    seq = 0
    entry_seq = -1
    blocked_until = -1              # no entry fill before this fill-bar sequence

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
                        sm.on_exit_fill(min(fb.open, br.stop_px), dbar.idx, "stop")
                        exited = True
                    elif seq > entry_seq and fb.high >= br.target_px:
                        sm.on_exit_fill(max(fb.open, br.target_px), dbar.idx,
                                        "target")
                        exited = True
                if exited:
                    blocked_until = seq + wait_bars

                entry = sm.working_entry
                if (entry is not None and seq >= blocked_until
                        and fb.low <= entry.limit_px):
                    sm.on_entry_fill(min(entry.limit_px, fb.open), dbar.idx)
                    entry_seq = seq
                    if fb.low <= sm.bracket.stop_px:
                        # A stop is a market order once touched; it does not get
                        # the stop price for free when the bar traded through it.
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
    returns, rows = {}, []
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
                for t in sm.trades:
                    rows.append({"date": date, "ret": t.ret, "outcome": t.outcome})
        history.append(stats)
    on = pd.Series(returns, dtype=float).sort_index()
    tr = pd.DataFrame(rows)
    f = (tr.groupby("date").size().reindex(on.index).fillna(0)
         if len(tr) else pd.Series(0.0, index=on.index))
    return on, tr, on - f * COST_BP_PER_FILL[symbol] / 1e4


def stats_line(x):
    m, sd = x.mean() * 1e4, x.std(ddof=1) * 1e4
    sem = sd / math.sqrt(len(x))
    return m, sd, sem, (m / sem if sem else float("nan"))


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def main() -> int:
    ap = argparse.ArgumentParser(description="backtest as executed")
    ap.add_argument("--out", default=os.path.join(_HERE, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    data = {}
    for s in SLEEVES:
        fine = dict(load_1min_sessions(s, ROOT))
        sessions = load_sessions(s, ROOT)
        dates = {d for d, _ in sessions} & set(fine)
        dates = {d for d in dates if d >= START}
        data[s] = (sessions, fine, dates)

    live_cfg = dict(whole_shares=True, tick_rounding=True, sizing_basis="limit")
    CASES = [
        ("1  published (same-minute re-buy, fractional shares)",
         dict(wait_bars=0, flatten_at_open_of_next=False), {}),
        ("2  re-buy waits one minute",
         dict(wait_bars=1, flatten_at_open_of_next=False), {}),
        ("3  + whole shares, tick rounding, size off the limit",
         dict(wait_bars=1, flatten_at_open_of_next=False), live_cfg),
        ("4  + exit at 15:55 like the engine does  <-- AS EXECUTED",
         dict(wait_bars=1, flatten_at_open_of_next=True), live_cfg),
    ]

    w = 92
    print("=" * w)
    print("THE BACKTEST, RUN THE WAY THE ENGINE TRADES   "
          "(net bp per ON-day, 1-min fills, 2022+)")
    print("=" * w)
    print(f"{'case':<54}{'SOXL':>9}{'SOXS':>9}{'account':>10}{'t':>8}")

    keep = None
    for label, kw, cfgkw in CASES:
        nets, ons = {}, {}
        for s in SLEEVES:
            sessions, fine, dates = data[s]
            cfg = dataclasses.replace(backtest_config(s), **cfgkw)
            on, tr, net = run(s, sessions, fine, dates, cfg, **kw)
            nets[s], ons[s] = net, on
        cal = pd.DatetimeIndex(sorted(set(nets["SOXL"].index)
                                      | set(nets["SOXS"].index)))
        acct = sum(W * nets[s].reindex(cal).fillna(0.0) for s in SLEEVES)
        m, sd, sem, t = stats_line(acct)
        print(f"{label:<54}{nets['SOXL'].mean()*1e4:>+9.2f}"
              f"{nets['SOXS'].mean()*1e4:>+9.2f}{m:>+10.2f}{t:>8.2f}")
        keep = (nets, acct)

    nets, acct = keep
    print("\n" + "=" * w)
    print("CASE 4 IN FULL — is there an edge?")
    print("=" * w)
    for s in SLEEVES:
        x = nets[s]
        m, sd, sem, t = stats_line(x)
        print(f"  {s}: {m:+7.2f} bp/ON-day over {len(x)} ON-days   sd {sd:6.1f}   "
              f"sem {sem:5.2f}   t = {t:+.2f}   p = {norm_sf(abs(t))*2:.3f}")
        print(f"        95% CI [{m-1.96*sem:+.2f}, {m+1.96*sem:+.2f}] bp"
              f"{'   ZERO INSIDE' if m-1.96*sem <= 0 <= m+1.96*sem else ''}")
    m, sd, sem, t = stats_line(acct)
    n = len(acct)
    ann_days = n / ((acct.index[-1] - acct.index[0]).days / 365.25)
    eq = (1.0 + acct).cumprod()
    mdd = float((eq / eq.cummax() - 1.0).min())
    print(f"\n  ACCOUNT: {m:+.2f} bp per active day over {n} days")
    print(f"    95% CI [{m-1.96*sem:+.2f}, {m+1.96*sem:+.2f}] bp   t = {t:+.2f}   "
          f"p = {norm_sf(abs(t))*2:.3f}")
    print(f"    annualised return  {((1+m/1e4)**ann_days - 1)*100:+.1f}% "
          f"   Sharpe {m/sd*math.sqrt(ann_days):+.2f}")
    print(f"    total over the sample {(eq.iloc[-1]-1)*100:+.1f}%   "
          f"max drawdown {mdd:+.1%}")
    if m > 0:
        print(f"    days for the mean to clear zero at 95%: "
              f"{(1.96*sd/m)**2:,.0f} active days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
