#!/usr/bin/env python3
"""
residual_generalization.py -- try to HARDEN trade B (semi-residual mean-reversion) by
running the identical walk-forward on an INDEPENDENT sector (FAS = 3x financials) and
pooling. Honest result: it generalizes (FAS is positive OOS) but is a COMMON 2024-REGIME
effect, not a diversifiable sector-idiosyncratic edge -- so pooling does NOT make it robust.
Real data only (SOXL, FAS, SPXL 5-min -> daily). Reproduce as-is.
"""
import itertools, numpy as np, pandas as pd, os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def dclose(f):
    d=pd.read_csv(os.path.join(ROOT,f)); d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]
P=pd.DataFrame({"SOXL":dclose("SOXL_5min_6Years.csv"),"FAS":dclose("FAS_5min_6Years.csv"),"SPXL":dclose("SPXL_5min_6Years.csv")}).dropna()
R=np.log(P/P.shift(1)).dropna(); R=R[(R.abs()<0.5).all(axis=1)]
BW=60; CBP=5.0; GRID=list(itertools.product([10,15,20,30,40],[0.0,0.5,1.0])); TRAIN,TEST=504,63
def resid(t,f):
    o=[]
    for i in range(BW,len(R)):
        w=R.iloc[i-BW:i]; X=np.column_stack([np.ones(BW)]+[w[c].values for c in f]); b,_,_,_=np.linalg.lstsq(X,w[t].values,rcond=None)
        o.append(R[t].iloc[i]-(b[0]+sum(b[j+1]*R[c].iloc[i] for j,c in enumerate(f))))
    return pd.Series(o,index=R.index[BW:])
def sret(r,L,th):
    sp=r.cumsum(); z=(sp-sp.rolling(L).mean())/sp.rolling(L).std()
    pos=pd.Series(np.where(z>th,-1.,np.where(z<-th,1.,0.)),index=r.index).shift(1).fillna(0)
    return pos*r-pos.diff().abs().fillna(0)*3*CBP/1e4
def sh(r): r=r.dropna(); return r.mean()/r.std()*np.sqrt(252) if len(r)>20 and r.std()>0 else -9
def wf(res):
    oos=[]; i=TRAIN
    while i+TEST<=len(res):
        tr=res.iloc[i-TRAIN:i]; te=res.iloc[i-BW:i+TEST]; best=max(GRID,key=lambda p:sh(sret(tr,*p))); oos.append(sret(te,*best).iloc[-TEST:]); i+=TEST
    return pd.concat(oos).dropna()
streams={}
for tgt,fac in [("SOXL",["SPXL","FAS"]),("FAS",["SPXL","SOXL"])]:
    res=resid(tgt,fac); w=wf(res); streams[tgt]=w; ex=w[w.index.year!=2024]
    ga=np.mean([sh(sret(res.loc[w.index[0]:],*p)) for p in GRID])
    print(f"{tgt} residual-MR (hedge {'+'.join(fac)}): OOS Sharpe {sh(w):+.2f} | grid-avg {ga:+.2f} | EX-2024 {sh(ex):+.2f} | 2024 P&L share {w[w.index.year==2024].sum()/w.sum()*100:.0f}%")
c=streams["SOXL"].index.intersection(streams["FAS"].index); sx,fs=streams["SOXL"].loc[c],streams["FAS"].loc[c]
pool=0.5*(sx/sx.std())+0.5*(fs/fs.std())
print(f"POOLED (equal-risk): corr={pd.concat([sx,fs],axis=1).corr().iloc[0,1]:+.2f} | Sharpe {sh(pool):+.2f} | 2024 P&L share {pool[pool.index.year==2024].sum()/pool.sum()*100:.0f}% | EX-2024 {sh(pool[pool.index.year!=2024]):+.2f}")
print("VERDICT: generalizes (FAS>0 OOS) but common-2024-regime; pooling amplifies not diversifies. Not a robust edge.")
