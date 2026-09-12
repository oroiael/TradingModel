"""$100,000 through the overnight strategy: weekly cash, running CAGR, p60 vs p80.

Full reinvestment -- the whole balance is committed on every night traded, which
is what "reinvest earnings" means and is aggressive on a 3x ETF. Thresholds are
WALK-FORWARD (expanding window, no forward information), so this is the honest
version, not the in-sample one.

Writes the complete week-by-week ledger to retreat_lab/out/weekly_cashflow.csv
and prints the summary.

Usage:  python3 retreat_lab/cashflow.py [bps_per_side] [starting_capital]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, BARS, SYMBOL, SUF

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
CAP = float(sys.argv[2]) if len(sys.argv) > 2 else 100_000.0
BURN = 252
OUT = os.path.join(ROOT, "retreat_lab/out")


def load():
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, BARS)) as f:
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

    variants = {"no filter": None, "p60": 60, "p80": 80}
    take = {}
    for name, p in variants.items():
        s = set()
        for i, _ in live:
            if p is None:
                s.add(i); continue
            hist = [rv[j] for j in sorted(rv) if j < i]
            if len(hist) >= 60 and rv[i] < pctile(hist, p):
                s.add(i)
        take[name] = s

    # week key = the Monday of the week the night's ENTRY falls in
    weeks = sorted({days[i] - dt.timedelta(days=days[i].weekday()) for i, _ in live})
    eq = {k: CAP for k in variants}
    peak = {k: CAP for k in variants}
    maxdd = {k: 0.0 for k in variants}
    rows = []
    t0 = days[live[0][0]]
    for w in weeks:
        rec = {"week_starting": w.isoformat()}
        yrs = max((w + dt.timedelta(days=4) - t0).days / 365.25, 1 / 365.25)
        for k in variants:
            start = eq[k]
            n = 0
            for i, r in live:
                if days[i] - dt.timedelta(days=days[i].weekday()) != w:
                    continue
                if i in take[k]:
                    eq[k] *= (1 + r); n += 1
            pnl = eq[k] - start
            peak[k] = max(peak[k], eq[k])
            maxdd[k] = min(maxdd[k], eq[k] / peak[k] - 1)
            cagr = (eq[k] / CAP) ** (1 / yrs) - 1 if eq[k] > 0 else -1
            rec[f"{k}_nights"] = n
            rec[f"{k}_cash_pnl"] = round(pnl, 2)
            rec[f"{k}_equity"] = round(eq[k], 2)
            rec[f"{k}_week_pct"] = round((eq[k] / start - 1) * 100, 3) if start else 0
            rec[f"{k}_running_cagr_pct"] = round(cagr * 100, 2)
            rec[f"{k}_drawdown_pct"] = round((eq[k] / peak[k] - 1) * 100, 2)
        rows.append(rec)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"weekly_cashflow{SUF}.csv")
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        wr.writeheader(); wr.writerows(rows)

    yrs = (days[live[-1][0]] - t0).days / 365.25
    print(f"${CAP:,.0f} start | overnight strategy, WALK-FORWARD threshold, "
          f"{COST:.1f} bps/side")
    print(f"{t0} → {days[live[-1][0]]}  ({yrs:.1f}y, {len(weeks)} weeks, "
          f"{len(live)} nights available)\n")
    print(f"  {'variant':<12}{'final equity':>16}{'total':>10}{'CAGR':>9}"
          f"{'maxDD':>9}{'nights':>8}{'wk win%':>9}{'best wk':>13}{'worst wk':>13}")
    for k in variants:
        pnl = [r[f"{k}_cash_pnl"] for r in rows]
        wins = sum(1 for x in pnl if x > 0) / len(pnl)
        n = sum(r[f"{k}_nights"] for r in rows)
        print(f"  {k:<12}{eq[k]:>15,.0f}{(eq[k]/CAP-1)*100:>9.0f}%"
              f"{((eq[k]/CAP)**(1/yrs)-1)*100:>8.1f}%{maxdd[k]*100:>8.1f}%"
              f"{n:>8}{wins:>9.1%}{max(pnl):>12,.0f}{min(pnl):>13,.0f}")

    print(f"\n  weekly cash, per variant (median | mean | p10 | p90):")
    for k in variants:
        pnl = sorted(r[f"{k}_cash_pnl"] for r in rows)
        print(f"    {k:<12} {median(pnl):>10,.0f} | {mean(pnl):>10,.0f} | "
              f"{pnl[int(len(pnl)*.1)]:>10,.0f} | {pnl[int(len(pnl)*.9)]:>10,.0f}")

    print(f"\n  YEAR BY YEAR — cash generated and running CAGR at year end")
    print(f"  {'year':<6}" + "".join(f"{k+' cash':>16}{k+' CAGR':>12}" for k in variants))
    for y in sorted({dt.date.fromisoformat(r["week_starting"]).year for r in rows}):
        yr = [r for r in rows if dt.date.fromisoformat(r["week_starting"]).year == y]
        line = f"  {y:<6}"
        for k in variants:
            line += (f"{sum(r[f'{k}_cash_pnl'] for r in yr):>15,.0f}"
                     f"{yr[-1][f'{k}_running_cagr_pct']:>11.1f}%")
        print(line)

    print(f"\n  five worst weeks by cash, p60:")
    for r in sorted(rows, key=lambda r: r["p60_cash_pnl"])[:5]:
        print(f"    {r['week_starting']}  {r['p60_cash_pnl']:>12,.0f}  "
              f"({r['p60_week_pct']:>6.2f}%)  {r['p60_nights']} nights")
    print(f"  five best weeks by cash, p60:")
    for r in sorted(rows, key=lambda r: -r["p60_cash_pnl"])[:5]:
        print(f"    {r['week_starting']}  {r['p60_cash_pnl']:>12,.0f}  "
              f"({r['p60_week_pct']:>6.2f}%)  {r['p60_nights']} nights")
    print(f"\nwrote {path}  ({len(rows)} weeks x {len(rows[0])} columns)")


if __name__ == "__main__":
    main()
