"""Sleeve any candidate into the strategy, and check it beats the dial.

`tail_screen.py` ranks instruments on what they do in SOXL's worst decile. That
is the right FILTER, but it is not the answer — a +0.38% tail payoff against a
-7.81% tail night is not a hedge at any sane size, and the screen cannot see
that because it never sizes anything.

So this runs the only test that settles it, and it is a dominance test rather
than an improvement test. Any hedge reduces the drawdown if you buy enough of
it. The question is whether it reduces the drawdown MORE PER POINT OF RETURN
GIVEN UP than simply holding less of the strategy — which costs nothing to
implement, needs no second instrument, and leaves Sharpe untouched at 1.82
(`dd_levers.py`).

For every sleeve ratio it therefore finds the scale f whose drawdown matches,
and prints both CAGRs side by side. A hedge is only interesting if its column
wins.

The sleeve is bought, not shorted, so it adds exposure above 1.0x and the
excess is financed — `carry.py` measured the IBKR tiered rate at 4.37-5.12%
and 5.0% is the default.

Usage:
    python3 retreat_lab/hedge_sleeve.py FAZ
    python3 retreat_lab/hedge_sleeve.py PEP,JNJ,KO,VZ        # equal-weight basket
    python3 retreat_lab/hedge_sleeve.py TMV --bps 1.5 --margin 5.0
"""
import argparse, csv, glob, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

# `coverage.py` reads sys.argv[1] as a cost in basis points AT IMPORT TIME, so
# importing it from a script whose first argument is a SYMBOL raises before a
# single line here runs. Every other consumer happened to pass numbers, which
# is why this was invisible until now. Shield the import rather than edit a
# module the committed research results depend on.
_argv, sys.argv = sys.argv, sys.argv[:1]
from coverage import load, walk                              # noqa: E402
sys.argv = _argv

SOXL_BP, XLU_BP = 0.29 / 1e4, 0.83 / 1e4
XLU_MULT = 2.5


def build(path, lag=1):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1, days=(d[i + 1] - d[i]).days)
            for i in range(21, len(d) - 1)}


def find(symbol):
    """A candidate's daily file, from either place they live."""
    for pat in (f"retreat_lab/out/{symbol}_daily_ibkr.csv",
                f"retreat_lab/out/universe/{symbol}.csv"):
        p = os.path.join(ROOT, pat)
        if os.path.exists(p):
            return pat
    raise FileNotFoundError(
        f"{symbol}: no daily file. Run retreat_lab/fetch_universe.py "
        f"--only {symbol}")


def curve(vals, yrs):
    eq = pk = 1.0
    dd = 0.0
    for v in vals:
        eq *= 1 + v
        pk = max(pk, eq)
        dd = min(dd, eq / pk - 1)
    g = eq - 1
    tr = [v for v in vals if v != 0.0]
    s = stdev(tr) if len(tr) > 1 else 0.0
    return dict(cagr=((1 + g) ** (1 / yrs) - 1) * 100, dd=dd * 100,
                sharpe=mean(tr) / s * (len(tr) / yrs) ** 0.5 if s else 0.0,
                worst=min(tr) * 100, n5=sum(1 for v in tr if v < -0.05))


def main():
    ap = argparse.ArgumentParser(description="sleeve a hedge into the strategy")
    ap.add_argument("hedge", help="symbol, or comma-separated equal-weight basket")
    ap.add_argument("--bps", type=float, default=1.0, help="cost per side, bps")
    ap.add_argument("--margin", type=float, default=5.0, help="%%/yr on the excess")
    ap.add_argument("--start", type=int, default=2023)
    args = ap.parse_args()

    legs = [s.strip().upper() for s in args.hedge.split(",") if s.strip()]
    H = {s: build(find(s)) for s in legs}
    S = build("SOXL_1min.csv")
    X = build("retreat_lab/out/XLU_daily_ibkr.csv")
    sd, xd = sorted(S), sorted(X)
    sel = walk({d: S[d]["rv"] for d in sd}, sd, 60)
    xe = walk({d: X[d]["rv"] for d in xd}, xd, 60)
    days = [d for d in sd if d.year >= args.start and d in X
            and all(d in H[s] for s in legs)]
    yrs = (days[-1] - days[0]).days / 365.25
    cost = args.bps / 1e4
    rate = args.margin / 100.0

    def run(r, f=1.0):
        out = []
        for d in days:
            if sel[d]:
                v = S[d]["on"] - 2 * SOXL_BP
                if r:
                    h = mean(H[s][d]["on"] for s in legs) - 2 * cost
                    v += r * h - r * rate * S[d]["days"] / 365.0
                out.append(f * v)
            elif xe.get(d):
                out.append(f * XLU_MULT * (X[d]["on"] - 2 * XLU_BP))
            else:
                out.append(0.0)
        return out

    base = curve(run(0.0), yrs)
    print(f"SLEEVING {'+'.join(legs)} INTO THE STRATEGY")
    print(f"{days[0]} → {days[-1]}   {len(days)} sessions, {yrs:.1f} years   "
          f"{args.bps:.1f} bp/side, {args.margin:.1f}%/yr on the excess\n")
    print(f"  {'sleeve':<10}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}{'worst':>10}"
          f"{'<-5%':>6}   {'same-DD by scaling':>22}")

    def scale_matching(target_dd):
        """The f whose drawdown matches, and what it returns. The comparison."""
        lo, hi = 0.05, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if curve(run(0.0, mid), yrs)["dd"] < target_dd:
                hi = mid          # deeper than target -> hold less
            else:
                lo = mid
        f = (lo + hi) / 2
        return f, curve(run(0.0, f), yrs)["cagr"]

    print(f"  {'none':<10}{base['cagr']:>8.1f}%{base['dd']:>8.1f}%"
          f"{base['sharpe']:>8.2f}{base['worst']:>9.2f}%{base['n5']:>6}")
    verdicts = []
    for r in (0.10, 0.20, 0.30, 0.50, 1.00):
        st = curve(run(r), yrs)
        f, fcagr = scale_matching(st["dd"])
        win = st["cagr"] > fcagr
        verdicts.append(win)
        print(f"  {f'{r:.0%} hedge':<10}{st['cagr']:>8.1f}%{st['dd']:>8.1f}%"
              f"{st['sharpe']:>8.2f}{st['worst']:>9.2f}%{st['n5']:>6}   "
              f"f={f:.2f} → {fcagr:>6.1f}%  {'HEDGE WINS' if win else 'scaling wins'}")

    print()
    if any(verdicts):
        print(f"  {'+'.join(legs)} beats the dial at some size — worth a closer look.")
    else:
        print(f"  {'+'.join(legs)} is DOMINATED: every drawdown it buys, holding")
        print(f"  less buys more cheaply, with no second instrument and no "
              f"financing.")


if __name__ == "__main__":
    main()
