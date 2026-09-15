"""The deployed configuration at a chosen position scale, year by year.

`dd_levers.py` established that scaling is the only lever that reduces the
drawdown — Sharpe is invariant at 1.82 for every f, so this is a dial and not a
discovery. This prints what living at a given f actually looks like, because a
single CAGR number hides the thing that matters: which YEARS were bad, and how
bad they were while you were sitting in them.

f scales the notional of whichever leg trades. The rest of the equity sits in
cash at 0% — deliberately not at the money-market rate, so the comparison is the
conservative one and no part of the result depends on a rate assumption.

Everything else is `final_config.py` exactly: RV20 through D-1, walk-forward
p60 on each series' own history, measured auction costs, XLU only when SOXL is
benched.

Usage:  python3 retreat_lab/scaled_run.py [scale] [start_year] [equity] [xlu_mult]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
from coverage import load, walk

F = float(sys.argv[1]) if len(sys.argv) > 1 else 0.6
START = int(sys.argv[2]) if len(sys.argv) > 2 else 2023
EQUITY = float(sys.argv[3]) if len(sys.argv) > 3 else 142_492.0
XLU_MULT = float(sys.argv[4]) if len(sys.argv) > 4 else 2.5
SOXL_BP = 0.29 / 1e4
XLU_BP = 0.83 / 1e4


def build(path, lag=1):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1, nxt=d[i + 1],
                       days=(d[i + 1] - d[i]).days)
            for i in range(21, len(d) - 1)}


def rows_for(days, S, X, sel, xe, f):
    out = []
    for d in days:
        if sel[d]:
            out.append(("SOXL", d, f * (S[d]["on"] - 2 * SOXL_BP)))
        elif xe.get(d):
            out.append(("XLU", d, f * XLU_MULT * (X[d]["on"] - 2 * XLU_BP)))
        else:
            out.append(("FLAT", d, 0.0))
    return out


def dd_of(vals):
    eq = pk = 1.0
    worst = 0.0
    for v in vals:
        eq *= 1 + v
        pk = max(pk, eq)
        worst = min(worst, eq / pk - 1)
    return worst


def summarise(rows, yrs):
    v = [x for _, _, x in rows]
    traded = [x for x in v if x != 0.0]
    g = math.prod(1 + x for x in v) - 1
    s = stdev(traded) if len(traded) > 1 else 0.0
    return dict(total=g * 100, cagr=((1 + g) ** (1 / yrs) - 1) * 100,
                dd=dd_of(v) * 100, n=len(traded),
                sharpe=mean(traded) / s * (len(traded) / yrs) ** 0.5 if s else 0.0,
                worst=min(traded) * 100, best=max(traded) * 100,
                mean=mean(traded) * 100,
                win=sum(1 for x in traded if x > 0) / len(traded) * 100)


def main():
    S = build("SOXL_1min.csv")
    X = build("retreat_lab/out/XLU_daily_ibkr.csv")
    sd = sorted(S); xd = sorted(X)
    sel = walk({d: S[d]["rv"] for d in sd}, sd, 60)
    xe = walk({d: X[d]["rv"] for d in xd}, xd, 60)
    days = [d for d in sd if d.year >= START and d in X]
    yrs = (days[-1] - days[0]).days / 365.25

    full = rows_for(days, S, X, sel, xe, 1.0)
    scal = rows_for(days, S, X, sel, xe, F)
    a, b = summarise(full, yrs), summarise(scal, yrs)

    print(f"DEPLOYED CONFIGURATION AT {F:.0%} POSITION SCALE")
    print(f"{days[0]} → {days[-1]}   {len(days)} sessions, {yrs:.1f} years   "
          f"XLU cover {XLU_MULT:.1f}x   starting ${EQUITY:,.0f}\n")

    print(f"  {'':<14}{'total':>12}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}"
          f"{'worst nt':>11}{'mean nt':>10}{'win':>7}")
    for lbl, st in ((f"full (1.00x)", a), (f"scaled ({F:.2f}x)", b)):
        print(f"  {lbl:<14}{st['total']:>11,.0f}%{st['cagr']:>8.1f}%"
              f"{st['dd']:>8.1f}%{st['sharpe']:>8.2f}{st['worst']:>10.2f}%"
              f"{st['mean']:>9.3f}%{st['win']:>6.0f}%")

    # ------------------------------------------------------ year by year
    print(f"\n  YEAR BY YEAR AT {F:.0%}")
    print(f"  {'year':<6}{'sess':>6}{'SOXL':>6}{'XLU':>5}{'flat':>6}"
          f"{'return':>10}{'maxDD':>9}{'equity end':>14}{'vs 1.00x':>11}")
    eq = EQUITY
    eq_full = EQUITY
    for y in sorted({d.year for d in days}):
        sy = [r for r in scal if r[1].year == y]
        fy = [r for r in full if r[1].year == y]
        gy = math.prod(1 + v for _, _, v in sy) - 1
        gf = math.prod(1 + v for _, _, v in fy) - 1
        eq *= 1 + gy
        eq_full *= 1 + gf
        print(f"  {y:<6}{len(sy):>6}"
              f"{sum(1 for l,_,_ in sy if l=='SOXL'):>6}"
              f"{sum(1 for l,_,_ in sy if l=='XLU'):>5}"
              f"{sum(1 for l,_,_ in sy if l=='FLAT'):>6}"
              f"{gy*100:>9.1f}%{dd_of([v for _,_,v in sy])*100:>8.1f}%"
              f"{eq:>13,.0f}{gf*100:>10.1f}%")

    print(f"\n  ${EQUITY:,.0f} → ${eq:,.0f} at {F:.0%}   "
          f"(${eq_full:,.0f} at 1.00x)")

    # ------------------------------------------------- what a bad night costs
    print(f"\n  WHAT A BAD NIGHT COSTS AT {F:.0%}, on ${EQUITY:,.0f}")
    worst = sorted(scal, key=lambda r: r[2])[:8]
    print(f"  {'date':<13}{'leg':>6}{'night':>10}{'on the starting equity':>26}")
    for l, d, v in worst:
        print(f"  {d.isoformat():<13}{l:>6}{v*100:>9.2f}%{v*EQUITY:>25,.0f}")

    v = [x for _, _, x in scal if x != 0.0]
    print(f"\n  nights worse than -5%: {sum(1 for x in v if x<-0.05)} of {len(v)}"
          f"   worse than -3%: {sum(1 for x in v if x<-0.03)}")
    print(f"  the -{abs(b['dd']):.1f}% drawdown is ${abs(b['dd'])/100*EQUITY:,.0f} "
          f"on the starting equity (-{abs(a['dd']):.1f}% = "
          f"${abs(a['dd'])/100*EQUITY:,.0f} at 1.00x)")

    out = os.path.join(ROOT, f"retreat_lab/out/scaled_{int(F*100)}.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["decision_date", "leg", "hold_to", "calendar_days",
                    "net_pct_scaled", "net_pct_full"])
        for (l, d, v), (_, _, vf) in zip(scal, full):
            w.writerow([d.isoformat(), l, S[d]["nxt"].isoformat(), S[d]["days"],
                        round(v * 100, 4), round(vf * 100, 4)])
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()
