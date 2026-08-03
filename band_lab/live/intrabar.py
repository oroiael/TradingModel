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
def needs_split_adjustment(df: pd.DataFrame, symbol: str) -> bool:
    """Is this 1-minute file quoted on the raw (pre-split) price grid?

    `fetch_1min.py` assumes IBKR returns unadjusted bars, exactly like the
    repository's 5-minute CSVs, and leaves the split to read time. That is an
    assumption about the vendor, not a property of the file — a source that
    delivers an already-adjusted series would be divided by 15 a second time
    and silently misprice every pre-split session by 15x. Since the study only
    needs `Date,Open,High,Low,Close,Volume` from *any* vendor
    (PHASE2_PARITY.md), the convention has to be detected rather than assumed.

    The test is the ratio of the median pre-split close to the median
    post-split close. On the raw grid SOXL trades near $700 before 2021-03-02
    and near $40 after; already-adjusted, both sides sit in the same range.
    """
    splits = SPLIT_ADJUSTMENTS.get(symbol, [])
    if not splits:
        return False
    cut, ratio = splits[0]
    pre, post = df["date"] < cut, df["date"] >= cut
    if not pre.any() or not post.any():
        # Nothing to compare against; fall back to the documented convention.
        return True
    level = float(df.loc[pre, "Close"].median() / df.loc[post, "Close"].median())
    # Raw pre-split data sits ~`ratio` times higher; adjusted data sits ~1x.
    # Geometric midpoint splits the two cases with a wide margin either side.
    return bool(level > ratio ** 0.5)


def load_1min_sessions(symbol: str, root: str = ROOT,
                       path: Optional[str] = None,
                       split_adjust: bool = False) -> list[tuple[pd.Timestamp, list[Bar]]]:
    """1-minute RTH bars grouped by session.

    `Bar.idx` is minutes since 09:30, so the 5-minute decision bar containing
    fill bar `j` is `j // 5`.

    Files already quoted on the adjusted grid are left alone — see
    `needs_split_adjustment`.
    """
    path = path or os.path.join(root, f"{symbol}_1min.csv")
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].astype(str).str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    df = df.assign(dt=dt, date=dt.dt.normalize()).sort_values("dt")
    if needs_split_adjustment(df, symbol):
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
class PriceScaleError(ValueError):
    """The fill stream and the decision stream are not on the same price scale.

    Almost always a split-adjustment mismatch. It must be fatal rather than a
    warning: mixing scales silently produces a *plausible-looking* table —
    entries fill at the low scale while the 15:55 flatten books at the high
    one, which reads as an enormous edge instead of as an error.
    """


def _assert_same_price_scale(decision_bars: Sequence[Bar],
                             fill_bars: Sequence[Bar], tol: float = 0.05) -> None:
    if not decision_bars or not fill_bars:
        return
    d = float(np.median([b.close for b in decision_bars]))
    f = float(np.median([b.close for b in fill_bars]))
    if d <= 0 or f <= 0 or abs(f / d - 1.0) > tol:
        ratio = f / d if d else float("inf")
        raise PriceScaleError(
            f"fill bars are {ratio:.4g}x the decision bars "
            f"(median close {f:.4f} vs {d:.4f}). If this is ~1/15 or ~15 on "
            "SOXL, it is the 2021-03-02 split: the repository's 5-minute CSV "
            "is unadjusted and IBKR's fetched data is adjusted. See "
            "load_1min_sessions(split_adjust=...) and run "
            "`intrabar.py --check`.")


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

    _assert_same_price_scale(decision_bars, fill_bars)

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
                           trade_dates: Optional[set] = None,
                           atr_lookback: Optional[int] = None):
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
        atr5 = (history.atr5() if atr_lookback is None
                else history.atr5(atr_lookback))
        thr80 = history.thr80()

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
                      path: Optional[str] = None,
                      start: Optional[pd.Timestamp] = None) -> None:
    """The S10 question, re-asked at 1-minute fill resolution.

    Restricted to the dates the 1-minute file covers, and the 5-minute rows are
    recomputed on that same date range so the comparison is like for like.

    `start` narrows the traded window only. Features still come from the full
    5-minute record, so narrowing it does not truncate ATR5 or thr80.
    """
    from replay import load_sessions, replay_symbol

    fine = dict(load_1min_sessions(symbol, root, path))
    every = load_sessions(symbol, root)          # the full 5-minute record
    dates = set(fine) & {d for d, _ in every}
    if start is not None:
        dates = {d for d in dates if d >= start}
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


