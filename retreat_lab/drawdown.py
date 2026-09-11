"""What can actually mitigate the drawdown, other than holding less?

The -29.5% drawdown on the p60 overnight strategy is a TAIL problem: 5 nights
out of 61 account for 88% of it, and across the whole sample only 13 nights of
979 are worse than -8%. That shape is what each candidate below is tested
against.

Candidates, each a genuinely different mechanism:
  1. continuous vol scaling instead of the binary filter
  2. a SOXS overlay -- the -3x mirror, no option premium
  3. a UVXY overlay -- convex crash hedge
  4. cutting weekend/holiday gaps, where the fat tail is assumed to live
  5. a real put overlay, priced from actual 15:55 -> 09:30 prints
  6. diversifying across SOXL / FAS / SPXL overnight legs
  7. expressing the same exposure as 3x SOXX instead of 1x SOXL

The put leg uses (entry - exit)/S from real prints, which is the COMPLETE hedge
P&L -- it already nets the tail payoffs against the premium. Modelling a payoff
on top of a measured net cost double-counts the benefit, which is exactly the
error that makes a put overlay look viable when it is not.

Needs the cached put extract (see protection_cost.py) for section 5; that
section is skipped if it is absent.

Usage:  python3 retreat_lab/drawdown.py [bps_per_side]
"""
import csv, datetime as dt, json, math, os, sys
from collections import defaultdict
from statistics import mean, stdev, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = (float(sys.argv[1]) if len(sys.argv) > 1 else 1.0) / 10000.0
CACHE = ("/tmp/claude-0/-home-user-TradingModel/"
         "50ac25d8-892f-559b-b09e-cc99c4333d8d/scratchpad/puts.json")


def ons(path):
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, path)) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            k = t.date()
            if k not in o:
                o[k] = float(a[1]); d.append(k)
            c[k] = float(a[4])
    return d, o, c


