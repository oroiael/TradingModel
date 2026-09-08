"""p60 overnight at f=0.5, plus: skip the night after a big intraday down day.

The rule is implementable with no look-ahead -- entry is at 15:59 and the day's
open-to-close move is known by then.

IMPORTANT: the -3% threshold was found by inspecting this same data (the bucket
boundaries -3/-1/+1/+3 were chosen, then the bottom bucket noticed). So it is a
fitted rule and this script treats it as a hypothesis to be attacked, not a
result: threshold sensitivity, split-sample, and a count of how few nights it
actually removes.

Usage:  python3 retreat_lab/skip_rule.py [bps_per_side] [capital] [fraction]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
CAP = float(sys.argv[2]) if len(sys.argv) > 2 else 100_000.0
F = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
BURN = 252
OUT = os.path.join(ROOT, "retreat_lab/out")


def daily(name):
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, name)) as f:
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


def perf(rets, yrs, f=F, cap=CAP):
    eq = cap; pk = cap; dd = 0.0
    for r in rets:
        eq *= (1 + f * r); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    sd = stdev(rets) if len(rets) > 1 else 0
    return dict(final=eq, total=eq / cap - 1,
                cagr=(eq / cap) ** (1 / yrs) - 1 if eq > 0 else -1, dd=dd,
                n=len(rets), mean=mean(rets) if rets else 0,
                sh=(mean(rets) / sd * ((len(rets) / yrs) ** 0.5)) if sd else 0,
                t=(mean(rets) / (sd / len(rets) ** 0.5)) if sd else 0)


def main():
    days, op, cl = daily("SOXL_1min.csv")
    c = COST / 10000.0
    dret = [cl[days[i]] / cl[days[i - 1]] - 1 for i in range(1, len(days))]
    rv = {}
    for i in range(20, len(days)):
        rv[i] = stdev(dret[i - 20:i]) * (252 ** 0.5) * 100
    nights = [(i, (op[days[i + 1]] / cl[days[i]] - 1) - 2 * c)
              for i in range(len(days) - 1) if i in rv]
    first = nights[0][0]
    live = [(i, r) for i, r in nights if i >= first + BURN]
    sel = []
    for i, r in live:
        h = [rv[j] for j in sorted(rv) if j < i]
        if len(h) >= 60 and rv[i] < pctile(h, 60):
            sel.append((i, days[i], r, cl[days[i]] / op[days[i]] - 1))
    yrs = (days[live[-1][0]] - days[live[0][0]]).days / 365.25
    print(f"p60 overnight, f={F:.2f}, ${CAP:,.0f}, {COST:.1f} bps/side, "
          f"{days[live[0][0]]} → {days[live[-1][0]]} ({yrs:.1f}y)\n")

    print("=" * 100)
    print("THRESHOLD SENSITIVITY — skip the night after an intraday move below X")
    print("=" * 100)
    print(f"  {'rule':<26}{'nights':>8}{'skipped':>9}{'final':>13}"
          f"{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}{'t':>7}")
    base = perf([r for _, _, r, _ in sel], yrs)
    print(f"  {'p60 only (no skip)':<26}{base['n']:>8}{0:>9}{base['final']:>12,.0f}"
          f"{base['cagr']*100:>8.1f}%{base['dd']*100:>8.1f}%{base['sh']:>8.2f}"
          f"{base['t']:>7.2f}")
    for thr in (-0.01, -0.02, -0.03, -0.04, -0.05, -0.07):
        keep = [r for _, _, r, g in sel if g >= thr]
        m = perf(keep, yrs)
        print(f"  {'skip after < ' + f'{thr:.0%}':<26}{m['n']:>8}"
              f"{len(sel)-m['n']:>9}{m['final']:>12,.0f}{m['cagr']*100:>8.1f}%"
              f"{m['dd']*100:>8.1f}%{m['sh']:>8.2f}{m['t']:>7.2f}")

    print("\n" + "=" * 100)
    print("DOES IT SURVIVE A SPLIT? — fit nothing, just apply the -3% rule to each half")
    print("=" * 100)
    mid = sel[len(sel) // 2][1]
    print(f"  {'half':<16}{'variant':<20}{'nights':>8}{'mean/nt':>10}"
          f"{'total':>11}{'t':>7}")
    for lbl, f_ in (("first", lambda d: d <= mid), ("second", lambda d: d > mid)):
        seg = [(r, g) for _, d, r, g in sel if f_(d)]
        for nm, rs in (("p60 only", [r for r, _ in seg]),
                       ("p60 + skip -3%", [r for r, g in seg if g >= -0.03])):
            y = yrs * len(seg) / len(sel)
            m = perf(rs, y)
            print(f"  {lbl:<16}{nm:<20}{m['n']:>8}{m['mean']*100:>9.3f}%"
                  f"{m['total']*100:>10.0f}%{m['t']:>7.2f}")

    # ---------- the chosen rule, weekly
    keep = [(i, d, r) for i, d, r, g in sel if g >= -0.03]
    skipped = [(d, r) for _, d, r, g in sel if g < -0.03]
    print(f"\n  what the rule actually removes: {len(skipped)} nights of {len(sel)} "
          f"({len(skipped)/len(sel):.1%})")
    print(f"  those nights averaged {mean(r for _, r in skipped)*100:+.3f}% "
          f"vs {mean(r for _, _, r in keep)*100:+.3f}% for the ones kept")

    allw = sorted({days[i] - dt.timedelta(days=days[i].weekday()) for i, _ in live})
    eq = CAP; pk = CAP; dd = 0.0; rows = []
    t0 = days[live[0][0]]
    for w in allw:
        start = eq; n = 0
        for _, d, r in keep:
            if d - dt.timedelta(days=d.weekday()) == w:
                eq *= (1 + F * r); n += 1
        pk = max(pk, eq); dd = min(dd, eq / pk - 1)
        y = max((w + dt.timedelta(days=4) - t0).days / 365.25, 1 / 365.25)
        rows.append(dict(week_starting=w.isoformat(), nights=n,
                         cash_pnl=round(eq - start, 2), equity=round(eq, 2),
                         week_pct=round((eq / start - 1) * 100, 3),
                         running_cagr_pct=round(((eq / CAP) ** (1 / y) - 1) * 100, 2),
                         drawdown_pct=round((eq / pk - 1) * 100, 2)))
    path = os.path.join(OUT, f"weekly_p60_skip3_f{int(F*100)}.csv")
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        wr.writeheader(); wr.writerows(rows)

    print("\n" + "=" * 100)
    print(f"p60 + SKIP AFTER A -3% DAY, at f={F:.2f}, week by week")
    print("=" * 100)
    pnl = [r["cash_pnl"] for r in rows]
    print(f"  final ${eq:,.0f}   total {(eq/CAP-1)*100:,.0f}%   "
          f"CAGR {((eq/CAP)**(1/yrs)-1)*100:.1f}%   maxDD {dd*100:.1f}%   "
          f"nights {len(keep)}")
    print(f"  weekly cash: median ${median(pnl):,.0f}  mean ${mean(pnl):,.0f}  "
          f"best ${max(pnl):,.0f}  worst ${min(pnl):,.0f}  "
          f"positive {sum(1 for x in pnl if x>0)/len(pnl):.1%}")
    print(f"  {'year':<6}{'cash':>12}{'equity end':>14}{'CAGR':>9}{'worst wk':>12}")
    for y in sorted({dt.date.fromisoformat(r['week_starting']).year for r in rows}):
        yr = [r for r in rows if dt.date.fromisoformat(r['week_starting']).year == y]
        print(f"  {y:<6}{sum(r['cash_pnl'] for r in yr):>11,.0f}"
              f"{yr[-1]['equity']:>14,.0f}{yr[-1]['running_cagr_pct']:>8.1f}%"
              f"{min(r['cash_pnl'] for r in yr):>11,.0f}")
    print(f"\n  wrote {path}")


if __name__ == "__main__":
    main()
