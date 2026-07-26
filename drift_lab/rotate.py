#!/usr/bin/env python3
"""
rotate.py -- the MIRROR of the vol-harvest: a breakout ROTATION between SOXL and SOXS
(long SOXL above the upper band, long SOXS below the lower). This is a synthetic long
straddle / long gamma -- wins in trends, bleeds in chop. Also answers "does the index
lead the fund?" (it does not, in any tradeable way).

Finding: every realistic variant (Donchian, MA-cross, Bollinger, ROC-gated) loses badly
(-27..-53%/yr, -95%+ DD) -- far worse than buy-hold SOXX (+35%, Sharpe 1.0). The index
gives NO leading edge: signal from SOXX vs SOXL is identical (SOXL=3xSOXX contemporaneously)
and all apparent edge is same-bar LOOKAHEAD (+140% fake vs -39% real). Rotation between two
decaying 3x ETFs = whipsaw x leverage x decay. No synthetic-option rotation play survives.
"""
import os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def daily(f):
    d=pd.read_csv(os.path.join(ROOT,f)); d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]
m=pd.DataFrame({"L":daily("SOXL_5min_6Years.csv"),"S":daily("SOXS_5min_6Years.csv"),"X":daily("SOXX_5min_6Years.csv")}).dropna()
for k in "LSX": m["r"+k]=m[k].pct_change()
m=m.dropna(); m=m[(m["rL"].abs()<0.6)&(m["rS"].abs()<0.6)]
def stats(r,lab):
    r=r.dropna(); e=(1+r).cumprod(); yrs=len(r)/252
    v="WIPED" if e.iloc[-1]<=0 else f"CAGR {(e.iloc[-1]**(1/yrs)-1)*100:+6.1f}%  Sharpe {r.mean()/r.std()*np.sqrt(252):5.2f}  maxDD {(e/e.cummax()-1).min()*100:6.1f}%"
    print(f"  {lab:38s} {v}")
def donchian(sig,N):
    up=sig.rolling(N).max().shift(1); dn=sig.rolling(N).min().shift(1)
    pos=pd.Series(np.nan,index=sig.index); pos[sig>=up]=1; pos[sig<=dn]=-1; pos=pos.ffill().fillna(0)
    return pos
if __name__=="__main__":
    print("=== breakout rotation (Donchian on index), realistic next-bar execution ===")
    for N in [20,40,60]:
        pos=donchian(m["X"],N)
        stats(pd.Series(np.where(pos.shift(1)==1,m["rL"],np.where(pos.shift(1)==-1,m["rS"],0)),index=m.index),f"Donchian {N}d")
    print("=== does the index LEAD? (signal source) + realistic-vs-lookahead ===")
    for nm,s in [("SOXX index",m["X"]),("SOXL fund",m["L"])]:
        pos=donchian(s,20); stats(pd.Series(np.where(pos.shift(1)==1,m["rL"],np.where(pos.shift(1)==-1,m["rS"],0)),index=m.index),f"Donchian20 signal={nm}")
    pos=donchian(m["X"],20)
    stats(pd.Series(np.where(pos==1,m["rL"],np.where(pos==-1,m["rS"],0)),index=m.index),"Donchian20 LOOKAHEAD (same-bar, FAKE)")
    print("=== benchmarks ===")
    stats(m["rX"],"buy-hold SOXX (1x)"); stats(m["rL"],"buy-hold SOXL (3x)")
