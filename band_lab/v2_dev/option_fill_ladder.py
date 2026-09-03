"""
V58 — the option fill ladder. What execution quality would the option
structures need to stop losing?

Every option result in this project (V22 through V57, roughly 1,400 priced
configurations) charges the same fill: sell at the bid, buy at the ask, cross
the whole quote every time. That assumption was never varied. On the equity
side it was, once — V26_FILL_LADDER.md — and the six conventions there spanned
+122.57 to -14.46 bp per day, a range larger than any parameter in the grid.

This runs the same experiment on the option structures.

The dial
--------
`k` is how many half-spreads the fill gives up against the mid:

    sell = mid - k * half_spread          buy = mid + k * half_spread

    k = +1.0   the bid / the ask -- cross the whole quote. THE PUBLISHED
               CONVENTION, and the regression target: every number at this
               rung must reproduce V54, V56 and V57 exactly.
    k = +0.6   20% of the spread inside each touch -- the V22 convention
    k =  0.0   both sides fill at the mid
    k = -1.0   sell the ask and buy the bid -- the CEILING. Impossible; it is
               the mirror of V26 row A and bounds the band from above.
    k = +1.3   worse than the touch, the option analogue of V26 row F

Prices are snapped to a whole tick measured from the touch ($0.01 under $3.00,
$0.05 at or above it, verified against the file). Two consequences worth
knowing: k = 1 returns the touch exactly, and a market only one tick wide has
nothing inside it, so k = 0 there is the touch as well.

WHAT THIS DOES NOT MODEL
------------------------
An order resting inside the spread may never fill. Nothing here models the
unfilled case: every cycle is assumed to trade at the rung's price. So the
ladder answers "how good would execution have to be", not "here is a
profitable strategy". A rung that turns positive is a hurdle, not a result.

    python3 band_lab/v2_dev/option_fill_ladder.py
    python3 band_lab/v2_dev/option_fill_ladder.py --quick
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import short_vol_backtest as sv                                    # noqa: E402
import credit_spread_backtest as cs                                # noqa: E402

RUNGS = ((-1.0, "A  CEILING — every fill at the far touch (impossible)"),
         (0.0,  "B  mid on both sides"),
         (0.3,  "C  30% of a half-spread off the mid"),
         (0.6,  "D  20% of the spread inside each touch (the V22 convention)"),
         (1.0,  "E  PUBLISHED — cross the whole quote (V54/V56/V57)"),
         (1.3,  "F  cross, plus a tick of slippage"))


def traded_legs(chain, structure="straddle"):
    """The quotes the structures actually trade, not every quote in the window.

    Averaging the whole 21-60d window would be dominated by deep in-the-money
    strikes with dollar-wide markets that no structure here ever touches. This
    replays the leg selection instead and returns only the legs that get
    picked -- for each tenor band, on each trade date.
    """
    rows = []
    for lo, hi, _ in sv.TENORS:
        for _d, day in chain.groupby("trade_date"):
            cand = day[day.dte.between(lo, hi)]
            if cand.empty:
                continue
            legs = sv.pick_legs(cand[cand.expiration == cand.expiration.min()],
                                structure)
            if legs is None:
                continue
            for r in legs:
                rows.append((r.bid, r.ask))
    return np.array(rows, dtype=float)


def fill_realised(legs, k):
    """What a rung actually buys, in cents and as a share of the half-spread.

    Tick snapping makes k a coarse dial on a narrow quote, so the nominal k is
    not what the trader gets: on a market one tick wide there is nothing inside
    it at all. This measures the improvement actually delivered.
    """
    b, a = legs[:, 0], legs[:, 1]
    s = np.array([sv.sell_px(x, y, k) for x, y in zip(b, a)])
    half = 0.5 * (a - b)
    return (s - b).mean(), np.divide(s - b, half, out=np.zeros_like(half),
                                     where=half > 0).mean(), half.mean()


def straddle_grid(chain, spot, side, k, structure="straddle"):
    out = []
    for lo, hi, tl in sv.TENORS:
        for ex in sv.EXITS:
            t = sv.run(chain, spot, structure, lo, hi, ex, side, k)
            s = sv.stats(t)
            if s:
                out.append(dict(tenor=tl, exit=ex, **s))
    return pd.DataFrame(out)


def spread_grid(chain, spot, k, structures=("put_cs", "call_cs", "condor")):
    out = []
    for st in structures:
        for lo, hi, tl in sv.TENORS:
            for ex in cs.EXITS:
                t = cs.run(chain, spot, st, lo, hi, ex, k)
                s = cs.stats(t)
                if s:
                    out.append(dict(structure=st, tenor=tl, exit=ex, **s))
    return pd.DataFrame(out)


def summarise(g, label, k, rung):
    """One row of the ladder: does any cell clear the bar at this rung?"""
    if g.empty:
        return dict(rung=rung, k=k, label=label, cells=0)
    best = g.loc[g["mean"].idxmax()]
    return dict(rung=rung, k=k, label=label, cells=len(g),
                pos=int((g["mean"] > 0).sum()),
                best=best["mean"], best_t=best["t"],
                best_cell=f"{best.get('structure','')} {best.tenor} {best.exit}".strip(),
                median=g["mean"].median(), n_best=int(best["n"]))


def band(v, floor, ceil):
    """Where a value sits between the published cross and the ceiling."""
    if not np.isfinite(v) or ceil == floor:
        return np.nan
    return 100.0 * (v - floor) / (ceil - floor)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL",
                   help="underlying; needs {SYMBOL}_Options_YYYY.csv to exist")
    p.add_argument("--quick", action="store_true",
                   help="straddles only, skip the 27-cell spread grid")
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    chain = sv.load_chain(a.symbol)
    spot = sv.underlying_daily(a.symbol)
    print(f"\nloaded {len(chain):,} quotes, {chain.trade_date.nunique()} dates, "
          f"{chain.trade_date.min().date()} -> {chain.trade_date.max().date()}")

    legs = traded_legs(chain)
    print(f"\nWHAT EACH RUNG ACTUALLY BUYS, on the {len(legs):,} straddle legs "
          f"these structures select\n  (mean half-spread on those legs: "
          f"{fill_realised(legs, 1.0)[2]*100:.1f}c)")
    print(f"  {'rung':<5}{'k':>6}{'improvement/leg':>18}{'of the half-spread':>21}")
    for k, name in RUNGS:
        c, frac, _ = fill_realised(legs, k)
        print(f"  {name[0]:<5}{k:>+6.2f}{c*100:>17.2f}c{frac*100:>20.0f}%")

    rows, dump = [], []
    for k, name in RUNGS:
        rung = name[0]
        print(f"\n{'='*78}\n{name}     k = {k:+.2f}\n{'='*78}")

        sh = straddle_grid(chain, spot, "short", k)
        lo_ = straddle_grid(chain, spot, "long", k)
        print(f"  {'tenor':<9}{'exit':<9}{'SHORT straddle':>16}{'LONG straddle':>16}"
              f"{'joint':>10}")
        joint = []
        for _, r in sh.iterrows():
            m = lo_[(lo_.tenor == r.tenor) & (lo_.exit == r.exit)]
            lm = m["mean"].iloc[0] if not m.empty else np.nan
            joint.append(r["mean"] + lm)
            print(f"  {r.tenor:<9}{r.exit:<9}{r['mean']*100:>15.3f}%"
                  f"{lm*100:>15.3f}%{(r['mean']+lm)*100:>9.2f}%")
        jm = float(np.nanmean(joint))
        print(f"  {'':<18}{'':>16}{'mean joint':>16}{jm*100:>9.2f}%"
              f"   <- the round trip, both sides")

        rows.append(dict(**summarise(sh, "short straddle", k, rung), joint=jm))
        rows.append(dict(**summarise(lo_, "long straddle", k, rung), joint=jm))
        dump.append(sh.assign(k=k, side="short", family="straddle"))
        dump.append(lo_.assign(k=k, side="long", family="straddle"))

        if not a.quick:
            sp = spread_grid(chain, spot, k)
            b = sp.loc[sp["mean"].idxmax()] if not sp.empty else None
            if b is not None:
                print(f"  credit spreads: {int((sp['mean']>0).sum())} of {len(sp)} "
                      f"cells positive   best {b['mean']*100:+.2f}% "
                      f"t={b['t']:.2f}  ({b.structure} {b.tenor} {b.exit})"
                      f"   B8 breaches {int(sp.breaches.sum())}")
            rows.append(dict(**summarise(sp, "credit spread", k, rung), joint=np.nan))
            dump.append(sp.assign(k=k, side="short", family="credit_spread"))

    L = pd.DataFrame(rows)
    sfx = "" if a.symbol == "SOXL" else f"_{a.symbol}"
    os.makedirs(a.outdir, exist_ok=True)
    L.to_csv(os.path.join(a.outdir, f"V58_option_fill_ladder{sfx}.csv"), index=False)
    pd.concat(dump).to_csv(os.path.join(a.outdir, f"V58_option_fill_cells{sfx}.csv"),
                           index=False)

    print(f"\n\n{'='*78}\nTHE LADDER — best cell in each grid, per cycle\n{'='*78}")
    for lab in L.label.unique():
        s = L[L.label == lab]
        ceil = s.loc[s.k == -1.0, "best"].iloc[0]
        floor_ = s.loc[s.k == 1.0, "best"].iloc[0]
        print(f"\n{lab.upper()}   (ceiling {ceil*100:+.2f}%, "
              f"published {floor_*100:+.2f}%)")
        print(f"  {'rung':<5}{'k':>6}{'best cell':>11}{'t':>7}{'pos':>8}"
              f"{'median':>10}{'band':>7}   where")
        for _, r in s.iterrows():
            print(f"  {r.rung:<5}{r.k:>+6.2f}{r.best*100:>10.2f}%{r.best_t:>7.2f}"
                  f"{f'{r.pos}/{r.cells}':>8}{r['median']*100:>9.2f}%"
                  f"{band(r.best, floor_, ceil):>6.0f}%   {r.best_cell}")

    print(f"\n  ladder -> {a.outdir}/V58_option_fill_ladder{sfx}.csv")
    print(f"  cells  -> {a.outdir}/V58_option_fill_cells{sfx}.csv\n")


if __name__ == "__main__":
    main()
