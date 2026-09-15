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

try:
    from universe import group_of
except Exception:                                             # noqa: BLE001
    def group_of(_):
        return "?"

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
PRIMARY = "SOXL"


def overnights(path):
    """{date: close -> next open return}. The only return this strategy takes."""
    d, o, c = load(path)
    return {d[i]: o[d[i + 1]] / c[d[i]] - 1 for i in range(len(d) - 1)}


def main():
    out_dir = os.path.join(ROOT, "retreat_lab/out")
    files = sorted(glob.glob(os.path.join(out_dir, "*_daily_ibkr.csv")))
    files += sorted(glob.glob(os.path.join(out_dir, "universe", "*.csv")))
    series = {}
    for f in files:
        sym = os.path.basename(f).replace("_daily_ibkr.csv", "").replace(".csv", "")
        if sym in series:
            continue                       # a hand-fetched file wins
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

    rows = []
    for sym, s in series.items():
        if sym == PRIMARY:
            continue
        common = [d for d in days if d in s]
        if len(common) < 200:
            continue
        drag = mean(s[d] for d in common)
        tl = [s[d] for d in common if d in decile]
        tail10 = mean(tl) if tl else 0.0
        # is the tail number distinguishable from this instrument's own noise?
        sd = stdev(tl) if len(tl) > 1 else 0.0
        t = tail10 / (sd / len(tl) ** 0.5) if sd else 0.0
        tail5 = mean(s[d] for d in common if d in worst5) if worst5 else 0.0
        dn = [d for d in common if d in down]
        hit = sum(1 for d in dn if s[d] > 0) / len(dn) * 100 if dn else 0.0
        c = corr([base[d] for d in common], [s[d] for d in common])
        rows.append(dict(sym=sym, n=len(common), corr=c, drag=drag,
                         tail10=tail10, t=t, tail5=tail5, hit=hit,
                         grp=group_of(sym)))

    rows.sort(key=lambda r: -r["tail10"])

    def show(rs, title):
        print(f"\n  {title}")
        print(f"  {'symbol':<8}{'class':<17}{'corr':>7}{'drag':>9}"
              f"{'tail-10%':>10}{'t':>7}{'tail-5%':>9}{'hit':>6}")
        for r in rs:
            print(f"  {r['sym']:<8}{r['grp']:<17}{r['corr']:>7.2f}"
                  f"{r['drag']*100:>8.3f}%{r['tail10']*100:>9.3f}%{r['t']:>7.1f}"
                  f"{r['tail5']*100:>8.3f}%{r['hit']:>5.0f}%")

    # THE question: pays in the tail AND does not bleed to hold.
    survivors = [r for r in rows if r["tail10"] > 0 and r["drag"] >= -0.0002]
    payers = [r for r in rows if r["tail10"] > 0 and r["drag"] < -0.0002]

    print(f"\n  screened {len(rows)} instruments with >=200 overlapping nights")
    if survivors:
        show(survivors, "PAYS IN THE TAIL AND IS NOT A DRAG — the only bucket "
                        "that matters")
    else:
        print(f"\n  PAYS IN THE TAIL AND IS NOT A DRAG:  nothing. Not one of "
              f"{len(rows)}.")
    show(payers[:15], f"pays in the tail, but bleeds to hold ({len(payers)} total)")
    show(rows[len(survivors)+len(payers):][:10],
         "best of the rest — every one of these FALLS with SOXL in the tail")
    show(rows[-8:], "worst — these are what the strategy is already long")

    by_grp = {}
    for r in rows:
        by_grp.setdefault(r["grp"], []).append(r["tail10"])
    print(f"\n  BY ASSET CLASS — mean tail-decile return, best first")
    for g, v in sorted(by_grp.items(), key=lambda kv: -mean(kv[1])):
        print(f"    {g:<18}{mean(v)*100:>8.3f}%   ({len(v)} names)")

    print(f"\n  read `tail-10%` first: it is the only column a hedge has to win.")
    print(f"  `drag` is what winning it costs on the other 90% of nights.")
    print(f"  `t` is that tail mean against the instrument's own noise in those "
          f"{len(decile)} nights.")

    path = os.path.join(out_dir, "tail_screen.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["symbol", "asset_class", "nights", "corr", "drag_pct",
                    "tail10_pct", "tail10_t", "tail5_pct", "hit_rate_pct"])
        for r in rows:
            w.writerow([r["sym"], r["grp"], r["n"], round(r["corr"], 4),
                        round(r["drag"] * 100, 4), round(r["tail10"] * 100, 4),
                        round(r["t"], 2), round(r["tail5"] * 100, 4),
                        round(r["hit"], 1)])
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
