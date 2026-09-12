"""Is 3x SOXX cheaper than 1x SOXL, once you pay your own margin interest?

soxx_hedge.py / drawdown.py measured that 3x SOXX beat SOXL by ~3.55 bp per
night held, GROSS of financing. That gap is SOXL's embedded expense ratio and
swap financing, which accrues into its NAV whether you hold it or not.

Replacing SOXL with 3x SOXX on margin replaces that embedded cost with your own
margin interest -- and the two are charged on different bases:

  SOXL          financing is embedded, accrues 24/7/365 into NAV, and you bear
                only the slice that falls in the hours you actually hold.
  3x SOXX       you borrow 2x equity and pay YOUR rate for every calendar day
                the debit exists -- 1 day for an ordinary night, 3 across a
                weekend, more across a holiday.

So the comparison turns on interest-DAYS, not nights. This prices it on the
actual p60-filtered night set and solves for the breakeven rate.

Rates: IBKR Pro Tier 1 (to $100k) is 5.12% as of 2026-09, quoted as the IBKR
benchmark (Fed Funds Effective, ~3.62%) + 1.5%. Higher tiers narrow the spread.
The breakeven below does not depend on which tier applies -- compare it to
whatever your blended rate actually is.

Usage:  python3 retreat_lab/carry.py [bps_per_side] [annual_margin_rate_pct ...]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = (float(sys.argv[1]) if len(sys.argv) > 1 else 1.0) / 10000.0
RATES = [float(x) / 100 for x in sys.argv[2:]] or [0.0437, 0.0462, 0.0512]
# per-side cost for SOXX. The SOXX route trades 3x the NOTIONAL for the same
# exposure, so it pays 3x the dollar friction even at an identical bp cost.
# SOXX is bigger and calmer than SOXL so its bp cost is likely lower; both
# assumptions are priced below.
COST_X = COST
LEV = 3.0            # semis exposure per unit of equity
BORROW = LEV - 1.0   # ~3x SOXX on 1x equity => ~2x debit (refined to beta below)


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


def curve(rets, yrs):
    g = math.prod(1 + v for v in rets) - 1
    eq = pk = 1.0; dd = 0.0
    for v in rets:
        eq *= 1 + v; pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    m, s = mean(rets), stdev(rets)
    return g * 100, ((1 + g) ** (1 / yrs) - 1) * 100, dd * 100, m / s * (len(rets) / yrs) ** 0.5


def main():
    dl, ol, cl = ons("SOXL_1min.csv")
    dx, ox, cx = ons("SOXX_5min_6Years.csv")
    dr = [cl[dl[i]] / cl[dl[i - 1]] - 1 for i in range(1, len(dl))]
    rows = []
    for i in range(20, len(dl) - 1):
        D, N = dl[i], dl[i + 1]
        if D not in cx or N not in ox:
            continue
        rows.append(dict(date=D, nxt=N, days=(N - D).days,
                         rv=stdev(dr[i - 20:i]) * (252 ** 0.5) * 100,
                         soxl_g=ol[N] / cl[D] - 1,
                         soxx_g=ox[N] / cx[D] - 1))
    cut = pctile([r["rv"] for r in rows], 60)
    F = [r for r in rows if r["rv"] < cut]
    yrs = (F[-1]["date"] - F[0]["date"]).days / 365.25
    days = sum(r["days"] for r in F)
    per = days / len(F)

    print(f"p60-filtered overnight, {COST*1e4:.0f} bp/side, {LEV:.0f}x semis exposure")
    print(f"{F[0]['date']} → {F[-1]['nxt']}   {len(F)} nights held, {yrs:.1f} years")
    print(f"interest-days: {days} over {len(F)} nights = {per:.2f} days/night "
          f"({sum(1 for r in F if r['days']>=3)} weekend/holiday nights at 3+ days)")
    print(f"  -> {days/yrs:.0f} interest-days per year on a {BORROW:.0f}x debit\n")

    # Match on REALISED beta, not a nominal 3.0 -- otherwise part of any
    # "advantage" is just holding more exposure than SOXL gives.
    L0, X0 = [r["soxl_g"] for r in F], [r["soxx_g"] for r in F]
    mL, mX = mean(L0), mean(X0)
    BETA = (sum((a - mL) * (b - mX) for a, b in zip(L0, X0))
            / sum((b - mX) ** 2 for b in X0))
    raw_l = L0
    raw_x = [BETA * v for v in X0]
    gross = mean(raw_x) - mean(raw_l)
    print(f"  realised overnight beta of SOXL to SOXX on this set: {BETA:.4f}")
    print(f"  (a flat 3.000x would show {(mean([3*v for v in X0])-mL)*1e4:+.2f} bp; "
          f"{((mean([3*v for v in X0])-mean(raw_x))/(mean([3*v for v in X0])-mL))*100:.0f}% "
          f"of that is extra exposure, not cheaper exposure)\n")

    print(f"  {'leg, GROSS of trading cost and financing':<44}{'mean/night':>13}")
    print(f"  {'1x SOXL':<44}{mean(raw_l)*100:>12.4f}%")
    print(f"  {'3x SOXX':<44}{mean(raw_x)*100:>12.4f}%")
    print(f"  {'gross SOXX advantage':<44}{gross*1e4:>11.2f} bp\n")

    print("  DECOMPOSITION, per night held, per unit of equity")
    print("  The SOXX route trades 3x the NOTIONAL for the same exposure, so it pays")
    print("  3x the dollar friction. That term is larger than the advantage it chases.")
    print(f"  {'term':<52}{'bp/night':>10}")
    for cx_bp in (COST * 1e4, COST * 1e4 / 2):
        tl, tx = 2 * COST * 1e4, BETA * 2 * cx_bp
        net_pre = gross * 1e4 - (tx - tl)
        be = (net_pre / 1e4) * 365.0 / ((BETA - 1.0) * per)
        print(f"\n  --- SOXL {COST*1e4:.1f} bp/side, SOXX {cx_bp:.1f} bp/side ---")
        print(f"  {'gross SOXX advantage':<52}{gross*1e4:>+10.2f}")
        print(f"  {'SOXL trading cost (1x notional, round trip)':<52}{-tl:>+10.2f}")
        print(f"  {f'SOXX trading cost ({BETA:.2f}x notional, round trip)':<52}"
              f"{-tx:>+10.2f}")
        print(f"  {'= net before financing':<52}{net_pre:>+10.2f}")
        print(f"  BREAKEVEN MARGIN RATE = {net_pre:.2f} bp x 365 / "
              f"({BETA-1:.2f} x {per:.2f} days) = {be*100:.2f}% / yr")

    cx_bp = COST * 1e4
    gl = [v - 2 * COST for v in raw_l]
    gx = [v - BETA * 2 * COST for v in raw_x]
    adv = mean(gx) - mean(gl)
    BORROW_B = BETA - 1.0
    be = adv * 365.0 / (BORROW_B * per)
    _, sl_cg, _, _ = curve(gl, yrs)
    print(f"\n  NET OF YOUR MARGIN INTEREST  (SOXL {COST*1e4:.0f} bp/side, "
          f"SOXX {cx_bp:.0f} bp/side; SOXL CAGR {sl_cg:.1f}%)")
    print(f"  {'your margin rate':<22}{'interest/yr':>13}{'net vs SOXL':>14}"
          f"{'net CAGR':>11}{'vs SOXL CAGR':>15}")
    for rt in sorted(set(RATES + [max(be, 0.0)])):
        net = [v - BORROW_B * rt * r["days"] / 365.0 for v, r in zip(gx, F)]
        t, cg, dd, sh = curve(net, yrs)
        tag = "  <-- breakeven" if abs(rt - be) < 1e-9 else ""
        print(f"  {rt*100:<21.2f}%{BORROW_B*rt*days/yrs/365*100:>12.2f}%"
              f"{(mean(net)-mean(gl))*1e4:>12.2f} bp{cg:>10.1f}%{cg-sl_cg:>+14.1f}pp{tag}")

    print(f"\n  MARGIN CAPACITY — the same exposure, very different footprint")
    print(f"  {'route':<34}{'notional / equity':>19}{'leverage used':>16}")
    print(f"  {'1x SOXL at 3x semis':<34}{'1.0x':>19}{'1.0 : 1':>16}")
    print(f"  {'3x SOXX at 3x semis':<34}{'3.0x':>19}{'3.0 : 1':>16}")
    print(f"  {'1x SOXL at f=2.0 (6x semis)':<34}{'2.0x':>19}{'2.0 : 1':>16}")
    print(f"  {'3x SOXX at f=2.0 (6x semis)':<34}{'6.0x':>19}{'6.0 : 1':>16}")
    print(f"  Identical economics, but the SOXX route consumes 3x the gross notional.")
    print(f"  Against the 3:1 cap you cited, SOXL at f=2.0 fits and SOXX at f=2.0 does not.")


if __name__ == "__main__":
    main()
