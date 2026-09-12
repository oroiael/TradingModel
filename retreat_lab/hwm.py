"""High-water-mark sweeping vs. the naive every-profitable-week sweep.

The question this answers: sweep.py banks 25% of every profitable week. That
is a RATCHET — it takes cash out on the way up and again on every bounce
inside a drawdown, so an account that ends a quarter flat can still have paid
out repeatedly. A high-water mark fixes that: you only bank on money the
account has never had before.

Definition used here
  hwm  = the highest TRADING-account equity ever recorded at a weekly mark.
  sweep = pct * max(0, equity_now - hwm), taken after the week's trading.
  hwm  = max(hwm, equity after the sweep).

Three consequences worth seeing in the numbers:
  * a losing week sweeps nothing (same as before), AND
  * a winning week that only recovers ground already lost sweeps nothing, and
  * the mark ratchets by the RETAINED part only (1-pct of the new high), so
    the next dollar above the old peak is swept again rather than being
    permanently exempt.

The mark is kept on the TRADING account, not on trading+reserve. If it were
kept on the total, the reserve's own interest would keep lifting the mark and
sweeping would eventually stop on its own. Both are shown.

Interest on the reserve accrues weekly BEFORE that week's sweep is added, the
same ordering sweep.py uses, so the two scripts' totals are comparable.

Usage:  python3 retreat_lab/hwm.py [bps_per_side] [capital] [fraction] [sweep_pct]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import stdev, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, BARS, SYMBOL, SUF

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
CAP = float(sys.argv[2]) if len(sys.argv) > 2 else 100_000.0
F = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
SWEEP = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25
MARGIN = 0.06
BURN = 252
OUT = os.path.join(ROOT, "retreat_lab/out")
RATES = {2021: 0.0005, 2022: 0.0200, 2023: 0.0500,
         2024: 0.0500, 2025: 0.0425, 2026: 0.0400}


def daily(name):
    o, c, d = {}, {}, []
    with open(os.path.join(ROOT, name)) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            k = t.date()
            if k not in o:
                o[k] = float(Decimal(a[1])); d.append(k)
            c[k] = float(Decimal(a[4]))
    return d, o, c


def pctile(xs, p):
    s = sorted(xs); k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main():
    days, op, cl = daily(BARS)
    c = COST / 10000.0
    dret = [cl[days[i]] / cl[days[i - 1]] - 1 for i in range(1, len(days))]
    rv = {}
    for i in range(20, len(days)):
        rv[i] = stdev(dret[i - 20:i]) * (252 ** 0.5) * 100
    nights = [(i, (op[days[i + 1]] / cl[days[i]] - 1) - 2 * c)
              for i in range(len(days) - 1) if i in rv]
    first = nights[0][0]
    live = [(i, r) for i, r in nights if i >= first + BURN]
    sel = {}
    for i, r in live:
        h = [rv[j] for j in sorted(rv) if j < i]
        if len(h) >= 60 and rv[i] < pctile(h, 60):
            sel[days[i]] = (r, cl[days[i]] / op[days[i]] - 1)
    keep = {d: v[0] for d, v in sel.items() if v[1] >= -0.04}
    t0 = days[live[0][0]]
    yrs = (days[live[-1][0]] - t0).days / 365.25
    per_night = max(F - 1, 0) * MARGIN / 365.0
    weeks = sorted({days[i] - dt.timedelta(days=days[i].weekday()) for i, _ in live})
    bucket = {}
    for d, r in keep.items():
        bucket.setdefault(d - dt.timedelta(days=d.weekday()), []).append(r)

    def sim(mode, pct=SWEEP, floor=0.0, rate=None):
        """mode: 'none' | 'every' (sweep every profitable week) | 'hwm' | 'hwm_total'"""
        rate = rate or (lambda w: RATES.get(w.year, 0.04))
        trade = CAP; res = 0.0; hwm = CAP; pk = CAP; dd = 0.0
        rows = []
        for w in weeks:
            start = trade
            for r in bucket.get(w, []):
                trade *= (1 + F * r - per_night)
            pnl = trade - start
            res *= (1 + rate(w) / 52.0)
            mark = trade + res if mode == "hwm_total" else trade
            hwm_before = hwm
            sw = 0.0
            if mode == "every" and pnl > 0:
                sw = pnl * pct
            elif mode in ("hwm", "hwm_total") and mark > hwm:
                sw = (mark - hwm) * pct
            if sw < floor:
                sw = 0.0
            if sw:
                trade -= sw; res += sw
            hwm = max(hwm, trade + res if mode == "hwm_total" else trade)
            tot = trade + res
            pk = max(pk, tot); dd = min(dd, tot / pk - 1)
            y = max((w + dt.timedelta(days=4) - t0).days / 365.25, 1 / 365.25)
            rows.append(dict(week_starting=w.isoformat(), nights=len(bucket.get(w, [])),
                             trading_pnl=round(pnl, 2),
                             equity_before_sweep=round(mark, 2),
                             hwm_before=round(hwm_before, 2),
                             swept_to_reserve=round(sw, 2),
                             trading_equity=round(trade, 2), reserve=round(res, 2),
                             high_water_mark=round(hwm, 2), total=round(tot, 2),
                             running_cagr_pct=round(((tot / CAP) ** (1 / y) - 1) * 100, 2),
                             drawdown_pct=round((tot / pk - 1) * 100, 2)))
        return trade, res, dd, rows

    def dry(rows):
        best = cur = 0; a = b = None; s = None
        for r in rows:
            if r["swept_to_reserve"] > 0:
                cur = 0; s = None
            else:
                cur += 1
                s = s or r["week_starting"]
                if cur > best:
                    best, a, b = cur, s, r["week_starting"]
        return best, a, b

    print(f"p60 + skip -4%, f={F:.1f}, ${CAP:,.0f}, {COST:.1f} bps/side, "
          f"{MARGIN:.0%}/yr margin, sweep {SWEEP:.0%}")
    print(f"{t0} → {days[live[-1][0]]} ({yrs:.1f}y, {len(keep)} nights, "
          f"{len(weeks)} weeks)\n")

    print(f"  {'sweep rule':<30}{'trading':>12}{'reserve':>12}{'total':>12}"
          f"{'CAGR':>8}{'maxDD':>8}{'weeks swept':>13}{'longest dry':>13}")
    store = {}
    for lbl, m in (("none (all reinvested)", "none"),
                   ("every profitable week", "every"),
                   ("high-water mark (trading)", "hwm"),
                   ("high-water mark (total)", "hwm_total")):
        tr, rs, dd, rows = sim(m)
        store[m] = rows
        n = sum(1 for r in rows if r["swept_to_reserve"] > 0)
        best, a, b = dry(rows)
        print(f"  {lbl:<30}{tr:>11,.0f}{rs:>12,.0f}{tr+rs:>12,.0f}"
              f"{((tr+rs)/CAP)**(1/yrs)-1:>7.1%}{dd*100:>7.1f}%{n:>9}/{len(rows):<3}"
              f"{best:>10}w")
    print(f"    longest dry stretch, HWM rule: {dry(store['hwm'])[1]} → "
          f"{dry(store['hwm'])[2]}")

    print(f"\n  WHY THEY DIFFER — 2022 drawdown and recovery (HWM rule)")
    print(f"  {'week':<12}{'start':>10}{'after trading':>15}{'HWM':>11}"
          f"{'above?':>10}{'swept':>9}{'end equity':>12}{'HWM after':>11}")
    prev = None
    for r in store["hwm"]:
        d = dt.date.fromisoformat(r["week_starting"])
        if not (dt.date(2022, 7, 25) <= d <= dt.date(2022, 11, 21)):
            prev = r; continue
        st = r["trading_equity"] + r["swept_to_reserve"] - r["trading_pnl"]
        aft = r["trading_equity"] + r["swept_to_reserve"]
        h = prev["high_water_mark"] if prev else CAP
        print(f"  {r['week_starting']:<12}{st:>10,.0f}{aft:>15,.0f}{h:>11,.0f}"
              f"{aft-h:>10,.0f}{r['swept_to_reserve']:>9,.0f}"
              f"{r['trading_equity']:>12,.0f}{r['high_water_mark']:>11,.0f}")
        prev = r

    print(f"\n  MINIMUM SWEEP SIZE (skip transfers below the floor, HWM rule)")
    print(f"  {'floor':<12}{'weeks swept':>13}{'total banked':>15}{'total equity':>15}")
    for fl in (0.0, 250.0, 1000.0, 5000.0):
        tr, rs, dd, rows = sim("hwm", floor=fl)
        n = sum(1 for r in rows if r["swept_to_reserve"] > 0)
        print(f"  ${fl:<11,.0f}{n:>13}{sum(r['swept_to_reserve'] for r in rows):>15,.0f}"
              f"{tr+rs:>15,.0f}")

    print(f"\n  SWEEP RATE, HWM RULE")
    print(f"  {'pct':<8}{'trading':>12}{'reserve':>12}{'total':>12}{'CAGR':>8}{'maxDD':>8}")
    for p in (0.10, 0.25, 0.50, 0.75, 1.00):
        tr, rs, dd, _ = sim("hwm", pct=p)
        print(f"  {p:<8.0%}{tr:>11,.0f}{rs:>12,.0f}{tr+rs:>12,.0f}"
              f"{((tr+rs)/CAP)**(1/yrs)-1:>7.1%}{dd*100:>7.1f}%")

    rows = store["hwm"]
    path = os.path.join(OUT, f"weekly_hwm{int(SWEEP*100)}_f{int(F*10)}{SUF}.csv")
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        wr.writeheader(); wr.writerows(rows)
    sw = [r["swept_to_reserve"] for r in rows]
    pos = [x for x in sw if x > 0]
    print(f"\n  HWM rule: {len(pos)}/{len(rows)} weeks swept, median ${median(pos):,.0f}, "
          f"largest ${max(sw):,.0f}, banked ${sum(sw):,.0f}")
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
