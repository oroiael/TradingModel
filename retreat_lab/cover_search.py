"""Search for a better cover leg, with a control group that says what luck looks like.

## Why not random, and why random anyway

Random selection is the WRONG WAY TO SEARCH and the RIGHT WAY TO CALIBRATE, and
running it for the second reason is what makes the first one safe.

Searching 235 candidates over ~190 benched nights, the best one WILL look good.
That is arithmetic, not discovery: with 235 draws from a null distribution the
maximum is far out in the tail. The question a search cannot answer about itself
is "how good would the best of 235 look if none of them had any edge at all?"

So this runs two passes:

  DESIGNED   candidates ranked by a mechanism stated in advance (below)
  CONTROL    `n` candidates drawn at random with a fixed seed, ranked the same way

The control's best score is the bar. A designed candidate that does not clear
the best of a random draw has found nothing a coin could not have found. This is
a cheap empirical stand-in for a Bonferroni correction, and unlike Bonferroni it
makes no assumption about the shape of the null.

## The designed criterion, and why it beats "correlate it with NVDA"

A cover leg has one job: EARN ON THE NIGHTS SOXL IS BENCHED. Two properties
decide that, and neither is return correlation to semiconductors.

1. AVAILABILITY. The cover must pass its own volatility filter on the nights
   SOXL fails its one. That is a property of the two RV SERIES, not the two
   return series, so the criterion is corr(candidate RV20, SOXL RV20) — LOW or
   negative. An instrument whose vol rises exactly when SOXL's rises is benched
   on precisely the nights it is needed. Return correlation does not measure
   this and can be near zero while RV correlation is near one, because
   volatility is common across risk assets even when direction is not.

2. DRIFT. Positive mean overnight return on those nights, after costs. Without
   it, availability just means being available to lose.

Correlation to NVDA is close to useless here for a third reason: NVDA is roughly
a fifth of the semiconductor index, so corr(candidate, NVDA) is nearly
corr(candidate, SOXL) for anything in or near the sector, and carries no
information the existing screen does not already have.

## What survives

Both passes are split in half. A candidate is reported as a finding only if it
beats the control bar AND holds up in both halves. Everything else is listed as
a curiosity.

Usage:  python3 retreat_lab/cover_search.py [n_random] [seed] [start_year]
"""
import csv, glob, math, os, random, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
_argv, sys.argv = sys.argv, sys.argv[:1]
from coverage import load, walk, corr                        # noqa: E402
sys.argv = _argv
try:
    from universe import group_of
except Exception:                                            # noqa: BLE001
    def group_of(_):
        return "?"

N_RANDOM = int(sys.argv[1]) if len(sys.argv) > 1 else 20
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 20260917
START = int(sys.argv[3]) if len(sys.argv) > 3 else 2023
COST_BP = 1.0


def series(path, lag=1):
    d, o, c = load(path)
    dr = [c[d[i]] / c[d[i - 1]] - 1 for i in range(1, len(d))]
    return {d[i]: dict(rv=stdev(dr[i - 20 - lag:i - lag]) * (252 ** 0.5) * 100,
                       on=o[d[i + 1]] / c[d[i]] - 1)
            for i in range(21, len(d) - 1)}


