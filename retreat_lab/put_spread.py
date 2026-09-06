"""Selling -- and buying -- the overnight put SPREAD instead of the naked put.

premium_selling.py showed the naked overnight seller wins 57-63% of nights,
carries a -1,200 to -1,500bp tail, and breaks even only below a 1.8% round-trip
spread. A vertical caps that tail. It also gives up credit and doubles the
crossings, so whether it helps is an empirical question, not a design opinion.

  short leg  put at K1 (nearest a target moneyness)
  long leg   put at K2 < K1, roughly `width` below, SAME expiration
  entry      both legs at the 15:55 print on day D
  exit       both legs at the 09:30 print on day D+1
  max loss   (K1 - K2) - credit  -- the whole point of the structure

Return is reported on RISK (max loss), which is the correct denominator for a
defined-risk spread, as well as in bp of spot for comparability with the naked
and long-put numbers.

Costs: a naked round trip crosses twice; a vertical crosses FOUR times (two
legs, both ways). The cost knob is a % of each leg's own premium, applied on
every crossing, so a vertical pays roughly double a naked position at the same
per-leg spread -- which is the pessimistic and realistic assumption unless the
package fills better than its legs.

Data: raw_data/SOXL_intraday_5m_exp_*.csv (prints, not quotes).
Usage:  python3 retreat_lab/put_spread.py
"""
import json, csv, datetime as dt, os, sys
from statistics import mean, median, stdev
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, pct

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


def paired():
    """-> {(exp, date): [(K, entry, exit), ...]} for contracts priced at both stamps."""
    close, opn = underlying()
    days = sorted(close)
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    px = defaultdict(dict)
    for exp, K, d, hm, p, cnt, vol in json.load(open(CACHE)):
        px[(exp, K)][(d, hm)] = p
    book = defaultdict(list)
    for (exp, K), v in px.items():
        E = dt.date.fromisoformat(exp)
        for (d, hm), p in v.items():
            if hm != "15:55":
                continue
            D = dt.date.fromisoformat(d)
            if D not in nxt or D not in close:
                continue
            if (E - D).days < 1:
                continue
            k2 = (nxt[D].isoformat(), "09:30")
            if k2 in v:
                book[(exp, D)].append((K, p, v[k2]))
    return book, close, opn, nxt


def build(book, close, opn, nxt, dte_lo, dte_hi, m_target, width_pct):
    """One spread per (expiration, night): short nearest m_target, long ~width below."""
    out = []
    for (exp, D), legs in book.items():
        dte = (dt.date.fromisoformat(exp) - D).days
        if not (dte_lo <= dte <= dte_hi):
            continue
        S = close[D]
        legs = sorted(legs)
        short = min(legs, key=lambda L: abs(L[0] / S - 1 - m_target))
        if abs(short[0] / S - 1 - m_target) > 0.015:
            continue
        tgt = short[0] - width_pct * S
        cands = [L for L in legs if L[0] < short[0]]
        if not cands:
            continue
        long_ = min(cands, key=lambda L: abs(L[0] - tgt))
        w = short[0] - long_[0]
        if not (0.5 * width_pct * S <= w <= 2.0 * width_pct * S):
            continue
        credit = short[1] - long_[1]
        if credit <= 0 or credit >= w:          # no credit, or free money = bad print
            continue
        exit_val = short[2] - long_[2]
        out.append(dict(D=D, S=S, K1=short[0], K2=long_[0], dte=dte, w=w,
                        credit=credit, maxloss=w - credit,
                        pnl=credit - exit_val,
                        p1=short[1], p2=long_[1],
                        gap=opn[nxt[D]] / S - 1))
    # one per night, keep the first expiration seen for that date
    best = {}
    for s in out:
        if s["D"] not in best:
            best[s["D"]] = s
    return [best[d] for d in sorted(best)]


