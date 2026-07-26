#!/usr/bin/env python3
"""
vol_harvest.py -- construct a SOXL/SOXS trade that harvests the volatility decay as cash.

Core idea (from the mechanics work): a 3x fund's -3*sigma^2 daily-reset decay is a
MULTI-DAY compounding effect. Shorting BOTH SOXL and SOXS is market-neutral and short
that decay (short gamma). DAILY rebalancing captures ~none of it (resets with the fund);
letting it DRIFT captures it but blows up in trends. The lever is a DRIFT-BAND rebalance:
reset to equal-dollar only when one leg exceeds `band` of gross -> harvest decay in chop,
force-cover the ballooning leg in a trend. Real data (SOXL/SOXS/SOXX 5-min -> daily).

Result (full sample, no borrow, band 55%, gross 2x short): CAGR +12%/yr, Sharpe 1.12,
maxDD -9.4%, +65% of months, positive every calendar year incl. the 2026 melt-up; robust
in both sample halves; survives transaction costs. It is still SHORT VOLATILITY -- the
tail is a fast melt-up / overnight gap you can't rebalance through. Borrow costs excluded
by request (SOXS borrow is the real drag). Not investment advice.
"""
import os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def daily(f):
    d=pd.read_csv(os.path.join(ROOT,f))
    d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]

def frame():
    m=pd.DataFrame({"L":daily("SOXL_5min_6Years.csv"),"S":daily("SOXS_5min_6Years.csv")}).dropna()
    m["rL"]=m["L"].pct_change(); m["rS"]=m["S"].pct_change()
    m=m.dropna(); return m[(m["rL"].abs()<0.6)&(m["rS"].abs()<0.6)]

def backtest(rL,rS,idx,band=0.55,w=1.0,cost_bp=0.0):
    """short w*equity of SOXL and SOXS; rebalance to equal when a leg exceeds `band` of gross."""
    cap=1.0; VL=w; VS=w; eq=np.empty(len(rL))
    for t in range(len(rL)):
        cap-=VL*rL[t]+VS*rS[t]                       # short P&L
        if cap<=0: eq[t:]=0; break                    # margin wipeout
        VL*=(1+rL[t]); VS*=(1+rS[t])
        if max(VL,VS)/(VL+VS)>band:
            cap-=cost_bp/1e4*abs(VL-VS); VL=VS=w*cap  # re-equalize (with cost)
        eq[t]=cap
    return pd.Series(eq,index=idx)

def stats(eq):
    r=eq.pct_change().replace([np.inf,-np.inf],np.nan).dropna()
    if len(r)<10 or eq.iloc[-1]<=0: return dict(cagr=np.nan,sharpe=np.nan,dd=-1,posmo=np.nan)
    yrs=len(r)/252; mo=eq.resample("ME").last().pct_change().dropna()
    return dict(cagr=(eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1, sharpe=r.mean()/r.std()*np.sqrt(252),
                dd=(eq/eq.cummax()-1).min(), posmo=(mo>0).mean(), medmo=mo.median())

if __name__=="__main__":
    m=frame(); rL,rS,idx=m["rL"].values,m["rS"].values,m.index
    def show(lab,eq):
        s=stats(eq); print(f"  {lab:30s} CAGR {s['cagr']*100:+6.1f}%  Sharpe {s['sharpe']:5.2f}  maxDD {s['dd']*100:6.1f}%  +mo {s['posmo']*100:3.0f}%")
    print("=== cadence: fixed-calendar vs drift-band (short-both, w=1, no cost) ===")
    print("  fixed calendar (blows up slow):")
    # simple calendar rebalance for contrast
    def cal(N):
        cap=1.0;VL=1.0;VS=1.0;eq=np.empty(len(rL))
        for t in range(len(rL)):
            cap-=VL*rL[t]+VS*rS[t]
            if cap<=0: eq[t:]=0;break
            VL*=(1+rL[t]);VS*=(1+rS[t])
            if (t+1)%N==0: VL=VS=cap
            eq[t]=cap
        return pd.Series(eq,index=idx)
    for N,l in [(1,"daily"),(5,"weekly"),(21,"monthly")]: show(f"calendar {l}",cal(N))
    print("  DRIFT-BAND (the fix):")
    for b in [0.53,0.55,0.60]: show(f"band {int(b*100)}%",backtest(rL,rS,idx,b))
    print("=== leverage sizing (band 55%) & transaction cost ===")
    for w in [0.5,1.0,1.5]: show(f"band55 w={w} (gross {2*w}x)",backtest(rL,rS,idx,0.55,w))
    for c in [3,10]: show(f"band55 w=1 cost {c}bp/rebal",backtest(rL,rS,idx,0.55,1.0,c))
    print("=== out-of-sample: band 55% w=1 in each half ===")
    for lab,sub in [("2020-2023",m[m.index<'2024-01-01']),("2024-2026",m[m.index>='2024-01-01'])]:
        show(lab,backtest(sub["rL"].values,sub["rS"].values,sub.index,0.55))
    print("=== per-year cash (band 55% w=1) ===")
    eq=backtest(rL,rS,idx,0.55); ys=eq.groupby(eq.index.year).apply(lambda s:(s.iloc[-1]/s.iloc[0]-1)*100)
    print("  "+"  ".join(f"{y}:{v:+4.0f}%" for y,v in ys.items()))
