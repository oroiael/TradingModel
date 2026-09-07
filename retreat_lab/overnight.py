"""Backtesting the overnight-only strategy the decomposition surfaced.

backtest.py found SOXL's 6.6 years split into +62.3%/yr overnight and -19.1%/yr
intraday. That decomposition is arithmetic, not a strategy: it assumes costless
round trips at prints you may not get. This turns it into a strategy and charges
it properly.

  buy   at the session close on day D
  sell  at the open of day D+1 (several exit variants, since "the open" is the
        single most contestable price in the whole idea)
  flat  all day, every day

251 round trips a year against the 1,066 the trigger strategy needed, so costs
bite ~4x less -- but they still bite, and the overnight leg carries the entire
gap tail, including the -21.6% night of 2026-06-22.

Usage:  python3 retreat_lab/overnight.py [bps_per_side]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, pct

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0


def load():
    bars = []
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            bars.append((t, float(Decimal(a[1])), float(Decimal(a[4]))))  # ts, open, close
    return bars


def sessions(bars):
    """-> ordered list of (date, first_idx, last_idx)."""
    out, d0 = [], 0
    for i in range(1, len(bars)):
        if bars[i][0].date() != bars[i - 1][0].date():
            out.append((bars[d0][0].date(), d0, i - 1)); d0 = i
    out.append((bars[d0][0].date(), d0, len(bars) - 1))
    return out


def curve(rets, yrs, per_yr):
    eq = 1.0; pk = 1.0; dd = 0.0
    for r in rets:
        eq *= (1 + r); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    sh = (mean(rets) / stdev(rets) * (per_yr ** 0.5)) if len(rets) > 1 and stdev(rets) else 0
    return dict(total=eq - 1, cagr=eq ** (1 / yrs) - 1 if eq > 0 else -1,
                dd=dd, sh=sh, n=len(rets),
                win=sum(1 for r in rets if r > 0) / len(rets),
                worst=min(rets), best=max(rets))


def row(lbl, s):
    print(f"  {lbl:<36}{s['total']*100:>13,.0f}%{s['cagr']*100:>9.1f}%"
          f"{s['dd']*100:>9.1f}%{s['sh']:>8.2f}{s['n']:>7}{s['win']:>7.1%}"
          f"{s['worst']*100:>8.1f}%{s['best']*100:>7.1f}%")


def main():
    bars = load()
    ses = sessions(bars)
    yrs = (bars[-1][0] - bars[0][0]).days / 365.25
    c = COST / 10000.0
    print(f"SOXL 1-min, {bars[0][0]:%Y-%m-%d} → {bars[-1][0]:%Y-%m-%d} "
          f"({yrs:.1f}y, {len(ses)} sessions)")
    print(f"costs: {COST:.1f} bps per side, {COST*2:.1f} bps round trip, "
          f"{len(ses)/yrs:.0f} round trips/yr = {len(ses)/yrs*2*COST/100:.1f}%/yr friction\n")

    # exit variants: "the open" is the contestable price
    variants = {
        "sell at 09:30 open print": lambda i: bars[ses[i + 1][1]][1],
        "sell at 09:30 bar close": lambda i: bars[ses[i + 1][1]][2],
        "sell 5 min after open": lambda i: bars[min(ses[i + 1][1] + 5, ses[i + 1][2])][2],
        "sell 30 min after open": lambda i: bars[min(ses[i + 1][1] + 30, ses[i + 1][2])][2],
        "sell at next close (buy&hold)": lambda i: bars[ses[i + 1][2]][2],
    }
    print(f"  {'strategy':<36}{'total':>13}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}"
          f"{'n':>7}{'win':>7}{'worst':>8}{'best':>7}")
    bh = bars[-1][2] / bars[0][2] - 1
    print(f"  {'buy and hold (no trading)':<36}{bh*100:>13,.0f}%"
          f"{((1+bh)**(1/yrs)-1)*100:>9.1f}%")
    res = {}
    for lbl, ex in variants.items():
        r = [(ex(i) / bars[ses[i][2]][2] - 1) - 2 * c for i in range(len(ses) - 1)]
        res[lbl] = r
        row(lbl, curve(r, yrs, len(ses) / yrs))

    print("\n  --- the same, with zero costs ---")
    for lbl, ex in variants.items():
        r = [ex(i) / bars[ses[i][2]][2] - 1 for i in range(len(ses) - 1)]
        row(lbl + " @0bp", curve(r, yrs, len(ses) / yrs))

    print("\n  --- cost sensitivity, sell at the 09:30 open print ---")
    for cb in (0, 1, 2, 3, 5, 10):
        r = [(bars[ses[i + 1][1]][1] / bars[ses[i][2]][2] - 1) - 2 * cb / 10000.0
             for i in range(len(ses) - 1)]
        s = curve(r, yrs, len(ses) / yrs)
        print(f"    {cb:>2} bps/side  total {s['total']*100:>11,.0f}%   "
              f"CAGR {s['cagr']*100:>6.1f}%   maxDD {s['dd']*100:>6.1f}%   "
              f"Sharpe {s['sh']:>5.2f}")

    print("\n" + "=" * 112)
    print("BY YEAR — sell at the 09:30 open print, 1 bp per side")
    print("=" * 112)
    base = [((bars[ses[i + 1][1]][1] / bars[ses[i][2]][2] - 1) - 2 * c, ses[i][0])
            for i in range(len(ses) - 1)]
    print(f"  {'year':<6}{'nights':>8}{'overnight':>12}{'buy&hold':>12}"
          f"{'intraday':>12}{'worst night':>14}{'win':>8}")
    for y in sorted(set(d.year for _, d in base)):
        rs = [r for r, d in base if d.year == y]
        idx = [i for i in range(len(ses) - 1) if ses[i][0].year == y]
        e = 1.0
        for r in rs:
            e *= (1 + r)
        bh_y = bars[ses[idx[-1] + 1][2]][2] / bars[ses[idx[0]][1]][1] - 1
        ei = 1.0
        for i in idx:
            ei *= (1 + bars[ses[i][2]][2] / bars[ses[i][1]][1] - 1)
        print(f"  {y:<6}{len(rs):>8}{(e-1)*100:>11.1f}%{bh_y*100:>11.1f}%"
              f"{(ei-1)*100:>11.1f}%{min(rs)*100:>13.1f}%"
              f"{sum(1 for r in rs if r>0)/len(rs):>8.1%}")

    print("\n" + "=" * 112)
    print("THE TAIL — ten worst nights (1 bp per side)")
    print("=" * 112)
    for r, d in sorted(base)[:10]:
        print(f"    {d} → next open   {r*100:>7.2f}%")
    rs = [r for r, _ in base]
    print(f"\n  nights worse than -5%: {sum(1 for r in rs if r < -0.05)}   "
          f"worse than -10%: {sum(1 for r in rs if r < -0.10)}   "
          f"p1 {pct(rs,1)*100:.2f}%   p99 {pct(rs,99)*100:.2f}%")
    print(f"  mean {mean(rs)*100:.3f}%/night   sd {stdev(rs)*100:.2f}%   "
          f"skew is the whole risk: best {max(rs)*100:.1f}%, worst {min(rs)*100:.1f}%")


if __name__ == "__main__":
    main()
