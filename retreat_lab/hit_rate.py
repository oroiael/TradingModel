"""Where the win rate comes from: the instrument, or the filter?

The strategy's edge is almost entirely its hit rate — mean win +2.19% against
mean loss -2.13% is a win/loss ratio of 1.027, so payoff asymmetry contributes
essentially nothing. That makes "can we raise the win rate" the right question,
and this answers the half of it that is measurable without new data.

For every instrument on hand it prints the overnight win rate UNCONDITIONALLY
and under the deployed p60 RV20 filter. The gap between them is what the rule
is worth. If the gap is small, the win rate is a property of the instrument and
choosing a different one is the only lever; if it is large, the rule is doing
the work and could be tuned.

Usage:  python3 retreat_lab/hit_rate.py [start_year]
"""
import csv, glob, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
_argv, sys.argv = sys.argv, sys.argv[:1]
from coverage import load, walk                              # noqa: E402
sys.argv = _argv
try:
    from universe import group_of
except Exception:                                            # noqa: BLE001
    def group_of(_):
        return "?"

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023


def series(path, lag=1):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1)
            for i in range(21, len(d) - 1)}


def main():
    out_dir = os.path.join(ROOT, "retreat_lab/out")
    files = sorted(glob.glob(os.path.join(out_dir, "*_daily_ibkr.csv")))
    files += sorted(glob.glob(os.path.join(out_dir, "universe", "*.csv")))
    rows = []
    seen = set()
    for f in files:
        sym = os.path.basename(f).replace("_daily_ibkr.csv", "").replace(".csv", "")
        if sym in seen:
            continue
        seen.add(sym)
        try:
            S = series(f)
        except Exception:                                    # noqa: BLE001
            continue
        d = sorted(S)
        days = [x for x in d if x.year >= START]
        if len(days) < 250:
            continue
        sel = walk({x: S[x]["rv"] for x in d}, d, 60)
        allr = [S[x]["on"] for x in days]
        selr = [S[x]["on"] for x in days if sel[x]]
        if len(selr) < 100:
            continue
        rows.append(dict(
            sym=sym, grp=group_of(sym), n=len(allr),
            uw=sum(1 for v in allr if v > 0) / len(allr) * 100,
            um=mean(allr) * 100,
            k=len(selr),
            fw=sum(1 for v in selr if v > 0) / len(selr) * 100,
            fm=mean(selr) * 100))
    rows.sort(key=lambda r: -r["fw"])

    print(f"OVERNIGHT WIN RATE — unconditional vs under the p60 RV20 filter")
    print(f"from {START}.  'lift' is what the rule adds to the raw instrument.\n")
    print(f"  {'symbol':<8}{'class':<17}{'nights':>7}{'uncond':>9}{'mean':>9}"
          f"{'traded':>8}{'filtered':>10}{'mean':>9}{'lift':>8}")
    for r in rows:
        print(f"  {r['sym']:<8}{r['grp']:<17}{r['n']:>7}{r['uw']:>8.1f}%"
              f"{r['um']:>8.3f}%{r['k']:>8}{r['fw']:>9.1f}%{r['fm']:>8.3f}%"
              f"{r['fw']-r['uw']:>+7.1f}")

    lifts = [r["fw"] - r["uw"] for r in rows]
    print(f"\n  across {len(rows)} instruments the filter's lift on win rate is")
    print(f"  mean {mean(lifts):+.2f} points, median "
          f"{sorted(lifts)[len(lifts)//2]:+.2f}, range "
          f"{min(lifts):+.1f} to {max(lifts):+.1f}")
    mlift = [r["fm"] - r["um"] for r in rows]
    print(f"  its lift on MEAN RETURN is {mean(mlift):+.4f} points "
          f"(median {sorted(mlift)[len(mlift)//2]:+.4f})")

    p = os.path.join(out_dir, "hit_rate.csv")
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["symbol", "class", "nights", "uncond_win_pct",
                    "uncond_mean_pct", "traded", "filtered_win_pct",
                    "filtered_mean_pct", "lift_pts"])
        for r in rows:
            w.writerow([r["sym"], r["grp"], r["n"], round(r["uw"], 2),
                        round(r["um"], 4), r["k"], round(r["fw"], 2),
                        round(r["fm"], 4), round(r["fw"] - r["uw"], 2)])
    print(f"\n  wrote {p}")


if __name__ == "__main__":
    main()
