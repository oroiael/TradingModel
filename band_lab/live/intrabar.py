"""
Dual-granularity replay — 5-minute decisions, finer-grained fills.

PHASE2_PARITY.md S10 showed that most of the strategy's measured edge comes
from re-entries priced inside the bar that exited the previous position. That
is a property of the *simulator's* resolution, not of the strategy: live, a
resting limit fills whenever price reaches it, not at bar boundaries.

This module separates the two clocks:

* **decision bars** stay 5-minute. The anchor ratchet, the 11:00 activation
  and the counters are all defined on 5-minute bars (§2.5) and every
  validated result depends on that cadence. It is not changed here.
* **fill bars** may be finer (1-minute). Only the price a fill is assumed to
  occur at changes.

Feeding the same 5-minute bars as both streams reproduces `replay.py` exactly
— that degenerate case is asserted in `test_live_intrabar.py`, so this file
cannot silently become a different backtest.

Run (needs 1-minute CSVs — see fetch_1min.py):
    python3 band_lab/live/intrabar.py --symbol SOXL
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
ROOT = os.path.dirname(_BAND_LAB)
for _p in (_HERE, os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import FILL_MODELS, SPLIT_ADJUSTMENTS, backtest_config  # noqa: E402
from sleeve import SleeveConfig, SleeveStateMachine  # noqa: E402
from strategy_core import Bar, FeatureHistory, session_stats  # noqa: E402

#: When may the +1% target fill after an entry? §2.6's anti-lookahead rule is
#: written for a bar-granularity simulator: "the target may fill from the next
#: bar onward". Which bar it means depends on the fill resolution.
TARGET_DELAY = (
    "decision_bar",   # not until the next 5-minute bar (the validated reading)
    "fill_bar",       # not until the next fill bar (1 minute, if 1-min data)
)


# --------------------------------------------------------------------- data
def load_1min_sessions(symbol: str, root: str = ROOT,
                       path: Optional[str] = None) -> list[tuple[pd.Timestamp, list[Bar]]]:
    """1-minute RTH bars, split-adjusted, grouped by session.

    `Bar.idx` is minutes since 09:30, so the 5-minute decision bar containing
    fill bar `j` is `j // 5`.
    """
    path = path or os.path.join(root, f"{symbol}_1min.csv")
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].astype(str).str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    df = df.assign(dt=dt, date=dt.dt.normalize()).sort_values("dt")
    for cut, ratio in SPLIT_ADJUSTMENTS.get(symbol, []):
        pre = df["date"] < cut
        for col in ("Open", "High", "Low", "Close"):
            df.loc[pre, col] = df.loc[pre, col] / ratio

    out = []
    open_offset = pd.Timedelta("09:30:00")
    for date, gb in df.groupby("date", sort=True):
        idx = ((gb["dt"] - (date + open_offset)).dt.total_seconds() / 60.0
               ).round().astype(int).to_numpy()
        bars = [Bar(int(i), float(o), float(h), float(l), float(c), float(v))
                for i, o, h, l, c, v in zip(
                    idx, gb["Open"], gb["High"], gb["Low"], gb["Close"], gb["Volume"])]
        out.append((date, bars))
    return out


def aggregate(fill_bars: Sequence[Bar], per_decision_bar: int) -> list[Bar]:
    """Build decision bars from fill bars. `per_decision_bar` = 5 for 1-minute."""
    buckets: dict[int, list[Bar]] = {}
    for b in fill_bars:
        buckets.setdefault(b.idx // per_decision_bar, []).append(b)
    out = []
    for i in sorted(buckets):
        grp = sorted(buckets[i], key=lambda b: b.idx)
        out.append(Bar(i, grp[0].open, max(b.high for b in grp),
                       min(b.low for b in grp), grp[-1].close,
                       sum(b.volume for b in grp)))
    return out


# ------------------------------------------------------------------ replay
def replay_session_intrabar(decision_bars: list[Bar], fill_bars: list[Bar],
                            sm: SleeveStateMachine, per_decision_bar: int,
                            fill_model: str = "spec",
                            target_delay: str = "decision_bar") -> None:
    """One session. Decisions on `decision_bars`, fills resolved on `fill_bars`.

    The state machine only ever sees decision bars, so the strategy's clock is
    untouched. `fill_model` and `target_delay` describe the simulator, not the
    strategy.
    """
    if fill_model not in FILL_MODELS:
        raise ValueError(f"bad fill_model={fill_model!r}")
    if target_delay not in TARGET_DELAY:
        raise ValueError(f"bad target_delay={target_delay!r}")

    start, stop = sm.cfg.start_idx, sm.cfg.last_holding_idx
    by_decision: dict[int, list[Bar]] = {}
    for b in fill_bars:
        by_decision.setdefault(b.idx // per_decision_bar, []).append(b)
    tradable = [b for b in decision_bars if start <= b.idx <= stop]

    entry_seq = -1          # fill-bar sequence of the current entry
    seq = 0

    for dbar in decision_bars:
        sm.on_bar_open(dbar.idx)

        if start <= dbar.idx <= stop:
            inner = sorted(by_decision.get(dbar.idx, [dbar]), key=lambda b: b.idx)
            for fb in inner:
                seq += 1
                exit_px = None
                if sm.in_position:
                    br = sm.bracket
                    target_ready = (seq > entry_seq if target_delay == "fill_bar"
                                    else dbar.idx > sm.entry_bar)
                    if fb.low <= br.stop_px:
                        exit_px = min(fb.open, br.stop_px)
                        sm.on_exit_fill(exit_px, dbar.idx, "stop")
                    elif target_ready and fb.high >= br.target_px:
                        exit_px = max(fb.open, br.target_px)
                        sm.on_exit_fill(exit_px, dbar.idx, "target")

                entry = sm.working_entry
                if (entry is not None and fb.low <= entry.limit_px
                        and not (fill_model == "next_bar" and exit_px is not None)):
                    px = min(entry.limit_px, fb.open)
                    if fill_model == "no_better" and exit_px is not None:
                        px = min(entry.limit_px, max(fb.open, exit_px))
                    sm.on_entry_fill(px, dbar.idx)
                    entry_seq = seq
                    if fb.low <= sm.bracket.stop_px:
                        sm.on_exit_fill(sm.bracket.stop_px, dbar.idx, "stop")

        sm.on_bar_close(dbar)

    if sm.in_position and tradable:
        sm.flatten(tradable[-1].close, tradable[-1].idx)


def replay_symbol_intrabar(symbol: str, sessions: list, per_decision_bar: int,
                           cfg: Optional[SleeveConfig] = None,
                           fill_model: str = "spec",
                           target_delay: str = "decision_bar",
                           fine_by_date: Optional[dict] = None,
                           trade_dates: Optional[set] = None):
    """Replay `sessions`, a list of (date, decision_bars) in date order.

    `sessions` must be the **full** 5-minute record, not just the window the
    1-minute file covers: ATR5 needs 5 prior sessions and thr80 needs 120, so
    a truncated history stands every early day down and silently deletes it
    from the sample. Decisions therefore always come from the same 5-minute
    series every validated result was produced from.

    `fine_by_date` supplies the finer fill stream per date; dates without one
    resolve fills on their own decision bars. `trade_dates` restricts which
    sessions actually trade, so a 1-minute run and a 5-minute run can be
    compared over exactly the same days.
    """
    cfg = cfg or backtest_config(symbol)
    fine_by_date = fine_by_date or {}
    history = FeatureHistory()
    trade_rows, returns = [], {}

    for date, dbars in sessions:
        stats = session_stats(dbars)
        atr5, thr80 = history.atr5(), history.thr80()

        if trade_dates is None or date in trade_dates:
            fbars = fine_by_date.get(date, dbars)
            step = per_decision_bar if date in fine_by_date else 1
            sm = SleeveStateMachine(cfg)
            gate = sm.begin_session(date, atr5, stats.is_half_day, stats.late_open)
            if gate.ok:
                filt = sm.apply_morning_filter(stats.or30, thr80, stats.pos10)
                if filt.ok:
                    replay_session_intrabar(dbars, fbars, sm, step,
                                            fill_model, target_delay)
                    returns[date] = sm.pnl
                    for t in sm.trades:
                        trade_rows.append({
                            "date": date, "entry_bar": t.entry_bar,
                            "exit_bar": t.exit_bar, "entry_px": t.entry_px,
                            "exit_px": t.exit_px, "limit_px": t.limit_px,
                            "qty": t.qty, "ret": t.ret, "outcome": t.outcome})
        history.append(stats)

    on = pd.Series(returns, dtype=float).sort_index()
    on.index.name = "date"
    return on, pd.DataFrame(trade_rows)


# --------------------------------------------------------------- reporting
def resolution_report(symbol: str, root: str = ROOT,
                      path: Optional[str] = None) -> None:
    """The S10 question, re-asked at 1-minute fill resolution.

    Restricted to the dates the 1-minute file covers, and the 5-minute rows are
    recomputed on that same date range so the comparison is like for like.
    """
    from replay import load_sessions, replay_symbol

    fine = dict(load_1min_sessions(symbol, root, path))
    every = load_sessions(symbol, root)          # the full 5-minute record
    dates = set(fine) & {d for d, _ in every}
    print("=" * 78)
    print(f"{symbol} — fill resolution: {len(fine)} 1-minute sessions, "
          f"{len(dates)} usable, {min(dates).date()} → {max(dates).date()}")
    print("Features (ATR5, thr80) come from the full 5-minute history; only the")
    print("price a fill is assumed to occur at differs between rows.")
    print("=" * 78)

    print(f"{'fill bars':<12}{'target delay':<15}{'fill model':<12}"
          f"{'bp/ON-day':>11}{'Sharpe':>9}{'ON days':>9}{'trades':>8}")
    rows = []
    for model in FILL_MODELS:
        on, tr = replay_symbol_intrabar(symbol, every, 1, fill_model=model,
                                        trade_dates=dates)
        rows.append(("5-minute", "decision_bar", model, on, tr))
    for delay in TARGET_DELAY:
        for model in FILL_MODELS:
            on, tr = replay_symbol_intrabar(symbol, every, 5, fill_model=model,
                                            target_delay=delay,
                                            fine_by_date=fine, trade_dates=dates)
            rows.append(("1-minute", delay, model, on, tr))

    for bars, delay, model, on, tr in rows:
        sharpe = on.mean() / on.std() * np.sqrt(252) if len(on) > 1 and on.std() else float("nan")
        print(f"{bars:<12}{delay:<15}{model:<12}{on.mean() * 1e4:>11.1f}"
              f"{sharpe:>9.2f}{len(on):>9}{len(tr):>8}")

    # how much same-bar exposure survives the finer resolution
    print("\nsame-bar re-entries (entry in the bar that just exited):")
    for bars, delay, model, on, tr in rows:
        if model != "spec":
            continue
        if not len(tr):
            continue
        s = tr.sort_values(["date", "entry_bar"])
        prev_exit = s.groupby("date")["exit_bar"].shift(1)
        n = int((s["entry_bar"] == prev_exit).sum())
        print(f"  {bars}, {delay}: {n} of {len(tr)} entries ({n / len(tr):.1%})")
    print()


def parity_check(symbol: str, root: str = ROOT, path: Optional[str] = None) -> int:
    """Data-quality gate: 1-minute bars aggregated to 5 minutes must match the
    5-minute file the validated results were produced from."""
    from replay import load_sessions

    fine = dict(load_1min_sessions(symbol, root, path))
    coarse = dict(load_sessions(symbol, root))
    shared = sorted(set(fine) & set(coarse))
    print(f"{symbol}: {len(fine)} 1-min sessions, {len(shared)} overlap the 5-min file")
    if not shared:
        print("  no overlap — cannot validate the fetch")
        return 1

    worst_px, worst_date, missing = 0.0, None, 0
    for d in shared:
        agg = {b.idx: b for b in aggregate(fine[d], 5)}
        for cb in coarse[d]:
            ab = agg.get(cb.idx)
            if ab is None:
                missing += 1
                continue
            for a, c in ((ab.open, cb.open), (ab.high, cb.high),
                         (ab.low, cb.low), (ab.close, cb.close)):
                if abs(a - c) > worst_px:
                    worst_px, worst_date = abs(a - c), d
    print(f"  worst OHLC difference vs the 5-min file: {worst_px:.4f}"
          f"{'' if worst_date is None else f' on {worst_date.date()}'}")
    print(f"  5-minute bars with no 1-minute coverage: {missing}")
    ok = worst_px < 0.011 and missing == 0
    print("  " + ("PASS" if ok else "FAIL — investigate before trusting the run"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="1-minute fill-resolution study")
    ap.add_argument("--symbol", default="SOXL")
    ap.add_argument("--path", default=None, help="1-minute CSV (default <SYM>_1min.csv)")
    ap.add_argument("--check", action="store_true",
                    help="only run the aggregation parity check against the 5-min file")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()

    rc = parity_check(args.symbol, args.root, args.path)
    if args.check:
        return rc
    print()
    resolution_report(args.symbol, args.root, args.path)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
