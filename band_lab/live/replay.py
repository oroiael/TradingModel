"""
Stage 1 — offline driver: historical bars -> the LIVE state machine.

This is the anti-drift harness. `sleeve.SleeveStateMachine` is the code that
will run against IBKR; here it is driven by historical 5-minute bars with a
market simulator standing in for the broker, and the resulting daily P&L
series is compared against `phase1/spec_engine.py` (`test_live_equivalence`).

If they match, a live shortfall can be attributed to fills rather than to a
coding error — which is the whole reason Phase 2 exists. If they diverge,
this file fails before a single order is ever sent.

The simulator's fill rules are the backtest's, and they live *here*, not in
the state machine: within a bar the stop is checked before the target, the
target may not fill on the entry bar (§2.6 anti-lookahead), and a gap through
a level fills at the bar open.

Run:
    python3 band_lab/live/replay.py            # equivalence report, exit 0 == green
    python3 band_lab/live/replay.py --sizing   # S9: cost of §2.4 limit-price sizing
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, replace
from typing import Iterator, Optional

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
ROOT = os.path.dirname(_BAND_LAB)
for _p in (_HERE, os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sleeve import (  # noqa: E402
    LAST_HOLDING_IDX,
    START_IDX,
    SleeveConfig,
    SleeveStateMachine,
)
from strategy_core import Bar, FeatureHistory, SessionStats, session_stats  # noqa: E402

# §4: SOXL's 15:1 split (2021-03-02) is not applied in the raw repo file, and
# §2.1's percentage measures require a consistently adjusted series. This is
# data conditioning, not strategy — the live engine gets adjusted bars from
# IBKR instead. Same table as spec_engine.SPLIT_ADJUSTMENTS.
SPLIT_ADJUSTMENTS = {"SOXL": [(pd.Timestamp("2021-03-02"), 15.0)]}

BACKTEST_SLEEVE_CAPITAL = 150_000.0


def backtest_config(symbol: str, **kw) -> SleeveConfig:
    """The sleeve configured to match `spec_engine.SPEC_LITERAL`.

    Tick rounding and whole shares are the two things the backtest does not
    model (Phase 1 S5/S7) and the live engine cannot avoid; `sizing_basis`
    is S9 (see PHASE2_PARITY.md). Everything else is identical.
    """
    return SleeveConfig(symbol=symbol, sleeve_capital=BACKTEST_SLEEVE_CAPITAL,
                        tick_rounding=False, whole_shares=False,
                        sizing_basis="fill", **kw)


# ------------------------------------------------------------------- data
def load_sessions(symbol: str, root: str = ROOT) -> list[tuple[pd.Timestamp, list[Bar]]]:
    """5-minute RTH bars, split-adjusted, grouped by session, clock-indexed."""
    path = os.path.join(root, f"{symbol}_5min_6Years.csv")
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    df = df.assign(dt=dt, date=dt.dt.normalize()).sort_values("dt")
    for cut, ratio in SPLIT_ADJUSTMENTS.get(symbol, []):
        pre = df["date"] < cut
        for col in ("Open", "High", "Low", "Close"):
            df.loc[pre, col] = df.loc[pre, col] / ratio

    out: list[tuple[pd.Timestamp, list[Bar]]] = []
    open_offset = pd.Timedelta("09:30:00")
    for date, gb in df.groupby("date", sort=True):
        # §2.1: bars are addressed by clock time, not by position in the file.
        idx = ((gb["dt"] - (date + open_offset)).dt.total_seconds() / 300.0
               ).round().astype(int).to_numpy()
        bars = [Bar(int(i), float(o), float(h), float(l), float(c), float(v))
                for i, o, h, l, c, v in zip(
                    idx, gb["Open"], gb["High"], gb["Low"], gb["Close"], gb["Volume"])]
        out.append((date, bars))
    return out


# ------------------------------------------------------- market simulator
#: How a same-bar re-entry is priced. See PHASE2_PARITY.md S10 — this is a
#: *fill-model* switch, not a strategy switch: the rules of §2 are identical
#: under all three, only the price a bar-granularity simulator is willing to
#: assume differs.
FILL_MODELS = (
    "spec",        # the validated engine: re-entry at min(limit, bar open)
    "no_better",   # a same-bar re-entry may not be priced below the exit it followed
    "next_bar",    # no same-bar re-entry at all
)


def replay_session(bars: list[Bar], sm: SleeveStateMachine,
                   fill_model: str = "spec") -> None:
    """Drive one session's bars through the state machine.

    Per-bar ordering, in the order a live engine would observe it:
      0. the bar opens   -> the 11:00 activation may fire
      1. the bar trades  -> resolve any open position against the OCA bracket,
                            stop first (worst-case intrabar ordering)
      2. still flat      -> the resting BUY LIMIT, priced off completed bars
                            only, may fill; its stop may fire on this same bar
      3. the bar closes  -> the anchor ratchets for the next bar

    Step 2 is where `fill_model` bites, and it is worth understanding before
    trusting any number this produces: under "spec" an entry that follows an
    exit *in the same bar* is priced at that bar's open — a price that traded
    before the exit did. See PHASE2_PARITY.md S10.
    """
    if fill_model not in FILL_MODELS:
        raise ValueError(f"bad fill_model={fill_model!r}")
    start, stop = sm.cfg.start_idx, sm.cfg.last_holding_idx
    tradable = [b for b in bars if start <= b.idx <= stop]

    for bar in bars:
        sm.on_bar_open(bar.idx)

        if start <= bar.idx <= stop:
            exit_px = None
            if sm.in_position:
                br = sm.bracket
                if bar.low <= br.stop_px:
                    # SELL STOP is stop-market: a gap through fills at the open.
                    exit_px = min(bar.open, br.stop_px)
                    sm.on_exit_fill(exit_px, bar.idx, "stop")
                elif bar.idx > sm.entry_bar and bar.high >= br.target_px:
                    # §2.6: the target may not fill on the entry bar.
                    exit_px = max(bar.open, br.target_px)
                    sm.on_exit_fill(exit_px, bar.idx, "target")

            entry = sm.working_entry
            if (entry is not None and bar.low <= entry.limit_px
                    and not (fill_model == "next_bar" and exit_px is not None)):
                px = min(entry.limit_px, bar.open)
                if fill_model == "no_better" and exit_px is not None:
                    px = min(entry.limit_px, max(bar.open, exit_px))
                sm.on_entry_fill(px, bar.idx)
                br = sm.bracket
                # The bracket is live from the fill, so the stop may fire on the
                # entry bar. entry_px <= open always, so no gap-through here.
                if bar.low <= br.stop_px:
                    sm.on_exit_fill(br.stop_px, bar.idx, "stop")

        sm.on_bar_close(bar)

    if sm.in_position and tradable:
        sm.flatten(tradable[-1].close, tradable[-1].idx)


# ------------------------------------------------------------- sleeve run
def replay_symbol(symbol: str, cfg: Optional[SleeveConfig] = None,
                  root: str = ROOT,
                  sessions: Optional[list] = None,
                  fill_model: str = "spec"):
    """Returns (daily_log, ON-day return Series, trade log) — same shape as
    `spec_engine.run_sleeve`, so the two can be diffed directly."""
    cfg = cfg or backtest_config(symbol)
    sessions = sessions if sessions is not None else load_sessions(symbol, root)
    history = FeatureHistory()

    log_rows, trade_rows, returns = [], [], {}
    for date, bars in sessions:
        stats = session_stats(bars)
        atr5, thr80 = history.atr5(), history.thr80()

        sm = SleeveStateMachine(cfg)
        gate = sm.begin_session(date, atr5, stats.is_half_day, stats.late_open)
        filt = None
        if gate.ok:
            filt = sm.apply_morning_filter(stats.or30, thr80, stats.pos10)
            if filt.ok:
                replay_session(bars, sm, fill_model)

        rec = {
            "date": date, "symbol": symbol,
            "atr5": atr5, "gate_on": gate.ok, "gate_reason": gate.reason,
            "or30": stats.or30, "thr80": thr80, "pos10": stats.pos10,
            "filter_on": bool(filt.ok) if filt else False,
            "filter_reason": filt.reason if filt else "gate_off",
            "n_bars": stats.n_bars, "is_half_day": stats.is_half_day,
            "traded": bool(filt.ok) if filt else False,
            "fills": sm.fills, "stop_outs": sm.stop_outs,
            "anchor_updates": len(sm.anchor_updates), "pnl": sm.pnl,
        }
        if rec["traded"]:
            returns[date] = sm.pnl
            for t in sm.trades:
                trade_rows.append({
                    "date": date, "symbol": symbol,
                    "entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
                    "entry_px": t.entry_px, "exit_px": t.exit_px,
                    "limit_px": t.limit_px,
                    "qty": t.qty, "ret": t.ret, "outcome": t.outcome})
        log_rows.append(rec)
        history.append(stats)      # only now is day d part of history

    daily_log = pd.DataFrame(log_rows).set_index("date")
    on = pd.Series(returns, dtype=float).sort_index()
    on.index.name = "date"
    return daily_log, on, pd.DataFrame(trade_rows)


# -------------------------------------------------------------- reporting
def _fmt(x, nd=2):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:,.{nd}f}"


def equivalence_report(symbols=("SOXL", "SOXS"), root: str = ROOT) -> int:
    """Compare the live state machine against the Phase 1 engine. 0 == green."""
    from spec_engine import SPEC_LITERAL, run_sleeve      # noqa: E402

    failures = 0
    print("=" * 74)
    print("STAGE 1 — live state machine vs phase1/spec_engine (SPEC_LITERAL)")
    print("=" * 74)
    for sym in symbols:
        ref_log, ref_on, ref_tr = run_sleeve(sym, SPEC_LITERAL, root=root)
        live_log, live_on, live_tr = replay_symbol(sym, backtest_config(sym), root=root)

        only_ref = sorted(set(ref_on.index) - set(live_on.index))
        only_live = sorted(set(live_on.index) - set(ref_on.index))
        common = ref_on.index.intersection(live_on.index)
        dmax = float((ref_on[common] - live_on[common]).abs().max()) if len(common) else 0.0

        gate_diff = int((ref_log["gate_reason"] != live_log["gate_reason"]).sum())
        filt_diff = int((ref_log["filter_reason"] != live_log["filter_reason"]).sum())
        atr_diff = float((ref_log["atr5"] - live_log["atr5"]).abs().max())
        thr_diff = float((ref_log["thr80"] - live_log["thr80"]).abs().max())
        or_diff = float((ref_log["or30"] - live_log["or30"]).abs().max())
        pos_diff = float((ref_log["pos10"] - live_log["pos10"]).abs().max())
        fills_diff = int((ref_log["fills"] != live_log["fills"]).sum())
        tr_diff = len(ref_tr) - len(live_tr)
        px_diff = 0.0
        if len(ref_tr) == len(live_tr) and len(ref_tr):
            px_diff = float(max((ref_tr["entry_px"] - live_tr["entry_px"]).abs().max(),
                                (ref_tr["exit_px"] - live_tr["exit_px"]).abs().max()))
        outcome_diff = (int((ref_tr["outcome"] != live_tr["outcome"]).sum())
                        if len(ref_tr) == len(live_tr) else -1)

        ok = (not only_ref and not only_live and dmax < 1e-12 and gate_diff == 0
              and filt_diff == 0 and fills_diff == 0 and tr_diff == 0
              and outcome_diff == 0 and px_diff < 1e-9)
        failures += 0 if ok else 1

        print(f"\n{sym}  {'PASS' if ok else 'FAIL'}")
        print(f"  ON days                  ref {len(ref_on)}  live {len(live_on)}"
              f"   only-ref {len(only_ref)}  only-live {len(only_live)}")
        print(f"  max |daily P&L diff|     {dmax:.3e}")
        print(f"  gate/filter reason diffs {gate_diff} / {filt_diff}")
        print(f"  feature max diffs        atr5 {atr_diff:.2e}  thr80 {thr_diff:.2e}"
              f"  or30 {or_diff:.2e}  pos10 {pos_diff:.2e}")
        print(f"  trades                   ref {len(ref_tr)}  live {len(live_tr)}"
              f"   outcome diffs {outcome_diff}  max |px diff| {px_diff:.2e}")
        print(f"  fill-count diffs         {fills_diff}")
        print(f"  gross bp/ON-day          ref {_fmt(ref_on.mean()*1e4)}"
              f"   live {_fmt(live_on.mean()*1e4)}")

    print("\n" + "=" * 74)
    print("STAGE 1 EQUIVALENCE: " + ("PASS" if failures == 0 else f"FAIL ({failures})"))
    print("=" * 74)
    return 1 if failures else 0


def sizing_basis_report(symbols=("SOXL", "SOXS"), root: str = ROOT) -> None:
    """S9 — §2.4 sizes off the limit price; the research engine sizes off the
    fill price. They differ only when a gap fills through the limit."""
    print("=" * 74)
    print("S9 — sizing basis: §2.4 'limit_price' vs the research engine's fill price")
    print("=" * 74)
    print(f"{'sleeve':<7}{'fill-priced bp':>16}{'limit-priced bp':>18}"
          f"{'delta':>10}{'trades affected':>18}")
    for sym in symbols:
        sessions = load_sessions(sym, root)
        _, on_fill, tr_fill = replay_symbol(
            sym, backtest_config(sym), sessions=sessions)
        _, on_limit, _ = replay_symbol(
            sym, replace(backtest_config(sym), sizing_basis="limit"),
            sessions=sessions)
        common = on_fill.index.intersection(on_limit.index)
        a, b = on_fill[common].mean() * 1e4, on_limit[common].mean() * 1e4
        # a gap-through entry is one that filled below its own resting limit
        gapped = int((tr_fill["entry_px"] < tr_fill["limit_px"] - 1e-12).sum())
        share = f"{gapped}/{len(tr_fill)} ({gapped / max(len(tr_fill), 1):.1%})"
        print(f"{sym:<7}{a:>16.2f}{b:>18.2f}{b - a:>10.2f}{share:>18}")
    print("\n§2.4 sizes off the limit price, so a gap-through fill buys the same\n"
          "shares at a better price rather than more shares. The live engine has\n"
          "no choice — the order quantity is fixed when the order is placed.\n")


def fill_model_report(symbols=("SOXL", "SOXS"), root: str = ROOT) -> None:
    """S10 — how much of the measured edge rests on same-bar sequencing.

    The rules of §2 are identical in every row; only the price a 5-minute
    simulator is willing to assume for a re-entry that follows an exit inside
    the same bar changes. The truth lies between the rows, and no amount of
    5-minute data can locate it — see PHASE2_PARITY.md S10.
    """
    print("=" * 78)
    print("S10 — same-bar re-entry sensitivity (fill model, NOT a strategy change)")
    print("=" * 78)
    print(f"{'sleeve':<7}{'fill model':<12}{'bp/ON-day':>12}{'Sharpe':>9}"
          f"{'ON days':>9}{'entries':>9}{'same-bar':>10}")
    for sym in symbols:
        sessions = load_sessions(sym, root)
        for model in FILL_MODELS:
            _, on, tr = replay_symbol(sym, backtest_config(sym),
                                      sessions=sessions, fill_model=model)
            sharpe = on.mean() / on.std() * np.sqrt(252) if on.std() else float("nan")
            same_bar = 0
            if len(tr):
                prev_exit = tr.sort_values(["date", "entry_bar"]).groupby(
                    "date")["exit_bar"].shift(1)
                same_bar = int((tr.sort_values(["date", "entry_bar"])["entry_bar"]
                                == prev_exit).sum())
            print(f"{sym:<7}{model:<12}{on.mean() * 1e4:>12.1f}{sharpe:>9.2f}"
                  f"{len(on):>9}{len(tr):>9}{same_bar:>10}")
    print("\n'spec' is the validated engine and the number every published figure\n"
          "comes from. 'no_better' forbids re-buying below the price just sold\n"
          "inside one bar; 'next_bar' forbids same-bar re-entry outright.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 1 replay harness")
    ap.add_argument("--sizing", action="store_true",
                    help="report the S9 sizing-basis difference and exit")
    ap.add_argument("--fill-models", action="store_true",
                    help="report the S10 same-bar re-entry sensitivity and exit")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()
    if args.sizing:
        sizing_basis_report(root=args.root)
        return 0
    if args.fill_models:
        fill_model_report(root=args.root)
        return 0
    return equivalence_report(root=args.root)


if __name__ == "__main__":
    raise SystemExit(main())
