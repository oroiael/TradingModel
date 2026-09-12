"""What covers SOXL's off-nights best?

The p60 rule benches SOXL on ~35% of nights. basket.py showed the gain from
adding TQQQ is COVERAGE of those nights, not diversification on the shared ones.
So the right question is not "what diversifies SOXL" but "what earns money on
the specific nights SOXL is benched".

Candidates span 3x equity, 2x equity, inverse, and debt -- the last both as a
position and, separately, as an INDICATOR feeding the eligibility rule.

Two distinct tests:

  A. AS A POSITION   on SOXL's off-nights only: mean overnight return, t-stat,
     and the SWITCH strategy (SOXL when eligible, candidate when SOXL is off and
     the candidate's own p60 rule says go).

  B. AS AN INDICATOR  does a bond-market signal improve SOXL's own eligibility
     rule? Tested signals: TLT trailing 20d return (bond momentum), TLT RV20
     (rate vol, a MOVE proxy), and HYG/TLT relative strength (a credit-spread
     proxy -- HYG lagging TLT means credit stress).

All thresholds are walk-forward: the p-th percentile of that series' own history
strictly before the night in question. Backtest from 2023 with a warm start.

Usage:  python3 retreat_lab/coverage.py [bps_per_side] [start_year]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = (float(sys.argv[1]) if len(sys.argv) > 1 else 1.0) / 10000.0
START = int(sys.argv[2]) if len(sys.argv) > 2 else 2023
O = "retreat_lab/out"

CAND = [
    ("TQQQ", f"{O}/TQQQ_daily_ibkr.csv", "3x Nasdaq-100"),
    ("SPXL", "SPXL_5min_6Years.csv", "3x S&P 500"),
    ("FAS", "FAS_1min.csv", "3x financials"),
    ("TECL", f"{O}/TECL_daily_ibkr.csv", "3x technology"),
    ("TNA", f"{O}/TNA_daily_ibkr.csv", "3x small cap"),
    ("LABU", f"{O}/LABU_daily_ibkr.csv", "3x biotech"),
    ("UTSL", f"{O}/UTSL_daily_ibkr.csv", "3x utilities"),
    ("XLU", f"{O}/XLU_daily_ibkr.csv", "1x utilities"),
    ("QLD", f"{O}/QLD_daily_ibkr.csv", "2x Nasdaq-100"),
    ("SOXX", "SOXX_5min_6Years.csv", "1x semis"),
    ("TMF", f"{O}/TMF_daily_ibkr.csv", "3x 20y Treasury"),
    ("TYD", f"{O}/TYD_daily_ibkr.csv", "3x 7-10y Treasury"),
    ("UBT", f"{O}/UBT_daily_ibkr.csv", "2x 20y Treasury"),
    ("TLT", f"{O}/TLT_daily_ibkr.csv", "1x 20y Treasury"),
    ("HYG", f"{O}/HYG_daily_ibkr.csv", "high-yield credit"),
    ("SQQQ", f"{O}/SQQQ_daily_ibkr.csv", "-3x Nasdaq-100"),
    ("SOXS", "SOXS_1min.csv", "-3x semis"),
]


def load(path):
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, path)) as f:
        r = csv.reader(f); next(r)
        for a in r:
            s = a[0].replace(" America/New_York", "")
            try:
                k = dt.datetime.strptime(s, "%Y%m%d %H:%M:%S").date()
            except ValueError:
                k = dt.date.fromisoformat(s[:10])
            if k not in o:
                o[k] = float(a[1]); d.append(k)
            c[k] = float(a[4])
    return d, o, c


def build(path):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    out = {}
    for i in range(20, len(d) - 1):
        out[d[i]] = dict(rv=stdev(dr[i - 20:i]) * (252 ** 0.5) * 100,
                         mom=c[d[i]] / c[d[i - 20]] - 1,
                         on=o[d[i + 1]] / c[d[i]] - 1, close=c[d[i]])
    return out


def pctile(xs, p):
    s = sorted(xs); k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def walk(series, days, p, low_good=True):
    """walk-forward percentile flag on an ordered {day: value} series"""
    out, hist = {}, []
    for d in days:
        v = series[d]
        if len(hist) >= 60:
            c = pctile(hist, p if low_good else 100 - p)
            out[d] = (v < c) if low_good else (v > c)
        else:
            out[d] = False
        hist.append(v)
    return out


def curve(rets, yrs):
    if not rets:
        return (0, 0, 0, 0, 0)
    g = math.prod(1 + v for v in rets) - 1
    eq = pk = 1.0; dd = 0.0
    for v in rets:
        eq *= 1 + v; pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    m, s = mean(rets), stdev(rets) if len(rets) > 1 else 0.0
    return (g * 100, ((1 + g) ** (1 / yrs) - 1) * 100, dd * 100,
            m / s * (len(rets) / yrs) ** 0.5 if s else 0.0,
            m / (s / len(rets) ** 0.5) if s else 0.0)


def corr(a, b):
    ma, mb = mean(a), mean(b)
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else 0.0


def main():
    D = {"SOXL": build("SOXL_1min.csv")}
    meta = {}
    for sym, path, desc in CAND:
        try:
            D[sym] = build(path); meta[sym] = desc
        except FileNotFoundError:
            print(f"  [skip] {path}")

    sdays = sorted(D["SOXL"])
    sel = walk({d: D["SOXL"][d]["rv"] for d in sdays}, sdays, 60)
    days = [d for d in sdays if d.year >= START]
    ON = [d for d in days if sel[d]]
    OFF = [d for d in days if not sel[d]]
    yrs = (days[-1] - days[0]).days / 365.25
    print(f"SOXL walk-forward p60, from {START}: {len(days)} nights, "
          f"{len(ON)} ON ({len(ON)/len(days)*100:.0f}%), {len(OFF)} OFF\n")
    base = [D["SOXL"][d]["on"] - 2 * COST for d in ON]
    g, cg, dd, sh, t = curve(base, yrs)
    print(f"  SOXL alone, flat on its off-nights: {g:,.0f}%  CAGR {cg:.1f}%  "
          f"maxDD {dd:.1f}%  Sharpe {sh:.2f}  t {t:.2f}\n")

    print("=" * 112)
    print("A. AS A POSITION — behaviour on SOXL's OFF-nights, and the SWITCH strategy")
    print("=" * 112)
    print(f"  {'sym':<7}{'what':<20}{'n off':>7}{'mean/nt':>10}{'t':>7}{'corr':>7}"
          f"  |  {'SWITCH total':>13}{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}{'t':>7}")
    rows = []
    for sym, _, desc in CAND:
        if sym not in D:
            continue
        cd = sorted(D[sym])
        ce = walk({d: D[sym][d]["rv"] for d in cd}, cd, 60)
        off = [d for d in OFF if d in D[sym]]
        if len(off) < 30:
            continue
        x = [D[sym][d]["on"] for d in off]
        both = [d for d in days if d in D[sym]]
        c = corr([D["SOXL"][d]["on"] for d in both], [D[sym][d]["on"] for d in both])
        sw = []
        for d in days:
            if sel[d]:
                sw.append(D["SOXL"][d]["on"] - 2 * COST)
            elif d in D[sym] and ce.get(d):
                sw.append(D[sym][d]["on"] - 2 * COST)
        g, cg, dd, sh, tt = curve(sw, yrs)
        tx = mean(x) / (stdev(x) / len(x) ** 0.5)
        rows.append((sym, desc, len(off), mean(x), tx, c, g, cg, dd, sh, tt))
    for r in sorted(rows, key=lambda z: -z[9]):
        print(f"  {r[0]:<7}{r[1]:<20}{r[2]:>7}{r[3]*100:>9.3f}%{r[4]:>7.2f}{r[5]:>7.2f}"
              f"  |  {r[6]:>12,.0f}%{r[7]:>7.1f}%{r[8]:>7.1f}%{r[9]:>8.2f}{r[10]:>7.2f}")
    print(f"\n  (corr = correlation of raw overnight returns with SOXL over all nights)")
    print(f"  SWITCH = hold SOXL when eligible; otherwise hold the candidate when ITS")
    print(f"  own walk-forward p60 says go. Sorted by Sharpe.")

    print("\n" + "=" * 112)
    print("B. AS AN INDICATOR — does a bond signal improve SOXL's own eligibility rule?")
    print("=" * 112)
    sigs = {}
    if "TLT" in D:
        td = sorted(D["TLT"])
        sigs["TLT 20d momentum > p40"] = walk({d: D["TLT"][d]["mom"] for d in td}, td, 60, False)
        sigs["TLT RV20 < p60 (rate vol)"] = walk({d: D["TLT"][d]["rv"] for d in td}, td, 60, True)
    if "TLT" in D and "HYG" in D:
        cd = sorted(set(D["TLT"]) & set(D["HYG"]))
        rel = {d: D["HYG"][d]["mom"] - D["TLT"][d]["mom"] for d in cd}
        sigs["HYG-TLT credit spread > p40"] = walk(rel, cd, 60, False)
    print(f"  {'rule':<44}{'n':>6}{'total':>11}{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}{'t':>7}")
    g, cg, dd, sh, t = curve(base, yrs)
    print(f"  {'SOXL RV20 < p60 (the published rule)':<44}{len(base):>6}{g:>10,.0f}%"
          f"{cg:>7.1f}%{dd:>7.1f}%{sh:>8.2f}{t:>7.2f}")
    for name, flag in sigs.items():
        alone = [D["SOXL"][d]["on"] - 2 * COST for d in days if flag.get(d)]
        g, cg, dd, sh, t = curve(alone, yrs)
        print(f"  {name + '  (alone)':<44}{len(alone):>6}{g:>10,.0f}%{cg:>7.1f}%"
              f"{dd:>7.1f}%{sh:>8.2f}{t:>7.2f}")
        comb = [D["SOXL"][d]["on"] - 2 * COST for d in days if sel[d] and flag.get(d)]
        g, cg, dd, sh, t = curve(comb, yrs)
        print(f"  {name + '  AND SOXL RV20<p60':<44}{len(comb):>6}{g:>10,.0f}%{cg:>7.1f}%"
              f"{dd:>7.1f}%{sh:>8.2f}{t:>7.2f}")


if __name__ == "__main__":
    main()