def score(C, benched, half=None):
    """Mean net overnight return on the benched nights the candidate can trade."""
    cd = sorted(C)
    ce = walk({x: C[x]["rv"] for x in cd}, cd, 60)
    nights = [x for x in benched if x in C and ce.get(x)]
    if half is not None:
        cut = benched[len(benched) // 2]
        nights = [x for x in nights if (x < cut) == (half == 0)]
    if len(nights) < 25:
        return None
    v = [C[x]["on"] - 2 * COST_BP / 1e4 for x in nights]
    return dict(n=len(nights), mean=mean(v) * 100,
                win=sum(1 for x in v if x > 0) / len(v) * 100,
                cover=len(nights) / max(len(benched), 1) * 100)


def main():
    out_dir = os.path.join(ROOT, "retreat_lab/out")
    files = {}
    for f in sorted(glob.glob(os.path.join(out_dir, "*_daily_ibkr.csv"))) + \
             sorted(glob.glob(os.path.join(out_dir, "universe", "*.csv"))):
        sym = os.path.basename(f).replace("_daily_ibkr.csv", "").replace(".csv", "")
        files.setdefault(sym, f)

    S = series(files["SOXL"])
    sd = sorted(S)
    sel = walk({x: S[x]["rv"] for x in sd}, sd, 60)
    days = [x for x in sd if x.year >= START]
    benched = [x for x in days if not sel[x]]
    print(f"COVER SEARCH   {len(days)} sessions from {START}, "
          f"{len(benched)} with SOXL benched")
    print(f"{len(files)} instruments on disk   control n={N_RANDOM} seed={SEED}\n")

    cand = {}
    for sym, f in files.items():
        if sym == "SOXL":
            continue
        try:
            C = series(f)
        except Exception:                                    # noqa: BLE001
            continue
        common = [x for x in days if x in C]
        if len(common) < 300:
            continue
        cand[sym] = dict(
            S=C,
            rvcorr=corr([S[x]["rv"] for x in common], [C[x]["rv"] for x in common]))

    # ---- CONTROL: what does the best of n random draws look like? -----------
    rng = random.Random(SEED)
    picks = rng.sample(sorted(cand), min(N_RANDOM, len(cand)))
    print(f"CONTROL — {len(picks)} drawn at random, seed {SEED}, reproducible")
    print(f"  {', '.join(picks)}\n")
    print(f"  {'sym':<7}{'class':<17}{'rv corr':>9}{'nights':>8}{'cover':>8}"
          f"{'mean':>9}{'win':>8}")
    ctrl = []
    for sym in picks:
        r = score(cand[sym]["S"], benched)
        if not r:
            continue
        ctrl.append(r["mean"])
        print(f"  {sym:<7}{group_of(sym):<17}{cand[sym]['rvcorr']:>9.2f}"
              f"{r['n']:>8}{r['cover']:>7.0f}%{r['mean']:>8.3f}%{r['win']:>7.1f}%")
    bar = max(ctrl) if ctrl else 0.0
    print(f"\n  BAR = best of {len(ctrl)} random candidates = {bar:+.3f}% per night.")
    print(f"  Anything designed must clear this to have found something.\n")

    # ---- DESIGNED: rank by the stated mechanism ----------------------------
    ranked = sorted(cand, key=lambda s: cand[s]["rvcorr"])
    print(f"DESIGNED — lowest RV-correlation to SOXL first (availability), "
          f"then drift")
    print(f"  {'sym':<7}{'class':<17}{'rv corr':>9}{'nights':>8}{'cover':>8}"
          f"{'mean':>9}{'win':>8}{'h1':>8}{'h2':>8}  verdict")
    found = []
    for sym in ranked[:25]:
        r = score(cand[sym]["S"], benched)
        if not r:
            continue
        h1 = score(cand[sym]["S"], benched, half=0)
        h2 = score(cand[sym]["S"], benched, half=1)
        ok = (r["mean"] > bar and h1 and h2 and h1["mean"] > 0 and h2["mean"] > 0)
        if ok:
            found.append(sym)
        print(f"  {sym:<7}{group_of(sym):<17}{cand[sym]['rvcorr']:>9.2f}"
              f"{r['n']:>8}{r['cover']:>7.0f}%{r['mean']:>8.3f}%{r['win']:>7.1f}%"
              f"{(h1['mean'] if h1 else float('nan')):>7.3f}%"
              f"{(h2['mean'] if h2 else float('nan')):>7.3f}%"
              f"  {'CLEARS BAR, BOTH HALVES' if ok else ''}")

    print()
    if found:
        print(f"  survived: {', '.join(found)}")
    else:
        print(f"  nothing cleared the random bar in both halves.")

    p = os.path.join(out_dir, "cover_search.csv")
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["symbol", "class", "rv_corr_to_soxl", "nights", "cover_pct",
                    "mean_pct", "win_pct", "in_control_group"])
        for sym in ranked:
            r = score(cand[sym]["S"], benched)
            if not r:
                continue
            w.writerow([sym, group_of(sym), round(cand[sym]["rvcorr"], 4),
                        r["n"], round(r["cover"], 1), round(r["mean"], 4),
                        round(r["win"], 1), sym in picks])
    print(f"  wrote {p}")


if __name__ == "__main__":
    main()
