"""Enter SOXL at a chosen time, exit the moment it is up X% — does that work?

A take-profit is the mirror of everything tested so far: it caps the upside at the
target and leaves the downside running to whatever the fallback exit is. Win rates
will be high by construction; the question is whether the losses on the days the
target never comes are small enough to leave anything behind.

  entry    the close of a chosen minute
  target   a resting limit at entry x (1 + X). A limit SELL fills when price
           TRADES there, so the target is detected on the bar HIGH, not the close
           -- the one place in this lab where intrabar data is the correct field
           rather than an optimistic one.
  fallback if the target never prints: exit at the session close, or hold to the
           next open (tested separately, since the overnight leg is where this
           instrument's return lives)

Also asks the user's second question directly: which days should not be traded --
by weekday, by volatility regime, by that morning's gap, by the prior day.

Usage:  python3 retreat_lab/take_profit.py [bps_per_side]
"""
import csv, datetime as dt, os, sys, math
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def load():
    """-> sessions: list of dicts with per-minute arrays for one session."""
    rows = []
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            rows.append((t, float(Decimal(a[2])), float(Decimal(a[4]))))  # ts, high, close
    ses, cur, d = [], [], rows[0][0].date()
    for x in rows:
        if x[0].date() != d:
            ses.append(dict(date=d, bars=cur)); cur = []; d = x[0].date()
        cur.append(x)
    ses.append(dict(date=d, bars=cur))
    for i, s in enumerate(ses):
        s["mins"] = {b[0].hour * 60 + b[0].minute: k for k, b in enumerate(s["bars"])}
        s["nxt_open"] = ses[i + 1]["bars"][0][2] if i + 1 < len(ses) else None
    return ses


def trade(s, entry_min, target, hold_overnight, c):
    """-> (net return, hit?) or None if the session has no such minute."""
    k = s["mins"].get(entry_min)
    if k is None:
        return None
    px = s["bars"][k][2]
    lim = px * (1 + target)
    for b in s["bars"][k + 1:]:
        if b[1] >= lim:                       # limit fills on the high
            return lim / px - 1 - 2 * c, True
    if hold_overnight:
        if s["nxt_open"] is None:
            return None
        return s["nxt_open"] / px - 1 - 2 * c, False
    return s["bars"][-1][2] / px - 1 - 2 * c, False