def pctile(xs, p):
    s = sorted(xs); k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def nights(path, gross=False):
    d, o, c = ons(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return [dict(date=d[i], nxt=d[i + 1], gap=(d[i + 1] - d[i]).days,
                 rv=stdev(dr[i - 20:i]) * (252 ** 0.5) * 100,
                 on=o[d[i + 1]] / c[d[i]] - 1 - (0 if gross else 2 * COST))
            for i in range(20, len(d) - 1)]


def stat(rets, yrs):
    g = math.prod(1 + v for v in rets) - 1
    eq = pk = 1.0; dd = 0.0
    for v in rets:
        eq *= 1 + v; pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    m, s = mean(rets), stdev(rets)
    return g * 100, ((1 + g) ** (1 / yrs) - 1) * 100, dd * 100, m / s * (len(rets) / yrs) ** 0.5


def row(lbl, rets, yrs, extra=""):
    t, cg, dd, sh = stat(rets, yrs)
    print(f"  {lbl:<40}{t:>10.0f}%{cg:>8.1f}%{dd:>8.1f}%{sh:>8.2f}   {extra}")


HDR = f"  {'variant':<40}{'total':>10}{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}"


def main():
    rows = nights("SOXL_1min.csv")
    cut = pctile([r["rv"] for r in rows], 60)
    F = [r for r in rows if r["rv"] < cut]
    YRS = len(rows) / 252.0
    base = [r["on"] for r in F]

    print("=" * 104)
    print("THE SHAPE OF THE PROBLEM — the drawdown is a tail, not a grind")
    print("=" * 104)
    x = sorted(base)
    print(f"  {len(F)} nights, total {(math.prod(1+v for v in base)-1)*100:.0f}%")
    for k in (1, 5, 10, 20):
        print(f"    removing the {k:>2} worst nights -> "
              f"{(math.prod(1+v for v in x[k:])-1)*100:>8.0f}%   "
              f"(they sum to {sum(x[:k])*100:>6.1f}%)")
    print(f"  nights worse than -5%: {sum(1 for v in x if v<-.05)}   "
          f"-8%: {sum(1 for v in x if v<-.08)}   -10%: {sum(1 for v in x if v<-.10)}")

    print("\n" + "=" * 104)
    print("0. THE SIZING FRONTIER — what every candidate below has to beat")
    print("=" * 104)
    print(f"  {'size':<40}{'total':>10}{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}")
    for f_ in (0.25, 0.50, 0.75, 1.00, 1.50, 2.00):
        row(f"{f_:.2f}x", [f_ * v for v in base], YRS)

    print("\n" + "=" * 104)
    print("1. CONTINUOUS VOL SCALING instead of the binary filter")
    print("=" * 104)
    print(HDR + "   avg size")
    for tgt in (60, 80):
        w = [min(1.0, tgt / r["rv"]) for r in F]
        row(f"p60 filter + target {tgt}% vol",
            [wi * r["on"] for wi, r in zip(w, F)], YRS, f"{mean(w):.2f}x")
    for tgt in (60, 100):
        w = [min(1.5, tgt / r["rv"]) for r in rows]
        row(f"no filter, target {tgt}% vol, cap 1.5x",
            [wi * r["on"] for wi, r in zip(w, rows)], YRS, f"{mean(w):.2f}x")

    print("\n" + "=" * 104)
    print("2. SOXS OVERLAY (-3x mirror) vs simply holding less SOXL")
    print("=" * 104)
    ds, os_, cs = ons("SOXS_1min.csv")
    pair = [(r, os_[r["nxt"]] / cs[r["date"]] - 1) for r in F
            if r["date"] in cs and r["nxt"] in os_]
    print(f"  {len(pair)} of {len(F)} nights covered")
    print(HDR)
    for h in (0.25, 0.50):
        row(f"SOXL 100% + SOXS {h:.0%}",
            [r["on"] + h * (s - 2 * COST) for r, s in pair], YRS)
    for f_ in (0.75, 0.50):
        row(f"just hold {f_:.0%} SOXL", [f_ * r["on"] for r, _ in pair], YRS)

    print("\n" + "=" * 104)
    print("3. UVXY OVERLAY — convex crash hedge")
    print("=" * 104)
    du, ou, cu = ons("UVXY_1min.csv")
    pu = [(r, ou[r["nxt"]] / cu[r["date"]] - 1) for r in F
          if r["date"] in cu and r["nxt"] in ou]
    w10 = sorted(pu, key=lambda z: z[0]["on"])[:10]
    print(f"  UVXY overnight mean {mean([u for _,u in pu])*100:+.3f}%/night; "
          f"on SOXL's 10 worst nights it averaged {mean([u for _,u in w10])*100:+.2f}% "
          f"(SOXL {mean([r['on'] for r,_ in w10])*100:+.2f}%)")
    print(HDR)
    for h in (0.05, 0.10, 0.20):
        row(f"SOXL 100% + UVXY {h:.0%}",
            [r["on"] + h * (u - 2 * COST) for r, u in pu], YRS)

    print("\n" + "=" * 104)
    print("4. WEEKEND / HOLIDAY GAPS — is the fat tail there?")
    print("=" * 104)
    wk = [r for r in F if r["gap"] >= 3]
    print(f"  {'bucket':<26}{'nights':>8}{'mean/nt':>10}{'sd':>8}{'worst':>9}{'<-8%':>7}")
    for lbl, b in (("weekend/holiday (>=3d)", wk),
                   ("ordinary overnight", [r for r in F if r["gap"] < 3])):
        v = [r["on"] for r in b]
        print(f"  {lbl:<26}{len(b):>8}{mean(v)*100:>9.3f}%{stdev(v)*100:>7.2f}%"
              f"{min(v)*100:>8.2f}%{sum(1 for z in v if z<-.08):>7}")
    t10 = sorted(F, key=lambda r: r["on"])[:10]
    print(f"  of the 10 worst nights, {sum(1 for r in t10 if r['gap']>=3)} are weekend gaps "
          f"({100*len(wk)/len(F):.0f}% of nights are)")
    print(HDR)
    for h in (0.5, 0.0):
        row(f"weekend size {h:.0%}, weekday 100%",
            [(h if r["gap"] >= 3 else 1.0) * r["on"] for r in F], YRS)

    print("\n" + "=" * 104)
    print("5. PUT OVERLAY, priced from REAL 15:55 -> 09:30 prints")
    print("=" * 104)
    if not os.path.exists(CACHE):
        print("  [skipped] cached put extract not present -- see protection_cost.py")
    else:
        d, o, c = ons("SOXL_1min.csv")
        nxt = {d[i]: d[i + 1] for i in range(len(d) - 1)}
        px = defaultdict(dict)
        for exp, K, dd_, hm, p, cnt, vol in json.load(open(CACHE)):
            px[(exp, K)][(dd_, hm)] = (p, cnt)
        cand = defaultdict(list)
        for (exp, K), v in px.items():
            E = dt.date.fromisoformat(exp)
            for (dd_, hm), (p, cnt) in v.items():
                if hm != "15:55":
                    continue
                D = dt.date.fromisoformat(dd_)
                if D not in nxt or D not in c:
                    continue
                k2 = (nxt[D].isoformat(), "09:30")
                if k2 not in v or not 3 <= (E - D).days <= 7:
                    continue
                cand[D].append(dict(m=K / c[D] - 1, entry=p, exit=v[k2][0],
                                    S=c[D], cnt=cnt))
        FD = {r["date"]: r for r in F}
        for lbl, lo, hi in (("3-7% OTM", -0.07, -0.03), ("ATM +/-1%", -0.01, 0.01)):
            best = {}
            for D in FD:
                xs = [z for z in cand.get(D, ()) if lo <= z["m"] <= hi]
                if xs:
                    best[D] = max(xs, key=lambda z: z["cnt"])
            have = sorted(best)
            if len(have) < 100:
                print(f"  {lbl}: only {len(have)} covered nights, skipping"); continue
            yrs = (have[-1] - have[0]).days / 365.25
            prem = [best[D]["entry"] / best[D]["S"] * 1e4 for D in have]
            print(f"\n  {lbl}, 3-7 DTE — {len(have)} of {len(F)} nights covered, "
                  f"median premium {median(prem):.0f} bp")
            print(HDR)
            row("UNHEDGED (same nights)", [FD[D]["on"] for D in have], yrs)
            for sp in (0.0, 0.05, 0.10, 0.15):
                h = [FD[D]["on"] - ((best[D]["entry"] - best[D]["exit"])
                                    + sp * best[D]["entry"]) / best[D]["S"] for D in have]
                eff = mean([((best[D]["entry"] - best[D]["exit"])
                             + sp * best[D]["entry"]) / best[D]["S"] * 1e4 for D in have])
                row(f"hedged, {sp:.0%} round-trip spread", h, yrs,
                    f"eff cost {eff:>5.1f} bp/nt")

    print("\n" + "=" * 104)
    print("6. DIVERSIFYING ACROSS OVERNIGHT LEGS")
    print("=" * 104)
    legs = {}
    for sym, path in (("SOXL", "SOXL_1min.csv"), ("FAS", "FAS_1min.csv")):
        rr = nights(path)
        ct = pctile([z["rv"] for z in rr], 60)
        legs[sym] = {z["date"]: (z["on"] if z["rv"] < ct else 0.0) for z in rr}
    common = sorted(set(legs["SOXL"]) & set(legs["FAS"]))
    a = [legs["SOXL"][d] for d in common]; b = [legs["FAS"][d] for d in common]
    ma, mb = mean(a), mean(b)
    cr = (sum((p - ma) * (q - mb) for p, q in zip(a, b))
          / ((sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b)) ** 0.5))
    yrs = (common[-1] - common[0]).days / 365.25
    print(f"  {len(common)} common nights; correlation of the two filtered streams {cr:+.3f}")
    print(HDR)
    for lbl, ws, wf in (("100% SOXL", 1.0, 0.0), ("100% FAS", 0.0, 1.0),
                        ("50/50", 0.5, 0.5), ("70/30", 0.7, 0.3),
                        ("70/30 levered to SOXL vol (1.2x)", 0.84, 0.36)):
        row(lbl, [ws * legs["SOXL"][d] + wf * legs["FAS"][d] for d in common], yrs)

    print("\n" + "=" * 104)
    print("7. SAME EXPOSURE AS 3x SOXX INSTEAD OF 1x SOXL")
    print("=" * 104)
    dx, ox, cx = ons("SOXX_5min_6Years.csv")
    d, o, c = ons("SOXL_1min.csv")
    pp = [(d[i], o[d[i+1]]/c[d[i]]-1, ox[d[i+1]]/cx[d[i]]-1)
          for i in range(len(d)-1)
          if d[i] in cx and d[i+1] in ox and d[i] in c and d[i+1] in o]
    L = [z[1] for z in pp]; X = [z[2] for z in pp]
    ml, mx = mean(L), mean(X)
    beta = sum((p_-ml)*(q-mx) for p_, q in zip(L, X)) / sum((q-mx)**2 for q in X)
    crx = (sum((p_-ml)*(q-mx) for p_, q in zip(L, X))
           / ((sum((p_-ml)**2 for p_ in L)*sum((q-mx)**2 for q in X))**0.5))
    print(f"  {len(pp)} nights with both.  overnight beta of SOXL to SOXX {beta:.3f}, "
          f"correlation {crx:.4f}")
    print(f"  mean/night: SOXL {ml*100:+.3f}%   3x SOXX {3*mx*100:+.3f}%   "
          f"gap {(ml-3*mx)*1e4:+.2f} bp/night in SOXX's favour")
    print(f"  compounded gross of financing: SOXL {(math.prod(1+v for v in L)-1)*100:+.0f}%   "
          f"3x SOXX {(math.prod(1+3*v for v in X)-1)*100:+.0f}%")
    print("  (the 3x-SOXX leg carries no financing cost here -- set your own margin")
    print("   rate on the 2x borrowed portion, for the hours actually held, against it)")


if __name__ == "__main__":
    main()
