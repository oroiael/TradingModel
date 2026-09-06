"""Selling the overnight put instead of buying it.

protection_cost.py priced the hedge. This prices the other side: sell a put at
the last print of the session (15:55), buy it back at the first print of the
next (09:30). Seller P&L per night = (entry - exit), i.e. exactly the buyer's
cost with the sign flipped -- but the two sides are NOT mirror images once you
account for the two things that actually decide this trade:

  1. the SPREAD hurts both sides. The buyer lifts the offer and hits the bid;
     the seller hits the bid and lifts the offer. A mid-market edge of a few bp
     is consumed by either.
  2. the TAIL sits on the seller. Short gamma into an overnight gap on a 3x
     levered semi ETF is the whole risk, and averages hide it.

So this reports the seller's distribution, its tail, a single-contract-per-night
equity curve with drawdown, and the break-even spread -- not just a mean.

Data: raw_data/SOXL_intraday_5m_exp_*.csv, 5-min option TRADE aggregates
(prints, not quotes). Usage:  python3 retreat_lab/premium_selling.py
"""
import json, csv, datetime as dt, os, sys
from statistics import mean, median, stdev
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, pct, CONFIGS, bl, tag

CACHE = "/tmp/claude-0/-home-user-TradingModel/50ac25d8-892f-559b-b09e-cc99c4333d8d/scratchpad/puts.json"


def underlying():
    close, opn = {}, {}
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            d = t.date()
            if d not in opn:
                opn[d] = float(a[1])
            close[d] = float(a[4])
    return close, opn


def trades():
    close, opn = underlying()
    days = sorted(close)
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    px = defaultdict(dict)
    for exp, K, d, hm, p, cnt, vol in json.load(open(CACHE)):
        px[(exp, K)][(d, hm)] = (p, cnt)
    out = []
    for (exp, K), v in px.items():
        E = dt.date.fromisoformat(exp)
        for (d, hm), (p, cnt) in v.items():
            if hm != "15:55":
                continue
            D = dt.date.fromisoformat(d)
            if D not in nxt or D not in close:
                continue
            dte = (E - D).days
            if dte < 1:
                continue
            k2 = (nxt[D].isoformat(), "09:30")
            if k2 not in v:
                continue
            S = close[D]
            out.append(dict(D=D, dte=dte, K=K, S=S, m=K / S - 1,
                            entry=p, exit=v[k2][0], cnt=cnt,
                            gap=opn[nxt[D]] / S - 1,
                            pnl=(p - v[k2][0]) / S * 10000,   # bp, seller +ve
                            prem=p / S * 10000))
    return out


def tailrow(lbl, rows):
    if len(rows) < 25:
        print(f"  {lbl:<24} n={len(rows):<5} (too thin)"); return
    p = [r["pnl"] for r in rows]
    prem = median([r["prem"] for r in rows])
    win = sum(1 for x in p if x > 0) / len(p)
    m = mean(p)
    # the ratio only means anything when the seller actually makes money
    ratio = f"{abs(min(p))/m:>7.0f}x" if m > 0 else "   mean<=0"
    print(f"  {lbl:<24} n={len(p):<5} prem {prem:>5.0f}bp  mean {m:>6.1f}bp "
          f"med {median(p):>6.1f}bp  win {win:>5.1%}  p5 {pct(p,5):>8.1f} "
          f"p1 {pct(p,1):>8.1f}  worst {min(p):>8.1f}  worst/mean {ratio}")


