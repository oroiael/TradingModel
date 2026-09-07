"""Position sizing caps, and a real put overlay, on the p60 overnight strategy.

Two questions:
  1. what does capping position size do, versus committing the whole balance?
  2. what does buying a put every night the strategy is long actually do to
     terminal wealth and drawdown -- priced from real option trades, not assumed?

Sizing: fraction f of equity is committed each night, the rest held in cash at
0%. For a high-variance strategy this is not merely a scaling: terminal wealth
is concave in f because variance drag grows with f^2 while return grows with f,
so there is an interior optimum. That optimum is reported.

Hedge: on every night with a paired 15:55 -> next-09:30 put print in
raw_data/SOXL_intraday_5m_exp_*.csv, the put's REALISED P&L is added to the
night. Hedged and unhedged are compared over exactly the same nights, so no
approximation is smuggled in for nights without option data.

Usage:  python3 retreat_lab/sizing_and_hedge.py [bps_per_side] [capital]
"""
import csv, json, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
CAP = float(sys.argv[2]) if len(sys.argv) > 2 else 100_000.0
BURN = 252
SCRATCH = "/tmp/claude-0/-home-user-TradingModel/50ac25d8-892f-559b-b09e-cc99c4333d8d/scratchpad"


def load():
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
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


def equity(rets, f, cap=CAP):
    """f of the balance committed, rest in cash. -> final, maxDD, path."""
    eq = cap; pk = cap; dd = 0.0
    for r in rets:
        eq *= (1 + f * r)
        if eq <= 0:
            return 0.0, -1.0
        pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    return eq, dd


def puts(days, cl, op):
    """-> {date: put P&L as a fraction of spot} for the cheapest usable tenor."""
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    out = {}
    for tag_, lo, hi, mlo, mhi in (("short", 3, 7, -0.07, 0.01),
                                   ("long", 15, 45, -0.07, 0.01)):
        px = {}
        for exp, K, dd, hm, p, cnt, vol in json.load(
                open(os.path.join(SCRATCH, "puts.json"))):
            px.setdefault((exp, K), {})[(dd, hm)] = p
        book = {}
        for (exp, K), v in px.items():
            E = dt.date.fromisoformat(exp)
            for (dd, hm), p in v.items():
                if hm != "15:55":
                    continue
                D = dt.date.fromisoformat(dd)
                if D not in nxt or D not in cl:
                    continue
                if not (lo <= (E - D).days <= hi):
                    continue
                k2 = (nxt[D].isoformat(), "09:30")
                if k2 not in v:
                    continue
                m = K / cl[D] - 1
                if not (mlo <= m < mhi):
                    continue
                # keep the contract nearest 3% OTM for that night
                if D not in book or abs(m + 0.03) < abs(book[D][0] + 0.03):
                    book[D] = (m, (v[k2] - p) / cl[D])
        out[tag_] = {d: v[1] for d, v in book.items()}
    return out


