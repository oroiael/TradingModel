"""Do the trigger / peak / retreat bars carry ANY information?

tradeability.py showed the mechanical trades are near zero-mean. That could
still hide a conditional edge, so this compares forward returns AFTER each
event against the UNCONDITIONAL forward return from a random bar over the same
window. If conditional == unconditional, the event told you nothing.

Two conditioning tests:
  1. fixed horizons after trigger / peak / retreat vs all bars
  2. the OVERNIGHT return when an episode was still open at the close, vs every
     other overnight -- the one structural asymmetry the timing study surfaced
     (late-session triggers span a close 42-82% of the time)

Usage:  python3 retreat_lab/edge_test.py
"""
import csv, sys, os, datetime as dt
from decimal import Decimal
from statistics import median, mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import CONFIGS, bl, tag, ROOT, pct

H = (15, 30, 60, 390)


def load():
    close, ts, idx = [], [], {}
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            idx[t] = len(close); ts.append(t)
            close.append(float(Decimal(a[4])))
    return close, ts, idx


def fwd(close, i, h):
    return close[i + h] / close[i] - 1 if i + h < len(close) else None


def summ(xs):
    xs = [x for x in xs if x is not None]
    return (f"n={len(xs):>6} mean {mean(xs)*100:>7.3f}% med {median(xs)*100:>7.3f}% "
            f"sd {stdev(xs)*100:>6.2f}% up {sum(1 for x in xs if x>0)/len(xs):>5.1%}")


def tstat(a, b):
    """Welch t of mean(a) - mean(b); |t|>2 is the usual eyebrow-raiser."""
    a = [x for x in a if x is not None]; b = [x for x in b if x is not None]
    va, vb = stdev(a) ** 2 / len(a), stdev(b) ** 2 / len(b)
    return (mean(a) - mean(b)) / (va + vb) ** 0.5


def main():
    close, ts, idx = load()
    dates = [t.date() for t in ts]
    print(f"SOXL_1min.csv  {ts[0]:%Y-%m-%d} → {ts[-1]:%Y-%m-%d}  {len(close):,} bars\n")

    print("=" * 108)
    print("TEST 1 — forward return after each event vs an unconditional random bar")
    print("=" * 108)
    base = {h: [fwd(close, i, h) for i in range(0, len(close), 7)] for h in H}
    for h in H:
        print(f"  +{h:>3}min  UNCONDITIONAL   {summ(base[h])}")
    print()
    for up_bps, dn_bps in CONFIGS:
        f = os.path.join(ROOT, "retreat_lab/out",
                         f"retreat_episodes_1min_{tag(up_bps, dn_bps)}.csv")
        T = lambda s: idx[dt.datetime.strptime(s, "%Y-%m-%d %H:%M")]
        rows = list(csv.DictReader(open(f)))
        ev = {"trigger": [T(r["trigger_ts"]) for r in rows],
              "peak":    [T(r["peak_ts"]) for r in rows],
              "retreat": [T(r["retreat_ts"]) for r in rows]}
        print(f"  --- {bl(up_bps)} / {bl(dn_bps)} ---")
        for name, ii in ev.items():
            for h in H:
                xs = [fwd(close, i, h) for i in ii]
                print(f"  +{h:>3}min  after {name:<8} {summ(xs)}  "
                      f"t vs uncond {tstat(xs, base[h]):>6.2f}")
        print()

    print("=" * 108)
    print("TEST 2 — overnight return when an episode was OPEN at the close, "
          "vs every other overnight")
    print("=" * 108)
    lastbar = {}                      # date -> index of that session's last bar
    for i, d in enumerate(dates):
        lastbar[d] = i
    days = sorted(lastbar)
    on = {}                           # date -> overnight return into the next session
    for k in range(len(days) - 1):
        i, j = lastbar[days[k]], lastbar[days[k]] + 1
        on[days[k]] = close[j] / close[i] - 1
    print(f"  ALL overnights          {summ(list(on.values()))}\n")
    for up_bps, dn_bps in CONFIGS:
        f = os.path.join(ROOT, "retreat_lab/out",
                         f"retreat_episodes_1min_{tag(up_bps, dn_bps)}.csv")
        T = lambda s: idx[dt.datetime.strptime(s, "%Y-%m-%d %H:%M")]
        openat = set()
        for r in csv.DictReader(open(f)):
            g, x = T(r["trigger_ts"]), T(r["retreat_ts"])
            for k in range(g, x):     # every session close inside the episode
                if k + 1 < len(dates) and dates[k] != dates[k + 1]:
                    openat.add(dates[k])
        a = [on[d] for d in openat if d in on]
        b = [on[d] for d in on if d not in openat]
        print(f"  {bl(up_bps)}/{bl(dn_bps)} episode open at the close")
        print(f"     open   {summ(a)}")
        print(f"     other  {summ(b)}   t {tstat(a, b):>6.2f}")


if __name__ == "__main__":
    main()
