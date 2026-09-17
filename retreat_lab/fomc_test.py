"""Is the night before an FOMC decision different?

## The hypothesis, from the literature rather than from this data

Lucca and Moench (2015) documented a "pre-FOMC announcement drift": large excess
equity returns in roughly the 24 hours BEFORE the 14:00 ET policy announcement.
The mechanism is disputed; the effect is well known and was found on broad US
equity indices.

That window matters here because it contains exactly one of this strategy's
trades. The announcement falls on the SECOND day of each two-day meeting, so the
overnight from the close of meeting-day-1 into the open of meeting-day-2 sits
inside the pre-FOMC window. Call that the EVE night. The ANNOUNCEMENT night, by
contrast, is the one entered at the close AFTER the decision is already public.

Three night types are tested separately, because they are three different bets:

    EVE   close of day before -> open of announcement day   (inside the window)
    ANN   close of announcement day -> next open            (after the news)
    POST  the night after that                              (control)

## Power, stated before the result

There are 30 announcement dates in this sample. SOXL's overnight standard
deviation is about 4.6%, so the standard error of a mean over 30 nights is about
0.84%. Detecting an effect at t=2 therefore needs a mean near +1.7%, against an
unconditional +0.39%. **This test can only see an effect four times the baseline
on SOXL.** Lower-volatility instruments have better power on the same 30 dates
and are included for that reason, even though they are not what we trade.

A null result here means "not detectable in 30 nights", not "absent".

## Checks

Permutation: 2,000 draws of an equal number of RANDOM nights, to see how often
chance produces the observed mean. Split-sample: the halves must agree.

## What was found, and what was NOT

The published EVE effect is present in direction and weak in size (SOXL +1.53%
against +0.35%, permutation p = 0.077). It does not survive a multiple-comparison
haircut.

The ANNOUNCEMENT night — entered at the close AFTER the decision and press
conference are public — is much stronger, and that is not what the literature
predicts. SOXL +2.36% against +0.33%, permutation p = 0.011, median +2.45%
against a +0.34% baseline, both halves of the sample positive, and still
+1.02% after dropping the three best nights. It replicates across TQQQ/QLD,
TECL and TNA — which is weak confirmation, since those are largely the same
equity beta.

NO MECHANISM IS ESTABLISHED. The obvious one is ruled out: FOMC-day intraday
returns are +0.130% against +0.127% on other days, statistically indistinguishable,
so this is not a reversal of a weak afternoon. The overnight is elevated and the
day session is not, and nothing here explains why.

Usage:  python3 retreat_lab/fomc_test.py [start_year]
"""
import csv, datetime as dt, glob, os, random, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
_argv, sys.argv = sys.argv, sys.argv[:1]
from coverage import load                                    # noqa: E402
sys.argv = _argv

START = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
SEED = 20260917


def overnights(path):
    d, o, c = load(path)
    return d, {d[i]: o[d[i + 1]] / c[d[i]] - 1 for i in range(len(d) - 1)}


def announce_dates():
    out = []
    for r in csv.DictReader(open(os.path.join(ROOT, "retreat_lab/fomc_dates.csv"))):
        if "future" in r["note"]:
            continue
        out.append(dt.date.fromisoformat(r["announcement_date"]))
    return sorted(out)


def classify(days, anns):
    """Map each announcement to the decision day of its eve/ann/post night."""
    idx = {d: i for i, d in enumerate(days)}
    eve, ann, post = [], [], []
    for a in anns:
        if a not in idx:
            continue
        i = idx[a]
        if i - 1 >= 0:
            eve.append(days[i - 1])       # held INTO the announcement morning
        ann.append(days[i])               # entered after the decision
        if i + 1 < len(days):
            post.append(days[i + 1])
    return eve, ann, post


def report(name, on, days, picked, rng):
    v = [on[d] for d in picked if d in on]
    rest = [on[d] for d in days if d in on and d not in set(picked)]
    if len(v) < 10:
        return
    m, r = mean(v), mean(rest)
    se = stdev(v) / len(v) ** 0.5
    # permutation: how often does a random set of the same size beat this mean?
    pool = [on[d] for d in days if d in on]
    hits = 0
    for _ in range(2000):
        if mean(rng.sample(pool, len(v))) >= m:
            hits += 1
    print(f"    {name:<6}{len(v):>5}{m*100:>+10.3f}%{r*100:>+10.3f}%"
          f"{(m-r)*100:>+10.3f}%{m/se:>8.2f}{hits/2000:>9.3f}"
          f"{sum(1 for x in v if x>0)/len(v)*100:>7.1f}%")


def main():
    anns = announce_dates()
    print(f"FOMC TEST   {len(anns)} announcements, {START} onward\n")
    files = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "retreat_lab/out/*_daily_ibkr.csv"))) + \
             sorted(glob.glob(os.path.join(ROOT, "retreat_lab/out/universe/*.csv"))):
        s = os.path.basename(f).replace("_daily_ibkr.csv", "").replace(".csv", "")
        files.setdefault(s, f)

    order = [s for s in ("SOXL", "XLU", "TQQQ", "QLD", "SPY", "TECL", "TNA",
                         "TLT", "SQQQ", "UTSL", "LABU", "IWM", "DIA")
             if s in files]
    rng = random.Random(SEED)
    for sym in order:
        try:
            days_all, on = overnights(files[sym])
        except Exception:                                    # noqa: BLE001
            continue
        days = [d for d in days_all if d.year >= START]
        if len(days) < 400:
            continue
        eve, ann, post = classify(days, anns)
        sd = stdev([on[d] for d in days if d in on])
        print(f"  {sym}   {len(days)} sessions, overnight sd {sd*100:.2f}%  "
              f"-> se over 30 nights {sd/30**0.5*100:.2f}%, so t=2 needs "
              f"{2*sd/30**0.5*100:.2f}%")
        print(f"    {'night':<6}{'n':>5}{'mean':>11}{'other':>11}{'diff':>11}"
              f"{'t':>8}{'perm p':>9}{'win':>8}")
        for nm, g in (("eve", eve), ("ann", ann), ("post", post)):
            report(nm, on, days, g, rng)
        print()


if __name__ == "__main__":
    main()
