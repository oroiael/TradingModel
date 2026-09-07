"""Does holding overnight only when volatility is low improve the strategy?

overnight.py found the overnight leg returns +1,586% but that 20 nights of 1,652
carry all of it, with a -78% drawdown and a -31.2% worst night. The obvious
question is whether a volatility filter keeps the return and drops the tail.

DATA NOTE — the VIX index itself was not obtainable here: it is absent from the
repo, and IBKR returns "Details currently unavailable" for contract 13455763
(index data subscription). Two substitutes are used and reported side by side:

  RV20   SOXL's own trailing 20-session close-to-close realised volatility,
         annualised. Computed from the 1-min file, exact, complete, and more
         directly relevant to a SOXL strategy than S&P implied vol.
  VXXr   VXX divided by its own 60-day moving average. VXX's LEVEL is useless
         across time -- roll decay and reverse splits put 2026's maximum below
         2020's minimum -- but the ratio to its own recent average detrends that
         and tracks the vol regime the way "VIX is high/low" does.

Both are computed strictly through the close of day D and applied to the night
D -> D+1, so there is no look-ahead.

Usage:  python3 retreat_lab/overnight_vol_filter.py [bps_per_side]
"""
import csv, datetime as dt, os, sys, math
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, pct

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


def vxx():
    c = {}
    with open(os.path.join(ROOT, "VXX_5min_6Years.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            c[t.date()] = float(a[4])
    return c


def comp(rs):
    e = 1.0
    for x in rs:
        e *= (1 + x)
    return e


def curve(rs, yrs, per_yr=None):
    """CAGR and Sharpe are over the FULL calendar span, not just the nights the
    filter trades -- a strategy flat 80% of the time cannot claim the compounding
    rate of the 20% it is in. per_yr defaults to this subset's own trade rate."""
    if not rs:
        return None
    eq = 1.0; pk = 1.0; dd = 0.0
    for x in rs:
        eq *= (1 + x); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    rate = per_yr if per_yr else len(rs) / yrs
    sh = mean(rs) / stdev(rs) * (rate ** 0.5) if len(rs) > 1 and stdev(rs) else 0
    return dict(total=eq - 1, cagr=eq ** (1 / yrs) - 1 if eq > 0 and yrs > 0 else -1,
                dd=dd, sh=sh, n=len(rs), win=sum(1 for x in rs if x > 0) / len(rs),
                worst=min(rs), mean=mean(rs), rate=rate)


def row(lbl, s, yrs):
    if not s:
        print(f"  {lbl:<26} (no nights)"); return
    print(f"  {lbl:<26}{s['n']:>7}{s['total']*100:>12,.0f}%{s['cagr']*100:>9.1f}%"
          f"{s['dd']*100:>9.1f}%{s['sh']:>8.2f}{s['win']:>7.1%}{s['worst']*100:>9.1f}%"
          f"{s['mean']*100:>9.3f}%")


def main():
    days, op, cl = soxl()
    vx = vxx()
    c = COST / 10000.0
    yrs = (days[-1] - days[0]).days / 365.25

    # trailing 20-session realised vol of SOXL, through the close of day D
    dret = [cl[days[i]] / cl[days[i - 1]] - 1 for i in range(1, len(days))]
    rv = {}
    for i in range(20, len(days)):
        w = dret[i - 20:i]                       # returns up to and incl. day i
        rv[days[i]] = stdev(w) * (252 ** 0.5) * 100
    # VXX relative to its own 60d MA, through day D
    vd = sorted(vx)
    vr = {}
    for i in range(60, len(vd)):
        ma = mean(vx[vd[j]] for j in range(i - 60, i))
        vr[vd[i]] = vx[vd[i]] / ma

    nights = []
    for i in range(len(days) - 1):
        D, D2 = days[i], days[i + 1]
        nights.append(dict(D=D, r=(op[D2] / cl[D] - 1) - 2 * c,
                           rv=rv.get(D), vr=vr.get(D)))
    print(f"SOXL overnight, {days[0]} → {days[-1]}, {len(nights)} nights, "
          f"{COST:.1f} bps/side")
    print(f"RV20 available on {sum(1 for n in nights if n['rv'] is not None)} nights, "
          f"VXX ratio on {sum(1 for n in nights if n['vr'] is not None)}\n")

    hdr = (f"  {'filter':<26}{'nights':>7}{'total':>12}{'CAGR':>9}{'maxDD':>9}"
           f"{'Sharpe':>8}{'win':>7}{'worst':>9}{'mean/nt':>9}")
    for key, lbl, cuts in (("rv", "SOXL realised vol (RV20)", None),
                           ("vr", "VXX / its 60d average", None)):
        have = [n for n in nights if n[key] is not None]
        vals = sorted(n[key] for n in have)
        qs = [vals[int(len(vals) * q)] for q in (0.2, 0.4, 0.6, 0.8)]
        print("=" * 106); print(f"{lbl}  (quintile breaks: "
                                + ", ".join(f"{q:.2f}" for q in qs) + ")")
        print("=" * 106); print(hdr)
        row("all nights", curve([n["r"] for n in have], yrs), yrs)
        lo = -1e9
        for k, hi in enumerate(qs + [1e9]):
            b = [n["r"] for n in have if lo <= n[key] < hi]
            row(f"  quintile {k+1}"
                + ("  (lowest vol)" if k == 0 else "  (highest vol)" if k == 4 else ""),
                curve(b, yrs), yrs)
            lo = hi
        # the actual strategy: trade only when below a threshold, flat otherwise
        print(f"  --- trade only below the Nth percentile, flat otherwise ---")
        for p in (20, 40, 60, 80):
            thr = vals[int(len(vals) * p / 100)]
            sel = [n["r"] for n in have if n[key] < thr]
            row(f"  below p{p}", curve(sel, yrs), yrs)
        print()

    print("=" * 106)
    print("WHERE THE 20 BEST NIGHTS SIT — the ones carrying the whole return")
    print("=" * 106)
    have = [n for n in nights if n["rv"] is not None]
    vals = sorted(n["rv"] for n in have)
    best = sorted(have, key=lambda n: -n["r"])[:20]
    worst = sorted(have, key=lambda n: n["r"])[:20]
    def q(n):
        return sum(1 for v in vals if v <= n["rv"]) / len(vals) * 100
    print(f"  best 20 nights : median RV20 percentile {sorted(q(n) for n in best)[10]:.0f}"
          f"   in the lowest quintile: {sum(1 for n in best if q(n) < 20)}/20")
    print(f"  worst 20 nights: median RV20 percentile {sorted(q(n) for n in worst)[10]:.0f}"
          f"   in the lowest quintile: {sum(1 for n in worst if q(n) < 20)}/20")
    print(f"  all nights     : median RV20 percentile 50")


if __name__ == "__main__":
    main()