def main():
    tr = trades()
    print(f"paired 15:55 → next-09:30 put trades: {len(tr):,}   "
          f"{min(t['D'] for t in tr)} → {max(t['D'] for t in tr)}\n")

    print("SELLING ONE OVERNIGHT PUT — P&L in bp of the SOXL notional, seller's sign")
    print("(positive = the seller kept premium; the tail column is the whole story)\n")
    for dl, lo, hi in (("1-2 DTE", 1, 2), ("3-7 DTE", 3, 7), ("8-14 DTE", 8, 14),
                       ("15-45 DTE", 15, 45)):
        print(f"--- {dl} ---")
        for ml, mlo, mhi in (("ATM  |m|<1%", -0.01, 0.01), ("OTM 1-3%", -0.03, -0.01),
                             ("OTM 3-7%", -0.07, -0.03), ("OTM 7-15%", -0.15, -0.07)):
            tailrow(ml, [t for t in tr if lo <= t["dte"] <= hi and mlo <= t["m"] < mhi])
        print()

    # ---- one contract per night, so an equity curve is well defined
    print("=" * 100)
    print("EQUITY CURVE — one sale per night: the 3-7 DTE contract nearest 3% OTM")
    print("=" * 100)
    best = {}
    for t in tr:
        if not (3 <= t["dte"] <= 7 and -0.07 <= t["m"] < 0.01):
            continue
        k = t["D"]
        if k not in best or abs(t["m"] + 0.03) < abs(best[k]["m"] + 0.03):
            best[k] = t
    nights = [best[d] for d in sorted(best)]
    print(f"  {len(nights)} nights, {nights[0]['D']} → {nights[-1]['D']}\n")

    for sp in (0, 2, 5, 10, 20):
        p = [n["pnl"] - n["prem"] * sp / 100 for n in nights]
        eq, cum, peak, dd = [], 0.0, 0.0, 0.0
        for x in p:
            cum += x; eq.append(cum)
            peak = max(peak, cum); dd = min(dd, cum - peak)
        sh = mean(p) / stdev(p) * (252 ** 0.5) if stdev(p) else 0
        print(f"  spread {sp:>2}%  mean {mean(p):>7.1f}bp/night  total {cum:>9,.0f}bp  "
              f"maxDD {dd:>9,.0f}bp  win {sum(1 for x in p if x>0)/len(p):>5.1%}  "
              f"Sharpe(ann) {sh:>5.2f}")
    be = mean([n["pnl"] for n in nights]) / median([n["prem"] for n in nights]) * 100
    print(f"\n  break-even round-trip spread: {be:.1f}% of premium "
          f"(above this the seller loses too)")

    print("\n  five worst nights for the seller:")
    for n in sorted(nights, key=lambda x: x["pnl"])[:5]:
        print(f"    {n['D']}  strike {n['K']:>6.1f}  spot {n['S']:>7.2f}  "
              f"gap {n['gap']:>7.2%}  premium {n['prem']:>5.0f}bp  "
              f"P&L {n['pnl']:>9.1f}bp")
    inc = mean([n["pnl"] for n in nights])
    print(f"\n  one worst night = {abs(min(n['pnl'] for n in nights))/max(inc,1e-9):.0f} "
          f"nights of average income")

    print("\nBY YEAR (one sale per night, zero spread)")
    for y in sorted(set(n["D"].year for n in nights)):
        tailrow(str(y), [n for n in nights if n["D"].year == y])

    # ---- does the retreat study help pick nights to sell?
    print("\nCONDITIONING — sell only on nights with NO open episode?")
    rows = list(csv.reader(open(os.path.join(ROOT, "SOXL_1min.csv"))))[1:]
    dates, idx = [], {}
    for i, a in enumerate(rows):
        t = dt.datetime.strptime(
            a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
        idx[t] = i; dates.append(t.date())
    for up, dn in CONFIGS:
        T = lambda s: idx[dt.datetime.strptime(s, "%Y-%m-%d %H:%M")]
        openat = set()
        for r in csv.DictReader(open(os.path.join(
                ROOT, "retreat_lab/out", f"retreat_episodes_1min_{tag(up,dn)}.csv"))):
            g, x = T(r["trigger_ts"]), T(r["retreat_ts"])
            for k in range(g, x):
                if k + 1 < len(dates) and dates[k] != dates[k + 1]:
                    openat.add(dates[k])
        a = [n["pnl"] for n in nights if n["D"] not in openat]
        b = [n["pnl"] for n in nights if n["D"] in openat]
        if len(b) < 20:
            continue
        t_ = (mean(a) - mean(b)) / ((stdev(a)**2/len(a) + stdev(b)**2/len(b)) ** 0.5)
        print(f"  {bl(up)+'/'+bl(dn):<11} quiet nights n={len(a):<4} mean {mean(a):>6.1f}bp"
              f"   episode-open n={len(b):<4} mean {mean(b):>7.1f}bp   t {t_:>5.2f}")


if __name__ == "__main__":
    main()
