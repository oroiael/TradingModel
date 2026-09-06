"""Does the sequential, non-overlapping episode rule distort the timing answer?

retreat_timing.py runs ONE episode at a time: the anchor is the running trough
since the previous retreat, and no new upswing is hunted while an episode is
open. Two couplings follow — the anchor depends on when the last episode ended,
and a qualifying upswing is skipped if another episode is already running.

This script re-measures the same durations with BOTH couplings removed:

  anchor  = trailing minimum over a FIXED lookback of L bars (no episode memory)
  trigger = every bar that is the FIRST crossing of that rolling anchor's
            +up% line (close[i] over, close[i-1] not over)
  episode = run forward independently to peak and retreat, OVERLAPS ALLOWED

If the duration distribution matches the primary engine, the sequencing rule is
not what produces the answer. Prices are integer cents, thresholds integer bps,
exactly as in the engine.

Usage:  python3 retreat_lab/independence_check.py [lookback_bars]
"""
import csv, sys, os, datetime as dt
from collections import deque
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import BPS, CONFIGS, bl, ROOT, pct

L = int(sys.argv[1]) if len(sys.argv) > 1 else 390     # 390 bars = one session


def load():
    close, ts = [], []
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            ts.append(dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S"))
            close.append(int((Decimal(a[4]) * 100).to_integral_exact()))
    return close, ts


def rolling_min(px, L):
    """min over the trailing L bars, inclusive. O(n) monotonic deque."""
    out, dq = [], deque()
    for i, v in enumerate(px):
        while dq and px[dq[-1]] >= v:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - L:
            dq.popleft()
        out.append(px[dq[0]])
    return out


def independent(close, up_bps, dn_bps, L, overlap=True):
    """Rolling-window anchor. overlap=True lets a new episode start while another
    is open; overlap=False skips triggers that land inside an open episode, so
    only the non-overlap rule differs between the two."""
    up_n, dn_n = BPS + up_bps, BPS - dn_bps
    rmin = rolling_min(close, L)
    over = [close[i] * BPS >= rmin[i] * up_n for i in range(len(close))]

    legA, legB, tot, censored = [], [], [], 0
    busy_until = -1
    for i in range(1, len(close)):
        if not (over[i] and not over[i - 1]):
            continue                                    # not a first crossing
        if not overlap and i < busy_until:
            continue                                    # inside an open episode
        peak, peak_i, done = close[i], i, False
        for j in range(i + 1, len(close)):
            if close[j] > peak:
                peak, peak_i = close[j], j
            if close[j] * BPS <= peak * dn_n:
                legA.append(peak_i - i); legB.append(j - peak_i); tot.append(j - i)
                busy_until = j
                done = True
                break
        if not done:
            censored += 1
    return legA, legB, tot, censored


def primary_medians():
    """Median total from the committed ledgers, for side-by-side comparison."""
    out = {}
    for up_bps, dn_bps in CONFIGS:
        f = os.path.join(ROOT, "retreat_lab/out",
                         f"retreat_episodes_1min_up{up_bps}_dn{dn_bps}.csv")
        t = [int(r["total_mkt_min"]) for r in csv.DictReader(open(f))]
        out[(up_bps, dn_bps)] = (len(t), pct(t, 50), pct(t, 90))
    return out


def main():
    close, ts = load()
    print(f"SOXL_1min.csv — {len(close):,} bars, {ts[0]:%Y-%m-%d} → {ts[-1]:%Y-%m-%d}")
    print(f"Anchor for both variants = trailing min over L={L} bars "
          f"({L/390:.1f} session), no episode memory.\n")
    prim = primary_medians()
    print("                 PRIMARY (event anchor,   V2 (rolling anchor,     "
          "V1 (rolling anchor,")
    print("                  no overlap)             no overlap)             "
          "overlap allowed)")
    print(f"  {'pair':<11}{'n':>7}{'med':>6}{'p90':>6}   {'n':>7}{'med':>6}{'p90':>6}"
          f"   {'n':>7}{'med':>6}{'p90':>6}{'cens':>6}")
    for up_bps, dn_bps in CONFIGS:
        pn, pm, pp = prim[(up_bps, dn_bps)]
        _, _, t2, _ = independent(close, up_bps, dn_bps, L, overlap=False)
        _, _, t1, c1 = independent(close, up_bps, dn_bps, L, overlap=True)
        lbl = f"{bl(up_bps)}/{bl(dn_bps)}"
        print(f"  {lbl:<11}{pn:>7}{pm:>6.0f}{pp:>6.0f}   "
              f"{len(t2):>7}{pct(t2,50):>6.0f}{pct(t2,90):>6.0f}   "
              f"{len(t1):>7}{pct(t1,50):>6.0f}{pct(t1,90):>6.0f}{c1:>6}")
    print("\n  PRIMARY vs V2 isolates the ANCHOR rule (event-reset vs rolling window).")
    print("  V2 vs V1 isolates the NON-OVERLAP rule, holding the anchor fixed.")


if __name__ == "__main__":
    main()
