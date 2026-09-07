"""Long put financed by a short call — the overnight collar on a long position.

The debit spread failed because its second leg capped the DOWNSIDE, the very
thing the position existed for (coverage fell 23% -> 12% as gaps got worse). A
collar puts the second leg on the other side: keep the put whole, sell a call to
pay for it, and give up UPSIDE instead. That is a different trade-off, so it gets
measured rather than assumed.

  hold      100 shares of SOXL through the night
  long put  ~1-3% OTM, 3-7 DTE, bought at the 15:55 print
  short call ~1-3% OTM, same expiration, sold at the 15:55 print
  unwind    both legs at the next 09:30 print

Everything is reported as the overnight return of the WHOLE position (stock +
overlay), against holding the stock naked, because that is the comparison that
decides whether the collar is worth putting on.

Costs: four crossings (two legs, both ways), charged as a % of each leg's own
premium, same convention as put_spread.py.

Data: raw_data/SOXL_intraday_5m_exp_*.csv (prints, not quotes).
Usage:  python3 retreat_lab/collar.py
"""
import json, csv, datetime as dt, os, sys
from statistics import mean, median, stdev
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, pct

SCRATCH = "/tmp/claude-0/-home-user-TradingModel/50ac25d8-892f-559b-b09e-cc99c4333d8d/scratchpad"


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


def book(path, close, nxt):
    """-> {(exp, date): [(K, entry, exit)]} for contracts priced at both stamps."""
    px = defaultdict(dict)
    for exp, K, d, hm, p, cnt, vol in json.load(open(path)):
        px[(exp, K)][(d, hm)] = p
    out = defaultdict(list)
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
                out[(exp, D)].append((K, p, v[k2]))
    return out


def build(pb, cb, close, opn, nxt, dte_lo, dte_hi, put_m, call_m, tol=0.015):
    rows = []
    for key in set(pb) & set(cb):
        exp, D = key
        dte = (dt.date.fromisoformat(exp) - D).days
        if not (dte_lo <= dte <= dte_hi):
            continue
        S = close[D]
        pl = [L for L in pb[key] if abs(L[0] / S - 1 - put_m) <= tol]
        cl = [L for L in cb[key] if abs(L[0] / S - 1 - call_m) <= tol]
        if not pl or not cl:
            continue
        P = min(pl, key=lambda L: abs(L[0] / S - 1 - put_m))
        C = min(cl, key=lambda L: abs(L[0] / S - 1 - call_m))
        gap = opn[nxt[D]] / S - 1
        rows.append(dict(D=D, S=S, dte=dte, gap=gap,
                         Kp=P[0], Kc=C[0], pp=P[1], cp=C[1],
                         # overlay P&L in bp of spot: long put + short call
                         put=(P[2] - P[1]) / S * 10000,
                         call=(C[1] - C[2]) / S * 10000,
                         net_debit=(P[1] - C[1]) / S * 10000,
                         prem=(P[1] + C[1]) / S * 10000))
    best = {}
    for r in rows:
        if r["D"] not in best:
            best[r["D"]] = r
    return [best[d] for d in sorted(best)]


def curve(p):
    cum = pk = dd = 0.0
    for x in p:
        cum += x; pk = max(pk, cum); dd = min(dd, cum - pk)
    sh = mean(p) / stdev(p) * (252 ** 0.5) if len(p) > 1 and stdev(p) else 0
    return cum, dd, sh


def main():
    close, opn = underlying()
    days = sorted(close)
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    pb = book(os.path.join(SCRATCH, "puts.json"), close, nxt)
    cb = book(os.path.join(SCRATCH, "calls.json"), close, nxt)
    print(f"(expiration, night) buckets — puts {len(pb):,}  calls {len(cb):,}  "
          f"both {len(set(pb) & set(cb)):,}\n")

    for pm, cm, lbl in ((-0.02, 0.02, "put 2% OTM / call 2% OTM"),
                        (-0.03, 0.03, "put 3% OTM / call 3% OTM"),
                        (-0.01, 0.05, "put 1% OTM / call 5% OTM")):
        rows = build(pb, cb, close, opn, nxt, 3, 7, pm, cm)
        if len(rows) < 25:
            print(f"--- {lbl} --- n={len(rows)} (too thin)\n"); continue
        print("=" * 104)
        print(f"{lbl}, 3-7 DTE — {len(rows)} nights, "
              f"{rows[0]['D']} → {rows[-1]['D']}")
        print("=" * 104)
        nd = median([r["net_debit"] for r in rows])
        print(f"  median net debit {nd:+.0f}bp of spot "
              f"({'financed' if nd <= 0 else 'still costs'}) — "
              f"put {median([r['pp']/r['S'] for r in rows])*1e4:.0f}bp, "
              f"call {median([r['cp']/r['S'] for r in rows])*1e4:.0f}bp\n")

        stock = [r["gap"] * 10000 for r in rows]
        print(f"  {'position':<28}{'mean':>9}{'med':>9}{'sd':>9}{'worst':>10}"
              f"{'best':>10}{'total':>11}{'maxDD':>11}{'Sharpe':>8}")
        c0, d0, s0 = curve(stock)
        print(f"  {'stock alone':<28}{mean(stock):>8.1f}bp{median(stock):>8.1f}bp"
              f"{stdev(stock):>8.1f}bp{min(stock):>9.0f}bp{max(stock):>9.0f}bp"
              f"{c0:>10,.0f}bp{d0:>10,.0f}bp{s0:>8.2f}")
        for cp in (0, 2, 5, 10):
            tot = [r["gap"] * 10000 + r["put"] + r["call"]
                   - (r["pp"] + r["cp"]) / r["S"] * 10000 * cp / 100 * 2
                   for r in rows]
            cu, dd, sh = curve(tot)
            print(f"  {'stock + collar @ ' + str(cp) + '% spread':<28}"
                  f"{mean(tot):>8.1f}bp{median(tot):>8.1f}bp{stdev(tot):>8.1f}bp"
                  f"{min(tot):>9.0f}bp{max(tot):>9.0f}bp{cu:>10,.0f}bp{dd:>10,.0f}bp"
                  f"{sh:>8.2f}")

        print(f"\n  what each leg did, by what the night actually was:")
        print(f"    {'gap bucket':<18}{'n':>5}{'stock':>10}{'put leg':>10}"
              f"{'call leg':>10}{'net':>10}{'collar cover':>14}")
        for bl_, lo, hi in (("worse than -6%", -1.0, -0.06), ("-6 to -3%", -0.06, -0.03),
                            ("-3 to 0%", -0.03, 0.0), ("0 to +3%", 0.0, 0.03),
                            ("+3 to +6%", 0.03, 0.06), ("better than +6%", 0.06, 1.0)):
            b = [r for r in rows if lo <= r["gap"] < hi]
            if len(b) < 5:
                continue
            st = mean([r["gap"] * 10000 for r in b])
            pu = mean([r["put"] for r in b]); ca = mean([r["call"] for r in b])
            cov = f"{(pu + ca) / -st:>12.0%}" if st < 0 else f"{'':>12}"
            print(f"    {bl_:<18}{len(b):>5}{st:>9.0f}bp{pu:>9.0f}bp{ca:>9.0f}bp"
                  f"{pu+ca:>9.0f}bp{cov}")
        print()


