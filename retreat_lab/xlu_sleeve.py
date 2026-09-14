"""Does holding XLU ALONGSIDE SOXL — not instead of it — help?

The deployed rule treats XLU as a SWITCH: SOXL when its own vol filter says go,
XLU at 2.5x only on the nights SOXL is benched, flat otherwise. `coverage.py`
chose it that way because the question it answered was "what earns money on the
nights SOXL cannot trade". Nothing in this repository has tested carrying a
standing XLU sleeve on the nights SOXL DOES trade.

That is a different claim, and it deserves its own test rather than an argument.
The hope would be that utilities rally when semiconductors gap down, so a small
permanent XLU position clips the left tail. The reason to doubt it is that
`coverage.py` measured SOXL/XLU overnight correlation at +0.21 to +0.26 — weakly
POSITIVE. A hedge needs negative correlation; weakly positive means the sleeve
is mostly just more risk with its own drift attached.

So the test below asks three separate questions, because "does it help" hides
all of them:

  1. what does it do to terminal wealth, drawdown and Sharpe?
  2. what does XLU actually do on SOXL's WORST nights — the only ones a hedge
     is for? A sleeve that pays on the median night and not the tail has not
     hedged anything, it has just levered up.
  3. is any difference bigger than the noise in a 3-year sample?

Construction is `final_config.py`'s, exactly, so the r=0 row reproduces the
proposed ledger and every other row differs from it only by the sleeve:

  * RV20 through D-1's close, walk-forward p60 on each series' own history
  * measured auction costs, 0.29 bp SOXL and 0.83 bp XLU per side
  * sleeve r is r x EQUITY of XLU held on SOXL nights only, financed on margin

Margin is charged, per calendar day held, on the borrowed portion — a 1.0x SOXL
leg plus an r sleeve is 1+r invested, so r is borrowed. `carry.py` measured the
IBKR tiered rate at 4.37-5.12%; 5.0% is the default here and the sensitivity is
printed.

Usage:  python3 retreat_lab/xlu_sleeve.py [start_year] [xlu_mult] [margin_pct]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
from coverage import load, walk, curve, corr

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
XLU_MULT = float(sys.argv[2]) if len(sys.argv) > 2 else 2.5   # deployed
MARGIN = (float(sys.argv[3]) if len(sys.argv) > 3 else 5.0) / 100.0

SOXL_BP = 0.29 / 1e4
XLU_BP = 0.83 / 1e4
SLEEVES = (0.0, 0.10, 0.20, 0.30)


def build(path, lag=1):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1, nxt=d[i + 1],
                       days=(d[i + 1] - d[i]).days)
            for i in range(21, len(d) - 1)}


def run(days, S, X, sel, xe, sleeve, margin=None):
    """One night's net return per session, for a given sleeve ratio."""
    out = []
    for d in days:
        if sel[d]:
            soxl = S[d]["on"] - 2 * SOXL_BP
            if sleeve > 0:
                xlu = X[d]["on"] - 2 * XLU_BP
                rate = MARGIN if margin is None else margin
                borrow = sleeve * rate * S[d]["days"] / 365.0
                out.append(("SOXL", d, soxl + sleeve * xlu - borrow))
            else:
                out.append(("SOXL", d, soxl))
        elif xe.get(d):
            out.append(("XLU", d, XLU_MULT * (X[d]["on"] - 2 * XLU_BP)))
        else:
            out.append(("FLAT", d, 0.0))
    return out


