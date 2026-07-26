#!/usr/bin/env python3
"""
active_strategies.py -- survey of active SOXL ideas, all on real data (daily/5-min):
  A) fast-SMA (intraday mean-reversion + daily momentum)  -> fails (cost trap / decay-whipsaw)
  B) cross-asset fit to SPXL(S&P) / FAS(financials)       -> no lead; but the market-neutral
                                                             semi-RESIDUAL weakly mean-reverts
  C) SOXL vs SOXS "independent"                            -> corr -0.99, not independent
Conclusion: directional/timing edges fail (SOXL is efficiently priced + decays). The only
survivors are MARKET-NEUTRAL structure trades: the vol-decay harvest (Sharpe ~1.1, robust)
and, as a qualified maybe, semi-residual mean-reversion (Sharpe ~0.6 net, unstable OOS).
Treasuries/FX are NOT in the repo -- upload to test a rates/FX lead (prior is low: even the
broad market, far more correlated to semis than rates/FX, does not lead).
"""
import os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def dclose(f):
    d=pd.read_csv(os.path.join(ROOT,f)); d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]
def ols(y,cols):
    X=np.column_stack([np.ones(len(y))]+cols); b,_,_,_=np.linalg.lstsq(X,y,rcond=None)
    r=y-X@b; return b, 1-(r@r)/np.sum((y-y.mean())**2)

def main():
    D=pd.DataFrame({k:dclose(f) for k,f in [("SOXL","SOXL_5min_6Years.csv"),("SPXL","SPXL_5min_6Years.csv"),
        ("FAS","FAS_5min_6Years.csv"),("SOXS","SOXS_5min_6Years.csv")]}).dropna()
    R=np.log(D/D.shift(1)).dropna(); R=R[(R.abs()<0.5).all(axis=1)]
    print("A) CROSS-ASSET: how much of SOXL is the market, and does it lead?")
    for k in ["SPXL","FAS"]:
        b,r2=ols(R["SOXL"].values,[R[k].values]); print(f"   SOXL~{k}: beta {b[1]:.2f} R2 {r2:.2f}")
        y=R["SOXL"].values[1:]; b2,_=ols(y,[R[k].values[1:],R[k].values[:-1]])
        print(f"      lead-lag: lagged {k} coef {b2[2]:+.3f} (want >0 to lead; ~0 => no lead)")
    print(f"   corr(SOXL,SOXS)={R['SOXL'].corr(R['SOXS']):.3f}  (not independent; both = one directional bet)")

    print("\nB) SEMI-RESIDUAL stat-arb (SOXL hedged of SPXL+FAS, rolling 60d beta):")
    win=60; res=[]
    for i in range(win,len(R)):
        w=R.iloc[i-win:i]; b,_=ols(w["SOXL"].values,[w["SPXL"].values,w["FAS"].values])
        res.append(R["SOXL"].iloc[i]-(b[0]+b[1]*R["SPXL"].iloc[i]+b[2]*R["FAS"].iloc[i]))
    res=pd.Series(res,index=R.index[win:])
    cum=res.cumsum(); z=(cum-cum.rolling(20).mean())/cum.rolling(20).std(); pos=(-np.sign(z)).shift(1).fillna(0)
    turn=pos.diff().abs().fillna(0)
    for cbp in [0,5]:
        pnl=((pos*res)-turn*3*cbp/1e4).dropna()
        print(f"   residual-MR cost {cbp}bp/leg: Sharpe {pnl.mean()/pnl.std()*np.sqrt(252):+.2f}")
    for lab,sub in [("2020-2023",res[res.index<'2024-01-01']),("2024-2026",res[res.index>='2024-01-01'])]:
        c=sub.cumsum(); zz=(c-c.rolling(20).mean())/c.rolling(20).std(); p=(-np.sign(zz)).shift(1).fillna(0); pn=(p*sub).dropna()
        print(f"      OOS {lab}: Sharpe {pn.mean()/pn.std()*np.sqrt(252):+.2f}")

    print("\nC) FAST-SMA (daily momentum): decay+whipsaw")
    dsx=dclose("SOXL_5min_6Years.csv"); dr=dsx.pct_change()
    for N in [5,20]:
        sma=dsx.rolling(N).mean(); rr=(pd.Series(np.where(dsx.shift(1)>sma.shift(1),1,-1),index=dsx.index)*dr).dropna()
        e=(1+rr).cumprod(); print(f"   SMA{N} momentum: CAGR {(e.iloc[-1]**(252/len(rr))-1)*100:+.0f}% Sharpe {rr.mean()/rr.std()*np.sqrt(252):+.2f}")

if __name__=="__main__": main()
