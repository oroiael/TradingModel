#!/usr/bin/env python3
"""
debug_bracket.py  --  find why the weekly bracket is +41% one way and -22% another.
Rebuild the SAME per-expiration cycles with three explicit exit rules and compare,
so we know which number (if any) is real.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import load_options  # noqa: E402

ANN = 252; WKS = 52


def cycles():
    o = load_options()
    o = o[(o["bid"] > 0) & (o["ask"] >= o["bid"]) & o["delta"].notna()].copy()
    o["trade_date"] = pd.to_datetime(o["trade_date"]); o["expiration"] = pd.to_datetime(o["expiration"])
    return o


def run(o, exit_rule):
    """exit_rule in {'expiry_intrinsic','expiry_bid','early3_bid'}. Long ATM straddle,
    delta-hedged daily. Returns per-cycle P&L (% of entry notional)."""
    recs = []
    for exp, g in o.groupby("expiration"):
        g = g.sort_values("trade_date")
        dte = (exp - g["trade_date"]).dt.days
        em = (dte >= 4) & (dte <= 8)
        if not em.any():
            continue
        t0 = g.loc[em, "trade_date"].min()
        ge = g[g["trade_date"] == t0]
        spot0 = float(ge["underlying_price"].iloc[0])
        calls, puts = ge[ge["right"] == "CALL"], ge[ge["right"] == "PUT"]
        if calls.empty or puts.empty or spot0 <= 0:
            continue
        K = float(calls.iloc[(calls["strike"] - spot0).abs().argmin()]["strike"])
        c0 = ge[(ge["right"] == "CALL") & (ge["strike"] == K)]
        p0 = ge[(ge["right"] == "PUT") & (ge["strike"] == K)]
        if c0.empty or p0.empty:
            continue
        cost = float(c0["ask"].iloc[0] + p0["ask"].iloc[0])
        gc = g[(g["right"] == "CALL") & (g["strike"] == K)].set_index("trade_date")
        gp = g[(g["right"] == "PUT") & (g["strike"] == K)].set_index("trade_date")
        dates = [d for d in sorted(set(gc.index) | set(gp.index)) if d >= t0]
        if exit_rule == "early3_bid":
            dates = [d for d in dates if (exp - d).days >= 3]
        if len(dates) < 2:
            continue
        spot, ndelta, cmid, pmid, cbid, pbid = {}, {}, {}, {}, {}, {}
        for d in dates:
            src = gc if d in gc.index else gp
            spot[d] = float(src.loc[d, "underlying_price"])
            dc = float(gc.loc[d, "delta"]) if d in gc.index else np.nan
            dp = float(gp.loc[d, "delta"]) if d in gp.index else np.nan
            ndelta[d] = (dc if dc == dc else 0.0) + (dp if dp == dp else 0.0)
            if d in gc.index:
                cmid[d] = float(gc.loc[d, "bid"] + gc.loc[d, "ask"]) / 2; cbid[d] = float(gc.loc[d, "bid"])
            if d in gp.index:
                pmid[d] = float(gp.loc[d, "bid"] + gp.loc[d, "ask"]) / 2; pbid[d] = float(gp.loc[d, "bid"])
        # hedge P&L (daily, using prior-day delta)
        hedge = 0.0; last = ndelta[dates[0]]
        for i in range(len(dates) - 1):
            d, d1 = dates[i], dates[i + 1]
            hedge += -last * (spot[d1] - spot[d])
            last = ndelta[d1]
        S_E = spot[dates[-1]]
        if exit_rule == "expiry_intrinsic":
            terminal = max(S_E - K, 0.0) + max(K - S_E, 0.0)
        elif exit_rule == "expiry_bid":
            terminal = cbid.get(dates[-1], 0.0) + pbid.get(dates[-1], 0.0)
        else:  # early3_bid -> close at last held day's bid
            terminal = cbid.get(dates[-1], 0.0) + pbid.get(dates[-1], 0.0)
        opt = terminal - cost
        recs.append(dict(date=t0, exp=exp, pnl=(opt + hedge) / spot0,
                         held_days=len(dates), last_dte=(exp - dates[-1]).days))
    return pd.DataFrame(recs)


def stat(df):
    r = df["pnl"].values
    eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (WKS / len(r)) - 1 if eq[-1] > 0 else -1
    return dict(n=len(r), mean=r.mean(), arith=r.mean() * WKS, cagr=cagr,
                sh=r.mean() / r.std(ddof=1) * np.sqrt(WKS), avg_last_dte=df["last_dte"].mean(),
                avg_held=df["held_days"].mean())


def main():
    o = cycles()
    for rule in ["expiry_intrinsic", "expiry_bid", "early3_bid"]:
        s = stat(run(o, rule))
        print(f"{rule:20s} n={s['n']} meanPnL/wk {s['mean']:+.2%}  arith {s['arith']:+.0%}  "
              f"CAGR {s['cagr']:+.0%}  Sharpe {s['sh']:+.2f}  "
              f"avg_last_dte {s['avg_last_dte']:.1f}  avg_held {s['avg_held']:.1f}")
    print("\nbracket_weekly.py uses 'expiry_intrinsic' + arithmetic annualization.")
    print("reconcile.py uses ~'early3_bid' + daily geometric compounding + continuous gaps.")


if __name__ == "__main__":
    main()
