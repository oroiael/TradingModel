"""What stop width works with a +1% target? Intraday only, as specified.

The rule under test, exactly:
  enter   at a chosen minute
  exit    at +1%                                    (limit, detected on the HIGH)
     or   on a dip below a FLOOR set W% under entry  (stop, detected on the LOW)
     or   after N minutes                            (time stop)
  whichever comes first. No overnight hold. Bell backstop only if the time stop
  is longer than the session has left.

N defaults to the duration this lab already measured for an upswing before it
retreats -- 4 minutes at 1%/0.25%, 6 at 2%/0.5% -- rather than the
median-time-to-target estimator, which conditions on winners and degenerates to
1 minute.

A trailing variant is reported alongside the fixed floor, since "floor" reads as
a level but the earlier proposal said "retreats by 0.5%".

Usage:  python3 retreat_lab/floor_sweep.py [bps_per_side]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
TARGET = 0.01


def load():
    rows = []
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            rows.append((t, float(Decimal(a[2])), float(Decimal(a[3])),
                         float(Decimal(a[4]))))
    ses, cur, d = [], [], rows[0][0].date()
    for x in rows:
        if x[0].date() != d:
            ses.append(dict(bars=cur, date=d)); cur = []; d = x[0].date()
        cur.append(x)
    ses.append(dict(bars=cur, date=d))
    for s in ses:
        s["mins"] = {b[0].hour * 60 + b[0].minute: k for k, b in enumerate(s["bars"])}
    return ses


def run(ses, entry_min, stop_w, tmin, trail, c):
    out = []
    for s in ses:
        k = s["mins"].get(entry_min)
        if k is None:
            continue
        px = s["bars"][k][3]
        tgt = px * (1 + TARGET)
        peak = px
        why, ret = None, None
        for j, b in enumerate(s["bars"][k + 1:], start=1):
            floor = (peak if trail else px) * (1 - stop_w)
            if b[2] <= floor:                       # stop first (pessimistic)
                why, ret = "stop", floor / px - 1; break
            if b[1] >= tgt:
                why, ret = "target", TARGET; break
            if b[1] > peak:
                peak = b[1]
            if j >= tmin:
                why, ret = "time", b[3] / px - 1; break
        if why is None:
            why, ret = "bell", s["bars"][-1][3] / px - 1
        out.append((ret - 2 * c, why))
    return out


def agg(tr):
    v = [x[0] for x in tr]
    eq = 1.0; pk = 1.0; dd = 0.0
    for x in v:
        eq *= (1 + x); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    sd = stdev(v)
    return dict(n=len(v), mean=mean(v), total=eq - 1, dd=dd,
                t=mean(v) / (sd / len(v) ** 0.5) if sd else 0,
                hit=sum(1 for x in tr if x[1] == "target") / len(v),
                stopped=sum(1 for x in tr if x[1] == "stop") / len(v))


def main():
    ses = load()
    c = COST / 10000.0
    widths = [0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05]
    print(f"SOXL {ses[0]['date']} → {ses[-1]['date']}, {len(ses)} sessions, "
          f"target +1%, INTRADAY ONLY, {COST:.1f} bps/side\n")

    print("=" * 104)
    print("STOP WIDTH SWEEP — fixed floor under entry, 4-minute time stop, enter 09:30")
    print("=" * 104)
    print(f"  {'floor':>8}{'n':>7}{'hit%':>8}{'stopped%':>10}{'mean':>10}"
          f"{'total':>11}{'maxDD':>9}{'t':>7}")
    for w in widths:
        a = agg(run(ses, 570, w, 4, False, c))
        print(f"  {w:>7.2%}{a['n']:>7}{a['hit']:>8.1%}{a['stopped']:>10.1%}"
              f"{a['mean']*100:>9.3f}%{a['total']*100:>10,.0f}%{a['dd']*100:>8.1f}%"
              f"{a['t']:>7.2f}")

    print("\n" + "=" * 104)
    print("FULL MATRIX — mean bp/trade, fixed floor (rows) x time stop minutes (cols)")
    print("enter 09:30, target +1%, intraday only")
    print("=" * 104)
    tms = [2, 4, 6, 10, 15, 30, 60, 390]
    print(f"  {'floor':>8}" + "".join(f"{t:>8}m" for t in tms))
    for w in widths:
        line = f"  {w:>7.2%}"
        for t in tms:
            line += f"{agg(run(ses, 570, w, t, False, c))['mean']*10000:>9.1f}"
        print(line)
    print("\n  (positive = the configuration made money per trade, in bp)")

    print("\n" + "=" * 104)
    print("BEST CONFIGURATIONS ACROSS ENTRY TIMES — intraday only")
    print("=" * 104)
    res = []
    for m, lbl in ((570, "09:30"), (600, "10:00"), (660, "11:00"), (720, "12:00"),
                   (780, "13:00"), (840, "14:00"), (900, "15:00"), (930, "15:30")):
        for w in widths:
            for t in tms:
                for tr in (False, True):
                    a = agg(run(ses, m, w, t, tr, c))
                    a["lbl"] = (f"{lbl} floor {w:.2%} {t}m"
                                + (" trail" if tr else ""))
                    res.append(a)
    res.sort(key=lambda r: -r["total"])
    print(f"  {'config':<30}{'n':>7}{'hit%':>8}{'stop%':>8}{'mean':>10}"
          f"{'total':>11}{'maxDD':>9}{'t':>7}")
    for a in res[:8]:
        print(f"  {a['lbl']:<30}{a['n']:>7}{a['hit']:>8.1%}{a['stopped']:>8.1%}"
              f"{a['mean']*100:>9.3f}%{a['total']*100:>10,.0f}%{a['dd']*100:>8.1f}%"
              f"{a['t']:>7.2f}")
    pos = [r for r in res if r["total"] > 0]
    sig = [r for r in res if r["t"] > 2]
    print(f"\n  configurations tested: {len(res)}")
    print(f"  with positive total return: {len(pos)}  ({len(pos)/len(res):.0%})")
    print(f"  with t > 2: {len(sig)}  (about {0.025*len(res):.0f} expected by chance)")


if __name__ == "__main__":
    main()
