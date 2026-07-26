#!/usr/bin/env python3
"""
option_harvest.py -- compare three ways to harvest SOXL/SOXS volatility, same axis,
same window (2022-2026, the intraday-option span). Real option TRADE prices for entry;
expiry settled at intrinsic vs the underlying close (minimizes option-data dependence).
Sell 5% below the print (trade-not-quote haircut); no borrow/commissions.

  1) bare drift-band pair (short SOXL+SOXS, ~55% band)   -- the ETF construction
  2) call-capped pair (pair + long OTM SOXL call overlay) -- protection is too dear
  3) naked weekly short strangle on SOXL                  -- selling premium fails

Verdict: the delta-neutral, band-rebalanced ETF pair wins. SOXL's ~100% IV makes selling
premium a -50%/yr, -95%-DD disaster (despite 60%+ winning weeks) and makes protective
calls cost ~30-40%/yr; the band already caps the pair's realized tail.
"""
import sys, os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import pandas as pd, numpy as np
from drift_engine import load_underlying, all_expirations, load_exp
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
umap=load_underlying(); exps=all_expirations()
def u_at(ts):
    try: return umap.loc[ts]
    except KeyError: return np.nan
def opt_px(d,strike,right,day,hhmm="10:00"):
    sub=d[(d["strike"]==strike)&(d["right"]==right)&(d["date"]==day)]
    if sub.empty: return np.nan
    tr=sub[(sub["count"]>0)&(sub["ts"]>=pd.Timestamp(f"{day} {hhmm}"))].sort_values("ts")
    if tr.empty: tr=sub[sub["count"]>0].sort_values("ts")
    if tr.empty: return np.nan
    r=tr.iloc[0]; return r["close"] if pd.notna(r["close"]) else (r["vwap"] if r["vwap"]>0 else np.nan)
def daily(f):
    x=pd.read_csv(os.path.join(ROOT,f)); x["ts"]=pd.to_datetime(x["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    x["date"]=pd.to_datetime(x["ts"].dt.date); return x.groupby("date").agg(c=("Close","last"))["c"]

def pair_daily(band=0.55,w=1.0,start='2022-01-01'):
    m=pd.DataFrame({"L":daily("SOXL_5min_6Years.csv"),"S":daily("SOXS_5min_6Years.csv")}).dropna()
    m["rL"]=m["L"].pct_change(); m["rS"]=m["S"].pct_change(); m=m.dropna()
    m=m[(m["rL"].abs()<0.6)&(m["rS"].abs()<0.6)]; m=m[m.index>=start]
    rL,rS,idx=m["rL"].values,m["rS"].values,m.index; cap=1.0;VL=w;VS=w;eq=np.empty(len(rL))
    for t in range(len(rL)):
        cap-=VL*rL[t]+VS*rS[t]
        if cap<=0: eq[t:]=0;break
        VL*=(1+rL[t]);VS*=(1+rS[t])
        if max(VL,VS)/(VL+VS)>band: VL=VS=w*cap
        eq[t]=cap
    return pd.Series(eq,index=idx)

def strangle(dist=0.05,slip=0.05):
    rows=[]
    for e in sorted(x for x in exps if pd.Timestamp(x).dayofweek==4):
        try: d=load_exp(e,exps[e])
        except: continue
        d["right"]=d["right"].str.upper(); ed=pd.Timestamp(e)
        S=np.nan
        for b in (4,3,2):
            mon=(ed-pd.Timedelta(days=b)).date(); S=u_at(pd.Timestamp(f"{mon} 10:00"))
            if np.isfinite(S): break
        if not np.isfinite(S): continue
        Kc=float(np.ceil(S*(1+dist))); Kp=float(np.floor(S*(1-dist)))
        c=opt_px(d,Kc,"CALL",mon); p=opt_px(d,Kp,"PUT",mon); Se=u_at(pd.Timestamp(f"{ed.date()} 15:55"))
        if not (np.isfinite(c) and np.isfinite(p) and np.isfinite(Se)): continue
        rows.append(dict(dt=ed,ret=((c+p)*(1-slip)-(max(0,Se-Kc)+max(0,Kp-Se)))/S))
    return pd.DataFrame(rows).set_index("dt")["ret"]

def call_overlay(otm=0.25):
    rows=[]
    for e in sorted(x for x in exps if pd.Timestamp(x).dayofweek==4 and 15<=pd.Timestamp(x).day<=21):
        try: d=load_exp(e,exps[e])
        except: continue
        d["right"]=d["right"].str.upper(); ed=pd.Timestamp(e); S=np.nan
        for b in range(28,36):
            ent=(ed-pd.Timedelta(days=b)).date(); S=u_at(pd.Timestamp(f"{ent} 10:00"))
            if np.isfinite(S): break
        if not np.isfinite(S): continue
        K=float(np.ceil(S*(1+otm))); px=opt_px(d,K,"CALL",ent); Se=u_at(pd.Timestamp(f"{ed.date()} 15:55"))
        if not (np.isfinite(px) and np.isfinite(Se)): continue
        rows.append(dict(m=pd.Timestamp(ed).to_period("M"), ovl=(max(0,Se-K)-px*1.05)/S))
    return pd.DataFrame(rows).set_index("m")["ovl"]

def stats(mo,lab,per=12):
    e=(1+mo).cumprod(); yrs=len(mo)/per
    print(f"  {lab:36s} CAGR {(e.iloc[-1]**(1/yrs)-1)*100:+6.1f}%  Sharpe {mo.mean()/mo.std()*np.sqrt(per):5.2f}  maxDD {(e/e.cummax()-1).min()*100:6.1f}%  win {100*(mo>0).mean():3.0f}%")

if __name__=="__main__":
    pm=pair_daily().resample("ME").last().pct_change().dropna(); pm.index=pm.index.to_period("M")
    print("=== THREE WAYS TO HARVEST SOXL/SOXS VOL (2022-2026, same capital axis) ===")
    stats(pm,"1) bare drift-band pair (gross 2x)")
    ov=call_overlay(0.25); stats(pm.add(ov,fill_value=0).dropna(),"2) call-capped pair (25% OTM, 1x)")
    st=strangle(0.05); stats(st,"3) naked weekly short strangle (5% OTM)",per=52)
    print("\n  (1) wins: the band already caps the tail; selling premium is a disaster on ~100%-IV SOXL;")
    print("      protective calls cost ~30-40%/yr. Options don't improve the ETF-pair harvest.")
