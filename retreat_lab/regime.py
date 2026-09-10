"""p80 against p60, and what actually differs between the early and late years.

Two questions:
  1. does a looser cut (p80) hold up where p60 was erratic?
  2. why did 2021-23 and 2024-26 behave so differently?

Both on the OVERNIGHT strategy (buy the close, sell the next open) with a
walk-forward expanding threshold -- no forward information in the cut.

Usage:  python3 retreat_lab/regime.py [bps_per_side]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, BARS, SYMBOL

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
BURN = 252


def load():
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, BARS)) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            k = t.date()
            if k not in o:
                o[k] = float(Decimal(a[1])); d.append(k)
            c[k] = float(Decimal(a[4]))
    return d, o, c


def pctile(xs, p):
    s = sorted(xs); k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def comp(v):
    e = 1.0
    for x in v:
        e *= (1 + x)
    return e


def main():
    days, op, cl = load()
    c = COST / 10000.0
    dret = [cl[days[i]] / cl[days[i - 1]] - 1 for i in range(1, len(days))]
    rv = {}
    for i in range(20, len(days)):
        rv[i] = stdev(dret[i - 20:i]) * (252 ** 0.5) * 100
    nights = [(i, (op[days[i + 1]] / cl[days[i]] - 1) - 2 * c)
              for i in range(len(days) - 1) if i in rv]
    first = nights[0][0]
    live = [(i, r) for i, r in nights if i >= first + BURN]

    sel = {}
    for p in (40, 60, 80):
        s = set()
        for i, _ in live:
            hist = [rv[j] for j in sorted(rv) if j < i]
            if len(hist) >= 60 and rv[i] < pctile(hist, p):
                s.add(i)
        sel[p] = s

    yrs = sorted(set(days[i].year for i, _ in live))
    print("WALK-FORWARD EXPANDING CUTS, year by year — overnight strategy\n")
    print(f"  {'year':<6}{'all':>10}{'p40':>10}{'p60':>10}{'p80':>10}"
          f"{'kept p60':>11}{'kept p80':>11}")
    for y in yrs:
        a = [r for i, r in live if days[i].year == y]
        if len(a) < 20:
            continue
        row = f"  {y:<6}{(comp(a)-1)*100:>9.1f}%"
        for p in (40, 60, 80):
            f_ = [r for i, r in live if days[i].year == y and i in sel[p]]
            row += f"{(comp(f_)-1)*100:>9.1f}%" if f_ else f"{'—':>10}"
        k6 = sum(1 for i, _ in live if days[i].year == y and i in sel[60])
        k8 = sum(1 for i, _ in live if days[i].year == y and i in sel[80])
        row += f"{k6:>7}/{len(a):<3}{k8:>7}/{len(a):<3}"
        print(row)
    print(f"\n  {'FULL':<6}" + f"{(comp([r for _,r in live])-1)*100:>9,.0f}%"
          + "".join(f"{(comp([r for i,r in live if i in sel[p]])-1)*100:>9,.0f}%"
                    for p in (40, 60, 80)))
    for lbl, seg in (("2021-23", [x for x in live if days[x[0]].year <= 2023]),
                     ("2024-26", [x for x in live if days[x[0]].year >= 2024])):
        row = f"  {lbl:<6}" + f"{(comp([r for _,r in seg])-1)*100:>9,.0f}%"
        row += "".join(f"{(comp([r for i,r in seg if i in sel[p]])-1)*100:>9,.0f}%"
                       for p in (40, 60, 80))
        print(row)

    print("\n" + "=" * 100)
    print("WHAT ACTUALLY CHANGED — the overnight return distribution by year")
    print("=" * 100)
    print(f"  {'year':<6}{'nights':>7}{'mean/nt':>10}{'sd/nt':>9}{'win%':>8}"
          f"{'best':>9}{'worst':>9}{'median RV20':>13}{'drag':>8}")
    for y in yrs:
        a = [r for i, r in live if days[i].year == y]
        if len(a) < 20:
            continue
        v = [rv[i] for i, _ in live if days[i].year == y]
        import math
        g = math.exp(mean(math.log(1 + x) for x in a)) - 1
        print(f"  {y:<6}{len(a):>7}{mean(a)*100:>9.3f}%{stdev(a)*100:>8.2f}%"
              f"{sum(1 for x in a if x>0)/len(a):>8.1%}{max(a)*100:>8.1f}%"
              f"{min(a)*100:>8.1f}%{median(v):>12.0f}%{(mean(a)-g)*100:>7.3f}")

    print("\n" + "=" * 100)
    print("IS THE VOL→RETURN RELATIONSHIP STABLE? mean overnight return by RV20 tercile")
    print("(computed within each year, so it is not a level effect)")
    print("=" * 100)
    print(f"  {'year':<6}{'low vol':>12}{'mid':>12}{'high vol':>12}"
          f"{'low-high':>12}{'sign':>8}")
    for y in yrs:
        b = [(rv[i], r) for i, r in live if days[i].year == y]
        if len(b) < 60:
            continue
        b.sort()
        k = len(b) // 3
        lo = mean(r for _, r in b[:k]); mid = mean(r for _, r in b[k:2 * k])
        hi = mean(r for _, r in b[2 * k:])
        print(f"  {y:<6}{lo*100:>11.3f}%{mid*100:>11.3f}%{hi*100:>11.3f}%"
              f"{(lo-hi)*100:>11.3f}%{'low wins' if lo > hi else 'high wins':>12}")


if __name__ == "__main__":
    main()
