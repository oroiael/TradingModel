#!/usr/bin/env python3
"""
run_real_intraday_episodes.py  --  harvest on REAL intraday option prices.

The continuous portfolio engine needs every expiration's chain, but only a sample
of the 1.5 GB intraday set is pulled, so this runs an EPISODE test instead: for
each expiration that HAS intraday data, enter one strangle at the earliest
intraday-covered date and compare three ways of harvesting each leg to expiry:

  REAL  : the option's own 5-min intraday HIGH that day (exit at high*(1-slip))
  BS    : Part-4's model -- BS(underlying intraday extreme, K, T, prior-EOD IV)
  EOD   : harvest only on the daily EOD close (what a close-only trader gets)

This shows, on real prices, (a) how much intraday harvesting beats EOD and (b)
whether the BS model reproduces the REAL-price result at the P&L level.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from data_loader import load_options, load_5min
from intraday_options import load_all_present, available_expirations
from verticals import buy_fill, sell_fill, valid_quote
from bs import bs_call, bs_put

DIST, TAKE, SLIP = 0.075, 0.50, 0.05
pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 80 + f"\n{t}\n" + "=" * 80)


def main():
    hr("LOAD")
    io = load_all_present()
    io["date"] = pd.to_datetime(io["ts_naive"]).dt.date
    # per (exp,right,strike,date): option intraday high + last vwap
    ohi = (io.groupby(["expiration", "right", "strike", "date"])
             .agg(opt_hi=("high", "max")).reset_index())
    ohi_key = {(r.date, r.expiration, float(r.strike), r.right): r.opt_hi
               for r in ohi.itertuples(index=False)}

    day = load_options(years=[2024, 2025])
    dkey = {(td, ex, float(k), r): (b, a, c, iv) for td, ex, k, r, b, a, c, iv in
            zip(day.trade_date, day.expiration, day.strike, day.right,
                day.bid, day.ask, day.close, day.implied_vol)}
    umap = day.groupby("trade_date")["underlying_price"].first().to_dict()
    tds = sorted(day["trade_date"].unique())
    tset = set(tds)
    prev = {tds[i]: tds[i - 1] for i in range(1, len(tds))}

    fm = load_5min(); fm["date"] = pd.to_datetime(fm["ts"]).dt.date
    dhl = fm.groupby("date").agg(hi=("High", "max"), lo=("Low", "min"))

    exps = sorted(available_expirations().keys())
    hr(f"EPISODE test across {len(exps)} expirations with intraday data  "
       f"(dist {DIST:.1%}, take +{TAKE:.0%}, slip {SLIP:.0%})")

    def leg_strike(exp, right, spot):
        # nearest strike present in BOTH daily and intraday for this exp
        tgt = spot * (1 + DIST) if right == "CALL" else spot * (1 - DIST)
        cand = sorted({k for (_, e, k, r) in ohi_key if e == exp and r == right},
                      key=lambda k: abs(k - tgt))
        return cand[0] if cand else None

    recs = []
    for exps_str in exps:
        exp = pd.to_datetime(exps_str).date()
        # entry = earliest daily trade_date that has intraday coverage for this exp
        idays = sorted({d for (d, e, k, r) in ohi_key if e == exp})
        idays = [d for d in idays if d in tset]
        if len(idays) < 5:
            continue
        entry = idays[0]
        spot = umap.get(entry)
        if spot is None:
            continue
        dte = (pd.Timestamp(exp) - pd.Timestamp(entry)).days
        for right in ("CALL", "PUT"):
            K = leg_strike(exp, right, spot)
            if K is None:
                continue
            q = dkey.get((entry, exp, K, right))
            if not q or not valid_quote(q[0], q[1]):
                continue
            entry_cost = buy_fill(q[0], q[1])
            if entry_cost <= 0.05:
                continue
            hold = [d for d in idays if d > entry]
            res = {}
            for method in ("REAL", "BS", "EOD"):
                exit_ret = None
                for d in hold:
                    S = umap.get(d)
                    if method == "REAL":
                        hi = ohi_key.get((d, exp, K, right))
                        if hi and hi / entry_cost - 1 >= TAKE:
                            exit_ret = hi * (1 - SLIP) / entry_cost - 1; break
                    elif method == "BS":
                        ptd = prev.get(d)
                        iv = dkey.get((ptd, exp, K, right), (0, 0, 0, None))[3] if ptd else None
                        if iv and iv > 0 and d in dhl.index:
                            T = max((pd.Timestamp(exp) - pd.Timestamp(d)).days, 0) / 365
                            Sx = dhl.loc[d, "hi"] if right == "CALL" else dhl.loc[d, "lo"]
                            bsp = bs_call(Sx, K, T, iv) if right == "CALL" else bs_put(Sx, K, T, iv)
                            if bsp / entry_cost - 1 >= TAKE:
                                exit_ret = bsp * (1 - SLIP) / entry_cost - 1; break
                    else:  # EOD
                        qd = dkey.get((d, exp, K, right))
                        if qd and valid_quote(qd[0], qd[1]) and sell_fill(qd[0], qd[1]) / entry_cost - 1 >= TAKE:
                            exit_ret = sell_fill(qd[0], qd[1]) / entry_cost - 1; break
                if exit_ret is None:                      # expire intrinsic
                    Sx = umap.get(exp) or umap.get([t for t in tds if t <= exp][-1])
                    intr = max(0.0, Sx - K) if right == "CALL" else max(0.0, K - Sx)
                    exit_ret = intr / entry_cost - 1
                res[method] = exit_ret
            recs.append(dict(exp=exp, dte=dte, right=right, K=K, entry_cost=entry_cost, **res))

    r = pd.DataFrame(recs)
    print(f"episodes (legs): {len(r)}  across {r['exp'].nunique()} expirations, "
          f"entry DTE {r['dte'].min()}-{r['dte'].max()}")
    print("\nmean leg return on premium, by harvest method:")
    print(f"   REAL (real intraday high) : {r['REAL'].mean():+.1%}   win {(r['REAL']>0).mean():.0%}")
    print(f"   BS   (Part-4 model)       : {r['BS'].mean():+.1%}   win {(r['BS']>0).mean():.0%}")
    print(f"   EOD  (close-only)         : {r['EOD'].mean():+.1%}   win {(r['EOD']>0).mean():.0%}")
    print(f"\n   intraday(REAL) uplift over EOD: {r['REAL'].mean()-r['EOD'].mean():+.1%} per leg")
    print(f"   BS vs REAL gap (model error) : {r['BS'].mean()-r['REAL'].mean():+.1%} per leg")
    print("\nby entry-DTE bucket (mean REAL leg return / n):")
    r["dte_b"] = pd.cut(r["dte"], [0, 30, 60, 400], labels=["<=30", "31-60", ">60"])
    print(r.groupby("dte_b", observed=True).agg(n=("REAL", "size"),
          REAL=("REAL", "mean"), EOD=("EOD", "mean")).round(3).to_string())


if __name__ == "__main__":
    main()