#: Gate tolerance, in basis points of price.
#:
#: This was originally "under a cent", which is well defined only for a series
#: quoted on a real $0.01 tick grid. SOXS's 5-minute file is back-adjusted and
#: opens at $1.07M/share (the S7 series): there, a cent is 2 parts per billion,
#: and no correct file could ever pass. The units of a back-adjusted series are
#: an artifact of its reverse-split history, so the comparison has to be
#: relative — as the strategy itself is, since §2 is written in percentages.
#:
#: 1 bp is *tighter* than the old rule everywhere SOXL actually trades (1 bp of
#: $47 is 0.5c, of $150 is 1.5c), so this does not weaken the SOXL gate; it
#: makes the SOXS gate expressible at all.
PARITY_TOL_BP = 1.0


def parity_check(symbol: str, root: str = ROOT, path: Optional[str] = None,
                 start: Optional[pd.Timestamp] = None,
                 tol_bp: float = PARITY_TOL_BP) -> int:
    """Data-quality gate: 1-minute bars aggregated to 5 minutes must match the
    5-minute file the validated results were produced from.

    Tolerance is relative (`PARITY_TOL_BP`), not a fixed cent — see that
    constant. The per-session counts are reported alongside the worst case
    because the two failure modes need different responses: a series on the
    wrong basis fails on nearly every session, while a handful of disputed
    prints fails on a few. Only the first invalidates the study.
    """
    from replay import load_sessions

    fine = dict(load_1min_sessions(symbol, root, path))
    coarse = dict(load_sessions(symbol, root))
    shared = sorted(set(fine) & set(coarse))
    if start is not None:
        shared = [d for d in shared if d >= start]
    print(f"{symbol}: {len(fine)} 1-min sessions, {len(shared)} overlap the 5-min file"
          + (f" from {start.date()}" if start is not None else ""))
    if not shared:
        print("  no overlap — cannot validate the fetch")
        return 1

    # A split-adjustment mismatch damages exactly one side of the split date,
    # so the eras are reported separately: a large `pre` beside a clean `post`
    # is a scale error, while both sides alike is ordinary vendor disagreement.
    cuts = SPLIT_ADJUSTMENTS.get(symbol, [])
    cut = cuts[0][0] if cuts else None
    worst_by_era = {"pre": 0.0, "post": 0.0}

    worst_px, worst_bp, worst_date, missing = 0.0, 0.0, None, 0
    bad_sessions, bad_bars, total_bars = set(), 0, 0
    for d in shared:
        agg = {b.idx: b for b in aggregate(fine[d], 5)}
        era = "pre" if cut is not None and d < cut else "post"
        for cb in coarse[d]:
            ab = agg.get(cb.idx)
            if ab is None:
                missing += 1
                continue
            total_bars += 1
            diff = max(abs(ab.open - cb.open), abs(ab.high - cb.high),
                       abs(ab.low - cb.low), abs(ab.close - cb.close))
            ref = max(abs(cb.open), abs(cb.high), abs(cb.low), abs(cb.close))
            rel = diff / ref * 1e4 if ref else 0.0
            if rel > tol_bp:
                bad_sessions.add(d)
                bad_bars += 1
            worst_px = max(worst_px, diff)
            worst_by_era[era] = max(worst_by_era[era], rel)
            if rel > worst_bp:
                worst_bp, worst_date = rel, d
    print(f"  sessions {shared[0].date()} → {shared[-1].date()}")
    print(f"  worst OHLC difference vs the 5-min file: {worst_bp:.3f} bp"
          f" (absolute {worst_px:.4f})"
          f"{'' if worst_date is None else f' on {worst_date.date()}'}")
    if cuts:
        print(f"    pre-split {worst_by_era['pre']:.4f} bp | "
              f"post-split {worst_by_era['post']:.4f} bp")
    print(f"  5-minute bars with no 1-minute coverage: {missing}")
    print(f"  bars over {tol_bp:g} bp: {bad_bars} of {total_bars} "
          f"({bad_bars / max(total_bars, 1):.4%}) "
          f"across {len(bad_sessions)} of {len(shared)} sessions")
    if bad_sessions and len(bad_sessions) <= 10:
        print("    " + ", ".join(str(d.date()) for d in sorted(bad_sessions)))
    ok = worst_bp <= tol_bp and missing == 0
    print("  " + ("PASS" if ok else "FAIL — investigate before trusting the run"))
    return 0 if ok else 1