def main():
    days, op, cl = load()
    c = COST / 10000.0
    dret = [cl[days[i]] / cl[days[i - 1]] - 1 for i in range(1, len(days))]
    rv = {}
    for i in range(20, len(days)):
        rv[i] = stdev(dret[i - 20:i]) * (252 ** 0.5) * 100
    alln = [(i, (op[days[i + 1]] / cl[days[i]] - 1) - 2 * c)
            for i in range(len(days) - 1) if i in rv]
    first = alln[0][0]
    live = [(i, r) for i, r in alln if i >= first + BURN]
    sel = []
    for i, r in live:
        hist = [rv[j] for j in sorted(rv) if j < i]
        if len(hist) >= 60 and rv[i] < pctile(hist, 60):
            sel.append((days[i], r))
    rets = [r for _, r in sel]
    # CAGR must be over the FULL live window -- you are in the strategy the whole
    # time, including the nights it stands aside -- not the first-to-last-selected
    # span, which would credit it for the flat periods it sat out.
    yrs = (days[live[-1][0]] - days[live[0][0]]).days / 365.25
    print(f"p60 overnight, walk-forward, {len(rets)} nights, "
          f"{sel[0][0]} → {sel[-1][0]} ({yrs:.1f}y), ${CAP:,.0f} start\n")

    print("=" * 96)
    print("1. POSITION SIZE CAP — fraction of the balance committed each night")
    print("=" * 96)
    print(f"  {'f':>6}{'final equity':>16}{'CAGR':>9}{'maxDD':>9}"
          f"{'ann vol':>10}{'Sharpe':>9}{'worst night $':>15}")
    best = (None, -1)
    for f in (0.10, 0.25, 0.40, 0.50, 0.75, 1.00, 1.50, 2.00, 2.50,
              3.00, 3.50, 4.00, 5.00):
        e, dd = equity(rets, f)
        cagr = (e / CAP) ** (1 / yrs) - 1 if e > 0 else -1
        sd = stdev([f * r for r in rets]) * (len(rets) / yrs) ** 0.5
        sh = mean([f * r for r in rets]) / stdev([f * r for r in rets]) \
            * ((len(rets) / yrs) ** 0.5)
        print(f"  {f:>6.2f}{e:>15,.0f}{cagr*100:>8.1f}%{dd*100:>8.1f}%"
              f"{sd*100:>9.1f}%{sh:>9.2f}{min(rets)*f*CAP:>14,.0f}")
        if e > best[1]:
            best = (f, e)
    print(f"\n  terminal wealth peaks near f = {best[0]:.2f}. Sharpe is CONSTANT in f "
          f"(scaling a return\n  series scales mean and sd together), so f is purely a "
          f"risk-appetite dial, not an\n  optimisation -- the only thing that changes "
          f"is where variance drag (f^2) finally\n  overtakes return (f). Full "
          f"reinvestment is f = 1.00; f > 1 needs margin, whose\n  cost is NOT charged "
          f"here and would move the peak left.")
    print(f"  a FIXED $100,000 stake, never compounded: "
          f"${CAP + sum(rets) * CAP:,.0f} "
          f"(sum of {len(rets)} nightly P&Ls, no reinvestment)")

    print("\n" + "=" * 96)
    print("2. PUT OVERLAY — one put per night, priced from real option trades")
    print("=" * 96)
    pb = puts(days, cl, op)
    for tag_, lbl in (("short", "3-7 DTE"), ("long", "15-45 DTE")):
        cov = [(d, r) for d, r in sel if d in pb[tag_]]
        if len(cov) < 50:
            print(f"  {lbl}: only {len(cov)} nights covered, too thin"); continue
        y2 = (days[live[-1][0]] - days[live[0][0]]).days / 365.25
        un = [r for _, r in cov]
        hd = [r + pb[tag_][d] for d, r in cov]
        print(f"\n  {lbl}, {len(cov)} of {len(sel)} p60 nights have a paired print "
              f"({len(cov)/len(sel):.0%} coverage)")
        print(f"  {'variant':<22}{'final':>14}{'CAGR':>9}{'maxDD':>9}"
              f"{'worst night':>13}{'ann vol':>10}")
        for nm, v in (("unhedged", un), ("+ long put", hd)):
            e, dd = equity(v, 1.0)
            sd = stdev(v) * (len(v) / y2) ** 0.5
            print(f"  {nm:<22}{e:>13,.0f}{((e/CAP)**(1/y2)-1)*100:>8.1f}%"
                  f"{dd*100:>8.1f}%{min(v)*100:>12.1f}%{sd*100:>9.1f}%")
        drag = mean(pb[tag_][d] for d, _ in cov)
        print(f"  put cost {drag*10000:>6.1f} bp/night on these nights "
              f"(prints, so a lower bound — add 16-33 bp for real spreads)")
        # what the hedge is worth at various spread assumptions
        print(f"  {'with spread':<22}{'final':>14}{'CAGR':>9}{'maxDD':>9}")
        prem = 0.033 if tag_ == "short" else 0.072
        for sp in (0, 5, 10):
            v = [r + pb[tag_][d] - prem * sp / 100 * 2 for d, r in cov]
            e, dd = equity(v, 1.0)
            print(f"  {'  +' + str(sp) + '% round trip':<22}{e:>13,.0f}"
                  f"{((e/CAP)**(1/y2)-1)*100:>8.1f}%{dd*100:>8.1f}%")


if __name__ == "__main__":
    main()
