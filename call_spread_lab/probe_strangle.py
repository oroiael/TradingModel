#!/usr/bin/env python3
"""
probe_strangle.py  --  does a plain long strangle on SOXL have the raw material
for active harvesting? Buys an OTM call + OTM put, marks both legs daily to
expiration (20% fill), and measures: cost, breakevens vs realized moves, how
often each leg spikes (the harvest fuel), and buy-&-hold strangle expectancy.

This is a GROUNDING probe, not the harvesting backtest -- it informs the design.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from data_loader import load_options
from verticals import build_index, buy_fill, sell_fill, valid_quote

DTE_TARGET = 90
DIST = 0.10          # 10% OTM each side


def nearest_strike(strikes, target):
    return strikes[int(np.argmin(np.abs(strikes - target)))]


def main():
    opt = load_options(whole_strikes_only=True, verbose=True)
    chain_by_td, spot_by_td, quote_by_key, tds = build_index(opt)
    td_index = {t: i for i, t in enumerate(tds)}

    # entry ~ every 10 trading days
    entries = tds[::10]
    rows = []
    for td in entries:
        spot = spot_by_td[td]
        day = chain_by_td[td]
        # pick expiration nearest 90 DTE
        exps = day[["expiration", "dte"]].drop_duplicates()
        exps = exps[(exps["dte"] >= DTE_TARGET - 15) & (exps["dte"] <= DTE_TARGET + 20)]
        if exps.empty:
            continue
        exp = exps.iloc[(exps["dte"] - DTE_TARGET).abs().argmin()]["expiration"]
        ce = day[(day["expiration"] == exp) & (day["right"] == "CALL")]
        pe = day[(day["expiration"] == exp) & (day["right"] == "PUT")]
        if ce.empty or pe.empty:
            continue
        kc = nearest_strike(ce["strike"].values, spot * (1 + DIST))
        kp = nearest_strike(pe["strike"].values, spot * (1 - DIST))
        cq = quote_by_key.get((td, "CALL", exp, kc))
        pq = quote_by_key.get((td, "PUT", exp, kp))
        if not cq or not pq or not valid_quote(*cq) or not valid_quote(*pq):
            continue
        c_cost = buy_fill(*cq); p_cost = buy_fill(*pq)
        cost = c_cost + p_cost
        if cost <= 0:
            continue

        # mark both legs each day to expiration; track peak gains + terminal
        i0 = td_index[td]
        j = i0 + 1
        c_peak = p_peak = 0.0
        S_exp = spot
        while j < len(tds) and tds[j] <= exp:
            d = tds[j]; S = spot_by_td[d]; S_exp = S
            cqi = quote_by_key.get((d, "CALL", exp, kc))
            pqi = quote_by_key.get((d, "PUT", exp, kp))
            if cqi and valid_quote(*cqi):
                c_peak = max(c_peak, sell_fill(*cqi) / c_cost - 1)
            if pqi and valid_quote(*pqi):
                p_peak = max(p_peak, sell_fill(*pqi) / p_cost - 1)
            j += 1
        # terminal intrinsic
        c_term = max(0.0, S_exp - kc); p_term = max(0.0, kp - S_exp)
        hold_pnl = (c_term + p_term) - cost
        rows.append(dict(entry=td, spot=spot, exp=exp, kc=kc, kp=kp,
                         cost=cost, cost_pct=cost / spot,
                         move=abs(S_exp / spot - 1), signed_move=S_exp / spot - 1,
                         c_peak=c_peak, p_peak=p_peak,
                         best_peak=max(c_peak, p_peak),
                         hold_ror=hold_pnl / cost))
    df = pd.DataFrame(rows)
    print(f"\n{len(df)} strangles, 90 DTE, 10% OTM each side, 20% fills\n")
    print(f"cost as % of spot: median {df['cost_pct'].median():.1%}  "
          f"mean {df['cost_pct'].mean():.1%}  "
          f"(breakeven needs move > ~cost/... this is a long-vol bet)")
    print(f"|move| to expiration: median {df['move'].median():.1%}  "
          f">15%: {(df['move']>0.15).mean():.0%}  >30%: {(df['move']>0.30).mean():.0%}")
    print("\nPEAK intra-life gain of the BEST leg (the harvest fuel):")
    for thr in (0.25, 0.5, 1.0, 2.0, 3.0):
        print(f"   best leg peaks >= +{thr*100:.0f}% at some point: "
              f"{(df['best_peak']>=thr).mean():.0%}")
    print("\nBUY-AND-HOLD strangle (no harvest), return on cost:")
    print(f"   mean {df['hold_ror'].mean():+.0%}  median {df['hold_ror'].median():+.0%}  "
          f"win {( df['hold_ror']>0).mean():.0%}  worst {df['hold_ror'].min():+.0%}  "
          f"best {df['hold_ror'].max():+.0%}")
    print("\nby year (buy-hold mean return on cost / best-leg median peak):")
    df["year"] = pd.to_datetime(df["entry"]).dt.year
    print(df.groupby("year").agg(n=("hold_ror", "size"),
                                 hold_ror=("hold_ror", "mean"),
                                 best_peak=("best_peak", "median"),
                                 move=("move", "median")).round(2).to_string())


if __name__ == "__main__":
    main()
