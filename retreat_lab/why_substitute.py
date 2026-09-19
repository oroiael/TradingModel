"""What the p60 filter actually selects — and why swapping to XLU is right.

The intuitive story is that the filter finds SOXL's BAD nights and the cover leg
avoids them. That is not what happens, and the numbers say so plainly:

    SOXL's own overnight mean, by which night the rule assigns it
      nights it TRADES SOXL   +0.342%   sd 3.44%
      nights it trades XLU    +0.483%   sd 6.06%
      nights it sits FLAT     +0.503%   sd 6.89%

SOXL's expected return is HIGHER on the nights it is benched. The filter does
not identify losing nights; it identifies HIGH-VARIANCE nights, and variance is
symmetric — it cuts the right tail along with the left.

So the substitution cannot be justified by avoiding losses. On the 189 nights it
actually happened, holding SOXL instead would have returned 74.3% against XLU's
53.2%. The justification is risk-adjusted: XLU at 2.5x returns 0.201 per unit of
overnight risk against SOXL's 0.079, two and a half times better, for half the
raw return at a fifth of the volatility.

That is also why the whole strategy Sharpes at 1.82 while SOXL held every night
Sharpes at 1.33, and why `dd_levers.py` found the drawdown to be entirely a SOXL
phenomenon.

XLU runs its OWN walk-forward p60 on its OWN RV history — it is not SOXL's rule
inverted. The two are mildly coupled, as risk assets are: XLU is eligible on
73.6% of all sessions, 78.2% when SOXL is also eligible, and 63.9% when SOXL is
benched. Storms are somewhat common; they are not the same storm.

Usage:  python3 retreat_lab/why_substitute.py [start_year]
"""
import os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_argv, sys.argv = sys.argv, sys.argv[:1]
from coverage import load, walk                              # noqa: E402
sys.argv = _argv

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023


def series(path, lag=1):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1)
            for i in range(21, len(d) - 1)}


def main():
    S = series("retreat_lab/out/SOXL_daily_ibkr.csv")
    X = series("retreat_lab/out/XLU_daily_ibkr.csv")
    sd, xd = sorted(S), sorted(X)
    sel = walk({x: S[x]["rv"] for x in sd}, sd, 60)
    xe = walk({x: X[x]["rv"] for x in xd}, xd, 60)
    days = [x for x in sd if x.year >= START and x in X]
    soxl = [x for x in days if sel[x]]
    bench = [x for x in days if not sel[x]]
    xlun = [x for x in bench if xe.get(x)]
    flat = [x for x in bench if not xe.get(x)]

    print(f"{len(days)} sessions from {START}: SOXL {len(soxl)}, XLU {len(xlun)}, "
          f"FLAT {len(flat)}\n")
    print("SOXL's OWN overnight return, grouped by what the rule did that night")
    print(f"  {'group':<22}{'n':>5}{'SOXL mean':>12}{'win':>8}{'sd':>8}")
    for nm, g in (("traded SOXL", soxl), ("traded XLU", xlun), ("sat flat", flat)):
        v = [S[x]["on"] for x in g]
        print(f"  {nm:<22}{len(v):>5}{mean(v)*100:>+11.3f}%"
              f"{sum(1 for r in v if r>0)/len(v)*100:>7.1f}%{stdev(v)*100:>7.2f}%")
    print("\n  Benched nights have a HIGHER mean, not a lower one. The filter")
    print("  selects variance, not direction, and variance is symmetric.\n")

    print("On the nights XLU actually traded, what each choice would have paid")
    print(f"  {'choice':<22}{'mean':>10}{'win':>8}{'sd':>8}{'per unit risk':>15}")
    for nm, v in (("XLU @2.5x (what we do)",
                   [2.5 * (X[x]["on"] - 2 * 0.83 / 1e4) for x in xlun]),
                  ("SOXL @1.0x", [S[x]["on"] - 2 * 0.29 / 1e4 for x in xlun])):
        m, s = mean(v), stdev(v)
        print(f"  {nm:<22}{m*100:>+9.3f}%{sum(1 for r in v if r>0)/len(v)*100:>7.1f}%"
              f"{s*100:>7.2f}%{m/s:>15.4f}")
    print(f"  {'cash':<22}{0.0:>+9.3f}%{0.0:>7.1f}%{0.0:>7.2f}%{0.0:>15.4f}")

    print(f"\nIs XLU on its own schedule?")
    e = sum(1 for x in days if xe.get(x))
    print(f"  P(XLU eligible)                 {e/len(days)*100:>5.1f}%")
    print(f"  P(XLU eligible | SOXL eligible) "
          f"{sum(1 for x in soxl if xe.get(x))/len(soxl)*100:>5.1f}%")
    print(f"  P(XLU eligible | SOXL benched)  {len(xlun)/len(bench)*100:>5.1f}%")
    print(f"  Own filter, own history, mildly coupled. Not SOXL inverted.")


if __name__ == "__main__":
    main()
