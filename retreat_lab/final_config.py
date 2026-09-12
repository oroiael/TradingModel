"""The exact configuration proposed for the paper run, priced end to end.

Everything here is the implementable version:
  * signal uses RV20 through D-1's close, so it is known before any MOC cutoff
  * thresholds are walk-forward (p60 of that series' own prior history)
  * costs are the measured ones from fills.py, auction execution
  * SOXL leg 1x notional; XLU cover leg 3x notional, only when SOXL is benched
    AND XLU's own filter says go

Usage:  python3 retreat_lab/final_config.py [start_year]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
from coverage import load, walk, curve

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
SOXL_BP = 0.29 / 1e4      # commission only, MOC/MOO auction
XLU_BP = 0.83 / 1e4
XLU_MULT = 3.0


def build(path, lag=1):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1, nxt=d[i + 1],
                       days=(d[i + 1] - d[i]).days)
            for i in range(21, len(d) - 1)}


def main():
    S = build("SOXL_1min.csv")
    X = build("retreat_lab/out/XLU_daily_ibkr.csv")
    sd = sorted(S); sel = walk({d: S[d]["rv"] for d in sd}, sd, 60)
    xd = sorted(X); xe = walk({d: X[d]["rv"] for d in xd}, xd, 60)
    days = [d for d in sd if d.year >= START and d in X]
    yrs = (days[-1] - days[0]).days / 365.25

    rows, nS, nX, nF = [], 0, 0, 0
    for d in days:
        if sel[d]:
            rows.append(("SOXL", d, S[d]["on"] - 2 * SOXL_BP)); nS += 1
        elif xe.get(d):
            rows.append(("XLU", d, XLU_MULT * X[d]["on"] - XLU_MULT * 2 * XLU_BP)); nX += 1
        else:
            rows.append(("FLAT", d, 0.0)); nF += 1
    r = [v for _, _, v in rows]
    g, cg, dd, sh, t = curve([v for v in r if v != 0.0], yrs)
    gall = math.prod(1 + v for v in r) - 1
    eq = pk = 1.0; ddall = 0.0
    for v in r:
        eq *= 1 + v; pk = max(pk, eq); ddall = min(ddall, eq / pk - 1)

    print(f"PROPOSED CONFIGURATION — paper run")
    print(f"{days[0]} → {days[-1]}   {len(days)} sessions, {yrs:.1f} years\n")
    print(f"  SOXL nights {nS} ({nS/len(days)*100:.0f}%)   "
          f"XLU nights {nX} ({nX/len(days)*100:.0f}%)   flat {nF} ({nF/len(days)*100:.0f}%)")
    print(f"  total {gall*100:,.0f}%   CAGR {((1+gall)**(1/yrs)-1)*100:.1f}%   "
          f"max DD {ddall*100:.1f}%   Sharpe {sh:.2f}   t {t:.2f}\n")

    print(f"  {'year':<7}{'sessions':>10}{'SOXL nts':>10}{'XLU nts':>9}{'flat':>7}{'return':>11}")
    for y in sorted({d.year for d in days}):
        dy = [x for x in rows if x[1].year == y]
        gy = math.prod(1 + v for _, _, v in dy) - 1
        print(f"  {y:<7}{len(dy):>10}{sum(1 for a,_,_ in dy if a=='SOXL'):>10}"
              f"{sum(1 for a,_,_ in dy if a=='XLU'):>9}"
              f"{sum(1 for a,_,_ in dy if a=='FLAT'):>7}{gy*100:>10.1f}%")

    pos = [v for v in r if v != 0.0]
    w = [v for v in pos if v > 0]
    print(f"\n  per-trade: {len(pos)} trades, win rate {len(w)/len(pos)*100:.0f}%, "
          f"mean {mean(pos)*100:+.3f}%, median {sorted(pos)[len(pos)//2]*100:+.3f}%")
    print(f"  best {max(pos)*100:+.2f}%   worst {min(pos)*100:+.2f}%   "
          f"sd {stdev(pos)*100:.2f}%")
    print(f"  nights worse than -5%: {sum(1 for v in pos if v<-0.05)}   "
          f"worse than -8%: {sum(1 for v in pos if v<-0.08)}")
    wk = sum(1 for _, d, v in rows if v != 0.0 and S[d]["days"] >= 3)
    print(f"  weekend/holiday holds: {wk} of {len(pos)} trades ({wk/len(pos)*100:.0f}%)")
    out = os.path.join(ROOT, "retreat_lab/out/proposed_ledger.csv")
    with open(out, "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["decision_date", "leg", "hold_to", "calendar_days", "return_pct"])
        for a, d, v in rows:
            wr.writerow([d.isoformat(), a, S[d]["nxt"].isoformat(), S[d]["days"],
                         round(v * 100, 4)])
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()
