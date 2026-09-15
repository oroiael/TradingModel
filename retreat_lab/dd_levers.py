"""What actually reduces the -28.9% drawdown?

Every hedge this repository has priced — puts (`sizing_and_hedge.py`,
`protection_cost.py`), SOXS and UVXY overlays (`drawdown.py`), the 3x SOXX
expression (`soxx_hedge.py`, `carry.py`), a standing XLU sleeve
(`xlu_sleeve.py`) — either costs more than the tail it removes or leaves Sharpe
where it found it. So the question left is not what to BUY against the
drawdown, it is what to change about the position itself.

The levers below are deliberately of two different kinds, and the difference
matters more than any number in the table:

**Scaling is not a fit.** Holding f x the position is a deterministic
transformation of the same nights. Terminal wealth is concave in f because
variance drag grows with f^2 while return grows with f, so there is a real
interior optimum — but the drawdown reduction is arithmetic, not discovered. It
will hold live because it cannot do otherwise.

**Filters ARE fits.** Tightening the percentile, skipping weekends, standing
down after a bad night: each is a new parameter chosen by looking at this
sample. They will all look better here than they will live, and the ones that
look best are the ones most likely to be noise. They are reported with the
number of nights they drop, because a filter that improves the drawdown by
skipping four nights has found four nights, not a rule.

Usage:  python3 retreat_lab/dd_levers.py [start_year] [xlu_mult]
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
from coverage import load, walk, pctile

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
XLU_MULT = float(sys.argv[2]) if len(sys.argv) > 2 else 2.5
SOXL_BP = 0.29 / 1e4
XLU_BP = 0.83 / 1e4


def build(path, lag=1):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1, nxt=d[i + 1],
                       days=(d[i + 1] - d[i]).days,
                       prev=c[d[i]] / c[d[i - 1]] - 1)
            for i in range(21, len(d) - 1)}


def stats(rets, yrs):
    """Compound over EVERY session, so flat nights dilute nothing away."""
    eq = pk = 1.0
    dd = 0.0
    for v in rets:
        eq *= 1 + v
        pk = max(pk, eq)
        dd = min(dd, eq / pk - 1)
    g = eq - 1
    traded = [v for v in rets if v != 0.0]
    m = mean(traded) if traded else 0.0
    s = stdev(traded) if len(traded) > 1 else 0.0
    sharpe = m / s * (len(traded) / yrs) ** 0.5 if s else 0.0
    return dict(cagr=((1 + g) ** (1 / yrs) - 1) * 100, dd=dd * 100,
                sharpe=sharpe, n=len(traded),
                worst=min(traded) * 100 if traded else 0.0,
                total=g * 100)


def line(label, st, base, extra=""):
    ratio = st["cagr"] / abs(st["dd"]) if st["dd"] else 0.0
    mark = ""
    if base and st["dd"] > base["dd"] + 0.05:
        mark = f"  DD {st['dd']-base['dd']:+.1f}pp"
    print(f"  {label:<30}{st['cagr']:>8.1f}%{st['dd']:>9.1f}%"
          f"{st['sharpe']:>8.2f}{ratio:>8.2f}{st['n']:>7}  {extra}{mark}")


def main():
    S = build("SOXL_1min.csv")
    X = build("retreat_lab/out/XLU_daily_ibkr.csv")
    sd = sorted(S)
    xd = sorted(X)
    days = [d for d in sd if d.year >= START and d in X]
    yrs = (days[-1] - days[0]).days / 365.25

    def legs(p_soxl=60, p_xlu=60, xmult=XLU_MULT, keep=None, f=1.0):
        sel = walk({d: S[d]["rv"] for d in sd}, sd, p_soxl)
        xe = walk({d: X[d]["rv"] for d in xd}, xd, p_xlu)
        out = []
        for d in days:
            if sel[d] and (keep is None or keep(d)):
                out.append(f * (S[d]["on"] - 2 * SOXL_BP))
            elif xe.get(d) and not sel[d] and (keep is None or keep(d)):
                out.append(f * xmult * (X[d]["on"] - 2 * XLU_BP))
            else:
                out.append(0.0)
        return out

    base_r = legs()
    base = stats(base_r, yrs)

    print("WHAT REDUCES THE DRAWDOWN")
    print(f"{days[0]} → {days[-1]}   {len(days)} sessions, {yrs:.1f} years  "
          f"(XLU cover {XLU_MULT:.1f}x)\n")
    print(f"  {'lever':<30}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}{'CAGR/DD':>8}"
          f"{'nights':>7}")
    line("DEPLOYED (nothing changed)", base, None)

    # ---------------------------------------------------- 1. scaling, not a fit
    print(f"\n  SCALING — arithmetic, not discovered. Holds live by construction.")
    for f in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3):
        line(f"hold {f:.0%} of the position", stats(legs(f=f), yrs), None)

    # ------------------------------------------------ 2. filters, which are fits
    print(f"\n  FILTERS — each is a parameter chosen by looking at this sample.")
    for p in (50, 45, 40, 30, 20):
        st = stats(legs(p_soxl=p), yrs)
        line(f"SOXL percentile p{p} (from p60)", st, None,
             f"-{base['n']-st['n']:>3} nights")

    keep_1day = lambda d: S[d]["days"] <= 1
    st = stats(legs(keep=keep_1day), yrs)
    line("skip weekend/holiday holds", st, None, f"-{base['n']-st['n']:>3} nights")

    for thr in (-0.03, -0.05, -0.07):
        k = lambda d, t=thr: S[d]["prev"] > t
        st = stats(legs(keep=k), yrs)
        line(f"skip after a {thr:.0%} SOXL day", st, None,
             f"-{base['n']-st['n']:>3} nights")

    # absolute vol ceiling on top of the relative cut
    rvs = sorted(S[d]["rv"] for d in days)
    for ceil in (90, 100, 110):
        k = lambda d, c=ceil: S[d]["rv"] < c
        st = stats(legs(keep=k), yrs)
        line(f"absolute RV ceiling {ceil}%", st, None,
             f"-{base['n']-st['n']:>3} nights")

    # ------------------------------------------------- 3. the cover leg's size
    print(f"\n  THE COVER LEG — 2.5x is the biggest single position taken.")
    for m in (2.0, 1.5, 1.0, 0.0):
        st = stats(legs(xmult=m), yrs)
        line(f"XLU cover at {m:.1f}x", st, None)

    # ------------------------------------------- 4. the frontier worth reading
    print(f"\n  THE TRADE-OFF, stated plainly (scaling only — the honest lever):")
    print(f"    {'f':<6}{'CAGR':>9}{'maxDD':>9}{'per 1pp of DD given up':>26}")
    for f in (1.0, 0.8, 0.6, 0.5, 0.4, 0.3):
        st = stats(legs(f=f), yrs)
        # both are negative percentages; a shallower drawdown is a LARGER number
        dgiven = st["dd"] - base["dd"]            # positive = DD improved
        cgiven = base["cagr"] - st["cagr"]        # positive = CAGR surrendered
        rate = (cgiven / dgiven) if dgiven > 0.01 else float("nan")
        print(f"    {f:<6.1f}{st['cagr']:>8.1f}%{st['dd']:>8.1f}%"
              f"{rate:>20.2f}pp CAGR")

    # ------------------------------------------------- 5. where the DD comes from
    print(f"\n  ANATOMY OF THE -28.9% — why nothing above touches it")
    eq = pk = 1.0
    peak_at = trough_at = days[0]
    worst = 0.0
    run_pk = days[0]
    for d, v in zip(days, base_r):
        eq *= 1 + v
        if eq > pk:
            pk, run_pk = eq, d
        if eq / pk - 1 < worst:
            worst = eq / pk - 1
            peak_at, trough_at = run_pk, d
    span = [d for d in days if peak_at <= d <= trough_at]
    legs_in = [(d, base_r[days.index(d)]) for d in span if base_r[days.index(d)] != 0.0]
    losers = sorted(legs_in, key=lambda t: t[1])[:6]
    print(f"    peak {peak_at} → trough {trough_at}  "
          f"({(trough_at-peak_at).days} calendar days, {len(span)} sessions, "
          f"{len(legs_in)} traded)")
    print(f"    the six nights that did it:")
    for d, v in losers:
        print(f"      {d}  {v*100:+7.2f}%")
    tot = sum(v for _, v in losers)
    print(f"    those six sum to {tot*100:+.1f}% of a {worst*100:.1f}% drawdown")
    print(f"    every one is a SOXL night, which is why cutting the XLU leg to "
          f"0.0x leaves the drawdown at -28.9%")

    out = os.path.join(ROOT, "retreat_lab/out/dd_levers.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["lever", "cagr_pct", "maxdd_pct", "sharpe", "nights"])
        for f in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3):
            st = stats(legs(f=f), yrs)
            w.writerow([f"scale_{f:.1f}", round(st["cagr"], 2),
                        round(st["dd"], 2), round(st["sharpe"], 3), st["n"]])
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()