def report(sp, lbl, cost_pct):
    if len(sp) < 25:
        print(f"  {lbl:<26} n={len(sp):<4} (too thin)"); return
    # cost: 4 crossings, cost_pct of each leg's own premium each time
    c = [(s["p1"] + s["p2"]) * cost_pct / 100 * 2 for s in sp]
    pnl_bp = [(s["pnl"] - ci) / s["S"] * 10000 for s, ci in zip(sp, c)]
    ror = [(s["pnl"] - ci) / s["maxloss"] for s, ci in zip(sp, c)]
    cred = [s["credit"] / s["maxloss"] for s in sp]
    win = sum(1 for x in pnl_bp if x > 0) / len(pnl_bp)
    print(f"  {lbl:<26} n={len(sp):<4} cred/risk {median(cred):>5.0%}  "
          f"mean {mean(pnl_bp):>7.1f}bp  med {median(pnl_bp):>6.1f}bp  win {win:>5.1%}  "
          f"RoR mean {mean(ror):>7.2%}  worst {min(pnl_bp):>8.1f}bp")


def main():
    book, close, opn, nxt = paired()
    print(f"(expiration, night) buckets with paired legs: {len(book):,}\n")

    print("SELLING AN OVERNIGHT PUT SPREAD — short leg 3% OTM, 3-7 DTE")
    print("cred/risk = credit as a share of max loss; RoR = return on max loss\n")
    for wp in (0.02, 0.05, 0.10):
        sp = build(book, close, opn, nxt, 3, 7, -0.03, wp)
        print(f"--- width ~{wp:.0%} of spot ---")
        for cp in (0, 2, 5, 10):
            report(sp, f"per-leg spread {cp}%", cp)
        print()

    print("=" * 100)
    print("HEAD TO HEAD at 3-7 DTE, short leg 3% OTM, width 5% of spot")
    print("=" * 100)
    sp = build(book, close, opn, nxt, 3, 7, -0.03, 0.05)
    if len(sp) >= 25:
        print(f"  {len(sp)} nights, {sp[0]['D']} → {sp[-1]['D']}")
        print(f"  median credit {median([s['credit']/s['S'] for s in sp])*10000:>5.0f}bp of spot, "
              f"median max loss {median([s['maxloss']/s['S'] for s in sp])*10000:>5.0f}bp")
        print()
        print(f"  {'per-leg spread':<18}{'mean/night':>12}{'total':>11}{'maxDD':>11}"
              f"{'win':>7}{'Sharpe':>8}{'worst':>10}")
        for cp in (0, 2, 5, 10):
            c = [(s["p1"] + s["p2"]) * cp / 100 * 2 for s in sp]
            p = [(s["pnl"] - ci) / s["S"] * 10000 for s, ci in zip(sp, c)]
            cum = pk = dd = 0.0
            for x in p:
                cum += x; pk = max(pk, cum); dd = min(dd, cum - pk)
            sh = mean(p) / stdev(p) * (252 ** 0.5) if stdev(p) else 0
            print(f"  {cp:>2}%{'':<15}{mean(p):>11.1f}bp{cum:>10,.0f}bp{dd:>10,.0f}bp"
                  f"{sum(1 for x in p if x>0)/len(p):>7.1%}{sh:>8.2f}{min(p):>9.1f}bp")
        base = [s["pnl"] / s["S"] * 10000 for s in sp]
        prem = median([(s["p1"] + s["p2"]) / s["S"] * 10000 for s in sp])
        print(f"\n  break-even per-leg spread: "
              f"{mean(base)/(prem*2)*100:.1f}% of each leg's premium")
        print("\n  five worst nights:")
        for s in sorted(sp, key=lambda x: x["pnl"])[:5]:
            print(f"    {s['D']}  K {s['K2']:>6.1f}/{s['K1']:>6.1f}  spot {s['S']:>7.2f}  "
                  f"gap {s['gap']:>7.2%}  credit {s['credit']/s['S']*1e4:>5.0f}bp  "
                  f"P&L {s['pnl']/s['S']*1e4:>8.1f}bp  (capped at "
                  f"{-s['maxloss']/s['S']*1e4:.0f}bp)")


