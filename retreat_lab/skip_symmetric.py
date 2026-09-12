"""Skip after a big intraday GAIN as well as a big loss — on p60.

The down-day rule came out of a coarse five-bucket table where the <-3% bucket
stood out. The same table showed the >+3% bucket at +0.373%, roughly in line
with everything else, so a priori the up side does not look promising. This
tests it properly rather than inferring from five buckets, and tests both tails
together.

Multiple comparisons are tracked and reported: this lab has now run many
threshold searches over one 5.5-year sample, and the honest way to read a new
marginal result is against the number of chances it had to appear.

Usage:  python3 retreat_lab/skip_symmetric.py [bps_per_side] [capital] [fraction]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, BARS, SYMBOL

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
CAP = float(sys.argv[2]) if len(sys.argv) > 2 else 100_000.0
F = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
BURN = 252


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
    return dict(final=eq, cagr=(eq / cap) ** (1 / yrs) - 1 if eq > 0 else -1,
                dd=dd, n=len(rets), mean=mean(rets) if rets else 0,
                sh=(mean(rets) / sd * ((len(rets) / yrs) ** 0.5)) if sd else 0,
                t=(mean(rets) / (sd / len(rets) ** 0.5)) if sd else 0)


def row(lbl, m, base=None):
    d = ""
    if base:
        d = f"{m['sh']-base['sh']:>+8.2f}"
    print(f"  {lbl:<28}{m['n']:>7}{m['final']:>12,.0f}{m['cagr']*100:>8.1f}%"
          f"{m['dd']*100:>8.1f}%{m['sh']:>8.2f}{m['t']:>7.2f}{d}")


def main():
    days, op, cl = daily(BARS)
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
            sel.append((days[i], r, cl[days[i]] / op[days[i]] - 1))
    yrs = (days[live[-1][0]] - days[live[0][0]]).days / 365.25
    print(f"p60 overnight, f={F:.2f}, ${CAP:,.0f}, {COST:.1f} bps/side, "
          f"{len(sel)} nights, {yrs:.1f}y\n")

    # the raw picture, finer buckets than the original five
    print("=" * 104)
    print("MEAN OVERNIGHT RETURN BY THAT DAY'S INTRADAY MOVE — finer buckets")
    print("=" * 104)
    print(f"  {'bucket':<18}{'nights':>8}{'mean':>10}{'sd':>9}{'t vs rest':>12}")
    edges = [(-1, -0.05), (-0.05, -0.03), (-0.03, -0.01), (-0.01, 0.01),
             (0.01, 0.03), (0.03, 0.05), (0.05, 1)]
    for lo, hi in edges:
        b = [r for _, r, g in sel if lo <= g < hi]
        o_ = [r for _, r, g in sel if not (lo <= g < hi)]
        if len(b) < 15:
            continue
        t_ = (mean(b) - mean(o_)) / ((stdev(b)**2/len(b) + stdev(o_)**2/len(o_))**0.5)
        lbl = f"{lo:+.0%} to {hi:+.0%}" if abs(lo) < 1 and abs(hi) < 1 else \
              (f"below {hi:+.0%}" if lo == -1 else f"above {lo:+.0%}")
        print(f"  {lbl:<18}{len(b):>8}{mean(b)*100:>9.3f}%{stdev(b)*100:>8.2f}%"
              f"{t_:>12.2f}")

    tests = 0
    base = perf([r for _, r, _ in sel], yrs)
    print("\n" + "=" * 104)
    print("SKIP AFTER A BIG INTRADAY GAIN")
    print("=" * 104)
    print(f"  {'rule':<28}{'nights':>7}{'final':>12}{'CAGR':>9}{'maxDD':>9}"
          f"{'Sharpe':>8}{'t':>7}{'dSharpe':>8}")
    row("p60 only", base)
    for thr in (0.02, 0.03, 0.04, 0.05, 0.07):
        tests += 1
        row(f"skip after > +{thr:.0%}",
            perf([r for _, r, g in sel if g <= thr], yrs), base)

    print("\n" + "=" * 104)
    print("SKIP BOTH TAILS")
    print("=" * 104)
    print(f"  {'rule':<28}{'nights':>7}{'final':>12}{'CAGR':>9}{'maxDD':>9}"
          f"{'Sharpe':>8}{'t':>7}{'dSharpe':>8}")
    row("p60 only", base)
    tests += 1
    row("skip < -3% (the known rule)",
        perf([r for _, r, g in sel if g >= -0.03], yrs), base)
    for d_, u in ((0.03, 0.03), (0.03, 0.05), (0.04, 0.04), (0.04, 0.05),
                  (0.05, 0.05)):
        tests += 1
        row(f"skip |move| > {d_:.0%}/{u:.0%}" if d_ != u else f"skip |move| > {d_:.0%}",
            perf([r for _, r, g in sel if -d_ <= g <= u], yrs), base)

    print("\n" + "=" * 104)
    print("SPLIT-SAMPLE on the best up-side rule found")
    print("=" * 104)
    cands = []
    for thr in (0.02, 0.03, 0.04, 0.05, 0.07):
        m = perf([r for _, r, g in sel if g <= thr], yrs)
        cands.append((m["sh"], thr, m))
    cands.sort(reverse=True)
    bsh, bthr, bm = cands[0]
    print(f"  best up-side threshold by Sharpe: skip after > +{bthr:.0%} "
          f"(Sharpe {bsh:.2f} vs {base['sh']:.2f} baseline)")
    mid = sel[len(sel) // 2][0]
    print(f"  {'half':<14}{'variant':<24}{'nights':>8}{'mean/nt':>10}{'t':>7}")
    for lbl, f_ in (("first", lambda d: d <= mid), ("second", lambda d: d > mid)):
        seg = [(r, g) for d, r, g in sel if f_(d)]
        for nm, rs in (("p60 only", [r for r, _ in seg]),
                       (f"p60 + skip > +{bthr:.0%}", [r for r, g in seg if g <= bthr])):
            m = perf(rs, yrs * len(seg) / len(sel))
            print(f"  {lbl:<14}{nm:<24}{m['n']:>8}{m['mean']*100:>9.3f}%{m['t']:>7.2f}")

    print(f"\n  thresholds tested in THIS script: {tests}")
    print("  thresholds tested across this lab on the same 5.5 years: well over 100")
    print("  (6 retreat pairs, 4 percentiles, 3 windows, 6 down-skips, 5 up-skips,")
    print("   5 both-tail combinations, 1,024 bracket configs, 200 take-profit configs)")
    print("  At that width roughly 1 in 20 tests clears t=2 by chance alone, so a new")
    print("  rule needs to clear it in BOTH halves and by a wide margin to mean anything.")


if __name__ == "__main__":
    main()
