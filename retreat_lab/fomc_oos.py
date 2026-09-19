"""Score the pre-registered FOMC test. Written before any of its data exists.

`PREREGISTRATION.md` locks the claim, the endpoint, the stopping rule and the
decision. This file locks the ARITHMETIC, and it is committed on the same day
for the same reason: a computation chosen after seeing the numbers is not a
test, and "we'd have used the median" is the easiest thing in the world to say
afterwards.

Nothing here may be changed once the first event is scored. If a genuine defect
is found, fix it in a new file, say so, and report both.

Run it any time. It reports progress, and only at n=9 does it decide.

Usage:  python3 retreat_lab/fomc_oos.py
"""
import csv, datetime as dt, math, os, sys
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT
_argv, sys.argv = sys.argv, sys.argv[:1]
from coverage import load                                    # noqa: E402
sys.argv = _argv

#: Locked 2026-09-17. Primary decides; the rest are recorded only.
PRIMARY = "QLD"
SECONDARY = ["SOXL", "TQQQ", "TECL", "TNA", "XLU"]
N_TARGET = 9
T_BAR = 2.0
LOCKED_ON = "2026-09-17"
OOS_FROM = dt.date(2026, 9, 17)


def overnights(sym):
    for rel in (f"retreat_lab/out/{sym}_daily_ibkr.csv",
                f"retreat_lab/out/universe/{sym}.csv"):
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            d, o, c = load(rel)
            return d, {d[i]: o[d[i + 1]] / c[d[i]] - 1 for i in range(len(d) - 1)}
    return None, None


def events():
    out = []
    for r in csv.DictReader(open(os.path.join(ROOT,
                                              "retreat_lab/fomc_dates.csv"))):
        a = dt.date.fromisoformat(r["announcement_date"])
        if a >= OOS_FROM:
            out.append((a, r["meeting"]))
    return sorted(out)[:N_TARGET]


def main():
    ev = events()
    print(f"PRE-REGISTERED FOMC TEST   locked {LOCKED_ON}")
    print(f"primary endpoint {PRIMARY}, decision at n={N_TARGET}, "
          f"t bar {T_BAR}\n")

    days, on = overnights(PRIMARY)
    if on is None:
        print(f"  no daily file for {PRIMARY}. Fetch it:")
        print(f"    python retreat_lab/fetch_universe.py --only {PRIMARY} --force")
        return 1

    rows, scored = [], []
    for a, meeting in ev:
        if a in on:
            v = on[a]
            scored.append(v)
            note = ""
        else:
            v = None
            note = "not yet observable" if a > max(days) else "MISSING from data"
        rows.append(dict(date=a, meeting=meeting, primary=v, note=note))

    print(f"  {'#':<3}{'date':<13}{'meeting':<22}{PRIMARY:>10}  note")
    for i, r in enumerate(rows, 1):
        val = f"{r['primary']*100:+.3f}%" if r["primary"] is not None else "—"
        print(f"  {i:<3}{r['date'].isoformat():<13}{r['meeting']:<22}{val:>10}"
              f"  {r['note']}")

    n = len(scored)
    print(f"\n  {n} of {N_TARGET} events scored")
    if n == 0:
        print("  nothing to report yet. Re-run after 2026-10-28.")
        return 0

    # contemporaneous baseline: every non-announcement night since the lock
    anns = {a for a, _ in ev}
    base = [on[d] for d in days if d >= OOS_FROM and d in on and d not in anns]
    m = mean(scored)
    print(f"  {PRIMARY} announcement nights: mean {m*100:+.3f}%, "
          f"median {sorted(scored)[n//2]*100:+.3f}%, "
          f"{sum(1 for v in scored if v > 0)}/{n} positive")
    if base:
        b = mean(base)
        print(f"  contemporaneous baseline ({len(base)} nights): {b*100:+.3f}%")
        print(f"  excess {(m-b)*100:+.3f}%   "
              f"(in-sample prediction was +1.081%)")
    else:
        b = 0.0

    for sym in SECONDARY:
        _, o2 = overnights(sym)
        if not o2:
            continue
        v = [o2[a] for a, _ in ev if a in o2]
        if v:
            print(f"    secondary {sym:<6} n={len(v)} mean {mean(v)*100:+.3f}%")

    out = os.path.join(ROOT, "retreat_lab/out/fomc_oos.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["n", "date", "meeting", f"{PRIMARY}_overnight_pct", "note"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["date"].isoformat(), r["meeting"],
                        "" if r["primary"] is None else round(r["primary"] * 100, 4),
                        r["note"]])

    print()
    if n < N_TARGET:
        print(f"  NO DECISION. The stopping rule is n={N_TARGET} and this is "
              f"n={n}.")
        print(f"  Interim numbers are not evidence and must not change anything.")
        return 0

    se = stdev(scored) / math.sqrt(n)
    t = (m - b) / se if se else 0.0
    print(f"  DECISION POINT   t = {t:+.2f} against a bar of {T_BAR}")
    if m - b <= 0:
        print(f"  ABANDONED. Mean excess {(m-b)*100:+.3f}% is not positive.")
        print(f"  Per the pre-registration: do not re-test, do not re-slice.")
    elif t >= T_BAR:
        print(f"  SURVIVES. This is the first point at which acting on it is")
        print(f"  even a conversation. It is not an instruction to act.")
    else:
        print(f"  UNRESOLVED. Extend to n=18 under the same rule, ONCE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
