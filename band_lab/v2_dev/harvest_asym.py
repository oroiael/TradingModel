"""
Asymmetric barriers: does an uneven target and stop change anything?

Every test so far used a symmetric threshold -- +X% against -X%. This sweeps
the two sides independently, and checks the theory that says it cannot help.

The theory, stated so the result can be checked against it
-----------------------------------------------------------
For a driftless random walk with an up barrier at +a and a down barrier at -b,
the optional stopping theorem gives

    P(up first) = b / (a + b)          E[payoff] = (b/(a+b))*a - (a/(a+b))*b = 0

The probability and the payoff move in exact opposition, so the expectation is
zero for EVERY pair. Asymmetry relocates the coin flip; it does not remove it.
A +1.0%/-0.5% setup wins a third of the time and pays double -- and nets zero.

So the check has two halves. First, measure P(up first) for each pair against
b/(a+b): agreement means the series is a driftless walk at this horizon and no
pair can have an edge. Deviation is drift, which is the only thing that could.
Second, backtest anyway, because two effects the theorem does not cover are
real: wider barriers trade less and so pay less cost, and PARK is not a barrier
bet at all -- it holds losers to 15:55, so moving the stop changes what gets
held rather than what gets realised.

Selection is validated, not assumed
------------------------------------
The symmetric sweep produced 31 "profitable" configurations out of 150 that
were the right tail of a zero-edge distribution. So every configuration here is
fitted on the first 70% of sessions and judged on the last 30%, and the
headline number is the correlation between the two across the whole grid. If
choosing by training performance does not predict test performance, parameter
selection on this rule is worthless no matter how good the best row looks.

    python3 band_lab/v2_dev/harvest_asym.py
    python3 band_lab/v2_dev/harvest_asym.py --stride 5
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_one_day import NO_NEW_MIN, ibkr_tiered, resolve  # noqa: E402
from harvest_series import load_sessions, run_series  # noqa: E402

GRID = (0.0025, 0.005, 0.0075, 0.010, 0.015, 0.020)
SLOTS = (50, 100)
CUTOFFS = (11 * 60, 14 * 60)
TRAIN_FRAC = 0.70


def barrier_probabilities(sessions, pairs, stride):
    """Observed P(up first) per barrier pair, against the driftless prediction.

    Every stride-th minute is an independent start, so this is a property of
    the price series and not of any trading rule.
    """
    print(f"  sampling every {stride}th minute as an independent start...")
    rows, t0 = [], time.time()
    for up, dn in pairs:
        n_up = n_dn = 0
        for bars in sessions.values():
            for i in range(0, len(bars), stride):
                if bars[i][0] >= NO_NEW_MIN:
                    break
                e = bars[i][1]
                out, _j, _f, _a = resolve(bars, i, e * (1 + up), e * (1 - dn))
                if out == "up":
                    n_up += 1
                elif out == "down":
                    n_dn += 1
        tot = n_up + n_dn
        if not tot:
            continue
        obs = n_up / tot
        theory = dn / (up + dn)
        # Expected payoff per resolved trade, in fractions of position value.
        ev = obs * up - (1 - obs) * dn
        rows.append(dict(up=up, dn=dn, n=tot, observed=obs, theory=theory,
                         gap=obs - theory, ev=ev))
    print(f"  done in {time.time() - t0:.0f}s")
    return pd.DataFrame(rows)


def score(df, equity0):
    eq = df.end_equity.to_numpy(float)
    final = float(eq[-1])
    yrs = (pd.Timestamp(df.date.iloc[-1]) - pd.Timestamp(df.date.iloc[0])).days / 365.25
    cagr = (final / equity0) ** (1 / yrs) - 1 if yrs > 0 and final > 0 else np.nan
    peaks = np.maximum.accumulate(eq)
    r = df.ret.to_numpy(float)
    sd = r.std(ddof=1)
    return dict(final=final, cagr=cagr, max_dd=float((eq / peaks - 1).min()),
                sharpe=r.mean() / sd * np.sqrt(252) if sd else np.nan,
                trades=int(df.trades.sum()), fees=float(df.fees.sum()),
                frozen=bool((df.trades == 0).iloc[-1]))


def evaluate(sessions, configs, equity0, reserve, commission, slippage, tag):
    rows, t0 = [], time.time()
    for k, (park, up, dn, slots, cutoff) in enumerate(configs, 1):
        df, _tp, _tw = run_series(sessions, (up, dn), park, equity0, reserve,
                                  slots, commission, slippage=slippage,
                                  cutoff=cutoff, marks=False)
        rows.append(dict(rule="PARK" if park else "CLOSE", up=up, dn=dn,
                         slots=slots if park else 1, cutoff=cutoff,
                         **score(df, equity0)))
        if k % 60 == 0 or k == len(configs):
            print(f"    {tag}: {k}/{len(configs)}  {time.time() - t0:.0f}s",
                  flush=True)
    return pd.DataFrame(rows)


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def show(df, title, n=15):
    print(f"\n  {title}")
    print(f"    {'rule':<6}{'up':>7}{'down':>7}{'slots':>7}{'cut':>7}"
          f"{'train CAGR':>12}{'test CAGR':>12}{'test maxDD':>12}"
          f"{'test Sh':>9}{'trades':>9}")
    for _, r in df.head(n).iterrows():
        print(f"    {r['rule']:<6}{r['up'] * 100:>6.2f}%{r['dn'] * 100:>6.2f}%"
              f"{r['slots']:>7.0f}{hhmm(int(r['cutoff'])):>7}"
              f"{r['cagr_train'] * 100:>11.2f}%{r['cagr_test'] * 100:>11.2f}%"
              f"{r['max_dd_test'] * 100:>11.1f}%{r['sharpe_test']:>9.2f}"
              f"{r['trades_test']:>9,.0f}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL")
    p.add_argument("--equity", type=float, default=100_000)
    p.add_argument("--reserve", type=float, default=25_000)
    p.add_argument("--slippage", type=float, default=0.005)
    p.add_argument("--stride", type=int, default=10,
                   help="sample every Nth minute for the probability check")
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    sessions = load_sessions(a.symbol)
    days = sorted(sessions)
    cut = int(len(days) * TRAIN_FRAC)
    train = {d: sessions[d] for d in days[:cut]}
    test = {d: sessions[d] for d in days[cut:]}
    print(f"loaded {len(sessions):,} sessions")
    print(f"  train {days[0].date()} -> {days[cut - 1].date()}  ({len(train):,})")
    print(f"  test  {days[cut].date()} -> {days[-1].date()}  ({len(test):,})\n")

    pairs = [(u, d) for u, d in itertools.product(GRID, GRID)]

    print(f"{'=' * 104}")
    print(f"  PART 1  Is the series a driftless walk? P(up first) vs b/(a+b)")
    print(f"{'=' * 104}")
    bp = barrier_probabilities(sessions, pairs, a.stride)
    print(f"\n    {'up':>7}{'down':>7}{'n':>10}{'observed':>11}{'theory':>10}"
          f"{'gap':>9}{'EV/trade':>11}")
    for _, r in bp.iterrows():
        flag = "  <-- drift" if abs(r["gap"]) > 0.02 else ""
        print(f"    {r['up'] * 100:>6.2f}%{r['dn'] * 100:>6.2f}%{r['n']:>10,.0f}"
              f"{r['observed'] * 100:>10.2f}%{r['theory'] * 100:>9.2f}%"
              f"{r['gap'] * 100:>+8.2f}{r['ev'] * 100:>+10.3f}%{flag}")
    print(f"\n    mean |gap| from the driftless prediction: "
          f"{bp.gap.abs().mean() * 100:.2f} percentage points")
    print(f"    pairs with EV > 0 before costs: {(bp.ev > 0).sum()} of {len(bp)}")
    print(f"    best EV/trade {bp.ev.max() * 100:+.3f}%   "
          f"worst {bp.ev.min() * 100:+.3f}%")

    configs = [(True, u, d, s, c)
               for (u, d), s, c in itertools.product(pairs, SLOTS, CUTOFFS)]
    configs += [(False, u, d, 1, c) for (u, d), c in itertools.product(pairs, CUTOFFS)]

    print(f"\n{'=' * 104}")
    print(f"  PART 2  {len(configs)} configurations, fitted on train, judged on test")
    print(f"{'=' * 104}")
    tr = evaluate(train, configs, a.equity, a.reserve, None, 0.0, "train")
    te = evaluate(test, configs, a.equity, a.reserve, None, 0.0, "test ")
    key = ["rule", "up", "dn", "slots", "cutoff"]
    m = tr.merge(te, on=key, suffixes=("_train", "_test"))

    good = m.dropna(subset=["cagr_train", "cagr_test"])
    rho = good.cagr_train.corr(good.cagr_test)
    # Spearman via pandas pulls in scipy, which is not installed here.
    # Rank correlation IS Pearson on the ranks, so compute it directly.
    rank = good.cagr_train.rank().corr(good.cagr_test.rank())
    print(f"\n{'=' * 104}")
    print(f"  DOES TRAINING PERFORMANCE PREDICT TEST PERFORMANCE?")
    print(f"{'=' * 104}")
    print(f"    across {len(good)} configurations:  "
          f"Pearson {rho:+.3f}    Spearman {rank:+.3f}")
    print(f"    train positive {int((m.cagr_train > 0).sum())}/{len(m)}   "
          f"test positive {int((m.cagr_test > 0).sum())}/{len(m)}   "
          f"positive in BOTH {int(((m.cagr_train > 0) & (m.cagr_test > 0)).sum())}")

    byt = m.sort_values("cagr_train", ascending=False)
    show(byt, "TOP 15 CHOSEN ON TRAIN -- and what they then did on TEST")
    print(f"\n    of the top 15 by train, {int((byt.head(15).cagr_test > 0).sum())} "
          f"were positive on test; mean test CAGR "
          f"{byt.head(15).cagr_test.mean() * 100:+.2f}%")
    show(m.sort_values("cagr_test", ascending=False),
         "TOP 15 ON TEST (cherry-picked with hindsight -- not selectable)", 15)

    sym = m[m.up == m.dn]
    asy = m[m.up != m.dn]
    print(f"\n  SYMMETRIC vs ASYMMETRIC (test period)")
    for lbl, sub in (("symmetric", sym), ("asymmetric", asy)):
        print(f"    {lbl:<11} {len(sub):>4} configs   "
              f"best {sub.cagr_test.max() * 100:>+7.2f}%   "
              f"median {sub.cagr_test.median() * 100:>+7.2f}%   "
              f"positive {int((sub.cagr_test > 0).sum()):>3}")

    top = [(r["rule"] == "PARK", r["up"], r["dn"], int(r["slots"]), int(r["cutoff"]))
           for _, r in byt.head(15).iterrows()]
    print(f"\n{'=' * 104}")
    print(f"  PART 3  the 15 train-selected configurations, priced on TEST with costs")
    print(f"{'=' * 104}")
    c1 = evaluate(test, top, a.equity, a.reserve, None, a.slippage, "slip ")
    c2 = evaluate(test, top, a.equity, a.reserve, ibkr_tiered, a.slippage, "all-in")
    print(f"\n    {'rule':<6}{'up':>7}{'down':>7}{'slots':>7}{'cut':>7}"
          f"{'gross':>11}{'+slippage':>12}{'+commission':>13}")
    for i in range(len(top)):
        r, s, t = byt.iloc[i], c1.iloc[i], c2.iloc[i]
        print(f"    {r['rule']:<6}{r['up'] * 100:>6.2f}%{r['dn'] * 100:>6.2f}%"
              f"{r['slots']:>7.0f}{hhmm(int(r['cutoff'])):>7}"
              f"{r['cagr_test'] * 100:>10.2f}%{s['cagr'] * 100:>11.2f}%"
              f"{t['cagr'] * 100:>12.2f}%")
    print(f"\n    survivors gross on test:            "
          f"{int((byt.head(15).cagr_test > 0).sum())} of 15")
    print(f"    survivors after slippage:           {int((c1.cagr > 0).sum())} of 15")
    print(f"    survivors after slippage+commission: {int((c2.cagr > 0).sum())} of 15")

    os.makedirs(a.outdir, exist_ok=True)
    bp.to_csv(os.path.join(a.outdir, f"harvest_asym_barrier_prob_{a.symbol}.csv"),
              index=False)
    m.to_csv(os.path.join(a.outdir, f"harvest_asym_grid_{a.symbol}.csv"), index=False)
    print(f"\n  -> {a.outdir}/harvest_asym_barrier_prob_{a.symbol}.csv")
    print(f"  -> {a.outdir}/harvest_asym_grid_{a.symbol}.csv\n")


if __name__ == "__main__":
    main()
