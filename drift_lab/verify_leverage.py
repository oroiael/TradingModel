#!/usr/bin/env python3
"""
verify_leverage.py -- confirm SOXL's stated mechanics (fact sheet / SAI) in the data.

Inputs (all on main):
  SOXL_5min_6Years.csv, SOXX_5min_6Years.csv  -- 3x fund and its 1x index proxy (5-min)
  SOXL.csv                                     -- SOXL holdings sheet (swap/collateral)
  SOXL-SOXS-Fact-Sheet.pdf, SAI_Combined3XShares.pdf -- stated mechanics

Confirms: (1) SOXL = 3x SOXX daily and intraday; (2) the daily-reset volatility-decay
law (slope ~ -3); (3) the 300% exposure is built from physical stock + index swaps.
Model-free; the only assumption is that SOXX is a faithful 1x of the same index.
"""
import os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load5(f):
    d=pd.read_csv(os.path.join(ROOT,f))
    d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d
def ols(y,x):
    A=np.column_stack([np.ones(len(x)),x]); b,_,_,_=np.linalg.lstsq(A,y,rcond=None)
    r=y-A@b; r2=1-(r@r)/np.sum((y-y.mean())**2)
    s2=(r@r)/(len(y)-2); se=np.sqrt(np.diag(s2*np.linalg.inv(A.T@A))); return b,b/se,r2

def daily_3x():
    L=load5("SOXL_5min_6Years.csv").groupby("date").agg(L=("Close","last"))
    X=load5("SOXX_5min_6Years.csv").groupby("date").agg(X=("Close","last"))
    m=L.join(X,how="inner").reset_index()
    m["rL"]=np.log(m["L"]/m["L"].shift(1)); m["rX"]=np.log(m["X"]/m["X"].shift(1))
    m=m.dropna()
    split=m[(m["rL"].abs()>0.5)|(m["rX"].abs()>0.5)]
    reg=m[(m["rL"].abs()<=0.5)&(m["rX"].abs()<=0.5)]
    b,t,r2=ols(reg["rL"].values,reg["rX"].values)
    print("="*70,"\n(1) DAILY 3x: SOXL vs SOXX 1x\n","="*70,sep="")
    print(f"  split days dropped: {list(split['date'].dt.date.astype(str))}")
    print(f"  r_SOXL = {b[0]*1e4:+.2f}bp + {b[1]:.3f}*r_SOXX   R2={r2:.4f}   (target 3.000)  n={len(reg)}")
    big=reg[reg["rX"].abs()>=0.005]; ratio=big["rL"]/big["rX"]
    print(f"  realized leverage median={ratio.median():.3f} IQR=[{ratio.quantile(.25):.2f},{ratio.quantile(.75):.2f}]")
    print(f"  ann vol: SOXX={reg['rX'].std()*np.sqrt(252)*100:.0f}%  SOXL={reg['rL'].std()*np.sqrt(252)*100:.0f}%  (x{reg['rL'].std()/reg['rX'].std():.2f})")
    reg=reg.copy(); reg["yr"]=reg["date"].dt.year
    print("  per-year beta:", {int(y):round(np.polyfit(g['rX'],g['rL'],1)[0],3) for y,g in reg.groupby('yr') if len(g)>20})
    return reg

def intraday_3x():
    def bars(f,n):
        d=load5(f); d["r"]=np.log(d["Close"]/d["Close"].shift(1))
        d.loc[d.groupby("date").head(1).index,"r"]=np.nan
        return d[["ts","date","r"]].rename(columns={"r":n})
    m=bars("SOXL_5min_6Years.csv","rL").merge(bars("SOXX_5min_6Years.csv","rX"),on=["ts","date"]).dropna()
    m=m[(m["rL"].abs()<0.3)&(m["rX"].abs()<0.3)]
    b,t,r2=ols(m["rL"].values,m["rX"].values)
    print("\n"+"="*70,"\n(2) INTRADAY 3x (5-min bar-by-bar)\n","="*70,sep="")
    print(f"  r_SOXL = {b[0]*1e4:+.3f}bp + {b[1]:.3f}*r_SOXX   R2={r2:.4f}   n={len(m):,}")

def decay_law(reg):
    print("\n"+"="*70,"\n(3) DAILY-RESET VOLATILITY-DECAY LAW (non-circular)\n","="*70,sep="")
    reg=reg.reset_index(drop=True); W=[]
    for i in range(0,len(reg)-21,21):
        g=reg.iloc[i:i+21]; W.append((g["rL"].sum()-3*g["rX"].sum(), np.sum(g["rX"]**2)))
    W=pd.DataFrame(W,columns=["gap","rv"]); cf=np.polyfit(W["rv"],W["gap"],1)
    print(f"  (lnSOXL - 3*lnSOXX) = {cf[1]*1e4:+.1f}bp + {cf[0]:.2f}*RealizedVar_SOXX   over 21-day windows (n={len(W)})")
    print(f"  theory for 3x daily reset: slope = -L(L-1)/2 = -3.00  |  measured = {cf[0]:.2f}")
    print(f"  intercept -> ~{cf[1]*(252/21)*100:+.1f}%/yr structural drag (expense 0.75% + swap financing + dividends)")

def holdings():
    h=pd.read_csv(os.path.join(ROOT,"SOXL.csv"),skiprows=4)
    h["p"]=pd.to_numeric(h["HoldingsPercent"],errors="coerce")
    d=h["SecurityDescription"].astype(str).str.upper()
    has=h["StockTicker"].notna()&(h["StockTicker"].astype(str).str.strip()!="")
    swap=d.str.contains("SWAP")|d.str.contains("BULL 3X"); cash=(~has)&(~swap)
    print("\n"+"="*70,"\n(4) HOLDINGS: how the 300% is built\n","="*70,sep="")
    print(f"  physical stocks {h.loc[has,'p'].sum():.1f}% + swaps {h.loc[swap,'p'].sum():.1f}% = "
          f"{h.loc[has,'p'].sum()+h.loc[swap,'p'].sum():.1f}% exposure (target 300%) | cash collateral {h.loc[cash,'p'].sum():.1f}%")

if __name__=="__main__":
    reg=daily_3x(); intraday_3x(); decay_law(reg); holdings()
