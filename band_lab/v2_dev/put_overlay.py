"""
Does a protective put pay for itself against a 1% stop?

The proposal: hold SOXL, buy a put one strike out of the money to match the
share position, and when the stock drops 1% sell the put for a profit that
offsets the loss. Tested at 30, 60 and 90 days to expiry.

The mechanism is real. The arithmetic is not.

Two things settle it, and neither needs a backtest
---------------------------------------------------
1. A put is a position-size cut, not insurance you get for free. Long 100
   shares plus one put of delta -d is a net delta of 100(1-d). At SOXL's
   quoted deltas that is 62 to 65. Both sides scale: the put cuts the 1% loss
   AND it cuts the 3% gain, by the same factor. The identical exposure is
   available by buying 62 shares instead of 100, at no premium, no spread and
   no decay.

   The only thing the put adds over simply holding fewer shares is convexity --
   the gamma term, 0.5 * gamma * dS^2. That term is measured here too, so it
   can be compared against what it costs rather than assumed to be worth
   something.

2. The put has to be bought and sold across a quoted spread. That spread is
   measured below against the hedge gain it is bought to capture.

Reads SOXL_1Yr_Options_Greeks_EOD.csv: real quotes, real greeks, one snapshot
per trade date. Note these are END OF DAY quotes and may be wider than the
same contract midday, so the spread figures are pessimistic -- though not by
the factor of seven that would be needed to change the conclusion.

    python3 band_lab/v2_dev/put_overlay.py
    python3 band_lab/v2_dev/put_overlay.py --move 0.02 --band 0.10
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TENORS = ((21, 40, "~30 day"), (50, 75, "~60 day"), (80, 105, "~90 day"))


def load_puts(path):
    cols = ["expiration", "strike", "right", "bid", "ask", "delta", "gamma",
            "theta", "implied_vol", "underlying_price", "trade_date"]
    df = pd.read_csv(path, usecols=cols, low_memory=False)
    df = df[df.right == "PUT"].copy()
    df["dte"] = (pd.to_datetime(df.expiration)
                 - pd.to_datetime(df.trade_date)).dt.days
    df["mid"] = (df.bid + df.ask) / 2
    # A quote needs two live sides to be a quote. Sub-nickel bids are noise.
    df = df[(df.bid > 0.05) & (df.ask > df.bid) & (df.mid > 0)
            & df.delta.notna() & (df.underlying_price > 0)]
    df["moneyness"] = df.strike / df.underlying_price - 1
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", default="SOXL_1Yr_Options_Greeks_EOD.csv")
    p.add_argument("--move", type=float, default=0.01,
                   help="adverse move the hedge is bought to cover")
    p.add_argument("--band", type=float, default=0.075,
                   help="how far below spot still counts as one strike OTM")
    p.add_argument("--commission", type=float, default=0.65,
                   help="per contract per side")
    a = p.parse_args()

    df = load_puts(os.path.join(ROOT, a.file))
    otm = df[(df.moneyness > -a.band) & (df.moneyness < -0.005)]
    print(f"{len(df):,} SOXL put quotes over {df.trade_date.nunique()} trade dates "
          f"({df.trade_date.min()} -> {df.trade_date.max()})")
    print(f"{len(otm):,} of them one strike OTM "
          f"(0.5% to {a.band * 100:.1f}% below spot)\n")

    print(f"ONE CONTRACT (100 shares) AGAINST A {a.move * 100:.0f}% ADVERSE MOVE")
    print(f"  {'tenor':<9}{'|delta|':>9}{'net delta':>11}{'premium $':>11}"
          f"{'delta gain':>12}{'gamma gain':>12}{'theta/day':>11}"
          f"{'spread $':>10}{'gain/cost':>11}")
    rows = []
    for lo, hi, lab in TENORS:
        g = otm[(otm.dte >= lo) & (otm.dte <= hi)]
        if len(g) < 50:
            continue
        d, gam, th = g.delta.abs().median(), g.gamma.median(), g.theta.median()
        S, spr, prem = g.underlying_price.median(), (g.ask - g.bid).median(), g.mid.median()
        dS = a.move * S
        delta_gain, gamma_gain = d * dS * 100, 0.5 * gam * dS * dS * 100
        cost = spr * 100 + 2 * a.commission          # one round trip, both sides
        rows.append((lab, d, prem, delta_gain, gamma_gain, th * 100, spr * 100, cost))
        print(f"  {lab:<9}{d:>9.3f}{100 * (1 - d):>11.0f}{prem * 100:>11,.0f}"
              f"{delta_gain:>12.2f}{gamma_gain:>12.2f}{th * 100:>11.2f}"
              f"{spr * 100:>10,.0f}{(delta_gain + gamma_gain) / cost:>10.2f}x")

    print(f"\n  delta gain  what the put makes on the move -- and exactly what you")
    print(f"              forgo on an equivalent move UP, so it is not profit")
    print(f"  gamma gain  the only part fewer shares cannot replicate")
    print(f"  gain/cost   (delta+gamma gain) / (spread + ${a.commission}/side commission)")
    print(f"              under 1.00x, one round trip costs more than the hedge pays")

    print(f"\nWHAT THE GAMMA IS ACTUALLY WORTH")
    for lab, d, prem, dg, gg, th, spr, cost in rows:
        print(f"  {lab:<9} gamma {gg:>6.2f}  vs round-trip cost {cost:>7.2f}"
              f"   = {gg / cost * 100:>5.2f}% of it")
    print(f"\nBREAKEVEN: the spread the hedge could bear, against what is quoted")
    print(f"  {'tenor':<9}{'breakeven spread':>18}{'quoted spread':>16}{'too wide by':>13}")
    for lab, d, prem, dg, gg, th, spr, cost in rows:
        be = dg + gg
        print(f"  {lab:<9}{be:>17,.2f}{spr:>16,.2f}{spr / be:>12.1f}x")

    print(f"\nAND THE STANDING-HEDGE VERSION (hold it, do not trade it)")
    for lab, d, prem, dg, gg, th, spr, cost in rows:
        dte = {"~30 day": 30, "~60 day": 60, "~90 day": 90}[lab]
        print(f"  {lab:<9} theta {th:>7.2f}/day x {dte} days = {th * dte:>9,.0f} "
              f"of a {prem * 100:>7,.0f} premium, to hold {100 * (1 - d):.0f} delta")
    print()


if __name__ == "__main__":
    main()
