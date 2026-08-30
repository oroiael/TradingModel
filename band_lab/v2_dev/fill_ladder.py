"""
Enforce a fill convention that cannot flatter itself, and see what is left.

The proposal: never let a fill take the good side of a minute. Buy at the
minute's open, or — worst case — its HIGH. Sell at the minute's low. Re-buy no
earlier than the next minute.

Most of that is right. One part of it cannot be done, and the reason matters:

  A resting BUY LIMIT at 100 in a market trading at 97.50 fills at **97.50**.
  It cannot fill at 100. Measured on this data, **64% of entry fills happen on
  a bar that opened BELOW the resting limit, by a median of 2.5%** — those are
  gaps down through a resting order, and taking the open there is not
  optimistic, it is the only thing that can happen. `min(limit, open)` is
  already the correct rule, and forcing "fill at your limit, never better"
  manufactures a purchase above the market that then instantly stops out. Row X
  below shows what that produces so the mistake is on the record rather than in
  a footnote: -305 bp/day, worse than the bound nobody could lose more than.

So pessimism is applied only where a fill really can be worse than the order:

  STOP    a SELL STOP is a market order once touched, and CAN fill below the
          stop price. The bar's LOW is the honest worst case. The current
          simulator uses min(open, stop), which is not it.  -> row D
  QUEUE   being at a price is not being filled at it. Requiring the bar to
          trade THROUGH the price rather than touch it is the conservative
          read of a resting limit.                          -> row E
  SLIP    a flat charge on every fill, on top of the commission and spread
          already in COST_BP_PER_FILL, for everything not modelled. -> row F

Rows A and G are BOUNDS on what could have happened inside a minute that
1-minute bars cannot see. Neither is producible by these order types. The gap
between them is how much this data simply cannot resolve.

    python3 band_lab/v2_dev/fill_ladder.py
    python3 band_lab/v2_dev/fill_ladder.py --live-cfg --slip 3
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from dataclasses import dataclass

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
for _p in (os.path.join(_BAND_LAB, "live"), os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest_as_executed import (COST_BP_PER_FILL, ROOT, SLEEVES, START, W,  # noqa: E402
                                  stats_line)
from intrabar import load_1min_sessions                            # noqa: E402
from replay import backtest_config, load_sessions                  # noqa: E402
from sleeve import SleeveStateMachine                              # noqa: E402
from strategy_core import FeatureHistory, session_stats            # noqa: E402


@dataclass(frozen=True)
class Rules:
    entry: str            # "marketable" | "limit_only" | "high" | "low"
    target: str           # "marketable" | "limit_only" | "high" | "low"
    stop: str             # "open" | "at_stop" | "low"
    same_bar_rebuy: bool
    through: bool         # a touch is not a fill; require trading through
    slip_bp: float = 0.0  # extra cost on every fill, both directions


def entry_fills(mode, bar, limit, through) -> bool:
    if mode in ("high", "low"):
        return bar.low <= limit
    if bar.open <= limit:
        return True                       # gapped through: marketable, fills
    return bar.low < limit if through else bar.low <= limit


def entry_px(mode, bar, limit, slip):
    if mode == "marketable":
        px = min(limit, bar.open)         # gap down -> you get the open
    elif mode == "limit_only":
        px = limit                        # IMPOSSIBLE on a gap; row X only
    elif mode == "high":
        px = bar.high                     # unproducible floor
    elif mode == "low":
        px = bar.low                      # unproducible ceiling
    else:
        raise ValueError(mode)
    return px * (1.0 + slip / 1e4)


def target_fills(mode, bar, target, through) -> bool:
    if mode in ("high", "low"):
        return bar.high >= target
    if bar.open >= target:
        return True
    return bar.high > target if through else bar.high >= target


def target_px(mode, bar, target, slip):
    if mode == "marketable":
        px = max(bar.open, target)
    elif mode == "limit_only":
        px = target
    elif mode == "high":
        px = bar.high
    elif mode == "low":
        px = bar.low
    else:
        raise ValueError(mode)
    return px * (1.0 - slip / 1e4)


def stop_px(mode, bar, stop, slip):
    if mode == "open":
        px = min(bar.open, stop)
    elif mode == "at_stop":
        px = stop                         # optimistic: the stop is honoured
    elif mode == "low":
        px = bar.low                      # a stop is a market order once hit
    else:
        raise ValueError(mode)
    return px * (1.0 - slip / 1e4)


def replay_session(decision_bars, fill_bars, sm, step, r: Rules,
                   flatten_at_open_of_next: bool):
    start, stop = sm.cfg.start_idx, sm.cfg.last_holding_idx
    by: dict[int, list] = {}
    for b in fill_bars:
        by.setdefault(b.idx // step, []).append(b)

    seq = entry_seq = 0
    exit_seq = -1
    for dbar in decision_bars:
        sm.on_bar_open(dbar.idx)
        if start <= dbar.idx <= stop:
            for fb in sorted(by.get(dbar.idx, [dbar]), key=lambda b: b.idx):
                seq += 1
                if sm.in_position:
                    br = sm.bracket
                    if fb.low <= br.stop_px:
                        sm.on_exit_fill(stop_px(r.stop, fb, br.stop_px,
                                                r.slip_bp), dbar.idx, "stop")
                        exit_seq = seq
                    elif seq > entry_seq and target_fills(r.target, fb,
                                                          br.target_px,
                                                          r.through):
                        sm.on_exit_fill(target_px(r.target, fb, br.target_px,
                                                  r.slip_bp), dbar.idx, "target")
                        exit_seq = seq

                e = sm.working_entry
                if e is None:
                    continue
                if (seq == exit_seq) and not r.same_bar_rebuy:
                    continue
                if not entry_fills(r.entry, fb, e.limit_px, r.through):
                    continue
                sm.on_entry_fill(entry_px(r.entry, fb, e.limit_px, r.slip_bp),
                                 dbar.idx)
                entry_seq = seq
                if fb.low <= sm.bracket.stop_px:
                    sm.on_exit_fill(stop_px(r.stop, fb, sm.bracket.stop_px,
                                            r.slip_bp), dbar.idx, "stop")
                    exit_seq = seq
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


def run(symbol, sessions, fine, dates, cfg, r, flatten):
    history = FeatureHistory()
    returns, n_fills = {}, {}
    for date, dbars in sessions:
        stats = session_stats(dbars)
        atr5, thr80 = history.atr5(), history.thr80()
        if date in dates:
            fbars = fine.get(date, dbars)
            step = 5 if date in fine else 1
            sm = SleeveStateMachine(cfg)
            g = sm.begin_session(date, atr5, stats.is_half_day, stats.late_open)
            if g.ok and sm.apply_morning_filter(stats.or30, thr80, stats.pos10).ok:
                replay_session(dbars, fbars, sm, step, r, flatten)
                returns[date] = sm.pnl
                n_fills[date] = len(sm.trades)
        history.append(stats)
    on = pd.Series(returns, dtype=float).sort_index()
    f = pd.Series(n_fills, dtype=float).reindex(on.index).fillna(0.0)
    return on - f * COST_BP_PER_FILL[symbol] / 1e4, f


def ladder(slip: float):
    return [
        ("A  CEILING: buy the bar's low, sell the bar's high",
         Rules("low", "high", "at_stop", True, False), True),
        ("B  published backtest (same-minute re-buy at the open)",
         Rules("marketable", "marketable", "open", True, False), False),
        ("C  no same-minute re-buy   <-- the V20 correction",
         Rules("marketable", "marketable", "open", False, False), False),
        ("D  + stop fills at the bar's LOW (stop = market once hit)",
         Rules("marketable", "marketable", "low", False, False), False),
        ("E  + must trade THROUGH the price, not just touch it",
         Rules("marketable", "marketable", "low", False, True), False),
        (f"F  + {slip:.0f} bp extra slippage on every fill",
         Rules("marketable", "marketable", "low", False, True, slip), True),
        ("G  FLOOR: buy the bar's high, sell the bar's low",
         Rules("high", "low", "low", False, False), True),
        ("X  force the fill AT the limit — IMPOSSIBLE on a gap, see docstring",
         Rules("limit_only", "limit_only", "low", False, False), False),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-cfg", action="store_true",
                    help="whole shares, tick rounding, size off the limit, "
                         "flatten at 15:55 — the engine's real constraints")
    ap.add_argument("--slip", type=float, default=2.0,
                    help="extra bp charged on every fill in row F")
    a = ap.parse_args()

    data = {}
    for s in SLEEVES:
        fine = dict(load_1min_sessions(s, ROOT))
        sessions = load_sessions(s, ROOT)
        dates = {d for d, _ in sessions} & set(fine)
        data[s] = (sessions, fine, {d for d in dates if d >= START})

    cfgkw = (dict(whole_shares=True, tick_rounding=True, sizing_basis="limit")
             if a.live_cfg else {})

    w = 102
    print("=" * w)
    print("FILL LADDER — how much of the result is the strategy and how much "
          "is the fill convention")
    print(f"   net bp per active day, after costs, 1-minute fills, 2022+"
          f"{'   [live constraints on]' if a.live_cfg else ''}")
    print("=" * w)
    rows = []
    for label, r, rule_off in ladder(a.slip):
        nets, fills = {}, {}
        for s in SLEEVES:
            sessions, fine, dates = data[s]
            cfg = dataclasses.replace(backtest_config(s), **cfgkw)
            nets[s], fills[s] = run(s, sessions, fine, dates, cfg, r,
                                    a.live_cfg)
        cal = pd.DatetimeIndex(sorted(set(nets["SOXL"].index)
                                      | set(nets["SOXS"].index)))
        acct = sum(W * nets[s].reindex(cal).fillna(0.0) for s in SLEEVES)
        m, sd, sem, t = stats_line(acct)
        rows.append((label, rule_off, nets["SOXL"].mean() * 1e4,
                     nets["SOXS"].mean() * 1e4, m, t,
                     sum(f.mean() for f in fills.values())))

    ceil_ = next(r[4] for r in rows if r[0].startswith("A"))
    floor_ = next(r[4] for r in rows if r[0].startswith("G"))

    print(f"{'convention':<60}{'SOXL':>9}{'SOXS':>9}{'account':>10}{'t':>7}"
          f"{'tr/d':>7}{'band':>7}")
    print("-" * w)
    for label, rule_off, sl, ss, m, t, tpd in rows:
        pos = (m - floor_) / (ceil_ - floor_) * 100
        print(f"{label:<60}{sl:>+9.2f}{ss:>+9.2f}{m:>+10.2f}{t:>7.2f}"
              f"{tpd:>7.2f}{pos:>6.0f}%")
        if rule_off:
            print("-" * w)

    print(f"\n  'band' = where the row sits between the floor ({floor_:+.0f} bp) "
          f"and the ceiling ({ceil_:+.0f} bp).")
    print(f"  A neutral convention should land near 50%. The published backtest "
          f"landed at "
          f"{(next(r[4] for r in rows if r[0].startswith('B')) - floor_)/(ceil_-floor_)*100:.0f}%.")
    print(f"  The band is {ceil_ - floor_:.0f} bp per day wide. That is how "
          f"much 1-minute bars cannot see.")

    print("""
  A and G bound what could have happened inside a minute. Neither is producible
  by these order types — a resting BUY LIMIT cannot fill above its limit and a
  SELL LIMIT cannot fill below its. They are the width of what 1-minute bars
  cannot see.

  C is the current baseline. D, E and F are the three places a fill can honestly
  be worse than the order price: a stop is a market order once touched, a touch
  is not a fill, and everything unmodelled costs something.

  X is in the table as a correction, not a result. It prices a resting buy at
  its own limit even when the bar opened 2.5% below it — a purchase above the
  market, which then instantly stops out. It is the version of "always assume
  the worst price" that is not conservative but simply wrong, and it lands below
  the floor, which is how you can tell.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
