"""Every strategy this lab measured, on identical terms, ranked.

Same window, same cost assumption, same metrics. Nothing here is new
measurement -- it re-runs the candidates side by side so the comparison is
apples to apples rather than assembled from separate write-ups.

Usage:  python3 retreat_lab/scoreboard.py [bps_per_side]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, tag

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0


def load():
    bars, idx = [], {}
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            idx[t] = len(bars)
            bars.append((t, float(Decimal(a[1])), float(Decimal(a[2])),
                         float(Decimal(a[3])), float(Decimal(a[4]))))
    ses, cur, d = [], [], bars[0][0].date()
    for x in bars:
        if x[0].date() != d:
            ses.append(cur); cur = []; d = x[0].date()
        cur.append(x)
    ses.append(cur)
    return bars, idx, ses


def metrics(rets, yrs, exposure):
    eq = 1.0; pk = 1.0; dd = 0.0
    for x in rets:
        eq *= (1 + x); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    sd = stdev(rets) if len(rets) > 1 else 0
    rate = len(rets) / yrs
    return dict(total=eq - 1, cagr=eq ** (1 / yrs) - 1 if eq > 0 else -1.0,
                dd=dd, sh=mean(rets) / sd * (rate ** 0.5) if sd else 0,
                n=len(rets), expo=exposure,
                t=mean(rets) / (sd / len(rets) ** 0.5) if sd else 0)


def main():
    bars, idx, ses = load()
    c = COST / 10000.0
    yrs = (bars[-1][0] - bars[0][0]).days / 365.25
    op = [s[0][1] for s in ses]; cl = [s[-1][4] for s in ses]
    dates = [s[0][0].date() for s in ses]
    N = len(bars)

    dret = [cl[i] / cl[i - 1] - 1 for i in range(1, len(ses))]
    rv = {}
    for i in range(20, len(ses)):
        rv[i] = stdev(dret[i - 20:i]) * (252 ** 0.5) * 100
    vals = sorted(rv.values())
    p60 = vals[int(len(vals) * 0.6)]; p80 = vals[int(len(vals) * 0.8)]

    on = [(op[i + 1] / cl[i] - 1) - 2 * c for i in range(len(ses) - 1)]
    on_bars = sum(1 for s in ses)             # overnight holds no session bars
    rows = []

    rows.append(("buy and hold (no trading)",
                 metrics([cl[-1] / cl[0] - 1], yrs, 1.0)))
    rows[-1][1]["n"] = 1; rows[-1][1]["sh"] = 0; rows[-1][1]["t"] = 0
    # recompute B&H drawdown on the daily path
    eq = 1.0; pk = 1.0; dd = 0.0
    for x in dret:
        eq *= (1 + x); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    rows[-1][1]["dd"] = dd
    rows[-1][1]["sh"] = mean(dret) / stdev(dret) * (252 ** 0.5)

    rows.append(("overnight only", metrics(on, yrs, 0.0)))
    sel = [on[i] for i in range(len(on)) if i in rv and rv[i] < p60]
    rows.append(("overnight, RV20 < p60", metrics(sel, yrs, 0.0)))
    sel80 = [on[i] for i in range(len(on)) if i in rv and rv[i] < p80]
    rows.append(("overnight, RV20 < p80", metrics(sel80, yrs, 0.0)))

    intr = [(cl[i] / op[i] - 1) - 2 * c for i in range(len(ses))]
    rows.append(("intraday long (open→close)", metrics(intr, yrs, 1.0)))
    rows.append(("intraday short (open→close)",
                 metrics([-(cl[i] / op[i] - 1) - 2 * c for i in range(len(ses))],
                         yrs, 1.0)))

    # best intraday bracket found in 1,024 configs
    br = []
    for s in ses:
        m = {b[0].hour * 60 + b[0].minute: k for k, b in enumerate(s)}
        k = m.get(600)
        if k is None:
            continue
        px = s[k][4]; peak = px; r = None
        for j, b in enumerate(s[k + 1:], start=1):
            fl = peak * (1 - 0.0025)
            if b[3] <= fl:
                r = fl / px - 1; break
            if b[2] >= px * 1.01:
                r = 0.01; break
            if b[2] > peak:
                peak = b[2]
            if j >= 10:
                r = b[4] / px - 1; break
        if r is None:
            r = s[-1][4] / px - 1
        br.append(r - 2 * c)
    rows.append(("best intraday bracket (of 1,024)", metrics(br, yrs, 0.02)))

    # the retreat-signal momentum trade
    f = os.path.join(ROOT, "retreat_lab/out",
                     f"retreat_episodes_1min_{tag(200, 50)}.csv")
    tr = []
    for row_ in csv.DictReader(open(f)):
        g = idx[dt.datetime.strptime(row_["trigger_ts"], "%Y-%m-%d %H:%M")]
        x = idx[dt.datetime.strptime(row_["retreat_ts"], "%Y-%m-%d %H:%M")]
        tr.append((bars[x][4] / bars[g][4] - 1) - 2 * c)
    rows.append(("2%/0.5% retreat momentum", metrics(tr, yrs, 0.122)))

    rows.sort(key=lambda r: -r[1]["total"])
    print(f"SOXL {bars[0][0]:%Y-%m-%d} → {bars[-1][0]:%Y-%m-%d} ({yrs:.1f}y), "
          f"{COST:.1f} bps per side\n")
    print(f"  {'strategy':<36}{'total':>12}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}"
          f"{'trades':>8}{'t':>7}")
    for lbl, m in rows:
        print(f"  {lbl:<36}{m['total']*100:>11,.0f}%{m['cagr']*100:>8.1f}%"
              f"{m['dd']*100:>8.1f}%{m['sh']:>8.2f}{m['n']:>8}{m['t']:>7.2f}")

    print(f"\n  Cost sensitivity of the two that beat buy-and-hold:")
    print(f"  {'bps/side':>9}{'overnight':>14}{'overnight RV20<p60':>22}")
    for cb in (0, 1, 2, 3, 5):
        cc = cb / 10000.0
        o = [(op[i + 1] / cl[i] - 1) - 2 * cc for i in range(len(ses) - 1)]
        sl = [o[i] for i in range(len(o)) if i in rv and rv[i] < p60]
        eo = 1.0
        for x in o:
            eo *= (1 + x)
        es = 1.0
        for x in sl:
            es *= (1 + x)
        print(f"  {cb:>9}{(eo-1)*100:>13,.0f}%{(es-1)*100:>21,.0f}%")


if __name__ == "__main__":
    main()
