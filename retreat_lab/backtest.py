"""Backtesting the underlying-only exit rules as actual strategies.

exit_rules.py compared exits per-trade. Per-trade means hide two things a real
strategy lives or dies on: compounding, and how much of the tape you are not in.
This runs each rule as a full strategy -- compounded equity, costs, drawdown --
against buy-and-hold over the same 6.6 years.

Entry is always the +2% upswing trigger, which the trade tests showed carries no
directional edge. That is deliberate: if a rule cannot beat buy-and-hold on a
zero-edge entry, the honest conclusion is that the exit rule was never the
binding constraint.

Position sizing is all-in / all-out: 100% long while in a trade, flat otherwise,
never levered, no overlapping trades. Costs are charged per side on entry and
exit.

Usage:  python3 retreat_lab/backtest.py [bps_per_side]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, tag

BPS = 10000
COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0     # bps per side


def load():
    close, ts, idx = [], [], {}
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            idx[t] = len(close); ts.append(t)
            close.append(int((Decimal(a[4]) * 100).to_integral_exact()))
    return close, ts, idx


def triggers(idx):
    f = os.path.join(ROOT, "retreat_lab/out",
                     f"retreat_episodes_1min_{tag(200, 50)}.csv")
    return [idx[dt.datetime.strptime(r["trigger_ts"], "%Y-%m-%d %H:%M")]
            for r in csv.DictReader(open(f))]


def strategy(close, dates, ent, stop_bps=None, time_min=None, eod=False, cost=COST):
    """-> list of (entry_i, exit_i, net return). Non-overlapping by construction:
    a trigger inside an open trade is skipped, as the engine itself does."""
    n = len(close); trades = []; busy = -1
    c = cost / BPS
    for g in ent:
        if g < busy:
            continue
        peak = close[g]
        limit = g + time_min if time_min else n - 1
        j = None
        for k in range(g + 1, n):
            if eod and dates[k] != dates[g]:
                j = k - 1; break
            if close[k] > peak:
                peak = close[k]
            if stop_bps and close[k] * BPS <= peak * (BPS - stop_bps):
                j = k; break
            if k >= limit:
                j = k; break
        if j is None or j >= n:
            continue
        r = (close[j] / close[g] - 1) - 2 * c
        trades.append((g, j, r))
        busy = j
    return trades


def stats(trades, close, ts, yrs):
    if not trades:
        return None
    eq = 1.0; peak = 1.0; dd = 0.0; curve = []
    for _, _, r in trades:
        eq *= (1 + r); peak = max(peak, eq); dd = min(dd, eq / peak - 1)
        curve.append(eq)
    rets = [r for _, _, r in trades]
    bars = sum(j - g for g, j, _ in trades)
    # annualise on trade returns scaled by how often they occur
    per_yr = len(trades) / yrs
    sh = (mean(rets) / stdev(rets) * (per_yr ** 0.5)) if len(rets) > 1 and stdev(rets) else 0
    return dict(total=eq - 1, cagr=eq ** (1 / yrs) - 1 if eq > 0 else -1,
                dd=dd, n=len(trades), win=sum(1 for r in rets if r > 0) / len(rets),
                sh=sh, expo=bars / len(close), hold=bars / len(trades))


def row(lbl, s):
    if not s:
        print(f"  {lbl:<34} (no trades)"); return
    print(f"  {lbl:<34}{s['total']*100:>12,.0f}%{s['cagr']*100:>9.1f}%"
          f"{s['dd']*100:>9.1f}%{s['sh']:>8.2f}{s['n']:>7}{s['win']:>7.1%}"
          f"{s['hold']:>7.0f}m{s['expo']:>8.1%}")


def main():
    close, ts, idx = load()
    dates = [t.date() for t in ts]
    ent = triggers(idx)
    yrs = (ts[-1] - ts[0]).days / 365.25
    bh = close[-1] / close[0] - 1
    print(f"SOXL 1-min, {ts[0]:%Y-%m-%d} → {ts[-1]:%Y-%m-%d} ({yrs:.1f}y), "
          f"{len(ent):,} triggers")
    print(f"costs: {COST:.1f} bps per side, {COST*2:.1f} bps round trip\n")

    print(f"  {'strategy':<34}{'total':>12}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>8}"
          f"{'trades':>7}{'win':>7}{'hold':>8}{'in mkt':>8}")
    print(f"  {'buy and hold':<34}{bh*100:>12,.0f}%"
          f"{((1+bh)**(1/yrs)-1)*100:>9.1f}%{'':>9}{'':>8}{1:>7}{'':>7}{'':>8}{100:>7.1%}")
    print()

    specs = [
        ("trail 0.5%, hold overnight",  dict(stop_bps=50)),
        ("trail 0.5%, flat at bell",    dict(stop_bps=50, eod=True)),
        ("trail 1%, hold overnight",    dict(stop_bps=100)),
        ("trail 1%, flat at bell",      dict(stop_bps=100, eod=True)),
        ("trail 2%, hold overnight",    dict(stop_bps=200)),
        ("trail 2%, flat at bell",      dict(stop_bps=200, eod=True)),
        ("trail 0.25%, flat at bell",   dict(stop_bps=25, eod=True)),
        ("time 30m only",               dict(time_min=30)),
        ("time 30m, flat at bell",      dict(time_min=30, eod=True)),
        ("trail 1% + time 60m + bell",  dict(stop_bps=100, time_min=60, eod=True)),
        ("flat at bell only (no stop)",  dict(eod=True)),
    ]
    for lbl, kw in specs:
        row(lbl, stats(strategy(close, dates, ent, **kw), close, ts, yrs))

    print("\n  the same rules with zero costs, to separate rule from friction:")
    for lbl, kw in specs[:6]:
        row(lbl + " @0bp", stats(strategy(close, dates, ent, cost=0.0, **kw),
                                 close, ts, yrs))

    print("\n" + "=" * 118)
    print("CONTROL — the same exit rules on RANDOM entries, same count")
    print("=" * 118)
    import random
    random.seed(7)
    rnd = sorted(random.sample(range(len(close) - 400), len(ent)))
    for lbl, kw in (("trail 1%, flat at bell", dict(stop_bps=100, eod=True)),
                    ("time 30m, flat at bell", dict(time_min=30, eod=True))):
        row(lbl + " [trigger]", stats(strategy(close, dates, ent, **kw), close, ts, yrs))
        row(lbl + " [random]", stats(strategy(close, dates, rnd, **kw), close, ts, yrs))

    print("\n" + "=" * 118)
    print("WHAT BEING FLAT OVERNIGHT COSTS")
    print("=" * 118)
    on = []
    for i in range(len(close) - 1):
        if dates[i] != dates[i + 1]:
            on.append(close[i + 1] / close[i] - 1)
    intr = []
    day0 = 0
    for i in range(1, len(close)):
        if dates[i] != dates[i - 1]:
            intr.append(close[i - 1] / close[day0] - 1); day0 = i
    eo = 1.0
    for x in on:
        eo *= (1 + x)
    ei = 1.0
    for x in intr:
        ei *= (1 + x)
    print(f"  overnight only (close→next open), {len(on)} nights: "
          f"{(eo-1)*100:>12,.0f}%   {eo**(1/yrs)-1:>7.1%}/yr")
    print(f"  intraday only (open→close), {len(intr)} sessions:   "
          f"{(ei-1)*100:>12,.0f}%   {ei**(1/yrs)-1:>7.1%}/yr")
    print("\n  Being flat at the bell forfeits the overnight leg entirely. That is")
    print("  the whole cost of the rule, and on this tape it is the larger half.")


if __name__ == "__main__":
    main()