def headtohead(pb, cb, close, opn, nxt):
    """Collar vs the protective put alone, on identical nights. Vol-matched,
    because a structure that cuts volatility must be compared at equal risk."""
    rows = build(pb, cb, close, opn, nxt, 3, 7, -0.03, 0.03)
    print("=" * 104)
    print(f"COLLAR vs PROTECTIVE PUT — identical {len(rows)} nights, "
          f"3% OTM put / 3% OTM call, 3-7 DTE")
    print("=" * 104)
    defs = [("stock alone", lambda r, cp: r["gap"] * 1e4),
            ("stock + long put only",
             lambda r, cp: r["gap"] * 1e4 + r["put"]
             - r["pp"] / r["S"] * 1e4 * cp / 100 * 2),
            ("stock + collar (put + call)",
             lambda r, cp: r["gap"] * 1e4 + r["put"] + r["call"]
             - (r["pp"] + r["cp"]) / r["S"] * 1e4 * cp / 100 * 2)]
    base_sd = None
    print(f"  {'position':<32}{'mean':>9}{'sd':>9}{'worst':>10}{'best':>10}"
          f"{'Sharpe':>8}{'vol-matched':>14}")
    for cp in (0, 5):
        print(f"  --- per-leg spread {cp}% ---")
        for lbl, f in defs:
            p_ = [f(r, 0 if lbl == "stock alone" else cp) for r in rows]
            _, _, sh = curve(p_); sd = stdev(p_)
            if lbl == "stock alone":
                base_sd = sd
            print(f"  {lbl:<32}{mean(p_):>8.1f}bp{sd:>8.1f}bp{min(p_):>9.0f}bp"
                  f"{max(p_):>9.0f}bp{sh:>8.2f}{mean(p_)*base_sd/sd:>12.1f}bp")

    print(f"\n  leg attribution over all {len(rows)} nights (zero spread):")
    print(f"    stock overnight drift   {mean([r['gap']*1e4 for r in rows]):>8.1f} bp/night")
    print(f"    long put leg            {mean([r['put'] for r in rows]):>8.1f} bp/night")
    print(f"    short call leg          {mean([r['call'] for r in rows]):>8.1f} bp/night")
    up = [r for r in rows if r["gap"] > 0]; dn = [r for r in rows if r["gap"] <= 0]
    print(f"\n    call leg: {len(up)} up nights {mean([r['call'] for r in up]):>7.1f}bp"
          f"   {len(dn)} down nights {mean([r['call'] for r in dn]):>6.1f}bp")
    print(f"    put  leg: {len(up)} up nights {mean([r['put'] for r in up]):>7.1f}bp"
          f"   {len(dn)} down nights {mean([r['put'] for r in dn]):>6.1f}bp")
    print(f"\n  NOTE: SOXL's overnight drift over this sample is "
          f"{mean([r['gap']*1e4 for r in rows]):.1f} bp/night "
          f"(~{mean([r['gap'] for r in rows])*252*100:.0f}%/yr from gaps alone).")
    print("  A short call is structurally punished in that regime, so the call-leg")
    print("  result is the most sample-dependent number in this lab.")


if __name__ == "__main__":
    main()
    close, opn = underlying()
    days = sorted(close)
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    pb = book(os.path.join(SCRATCH, "puts.json"), close, nxt)
    cb = book(os.path.join(SCRATCH, "calls.json"), close, nxt)
    headtohead(pb, cb, close, opn, nxt)
