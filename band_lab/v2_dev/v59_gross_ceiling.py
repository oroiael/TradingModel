"""
V59 — What the 1-minute data can and cannot be asked, once spreads are set aside.

Two halves, because the two instruments in this project are in completely
different situations and it is worth never confusing them again.

  EQUITY   SOXL_1min.csv is Date,Open,High,Low,Close,Volume. Trade prices only.
           No bid, no ask, no sizes. Every equity transaction-cost number in
           this project is therefore an ASSUMPTION, and no amount of care with
           this file can turn it into a measurement.

  OPTIONS  the SOXL_Options_YYYY.csv files carry bid, ask, bid_size, ask_size,
           bid_exchange, ask_exchange and both quote conditions. Those are real
           quotes, so V54/V56/V57/V58 are charged a measured spread already and
           are untouched by the decision recorded here.

    python3 band_lab/v2_dev/v59_gross_ceiling.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def equity_ceiling():
    """The gross surface: the fine grid's `ev`, which charges nothing at all."""
    f = pd.read_csv(os.path.join(OUT, "harvest_fine_surface_SOXL.csv"))
    print("=" * 78)
    print("HALF 1 — THE EQUITY CEILING, no spread and no commission")
    print("=" * 78)
    print(f"\n  {len(f)} barrier pairs, {f.n.iloc[0]:,} candidate entries each.")
    print(f"  `ev` is expectation per trade before ANY cost. `edge_ticks` is the")
    print(f"  same number in cents at the sample's median price.\n")
    b = f.loc[f.ev.idxmax()]
    print(f"  cells with a positive gross edge     {int((f.ev > 0).sum()):>4} of {len(f)}"
          f"   ({(f.ev > 0).mean() * 100:.0f}%)")
    print(f"  best gross EV per trade              {f.ev.max() * 100:>+8.4f}%"
          f"  = {b.edge_ticks:.2f} ticks")
    print(f"     at up {b.up * 100:.1f}% / down {b.dn * 100:.1f}%,"
          f" {b.ev / b.ev_se:.1f} SE, {b.unresolved * 100:.0f}% of starts unresolved")
    print(f"  median gross EV per trade            {f.ev.median() * 100:>+8.4f}%"
          f"  = {f.edge_ticks.median():.2f} ticks")
    print(f"  gross edge larger than ONE tick      {int((f.edge_ticks > 1).sum()):>4} of {len(f)}")
    print(f"  gross edge larger than HALF a tick   {int((f.edge_ticks > 0.5).sum()):>4} of {len(f)}")

    up_r = f.up.rank().corr(f.ev.rank())
    dn_r = f.dn.rank().corr(f.ev.rank())
    print(f"\n  THE REASON THE CEILING IS NOT A RESULT")
    print(f"    rank corr of gross EV with the UP-barrier width    {up_r:>+7.3f}")
    print(f"    rank corr of gross EV with the DOWN-barrier width  {dn_r:>+7.3f}")
    print(f"    SOXL rose 540% across the sample. A gross edge that tracks the up")
    print(f"    barrier this closely is long exposure to that rise, not a harvest.")
    return f


def option_spread_census():
    """The EOD quoted spread that V54/V56/V58 actually pay, by year."""
    import short_vol_backtest as sv
    chain = sv.load_chain()
    rows = []
    for d0, day in chain.groupby("trade_date"):
        cand = day[day.dte.between(35, 39)]          # V32's own selection rule
        if cand.empty:
            continue
        legs = sv.pick_legs(cand[cand.expiration == cand.expiration.min()], "straddle")
        if legs is None:
            continue
        rows.append((d0, sum(r.bid for r in legs), sum(r.ask for r in legs),
                     legs[0].underlying_price))
    d = pd.DataFrame(rows, columns=["date", "bid", "ask", "spot"])
    d["pct"] = (d.ask - d.bid) / ((d.ask + d.bid) / 2) * 100
    d["yr"] = d.date.dt.year

    print("\n" + "=" * 78)
    print("HALF 2 — THE OPTION SPREAD IS MEASURED, NOT ASSUMED")
    print("=" * 78)
    print("\n  ATM straddle, 35-39 DTE -- the contract-selection rule V32 used, so")
    print("  the rows below are directly comparable to its live IBKR measurement.")
    print("  V52 established these bid/ask columns are END-OF-DAY quotes; the")
    print("  `timestamp` column is a last-TRADE time and belongs to the trade")
    print("  record joined beside them, not to the quote.\n")
    print(f"  {'year':<6}{'n':>5}{'mean':>9}{'median':>9}{'p90':>9}{'mean $':>9}{'mean spot':>11}")
    for y, g in d.groupby("yr"):
        print(f"  {y:<6}{len(g):>5}{g.pct.mean():>8.1f}%{g.pct.median():>8.1f}%"
              f"{g.pct.quantile(.9):>8.1f}%{(g.ask - g.bid).mean():>9.2f}{g.spot.mean():>11.2f}")
    print(f"  {'ALL':<6}{len(d):>5}{d.pct.mean():>8.1f}%{d.pct.median():>8.1f}%"
          f"{d.pct.quantile(.9):>8.1f}%{(d.ask - d.bid).mean():>9.2f}{d.spot.mean():>11.2f}")
    print(f"\n  V32's live IBKR ticks, 2026-08-17..08-28: 14.6% of mid.")
    print(f"  That sits INSIDE the file's own 4.2%-19.2% year range and the two")
    print(f"  samples do not overlap in time, so it does not establish that the")
    print(f"  file is too tight. It does establish the spread is regime-dependent")
    print(f"  by a factor of four, which is why a single flat assumption is wrong.")
    return d


def main():
    f = equity_ceiling()
    d = option_spread_census()
    os.makedirs(OUT, exist_ok=True)
    d.to_csv(os.path.join(OUT, "V59_option_spread_by_year.csv"), index=False)
    print(f"\n  spread census -> {OUT}/V59_option_spread_by_year.csv\n")


if __name__ == "__main__":
    main()
