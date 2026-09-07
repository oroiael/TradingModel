"""Does a volatility filter rescue the intraday leg, either direction?

intraday_short.py found the intraday leg has a POSITIVE arithmetic mean
(+0.0770%/day, +21.4%/yr) and a NEGATIVE geometric one (-17.9%/yr), the gap being
39%/yr of variance drag from a 5.58%-a-day standard deviation. Shorting it is
worse still, because the short flips the mean negative and keeps the drag.

That gives a precise, testable hypothesis rather than a hunch: drag is ~sigma^2/2,
so restricting to low-volatility days should shrink it roughly with the square of
sigma. If the arithmetic mean survives the filter, the geometric mean can flip
positive and the intraday long becomes viable. If the mean shrinks with the vol,
it cannot.

Conditioner is RV20 -- SOXL's own trailing 20-session realised vol through the
close of day D-1, applied to day D, so there is no look-ahead. (Note this differs
from the overnight test, which used RV through day D for the night D->D+1; here
day D's own move must not inform its own filter.) VXX/MA60 is reported alongside.

Usage:  python3 retreat_lab/intraday_vol_filter.py [bps_per_side]
"""
import csv, datetime as dt, os, sys, math
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0


def soxl():
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


def vxxr():
    px = {}
    with open(os.path.join(ROOT, "VXX_5min_6Years.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            px[t.date()] = float(a[4])
    ks = sorted(px); out = {}
    for i in range(60, len(ks)):
        out[ks[i]] = px[ks[i]] / mean(px[ks[j]] for j in range(i - 60, i))
    return out


def comp(rs):
    e = 1.0
    for x in rs:
        e *= (1 + x)
    return e


def stat(rs, yrs):
    if len(rs) < 10:
        return None
    a = mean(rs)
    g = math.exp(mean(math.log(1 + x) for x in rs)) - 1
    e = comp(rs); pk = 1.0; dd = 0.0; cum = 1.0
    for x in rs:
        cum *= (1 + x); pk = max(pk, cum); dd = min(dd, cum / pk - 1)
    sd = stdev(rs)
    return dict(n=len(rs), total=e - 1, arith=a, geo=g, drag=a - g, sd=sd, dd=dd,
                cagr=e ** (1 / yrs) - 1 if e > 0 else -1,
                sh=a / sd * ((len(rs) / yrs) ** 0.5) if sd else 0,
                t=a / (sd / len(rs) ** 0.5))


def row(lbl, s):
    if not s:
        print(f"  {lbl:<26} (too thin)"); return
    print(f"  {lbl:<26}{s['n']:>6}{s['total']*100:>11,.0f}%{s['cagr']*100:>9.1f}%"
          f"{s['arith']*100:>9.4f}%{s['geo']*100:>9.4f}%{s['drag']*100:>8.3f}"
          f"{s['sd']*100:>7.2f}%{s['dd']*100:>9.1f}%{s['t']:>7.2f}")


def main():
    days, op, cl = soxl()
    c = COST / 10000.0
    yrs = (days[-1] - days[0]).days / 365.25
    dret = [cl[days[i]] / cl[days[i - 1]] - 1 for i in range(1, len(days))]
    rv = {}
    for i in range(21, len(days)):
        rv[days[i]] = stdev(dret[i - 21:i - 1]) * (252 ** 0.5) * 100   # through D-1
    vr = vxxr()

    rows = []
    for i in range(len(days)):
        D = days[i]
        g = cl[D] / op[D] - 1
        rows.append(dict(D=D, lo=g - 2 * c, sh=-g - 2 * c,
                         rv=rv.get(D), vr=vr.get(D)))
    print(f"SOXL intraday, {days[0]} → {days[-1]}, {len(rows)} sessions, "
          f"{COST:.1f} bps/side\n")
    hdr = (f"  {'bucket':<26}{'n':>6}{'total':>11}{'CAGR':>9}{'arith':>9}{'geo':>9}"
           f"{'drag':>8}{'sd':>7}{'maxDD':>9}{'t':>7}")

    for key, kl in (("rv", "SOXL realised vol (RV20)"), ("vr", "VXX / its 60d average")):
        have = [r for r in rows if r[key] is not None]
        vals = sorted(r[key] for r in have)
        qs = [vals[int(len(vals) * q)] for q in (0.2, 0.4, 0.6, 0.8)]
        for side, sl in (("lo", "INTRADAY LONG"), ("sh", "INTRADAY SHORT")):
            print("=" * 112)
            print(f"{sl} by {kl}   (quintile breaks "
                  + ", ".join(f"{q:.2f}" for q in qs) + ")")
            print("=" * 112); print(hdr)
            row("all sessions", stat([r[side] for r in have], yrs))
            lo = -1e9
            for k, hi in enumerate(qs + [1e9]):
                b = [r[side] for r in have if lo <= r[key] < hi]
                tag = "  (lowest vol)" if k == 0 else "  (highest vol)" if k == 4 else ""
                row(f"  quintile {k+1}{tag}", stat(b, yrs))
                lo = hi
            print(f"  --- trade only below the Nth percentile ---")
            for p in (20, 40, 60):
                thr = vals[int(len(vals) * p / 100)]
                row(f"  below p{p}", stat([r[side] for r in have if r[key] < thr], yrs))
            print()

    # the mechanism: does the arithmetic mean survive as sigma falls?
    print("=" * 112)
    print("THE MECHANISM — drag falls with sigma^2, but does the mean survive?")
    print("=" * 112)
    have = [r for r in rows if r["rv"] is not None]
    vals = sorted(r["rv"] for r in have)
    qs = [vals[int(len(vals) * q)] for q in (0.2, 0.4, 0.6, 0.8)]
    print(f"  {'quintile':<12}{'sd/day':>9}{'drag=sd^2/2':>14}{'arith mean':>13}"
          f"{'geo mean':>11}{'mean/drag':>11}")
    lo = -1e9
    for k, hi in enumerate(qs + [1e9]):
        b = [r["lo"] for r in have if lo <= r["rv"] < hi]
        s = stat(b, yrs); pred = s["sd"] ** 2 / 2
        print(f"  Q{k+1:<11}{s['sd']*100:>8.2f}%{pred*100:>13.3f}pp"
              f"{s['arith']*100:>12.4f}%{s['geo']*100:>10.4f}%"
              f"{s['arith']/pred:>11.2f}")
        lo = hi
    print("\n  mean/drag > 1 would mean the long survives compounding in that bucket.")


if __name__ == "__main__":
    main()