def summarise(rs, yrs):
    if len(rs) < 20:
        return None
    v = [x[0] for x in rs]
    eq = 1.0; pk = 1.0; dd = 0.0
    for x in v:
        eq *= (1 + x); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    hit = sum(1 for x in rs if x[1]) / len(rs)
    sd = stdev(v)
    return dict(n=len(v), hit=hit, mean=mean(v), med=sorted(v)[len(v) // 2],
                total=eq - 1, cagr=eq ** (1 / yrs) - 1 if eq > 0 else -1,
                dd=dd, worst=min(v), sd=sd,
                t=mean(v) / (sd / len(v) ** 0.5) if sd else 0)


def row(lbl, s):
    if not s:
        print(f"  {lbl:<24} (thin)"); return
    print(f"  {lbl:<24}{s['n']:>6}{s['hit']:>8.1%}{s['mean']*100:>9.3f}%"
          f"{s['med']*100:>9.3f}%{s['total']*100:>12,.0f}%{s['cagr']*100:>9.1f}%"
          f"{s['dd']*100:>9.1f}%{s['worst']*100:>8.1f}%{s['t']:>7.2f}")


def main():
    ses = load()
    yrs = (ses[-1]["date"] - ses[0]["date"]).days / 365.25
    c = COST / 10000.0
    print(f"SOXL, {ses[0]['date']} → {ses[-1]['date']}, {len(ses)} sessions, "
          f"{COST:.1f} bps/side")
    print("target detected on the bar HIGH (a resting limit fills on a trade)\n")
    hdr = (f"  {'config':<24}{'n':>6}{'hit%':>8}{'mean':>9}{'median':>9}"
           f"{'total':>12}{'CAGR':>9}{'maxDD':>9}{'worst':>8}{'t':>7}")

    times = [(570, "09:30"), (600, "10:00"), (660, "11:00"), (720, "12:00"),
             (780, "13:00"), (840, "14:00"), (900, "15:00"), (930, "15:30")]
    for tgt in (0.01, 0.02, 0.03):
        print("=" * 116)
        print(f"TARGET +{tgt:.0%}, fallback = exit at the session close")
        print("=" * 116); print(hdr)
        for m, lbl in times:
            rs = [x for x in (trade(s, m, tgt, False, c) for s in ses) if x]
            row(f"enter {lbl}", summarise(rs, yrs))
        print()

    print("=" * 116)
    print("TARGET +1%, fallback = HOLD OVERNIGHT to the next open")
    print("=" * 116); print(hdr)
    for m, lbl in times:
        rs = [x for x in (trade(s, m, 0.01, True, c) for s in ses) if x]
        row(f"enter {lbl}", summarise(rs, yrs))

    # --- which days not to trade: use the best plain config as the base
    print("\n" + "=" * 116)
    print("WHICH DAYS NOT TO TRADE — enter 15:30, target +1%, hold to next open")
    print("=" * 116)
    dret = {}
    for i in range(1, len(ses)):
        dret[ses[i]["date"]] = (ses[i]["bars"][-1][2] / ses[i - 1]["bars"][-1][2] - 1)
    ds = sorted(dret)
    rv = {}
    for i in range(20, len(ds)):
        rv[ds[i]] = stdev(dret[ds[j]] for j in range(i - 20, i)) * (252 ** 0.5) * 100
    recs = []
    for i, s in enumerate(ses):
        r = trade(s, 930, 0.01, True, c)
        if not r:
            continue
        gap = (s["bars"][0][2] / ses[i - 1]["bars"][-1][2] - 1) if i else None
        recs.append(dict(r=r, D=s["date"], dow=s["date"].weekday(),
                         rv=rv.get(s["date"]), gap=gap,
                         prev=dret.get(ses[i - 1]["date"]) if i else None))
    print(hdr)
    row("all sessions", summarise([x["r"] for x in recs], yrs))
    print("  --- by weekday ---")
    for w in range(5):
        row(f"  {DOW[w]}", summarise([x["r"] for x in recs if x["dow"] == w], yrs))
    print("  --- by RV20 quintile (through the prior close) ---")
    hv = [x for x in recs if x["rv"] is not None]
    vals = sorted(x["rv"] for x in hv)
    qs = [vals[int(len(vals) * q)] for q in (0.2, 0.4, 0.6, 0.8)]
    lo = -1e9
    for k, hi in enumerate(qs + [1e9]):
        b = [x["r"] for x in hv if lo <= x["rv"] < hi]
        row(f"  Q{k+1}" + ("  lowest vol" if k == 0 else "  highest vol" if k == 4 else ""),
            summarise(b, yrs)); lo = hi
    print("  --- by that morning's gap ---")
    hg = [x for x in recs if x["gap"] is not None]
    for lbl, f in ((" gap < -2%", lambda g: g < -0.02),
                   (" gap -2 to 0%", lambda g: -0.02 <= g < 0),
                   (" gap 0 to +2%", lambda g: 0 <= g < 0.02),
                   (" gap > +2%", lambda g: g >= 0.02)):
        row(f"  {lbl}", summarise([x["r"] for x in hg if f(x["gap"])], yrs))
    print("  --- by the prior session's close-to-close ---")
    hp = [x for x in recs if x["prev"] is not None]
    for lbl, f in ((" prior day < -3%", lambda g: g < -0.03),
                   (" prior day -3 to 0%", lambda g: -0.03 <= g < 0),
                   (" prior day 0 to +3%", lambda g: 0 <= g < 0.03),
                   (" prior day > +3%", lambda g: g >= 0.03)):
        row(f"  {lbl}", summarise([x["r"] for x in hp if f(x["prev"])], yrs))


if __name__ == "__main__":
    main()
