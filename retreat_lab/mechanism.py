"""What is the overnight vol filter actually selecting?

The FAS port failed. That raised the question this script answers: is the SOXL
result a volatility mechanism, a leveraged-ETF structural effect, or directional
exposure to semiconductors wearing a volatility costume?

Three tests, each one falsifying something:

  1. SOXS is -3x the SAME underlying as SOXL. If the overnight premium is
     structural -- something about how leveraged ETFs trade from close to open
     -- SOXS must show it with the SAME sign. If it is directional exposure to
     semis, SOXS must show the MIRROR sign at the same magnitude.

  2. Is the filter picking a higher mean, or just lower variance? Decompose the
     kept/excluded sets into arithmetic mean and 1/2-sigma-squared.

  3. Is RV20 a volatility conditioner or a trend conditioner in disguise?
     Correlate it with trailing return and with drawdown from the 60-day high,
     then substitute each as the conditioner and compare.

Reads SOXL_1min.csv, SOXS_1min.csv and FAS_1min.csv directly -- this is a
cross-instrument test, so it does not use SYMBOL.

Usage:  python3 retreat_lab/mechanism.py [bps_per_side]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = (float(sys.argv[1]) if len(sys.argv) > 1 else 1.0) / 10000.0
SYMS = ("SOXL", "SOXS", "FAS")


def build(sym):
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, f"{sym}_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            k = t.date()
            if k not in o:
                o[k] = float(a[1]); d.append(k)
            c[k] = float(a[4])
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    rows = []
    for i in range(20, len(d) - 1):
        pk = max(c[d[j]] for j in range(max(0, i - 60), i + 1))
        rows.append(dict(date=d[i],
                         rv=stdev(dr[i - 20:i]) * (252 ** 0.5) * 100,
                         mom=c[d[i]] / c[d[i - 20]] - 1,
                         dd=c[d[i]] / pk - 1,
                         on=o[d[i + 1]] / c[d[i]] - 1,
                         idy=c[d[i + 1]] / o[d[i + 1]] - 1))
    return d, o, c, rows


def pctile(xs, p):
    s = sorted(xs); k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def corr(a, b):
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def tstat(x):
    return mean(x) / (stdev(x) / len(x) ** 0.5) if len(x) > 1 else 0.0


def curve(sel, yrs):
    g = math.prod(1 + v for v in sel) - 1
    eq = pk = 1.0; dd = 0.0
    for v in sel:
        eq *= 1 + v; pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    m, s = mean(sel), stdev(sel)
    return g, ((1 + g) ** (1 / yrs) - 1), dd, (m / s * (len(sel) / yrs) ** 0.5)


def main():
    D = {}
    for s in SYMS:
        try:
            D[s] = build(s)
        except FileNotFoundError:
            print(f"  [skip] {s}_1min.csv not present")
    print(f"cross-instrument mechanism test, {COST*1e4:.0f} bps/side\n")

    print("=" * 100)
    print("TEST 1 — SOXS is -3x the SAME underlying. Structural effect, or direction?")
    print("=" * 100)
    print(f"  {'symbol':<8}{'sessions':>10}{'span':>26}{'overnight':>12}"
          f"{'intraday':>11}{'on mean/nt':>13}{'t':>8}")
    for s in D:
        d, o, c, rows = D[s]
        on = math.prod(1 + r["on"] for r in rows) - 1
        iy = math.prod(1 + r["idy"] for r in rows) - 1
        x = [r["on"] for r in rows]
        print(f"  {s:<8}{len(d):>10}{str(d[0]) + ' to ' + str(d[-1]):>26}"
              f"{on*100:>11.0f}%{iy*100:>10.0f}%{mean(x)*100:>12.3f}%{tstat(x):>8.2f}")
    print(f"\n  overnight mean per night by the instrument's OWN RV20 quintile (raw)")
    print(f"  {'symbol':<8}{'Q1 low':>11}{'Q2':>11}{'Q3':>11}{'Q4':>11}{'Q5 high':>11}")
    for s in D:
        rows = D[s][3]; rv = [r["rv"] for r in rows]
        qs = [pctile(rv, p) for p in (20, 40, 60, 80)]
        q = lambda v: next((i for i, t in enumerate(qs) if v < t), 4)
        ms = [mean([r["on"] for r in rows if q(r["rv"]) == i]) for i in range(5)]
        print(f"  {s:<8}" + "".join(f"{m*100:>10.3f}%" for m in ms))
    if "SOXL" in D and "SOXS" in D:
        a = [r["on"] for r in D["SOXL"][3]]
        b = [r["on"] for r in D["SOXS"][3]]
        print(f"\n  SOXL + SOXS overnight means sum to {(mean(a)+mean(b))*100:+.3f}%/night.")
        print("  A structural close-to-open effect would add; a directional one cancels.")

    print("\n" + "=" * 100)
    print("TEST 2 — does the p60 filter raise the MEAN, or only cut VARIANCE?")
    print("=" * 100)
    print(f"  {'symbol':<8}{'set':<12}{'n':>6}{'arith/nt':>12}{'sd/nt':>9}"
          f"{'half-var':>11}{'geo/nt':>11}")
    for s in D:
        rows = D[s][3]; cut = pctile([r["rv"] for r in rows], 60)
        for lbl, sel in (("kept", [r["on"] - 2*COST for r in rows if r["rv"] < cut]),
                         ("excluded", [r["on"] - 2*COST for r in rows if r["rv"] >= cut])):
            m, sd = mean(sel), stdev(sel)
            g = math.prod(1 + v for v in sel) ** (1 / len(sel)) - 1
            print(f"  {s if lbl=='kept' else '':<8}{lbl:<12}{len(sel):>6}{m*100:>11.4f}%"
                  f"{sd*100:>8.3f}%{0.5*sd*sd*100:>10.4f}%{g*100:>10.4f}%")

    print("\n" + "=" * 100)
    print("TEST 3 — is RV20 a volatility conditioner, or a trend conditioner?")
    print("=" * 100)
    for s in D:
        rows = D[s][3]; yrs = len(rows) / 252.0
        rv = [r["rv"] for r in rows]
        print(f"\n  {s}:  corr(RV20, trailing 20d return) = "
              f"{corr(rv,[r['mom'] for r in rows]):+.3f}   "
              f"corr(RV20, drawdown from 60d high) = {corr(rv,[r['dd'] for r in rows]):+.3f}")
        print(f"  {'conditioner (keep 60% of nights)':<36}{'n':>6}{'total':>10}"
              f"{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}{'arith/nt':>11}")
        allr = [r["on"] - 2*COST for r in rows]
        g, cg, dd, sh = curve(allr, yrs)
        print(f"  {'no filter (all nights)':<36}{len(allr):>6}{g*100:>9.0f}%"
              f"{cg*100:>7.1f}%{dd*100:>7.1f}%{sh:>8.2f}{mean(allr)*100:>10.4f}%")
        for name, key, low_good in (("LOW RV20 (the published rule)", "rv", True),
                                    ("HIGH trailing 20d return", "mom", False),
                                    ("SMALL drawdown from 60d high", "dd", False)):
            vals = [r[key] for r in rows]
            cut = pctile(vals, 60 if low_good else 40)
            sel = [r["on"] - 2*COST for r in rows
                   if (r[key] < cut if low_good else r[key] > cut)]
            g, cg, dd, sh = curve(sel, yrs)
            print(f"  {name:<36}{len(sel):>6}{g*100:>9.0f}%{cg*100:>7.1f}%"
                  f"{dd*100:>7.1f}%{sh:>8.2f}{mean(sel)*100:>10.4f}%")


if __name__ == "__main__":
    main()
