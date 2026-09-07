"""The three-way bracket: take-profit, trailing stop, adaptive time stop.

The proposal, implemented literally:
  enter   at a chosen minute
  target  exit at +X% -- a resting limit, so detected on the bar HIGH
  stop    exit if price retreats 0.5% from the running PEAK -- a resting stop,
          so detected on the bar LOW
  time    if neither fires, exit at the ADAPTIVE limit: the median minutes-to-
          target over the trailing 6 months of trades that DID hit, recomputed
          before every trade from completed history only (no look-ahead)
  bell    a session-close backstop, and an overnight variant

Two implementation choices are stated because they are not neutral:
  * when a bar's high clears the target AND its low breaks the stop, the ORDER
    within the minute is unknowable, so the STOP is assumed to fill first. That
    is the pessimistic reading and the honest one.
  * the stop fills AT its trigger level. Real stops slip; the earlier slippage
    work measured 24-30 bp of it on this instrument, so these results are
    optimistic by roughly that much per stopped trade.

Usage:  python3 retreat_lab/bracket.py [bps_per_side]
"""
import csv, datetime as dt, os, sys
from decimal import Decimal
from statistics import mean, stdev, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

COST = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
LOOKBACK = 126          # ~6 months of sessions
DEFAULT_LIMIT = 30      # minutes, used until history exists


def load():
    rows = []
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            rows.append((t, float(Decimal(a[2])), float(Decimal(a[3])),
                         float(Decimal(a[4]))))          # ts, high, low, close
    ses, cur, d = [], [], rows[0][0].date()
    for x in rows:
        if x[0].date() != d:
            ses.append(dict(date=d, bars=cur)); cur = []; d = x[0].date()
        cur.append(x)
    ses.append(dict(date=d, bars=cur))
    for i, s in enumerate(ses):
        s["mins"] = {b[0].hour * 60 + b[0].minute: k for k, b in enumerate(s["bars"])}
        s["nxt_open"] = ses[i + 1]["bars"][0][3] if i + 1 < len(ses) else None
    return ses


def run(ses, entry_min, target, stop, adaptive=True, fixed_limit=None,
        overnight=False, trail=True, c=0.0):
    """-> list of dicts, one per trade."""
    hist, out = [], []
    for s in ses:
        k = s["mins"].get(entry_min)
        if k is None:
            continue
        lim = (DEFAULT_LIMIT if not hist else int(median(hist))) if adaptive \
            else (fixed_limit if fixed_limit else 10 ** 9)
        px = s["bars"][k][3]
        tgt = px * (1 + target)
        peak = px
        why, ret, held = None, None, None
        for j, b in enumerate(s["bars"][k + 1:], start=1):
            stop_px = (peak if trail else px) * (1 - stop)
            # pessimistic: if both trigger in the same minute, the stop wins
            if b[2] <= stop_px:
                why, ret, held = "stop", stop_px / px - 1, j; break
            if b[1] >= tgt:
                why, ret, held = "target", target, j
                hist.append(j)
                if len(hist) > LOOKBACK:
                    hist.pop(0)
                break
            if b[1] > peak:
                peak = b[1]
            if j >= lim:
                why, ret, held = "time", b[3] / px - 1, j; break
        if why is None:
            if overnight and s["nxt_open"] is not None:
                why, ret, held = "overnight", s["nxt_open"] / px - 1, len(s["bars"]) - k
            else:
                why, ret, held = "bell", s["bars"][-1][3] / px - 1, len(s["bars"]) - k - 1
        out.append(dict(D=s["date"], why=why, ret=ret - 2 * c, held=held, limit=lim))
    return out


def summ(lbl, tr, yrs):
    if len(tr) < 20:
        print(f"  {lbl:<30} (thin)"); return
    v = [x["ret"] for x in tr]
    eq = 1.0; pk = 1.0; dd = 0.0
    for x in v:
        eq *= (1 + x); pk = max(pk, eq); dd = min(dd, eq / pk - 1)
    n = len(v)
    cnt = {w: sum(1 for x in tr if x["why"] == w) / n
           for w in ("target", "stop", "time", "bell", "overnight")}
    sd = stdev(v)
    print(f"  {lbl:<30}{n:>6}{cnt['target']:>8.1%}{cnt['stop']:>8.1%}"
          f"{cnt['time']+cnt['bell']+cnt['overnight']:>8.1%}"
          f"{mean(v)*100:>9.3f}%{(eq-1)*100:>11,.0f}%"
          f"{(eq**(1/yrs)-1 if eq>0 else -1)*100:>8.1f}%{dd*100:>8.1f}%"
          f"{mean(v)/(sd/n**0.5):>7.2f}")


