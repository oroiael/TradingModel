"""Does the model mark reproduce a real 10:00 trade print? Measured, not assumed."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import data, pricing

CARRY = 0.04

def main():
    e, tr = data.eod_chain(), data.intraday_trades()
    spot = data.spot_at(600)
    # real 10:00 prints, joined to the same day's EOD chain row
    p = tr[tr.minute == 600].copy()
    j = p.merge(e[["date","exp","right","strike","bid","ask","iv","spot","dte"]],
                on=["date","exp","right","strike"], how="inner")
    j = j[j.iv.notna() & (j.iv > 0) & (j.px > 0.02)]
    j["S10"] = j["date"].map(spot["px"])
    j = j[j.S10.notna() & j.dte.between(0, 200)]
    j["T"] = (j.dte + (960 - 600) / 390.0) / 365.0
    j["model"] = pricing.bs_price(j.S10.values, j.strike.values, j["T"].values,
                                  j.iv.values, CARRY, 0.0, j.right.values)
    j["mid"] = (j.bid + j.ask) / 2
    j["rel"] = (j.model - j.px) / j.px
    j["moneyness"] = j.strike / j.S10

    print(f"paired 10:00 prints x EOD chain: {len(j):,}\n")
    def rep(g, label):
        if len(g) < 30: return
        print(f"{label:<28} n={len(g):>7,}  median rel err {np.median(g.rel):+.3f}"
              f"  MAE {np.mean(np.abs(g.rel)):.3f}  |err|<10%: {(g.rel.abs()<.10).mean():.1%}")
    rep(j, "ALL")
    print("\n-- by DTE bucket --")
    for lab, g in j.groupby(pd.cut(j.dte, [-1,1,7,30,60,120,200])):
        rep(g, str(lab))
    print("\n-- by option price bucket --")
    for lab, g in j.groupby(pd.cut(j.px, [0.02,0.10,0.25,0.50,1,2,5,1000])):
        rep(g, str(lab))
    print("\n-- the two legs this strategy actually trades --")
    calls = j[(j.right=="C") & j.dte.between(2,7) & j.moneyness.between(1.0,1.15)]
    rep(calls, "weekly call, 2-strk OTM")
    puts = j[(j.right=="P") & j.dte.between(60,150) & j.moneyness.between(0.85,1.0)]
    rep(puts, "~90d put, 2-strk OTM")
    print("\n-- print vs EOD mid, same contracts (how far does a day move things?) --")
    for lab,g in [("weekly call",calls),("90d put",puts)]:
        if len(g)>30:
            r=(g["mid"]-g.px)/g.px
            print(f"{lab:<28} median (EODmid-print)/print {np.median(r):+.3f}")
    print("\n-- EOD relative bid/ask spread on the traded legs --")
    for lab,g in [("weekly call 2-OTM",calls),("90d put 2-OTM",puts)]:
        if len(g)>30:
            rs=((g.ask-g.bid)/g["mid"]).replace([np.inf,-np.inf],np.nan).dropna()
            print(f"{lab:<28} median {rs.median():.3f}  p75 {rs.quantile(.75):.3f}  "
                  f"half-spread in $: {((g.ask-g.bid)/2).median():.3f}")

if __name__ == "__main__":
    main()
