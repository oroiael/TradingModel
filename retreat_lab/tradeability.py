"""What the retreat episodes are worth as trades, measured — not assumed.

retreat_timing.py measured TIMING. Timing alone is an exposure profile, not an
edge. This script turns each episode ledger into a trade log and prices it:

  LONG  buy at the upswing trigger, sell at the retreat  (the mechanical
        trailing-stop momentum trade the episodes literally describe)
  SHORT sell at the retreat, cover after a fixed horizon  (is the trailing-stop
        breach a continuation signal?)
  FADE  sell at the trigger, cover at the retreat         (the mirror of LONG)

Everything is measured against buy-and-hold over the same window, with and
without a one-bar execution lag (you see a close, you trade the next bar) and
with a per-side cost knob in basis points.

Usage:  python3 retreat_lab/tradeability.py [cost_bps_per_side]
"""
import csv, sys, os, datetime as dt
from decimal import Decimal
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import CONFIGS, bl, tag, ROOT, pct

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0     # bps per side


def load():
    close, ts, idx = [], [], {}
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            idx[t] = len(close); ts.append(t)
            close.append(float(Decimal(a[4])))
    return close, ts, idx


def ledger(up_bps, dn_bps, idx):
    f = os.path.join(ROOT, "retreat_lab/out",
                     f"retreat_episodes_1min_{tag(up_bps, dn_bps)}.csv")
    T = lambda s: idx[dt.datetime.strptime(s, "%Y-%m-%d %H:%M")]
    return [(T(r["trigger_ts"]), T(r["peak_ts"]), T(r["retreat_ts"]))
            for r in csv.DictReader(open(f))]


def stats(rets):
    n = len(rets)
    wins = sum(1 for x in rets if x > 0)
    tot = 1.0
    for x in rets:
        tot *= (1 + x)
    return dict(n=n, win=wins / n, mean=sum(rets) / n, med=median(rets),
                p10=pct(rets, 10), p90=pct(rets, 90),
                worst=min(rets), best=max(rets), compound=tot - 1)


def line(lbl, s, extra=""):
    print(f"  {lbl:<22}{s['n']:>6} {s['win']:>6.1%} {s['mean']*100:>8.3f}% "
          f"{s['med']*100:>8.3f}% {s['p10']*100:>8.2f}% {s['p90']*100:>7.2f}% "
          f"{s['worst']*100:>8.1f}% {s['best']*100:>7.1f}% {extra}")


def main():
    close, ts, idx = load()
    bh = close[-1] / close[0] - 1
    yrs = (ts[-1] - ts[0]).days / 365.25
    print(f"SOXL_1min.csv  {ts[0]:%Y-%m-%d} → {ts[-1]:%Y-%m-%d}  ({yrs:.1f}y)")
    print(f"Buy-and-hold over the same window: {bh*100:,.0f}%  "
          f"({(1+bh)**(1/yrs)-1:.1%} / yr), {close[0]:.2f} → {close[-1]:.2f}")
    print(f"Costs applied: {COST:.0f} bps per side ({COST*2:.0f} bps round trip)\n")

    c = COST / 10000.0
    for up_bps, dn_bps in CONFIGS:
        eps = ledger(up_bps, dn_bps, idx)
        U, D = bl(up_bps), bl(dn_bps)
        print("=" * 118)
        print(f"{U} upswing / {D} retreat — {len(eps)} episodes")
        print("=" * 118)
        print(f"  {'trade':<22}{'n':>6} {'win%':>6} {'mean':>9} {'median':>9} "
              f"{'p10':>9} {'p90':>8} {'worst':>9} {'best':>8}")

        # --- LONG: enter at trigger, exit at retreat. lag 0 and 1 bar.
        for lag in (0, 1):
            r = []
            for g, p, x in eps:
                a, b = g + lag, x + lag
                if b >= len(close):
                    continue
                r.append((close[b] / close[a] - 1) - 2 * c)
            s = stats(r)
            line(f"LONG trig→retreat L{lag}", s,
                 f"compound {s['compound']*100:>10,.0f}%")

        # --- FADE: short at the trigger, cover at the retreat (mirror of LONG)
        r = [-(close[x] / close[g] - 1) - 2 * c for g, p, x in eps]
        line("FADE short trig→ret", stats(r),
             f"compound {stats(r)['compound']*100:>10,.0f}%")

        # --- SHORT after the retreat: is the breach a continuation signal?
        for h in (15, 30, 60, 390):
            r = [-(close[x + h] / close[x] - 1) - 2 * c
                 for g, p, x in eps if x + h < len(close)]
            line(f"SHORT ret +{h}min", stats(r))

        # --- what the trade captures of the move it is riding
        cap = [(close[x] / close[g] - 1) / (close[p] / close[g] - 1)
               for g, p, x in eps if close[p] > close[g]]
        runup = [close[p] / close[g] - 1 for g, p, x in eps]
        expo = sum(x - g for g, p, x in eps) / len(close)
        print(f"\n  run-up trigger→peak: med {median(runup)*100:.2f}%   "
              f"share of that run-up still held at the exit: med "
              f"{median(cap)*100:.0f}%")
        print(f"  time in market: {expo:.1%} of all bars   "
              f"round trips per year: {len(eps)/yrs:.0f}\n")


if __name__ == "__main__":
    main()
