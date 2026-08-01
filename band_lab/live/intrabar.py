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
                       path: Optional[str] = None,
                       split_adjust: bool = False) -> list[tuple[pd.Timestamp, list[Bar]]]:
    """1-minute RTH bars grouped by session.

    `Bar.idx` is minutes since 09:30, so the 5-minute decision bar containing
    fill bar `j` is `j // 5`.

    **`split_adjust` defaults to False, unlike the 5-minute loader.** The
    repository's 5-minute CSVs hold SOXL's *unadjusted* pre-2021-03-02 prices
    and are divided by 15 at read time; data fetched fresh from IBKR comes
    back already adjusted, so adjusting it again puts the fill stream at 1/15
    the scale of the decision stream. Pass True only for a vendor file that is
    genuinely unadjusted — `parity_check` diagnoses which you have.
    """
    path = path or os.path.join(root, f"{symbol}_1min.csv")
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].astype(str).str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    df = df.assign(dt=dt, date=dt.dt.normalize()).sort_values("dt")
    if split_adjust:
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
                      path: Optional[str] = None,
                      split_adjust: bool = False) -> None:
    """The S10 question, re-asked at 1-minute fill resolution.

    Restricted to the dates the 1-minute file covers, and the 5-minute rows are
    recomputed on that same date range so the comparison is like for like.
    """
    from replay import load_sessions, replay_symbol

    fine = dict(load_1min_sessions(symbol, root, path, split_adjust))
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


def _scale_diagnosis(symbol: str, fine: dict, coarse: dict,
                     shared: Sequence[pd.Timestamp]) -> None:
    """Report the fill/decision price ratio either side of each split date."""
    cuts = [c for c, _ in SPLIT_ADJUSTMENTS.get(symbol, [])]
    if not cuts:
        return
    cut = cuts[0]
    for label, dates in (("before", [d for d in shared if d < cut]),
                         ("after", [d for d in shared if d >= cut])):
        if not dates:
            continue
        ratios = [float(np.median([b.close for b in fine[d]]))
                  / float(np.median([b.close for b in coarse[d]])) for d in dates]
        r = float(np.median(ratios))
        verdict = "ok" if abs(r - 1.0) <= 0.05 else "MISMATCH"
        print(f"  price scale {label} {cut.date()}: 1-min / 5-min = {r:.4f}  [{verdict}]")
        if verdict == "MISMATCH":
            if abs(r - 1.0 / 15.0) < 0.02:
                print("     -> the 1-minute data was adjusted twice; it is already "
                      "split-adjusted. Drop --split-adjust.")
            elif abs(r - 15.0) < 1.0:
                print("     -> the 1-minute data is NOT split-adjusted. "
                      "Re-run with --split-adjust.")


def parity_check(symbol: str, root: str = ROOT, path: Optional[str] = None,
                 split_adjust: bool = False) -> int:
    """Data-quality gate: 1-minute bars aggregated to 5 minutes must match the
    5-minute file the validated results were produced from."""
    from replay import load_sessions

    fine = dict(load_1min_sessions(symbol, root, path, split_adjust))
    coarse = dict(load_sessions(symbol, root))
    shared = sorted(set(fine) & set(coarse))
    print(f"{symbol}: {len(fine)} 1-min sessions, {len(shared)} overlap the 5-min file")
    extra = sorted(set(fine) - set(shared))
    if extra:
        counts = sorted(len(fine[d]) for d in extra)
        # a full RTH session is 390 one-minute bars; a half-day is 210
        stubs = [d for d in extra if len(fine[d]) < 100]
        print(f"  {len(extra)} 1-minute sessions are absent from the 5-minute "
              "file and are excluded from the study")
        print(f"     bars per session: min {counts[0]}, "
              f"median {counts[len(counts) // 2]}, max {counts[-1]}  "
              f"(full RTH = 390, half-day = 210)")
        if stubs:
            print(f"     {len(stubs)} of them have <100 bars — likely partial "
                  "fetches rather than real sessions, e.g. "
                  + ", ".join(str(d.date()) for d in stubs[:4])
                  + ("..." if len(stubs) > 4 else ""))
    if not shared:
        print("  no overlap — cannot validate the fetch")
        return 1

    _scale_diagnosis(symbol, fine, coarse, shared)

    worst_px, worst_date, missing = 0.0, None, 0
    worst_by_era = {"pre": 0.0, "post": 0.0}
    cuts = [c for c, _ in SPLIT_ADJUSTMENTS.get(symbol, [])]
    cut = cuts[0] if cuts else pd.Timestamp.min
    for d in shared:
        agg = {b.idx: b for b in aggregate(fine[d], 5)}
        era = "pre" if d < cut else "post"
        for cb in coarse[d]:
            ab = agg.get(cb.idx)
            if ab is None:
                missing += 1
                continue
            for a, c in ((ab.open, cb.open), (ab.high, cb.high),
                         (ab.low, cb.low), (ab.close, cb.close)):
                diff = abs(a - c)
                worst_by_era[era] = max(worst_by_era[era], diff)
                if diff > worst_px:
                    worst_px, worst_date = diff, d
    print(f"  worst OHLC difference vs the 5-min file: {worst_px:.4f}"
          f"{'' if worst_date is None else f' on {worst_date.date()}'}")
    if cuts:
        print(f"    pre-split {worst_by_era['pre']:.4f} | "
              f"post-split {worst_by_era['post']:.4f}")
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
    ap.add_argument("--split-adjust", action="store_true",
                    help="apply the repo's split table to the 1-minute file; "
                         "needed only for genuinely unadjusted vendor data "
                         "(IBKR's is already adjusted)")
    ap.add_argument("--force", action="store_true",
                    help="run the study even if the data-quality check fails")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()

    rc = parity_check(args.symbol, args.root, args.path, args.split_adjust)
    if args.check:
        return rc
    if rc and not args.force:
        print("\nrefusing to run the study on data that failed the check "
              "(--force to override)")
        return rc
    print()
    resolution_report(args.symbol, args.root, args.path, args.split_adjust)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
