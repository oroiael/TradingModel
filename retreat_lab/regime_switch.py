"""p60 at f=0.5 with weekly cash, and whether this is a bull-market strategy.

Three parts:
  1. the p60 overnight strategy at half size, week by week, from $100,000
  2. is it a bull strategy? -- performance split by the regime of SOXX, the
     UNLEVERED semiconductor index ETF. SOXX is the right yardstick because it
     carries no leverage decay, so its moving averages mean what they say.
  3. do any indicators call the regime early enough to switch on? Tested:
     SOXX vs its 50/200-day averages, SOXX drawdown from a 252-day high, SOXL's
     own realised vol, and the leveraged-ETF rebalance mechanic itself.

The rebalance test is the mechanistic one. A 3x ETF must trade in the direction
of the day's move at the close to hold leverage constant -- buying after up days,
selling after down days -- so required flow scales with |intraday move|. If the
overnight premium is rebalance-driven, it should depend on that day's move and
its sign. That is directly testable.

Usage:  python3 retreat_lab/regime_switch.py [bps_per_side] [capital] [fraction]
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


def daily(name, use_1min=False):
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


def perf(rets, yrs, cap=CAP, f=F):
    eq = cap; pk = cap; dd = 0.0
    for r in rets:
        eq *= (1 + f * r); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    return dict(final=eq, cagr=(eq / cap) ** (1 / yrs) - 1 if eq > 0 else -1,
                dd=dd, n=len(rets),
                sh=(mean(rets) / stdev(rets) * ((len(rets) / yrs) ** 0.5))
                if len(rets) > 1 and stdev(rets) else 0,
                mean=mean(rets) if rets else 0)


def main():
    days, op, cl = daily("SOXL_1min.csv")
    xd, xo, xc = daily("SOXX_5min_6Years.csv")
    c = COST / 10000.0
    dret = [cl[days[i]] / cl[days[i - 1]] - 1 for i in range(1, len(days))]
    rv = {}
    for i in range(20, len(days)):
        rv[i] = stdev(dret[i - 20:i]) * (252 ** 0.5) * 100

    # SOXX regime, trailing only
    xs = sorted(xc)
    ma50, ma200, ddn = {}, {}, {}
    for i in range(len(xs)):
        if i >= 50:
            ma50[xs[i]] = mean(xc[xs[j]] for j in range(i - 50, i))
        if i >= 200:
            ma200[xs[i]] = mean(xc[xs[j]] for j in range(i - 200, i))
        if i >= 252:
            hi = max(xc[xs[j]] for j in range(i - 252, i + 1))
            ddn[xs[i]] = xc[xs[i]] / hi - 1

    nights = [(i, (op[days[i + 1]] / cl[days[i]] - 1) - 2 * c)
              for i in range(len(days) - 1) if i in rv]
    first = nights[0][0]
    live = [(i, r) for i, r in nights if i >= first + BURN]
    sel = []
    for i, r in live:
        hist = [rv[j] for j in sorted(rv) if j < i]
        if len(hist) >= 60 and rv[i] < pctile(hist, 60):
            sel.append((i, days[i], r))
    yrs = (days[live[-1][0]] - days[live[0][0]]).days / 365.25

    # ---------- 1. weekly cash at f
    weeks = sorted({d - dt.timedelta(days=d.weekday()) for _, d, _ in sel})
    allw = sorted({days[i] - dt.timedelta(days=days[i].weekday()) for i, _ in live})
    eq = CAP; pk = CAP; dd = 0.0; rows = []
    t0 = days[live[0][0]]
    for w in allw:
        start = eq; n = 0
        for _, d, r in sel:
            if d - dt.timedelta(days=d.weekday()) == w:
                eq *= (1 + F * r); n += 1
        pk = max(pk, eq); dd = min(dd, eq / pk - 1)
        y = max((w + dt.timedelta(days=4) - t0).days / 365.25, 1 / 365.25)
        rows.append(dict(week_starting=w.isoformat(), nights=n,
                         cash_pnl=round(eq - start, 2), equity=round(eq, 2),
                         week_pct=round((eq / start - 1) * 100, 3),
                         running_cagr_pct=round(((eq / CAP) ** (1 / y) - 1) * 100, 2),
                         drawdown_pct=round((eq / pk - 1) * 100, 2)))
    path = os.path.join(OUT, f"weekly_p60_f{int(F*100)}.csv")
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        wr.writeheader(); wr.writerows(rows)

    print(f"1. p60 OVERNIGHT AT f={F:.2f}, ${CAP:,.0f} start, {COST:.1f} bps/side")
    print(f"   {t0} → {days[live[-1][0]]}  ({yrs:.1f}y, {len(allw)} weeks, "
          f"{len(sel)} nights traded)\n")
    pnl = [r["cash_pnl"] for r in rows]
    print(f"   final ${eq:,.0f}   total {(eq/CAP-1)*100:,.0f}%   "
          f"CAGR {((eq/CAP)**(1/yrs)-1)*100:.1f}%   maxDD {dd*100:.1f}%")
    print(f"   weekly cash: median ${median(pnl):,.0f}  mean ${mean(pnl):,.0f}  "
          f"best ${max(pnl):,.0f}  worst ${min(pnl):,.0f}  "
          f"positive {sum(1 for x in pnl if x>0)/len(pnl):.1%}")
    print(f"   {'year':<6}{'cash':>12}{'equity end':>14}{'CAGR':>9}{'worst wk':>12}")
    for y in sorted({dt.date.fromisoformat(r['week_starting']).year for r in rows}):
        yr = [r for r in rows if dt.date.fromisoformat(r['week_starting']).year == y]
        print(f"   {y:<6}{sum(r['cash_pnl'] for r in yr):>11,.0f}"
              f"{yr[-1]['equity']:>14,.0f}{yr[-1]['running_cagr_pct']:>8.1f}%"
              f"{min(r['cash_pnl'] for r in yr):>11,.0f}")
    print(f"   wrote {path}")

    # ---------- 2. bull or bear?
    print(f"\n2. IS THIS A BULL STRATEGY? — split by SOXX regime (unlevered semis)")
    print(f"   {'regime':<30}{'nights':>8}{'mean/nt':>10}{'CAGR':>9}"
          f"{'maxDD':>9}{'Sharpe':>8}")
    def show(lbl, sub):
        if len(sub) < 30:
            print(f"   {lbl:<30}{len(sub):>8}  (thin)"); return
        y = yrs * len(sub) / len(sel)
        m = perf([r for r in sub], y)
        print(f"   {lbl:<30}{len(sub):>8}{m['mean']*100:>9.3f}%"
              f"{m['cagr']*100:>8.1f}%{m['dd']*100:>8.1f}%{m['sh']:>8.2f}")
    show("all p60 nights", [r for _, _, r in sel])
    show("SOXX above its 200d avg", [r for _, d, r in sel if d in ma200 and xc[d] > ma200[d]])
    show("SOXX below its 200d avg", [r for _, d, r in sel if d in ma200 and xc[d] <= ma200[d]])
    show("SOXX above its 50d avg", [r for _, d, r in sel if d in ma50 and xc[d] > ma50[d]])
    show("SOXX below its 50d avg", [r for _, d, r in sel if d in ma50 and xc[d] <= ma50[d]])
    show("SOXX within 10% of 1y high", [r for _, d, r in sel if d in ddn and ddn[d] > -0.10])
    show("SOXX 10-20% off 1y high", [r for _, d, r in sel if d in ddn and -0.20 < ddn[d] <= -0.10])
    show("SOXX >20% off 1y high", [r for _, d, r in sel if d in ddn and ddn[d] <= -0.20])

    # ---------- 3. does switching help?
    print(f"\n3. TRADING THE FILTER — full period, f={F:.2f}, flat when the gate is shut")
    print(f"   {'gate':<34}{'nights':>8}{'final':>13}{'CAGR':>9}{'maxDD':>9}")
    for lbl, keep in (("none (all p60 nights)", lambda d: True),
                      ("+ SOXX > 200d avg", lambda d: d in ma200 and xc[d] > ma200[d]),
                      ("+ SOXX > 50d avg", lambda d: d in ma50 and xc[d] > ma50[d]),
                      ("+ SOXX within 20% of 1y high",
                       lambda d: d in ddn and ddn[d] > -0.20),
                      ("+ SOXX >200d AND within 20%",
                       lambda d: d in ma200 and xc[d] > ma200[d]
                       and d in ddn and ddn[d] > -0.20)):
        rs = [r for _, d, r in sel if keep(d)]
        m = perf(rs, yrs)
        print(f"   {lbl:<34}{len(rs):>8}{m['final']:>12,.0f}"
              f"{m['cagr']*100:>8.1f}%{m['dd']*100:>8.1f}%")

    # ---------- the mechanism
    print(f"\n4. THE REBALANCE MECHANIC — a 3x ETF must trade WITH the day's move at")
    print(f"   the close. If the overnight premium is that flow, it should depend on")
    print(f"   the day's own intraday move and its sign.")
    print(f"   {'that day intraday move':<30}{'nights':>8}{'mean overnight':>17}")
    for lbl, f_ in ((" < -3%", lambda g: g < -0.03), (" -3 to -1%", lambda g: -0.03 <= g < -0.01),
                    (" -1 to +1%", lambda g: -0.01 <= g < 0.01),
                    (" +1 to +3%", lambda g: 0.01 <= g < 0.03), (" > +3%", lambda g: g >= 0.03)):
        b = [r for i, d, r in sel if f_(cl[d] / op[d] - 1)]
        if len(b) >= 20:
            print(f"   {lbl:<30}{len(b):>8}{mean(b)*100:>16.3f}%")


if __name__ == "__main__":
    main()
