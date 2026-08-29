"""
Owning gamma without options: short both SOXL and SOXS.

A daily-reset leveraged fund must trade in the direction of the move to restore
its leverage every afternoon — buying after a rise, selling after a fall. That is
mechanically a short-gamma position, and its cost shows up as the funds' decay.
Short both sides of the pair and, to first order, the market exposure cancels and
what is left is that decay. The payoff has the shape of a long variance position
with no option and no delta hedging.

Whether it is worth anything is an empirical question with three parts, and only
one of them can be answered from price files:

  1. What does the pair actually decay, gross?          <- measured here
  2. What does it cost to borrow both?                  <- NOT in this repo
  3. Does the market exposure really cancel?            <- measured here

Part 2 is the whole trade and there is no borrow data in this repository, so
nothing here is a return estimate. What is printed instead is the **break-even
combined borrow rate**: the number that, if the real cost is below it, makes the
trade work. That converts an unanswerable question into one the broker can
answer in a minute.

Rebalanced daily to equal dollar shorts, because the two legs drift apart fast
and an unrebalanced pair stops being market neutral within weeks.

    python3 band_lab/v2_dev/pair_decay.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from research_kit import daily_closes, friction_for                # noqa: E402

TRADING_DAYS = 252


def main() -> int:
    a = daily_closes("SOXL")
    b = daily_closes("SOXS")
    j = pd.concat([a.rename("SOXL"), b.rename("SOXS")], axis=1).dropna()
    j = j[j.index >= pd.Timestamp("2022-01-01")]
    rl = j["SOXL"].pct_change().dropna()
    rs = j["SOXS"].pct_change().dropna()

    # Short $1 of each, rebalanced to equal dollars every close. The daily
    # return on $2 of gross short exposure is -(rl + rs)/2.
    pair = -(rl + rs) / 2.0
    eq = (1.0 + pair).cumprod()
    n = len(pair)
    yrs = (j.index[-1] - j.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    sd = pair.std(ddof=1) * np.sqrt(TRADING_DAYS)
    mdd = float((eq / eq.cummax() - 1).min())

    f = friction_for("SOXL")
    # Rebalancing both legs back to equal dollars each close. The traded amount
    # is the drift between the legs; approximate it by the mean absolute
    # difference in leg returns, on half the book each side.
    turn = (rl - rs).abs().mean() / 2.0
    reb_bp = turn * f.round_trip_bp / 1e4 * TRADING_DAYS

    w = 88
    print("=" * w)
    print("SHORT SOXL + SHORT SOXS, rebalanced daily to equal dollars")
    print("=" * w)
    print(f"  {n:,} sessions, {j.index[0].date()} to {j.index[-1].date()} "
          f"({yrs:.2f} years)")
    print(f"\n  GROSS, before borrow and before rebalancing costs")
    print(f"    total return           {(eq.iloc[-1]-1)*100:+8.1f}%")
    print(f"    CAGR                   {cagr*100:+8.1f}%")
    print(f"    annualised vol         {sd*100:8.1f}%")
    print(f"    Sharpe (rf=0)          {cagr/sd if sd else float('nan'):8.2f}")
    print(f"    max drawdown           {mdd*100:8.1f}%")
    print(f"    best day               {pair.max()*100:+8.2f}%")
    print(f"    worst day              {pair.min()*100:+8.2f}%")
    print(f"    positive days          {(pair > 0).mean()*100:8.1f}%")

    print(f"\n  IS IT ACTUALLY MARKET NEUTRAL?")
    print(f"    correlation of the pair return with SOXL   "
          f"{np.corrcoef(pair, rl)[0,1]:+.3f}")
    beta = np.polyfit(rl, pair, 1)[0]
    print(f"    beta to SOXL                               {beta:+.3f}")
    print(f"    A pair that were truly neutral would show both near zero. "
          f"Whatever is left is a\n    directional bet the trade is making "
          f"without being asked to.")

    print(f"\n  BY YEAR")
    print(f"    {'year':<8}{'n':>6}{'return':>10}{'vol':>9}{'worst day':>12}")
    print("    " + "-" * 45)
    for y, g in pair.groupby(pair.index.year):
        e = (1 + g).prod() - 1
        print(f"    {y:<8}{len(g):>6}{e*100:>+9.1f}%"
              f"{g.std(ddof=1)*np.sqrt(TRADING_DAYS)*100:>8.1f}%"
              f"{g.min()*100:>+11.2f}%")

    # ---- the version that actually harvests anything
    print(f"\n" + "=" * w)
    print("REBALANCING FREQUENCY — and why the daily version above is a trap")
    print("=" * w)
    print(f"""
  A 3x daily-reset fund delivers exactly 3x the underlying's move over ONE day,
  by construction. So a pair shorted and rebalanced EVERY day captures no decay
  at all — the {cagr*100:.2f}% above is expense ratios and tracking error, not the
  effect being chased. Decay only accumulates when the position is left alone
  and the fund's own compounding works against it.

  Held for N days without touching it, on $2 of gross short exposure:
