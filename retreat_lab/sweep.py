"""f=2.0 with a weekly cash sweep: reinvest 75%, move 25% to interest.

Rules, stated because each is a choice:
  * the sweep fires only on PROFITABLE weeks. A losing week sweeps nothing.
  * it is ONE-WAY. The reserve never funds losses back into the trading
    account, so the trading account can shrink while the reserve only grows.
    That is what makes this de-risking rather than rebalancing.
  * position size is 2.0x the TRADING account, not the total. Sweeping cash out
    therefore shrinks the position, which is the mechanism.
  * margin at 6%/yr on the borrowed portion, per night held, as in the f>1 runs.
  * the reserve earns a rate schedule approximating short T-bills over the
    period rather than one flat number, since 2021 and 2024 were nothing alike.
    Flat-rate sensitivity is printed alongside.

Usage:  python3 retreat_lab/sweep.py [bps_per_side] [capital] [fraction] [sweep_pct]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
CAP = float(sys.argv[2]) if len(sys.argv) > 2 else 100_000.0
F = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
SWEEP = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25
MARGIN = 0.06
BURN = 252
OUT = os.path.join(ROOT, "retreat_lab/out")

# approximate short T-bill / money-market yield by year
RATES = {2021: 0.0005, 2022: 0.0200, 2023: 0.0500,
         2024: 0.0500, 2025: 0.0425, 2026: 0.0400}


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


def main():
    days, op, cl = daily("SOXL_1min.csv")
    c = COST / 10000.0
    dret = [cl[days[i]] / cl[days[i - 1]] - 1 for i in range(1, len(days))]
    rv = {}
    for i in range(20, len(days)):
        rv[i] = stdev(dret[i - 20:i]) * (252 ** 0.5) * 100
    nights = [(i, (op[days[i + 1]] / cl[days[i]] - 1) - 2 * c)
              for i in range(len(days) - 1) if i in rv]
    first = nights[0][0]
    live = [(i, r) for i, r in nights if i >= first + BURN]
    sel = {}
    for i, r in live:
        h = [rv[j] for j in sorted(rv) if j < i]
        if len(h) >= 60 and rv[i] < pctile(h, 60):
            sel[days[i]] = (r, cl[days[i]] / op[days[i]] - 1)
    keep = {d: v[0] for d, v in sel.items() if v[1] >= -0.04}
    t0 = days[live[0][0]]
    yrs = (days[live[-1][0]] - t0).days / 365.25
    per_night = max(F - 1, 0) * MARGIN / 365.0

    def simulate(sweep, rate_fn):
        trade = CAP; res = 0.0; pk = CAP; dd = 0.0
        rows = []
        allw = sorted({days[i] - dt.timedelta(days=days[i].weekday())
                       for i, _ in live})
        for w in allw:
            start = trade
            n = 0
            for d, r in keep.items():
                if d - dt.timedelta(days=d.weekday()) == w:
                    trade *= (1 + F * r - per_night)
                    n += 1
            pnl = trade - start
            res *= (1 + rate_fn(w) / 52.0)          # a week of interest
            swept = 0.0
            if pnl > 0 and sweep > 0:
                swept = pnl * sweep
                trade -= swept; res += swept
            tot = trade + res
            pk = max(pk, tot); dd = min(dd, tot / pk - 1)
            y = max((w + dt.timedelta(days=4) - t0).days / 365.25, 1 / 365.25)
            rows.append(dict(week_starting=w.isoformat(), nights=n,
                             trading_pnl=round(pnl, 2), swept_to_reserve=round(swept, 2),
                             trading_equity=round(trade, 2), reserve=round(res, 2),
                             total=round(tot, 2),
                             running_cagr_pct=round(((tot / CAP) ** (1 / y) - 1) * 100, 2),
                             drawdown_pct=round((tot / pk - 1) * 100, 2)))
        return trade, res, dd, rows

    sched = lambda w: RATES.get(w.year, 0.04)
    print(f"p60 + skip -4%, f={F:.1f}, ${CAP:,.0f}, {COST:.1f} bps/side, "
          f"{MARGIN:.0%}/yr margin")
    print(f"{t0} → {days[live[-1][0]]} ({yrs:.1f}y, {len(keep)} nights)")
    print(f"sweep {SWEEP:.0%} of each profitable week's P&L to a reserve earning "
          f"{RATES[2021]:.2%}→{RATES[2026]:.2%} by year\n")

    print(f"  {'variant':<34}{'trading':>13}{'reserve':>12}{'total':>13}"
          f"{'CAGR':>9}{'maxDD':>9}")
    for lbl, sw in ((f"no sweep (all reinvested)", 0.0),
                    (f"sweep {SWEEP:.0%} weekly", SWEEP)):
        tr, rs, dd, rows = simulate(sw, sched)
        print(f"  {lbl:<34}{tr:>12,.0f}{rs:>11,.0f}{tr+rs:>12,.0f}"
              f"{((tr+rs)/CAP)**(1/yrs)-1:>8.1%}{dd*100:>8.1f}%")
    for sw in (0.10, 0.50, 0.75):
        tr, rs, dd, rows = simulate(sw, sched)
        print(f"  {'sweep ' + f'{sw:.0%}' + ' weekly':<34}{tr:>12,.0f}{rs:>11,.0f}"
              f"{tr+rs:>12,.0f}{((tr+rs)/CAP)**(1/yrs)-1:>8.1%}{dd*100:>8.1f}%")

    print(f"\n  interest-rate sensitivity on the {SWEEP:.0%} sweep:")
    for rt in (0.0, 0.02, 0.04, 0.05):
        tr, rs, dd, _ = simulate(SWEEP, lambda w, r=rt: r)
        print(f"    flat {rt:.0%}/yr  trading ${tr:,.0f}  reserve ${rs:,.0f}  "
              f"total ${tr+rs:,.0f}")

    tr, rs, dd, rows = simulate(SWEEP, sched)
    path = os.path.join(OUT, f"weekly_sweep{int(SWEEP*100)}_f{int(F*10)}.csv")
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        wr.writeheader(); wr.writerows(rows)

    print(f"\n  THE {SWEEP:.0%} SWEEP, YEAR BY YEAR")
    print(f"  {'year':<6}{'trading P&L':>14}{'swept':>12}{'trading eq':>14}"
          f"{'reserve':>12}{'total':>14}{'CAGR':>8}")
    for y in sorted({dt.date.fromisoformat(r['week_starting']).year for r in rows}):
        yr = [r for r in rows if dt.date.fromisoformat(r['week_starting']).year == y]
        print(f"  {y:<6}{sum(r['trading_pnl'] for r in yr):>13,.0f}"
              f"{sum(r['swept_to_reserve'] for r in yr):>12,.0f}"
              f"{yr[-1]['trading_equity']:>14,.0f}{yr[-1]['reserve']:>12,.0f}"
              f"{yr[-1]['total']:>14,.0f}{yr[-1]['running_cagr_pct']:>7.1f}%")
    sw = [r['swept_to_reserve'] for r in rows]
    print(f"\n  weeks that swept: {sum(1 for x in sw if x>0)}/{len(rows)}   "
          f"median sweep ${median([x for x in sw if x>0]):,.0f}   "
          f"largest ${max(sw):,.0f}   total swept ${sum(sw):,.0f}")
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
