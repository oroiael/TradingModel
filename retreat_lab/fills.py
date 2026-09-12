"""Can the XLU cover leg actually be filled at the cost the backtest assumes?

coverage.py showed the XLU cover leg is cost-fragile: it needs 3x notional for
the same exposure, so it pays ~3x the friction, and the edge is gone by 5 bp per
side. This prices the real thing.

VERIFIED FROM THE REPO'S TWS API 10.39.01 SOURCE (not from memory):
  MOC is a real order type -- source/JavaClient/com/ib/client/OrderType.java:25
      MOC( Arrays.asList("MOC", "MKT CLS", "MKTCLS") )
  MarketOnClose  -- samples/Python/Testbed/OrderSamples.py:100  orderType = "MOC"
  MarketOnOpen   -- samples/Python/Testbed/OrderSamples.py:117  orderType = "MKT",
                    tif = "OPG"

NOT VERIFIABLE HERE, and therefore NOT asserted: the MOC submission cutoff time,
and whether IBKR routes MOC/MOO to the primary listing auction. Those are
exchange/broker behaviours; interactivebrokers.com and ibkrcampus.com are
egress-blocked from this environment and the local 131-page PDF does not extract.
Confirm both against a live session before sizing on them.

Why the execution method dominates: the backtest buys at the official close and
sells at the official open. An auction order fills AT those prints and crosses no
spread, so its cost is commission only. A marketable order pays the half-spread
on both legs -- and XLU's spread is TICK-CONSTRAINED at $0.01, which on a $42
share is 2.36 bp, nearly 3x SOXL's 0.82 bp at $122.

Usage:  python3 retreat_lab/fills.py [start_year]
"""
import csv, math, os, sys
from statistics import stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
from coverage import load, walk, curve

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
C = 1.0 / 10000.0
QUOTES = os.path.join(ROOT, "retreat_lab/out/fill_quality_20260912.csv")


def build(path, lag=0):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1)
            for i in range(21, len(d) - 1)}


def main():
    q = {r["symbol"]: r for r in csv.DictReader(open(QUOTES))}
    print("MEASURED LIQUIDITY AND COST, IBKR snapshot 2026-09-12\n")
    print(f"  {'sym':<6}{'last':>9}{'AUM':>16}{'90d $ vol/day':>16}"
          f"{'tick':>8}{'x notional':>12}")
    for s in ("SOXL", "XLU", "UTSL"):
        r = q[s]
        aum = f"${float(r['aum_usd'])/1e9:,.1f}B" if r["aum_usd"] else "--"
        print(f"  {s:<6}{'$'+r['last_price']:>9}{aum:>16}"
              f"{'$'+f'{float(r[chr(97)+chr(118)+chr(103)+chr(95)+chr(57)+chr(48)+chr(100)+chr(95)+chr(117)+chr(115)+chr(100)+chr(95)+chr(118)+chr(111)+chr(108)+chr(117)+chr(109)+chr(101)])/1e6:,.0f}M':>16}"
              f"{r['tick_bp']+' bp':>8}{r['notional_multiple']+'x':>12}")

    print(f"\n  {'route':<34}{'commission':>12}{'half-spread':>13}"
          f"{'bp/side':>10}{'bp of EQUITY, round trip':>26}")
    eff = {}
    for s, lbl in (("SOXL", "SOXL leg, 1x notional"), ("XLU", "XLU cover leg, 3x notional")):
        r = q[s]
        cm, hs, m = float(r["commission_bp_per_side"]), float(r["half_spread_bp_per_side"]), float(r["notional_multiple"])
        for mode, per in (("auction (MOC/MOO)", cm), ("marketable", cm + hs)):
            print(f"  {lbl + ' — ' + mode:<34}{cm:>11.2f}{hs if mode=='marketable' else 0.0:>13.2f}"
                  f"{per:>10.2f}{per*m*2:>25.2f}")
            eff[(s, mode)] = per
        print()

    S = build("SOXL_1min.csv")
    X = build("retreat_lab/out/XLU_daily_ibkr.csv")
    sd = sorted(S); sel = walk({d: S[d]["rv"] for d in sd}, sd, 60)
    xd = sorted(X); xe = walk({d: X[d]["rv"] for d in xd}, xd, 60)
    days = [d for d in sd if d.year >= START and d in X]
    yrs = (days[-1] - days[0]).days / 365.25
    print(f"  BACKTEST AT THE MEASURED COSTS — {days[0]} → {days[-1]}, {len(days)} nights")
    print(f"  {'execution':<40}{'total':>11}{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}{'t':>7}")
    b = [S[d]["on"] - 2 * C for d in days if sel[d]]
    g, cg, dd, sh, t = curve(b, yrs)
    print(f"  {'SOXL alone (no cover)':<40}{g:>10,.0f}%{cg:>7.1f}%{dd:>7.1f}%{sh:>8.2f}{t:>7.2f}")
    for mode in ("auction (MOC/MOO)", "marketable"):
        sx, xx = eff[("SOXL", mode)] / 1e4, eff[("XLU", mode)] / 1e4
        r = []
        for d in days:
            if sel[d]:
                r.append(S[d]["on"] - 2 * sx)
            elif xe.get(d):
                r.append(3.0 * X[d]["on"] - 3.0 * 2 * xx)
        g, cg, dd, sh, t = curve(r, yrs)
        print(f"  {'+ XLU cover, ' + mode:<40}{g:>10,.0f}%{cg:>7.1f}%{dd:>7.1f}%{sh:>8.2f}{t:>7.2f}")
    print(f"\n  For reference, the edge disappears at 5 bp/side on the XLU leg (Sharpe 1.34).")


if __name__ == "__main__":
    main()
