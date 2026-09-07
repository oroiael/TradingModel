"""Backtesting the intraday short — the other half of the decomposition.

overnight.py traded the +62.3%/yr leg. This trades the -19.1%/yr one: short at
the session open, cover at the close, flat overnight. Same 251 round trips a
year.

Shorting is not the long leg with a minus sign:
  * returns compound on the negated daily return, so a +180% long year is not a
    -180% short year -- it is bounded below by -100% and gets there fast;
  * borrow must be paid. An intraday-only short is flat at settlement, so on a
    liquid ETF it typically avoids the overnight borrow charge entirely -- but
    locate is not free in stress, so borrow is a parameter here, not an
    assumption;
  * the loss on an up day is unbounded in a way a long's is not.

Usage:  python3 retreat_lab/intraday_short.py [bps_per_side] [borrow_pct_annual]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, pct

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
BORROW = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0     # % / yr while short


def load():
    bars = []
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            bars.append((t, float(Decimal(a[1])), float(Decimal(a[4]))))
    return bars


def sessions(bars):
    out, d0 = [], 0
    for i in range(1, len(bars)):
        if bars[i][0].date() != bars[i - 1][0].date():
            out.append((bars[d0][0].date(), d0, i - 1)); d0 = i
    out.append((bars[d0][0].date(), d0, len(bars) - 1))
    return out


def curve(rets, yrs, per_yr):
    eq = 1.0; pk = 1.0; dd = 0.0; busted = None
    for i, r in enumerate(rets):
        eq *= (1 + r)
        if eq <= 0 and busted is None:
            busted = i
        pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    sh = (mean(rets) / stdev(rets) * (per_yr ** 0.5)) if len(rets) > 1 and stdev(rets) else 0
    return dict(total=eq - 1, cagr=(eq ** (1 / yrs) - 1) if eq > 0 else -1.0,
                dd=dd, sh=sh, n=len(rets), busted=busted,
                win=sum(1 for r in rets if r > 0) / len(rets),
                worst=min(rets), best=max(rets), mean=mean(rets), sd=stdev(rets))


def row(lbl, s):
    b = "  BUSTED" if s["busted"] is not None else ""
    print(f"  {lbl:<34}{s['total']*100:>12,.0f}%{s['cagr']*100:>9.1f}%"
          f"{s['dd']*100:>9.1f}%{s['sh']:>8.2f}{s['win']:>7.1%}"
          f"{s['worst']*100:>8.1f}%{s['best']*100:>7.1f}%{b}")


def main():
    bars = load(); ses = sessions(bars)
    yrs = (bars[-1][0] - bars[0][0]).days / 365.25
    c = COST / 10000.0
    # borrow accrues only while the position is open: ~6.5h of a 24h day
    bday = BORROW / 100.0 / 252.0 * (6.5 / 24.0) if BORROW else 0.0
    print(f"SOXL 1-min, {bars[0][0]:%Y-%m-%d} → {bars[-1][0]:%Y-%m-%d} "
          f"({yrs:.1f}y, {len(ses)} sessions)")
    print(f"costs {COST:.1f} bps/side ({len(ses)/yrs*2*COST/100:.1f}%/yr), "
          f"borrow {BORROW:.1f}%/yr charged only while short\n")

    o = [bars[s[1]][1] for s in ses]          # session open
    cl = [bars[s[2]][2] for s in ses]         # session close
    intr_long = [cl[i] / o[i] - 1 for i in range(len(ses))]
    short = [-(x) - 2 * c - bday for x in intr_long]
    long_ = [x - 2 * c for x in intr_long]
    on = [(o[i + 1] / cl[i] - 1) - 2 * c for i in range(len(ses) - 1)]
    # always-in: short the day, long the night
    both = []
    for i in range(len(ses) - 1):
        both.append(short[i]); both.append(on[i])

    bh = cl[-1] / cl[0] - 1
    print(f"  {'strategy':<34}{'total':>12}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}"
          f"{'win':>7}{'worst':>8}{'best':>7}")
    print(f"  {'buy and hold':<34}{bh*100:>12,.0f}%"
          f"{((1+bh)**(1/yrs)-1)*100:>9.1f}%")
    row("intraday LONG (open→close)", curve(long_, yrs, 252))
    row("intraday SHORT (open→close)", curve(short, yrs, 252))
    row("overnight LONG (close→open)", curve(on, yrs, 252))
    row("short day + long night", curve(both, yrs, 504))

    print("\n  --- cost / borrow sensitivity, intraday short ---")
    for cb in (0, 1, 2, 5):
        for bo in (0, 3, 10):
            bd = bo / 100.0 / 252.0 * (6.5 / 24.0)
            s = curve([-(x) - 2 * cb / 10000.0 - bd for x in intr_long], yrs, 252)
            print(f"    {cb} bps/side + {bo:>2}%/yr borrow:  total {s['total']*100:>9,.0f}%"
                  f"   CAGR {s['cagr']*100:>6.1f}%   maxDD {s['dd']*100:>6.1f}%"
                  f"   Sharpe {s['sh']:>5.2f}")

    print("\n" + "=" * 106)
    print("BY YEAR")
    print("=" * 106)
    print(f"  {'year':<6}{'days':>6}{'intraday short':>16}{'intraday long':>15}"
          f"{'overnight':>12}{'buy&hold':>11}{'worst day':>12}")
    for y in sorted(set(s[0].year for s in ses)):
        ii = [i for i in range(len(ses)) if ses[i][0].year == y]
        if len(ii) < 20:
            continue
        f = lambda rs: (lambda e: (e - 1) * 100)(
            __import__("functools").reduce(lambda a, b: a * (1 + b), rs, 1.0))
        sh_ = [short[i] for i in ii]; lo = [long_[i] for i in ii]
        onn = [on[i] for i in ii if i < len(on)]
        bhy = cl[ii[-1]] / o[ii[0]] - 1
        print(f"  {y:<6}{len(ii):>6}{f(sh_):>15.1f}%{f(lo):>14.1f}%"
              f"{f(onn):>11.1f}%{bhy*100:>10.1f}%{min(sh_)*100:>11.1f}%")

    print("\n" + "=" * 106)
    print("ROBUSTNESS — intraday short")
    print("=" * 106)
    import functools
    comp = lambda rs: functools.reduce(lambda a, b: a * (1 + b), rs, 1.0)
    full = comp(short)
    s_sorted = sorted(short, reverse=True)
    for k in (5, 10, 20, 50):
        print(f"  drop the best {k:>2} days of {len(short)}: "
              f"total {(comp(s_sorted[k:])-1)*100:>9,.0f}%  (from {(full-1)*100:,.0f}%)")
    mid = len(short) // 2
    for lbl, rs in (("first half", short[:mid]), ("second half", short[mid:])):
        e = comp(rs)
        print(f"  {lbl:<12} n={len(rs)}  total {(e-1)*100:>9,.0f}%  "
              f"Sharpe {mean(rs)/stdev(rs)*(252**0.5):>5.2f}  mean {mean(rs)*100:>6.3f}%/day")
    t = mean(short) / (stdev(short) / len(short) ** 0.5)
    print(f"\n  mean {mean(short)*100:.3f}%/day, sd {stdev(short)*100:.2f}%, "
          f"n={len(short)}  ->  t = {t:.2f}")
    print(f"  worst days: " + ", ".join(f"{x*100:.1f}%" for x in sorted(short)[:6]))
    print(f"  days worse than -5%: {sum(1 for x in short if x < -0.05)}   "
          f"worse than -10%: {sum(1 for x in short if x < -0.10)}")


if __name__ == "__main__":
    main()
