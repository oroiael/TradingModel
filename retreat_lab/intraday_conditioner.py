"""Does the day's move BY 15:45 predict tonight's gap?

## The hypothesis, stated before the test

A 3x ETF must rebalance into every close to hold its leverage: on an up day it
buys, on a down day it sells, and the size of the required trade scales with the
day's move. If that forced flow pushes the closing print away from fair value,
the distortion should REVERSE overnight. The prediction is therefore a NEGATIVE
relationship between the day's move and the following gap — big up day, give it
back; big down day, bounce.

This is the one piece of information genuinely known at 15:45 that the deployed
rule ignores entirely.

## The trap, and how it is avoided

`close(D)/open(D) - 1` is NOT known at 15:45, and using it is catastrophic
rather than merely wrong: the entry price IS close(D), so close(D) would appear
in both the conditioner and the denominator of the return being predicted. Any
mechanical relationship between them then shows up as a spectacular fake edge.

So the conditioner is `px(15:45)/open(D) - 1`, taken from the 1-minute file,
which is the last price observable before the MOC deadline. The LEAKY version is
computed too and printed beside it — not as an alternative, but so the size of
the illusion is visible and the reader can see the clean test is not it.

Returns come from the daily file, whose open and close are auction prints and
therefore the prices actually transacted. The conditioner comes entirely from
the 1-minute file so it is internally consistent. Half-days with a 13:00 close
have no 15:45 bar and are dropped (12 of 1,641).

## Three checks on the test itself

  LEAKY CONTROL    the same test with close(D) as the conditioner. It must look
                   dramatically better, or the test is not sensitive enough to
                   detect the leak it is designed to avoid.
  PLACEBO          the conditioner shuffled against the returns, fixed seed.
                   Any structure surviving this is an artifact of the method.
  SPLIT SAMPLE     halves must agree.

Usage:  python3 retreat_lab/intraday_conditioner.py [start_year]
"""
import csv, datetime as dt, os, random, sys
from decimal import Decimal
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
_argv, sys.argv = sys.argv, sys.argv[:1]
from coverage import load, walk, corr                        # noqa: E402
sys.argv = _argv

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
CUTOFF = "15:45"


def intraday_marks():
    """open, the 15:45 print, and the last print — all from the 1-minute grid."""
    o, p, c = {}, {}, {}
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as fh:
        r = csv.reader(fh)
        next(r)
        for a in r:
            t = dt.datetime.strptime(a[0].replace(" America/New_York", ""),
                                     "%Y%m%d %H:%M:%S")
            d = t.date()
            if d not in o:
                o[d] = float(Decimal(a[1]))
            c[d] = float(Decimal(a[4]))
            if t.strftime("%H:%M") == CUTOFF:
                p[d] = float(Decimal(a[4]))
    return o, p, c


def buckets(pairs, k=10):
    """pairs = [(conditioner, return)]. Equal-count buckets, low to high."""
    s = sorted(pairs)
    n = len(s)
    out = []
    for i in range(k):
        seg = s[i * n // k:(i + 1) * n // k]
        v = [y for _, y in seg]
        out.append((seg[0][0], seg[-1][0], mean(v) * 100,
                    sum(1 for x in v if x > 0) / len(v) * 100, len(v)))
    return out


def show(title, pairs):
    print(f"\n  {title}   n={len(pairs)}   corr = "
          f"{corr([a for a, _ in pairs], [b for _, b in pairs]):+.4f}")
    print(f"    {'decile':<8}{'range of the day move':>26}{'overnight':>12}"
          f"{'win':>8}{'n':>6}")
    for i, (lo, hi, m, w, n) in enumerate(buckets(pairs), 1):
        print(f"    {i:<8}{f'{lo*100:+7.2f}% .. {hi*100:+7.2f}%':>26}"
              f"{m:>11.3f}%{w:>7.1f}%{n:>6}")


def main():
    o1, p1545, c1 = intraday_marks()
    d, do, dc = load("retreat_lab/out/SOXL_daily_ibkr.csv")
    S = {d[i]: dict(on=do[d[i + 1]] / dc[d[i]] - 1) for i in range(len(d) - 1)}

    days = [x for x in sorted(S)
            if x.year >= START and x in p1545 and x in o1 and x in c1]
    print(f"INTRADAY CONDITIONER   {len(days)} sessions from {START}")
    print(f"conditioner: SOXL {CUTOFF} print vs the day's open, 1-minute file")
    print(f"return:      close -> next open, daily file (auction prints)")

    clean = [(p1545[x] / o1[x] - 1, S[x]["on"]) for x in days]
    leaky = [(c1[x] / o1[x] - 1, S[x]["on"]) for x in days]

    show("CLEAN — move by 15:45, the only version that is tradeable", clean)
    show("LEAKY CONTROL — move to the CLOSE. Not knowable at 15:45.", leaky)

    rng = random.Random(20260917)
    sh = [b for _, b in clean]
    rng.shuffle(sh)
    show("PLACEBO — conditioner shuffled against returns, seed 20260917",
         [(a, b) for (a, _), b in zip(clean, sh)])

    # ---- split sample on the clean version --------------------------------
    mid = len(days) // 2
    print(f"\n  SPLIT SAMPLE (clean)")
    print(f"    {'window':<34}{'corr':>9}{'bottom decile':>16}{'top decile':>14}")
    for lbl, a, b in (("first  " + str(days[0]) + ".." + str(days[mid - 1]), 0, mid),
                      ("second " + str(days[mid]) + ".." + str(days[-1]), mid, len(days))):
        sub = clean[a:b]
        bk = buckets(sub)
        print(f"    {lbl:<34}"
              f"{corr([x for x,_ in sub],[y for _,y in sub]):>+9.4f}"
              f"{bk[0][2]:>15.3f}%{bk[-1][2]:>13.3f}%")

    out = os.path.join(ROOT, "retreat_lab/out/intraday_conditioner.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "move_by_1545_pct", "move_to_close_pct",
                    "overnight_pct"])
        for x in days:
            w.writerow([x.isoformat(), round((p1545[x] / o1[x] - 1) * 100, 4),
                        round((c1[x] / o1[x] - 1) * 100, 4),
                        round(S[x]["on"] * 100, 4)])
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()
