#!/usr/bin/env python3
"""
decay_harvest.py -- can you harvest SOXL's decay/financing by shorting it market-neutral?

Tests the SOXL/SOXX version (both real): short $1 SOXL + long $3 SOXX, rebalanced daily.
Result: the ~8%/yr GROSS carry is SOXL's own financing drag, which you must PAY BACK to
fund the leveraged hedge -> net ~breakeven. The sigma^2 decay is NOT captured by daily
rebalancing; capturing it means NOT rebalancing, which reintroduces the blow-up risk of a
naive short (see single-leg). The SOXL/SOXS pair differs (no leveraged long to fund) and
needs real SOXS data to settle -- do NOT synthesize it.
"""
import os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(f):
    d=pd.read_csv(os.path.join(ROOT,f))
    d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]

def main():
    m=pd.DataFrame({"L":load("SOXL_5min_6Years.csv"),"X":load("SOXX_5min_6Years.csv")}).dropna()
    m["rL"]=m["L"].pct_change(); m["rX"]=m["X"].pct_change(); m=m.dropna()
    m=m[(m["rL"].abs()<0.6)&(m["rX"].abs()<0.6)]; m["yr"]=m.index.year
    m["pnl"]=-m["rL"]+3*m["rX"]                    # short $1 SOXL + long $3 SOXX, daily reset
    ffr={2020:0.1,2021:0.1,2022:1.9,2023:5.0,2024:5.1,2025:4.4,2026:4.3}   # ~avg fed funds (context)
    print("=== market-neutral decay/carry harvest: short $1 SOXL + long $3 SOXX (daily rebal) ===")
    print(" yr | GROSS %/yr | Sharpe | your funding(-2*rate) | -borrow | NET %/yr")
    for y,g in m.groupby("yr"):
        gross=g["pnl"].sum()*100; sh=g["pnl"].mean()/g["pnl"].std()*np.sqrt(252)
        fund=-2*ffr[y]; borrow=-0.5
        print(f" {y} | {gross:+7.1f} | {sh:5.2f} | {fund:+6.1f} | {borrow:+.1f} | {gross+fund+borrow:+6.1f}")
    print(f"\n full-sample GROSS ~{m['pnl'].sum()/(len(m)/252)*100:.1f}%/yr Sharpe {m['pnl'].mean()/m['pnl'].std()*np.sqrt(252):.2f}"
          f"  -> NET ~breakeven after funding the hedge (the carry IS the financing you also pay).")
    print("\n=== single-leg naive short SOXL (unhedged) — the blow-up you must neutralize ===")
    for y,g in m.groupby("yr"):
        v=(np.prod(1+g["rL"])-1)*-100
        print(f" {y}: short-SOXL {v:+7.1f}%  {'BLOWN UP' if v<-80 else ''}")

if __name__=="__main__": main()
