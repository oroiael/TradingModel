#!/usr/bin/env python3
"""
verify_data.py -- reproduces every data-quality claim in DATA_NOTES.md from the raw
files. Run: python3 drift_lab/verify_data.py   (git lfs pull the files first).
"""
import os, glob, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drift_engine import load_underlying, all_expirations, load_exp, ROOT

def check_underlying():
    print("="*70, "\nUNDERLYING  SOXL_5min_6Years.csv\n", "="*70, sep="")
    u = pd.read_csv(os.path.join(ROOT,"SOXL_5min_6Years.csv"))
    u["ts"]=pd.to_datetime(u["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    u["date"]=u["ts"].dt.date
    print(f"bars={len(u):,}  sessions={u['date'].nunique():,}  range {u['ts'].min()} .. {u['ts'].max()}")
    bpd=u.groupby("date").size()
    print(f"bars/session: {bpd.value_counts().to_dict()}  (78=full, 42=half-day)")
    print(f"NaNs in OHLCV: {int(u[['Open','High','Low','Close','Volume']].isna().sum().sum())}  "
          f"non-positive close: {int((u['Close']<=0).sum())}  zero-vol bars: {int((u['Volume']<=0).sum())}")
    d=u.groupby("date").agg(o=("Open","first"),c=("Close","last")).reset_index()
    d["on"]=d["o"]/d["c"].shift(1)
    sp=d[(d["on"]>1.8)|(d["on"]<0.6)].dropna()
    print(f"split/huge-gap events (overnight ratio outside 0.6..1.8): "
          f"{[(str(r.date),round(r.on,3)) for r in sp.itertuples()]}")

def check_options():
    print("\n"+"="*70,"\nOPTIONS  raw_data/SOXL_intraday_5m_exp_*.csv\n","="*70,sep="")
    exps=all_expirations()
    print(f"files present(>10KB)={sum(len(v) for v in exps.values()):,}  distinct expirations={len(exps)}")
    yrs={}
    for e in exps: yrs[e[:4]]=yrs.get(e[:4],0)+1
    print(f"expirations/year: {dict(sorted(yrs.items()))}")
    # deep field checks on one representative expiration
    exp="20240628"; d=load_exp(exp,exps[exp])
    tf=(d["count"]>0); vf=(d["volume"]>0)
    print(f"\n[{exp}] rows={len(d):,}  count>0 == volume>0 : {(tf==vf).all()}")
    print(f"  bars/session(distinct times): {sorted(d.groupby('date')['ts'].apply(lambda s:s.dt.strftime('%H:%M').nunique()).unique())}")
    tr=d[tf]
    print(f"  close present on trade bars: {tr['close'].notna().mean()*100:.1f}%")
    oh=d[d["close"].notna()]
    lo_ok=(oh["low"]-1e-9<=oh[["open","close"]].min(axis=1))
    hi_ok=(oh[["open","close"]].max(axis=1)<=oh["high"]+1e-9)
    print(f"  OHLC internal consistency (low<=open,close<=high): {((lo_ok&hi_ok).mean())*100:.1f}%")
    d=d.sort_values(['strike','right','ts'])
    d['pv']=d.groupby(['strike','right'])['vwap'].shift(1)
    nt=d[(~tf)&(d['vwap']>0)&d['pv'].notna()]
    print(f"  vwap carried-forward on no-trade bars (vwap==prev): {(np.abs(nt['vwap']-nt['pv'])<1e-9).mean()*100:.1f}%")
    inr=((tr['vwap']>=tr['low']-1e-6)&(tr['vwap']<=tr['high']+1e-6))
    print(f"  vwap within bar [low,high] on trade bars: {inr.mean()*100:.1f}%  <-- why we use close, not vwap")

def check_join_and_alignment():
    print("\n"+"="*70,"\nJOIN & STRIKE/UNDERLYING ALIGNMENT\n","="*70,sep="")
    umap=load_underlying(); exps=all_expirations()
    # raw underlying (no synthetic 16:00) to demonstrate the only mismatch
    uraw=pd.read_csv(os.path.join(ROOT,"SOXL_5min_6Years.csv"))
    uraw_ts=set(pd.to_datetime(uraw["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S"))
    for exp in ["20220624","20240628","20260626"]:
        d=load_exp(exp,exps[exp])
        raw_miss=pd.Series([t for t in d["ts"].unique() if t not in uraw_ts])
        tob=pd.to_datetime(raw_miss).dt.strftime("%H:%M").value_counts().to_dict() if len(raw_miss) else {}
        d["U"]=d["ts"].map(umap)                       # augmented map (16:00 -> 15:55)
        tr=d[(d["count"]>0)&d["U"].notna()]
        atm=(tr["strike"]-tr["U"]).abs().min()
        print(f"[{exp}] underlying {d['U'].min():.1f}..{d['U'].max():.1f} | strikes {d['strike'].min():.1f}..{d['strike'].max():.1f}"
              f" | raw-unmatched option ts={tob} (mapped to 15:55) | post-map unmatched={int(d['U'].isna().sum())} | min|K-S| traded={atm:.2f}")

if __name__=="__main__":
    check_underlying(); check_options(); check_join_and_alignment()
    print("\nAll data-quality claims in DATA_NOTES.md reproduced above.")