""")
    pl, ps = j["SOXL"].to_numpy(float), j["SOXS"].to_numpy(float)
    print(f"  {'hold':<12}{'windows':>9}{'mean':>10}{'median':>10}"
          f"{'worst':>10}{'best':>10}{'% > 0':>9}{'ann.':>9}")
    print("  " + "-" * 79)
    for N in (5, 21, 63, 126, 252, 504):
        if N >= len(pl):
            continue
        ret = -((pl[N:] / pl[:-N] - 1.0) + (ps[N:] / ps[:-N] - 1.0)) / 2.0
        ann = (1 + ret.mean()) ** (TRADING_DAYS / N) - 1
        lbl = {5: "1 week", 21: "1 month", 63: "1 quarter",
               126: "6 months", 252: "1 year", 504: "2 years"}[N]
        print(f"  {lbl:<12}{len(ret):>9,}{ret.mean()*100:>+9.2f}%"
              f"{np.median(ret)*100:>+9.2f}%{ret.min()*100:>+9.2f}%"
              f"{ret.max()*100:>+9.2f}%{(ret > 0).mean()*100:>8.0f}%"
              f"{ann*100:>+8.1f}%")
    print(f"\n  And the SAME positions the other way — LONG both SOXL and "
          f"SOXS, held N days.")
    print(f"  This is a long-gamma structure with no option in it: it bleeds "
          f"the decay every day\n  and pays off on any large move in either "
          f"direction.\n")
    print(f"  {'hold':<12}{'windows':>9}{'mean':>10}{'median':>10}"
          f"{'worst':>10}{'best':>10}{'% > 0':>9}{'ann.':>9}")
    print("  " + "-" * 79)
    for N in (5, 21, 63, 126, 252, 504):
        if N >= len(pl):
            continue
        ret = ((pl[N:] / pl[:-N] - 1.0) + (ps[N:] / ps[:-N] - 1.0)) / 2.0
        ann = (1 + ret.mean()) ** (TRADING_DAYS / N) - 1
        lbl = {5: "1 week", 21: "1 month", 63: "1 quarter",
               126: "6 months", 252: "1 year", 504: "2 years"}[N]
        print(f"  {lbl:<12}{len(ret):>9,}{ret.mean()*100:>+9.2f}%"
              f"{np.median(ret)*100:>+9.2f}%{ret.min()*100:>+9.2f}%"
              f"{ret.max()*100:>+9.2f}%{(ret > 0).mean()*100:>8.0f}%"
              f"{ann*100:>+8.1f}%")
    print(f"""
  Note the shape: a NEGATIVE median and a POSITIVE mean. That is what long
  gamma looks like — lose a little most of the time, win large occasionally.
  It is also what an overfitted tail looks like, and 4.5 years contains only a
  handful of independent large moves, so the mean here rests on very few
  events.

  Overlapping windows: the counts are not independent observations, so the
  '% > 0' column overstates how settled these are. It is a shape, not a t-test.

  The catch is in the 'worst' column. Left alone, the pair stops being market
  neutral — whichever leg is winning grows into the book — so the drawdown is a
  directional loss, not a decay loss. That is the real trade-off: rebalance
  often and harvest nothing, rebalance rarely and take directional risk.""")

    print(f"\n  THE NUMBER THAT DECIDES IT (daily-rebalanced version)")
    print(f"    gross CAGR on the book                     {cagr*100:+7.2f}%")
    print(f"    daily rebalancing friction (estimated)     {-reb_bp*100:+7.2f}%")
    print(f"    ----------------------------------------------------")
    print(f"    break-even COMBINED borrow rate            "
          f"{(cagr - reb_bp)*100:7.2f}%  per year on gross short exposure")
    print(f"""
    Borrow is charged on the value of BOTH shorts. This repository has no
    borrow data, so that number is not estimated here — it is the question to
    put to IBKR. SOXL and SOXS are among the most heavily shorted ETFs in the
    market and hard-to-borrow rates on them are not small. If the combined
    quoted rate is comfortably under the figure above, the trade has room. If
    it is near or over it, there is nothing here.

    Two further costs are not in the number above and both are real:
      - a short position pays every distribution the fund makes
      - both funds have reverse split repeatedly; a short through a reverse
        split is not free to maintain
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
