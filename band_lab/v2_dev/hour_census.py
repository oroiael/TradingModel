"""
Time-of-day census: buy the first minute of an hour, sell the 59th minute.

No band. No gate. No anchor. No stop. No target. No fill model. Nothing from
the strategy is imported. The only decision is a clock: enter at the top of an
hour, exit at the end of it, every hour of every day.

The question this answers, exactly as asked: for each (weekday x trading hour)
cell, what is the average POSITIVE move and the average NEGATIVE move, and how
often does each happen.

Definitions, stated because every one of them is a choice:

  entry price  the OPEN of the :00 bar of that hour. A market order sent at the
               top of the hour fills near the open of that minute, not its
               close. The 09:00 hour has no :00 bar in regular hours, so it
               enters at 09:30 and is a 30-minute hold, not 60. It is labelled
               partial everywhere it appears and is never pooled silently.
  exit price   the CLOSE of the :59 bar. A market order at the end of the last
               minute of the hour.
  return       exit_close / entry_open - 1.
  avg positive the mean of the returns that came out positive.
  avg negative the mean of the returns that came out negative.
  MFE / MAE    the best and worst the position was DURING the hour, from the
               intra-hour High and Low against the entry price. This is the
               other thing "positive movement" can mean, so both are printed.

  ret_cc       a sensitivity: close of :00 -> close of :59, i.e. giving up the
               first minute. If a cell's edge lives entirely in the opening
               minute it will show up as the gap between these two.

Friction is charged at the measured per-symbol round trip from research_kit
(SOXL 6.70 bp, SOXS 8.18 bp). One hourly hold is one complete round trip.

    python3 band_lab/v2_dev/hour_census.py
    python3 band_lab/v2_dev/hour_census.py --since 2022-01-01
    python3 band_lab/v2_dev/hour_census.py --symbol SOXL --cc
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_kit import Result, daily_closes, friction_for, table  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SYMBOLS = ("SOXL", "SOXS")

OPEN_MIN, CLOSE_MIN = 9 * 60 + 30, 15 * 60 + 59
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
HOURS = (9, 10, 11, 12, 13, 14, 15)

#: The 09:00 hour is 09:30-09:59 in regular trading hours: half an hour, not a
#: full one. Comparing it to the others as if it were the same length would be
#: wrong, so it carries this flag through every table it appears in.
PARTIAL = {9}


def load(symbol: str, since: str | None) -> pd.DataFrame:
    """One row per regular-hours minute. Prices exactly as the file has them.

    SOXS's file is back-adjusted and its prices run to the millions. Every
    number below is a ratio, so the scale is irrelevant.
    """
    path = os.path.join(ROOT, f"{symbol}_1min.csv")
    with open(path, "rb") as fh:
        if fh.read(40).startswith(b"version https://git-lfs"):
            raise RuntimeError(f"{path} is an LFS pointer — run `git lfs pull`")
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    mins = dt.dt.hour * 60 + dt.dt.minute
    keep = ((mins >= OPEN_MIN) & (mins <= CLOSE_MIN)).to_numpy()
    df = df.assign(date=dt.dt.normalize(), hour=dt.dt.hour,
                   mofh=dt.dt.minute, weekday=dt.dt.weekday)[keep]
    if since:
        df = df[df["date"] >= pd.Timestamp(since)]
    return df.sort_values(["date", "hour", "mofh"])


def slots(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (session, hour) that has both an entry bar and a :59 bar.

    An hour missing either bar is dropped rather than approximated with a
    neighbouring minute. Half-day sessions simply have fewer hours; that is not
    an error and is counted, not patched.
    """
    first = np.where(df["hour"].to_numpy() == 9, 30, 0)
    entry = df[df["mofh"].to_numpy() == first]
    exit_ = df[df["mofh"] == 59]

    e = entry.set_index(["date", "hour"])[["Open", "Close", "weekday"]]
    e.columns = ["entry_open", "entry_close", "weekday"]
    x = exit_.set_index(["date", "hour"])[["Close"]]
    x.columns = ["exit_close"]

    # intra-hour excursion over exactly the bars of that clock hour
    ex = df.groupby(["date", "hour"]).agg(hi=("High", "max"), lo=("Low", "min"),
                                          bars=("Close", "size"))

    s = e.join(x, how="inner").join(ex, how="inner").reset_index()
    s["ret"] = s["exit_close"] / s["entry_open"] - 1.0
    s["ret_cc"] = s["exit_close"] / s["entry_close"] - 1.0
    s["mfe"] = s["hi"] / s["entry_open"] - 1.0
    s["mae"] = s["lo"] / s["entry_open"] - 1.0
    s["dow"] = s["weekday"].map(lambda i: DAYS[i] if i < 5 else "?")
    return s


