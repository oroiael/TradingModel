"""
Show the backtest's work, minute by minute, and count the same-minute re-buys.

Two outputs, both meant to be read rather than summarised:

  --census   every trade in the sample, split by whether it was bought back in
             the same minute a sell happened. This is the whole argument in one
             table: how many such trades there are, what they earn, and what
             they contribute per trading day.

  --day      one session, one line per minute, showing the price the simulator
             saw and the decision it made. Nothing is aggregated.

    python3 band_lab/v2_dev/trace_day.py --census
    python3 band_lab/v2_dev/trace_day.py --day 2026-06-10 --symbol SOXS
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys

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
SLEEVES = ("SOXL", "SOXS")


def clock(idx: int) -> str:
    """Bar index -> wall clock. Bar 0 is 09:30; each bar is one minute."""
    m = 9 * 60 + 30 + idx
    return f"{m // 60:02d}:{m % 60:02d}"


def replay(decision_bars, fill_bars, sm, step, *, wait_bars, trace=None):
    """The `spec` loop, instrumented. `wait_bars=0` reproduces the published
    backtest exactly; `wait_bars=1` makes a re-buy wait one minute."""
    start, stop = sm.cfg.start_idx, sm.cfg.last_holding_idx
    by_decision: dict[int, list] = {}
    for b in fill_bars:
        by_decision.setdefault(b.idx // step, []).append(b)

    seq = entry_seq = 0
    entry_seq = -1
    blocked_until = -1
    exit_seq = -10          # fill-bar sequence of the most recent exit
    marks = []              # (was_same_minute_rebuy,) per entry, in order

    for dbar in decision_bars:
        sm.on_bar_open(dbar.idx)
        if start <= dbar.idx <= stop:
            inner = sorted(by_decision.get(dbar.idx, [dbar]), key=lambda b: b.idx)
            for fb in inner:
                seq += 1
                note, exited = [], False
                if sm.in_position:
                    br = sm.bracket
                    if fb.low <= br.stop_px:
                        px = min(fb.open, br.stop_px)
                        sm.on_exit_fill(px, dbar.idx, "stop")
                        note.append(f"SELL stop  @ {px:.4f}")
                        exited = True
                    elif seq > entry_seq and fb.high >= br.target_px:
                        px = max(fb.open, br.target_px)
                        sm.on_exit_fill(px, dbar.idx, "target")
                        note.append(f"SELL target@ {px:.4f}")
                        exited = True
                if exited:
                    exit_seq = seq
                    blocked_until = seq + wait_bars

                entry = sm.working_entry
                if entry is not None and fb.low <= entry.limit_px:
                    if seq < blocked_until:
                        note.append(f"(re-buy BLOCKED this minute; limit "
                                    f"{entry.limit_px:.4f}, low {fb.low:.4f})")
                    else:
                        px = min(entry.limit_px, fb.open)
                        same = (seq == exit_seq)
                        sm.on_entry_fill(px, dbar.idx)
                        marks.append(same)
                        entry_seq = seq
                        tag = "  <== SAME MINUTE as the sell" if same else ""
                        note.append(f"BUY       @ {px:.4f} "
                                    f"(limit {entry.limit_px:.4f}, "
                                    f"bar open {fb.open:.4f}){tag}")
                        if fb.low <= sm.bracket.stop_px:
                            sp = min(fb.open, sm.bracket.stop_px)
                            sm.on_exit_fill(sp, dbar.idx, "stop")
                            note.append(f"SELL stop  @ {sp:.4f} (same minute)")
                            exit_seq = seq
                            blocked_until = seq + wait_bars
                if trace is not None:
                    trace.append((fb, list(note), sm.state.name))
        sm.on_bar_close(dbar)

    if sm.in_position:
        tradable = [b for b in decision_bars if start <= b.idx <= stop]
        if tradable:
            sm.flatten(tradable[-1].close, tradable[-1].idx)
    return marks


def load(symbol):
    fine = dict(load_1min_sessions(symbol, ROOT))
    sessions = load_sessions(symbol, ROOT)
    dates = {d for d, _ in sessions} & set(fine)
    return sessions, fine, {d for d in dates if d >= START}


def each_session(symbol, wait_bars, only=None, trace=None):
    sessions, fine, dates = load(symbol)
    cfg = dataclasses.replace(backtest_config(symbol))
    history = FeatureHistory()
    out = []
    for date, dbars in sessions:
        stats = session_stats(dbars)
        atr5, thr80 = history.atr5(), history.thr80()
        if date in dates and (only is None or date == only):
            sm = SleeveStateMachine(cfg)
            g = sm.begin_session(date, atr5, stats.is_half_day, stats.late_open)
            if g.ok and sm.apply_morning_filter(stats.or30, thr80, stats.pos10).ok:
                marks = replay(dbars, fine.get(date, dbars), sm,
                               5 if date in fine else 1,
                               wait_bars=wait_bars, trace=trace)
                out.append((date, sm, marks))
            elif only is not None:
                reason = g.reason if not g.ok else "morning filter stood it down"
                print(f"  {date.date()} did not trade: {reason}")
        history.append(stats)
    return out


def census():
    print("=" * 88)
    print("EVERY TRADE IN THE SAMPLE, SPLIT BY WHETHER IT WAS A SAME-MINUTE RE-BUY")
    print("published backtest (wait_bars=0), 1-minute fills, 2022+, BEFORE costs")
    print("=" * 88)
    for symbol in SLEEVES:
        rows = each_session(symbol, wait_bars=0)
        n_days = len(rows)
        same, other = [], []
        for _d, sm, marks in rows:
            for t, is_same in zip(sm.trades, marks + [False] * len(sm.trades)):
                (same if is_same else other).append(t.ret)
        tot = sum(same) + sum(other)
        print(f"\n{symbol}:  {n_days} trading days, {len(same)+len(other)} trades")
        print(f"  {'group':<26}{'trades':>8}{'avg return':>12}"
              f"{'total':>12}{'per day':>12}{'share':>9}")
        for lbl, xs in (("bought in the SAME minute", same),
                        ("bought a later minute", other)):
            if not xs:
                continue
            print(f"  {lbl:<26}{len(xs):>8}{sum(xs)/len(xs)*100:>11.3f}%"
                  f"{sum(xs)*100:>11.1f}%{sum(xs)/n_days*1e4:>+11.1f}bp"
                  f"{sum(xs)/tot*100 if tot else float('nan'):>8.0f}%")
        print(f"  {'ALL':<26}{len(same)+len(other):>8}{'':>12}"
              f"{tot*100:>11.1f}%{tot/n_days*1e4:>+11.1f}bp")


def day(symbol, date_str):
    want = pd.Timestamp(date_str)
    trace = []
    rows = each_session(symbol, wait_bars=0, only=want, trace=trace)
    if not rows:
        print(f"  no traded session for {symbol} on {date_str}")
        return
    _d, sm, marks = rows[0]
    print("=" * 88)
    print(f"{symbol}  {date_str}  — every minute the simulator looked at, "
          f"published rules")
    print("=" * 88)
    print(f"{'time':>6} {'open':>9} {'high':>9} {'low':>9} {'close':>9}  what happened")
    for fb, note, state in trace:
        line = "; ".join(note)
        if not line and state == "IN_POSITION":
            line = "holding"
        print(f"{clock(fb.idx):>6} {fb.open:>9.4f} {fb.high:>9.4f} "
              f"{fb.low:>9.4f} {fb.close:>9.4f}  {line}")
    print("-" * 88)
    for i, t in enumerate(sm.trades, 1):
        print(f"  trade {i}: bought {t.entry_px:.4f}  sold {t.exit_px:.4f}  "
              f"{t.outcome:<8} return {t.ret*100:+.3f}%")
    print(f"  day total: {sm.pnl*100:+.3f}% of sleeve capital")


def main() -> int:
    ap = argparse.ArgumentParser(description="show the backtest's work")
    ap.add_argument("--census", action="store_true")
    ap.add_argument("--day")
    ap.add_argument("--symbol", default="SOXS", choices=SLEEVES)
    a = ap.parse_args()
    if a.day:
        day(a.symbol, a.day)
    else:
        census()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