def worst_bars(symbol: str, root: str = ROOT, path: Optional[str] = None,
               split_adjust: bool = False, n: int = 15) -> None:
    """Dump the worst-disagreeing bars side by side.

    Whether the 5-minute file is *wider* or *narrower* than the aggregated
    1-minute bars is the diagnostic: systematically wider means the 1-minute
    fetch is missing extreme prints (a filtering difference), narrower means
    the 5-minute file carries prints the 1-minute tape does not.
    """
    from replay import load_sessions

    fine = dict(load_1min_sessions(symbol, root, path, split_adjust))
    coarse = dict(load_sessions(symbol, root))
    rows = []
    for d in sorted(set(fine) & set(coarse)):
        agg = {b.idx: b for b in aggregate(fine[d], 5)}
        for cb in coarse[d]:
            ab = agg.get(cb.idx)
            if ab is None:
                continue
            for field in ("open", "high", "low", "close"):
                a, c = getattr(ab, field), getattr(cb, field)
                if c:
                    rows.append((abs(a - c) / abs(c) * 1e4, d, cb.idx, field, a, c))
    rows.sort(reverse=True)

    print(f"\n{symbol} — {n} worst-disagreeing bars (1-min aggregate vs 5-min file)")
    print(f"{'date':<12}{'bar':>5}{'field':>7}{'1-min agg':>12}{'5-min':>12}"
          f"{'diff bp':>10}")
    for bp, d, idx, field, a, c in rows[:n]:
        print(f"{str(d.date()):<12}{idx:>5}{field:>7}{a:>12.4f}{c:>12.4f}{bp:>10.1f}")

    wider = sum(1 for bp, _, _, f, a, c in rows[:200]
                if (f == "high" and c > a) or (f == "low" and c < a))
    narrower = sum(1 for bp, _, _, f, a, c in rows[:200]
                   if (f == "high" and c < a) or (f == "low" and c > a))
    print(f"\nof the 200 worst: 5-min range wider {wider}, narrower {narrower}")
    print("  wider  -> the 1-minute fetch is missing extreme prints")
    print("  narrower -> the 5-minute file carries prints the 1-minute tape lacks")


def main() -> int:
    ap = argparse.ArgumentParser(description="1-minute fill-resolution study")
    ap.add_argument("--symbol", default="SOXL")
    ap.add_argument("--path", default=None, help="1-minute CSV (default <SYM>_1min.csv)")
    ap.add_argument("--check", action="store_true",
                    help="only run the aggregation parity check against the 5-min file")
    ap.add_argument("--start", default=None,
                    help="earliest session to trade/validate, YYYY-MM-DD "
                         "(features always use the full 5-minute history)")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--force", action="store_true",
                    help="run the study even if the parity check fails")
    args = ap.parse_args()

    start = pd.Timestamp(args.start) if args.start else None
    rc = parity_check(args.symbol, args.root, args.path, start)
    if args.check:
        return rc
    if rc and not args.force:
        print("\nrefusing to run the study on data that failed the check "
              "(--force to override)")
        return rc
    print()
    resolution_report(args.symbol, args.root, args.path, start)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
