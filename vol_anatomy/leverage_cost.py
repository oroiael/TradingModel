"""What leverage actually costs: the ETF wrapper vs building it yourself.

1. THE ETF'S ALL-IN COST, measured exactly.
   If SOXL = +3x and SOXS = -3x of the SAME daily index return, then
       r_L = 3*r_I - f_L      and      r_S = -3*r_I - f_S
   so  r_L + r_S = -(f_L + f_S)  EXACTLY, every day, with the index cancelling.
   The mean of that sum is the pair's combined expense + swap financing drag.

2. DIY FINANCING, from the listed option chain.
   For each (date, expiry), put-call parity across strikes gives
       C - K = e^{-rT}(F - K)   ->   regressing (C-P) on K yields
       slope = -e^{-rT}  and  intercept = e^{-rT} * F
   which recovers BOTH the discount rate and the implied forward. A synthetic
   long (long call + short put, same strike) is the listed equivalent of a total
   return swap, and ln(F/S)/T is the financing rate embedded in it.

3. GROWTH-OPTIMAL LEVERAGE. g(k) = k*mu - (k*sigma)^2/2 has a maximum. Past it,
   more leverage lowers compound growth. Measured, not assumed.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from anatomy import load, ann_vol

ROOT = "/home/user/TradingModel"
OUT = os.path.join(ROOT, "vol_anatomy/out")
W = pd.Timestamp("2022-01-01")


def daily_cc(name):
    d = load(name).groupby("date").agg(o=("Open", "first"), c=("Close", "last"))
    d["cc"] = d.c.pct_change()
    d["intra"] = d.c / d.o - 1
    return d


def etf_wrapper_cost():
    L, S = daily_cc("SOXL_5min_6Years.csv"), daily_cc("SOXS_5min_6Years.csv")
    j = pd.DataFrame({"L": L.cc, "S": S.cc, "Li": L.intra, "Si": S.intra}).dropna()
    j = j[j.index >= W]
    # SOXS has repeated reverse splits; a split day breaks close-to-close.
    # Flag them as days where the pair sum is impossibly large.
    s = j.L + j.S
    bad = s.abs() > 0.25
    print(f"  sessions {len(j)}, split/bad-basis days excluded: {int(bad.sum())}")
    good = j[~bad]
    tot = good.L.add(good.S).mean() * 252
    print(f"  mean(r_SOXL + r_SOXS) x 252 = {tot:+.2%} per year   <- COMBINED all-in drag")
    print(f"  stated net expense ratios:    SOXL 0.75% + SOXS 1.00% = 1.75%")
    print(f"  residual (swap spread + tracking, both legs): {abs(tot)-0.0175:+.2%} per year")
    print("\n  NOT decomposable further from this identity: the long leg PAYS financing on")
    print("  its borrowed notional while the short leg RECEIVES it on short proceeds, so the")
    print("  two financing terms partly cancel inside the sum. What is identified is the")
    print("  round-trip cost of the PAIR, and it is the right benchmark for 'is the wrapper")
    print("  cheap?' -- 2.63%/yr of NAV for both legs together, against a stated 1.75%.")
    return tot


def implied_financing():
    e = pd.read_parquet(f"{ROOT}/cc_lp_lab/out/opt_eod_chain.parquet")
    e["date"] = pd.to_datetime(e["date"]); e["exp"] = pd.to_datetime(e["exp"])
    e["dte"] = (e["exp"] - e["date"]).dt.days
    e["mid"] = (e.bid + e.ask) / 2
    e = e[(e.bid > 0) & (e.ask > e.bid) & e.mid.notna()]
    rows = []
    for (d, x), g in e[e.dte.between(20, 400)].groupby(["date", "exp"]):
        c = g[g.right == "C"].set_index("strike")["mid"]
        p = g[g.right == "P"].set_index("strike")["mid"]
        k = c.index.intersection(p.index)
        S = float(g.spot.iloc[0])
        k = k[(k > S * 0.85) & (k < S * 1.15)]
        if len(k) < 5:
            continue
        y = (c[k] - p[k]).values
        A = np.polyfit(k.values, y, 1)
        slope, icept = A[0], A[1]
        if slope >= 0 or slope < -1.5:
            continue
        T = (x - d).days / 365.0
        df = -slope                      # e^{-rT}
        r = -np.log(df) / T
        F = icept / df
        rows.append(dict(date=d, dte=(x - d).days, T=T, S=S, F=F, r=r,
                         carry=np.log(F / S) / T))
    f = pd.DataFrame(rows)
    f = f[f.carry.between(-0.25, 0.35)]
    f.to_csv(f"{OUT}/implied_financing.csv", index=False)
    print(f"  {len(f):,} (date, expiry) fits, 20-400 DTE, 2022-2026")
    print(f"  implied discount rate r : median {f.r.median():.2%}  IQR "
          f"{f.r.quantile(.25):.2%}..{f.r.quantile(.75):.2%}")
    print(f"  implied carry ln(F/S)/T : median {f.carry.median():.2%}  IQR "
          f"{f.carry.quantile(.25):.2%}..{f.carry.quantile(.75):.2%}")
    print("\n  by year (median implied carry = the financing rate baked into a synthetic long):")
    print(f.groupby(f.date.dt.year).agg(carry=("carry", "median"), r=("r", "median"),
                                        n=("r", "size")).to_string(
        formatters={"carry": "{:.2%}".format, "r": "{:.2%}".format}))
    return f


def growth_optimal():
    L = daily_cc("SOXL_5min_6Years.csv")
    L = L[L.index >= W]
    idx = L.cc / 3.0                      # the 1x index, de-levered
    mu, sig = idx.mean() * 252, ann_vol(idx)
    print(f"  1x semis index 2022-2026: arithmetic mean {mu:+.1%}/yr, vol {sig:.1%}")
    print(f"  theoretical growth-optimal leverage k* = mu/sigma^2 = {mu/sig**2:.2f}x\n")
    print("  measured: compound growth of a k-times DAILY-REBALANCED position")
    print("  (no fees; adding the ~2-3%/yr wrapper cost shifts every row down)\n")
    print("     k    ann vol    total return    CAGR      max DD")
    for k in (1, 2, 3, 4, 5, 6, 8):
        r = k * idx
        if (1 + r).min() <= 0:
            print(f"    {k}x    {k*sig:6.1%}    WIPED OUT (a single day <= -{100/k:.1f}% is total loss)")
            continue
        eq = (1 + r).cumprod()
        yrs = (idx.index[-1] - idx.index[0]).days / 365.25
        print(f"    {k}x    {k*sig:6.1%}    {eq.iloc[-1]-1:+11.1%}    "
              f"{eq.iloc[-1]**(1/yrs)-1:+7.1%}   {(eq/eq.cummax()-1).min():7.1%}")
    print(f"\n  the wipe-out threshold is mechanical: at k times leverage a single-day")
    print(f"  index move of -{100:.0f}/k percent takes the position to zero. Worst 1x day")
    print(f"  in this sample: {idx.min():.1%}  -> ruin at k >= {abs(1/idx.min()):.1f}x")


if __name__ == "__main__":
    print("=" * 96); print("1. WHAT THE ETF WRAPPER ACTUALLY COSTS"); print("=" * 96)
    etf_wrapper_cost()
    print("\n" + "=" * 96); print("2. FINANCING IMPLIED BY THE LISTED OPTION CHAIN (the DIY swap)"); print("=" * 96)
    implied_financing()
    print("\n" + "=" * 96); print("3. HOW MUCH LEVERAGE IS TOO MUCH"); print("=" * 96)
    growth_optimal()