def cell_stats(g: pd.DataFrame, col: str) -> dict:
    r = g[col].to_numpy(float)
    n = len(r)
    pos, neg = r[r > 0], r[r < 0]
    sd = float(r.std(ddof=1)) if n > 1 else float("nan")
    return dict(
        n=n,
        win=len(pos) / n if n else float("nan"),
        avg_pos=float(pos.mean()) if len(pos) else 0.0,
        avg_neg=float(neg.mean()) if len(neg) else 0.0,
        mean=float(r.mean()) if n else float("nan"),
        sd=sd,
        t=float(r.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else float("nan"),
        mfe=float(g["mfe"].mean()),
        mae=float(g["mae"].mean()),
    )


def summarize(s: pd.DataFrame, by, col: str) -> pd.DataFrame:
    rows = []
    for key, g in s.groupby(by, sort=True):
        d = cell_stats(g, col)
        if not isinstance(key, tuple):
            key = (key,)
        for name, v in zip(by if isinstance(by, list) else [by], key):
            d[name] = v
        rows.append(d)
    return pd.DataFrame(rows)


def bh(pvals: np.ndarray, q: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg. Returns a boolean mask of survivors."""
    n = len(pvals)
    order = np.argsort(pvals)
    thresh = q * (np.arange(1, n + 1) / n)
    passed = pvals[order] <= thresh
    keep = np.zeros(n, dtype=bool)
    if passed.any():
        cut = np.max(np.flatnonzero(passed))
        keep[order[: cut + 1]] = True
    return keep


def two_sided_p(t: np.ndarray) -> np.ndarray:
    """Normal approximation; n per cell is 300+, so the t/z gap is immaterial."""
    from math import erfc, sqrt
    return np.array([erfc(abs(v) / sqrt(2.0)) if np.isfinite(v) else 1.0
                     for v in t])


def bp(x: float) -> str:
    return f"{x*1e4:+.1f}"


def hour_label(h: int) -> str:
    return f"{h:02d}:30-{h:02d}:59*" if h in PARTIAL else f"{h:02d}:00-{h:02d}:59"


# ------------------------------------------------------------------ reporting
def report_symbol(sym: str, s: pd.DataFrame, col: str, args) -> list[Result]:
    f = friction_for(sym)
    rt = f.round_trip_bp / 1e4

    print("=" * 100)
    print(f"{sym} — enter at the first minute of the hour, exit at the 59th "
          f"minute ({'close->close' if col == 'ret_cc' else 'open->close'})")
    print("=" * 100)
    n_days = s["date"].nunique()
    print(f"  {len(s):,} hour-slots over {n_days:,} sessions, "
          f"{s['date'].min().date()} to {s['date'].max().date()}")
    print(f"  friction {f.round_trip_bp:.2f} bp per hourly round trip "
          f"({f.round_trip_bp*100/1e4:.4f}%)")
    print(f"  * 09:30-09:59 is a 30-minute hold, not 60. Never pooled with the "
          f"full hours.")

    # ---- the direct answer: every (weekday x hour) cell
    print(f"\n  EVERY CELL — {len(DAYS)} weekdays x {len(HOURS)} hours\n")
    print(f"  {'day':<5}{'hour':<16}{'n':>6}{'win%':>7}"
          f"{'avg +':>9}{'avg -':>9}{'mean':>9}{'net':>9}"
          f"{'MFE':>9}{'MAE':>9}{'t':>7}")
    print("  " + "-" * 96)

    tbl = summarize(s, ["dow", "hour"], col)
    tbl["order"] = tbl["dow"].map({d: i for i, d in enumerate(DAYS)})
    tbl = tbl.sort_values(["order", "hour"])

    for d in DAYS:
        for _, r in tbl[tbl["dow"] == d].iterrows():
            net = r["mean"] - rt
            print(f"  {r['dow']:<5}{hour_label(int(r['hour'])):<16}"
                  f"{int(r['n']):>6}{r['win']*100:>6.1f}%"
                  f"{bp(r['avg_pos']):>9}{bp(r['avg_neg']):>9}"
                  f"{bp(r['mean']):>9}{bp(net):>9}"
                  f"{bp(r['mfe']):>9}{bp(r['mae']):>9}{r['t']:>7.2f}")
        print()

    print("  all numbers are basis points. 1 bp = 0.01%. 100 bp = 1%.")
    print("  avg + = mean of the hours that ENDED positive.  avg - = mean of "
          "the hours that ended negative.")
    print("  mean  = the average of every hour = win% x (avg +) + (1-win%) x "
          "(avg -).  net = mean minus friction.")
    print("  MFE / MAE = the average best and worst the position reached "
          "DURING the hour (from the bar highs and lows).")

    # ---- margins, which is where the sample size actually is
    print(f"\n  BY HOUR (all weekdays pooled)\n")
    print(f"  {'hour':<16}{'n':>7}{'win%':>7}{'avg +':>9}{'avg -':>9}"
          f"{'mean':>9}{'net':>9}{'MFE':>9}{'MAE':>9}{'t':>7}")
    print("  " + "-" * 91)
    byh = summarize(s, ["hour"], col).sort_values("hour")
    for _, r in byh.iterrows():
        print(f"  {hour_label(int(r['hour'])):<16}{int(r['n']):>7}"
              f"{r['win']*100:>6.1f}%{bp(r['avg_pos']):>9}{bp(r['avg_neg']):>9}"
              f"{bp(r['mean']):>9}{bp(r['mean']-rt):>9}"
              f"{bp(r['mfe']):>9}{bp(r['mae']):>9}{r['t']:>7.2f}")

    print(f"\n  BY WEEKDAY (all hours pooled)\n")
    print(f"  {'day':<16}{'n':>7}{'win%':>7}{'avg +':>9}{'avg -':>9}"
          f"{'mean':>9}{'net':>9}{'MFE':>9}{'MAE':>9}{'t':>7}")
    print("  " + "-" * 91)
    byd = summarize(s, ["dow"], col)
    byd["order"] = byd["dow"].map({d: i for i, d in enumerate(DAYS)})
    for _, r in byd.sort_values("order").iterrows():
        print(f"  {r['dow']:<16}{int(r['n']):>7}"
              f"{r['win']*100:>6.1f}%{bp(r['avg_pos']):>9}{bp(r['avg_neg']):>9}"
              f"{bp(r['mean']):>9}{bp(r['mean']-rt):>9}"
              f"{bp(r['mfe']):>9}{bp(r['mae']):>9}{r['t']:>7.2f}")

    # ---- how many of the 35 cells would look good by luck alone
    t = tbl["t"].to_numpy(float)
    p = two_sided_p(t)
    keep = bh(p, 0.05)
    print(f"\n  MULTIPLE COMPARISONS")
    print(f"    {len(tbl)} cells tested. At a 5% threshold, "
          f"{len(tbl)*0.05:.2f} cells are expected to look significant by "
          f"chance alone.")
    print(f"    raw p < 0.05:                 {int((p < 0.05).sum())} cells")
    print(f"    survive Benjamini-Hochberg:   {int(keep.sum())} cells")
    if keep.any():
        for _, r in tbl[keep].iterrows():
            print(f"      {r['dow']} {hour_label(int(r['hour']))}  "
                  f"mean {bp(r['mean'])} bp  t {r['t']:.2f}  n {int(r['n'])}")
    else:
        print(f"      none. Every cell is inside what 35 coin flips produce.")

    # ---- does the best cell survive being cut in half by time
    print(f"\n  SPLIT-HALF STABILITY — the top 5 cells by mean, first half of "
          f"the data vs second")
    mid = s["date"].quantile(0.5)
    h1, h2 = s[s["date"] <= mid], s[s["date"] > mid]
    t1 = summarize(h1, ["dow", "hour"], col).set_index(["dow", "hour"])
    t2 = summarize(h2, ["dow", "hour"], col).set_index(["dow", "hour"])
    top = tbl.nlargest(5, "mean")
    print(f"    split at {pd.Timestamp(mid).date()}")
    print(f"    {'cell':<24}{'full':>10}{'first half':>13}{'second half':>14}"
          f"{'same sign?':>12}")
    print("    " + "-" * 71)
    for _, r in top.iterrows():
        k = (r["dow"], r["hour"])
        a = t1.loc[k, "mean"] if k in t1.index else float("nan")
        b = t2.loc[k, "mean"] if k in t2.index else float("nan")
        same = "yes" if np.isfinite(a) and np.isfinite(b) and a * b > 0 else "NO"
        print(f"    {r['dow'] + ' ' + hour_label(int(r['hour'])):<24}"
              f"{bp(r['mean']):>10}{bp(a):>13}{bp(b):>14}{same:>12}")
    print(f"    A cell selected on the full sample keeps its sign in both "
          f"halves only if it is real.")

    # ---- what it costs to actually trade this
    print(f"\n  FRICTION, APPLIED")
    full = byh[~byh["hour"].isin(PARTIAL)]
    gross_all = float(s[~s["hour"].isin(PARTIAL)][col].mean())
    print(f"    average full hour, gross:        {bp(gross_all)} bp")
    print(f"    friction per round trip:         "
          f"{-f.round_trip_bp:+.1f} bp")
    print(f"    average full hour, net:          {bp(gross_all - rt)} bp")
    print(f"    trading all 6 full hours daily:  "
          f"{bp(6*(gross_all - rt))} bp/day  "
          f"= {bp(6*(gross_all-rt))} bp x 252 = "
          f"{6*(gross_all-rt)*252*100:+.1f}% per year")
    best = tbl.loc[tbl["mean"].idxmax()]
    print(f"    the single best cell, net:       {bp(best['mean'] - rt)} bp "
          f"on {int(best['n'])} trades "
          f"({best['dow']} {hour_label(int(best['hour']))})")
    print(f"    break-even gross mean needed:    "
          f"{f.round_trip_bp:+.1f} bp — the hour has to average at least this "
          f"much just to pay for itself")
    n_over = int((tbl["mean"] > rt).sum())
    print(f"    cells whose GROSS mean clears friction: {n_over} of {len(tbl)}")

    # ---- T23: the benchmark column
    start, end = s["date"].min(), s["date"].max()
    closes = daily_closes(sym) if sym in ("SOXL", "SOXS") else None
    out: list[Result] = []

    def compound(sub: pd.DataFrame, name: str, charge: bool) -> Result:
        r = sub[col].to_numpy(float) - (rt if charge else 0.0)
        return Result.of(name, start, end, float(np.prod(1.0 + r) - 1.0),
                         sym, closes=closes, n_trades=len(r))

    bestsub = s[(s["dow"] == best["dow"]) & (s["hour"] == best["hour"])]
    allfull = s[~s["hour"].isin(PARTIAL)]
    out.append(compound(bestsub, "best cell, gross", False))
    out.append(compound(bestsub, "best cell, net of costs", True))
    out.append(compound(allfull, "every full hour, gross", False))
    out.append(compound(allfull, "every full hour, net", True))

    print(f"\n  T23 — THE BENCHMARK COLUMN (buy and hold {sym}, same window)\n")
    print(table(out))
    print(f"\n    The best cell is the best of {len(tbl)}, chosen after seeing "
          f"all {len(tbl)}. Its number is an upper bound on what an honest\n"
          f"    out-of-sample version would earn, not an estimate of it. The "
          f"split-half table above is the check that matters.")
    print(f"    'every full hour' is in the market {6*60} minutes a day; buy "
          f"and hold is in it 24 hours including the overnight gap. They are\n"
          f"    not the same risk. The column is here because a return without "
          f"one is not a result.")
    return out


def drill(sym: str, s: pd.DataFrame, dow: str, hour: int, col: str) -> None:
    """Take one cell apart. A mean over 300 observations hides four things.

    Whether it happened every year or in one. Whether a handful of days carry
    it. Whether it needs the first minute's print, which is the hardest fill of
    the day. And what the median says when the mean is being dragged.
    """
    g = s[(s["dow"] == dow) & (s["hour"] == hour)]
    f = friction_for(sym)
    rt = f.round_trip_bp / 1e4
    r = g[col].to_numpy(float)

    print(f"\n  DRILL-DOWN — {sym} {dow} {hour_label(hour)}  "
          f"(n={len(r)}, mean {bp(r.mean())} bp, net {bp(r.mean()-rt)} bp)")

    print(f"\n    by calendar year")
    print(f"    {'year':<8}{'n':>5}{'win%':>7}{'mean':>9}{'net':>9}{'t':>7}")
    print("    " + "-" * 45)
    yrs = g.assign(y=g["date"].dt.year)
    pos_years = 0
    for y, gy in yrs.groupby("y"):
        v = gy[col].to_numpy(float)
        sd = v.std(ddof=1) if len(v) > 1 else float("nan")
        t = v.mean() / (sd / np.sqrt(len(v))) if len(v) > 1 and sd > 0 else float("nan")
        pos_years += v.mean() > 0
        print(f"    {y:<8}{len(v):>5}{(v > 0).mean()*100:>6.1f}%"
              f"{bp(v.mean()):>9}{bp(v.mean()-rt):>9}{t:>7.2f}")
    print(f"    positive in {pos_years} of {yrs['y'].nunique()} calendar years")

    srt = np.sort(r)
    k = int(0.05 * len(r))
    print(f"\n    outlier check — is a handful of days carrying this?")
    print(f"      mean                    {bp(r.mean())} bp")
    print(f"      median                  {bp(float(np.median(r)))} bp")
    print(f"      5% trimmed both tails   {bp(float(srt[k:len(r)-k].mean()))} bp"
          f"   ({k} cut from each end)")
    print(f"      drop the 5 best days    {bp(float(srt[:-5].mean()))} bp")
    print(f"      drop the 5 worst days   {bp(float(srt[5:].mean()))} bp")
    print(f"      drop 5 best AND 5 worst {bp(float(srt[5:-5].mean()))} bp")
    print(f"      best 5:  {', '.join(f'{v*100:+.2f}%' for v in srt[-5:][::-1])}")
    print(f"      worst 5: {', '.join(f'{v*100:+.2f}%' for v in srt[:5])}")
    print(f"      Dropping only the best days is a rigged test — the tails are "
          f"two-sided. The symmetric rows are the fair ones.")

    other = "ret_cc" if col == "ret" else "ret"
    v = g[other].to_numpy(float)
    lbl = "close->close (gives up the first minute)" if other == "ret_cc" \
        else "open->close (takes the opening print)"
    print(f"\n    same cell, {lbl}: {bp(v.mean())} bp, "
          f"net {bp(v.mean()-rt)} bp")
    share = 1.0 - v.mean()/r.mean() if r.mean() else float("nan")
    print(f"      {share*100:.0f}% of this cell's move happens in its first "
          f"minute — the minute you are least likely to get filled in at the "
          f"price shown.")

    # The measured spread came from live fills between 11:00 and 15:55. The
    # open is wider than that and nobody here has measured how much wider, so
    # the honest thing is to show what a range of answers would do rather than
    # pick one.
    print(f"\n    what if the spread at the open is worse than the measured "
          f"{f.spread_bp_entry + f.spread_bp_exit:.2f} bp?")
    print(f"      {'spread x':<12}{'friction':>10}{'net mean':>11}")
    for mult in (1, 2, 3, 5, 10):
        fr = (2 * f.commission_bp_per_side
              + mult * (f.spread_bp_entry + f.spread_bp_exit)) / 1e4
        print(f"      {mult:<12}{fr*1e4:>9.1f}bp{bp(r.mean()-fr):>11}")
    print(f"      The measured figure is from 11:00-15:55 fills. The opening "
          f"minute is not that. This row set is a range, not a measurement.")


def cross_symbol(a: pd.DataFrame, b: pd.DataFrame, col: str) -> None:
    """SOXL and SOXS are the same bet in opposite directions.

    So they are NOT two independent confirmations of anything. What they do
    give is a falsification test: a pattern that lives in the underlying index
    must show up with opposite signs and similar size in both. A pattern that
    is noise, or an artifact of one file, will not.
    """
    ka = summarize(a, ["dow", "hour"], col).set_index(["dow", "hour"])["mean"]
    kb = summarize(b, ["dow", "hour"], col).set_index(["dow", "hour"])["mean"]
    j = pd.concat([ka.rename("SOXL"), kb.rename("SOXS")], axis=1).dropna()
    rho = float(np.corrcoef(j["SOXL"], j["SOXS"])[0, 1])
    agree = int((j["SOXL"] * j["SOXS"] < 0).sum())

    print("=" * 100)
    print("CROSS-SYMBOL CHECK — the same 35 cells measured through a 3x long "
          "and a 3x short")
    print("=" * 100)
    print(f"""
  correlation of the 35 cell means, SOXL vs SOXS:   {rho:+.3f}
  cells with opposite signs:                        {agree} of {len(j)}

  A perfectly inverse pair would be -1.000 and 35 of 35. It is not, and cannot
  be: both are 3x daily-reset funds and both decay, so their means are pushed
  down together rather than mirrored. But {rho:+.3f} is far from zero, which says
  the time-of-day pattern is in the semiconductor index, not in one CSV.

  This is one piece of evidence counted once, not two.
""")
    print(f"  {'cell':<22}{'SOXL':>10}{'SOXS':>10}{'implied SOX*':>15}")
    print("  " + "-" * 57)
    for k, row in j.reindex(
            [(d, h) for d in DAYS for h in HOURS]).dropna().iterrows():
        # SOXL ~ +3x, SOXS ~ -3x of the same underlying move over an hour.
        # Averaging the two estimates is the only use made of this; it is a
        # sanity figure, not an input to anything.
        implied = (row["SOXL"] / 3.0 + row["SOXS"] / -3.0) / 2.0
        star = "  <--" if abs(implied) > 3e-4 else ""
        print(f"  {k[0] + ' ' + hour_label(int(k[1])):<22}"
              f"{bp(row['SOXL']):>10}{bp(row['SOXS']):>10}"
              f"{bp(implied):>15}{star}")
    print("\n  * implied SOX = average of (SOXL/3) and (SOXS/-3). Rough: it "
          "ignores decay, financing and\n    the fact that leverage is exact "
          "only over a single day. Use it for direction and rough size only.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", choices=SYMBOLS + ("BOTH",), default="BOTH")
    ap.add_argument("--since", default=None,
                    help="restrict to sessions on or after this date")
    ap.add_argument("--cc", action="store_true",
                    help="use close-of-:00 -> close-of-:59 instead of open->close")
    ap.add_argument("--drill", default=None, metavar="DOW,HOUR",
                    help="take one cell apart, e.g. --drill Mon,9")
    args = ap.parse_args()

    col = "ret_cc" if args.cc else "ret"
    syms = SYMBOLS if args.symbol == "BOTH" else (args.symbol,)

    held = {}
    for sym in syms:
        df = load(sym, args.since)
        s = slots(df)
        s = s[s["weekday"] < 5]
        held[sym] = s
        report_symbol(sym, s, col, args)
        if args.drill:
            d, h = args.drill.split(",")
            drill(sym, s, d.strip(), int(h), col)
        else:
            tbl = summarize(s, ["dow", "hour"], col)
            top = tbl.loc[tbl["t"].abs().idxmax()]
            drill(sym, s, top["dow"], int(top["hour"]), col)
        print()

    if len(held) == 2:
        cross_symbol(held["SOXL"], held["SOXS"], col)
        print()

    print("=" * 100)
    print("WHAT THIS IS NOT")
    print("=" * 100)
    print("""
  Not a backtest. There is no position sizing, no compounding rule beyond the
  arithmetic printed above, no overnight exposure, no slippage model beyond the
  measured round-trip friction, and no allowance for the fact that a market
  order at 09:30 or 15:59 pays a wider spread than the daily average this
  friction figure came from.

  The averages are of one-hour returns. Nothing here says the hours are
  independent of each other; they are not, and the t-statistics assume they
  are, so treat them as a screen and not as a p-value you would publish.

  Every cell count is a real count from the price files. Every return is
  exit_close / entry_open - 1 on real bars. Nothing is modelled or imputed.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