def main():
    S = build("SOXL_1min.csv")
    X = build("retreat_lab/out/XLU_daily_ibkr.csv")
    sd = sorted(S); sel = walk({d: S[d]["rv"] for d in sd}, sd, 60)
    xd = sorted(X); xe = walk({d: X[d]["rv"] for d in xd}, xd, 60)
    days = [d for d in sd if d.year >= START and d in X]
    yrs = (days[-1] - days[0]).days / 365.25
    soxl_nights = [d for d in days if sel[d]]

    print("XLU AS A STANDING SLEEVE ON SOXL NIGHTS")
    print(f"{days[0]} → {days[-1]}   {len(days)} sessions, {yrs:.1f} years")
    print(f"SOXL nights {len(soxl_nights)}   XLU cover {XLU_MULT:.1f}x   "
          f"margin {MARGIN:.1%}/yr on the borrowed portion\n")

    # ---------------------------------------------------------------- 1. curves
    print(f"  {'sleeve':<9}{'total':>11}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>9}"
          f"{'t':>7}{'worst nt':>11}{'<-5%':>7}{'<-8%':>7}")
    results = {}
    for r in SLEEVES:
        rows = run(days, S, X, sel, xe, r)
        v = [x for _, _, x in rows]
        traded = [x for x in v if x != 0.0]
        g, cg, dd, sh, t = curve(traded, yrs)
        eq = pk = 1.0; ddall = 0.0
        for x in v:
            eq *= 1 + x; pk = max(pk, eq); ddall = min(ddall, eq / pk - 1)
        gall = math.prod(1 + x for x in v) - 1
        results[r] = dict(rows=rows, total=gall * 100,
                          cagr=((1 + gall) ** (1 / yrs) - 1) * 100,
                          dd=ddall * 100, sh=sh, t=t, traded=traded)
        lbl = "none" if r == 0 else f"{r:.0%}"
        print(f"  {lbl:<9}{gall*100:>10,.0f}%{results[r]['cagr']:>8.1f}%"
              f"{ddall*100:>8.1f}%{sh:>9.2f}{t:>7.2f}{min(traded)*100:>10.2f}%"
              f"{sum(1 for x in traded if x<-0.05):>7}"
              f"{sum(1 for x in traded if x<-0.08):>7}")

    # ------------------------------------------- 2. what XLU does in the tail
    print(f"\n  WHAT XLU ACTUALLY DID ON SOXL'S WORST NIGHTS")
    print(f"  A hedge has to pay HERE. Paying on the median night is leverage.\n")
    pairs = [(S[d]["on"], X[d]["on"], d) for d in soxl_nights]
    pairs.sort()
    print(f"  {'date':<13}{'SOXL':>10}{'XLU':>9}{'XLU offset of the SOXL loss':>32}")
    for s, x, d in pairs[:10]:
        off = (-x / s * 100) if s < 0 else 0.0
        note = f"{x/abs(s)*100:+.1f}% of the move" if s < 0 else ""
        print(f"  {d.isoformat():<13}{s*100:>9.2f}%{x*100:>8.2f}%{note:>32}")

    worst20 = pairs[:max(len(pairs) // 20, 1)]
    xw = [x for _, x, _ in worst20]
    print(f"\n  worst 5% of SOXL nights ({len(worst20)}): XLU mean "
          f"{mean(xw)*100:+.3f}%, up on {sum(1 for x in xw if x>0)}/{len(xw)}")
    allx = [x for _, x, _ in pairs]
    print(f"  all SOXL nights ({len(pairs)}):          XLU mean "
          f"{mean(allx)*100:+.3f}%, up on {sum(1 for x in allx if x>0)}/{len(allx)}")
    print(f"  overnight correlation SOXL vs XLU on these nights: "
          f"{corr([s for s,_,_ in pairs], allx):+.3f}")

    # ----------------------------------------------- 3. is it bigger than noise
    print(f"\n  IS ANY OF IT REAL?")
    base = results[0.0]["traded"]
    for r in SLEEVES[1:]:
        alt = results[r]["traded"]
        diff = [a - b for a, b in zip(alt, base)]
        m, s = mean(diff), stdev(diff)
        t = m / (s / len(diff) ** 0.5) if s else 0.0
        print(f"    sleeve {r:.0%}: mean per-night change {m*100:+.4f}% "
              f"(sd {s*100:.3f}%), t = {t:+.2f}"
              f"{'   NOT significant' if abs(t) < 2 else '   significant'}")

    # ------------------------------------------------------- margin sensitivity
    print(f"\n  MARGIN SENSITIVITY on the 30% sleeve (CAGR):")
    for rate in (0.0, 0.0437, 0.05, 0.0512, 0.07):
        v = [x for _, _, x in run(days, S, X, sel, xe, 0.30, margin=rate)]
        g = math.prod(1 + x for x in v) - 1
        print(f"    {rate:>6.2%}/yr  CAGR {((1+g)**(1/yrs)-1)*100:>7.1f}%")

    out = os.path.join(ROOT, "retreat_lab/out/xlu_sleeve.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["decision_date", "leg", "soxl_on_pct", "xlu_on_pct"] +
                   [f"net_sleeve_{int(r*100)}_pct" for r in SLEEVES])
        for i, (a, d, _) in enumerate(results[0.0]["rows"]):
            w.writerow([d.isoformat(), a,
                        round(S[d]["on"] * 100, 4), round(X[d]["on"] * 100, 4)] +
                       [round(results[r]["rows"][i][2] * 100, 4) for r in SLEEVES])
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()
