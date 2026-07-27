#!/usr/bin/env python3
"""
combined_portfolio.py -- capstone: blend A (vol-decay harvest) + B (semi-residual MR),
both market-neutral and ~uncorrelated, on the common walk-forward-OOS window. Vol-target
each sleeve, combine, scan portfolio-margin leverage, stress. Real costs: A net of ~5.5%/yr
borrow; B net of 5 bp/leg. Daily close-to-close.
"""
import os, itertools, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def dclose(f):
    d=pd.read_csv(os.path.join(ROOT,f)); d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]

# ---- A: band-55 harvest daily returns (gross 2x), net of borrow ----
mA=pd.DataFrame({"L":dclose("SOXL_5min_6Years.csv"),"S":dclose("SOXS_5min_6Years.csv")}).dropna()
mA["rL"]=mA["L"].pct_change(); mA["rS"]=mA["S"].pct_change(); mA=mA.dropna()
mA=mA[(mA["rL"].abs()<0.6)&(mA["rS"].abs()<0.6)]
rL,rS,idxA=mA["rL"].values,mA["rS"].values,mA.index
cap=1.0;VL=1;VS=1;dp=np.empty(len(rL))
for t in range(len(rL)):
    p=-(VL*rL[t]+VS*rS[t]); dp[t]=p/cap; cap+=p; VL*=(1+rL[t]);VS*=(1+rS[t])
    if max(VL,VS)/(VL+VS)>0.55: VL=VS=cap
A=pd.Series(dp,index=idxA)-0.055/252            # net of ~5.5%/yr borrow

# ---- B: residual-MR walk-forward OOS daily returns (net 5bp/leg) ----
D=pd.DataFrame({k:dclose(f) for k,f in [("SOXL","SOXL_5min_6Years.csv"),("SPXL","SPXL_5min_6Years.csv"),("FAS","FAS_5min_6Years.csv")]}).dropna()
R=np.log(D/D.shift(1)).dropna(); R=R[(R.abs()<0.5).all(axis=1)]
BW=60; res=[]
for i in range(BW,len(R)):
    w=R.iloc[i-BW:i]; X=np.column_stack([np.ones(BW),w["SPXL"],w["FAS"]]); b,_,_,_=np.linalg.lstsq(X,w["SOXL"].values,rcond=None)
    res.append(R["SOXL"].iloc[i]-(b[0]+b[1]*R["SPXL"].iloc[i]+b[2]*R["FAS"].iloc[i]))
res=pd.Series(res,index=R.index[BW:]); CBP=5.0
def sret(r,L,th):
    sp=r.cumsum(); z=(sp-sp.rolling(L).mean())/sp.rolling(L).std()
    pos=pd.Series(np.where(z>th,-1.0,np.where(z<-th,1.0,0.0)),index=r.index).shift(1).fillna(0)
    return pos*r - pos.diff().abs().fillna(0)*3*CBP/1e4
def sh(r): r=r.dropna(); return r.mean()/r.std()*np.sqrt(252) if len(r)>20 and r.std()>0 else -9
GRID=list(itertools.product([10,15,20,30,40],[0.0,0.5,1.0])); TRAIN,TEST=504,63; oos=[]; i=TRAIN
while i+TEST<=len(res):
    tr=res.iloc[i-TRAIN:i]; te=res.iloc[i-BW:i+TEST]
    best=max(GRID,key=lambda p:sh(sret(tr,*p))); oos.append(sret(te,*best).iloc[-TEST:]); i+=TEST
B=pd.concat(oos).dropna()

# ---- align on common window; vol-target each to 10%/yr (causal) ----
def vt(r,tgt=0.10,capx=4.0):
    s=(tgt/(r.rolling(20).std()*np.sqrt(252))).clip(upper=capx).shift(1)
    return (r*s).dropna()
common=A.index.intersection(B.index)
Ac,Bc=A.loc[common],B.loc[common]
Av,Bv=vt(Ac),vt(Bc); common2=Av.index.intersection(Bv.index)
Av,Bv=Av.loc[common2],Bv.loc[common2]
def rep(r,lab):
    r=r.dropna(); e=(1+r).cumprod(); yrs=len(r)/252; mo=e.resample("ME").last().pct_change().dropna()
    print(f"  {lab:28s} CAGR {(e.iloc[-1]**(1/yrs)-1)*100:+6.1f}%  Sharpe {sh(r):5.2f}  maxDD {(e/e.cummax()-1).min()*100:6.1f}%  +mo {100*(mo>0).mean():3.0f}%")
print(f"=== A+B COMBINED (common OOS window {common2[0].date()}..{common2[-1].date()}, each vol-targeted 10%) ===")
print(f"  correlation A,B = {pd.concat([Av,Bv],axis=1).corr().iloc[0,1]:+.2f}")
rep(Av,"A alone (harvest, 10% vol)"); rep(Bv,"B alone (residual, 10% vol)")
for wA in [0.5,0.7]:
    rep(wA*Av+(1-wA)*Bv, f"BLEND {int(wA*100)}/{int((1-wA)*100)} A/B")
print(f"\n=== A (harvest) gross vs NET-of-borrow by period — why the recent window is weak ===")
for lab,s,e in [("full 2020-2026",None,None),("option era 2022-2026","2022-01-01",None),("common OOS","2022-11-17","2026-04-28")]:
    a=pd.Series(dp,index=idxA).loc[s:e]
    def _c(r): ee=(1+r.dropna()).cumprod(); return (ee.iloc[-1]**(252/len(r.dropna()))-1)*100
    print(f"  {lab:22s}: gross CAGR {_c(a):+5.1f}% Sh {sh(a):+.2f} | net(-5.5% borrow) CAGR {_c(a-0.055/252):+5.1f}% Sh {sh(a-0.055/252):+.2f}")
port=0.5*Av+0.5*Bv
print(f"\n=== PORTFOLIO-MARGIN LEVERAGE scan on the 50/50 blend (target portfolio vol) ===")
base_vol=port.std()*np.sqrt(252)
for tv in [0.10,0.15,0.20,0.25]:
    k=tv/base_vol; r=port*k; e=(1+r).cumprod(); dd=(e/e.cummax()-1).min()
    print(f"  target {tv*100:.0f}% vol (lev {k:.1f}x): CAGR {(e.iloc[-1]**(252/len(r))-1)*100:+5.0f}%  maxDD {dd*100:5.0f}%  worst day {r.min()*100:5.1f}%  ->$150K: ${(e.iloc[-1]-1)*150000:>9,.0f} end-gain, {(e.iloc[-1]**(252/len(r))-1)*150000:>8,.0f}/yr")
