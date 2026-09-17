"""Win and loss rates and magnitudes, on both denominators that matter.

Two numbers get confused constantly and they differ by the leverage multiple:

  loss / CAPITAL AT RISK   the move on the instrument itself. A 2.5x XLU leg
                           puts $369k of capital to work on a $147k account, so
                           this is the number that says how much of the POSITION
                           a bad night takes.
  loss / EQUITY            the same night scaled by the multiple. This is what
                           the ledger records and what compounds the account.

For SOXL at 1.00x they are identical. For XLU at 2.50x the equity number is two
and a half times the capital-at-risk number. Reporting one and calling it the
other overstates or understates by exactly that factor.

Rates are given on three denominators, because "loss rate" is ambiguous:
  * per TRADED night      — how often a trade loses when one is placed
  * per SESSION           — how often a calendar day loses, flat days included
                            in the denominator and never in the numerator
  * per 252-session YEAR  — the same thing as an expected count

Deployed multiples: SOXL 1.00x, XLU 2.50x. Costs are the measured auction ones.

Usage:  python3 retreat_lab/win_loss.py [start_year] [xlu_mult]
"""
import csv, os, sys
from statistics import mean, median, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
_argv, sys.argv = sys.argv, sys.argv[:1]
from coverage import load, walk                              # noqa: E402
sys.argv = _argv

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
XLU_MULT = float(sys.argv[2]) if len(sys.argv) > 2 else 2.5
SOXL_BP, XLU_BP = 0.29 / 1e4, 0.83 / 1e4
YEAR = 252


def build(path, lag=1):
    from statistics import stdev as sd
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=sd(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1)
            for i in range(21, len(d) - 1)}


def pct(xs, p):
    s = sorted(xs)
    return s[min(int(len(s) * p), len(s) - 1)]


def table(name, rows, sessions, sign):
    """rows = [(risk_pct, equity_pct)] for one outcome class."""
    n = len(rows)
    risk = [abs(a) for a, _ in rows]
    eq = [abs(b) for _, b in rows]
    print(f"\n  {name}  —  {n} nights")
    print(f"    rate per TRADED night   {n/sessions['traded']*100:>6.2f}%")
    print(f"    rate per SESSION        {n/sessions['all']*100:>6.2f}%")
    print(f"    expected per 252-day yr {n/sessions['all']*YEAR:>6.1f} nights")
    if not rows:
        return
    print(f"    {'magnitude':<12}{'mean':>9}{'median':>9}{'sd':>9}"
          f"{'p75':>9}{'p90':>9}{'p99':>9}{'worst':>9}")
    for lbl, v in (("/ capital", risk), ("/ equity", eq)):
        s = stdev(v) if len(v) > 1 else 0.0
        print(f"    {lbl:<12}{mean(v)*100:>8.3f}%{median(v)*100:>8.3f}%"
              f"{s*100:>8.3f}%{pct(v,.75)*100:>8.3f}%{pct(v,.90)*100:>8.3f}%"
              f"{pct(v,.99)*100:>8.3f}%{max(v)*100:>8.3f}%")


def main():
    S = build("SOXL_1min.csv")
    X = build("retreat_lab/out/XLU_daily_ibkr.csv")
    sd_, xd = sorted(S), sorted(X)
    sel = walk({d: S[d]["rv"] for d in sd_}, sd_, 60)
    xe = walk({d: X[d]["rv"] for d in xd}, xd, 60)
    days = [d for d in sd_ if d.year >= START and d in X]

    trades = []          # (leg, risk_net, equity_net)
    flat = 0
    for d in days:
        if sel[d]:
            r = S[d]["on"] - 2 * SOXL_BP
            trades.append(("SOXL", r, 1.0 * r))
        elif xe.get(d):
            r = X[d]["on"] - 2 * XLU_BP
            trades.append(("XLU", r, XLU_MULT * r))
        else:
            flat += 1

    sess = dict(all=len(days), traded=len(trades), flat=flat)
    yrs = len(days) / YEAR
    print(f"BACKTEST WIN / LOSS PROFILE   SOXL 1.00x, XLU {XLU_MULT:.2f}x")
    print(f"{days[0]} → {days[-1]}   {sess['all']} sessions "
          f"({yrs:.2f} years of 252)   {sess['traded']} traded, {flat} flat\n")
    print(f"  flat (no capital at risk): {flat} = {flat/sess['all']*100:.1f}% "
          f"of sessions = {flat/sess['all']*YEAR:.0f} nights/yr")

    for label, keep in (("ALL TRADES", lambda l: True),
                        ("SOXL only", lambda l: l == "SOXL"),
                        ("XLU only", lambda l: l == "XLU")):
        sub = [(r, e) for l, r, e in trades if keep(l)]
        if label != "ALL TRADES":
            sess2 = dict(all=sess["all"], traded=len(sub))
        else:
            sess2 = sess
        print(f"\n{'='*78}\n{label}   ({len(sub)} of {sess['traded']} trades)")
        table("LOSERS", [(r, e) for r, e in sub if e < 0], sess2, -1)
        table("WINNERS", [(r, e) for r, e in sub if e > 0], sess2, +1)

    # expectancy, which is what the rates and magnitudes are FOR
    L = [e for _, _, e in trades if e < 0]
    W = [e for _, _, e in trades if e > 0]
    p = len(W) / len(trades)
    print(f"\n{'='*78}\nEXPECTANCY per traded night, on equity")
    print(f"  win {p:.1%} x {mean(W)*100:+.3f}%  +  loss {1-p:.1%} x "
          f"{mean(L)*100:+.3f}%  =  {(p*mean(W)+(1-p)*mean(L))*100:+.4f}%")
    print(f"  win/loss ratio (mean win / mean loss) = {mean(W)/abs(mean(L)):.3f}")
    print(f"  per 252-day year: {len(W)/sess['all']*YEAR:.0f} winners, "
          f"{len(L)/sess['all']*YEAR:.0f} losers, {flat/sess['all']*YEAR:.0f} flat")

    out = os.path.join(ROOT, "retreat_lab/out/win_loss.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["leg", "return_on_capital_pct", "return_on_equity_pct"])
        for l, r, e in trades:
            w.writerow([l, round(r * 100, 4), round(e * 100, 4)])
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()
