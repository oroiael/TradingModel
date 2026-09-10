"""Absolute vs relative volatility cut -- does the SOXL threshold port to FAS?

The SOXL walk-forward concluded the overnight vol filter tracks ABSOLUTE
volatility, not relative: an expanding-window (absolute-memory) threshold
worked, a rolling (relative-to-recent) one was worse than no filter at all.

That claim makes a hard prediction. If the effect is absolute, SOXL's own cut
-- RV20 below 107.6% annualised -- should carry to any instrument unchanged.
If instead it is relative, the p60 of each instrument's OWN distribution should
be what carries.

This runs both parameterizations on both instruments, on identical terms, and
prints where each instrument's distribution actually sits.

Usage:  python3 retreat_lab/abs_threshold.py [bps_per_side]
"""
import csv, datetime as dt, math, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0


def daily(sym):
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, f"{sym}_1min.csv")) as f:
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


def rank_of(xs, v):
    return 100.0 * sum(1 for x in xs if x < v) / len(xs)


def build(sym):
    d, o, c = daily(sym)
    cst = COST / 10000.0
    dret = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    rows = []
    for i in range(20, len(d) - 1):
        rv = stdev(dret[i - 20:i]) * (252 ** 0.5) * 100
        rows.append((d[i], rv, (o[d[i + 1]] / c[d[i]] - 1) - 2 * cst))
    yrs = (rows[-1][0] - rows[0][0]).days / 365.25
    return rows, yrs


def score(sel, yrs, n_all):
    if not sel:
        return None
    g = math.prod(1 + r for r in sel) - 1
    eq, pk, dd = 1.0, 1.0, 0.0
    for r in sel:
        eq *= 1 + r; pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    m, s = mean(sel), (stdev(sel) if len(sel) > 1 else 0.0)
    ann = len(sel) / yrs
    return dict(n=len(sel), pct=100.0 * len(sel) / n_all, total=g * 100,
                cagr=((1 + g) ** (1 / yrs) - 1) * 100, dd=dd * 100,
                sharpe=(m / s * (ann ** 0.5)) if s else 0.0,
                t=(m / (s / len(sel) ** 0.5)) if s else 0.0)


def line(lbl, r):
    if r is None:
        print(f"  {lbl:<40}{'no nights selected':>50}")
        return
    print(f"  {lbl:<40}{r['n']:>6}{r['pct']:>7.1f}%{r['total']:>10.0f}%"
          f"{r['cagr']:>8.1f}%{r['dd']:>8.1f}%{r['sharpe']:>8.2f}{r['t']:>7.2f}")


def main():
    print(f"absolute vs relative volatility cut, {COST:.1f} bps/side\n")
    data = {s: build(s) for s in ("SOXL", "FAS")}
    SOXL_ABS = pctile([r[1] for r in data["SOXL"][0]], 60)

    print("  WHERE EACH DISTRIBUTION SITS (RV20, annualised %)")
    print(f"  {'symbol':<10}{'p20':>8}{'p40':>8}{'p50':>8}{'p60':>8}{'p80':>8}"
          f"{'max':>8}{'SOXL p60 ranks at':>20}")
    for s in ("SOXL", "FAS"):
        rv = [r[1] for r in data[s][0]]
        print(f"  {s:<10}" + "".join(f"{pctile(rv,p):>8.1f}" for p in (20,40,50,60,80))
              + f"{max(rv):>8.1f}{rank_of(rv, SOXL_ABS):>19.1f}%")
    print(f"\n  SOXL's p60 cut = RV20 below {SOXL_ABS:.1f}% annualised.\n")

    for s in ("SOXL", "FAS"):
        rows, yrs = data[s]
        rv = [r[1] for r in rows]
        print("=" * 104)
        print(f"{s} — {rows[0][0]} → {rows[-1][0]} ({yrs:.1f}y, {len(rows)} nights)")
        print("=" * 104)
        print(f"  {'rule':<40}{'n':>6}{'kept':>8}{'total':>10}{'CAGR':>8}"
              f"{'maxDD':>8}{'Sharpe':>8}{'t':>7}")
        line("hold every night", score([r[2] for r in rows], yrs, len(rows)))
        line(f"ABSOLUTE: RV20 < {SOXL_ABS:.1f}% (SOXL's cut)",
             score([r[2] for r in rows if r[1] < SOXL_ABS], yrs, len(rows)))
        own = pctile(rv, 60)
        line(f"RELATIVE: RV20 < own p60 ({own:.1f}%)",
             score([r[2] for r in rows if r[1] < own], yrs, len(rows)))
        print()

    print("=" * 104)
    print("READ")
    print("=" * 104)
    rvF = [r[1] for r in data["FAS"][0]]
    kept = 100.0 * sum(1 for x in rvF if x < SOXL_ABS) / len(rvF)
    print(f"  SOXL's absolute cut keeps {kept:.1f}% of FAS nights — it is above FAS's")
    print(f"  {rank_of(rvF, SOXL_ABS):.0f}th percentile, so as a filter on FAS it is")
    print(f"  nearly a no-op: it cannot discriminate on a distribution that sits")
    print(f"  almost entirely beneath it. The absolute reading of the SOXL result")
    print(f"  therefore makes no usable prediction for FAS, and the relative one")
    print(f"  has to be judged on FAS's own numbers above.")


if __name__ == "__main__":
    main()
