"""
The same-minute re-buy, shown one real minute at a time.

`wait_sweep.py` proves the published edge came from the re-buy PRICE and not
from the speed of the re-buy. This prints the individual minutes so the claim
can be checked by eye against the 1-minute file instead of taken on trust.

For every re-buy that happened in the very minute a TARGET sell happened, it
prints the actual bar — open, high, low, close — the price the backtest sold at,
the price it paid to get back in, and the cheapest price that was still
available after the sell. The difference between the last two is money the
backtest booked and no trader could have taken.

    python3 band_lab/v2_dev/same_minute_examples.py SOXL
    python3 band_lab/v2_dev/same_minute_examples.py SOXS --n 20
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
for _p in (os.path.join(_BAND_LAB, "live"), os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest_as_executed import ROOT, START                       # noqa: E402
from intrabar import load_1min_sessions                            # noqa: E402
from replay import backtest_config, load_sessions                  # noqa: E402
from sleeve import SleeveStateMachine                              # noqa: E402
from strategy_core import FeatureHistory, session_stats            # noqa: E402

STEP = 5        # decisions are on 5-minute bars; fills are on 1-minute bars


def clock(minute_idx: int) -> str:
    """1-minute bar index -> wall clock. Bar 0 is 09:30."""
    m = 9 * 60 + 30 + minute_idx
    return f"{m//60:02d}:{m%60:02d}"


def collect(symbol: str) -> pd.DataFrame:
    """Replay exactly as published and record every same-minute target re-buy."""
    found: list[dict] = []
    fine = dict(load_1min_sessions(symbol, ROOT))
    sessions = load_sessions(symbol, ROOT)
    dates = {d for d, _ in sessions} & set(fine)
    cfg = backtest_config(symbol)
    history = FeatureHistory()
    n_days = 0

    for date, dbars in sessions:
        stats = session_stats(dbars)
        atr5, thr80 = history.atr5(), history.thr80()
        if date in dates and date >= START:
            sm = SleeveStateMachine(cfg)
            g = sm.begin_session(date, atr5, stats.is_half_day, stats.late_open)
            if g.ok and sm.apply_morning_filter(stats.or30, thr80, stats.pos10).ok:
                n_days += 1
                _replay(dbars, fine[date], sm, date, found)
        history.append(stats)

    df = pd.DataFrame(found)
    df.attrs["n_days"] = n_days
    return df


def _replay(decision_bars, fill_bars, sm, date, found):
    start, stop = sm.cfg.start_idx, sm.cfg.last_holding_idx
    by: dict[int, list] = {}
    for b in fill_bars:
        by.setdefault(b.idx // STEP, []).append(b)

    seq = entry_seq = 0
    exit_seq, exit_px, exit_kind = -1, None, None
    for dbar in decision_bars:
        sm.on_bar_open(dbar.idx)
        if start <= dbar.idx <= stop:
            for fb in sorted(by.get(dbar.idx, [dbar]), key=lambda b: b.idx):
                seq += 1
                if sm.in_position:
                    br = sm.bracket
                    if fb.low <= br.stop_px:
                        exit_px = min(fb.open, br.stop_px)
                        sm.on_exit_fill(exit_px, dbar.idx, "stop")
                        exit_seq, exit_kind = seq, "stop"
                    elif seq > entry_seq and fb.high >= br.target_px:
                        exit_px = max(fb.open, br.target_px)
                        sm.on_exit_fill(exit_px, dbar.idx, "target")
                        exit_seq, exit_kind = seq, "target"
                entry = sm.working_entry
                if entry is not None and fb.low <= entry.limit_px:
                    paid = min(entry.limit_px, fb.open)
                    if seq == exit_seq and exit_kind == "target":
                        # The best price still on offer AFTER selling at exit_px.
                        # The bar's open is not it: the open already traded.
                        honest = min(entry.limit_px, max(fb.open, exit_px))
                        found.append(dict(
                            date=date, clock=clock(fb.idx), o=fb.open,
                            h=fb.high, l=fb.low, c=fb.close, sold_at=exit_px,
                            paid=paid, honest=honest,
                            gift=(honest - paid) / paid))
                    sm.on_entry_fill(paid, dbar.idx)
                    entry_seq = seq
                    if fb.low <= sm.bracket.stop_px:
                        sm.on_exit_fill(min(fb.open, sm.bracket.stop_px),
                                        dbar.idx, "stop")
        sm.on_bar_close(dbar)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", choices=("SOXL", "SOXS"))
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()

    df = collect(a.symbol)
    days = df.attrs["n_days"]
    per_day = len(df) / days
    print("=" * 96)
    print(f"{a.symbol} — every re-buy that happened in the same minute as a "
          f"TARGET sell, 2022+")
    print("=" * 96)
    print(f"  {len(df):,} of them over {days:,} active days = "
          f"{per_day:.2f} per day")
    print(f"  the bar's open was BELOW the sell price in "
          f"{int((df.gift > 0).sum()):,} of {len(df):,} "
          f"({(df.gift > 0).mean()*100:.0f}%) — i.e. almost always a discount")
    print(f"  size of the discount: median {df.gift.median()*100:.3f}%, "
          f"mean {df.gift.mean()*100:.3f}%")
    print(f"\n  {per_day:.2f} per day x {df.gift.mean()*100:.3f}% = "
          f"{per_day*df.gift.mean()*1e4:.1f} bp per day of return that came "
          f"from a price that had already traded.")

    print(f"\n  the {a.n} biggest, straight out of {a.symbol}_1min.csv:\n")
    h = (f"  {'date':<12}{'minute':>8}{'open':>12}{'high':>12}{'low':>12}"
         f"{'sold at':>12}{'paid':>12}{'available':>12}{'gift':>8}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for _, r in df.nlargest(a.n, "gift").iterrows():
        print(f"  {str(r['date'].date()):<12}{r['clock']:>8}{r.o:>12.4f}"
              f"{r.h:>12.4f}{r.l:>12.4f}{r.sold_at:>12.4f}{r.paid:>12.4f}"
              f"{r.honest:>12.4f}{r.gift*100:>7.2f}%")

    med = df.iloc[(df.gift - df.gift.median()).abs().argsort()[:1]].iloc[0]
    print(f"\n  a typical one — {med['date'].date()} at {med['clock']}, "
          f"one minute of {a.symbol}:\n")
    print(f"    the minute opened at {med.o:.4f}, ran up to {med.h:.4f}, "
          f"down to {med.l:.4f}, closed at {med.c:.4f}")
    print(f"    the backtest SOLD at {med.sold_at:.4f} — its target, hit on "
          f"the way up")
    print(f"    then BOUGHT BACK in that same minute at {med.paid:.4f}, "
          f"the minute's OPEN")
    print(f"    but {med.paid:.4f} traded BEFORE the sell at {med.sold_at:.4f}. "
          f"Once you have sold at the high of the minute,")
    print(f"    the low of that same minute is behind you. The cheapest thing "
          f"still available was {med.honest:.4f}.")
    print(f"    The backtest booked {med.gift*100:.2f}% that nobody could "
          f"have taken.")
    print(f"\n  The rest of the bar is real. The sell is real. Only the "
          f"re-buy price is a time machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
