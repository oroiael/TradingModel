"""
V21 — re-score every strategy parameter on the corrected simulator.

See V21_REPARAM.md. The bar in that document was committed before this ran.

    python3 band_lab/v2_dev/reparam.py --run       # sweep; writes every trade
    python3 band_lab/v2_dev/reparam.py --verify    # rebuild the summary from
                                                   # the trade files and compare
    python3 band_lab/v2_dev/reparam.py --show target_pct

`--verify` is the point of the layout. Every number in the summary is recomputed
from the raw per-trade CSVs and compared; any mismatch is a hard failure. You do
not have to take a single figure here on trust.
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
for _p in (_HERE, os.path.join(_BAND_LAB, "live"), os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest_as_executed import COST_BP_PER_FILL, START, replay_session  # noqa: E402
from intrabar import load_1min_sessions                                   # noqa: E402
from replay import backtest_config, load_sessions                         # noqa: E402
from sleeve import START_IDX, SleeveStateMachine                          # noqa: E402
from strategy_core import FeatureHistory, session_stats                   # noqa: E402
from spec_constants import (DIP_PCT, GATE_ATR5_MIN, MAX_FILLS,            # noqa: E402
                            STOP_PCT, TARGET_PCT)

SLEEVES = ("SOXL", "SOXS")
OUT = os.path.join(_HERE, "out", "reparam")

#: The corrected simulator. Identical to backtest_as_executed.py; not a knob.
AS_EXECUTED = dict(wait_bars=1, flatten_at_open_of_next=True)
LIVE_CFG = dict(whole_shares=True, tick_rounding=True, sizing_basis="limit")

#: (config field, incumbent, values to score). `morning_filter` is not a
#: SleeveConfig field — it is applied by the caller, so it is handled specially.
SWEEPS = {
    "dip_pct":       (DIP_PCT,       [0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02]),
    "target_pct":    (TARGET_PCT,    [0.005, 0.0075, 0.01, 0.015, 0.02]),
    "stop_pct":      (STOP_PCT,      [0.02, 0.03, 0.04, 0.05, 0.06]),
    "start_idx":     (START_IDX,     [12, 15, 18, 24, 30]),
    "max_fills":     (MAX_FILLS,     [1, 2, 3, 5, 8, 20]),
    "gate_atr5_min": (GATE_ATR5_MIN, [0.0, 4.0, 5.0, 6.0, 7.0, 8.0]),
}


def tag(value) -> str:
    return str(value).replace(".", "p")


def trades_path(param, value, symbol):
    return os.path.join(OUT, f"trades__{param}__{tag(value)}__{symbol}.csv")


def one_run(symbol, param, value, sessions, fine, dates):
    """Replay the whole sample once. Returns the trade table."""
    cfg = dataclasses.replace(backtest_config(symbol), **LIVE_CFG,
                              **{param: value})
    history = FeatureHistory()
    rows = []
    for date, dbars in sessions:
        stats = session_stats(dbars)
        atr5, thr80 = history.atr5(), history.thr80()
        if date in dates:
            sm = SleeveStateMachine(cfg)
            g = sm.begin_session(date, atr5, stats.is_half_day, stats.late_open)
            if g.ok and sm.apply_morning_filter(stats.or30, thr80, stats.pos10).ok:
                replay_session(dbars, fine.get(date, dbars), sm,
                               5 if date in fine else 1, **AS_EXECUTED)
                if not sm.trades:
                    # An ON day that never filled still counts as a zero day;
                    # dropping it would quietly shrink the denominator and
                    # flatter every parameter that trades less often.
                    rows.append(dict(date=date.date(), entry_bar=-1, exit_bar=-1,
                                     entry_px=0.0, exit_px=0.0, qty=0.0,
                                     ret=0.0, outcome="no_fill"))
                for t in sm.trades:
                    rows.append(dict(date=date.date(), entry_bar=t.entry_bar,
                                     exit_bar=t.exit_bar, entry_px=t.entry_px,
                                     exit_px=t.exit_px, qty=t.qty, ret=t.ret,
                                     outcome=t.outcome))
        history.append(stats)
    return pd.DataFrame(rows)


def daily_from_trades(tr, symbol):
    """Net return per ON-day, rebuilt from the trade rows alone.

    This is the only path from trades to a daily number, so `--verify` and
    `--run` cannot drift: both call it.
    """
    if not len(tr):
        return pd.Series(dtype=float)
    real = tr[tr.outcome != "no_fill"]
    gross = real.groupby("date")["ret"].sum()
    fills = real.groupby("date").size()
    days = pd.Index(sorted(tr["date"].unique()))
    gross = gross.reindex(days).fillna(0.0)
    fills = fills.reindex(days).fillna(0)
    return gross - fills * COST_BP_PER_FILL[symbol] / 1e4


def summarise(tr, symbol):
    d = daily_from_trades(tr, symbol)
    if not len(d):
        return dict(on_days=0, trades=0, mean_bp=float("nan"), sd_bp=float("nan"),
                    sem_bp=float("nan"), t=float("nan"), total_pct=float("nan"),
                    mdd_pct=float("nan"), win_pct=float("nan"), pos_years=0,
                    n_years=0)
    real = tr[tr.outcome != "no_fill"]
    sd = d.std(ddof=1)
    sem = sd / math.sqrt(len(d)) if len(d) > 1 else float("nan")
    eq = (1.0 + d).cumprod()
    idx = pd.to_datetime(pd.Series(d.index))
    yrs = d.groupby(idx.dt.year.values).mean()
    return dict(on_days=len(d), trades=len(real), mean_bp=d.mean() * 1e4,
                sd_bp=sd * 1e4, sem_bp=sem * 1e4,
                t=d.mean() / sem if sem else float("nan"),
                total_pct=(eq.iloc[-1] - 1) * 100,
                mdd_pct=float((eq / eq.cummax() - 1).min()) * 100,
                win_pct=float((d > 0).mean()) * 100,
                pos_years=int((yrs > 0).sum()), n_years=int(len(yrs)))


def assumptions():
    print("ASSUMPTIONS IN THIS RUN — every one of them, stated")
    print("-" * 78)
    print("  data          real 1-minute and 5-minute bars, 2022-01-01 onward")
    print("  decisions     on 5-minute bars; fills resolved on 1-minute bars")
    print("  re-buy        must wait one full minute after a sell     <- the fix")
    print("  buy price     lower of (your limit, that minute's open)")
    print("  target sell   higher of (that minute's open, your target)")
    print("  stop sell     lower of (that minute's open, your stop)")
    print("  end of day    market order at 15:55, filled at that bar's open")
    print("  shares        whole shares, prices rounded to the cent")
    print("  sizing        off the limit price, as the live engine does")
    print(f"  cost          {COST_BP_PER_FILL['SOXL']:.3f} bp/fill SOXL, "
          f"{COST_BP_PER_FILL['SOXS']:.3f} SOXS")
    print("                (checked: IBKR 08-03..08-25 commissions $599.36 = "
          "1.16 bp/side)")
    print("  an ON day that never fills counts as a 0.00% day, not a dropped day")
    print("-" * 78)


def run():
    os.makedirs(OUT, exist_ok=True)
    assumptions()
    data = {}
    for s in SLEEVES:
        fine = dict(load_1min_sessions(s, ROOT))
        sessions = load_sessions(s, ROOT)
        dates = {d for d, _ in sessions} & set(fine)
        data[s] = (sessions, fine, {d for d in dates if d >= START})

    rows = []
    total = sum(len(v) for _, v in SWEEPS.values()) * len(SLEEVES)
    i = 0
    for param, (incumbent, values) in SWEEPS.items():
        for value in values:
            for s in SLEEVES:
                i += 1
                sessions, fine, dates = data[s]
                tr = one_run(s, param, value, sessions, fine, dates)
                tr.to_csv(trades_path(param, value, s), index=False)
                rows.append(dict(param=param, value=value, symbol=s,
                                 incumbent=(value == incumbent),
                                 **summarise(tr, s)))
                print(f"  [{i:>3}/{total}] {param}={value} {s}: "
                      f"{rows[-1]['trades']} trades, "
                      f"{rows[-1]['mean_bp']:+.2f} bp/ON-day", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "summary.csv"), index=False)
    print(f"\nwrote {OUT}/summary.csv and {total} per-trade files")
    report(df)


def verify():
    """Rebuild every summary number from the raw trade files."""
    path = os.path.join(OUT, "summary.csv")
    if not os.path.exists(path):
        print("no summary.csv — run --run first", file=sys.stderr)
        return 2
    df = pd.read_csv(path)
    bad = 0
    print("REBUILDING EVERY SUMMARY ROW FROM ITS RAW TRADE FILE")
    print("-" * 78)
    for _, r in df.iterrows():
        p = trades_path(r["param"], r["value"], r["symbol"])
        if not os.path.exists(p):
            print(f"  MISSING {p}")
            bad += 1
            continue
        got = summarise(pd.read_csv(p), r["symbol"])
        for k in ("on_days", "trades", "mean_bp", "sd_bp", "t", "total_pct",
                  "mdd_pct", "win_pct", "pos_years"):
            a, b = r[k], got[k]
            ok = (a == b) if isinstance(b, int) else (
                abs(float(a) - float(b)) < 1e-6 or
                (pd.isna(a) and pd.isna(b)))
            if not ok:
                print(f"  MISMATCH {r['param']}={r['value']} {r['symbol']} "
                      f"{k}: summary {a} vs trades {b}")
                bad += 1
    print("-" * 78)
    if bad:
        print(f"FAILED — {bad} mismatch(es). The summary does not describe the "
              f"trade files.")
        return 1
    print(f"OK — all {len(df)} rows rebuild exactly from their trade files.")
    print(f"     {int(df.trades.sum())} trades checked across "
          f"{len(df)} configurations.")
    return 0


def report(df=None, only=None):
    if df is None:
        df = pd.read_csv(os.path.join(OUT, "summary.csv"))
    print()
    for param, (incumbent, _values) in SWEEPS.items():
        if only and param != only:
            continue
        print("=" * 96)
        print(f"{param}   (incumbent = {incumbent})")
        print("=" * 96)
        print(f"{'value':>10}{'':>3}{'SOXL bp':>10}{'t':>7}{'yrs+':>6}"
              f"{'maxDD':>9}{'':>4}{'SOXS bp':>10}{'t':>7}{'yrs+':>6}{'maxDD':>9}"
              f"{'':>4}{'trades L/S':>13}")
        sub = df[df.param == param]
        for value in sorted(sub.value.unique()):
            r = {s: sub[(sub.value == value) & (sub.symbol == s)].iloc[0]
                 for s in SLEEVES}
            mark = " <-" if r["SOXL"]["incumbent"] else "   "
            print(f"{value:>10}{mark:>3}"
                  f"{r['SOXL']['mean_bp']:>+10.2f}{r['SOXL']['t']:>7.2f}"
                  f"{int(r['SOXL']['pos_years'])}/{int(r['SOXL']['n_years'])}"
                  f"{'':>2}{r['SOXL']['mdd_pct']:>9.1f}{'':>4}"
                  f"{r['SOXS']['mean_bp']:>+10.2f}{r['SOXS']['t']:>7.2f}"
                  f"{int(r['SOXS']['pos_years'])}/{int(r['SOXS']['n_years'])}"
                  f"{'':>2}{r['SOXS']['mdd_pct']:>9.1f}{'':>4}"
                  f"{int(r['SOXL']['trades'])}/{int(r['SOXS']['trades']):<6}")
        # --- the prespecified readings, applied mechanically
        for s in SLEEVES:
            t = sub[sub.symbol == s].sort_values("value")
            inc = t[t.incumbent]
            if not len(inc):
                continue
            inc = inc.iloc[0]
            best = t.loc[t.mean_bp.idxmax()]
            sem = float(inc.sem_bp)
            gap = float(best.mean_bp) - float(inc.mean_bp)
            spread = float(t.mean_bp.max() - t.mean_bp.min())
            notes = []
            notes.append(f"P1 unrefuted (best is {gap:+.2f} bp away, "
                         f"1 se = {sem:.2f})" if gap <= sem else
                         f"best={best.value} beats incumbent by {gap:+.2f} bp "
                         f"= {gap/sem:.1f} se")
            if spread < sem:
                notes.append(f"P3 flat: best-worst {spread:.2f} bp < 1 se")
            vals = t.mean_bp.values
            spiky = [t.value.values[j] for j in range(1, len(vals) - 1)
                     if vals[j] - max(vals[j-1], vals[j+1]) > sem]
            if spiky:
                notes.append(f"P4 SPIKE at {spiky} — treat as unreliable")
            print(f"   {s}: " + "; ".join(notes))
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description="V21 parameter re-scoring")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--show")
    a = ap.parse_args()
    if a.verify:
        return verify()
    if a.show:
        report(only=a.show)
        return 0
    if a.run:
        run()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
