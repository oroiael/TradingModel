"""Out-of-sample replication: does the SOXL result hold on TQQQ and SPXL?

FAS was the only external test and it failed. That is n=1. This adds TQQQ (3x
Nasdaq-100) and SPXL (3x S&P 500), so the structural claim and the conditioner
claim are each tested on four instruments instead of two.

Two separate claims are at stake and they must not be conflated:

  STRUCTURAL   the overnight leg carries the directional drift; the intraday
               session is variance drag. Confirmed so far on SOXL, SOXS, FAS.
  CONDITIONER  low trailing vol (RV20 < p60) selects better overnight nights.
               This is the fitted part, and mechanism.py showed it is really a
               TREND proxy -- so trailing 20d return is run alongside it.

Data sources differ by instrument, so a CONTROL runs first: SOXL from daily
bars against SOXL from 1-minute bars over the same window. If daily-bar
open/close reproduces the 1-minute decomposition, the daily-sourced TQQQ
figures can be read on the same footing.

  SOXL   SOXL_1min.csv            1-min, 2019-12-31 ->
  SOXL   out/SOXL_daily_ibkr.csv  daily, IBKR, 2021-09 ->     (control)
  FAS    FAS_1min.csv             1-min, 2019-12-31 ->
  SPXL   SPXL_5min_6Years.csv     5-min, 2020-07 ->
  TQQQ   out/TQQQ_daily_ibkr.csv  daily, IBKR, 2021-09 ->

Usage:  python3 retreat_lab/replicate.py [bps_per_side]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = (float(sys.argv[1]) if len(sys.argv) > 1 else 1.0) / 10000.0

SRC = [("SOXL", "SOXL_1min.csv", "1-min"),
       ("SOXL-daily", "retreat_lab/out/SOXL_daily_ibkr.csv", "daily"),
       ("FAS", "FAS_1min.csv", "1-min"),
       ("SPXL", "SPXL_5min_6Years.csv", "5-min"),
       ("TQQQ", "retreat_lab/out/TQQQ_daily_ibkr.csv", "daily")]


def load(path):
    """-> ordered days, open[d], close[d]. Handles both bar-grid and daily files."""
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
    rows = []
    for i in range(20, len(d) - 1):
        rows.append(dict(date=d[i], days=(d[i + 1] - d[i]).days,
                         rv=stdev(dr[i - 20:i]) * (252 ** 0.5) * 100,
                         mom=c[d[i]] / c[d[i - 20]] - 1,
                         on=o[d[i + 1]] / c[d[i]] - 1,
                         idy=c[d[i + 1]] / o[d[i + 1]] - 1,
                         full=c[d[i + 1]] / c[d[i]] - 1))
    return rows


def pctile(xs, p):
    s = sorted(xs); k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def curve(rets, yrs):
    g = math.prod(1 + v for v in rets) - 1
    eq = pk = 1.0; dd = 0.0
    for v in rets:
        eq *= 1 + v; pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    m, s = mean(rets), stdev(rets)
    return (g * 100, ((1 + g) ** (1 / yrs) - 1) * 100, dd * 100,
            m / s * (len(rets) / yrs) ** 0.5, m / (s / len(rets) ** 0.5))


def section(title):
    print("\n" + "=" * 104); print(title); print("=" * 104)


def main():
    data = {}
    for sym, path, res in SRC:
        try:
            data[sym] = (build(path), res)
        except FileNotFoundError:
            print(f"  [skip] {path} not present")

    section("CONTROL — does a daily bar reproduce the 1-minute decomposition?")
    a, b = data["SOXL"][0], data["SOXL-daily"][0]
    lo = max(a[0]["date"], b[0]["date"]); hi = min(a[-1]["date"], b[-1]["date"])
    A = {r["date"]: r for r in a if lo <= r["date"] <= hi}
    B = {r["date"]: r for r in b if lo <= r["date"] <= hi}
    k = sorted(set(A) & set(B))
    print(f"  {len(k)} shared sessions, {lo} → {hi}")
    print(f"  {'leg':<16}{'from 1-min':>14}{'from daily':>14}{'difference':>14}")
    for leg in ("on", "idy", "full"):
        x = mean([A[d][leg] for d in k]); y = mean([B[d][leg] for d in k])
        print(f"  {leg:<16}{x*100:>13.4f}%{y*100:>13.4f}%{(y-x)*1e4:>+13.2f}bp")
    corr_on = (lambda u, v: (sum((p - mean(u)) * (q - mean(v)) for p, q in zip(u, v))
                             / ((sum((p - mean(u))**2 for p in u)
                                 * sum((q - mean(v))**2 for q in v)) ** 0.5)))(
        [A[d]["on"] for d in k], [B[d]["on"] for d in k])
    print(f"  overnight-return correlation between the two sources: {corr_on:.5f}")

    section("1. THE STRUCTURAL CLAIM — overnight drift vs intraday variance drag")
    print(f"  {'symbol':<12}{'src':<8}{'span':>24}{'n':>6}{'buy&hold':>11}"
          f"{'overnight':>12}{'intraday':>11}{'on mean/nt':>12}{'t':>7}")
    for sym in data:
        rows, res = data[sym]
        yrs = (rows[-1]["date"] - rows[0]["date"]).days / 365.25
        on = math.prod(1 + r["on"] for r in rows) - 1
        iy = math.prod(1 + r["idy"] for r in rows) - 1
        bh = math.prod(1 + r["full"] for r in rows) - 1
        x = [r["on"] for r in rows]
        print(f"  {sym:<12}{res:<8}{str(rows[0]['date'])+'→'+str(rows[-1]['date']):>24}"
              f"{len(rows):>6}{bh*100:>10.0f}%{on*100:>11.0f}%{iy*100:>10.0f}%"
              f"{mean(x)*100:>11.3f}%{mean(x)/(stdev(x)/len(x)**0.5):>7.2f}")

    section("2. THE CONDITIONER — vol filter vs trend filter, each on its own data")
    for sym in data:
        if sym == "SOXL-daily":
            continue
        rows, res = data[sym]
        yrs = (rows[-1]["date"] - rows[0]["date"]).days / 365.25
        print(f"\n  {sym} ({res}, {rows[0]['date']} → {rows[-1]['date']}, {yrs:.1f}y)")
        print(f"  {'rule (keep 60% of nights)':<34}{'n':>6}{'total':>11}{'CAGR':>8}"
              f"{'maxDD':>8}{'Sharpe':>8}{'t':>7}")
        allr = [r["on"] - 2 * COST for r in rows]
        g, cg, dd, sh, t = curve(allr, yrs)
        print(f"  {'hold every night':<34}{len(allr):>6}{g:>10.0f}%{cg:>7.1f}%"
              f"{dd:>7.1f}%{sh:>8.2f}{t:>7.2f}")
        for lbl, key, low_good in (("LOW RV20 (the published rule)", "rv", True),
                                   ("HIGH trailing 20d return", "mom", False)):
            vals = [r[key] for r in rows]
            cut = pctile(vals, 60 if low_good else 40)
            sel = [r["on"] - 2 * COST for r in rows
                   if (r[key] < cut if low_good else r[key] > cut)]
            g, cg, dd, sh, t = curve(sel, yrs)
            print(f"  {lbl:<34}{len(sel):>6}{g:>10.0f}%{cg:>7.1f}%{dd:>7.1f}%"
                  f"{sh:>8.2f}{t:>7.2f}")

    section("3. COMMON WINDOW — every instrument on exactly the same sessions")
    keys = [s for s in data if s != "SOXL-daily"]
    lo = max(data[s][0][0]["date"] for s in keys)
    hi = min(data[s][0][-1]["date"] for s in keys)
    idx = {s: {r["date"]: r for r in data[s][0] if lo <= r["date"] <= hi} for s in keys}
    common = sorted(set.intersection(*[set(idx[s]) for s in keys]))
    yrs = (common[-1] - common[0]).days / 365.25
    print(f"  {len(common)} sessions, {lo} → {hi} ({yrs:.1f}y)\n")
    print(f"  {'symbol':<10}{'overnight':>11}{'intraday':>11}{'on t':>7}   |  "
          f"{'RV20<p60 CAGR':>15}{'Sharpe':>9}{'t':>7}   |  {'trend CAGR':>12}{'Sharpe':>9}{'t':>7}")
    for s in keys:
        rr = [idx[s][d] for d in common]
        on = math.prod(1 + r["on"] for r in rr) - 1
        iy = math.prod(1 + r["idy"] for r in rr) - 1
        x = [r["on"] for r in rr]
        cut = pctile([r["rv"] for r in rr], 60)
        v = curve([r["on"] - 2 * COST for r in rr if r["rv"] < cut], yrs)
        mcut = pctile([r["mom"] for r in rr], 40)
        m = curve([r["on"] - 2 * COST for r in rr if r["mom"] > mcut], yrs)
        print(f"  {s:<10}{on*100:>10.0f}%{iy*100:>10.0f}%"
              f"{mean(x)/(stdev(x)/len(x)**0.5):>7.2f}   |  {v[1]:>14.1f}%{v[3]:>9.2f}{v[4]:>7.2f}"
              f"   |  {m[1]:>11.1f}%{m[3]:>9.2f}{m[4]:>7.2f}")


if __name__ == "__main__":
    main()
