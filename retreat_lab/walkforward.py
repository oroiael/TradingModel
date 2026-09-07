"""The RV20 overnight filter with a walk-forward threshold.

The filter as reported used a percentile computed from the WHOLE sample: at any
night it implicitly knew where that night's volatility would rank against
volatility that had not happened yet. RV20 itself was always trailing, but the
cut was not, and that is look-ahead.

This rebuilds it with no forward information anywhere:

  threshold(i) = the p-th percentile of {RV20(j) : j in a window strictly BEFORE i}
  trade night i only if RV20(i) < threshold(i)

Windows tested: expanding (all history so far), rolling 252 and rolling 504
sessions. A burn-in of 252 sessions passes before the first trade, so early
thresholds are not built on a handful of observations.

Everything is compared over the SAME post-burn-in nights, because a strategy that
sits out 2020 is not comparable to one that does not.

Usage:  python3 retreat_lab/walkforward.py [bps_per_side]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
BURN = 252


def load():
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
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
    s = sorted(xs)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def met(rs, yrs):
    if len(rs) < 20:
        return None
    eq = 1.0; pk = 1.0; dd = 0.0
    for x in rs:
        eq *= (1 + x); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    sd = stdev(rs)
    return dict(n=len(rs), total=eq - 1, cagr=eq ** (1 / yrs) - 1 if eq > 0 else -1,
                dd=dd, sh=mean(rs) / sd * ((len(rs) / yrs) ** 0.5) if sd else 0,
                t=mean(rs) / (sd / len(rs) ** 0.5), mean=mean(rs))


def row(lbl, m):
    if not m:
        print(f"  {lbl:<34} (thin)"); return
    print(f"  {lbl:<34}{m['n']:>7}{m['total']*100:>12,.0f}%{m['cagr']*100:>9.1f}%"
          f"{m['dd']*100:>9.1f}%{m['sh']:>8.2f}{m['mean']*100:>9.3f}%{m['t']:>7.2f}")


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
    yrs = (days[live[-1][0]] - days[live[0][0]]).days / 365.25
    print(f"SOXL overnight, walk-forward threshold, {COST:.1f} bps/side")
    print(f"burn-in {BURN} sessions; live window {days[live[0][0]]} → "
          f"{days[live[-1][0]]} ({yrs:.1f}y, {len(live)} nights)\n")
    hdr = (f"  {'strategy':<34}{'n':>7}{'total':>12}{'CAGR':>9}{'maxDD':>9}"
           f"{'Sharpe':>8}{'mean/nt':>9}{'t':>7}")
    print(hdr)
    row("hold every night (no filter)", met([r for _, r in live], yrs))

    # in-sample fitted cut, for the bias it introduces
    allv = [rv[i] for i, _ in nights]
    for p in (40, 60, 80):
        thr = pctile(allv, p)
        row(f"IN-SAMPLE cut at p{p}",
            met([r for i, r in live if rv[i] < thr], yrs))

    print()
    for wname, w in (("expanding", None), ("rolling 252", 252), ("rolling 504", 504)):
        for p in (40, 60, 80):
            sel = []
            for i, r in live:
                hist = [rv[j] for j in sorted(rv) if j < i] if w is None else \
                       [rv[j] for j in sorted(rv) if i - w <= j < i]
                if len(hist) < 60:
                    continue
                if rv[i] < pctile(hist, p):
                    sel.append(r)
            row(f"WALK-FWD {wname}, p{p}", met(sel, yrs))
        print()

    # single clean out-of-sample split
    print("=" * 104)
    print("SINGLE SPLIT — threshold fitted on the first half, applied to the second")
    print("=" * 104)
    mid = live[len(live) // 2][0]
    fit = [rv[i] for i, _ in nights if i < mid]
    oos = [(i, r) for i, r in live if i >= mid]
    yo = (days[oos[-1][0]] - days[oos[0][0]]).days / 365.25
    print(hdr)
    row("2nd half, hold every night", met([r for _, r in oos], yo))
    for p in (40, 60, 80):
        thr = pctile(fit, p)
        row(f"2nd half, cut fitted on 1st (p{p})",
            met([r for i, r in oos if rv[i] < thr], yo))
    print(f"\n  thresholds fitted on the first half: "
          + ", ".join(f"p{p}={pctile(fit,p):.0f}%" for p in (40, 60, 80)))
    print(f"  the same percentiles of the SECOND half: "
          + ", ".join(f"p{p}={pctile([rv[i] for i,_ in oos],p):.0f}%" for p in (40, 60, 80)))


if __name__ == "__main__":
    main()
