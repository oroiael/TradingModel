"""SOXL + TQQQ + SPXL as a basket. Fixed weights, or managed allocation?

The p60 rule is already a per-instrument on/off switch, so "fixed vs dynamic"
is really two questions:

  ELIGIBILITY  which legs are allowed to trade tonight (the existing RV20 rule)
  ALLOCATION   how capital is split across whichever legs are eligible

Six allocation policies are tested against the same eligibility rule:

  1. fixed 1/3, ungated        no filter at all -- the naive basket
  2. fixed 1/3, gated          1/3 per eligible leg; capital idles when a leg is off
  3. renormalised              split evenly across eligible legs, always fully deployed
  4. inverse-vol               split across eligible legs in proportion to 1/RV20
  5. breadth >= 2              trade only when at least 2 of 3 are eligible
  6. concentrate               hold only the single lowest-RV20 eligible leg

The threshold is walk-forward: at each night it is the p60 of that instrument's
own RV20 history strictly BEFORE that night. The backtest window starts in 2023
but the estimator is allowed the 2021-22 history that precedes it -- that is a
warm start, not look-ahead.

Costs: 1 bp/side on deployed notional. Splitting one unit of capital three ways
does not multiply the cost, since total turnover is unchanged; per-ticket
commissions are not modelled and are small relative to this at any real size.

Usage:  python3 retreat_lab/basket.py [bps_per_side] [start_year]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = (float(sys.argv[1]) if len(sys.argv) > 1 else 1.0) / 10000.0
START = int(sys.argv[2]) if len(sys.argv) > 2 else 2023
LEGS = [("SOXL", "SOXL_1min.csv"), ("TQQQ", "retreat_lab/out/TQQQ_daily_ibkr.csv"),
        ("SPXL", "SPXL_5min_6Years.csv")]


def load(path):
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, path)) as f:
        r = csv.reader(f); next(r)
        for a in r:
            s = a[0].replace(" America/New_York", "")
            try:
                k = dt.datetime.strptime(s, "%Y%m%d %H:%M:%S").date()
            except ValueError:
                k = dt.date.fromisoformat(s[:10])
            if k not in o:
                o[k] = float(a[1]); d.append(k)
            c[k] = float(a[4])
    return d, o, c


def build(path):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    out = {}
    hist = []
    for i in range(20, len(d) - 1):
        rv = stdev(dr[i - 20:i]) * (252 ** 0.5) * 100
        out[d[i]] = dict(rv=rv, on=o[d[i + 1]] / c[d[i]] - 1, hist=len(hist))
        hist.append(rv)
    return out, sorted(out)


def pctile(xs, p):
    s = sorted(xs); k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def curve(rets, yrs):
    g = math.prod(1 + v for v in rets) - 1
    eq = pk = 1.0; dd = 0.0
    for v in rets:
        eq *= 1 + v; pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    m, s = mean(rets), stdev(rets)
    return (g * 100, ((1 + g) ** (1 / yrs) - 1) * 100, dd * 100,
            m / s * (len(rets) / yrs) ** 0.5 if s else 0.0,
            m / (s / len(rets) ** 0.5) if s else 0.0)


def main():
    D, ORD = {}, {}
    for sym, path in LEGS:
        m, days = build(path)
        D[sym] = m; ORD[sym] = days
    # walk-forward eligibility: p60 of that leg's OWN prior RV20 history
    elig = {}
    for sym in D:
        days = ORD[sym]; hist = []
        e = {}
        for d in days:
            rv = D[sym][d]["rv"]
            e[d] = (len(hist) >= 60 and rv < pctile(hist, 60))
            hist.append(rv)
        elig[sym] = e
    common = sorted(set.intersection(*[set(D[s]) for s in D]))
    W = [d for d in common if d.year >= START]
    ALL = common
    syms = [s for s, _ in LEGS]

    def run(policy, days):
        yrs = (days[-1] - days[0]).days / 365.25
        rets, dep = [], []
        for d in days:
            ok = [s for s in syms if elig[s][d]]
            w = {s: 0.0 for s in syms}
            if policy == "ungated":
                for s in syms:
                    w[s] = 1 / 3
            elif policy == "gated":
                for s in ok:
                    w[s] = 1 / 3
            elif policy == "renorm" and ok:
                for s in ok:
                    w[s] = 1 / len(ok)
            elif policy == "invvol" and ok:
                iv = {s: 1.0 / D[s][d]["rv"] for s in ok}
                tt = sum(iv.values())
                for s in ok:
                    w[s] = iv[s] / tt
            elif policy == "breadth2" and len(ok) >= 2:
                for s in ok:
                    w[s] = 1 / len(ok)
            elif policy == "concentrate" and ok:
                w[min(ok, key=lambda s: D[s][d]["rv"])] = 1.0
            elif policy.startswith("w:") and ok:
                a, b, c = (float(x) / 100.0 for x in policy[2:].split("/"))
                base = {"SOXL": a, "TQQQ": b, "SPXL": c}
                tt = sum(base[s] for s in ok)
                if tt > 0:
                    for s in ok:
                        w[s] = base[s] / tt
            elif policy.startswith("tilt") and ok:
                a = float(policy[4:]) / 100.0           # SOXL target weight
                base = {"SOXL": a, "TQQQ": (1 - a) / 2, "SPXL": (1 - a) / 2}
                tt = sum(base[s] for s in ok)
                if tt > 0:                              # renormalised over eligible
                    for s in ok:
                        w[s] = base[s] / tt
            tot = sum(w.values())
            rets.append(sum(w[s] * D[s][d]["on"] for s in syms) - tot * 2 * COST)
            dep.append(tot)
        return curve(rets, yrs), mean(dep), rets

    print(f"basket backtest, {COST*1e4:.0f} bp/side, walk-forward p60 per leg")
    print(f"window {W[0]} → {W[-1]}  ({len(W)} sessions, "
          f"{(W[-1]-W[0]).days/365.25:.1f}y)\n")

    print("  nightly eligibility (how often each leg is allowed to trade)")
    for s in syms:
        print(f"    {s:<6}{sum(1 for d in W if elig[s][d])/len(W)*100:>5.0f}% of nights")
    from collections import Counter
    cnt = Counter(sum(1 for s in syms if elig[s][d]) for d in W)
    print(f"    legs eligible per night: " +
          "  ".join(f"{k}:{cnt[k]/len(W)*100:.0f}%" for k in sorted(cnt)))

    print("\n  correlation of the three filtered overnight streams (eligible nights only)")
    print(f"  {'':<8}" + "".join(f"{s:>8}" for s in syms))
    for a in syms:
        row = f"  {a:<8}"
        for b in syms:
            x = [D[a][d]["on"] for d in W if elig[a][d] and elig[b][d]]
            y = [D[b][d]["on"] for d in W if elig[a][d] and elig[b][d]]
            if len(x) < 10:
                row += f"{'--':>8}"; continue
            ma, mb = mean(x), mean(y)
            c = (sum((p - ma) * (q - mb) for p, q in zip(x, y))
                 / ((sum((p - ma) ** 2 for p in x) * sum((q - mb) ** 2 for q in y)) ** 0.5))
            row += f"{c:>8.2f}"
        print(row)

    for lbl, days in ((f"FROM {START}", W), ("INCLUDING 2022 (for comparison)", ALL)):
        print(f"\n{'='*100}\n{lbl}   {days[0]} → {days[-1]}  ({len(days)} sessions)\n{'='*100}")
        print(f"  {'policy':<34}{'total':>10}{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}"
              f"{'t':>7}{'avg deployed':>14}")
        yrs = (days[-1] - days[0]).days / 365.25
        for s in syms:
            sel = [D[s][d]["on"] - 2 * COST for d in days if elig[s][d]]
            g, cg, dd, sh, t = curve(sel, yrs)
            print(f"  {s + ' alone (filtered)':<34}{g:>9.0f}%{cg:>7.1f}%{dd:>7.1f}%"
                  f"{sh:>8.2f}{t:>7.2f}{len(sel)/len(days)*100:>13.0f}%")
        print(f"  {'-'*92}")
        for pol, name in (("ungated", "1. fixed 1/3, NO filter"),
                          ("gated", "2. fixed 1/3, gated"),
                          ("renorm", "3. renormalised across eligible"),
                          ("invvol", "4. inverse-vol across eligible"),
                          ("breadth2", "5. breadth >= 2 legs"),
                          ("concentrate", "6. concentrate in lowest RV20"),
                          ("w:60/30/10", "7. 60/30/10 SOXL/TQQQ/SPXL")):
            (g, cg, dd, sh, t), dep, _ = run(pol, days)
            print(f"  {name:<34}{g:>9.0f}%{cg:>7.1f}%{dd:>7.1f}%{sh:>8.2f}{t:>7.2f}"
                  f"{dep*100:>13.0f}%")
        if days is W:
            pols = [("w:60/30/10", "60/30/10"), ("w:100/0/0", "SOXL only"),
                    ("renorm", "equal 1/3"), ("ungated", "1/3 no filter")]
            print(f"\n  YEAR BY YEAR — % return (2026 is partial, to {days[-1]})")
            ser = yearly(run, syms, D, elig, days, pols)
            print(f"\n  {'policy':<16}{'worst DD in year':>60}")
            print(f"  {'':<16}" + "".join(f"{y:>10}" for y in
                                          sorted({d.year for d in days})))
            for pol, n in pols:
                _, _, by = drawdowns(ser, days, n)
                print(f"  {n:<16}" + "".join(
                    f"{by.get(y,0)*100:>9.1f}%" for y in sorted({d.year for d in days})))
            print(f"\n  {'policy':<16}{'nights with each leg on (60/30/10 weights)':>50}")
            for s_ in syms:
                print(f"    {s_:<6}{sum(1 for d in days if elig[s_][d])/len(days)*100:>5.0f}%"
                      f" of nights eligible")
        print(f"  {'-'*92}")
        print(f"  SOXL TILT (renormalised over eligible legs)")
        for a in (33, 50, 60, 70, 80, 100):
            (g, cg, dd, sh, t), dep, _ = run(f"tilt{a}", days)
            star = "  <-- best Sharpe of the tilts" if False else ""
            print(f"  {f'   {a}% SOXL / {(100-a)//2}% each other':<34}{g:>9.0f}%{cg:>7.1f}%"
                  f"{dd:>7.1f}%{sh:>8.2f}{t:>7.2f}{dep*100:>13.0f}%{star}")


def yearly(run, syms, D, elig, days, policies):
    """Year-by-year return for each policy, plus per-leg contribution."""
    import itertools
    yrs = sorted({d.year for d in days})
    series = {}
    for pol, name in policies:
        _, _, rets = run(pol, days)
        series[name] = dict(zip(days, rets))
    print(f"\n  {'year':<6}{'sessions':>10}" +
          "".join(f"{n.split('.')[0][:14]:>16}" for _, n in policies))
    for y in yrs:
        dd = [d for d in days if d.year == y]
        row = f"  {y:<6}{len(dd):>10}"
        for _, n in policies:
            g = math.prod(1 + series[n][d] for d in dd) - 1
            row += f"{g*100:>15.1f}%"
        print(row)
    print(f"  {'-'*(16+len(policies)*16)}")
    row = f"  {'ALL':<6}{len(days):>10}"
    for _, n in policies:
        g = math.prod(1 + series[n][d] for d in days) - 1
        row += f"{g*100:>15.1f}%"
    print(row)
    return series


def drawdowns(series, days, name):
    eq = pk = 1.0; dd = 0.0; worst = None
    by = {}
    for d in days:
        eq *= 1 + series[name][d]
        pk = max(pk, eq)
        x = eq / pk - 1
        if x < dd:
            dd = x; worst = d
        by[d.year] = min(by.get(d.year, 0.0), x)
    return dd, worst, by


if __name__ == "__main__":
    main()
