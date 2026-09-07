"""Testing the three underlying-only claims this lab made but never checked.

After the trade tests showed the trigger carries no directional edge, three
claims were offered about using the timing data for RISK MANAGEMENT rather than
signal. They were asserted, not measured. This measures them.

  CLAIM 1  "time stops beat price stops" — 93% of 2%/0.5% episodes resolve in 30
           minutes, so a clock exit should do at least as well as a trailing one.
  CLAIM 2  "don't set a trailing stop tighter than ~4x the median minute (0.119%)"
           — below ~0.5% you stop on noise.
  CLAIM 3  "don't open a stop-managed position in the last 30 minutes" — that is
           where 34-96% of all overnight exposure originates.

Entry for every test is the same: the +2% upswing trigger (7,014 of them), so
only the EXIT rule varies. The entry has no edge, which is the point — these are
exit-quality questions, and a rule is judged on dispersion, tail and execution
slippage, not on turning a zero-mean entry into a profit.

Usage:  python3 retreat_lab/exit_rules.py
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, median, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, pct, tag

BPS = 10000


def load():
    close, ts, idx = [], [], {}
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            idx[t] = len(close); ts.append(t)
            close.append(int((Decimal(a[4]) * 100).to_integral_exact()))
    return close, ts, idx


def entries(idx):
    f = os.path.join(ROOT, "retreat_lab/out",
                     f"retreat_episodes_1min_{tag(200, 50)}.csv")
    return [idx[dt.datetime.strptime(r["trigger_ts"], "%Y-%m-%d %H:%M")]
            for r in csv.DictReader(open(f))]


def run(close, ts, dates, ent, stop_bps=None, time_min=None, eod=False):
    """Exit on whichever of the active rules fires first. Returns per-trade
    dicts: return in bp, whether it crossed a close, and the slippage past the
    intended stop level (0 when no stop rule is active)."""
    out = []
    n = len(close)
    for g in ent:
        peak = close[g]
        limit = g + time_min if time_min else n - 1
        j, fired = None, None
        for k in range(g + 1, n):
            if eod and dates[k] != dates[g]:
                j, fired = k - 1, "eod"; break         # last bar of the entry day
            if close[k] > peak:
                peak = close[k]
            if stop_bps and close[k] * BPS <= peak * (BPS - stop_bps):
                j, fired = k, "stop"; break
            if k >= limit:
                j, fired = k, "time"; break
        if j is None or j >= n:
            continue
        # slippage is only defined when the STOP is what fired; a clock or bell
        # exit has no intended price level to miss, and scoring it against the
        # trailing level produced spurious negative "slippage" in a first pass.
        want = peak * (BPS - stop_bps) / BPS if stop_bps else None
        out.append(dict(
            ret=(close[j] / close[g] - 1) * BPS,
            spans=dates[j] != dates[g],
            held=j - g, fired=fired,
            slip=((want - close[j]) / want * BPS) if fired == "stop" else None))
    return out


def show(lbl, r):
    if not r:
        print(f"  {lbl:<30} (none)"); return
    x = [d["ret"] for d in r]
    sl = [d["slip"] for d in r if d["slip"] is not None]
    sp = sum(1 for d in r if d["spans"]) / len(r)
    st = f"{mean(sl):>6.1f}bp on {len(sl)/len(r):>4.0%}" if sl else "        n/a"
    print(f"  {lbl:<30} n={len(x):<5} mean {mean(x):>7.2f}bp  med {median(x):>7.2f}bp  "
          f"sd {stdev(x):>7.1f}  p1 {pct(x,1):>8.1f}  worst {min(x):>8.0f}  "
          f"held {median([d['held'] for d in r]):>5.0f}m  spans {sp:>5.1%}  "
          f"slip {st}")


def main():
    close, ts, idx = load()
    dates = [t.date() for t in ts]
    ent = entries(idx)
    print(f"entry: the +2% upswing trigger, {len(ent):,} of them, "
          f"{ts[ent[0]]:%Y-%m-%d} → {ts[ent[-1]]:%Y-%m-%d}")
    print("the entry has NO directional edge — these compare EXIT rules only\n")

    print("=" * 122)
    print("CLAIM 2 — 'don't set a trailing stop tighter than ~0.5%'")
    print("=" * 122)
    for w in (25, 50, 100, 150, 200, 300, 500):
        show(f"trailing stop {w/100:.2f}%", run(close, ts, dates, ent, stop_bps=w))

    print("\n" + "=" * 122)
    print("CLAIM 1 — 'time stops beat price stops'")
    print("=" * 122)
    for t_ in (5, 15, 30, 60, 120, 390):
        show(f"time stop {t_} min", run(close, ts, dates, ent, time_min=t_))
    print("  --- the two combined (whichever fires first) ---")
    for w, t_ in ((50, 30), (50, 60), (100, 30), (100, 60), (200, 60)):
        show(f"stop {w/100:.2f}% + time {t_}m",
             run(close, ts, dates, ent, stop_bps=w, time_min=t_))

    print("\n" + "=" * 122)
    print("CLAIM 3 — 'don't open a stop-managed position in the last 30 minutes'")
    print("=" * 122)
    late = [g for g in ent if ts[g].hour * 60 + ts[g].minute >= 930]
    early = [g for g in ent if ts[g].hour * 60 + ts[g].minute < 930]
    print(f"  {len(early):,} entries before 15:30, {len(late):,} at or after\n")
    for w in (50, 100, 200):
        print(f"  --- trailing stop {w/100:.2f}% ---")
        show("  entries before 15:30", run(close, ts, dates, early, stop_bps=w))
        show("  entries 15:30-16:00", run(close, ts, dates, late, stop_bps=w))
        show("  late + forced EOD exit",
             run(close, ts, dates, late, stop_bps=w, eod=True))

    print("\n" + "=" * 122)
    print("FORCED FLAT AT THE BELL — never hold a stop-managed position overnight")
    print("=" * 122)
    for w in (50, 100, 200):
        show(f"stop {w/100:.2f}%, hold overnight",
             run(close, ts, dates, ent, stop_bps=w))
        show(f"stop {w/100:.2f}%, flat at bell",
             run(close, ts, dates, ent, stop_bps=w, eod=True))


if __name__ == "__main__":
    main()
