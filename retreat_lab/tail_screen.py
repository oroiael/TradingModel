"""Screen candidates for what a hedge actually has to do: pay in SOXL's tail.

**Negative correlation is the wrong thing to search for, and `xlu_sleeve.py` is
the proof.** XLU's unconditional correlation to SOXL overnight is +0.27, which
sounds like "mildly unhelpful". What actually killed it is that on SOXL's worst
5% of nights XLU averaged -0.344% and rose on 6 of 29. A correlation is an
average over a cloud of points; the drawdown lives in one corner of it.

There is also a structural reason a pure correlation screen cannot succeed here.
`mechanism.py` established that SOXL's overnight edge IS levered semiconductor
beta — SOXL +0.291%/night against SOXS -0.266%/night, summing to +0.024%. SOXS
is the perfect negative-correlation instrument, rho ~ -1 by construction, and it
loses money. In a one-factor world hedge quality and return drag are the SAME
NUMBER, so "most negatively correlated" just returns the most expensive short.

What is NOT ruled out by that argument is convexity: an instrument flat or
mildly positive on ordinary nights that pays specifically in a semis gap. That
is a different statistic and it is what this ranks on:

    tail     mean overnight return on SOXL's worst-decile nights  (want > 0)
    drag     unconditional mean overnight return                  (want >= 0)
    hit      share of SOXL DOWN nights the candidate rose          (want > 50%)

A candidate is only interesting if `tail` is positive AND `drag` is not badly
negative. Ranking on `tail` alone finds inverse ETFs, which is the trap.

Usage:  python3 retreat_lab/tail_screen.py [start_year]
"""
import csv, datetime as dt, glob, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
from coverage import load, corr

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
PRIMARY = "SOXL"


def overnights(path):
    """{date: close -> next open return}. The only return this strategy takes."""
    d, o, c = load(path)
    return {d[i]: o[d[i + 1]] / c[d[i]] - 1 for i in range(len(d) - 1)}


def main():
    out_dir = os.path.join(ROOT, "retreat_lab/out")
    files = sorted(glob.glob(os.path.join(out_dir, "*_daily_ibkr.csv")))
    series = {}
    for f in files:
        sym = os.path.basename(f).replace("_daily_ibkr.csv", "")
        try:
            series[sym] = overnights(f)
        except Exception as exc:                              # noqa: BLE001
            print(f"  skipped {sym}: {exc}")

    if PRIMARY not in series:
        print(f"no {PRIMARY} series; nothing to screen against")
        return
    base = series[PRIMARY]
    days = sorted(d for d in base if d.year >= START)
    ranked = sorted(days, key=lambda d: base[d])
    decile = set(ranked[:max(len(ranked) // 10, 1)])
    worst5 = set(ranked[:max(len(ranked) // 20, 1)])
    down = {d for d in days if base[d] < 0}

    print(f"TAIL SCREEN vs {PRIMARY} overnight   {days[0]} → {days[-1]}   "
          f"{len(days)} nights")
    print(f"worst decile = {len(decile)} nights, mean "
          f"{mean(base[d] for d in decile)*100:.2f}%   "
          f"down nights = {len(down)}\n")

    print(f"  {'symbol':<8}{'n':>5}{'corr':>8}{'drag':>9}{'tail-10%':>10}"
          f"{'tail-5%':>9}{'hit':>7}   verdict")
    rows = []
    for sym, s in series.items():
        if sym == PRIMARY:
            continue
        common = [d for d in days if d in s]
        if len(common) < 200:
            continue
        drag = mean(s[d] for d in common)
        tail10 = mean(s[d] for d in common if d in decile) if decile else 0.0
        tail5 = mean(s[d] for d in common if d in worst5) if worst5 else 0.0
        dn = [d for d in common if d in down]
        hit = sum(1 for d in dn if s[d] > 0) / len(dn) * 100 if dn else 0.0
        c = corr([base[d] for d in common], [s[d] for d in common])
        rows.append((tail10, sym, len(common), c, drag, tail5, hit))

    for tail10, sym, n, c, drag, tail5, hit in sorted(rows, reverse=True):
        if tail10 > 0 and drag >= -0.0002:
            v = "PAYS IN THE TAIL AND IS NOT A DRAG"
        elif tail10 > 0:
            v = f"pays in the tail, costs {drag*100:.3f}%/night to hold"
        elif drag > 0:
            v = "positive drift, but falls with SOXL — leverage, not a hedge"
        else:
            v = "loses both ways"
        print(f"  {sym:<8}{n:>5}{c:>8.2f}{drag*100:>8.3f}%{tail10*100:>9.3f}%"
              f"{tail5*100:>8.3f}%{hit:>6.0f}%   {v}")

    print(f"\n  read `tail-10%` first: it is the only column a hedge has to win.")
    print(f"  `drag` is what winning it costs you on the other 90% of nights.")

    path = os.path.join(out_dir, "tail_screen.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["symbol", "nights", "corr", "drag_pct", "tail10_pct",
                    "tail5_pct", "hit_rate_pct"])
        for tail10, sym, n, c, drag, tail5, hit in sorted(rows, reverse=True):
            w.writerow([sym, n, round(c, 4), round(drag * 100, 4),
                        round(tail10 * 100, 4), round(tail5 * 100, 4),
                        round(hit, 1)])
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