def main():
    ses = load()
    yrs = (ses[-1]["date"] - ses[0]["date"]).days / 365.25
    c = COST / 10000.0
    print(f"SOXL, {ses[0]['date']} → {ses[-1]['date']}, {len(ses)} sessions, "
          f"{COST:.1f} bps/side")
    print("same-minute target+stop resolved as STOP FIRST (pessimistic); "
          "stops fill at trigger (optimistic by the 24-30bp measured earlier)\n")
    hdr = (f"  {'config':<30}{'n':>6}{'targ%':>8}{'stop%':>8}{'time%':>8}"
           f"{'mean':>9}{'total':>11}{'CAGR':>8}{'maxDD':>8}{'t':>7}")

    for tgt in (0.01, 0.02):
        print("=" * 116)
        print(f"TARGET +{tgt:.0%}, trailing stop 0.5% off the peak, "
              f"adaptive time stop (6mo median), bell backstop")
        print("=" * 116); print(hdr)
        for m, lbl in ((570, "09:30"), (660, "11:00"), (780, "13:00"),
                       (840, "14:00"), (900, "15:00"), (930, "15:30")):
            summ(f"enter {lbl}", run(ses, m, tgt, 0.005, c=c), yrs)
        print()

    print("=" * 116)
    print("WHAT EACH RULE CONTRIBUTES — enter 09:30, target +1%")
    print("=" * 116); print(hdr)
    summ("target only (bell backstop)", run(ses, 570, 0.01, 1.0, adaptive=False, c=c), yrs)
    summ("+ trailing stop 0.5%", run(ses, 570, 0.01, 0.005, adaptive=False, c=c), yrs)
    summ("+ adaptive time stop", run(ses, 570, 0.01, 0.005, adaptive=True, c=c), yrs)
    summ("stop from ENTRY not peak", run(ses, 570, 0.01, 0.005, adaptive=True,
                                         trail=False, c=c), yrs)
    for w in (0.01, 0.02):
        summ(f"trailing stop {w:.0%} instead", run(ses, 570, 0.01, w, c=c), yrs)
    for fl in (5, 15, 60):
        summ(f"fixed {fl}m time stop", run(ses, 570, 0.01, 0.005, adaptive=False,
                                           fixed_limit=fl, c=c), yrs)

    print("\n" + "=" * 116)
    print("THE ADAPTIVE LIMIT ITSELF — what the trailing 6mo median chose")
    print("=" * 116)
    tr = run(ses, 570, 0.01, 0.005, c=c)
    lims = [x["limit"] for x in tr]
    print(f"  median {median(lims):.0f} min, range {min(lims)}-{max(lims)}, "
          f"mean {mean(lims):.1f}")
    hit = [x["held"] for x in tr if x["why"] == "target"]
    print(f"  actual minutes-to-target when hit: median {median(hit):.0f}, "
          f"n={len(hit)}")
    print(f"\n  mean return by exit reason:")
    for w in ("target", "stop", "time", "bell"):
        v = [x["ret"] for x in tr if x["why"] == w]
        if v:
            print(f"    {w:<10} n={len(v):>5} ({len(v)/len(tr):>5.1%})  "
                  f"mean {mean(v)*100:>8.3f}%  total contribution "
                  f"{sum(v)*100:>9.1f}pp")

    print("\n" + "=" * 116)
    print("OVERNIGHT VARIANT — same bracket, but hold to the next open if unresolved")
    print("=" * 116); print(hdr)
    for m, lbl in ((840, "14:00"), (900, "15:00"), (930, "15:30")):
        summ(f"enter {lbl}", run(ses, m, 0.01, 0.005, overnight=True, c=c), yrs)


if __name__ == "__main__":
    main()
