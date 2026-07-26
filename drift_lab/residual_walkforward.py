#!/usr/bin/env python3
"""
residual_walkforward.py -- honest walk-forward of the semi-residual mean-reversion.

Residual = SOXL daily return minus its CAUSAL market fit (rolling 60d beta to SPXL+FAS).
Strategy(L,theta): fade the z-score (lookback L) of the cumulative residual when |z|>theta;
trade NEXT day (shift 1). Walk-forward: every `test` days, pick (L,theta) that maximized
Sharpe on the trailing `train` window (past only), apply to the next test block; concatenate
the OOS test returns. Costs = turnover x 3 legs x bp. Compares WF vs fixed vs grid-average.
"""
import os, itertools, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def dclose(f):
    d=pd.read_csv(os.path.join(ROOT,f)); d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]

D=pd.DataFrame({k:dclose(f) for k,f in [("SOXL","SOXL_5min_6Years.csv"),("SPXL","SPXL_5min_6Years.csv"),("FAS","FAS_5min_6Years.csv")]}).dropna()
R=np.log(D/D.shift(1)).dropna(); R=R[(R.abs()<0.5).all(axis=1)]
# causal residual (rolling 60d beta, applied out-of-sample to today)
BW=60; res=[]
for i in range(BW,len(R)):
    w=R.iloc[i-BW:i]; X=np.column_stack([np.ones(BW),w["SPXL"],w["FAS"]])
    b,_,_,_=np.linalg.lstsq(X,w["SOXL"].values,rcond=None)
    res.append(R["SOXL"].iloc[i]-(b[0]+b[1]*R["SPXL"].iloc[i]+b[2]*R["FAS"].iloc[i]))
res=pd.Series(res,index=R.index[BW:]); n=len(res)

CBP=5.0  # bp per leg per unit turnover
def strat_ret(residual, L, theta):
    spread=residual.cumsum(); z=(spread-spread.rolling(L).mean())/spread.rolling(L).std()
    raw=np.where(z>theta,-1.0,np.where(z<-theta,1.0,0.0))
    pos=pd.Series(raw,index=residual.index).shift(1).fillna(0)
    gross=pos*residual; turn=pos.diff().abs().fillna(0)
    return (gross - turn*3*CBP/1e4)
def sharpe(r): r=r.dropna(); return r.mean()/r.std()*np.sqrt(252) if r.std()>0 and len(r)>20 else -9

GRID=list(itertools.product([10,15,20,30,40],[0.0,0.5,1.0]))
TRAIN,TEST=504,63
oos=[]; picks=[]
i=TRAIN
while i+TEST<=n:
    tr=res.iloc[i-TRAIN:i]; te=res.iloc[i-BW:i+TEST]        # include lookback tail for rolling calc
    best=max(GRID, key=lambda p: sharpe(strat_ret(tr,*p)))
    r_te=strat_ret(te,*best).iloc[-TEST:]                   # only the test block
    oos.append(r_te); picks.append((res.index[i].date(),best)); i+=TEST
OOS=pd.concat(oos)
def rep(r,lab):
    r=r.dropna(); e=(1+r).cumprod()
    print(f"  {lab:34s} Sharpe {sharpe(r):+.2f}  CAGR {(e.iloc[-1]**(252/len(r))-1)*100:+5.0f}%  maxDD {(e/e.cummax()-1).min()*100:5.0f}%  n={len(r)}")
print(f"=== WALK-FORWARD (train {TRAIN}d, test {TEST}d, {len(picks)} OOS blocks, {CBP}bp/leg) ===")
rep(OOS,"WALK-FORWARD (OOS, selected)")
# benchmarks on the SAME OOS window
win0=OOS.index[0]
rep(strat_ret(res,20,0.0).loc[win0:],"fixed (L=20, theta=0), same window")
rep(pd.concat([strat_ret(res,*p).loc[win0:] for p in GRID],axis=1).mean(axis=1),"GRID-AVERAGE (all params), same window")
# in-sample-best (upward biased, for reference)
isb=max(GRID,key=lambda p:sharpe(strat_ret(res,*p)))
rep(strat_ret(res,*isb).loc[win0:],f"in-sample-best {isb} (BIASED ref)")
# parameter stability + per-year OOS
from collections import Counter
print("  selected-param frequency:",Counter(p for _,p in picks).most_common())
yr=OOS.groupby(OOS.index.year).apply(lambda r:sharpe(r))
print("  OOS Sharpe by year:", {int(k):round(v,2) for k,v in yr.items()})

# ---- robustness: concentration, realistic sizing, diversification ----
ex24=OOS[OOS.index.year!=2024]
print("\n=== ROBUSTNESS ===")
print(f"  EX-2024 Sharpe {sharpe(ex24):+.2f}  |  share of OOS P&L from 2024: {OOS[OOS.index.year==2024].sum()/OOS.sum()*100:.0f}%  (lumpy)")
print(f"  OOS quarters positive: {sum(1 for b in oos if b.sum()>0)}/{len(oos)}")
tv=OOS.rolling(20).std()*np.sqrt(252); vt=(OOS*(0.15/tv).clip(upper=3).shift(1)).dropna(); e=(1+vt).cumprod()
print(f"  vol-targeted 15%: Sharpe {sharpe(vt):+.2f}  CAGR {(e.iloc[-1]**(252/len(vt))-1)*100:+.0f}%  maxDD {(e/e.cummax()-1).min()*100:.0f}%")
# correlation to the decay harvest (diversification)
m=pd.DataFrame({"L":dclose("SOXL_5min_6Years.csv"),"S":dclose("SOXS_5min_6Years.csv")}).dropna()
m["rL"]=m["L"].pct_change(); m["rS"]=m["S"].pct_change(); m=m.dropna(); m=m[(m["rL"].abs()<0.6)&(m["rS"].abs()<0.6)]
rL,rS,idx=m["rL"].values,m["rS"].values,m.index; cap=1.0;VL=1;VS=1;eq=np.empty(len(rL))
for t in range(len(rL)):
    cap-=VL*rL[t]+VS*rS[t]; VL*=(1+rL[t]);VS*=(1+rS[t])
    if max(VL,VS)/(VL+VS)>0.55: VL=VS=cap
    eq[t]=cap
harv=pd.Series(eq,index=idx).pct_change()
print(f"  corr(residual-MR, decay-harvest) = {pd.DataFrame({'a':OOS,'b':harv}).dropna().corr().iloc[0,1]:+.2f}  (low => diversifying sleeve)")