def buyside(book, close, opn, nxt):
    """Buying the vertical (debit put spread) as CHEAPER PROTECTION: long a put
    ~1% OTM, short one below it. The question is not expectancy -- it is whether
    capped protection still covers the nights it exists for."""
    print("\n" + "=" * 100)
    print("BUYING THE SPREAD — long put ~1% OTM, short leg below, 3-7 DTE")
    print("=" * 100)
    for wp in (0.02, 0.05, 0.10):
        sp = build(book, close, opn, nxt, 3, 7, -0.01, wp)
        if len(sp) < 25:
            continue
        # long vertical = short vertical negated; costs hit BOTH sides the same way
        print(f"\n--- width ~{wp:.0%} of spot ---   n={len(sp)}   "
              f"median debit {median([s['maxloss']/s['S'] for s in sp])*1e4:.0f}bp, "
              f"max payoff {median([s['credit']/s['S'] for s in sp])*1e4:.0f}bp")
        for cp in (0, 2, 5, 10):
            c = [(s["p1"] + s["p2"]) * cp / 100 * 2 for s in sp]
            p = [(-s["pnl"] - ci) / s["S"] * 10000 for s, ci in zip(sp, c)]
            print(f"  per-leg spread {cp:>2}%   mean {mean(p):>7.1f}bp   "
                  f"med {median(p):>7.1f}bp   win {sum(1 for x in p if x>0)/len(p):>5.1%}   "
                  f"best {max(p):>7.1f}bp")

    print("\n" + "=" * 100)
    print("DOES CAPPED PROTECTION COVER THE NIGHTS IT EXISTS FOR?")
    print("coverage = realised option P&L / the underlying loss on that night")
    print("=" * 100)
    naked = {}
    for (exp, D), legs in book.items():
        dte = (dt.date.fromisoformat(exp) - D).days
        if not (3 <= dte <= 7):
            continue
        S = close[D]
        cands = [L for L in legs if -0.02 <= L[0] / S - 1 < 0.0]
        if cands:
            L = min(cands, key=lambda L: abs(L[0] / S - 1 + 0.01))
            if D not in naked:
                naked[D] = (L[2] - L[1]) / S * 10000      # long put P&L, bp
    sp = {s["D"]: s for s in build(book, close, opn, nxt, 3, 7, -0.01, 0.05)}
    both = sorted(set(naked) & set(sp))
    downs = [d for d in both if sp[d]["gap"] < 0]
    print(f"\n  nights with both a naked put and a 5%-wide spread priced: {len(both)}"
          f"   ({len(downs)} gapped down)\n")
    print(f"  {'gap bucket':<18}{'n':>5}{'und loss':>11}{'naked put':>12}{'cover':>8}"
          f"{'spread':>11}{'cover':>8}")
    for lbl, lo, hi in (("0 to -1%", -0.01, 0.0), ("-1 to -3%", -0.03, -0.01),
                        ("-3 to -6%", -0.06, -0.03), ("worse than -6%", -1.0, -0.06)):
        ds = [d for d in downs if lo <= sp[d]["gap"] < hi]
        if len(ds) < 5:
            continue
        ul = [-sp[d]["gap"] * 10000 for d in ds]
        nk = [naked[d] for d in ds]
        vr = [-sp[d]["pnl"] / sp[d]["S"] * 10000 for d in ds]
        print(f"  {lbl:<18}{len(ds):>5}{mean(ul):>10.0f}bp{mean(nk):>11.0f}bp"
              f"{mean(nk)/mean(ul):>7.0%}{mean(vr):>10.0f}bp{mean(vr)/mean(ul):>7.0%}")
    print("\n  the five worst gaps, night by night:")
    print(f"    {'date':<12}{'gap':>8}{'und loss':>11}{'naked put':>11}{'spread':>10}"
          f"{'spread cap':>12}")
    for d in sorted(downs, key=lambda d: sp[d]["gap"])[:5]:
        s = sp[d]
        print(f"    {str(d):<12}{s['gap']:>7.1%}{-s['gap']*1e4:>10.0f}bp"
              f"{naked[d]:>10.0f}bp{-s['pnl']/s['S']*1e4:>9.0f}bp"
              f"{s['credit']/s['S']*1e4:>11.0f}bp")


if __name__ == "__main__":
    main()
    book, close, opn, nxt = paired()
    buyside(book, close, opn, nxt)
