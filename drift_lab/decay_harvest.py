#!/usr/bin/env python3
"""
decay_harvest.py -- can you harvest SOXL's decay/financing market-neutral? Two hedges,
both on REAL data (SOXL, SOXS, SOXX 5-min -> daily close).

A) short $1 SOXL + long $3 SOXX (index hedge): gross ~8%/yr looks great, but the carry IS
   SOXL's financing, which you pay back to fund the $2 leveraged long -> NET ~breakeven.
B) short $1 SOXL + short $1 SOXS (pair): NO leveraged long to fund, so the carry survives
   -> gross ~3.3%/yr, Sharpe ~0.9, maxDD ~-2.5%, market-neutral. But it collects only the
   expense ratios + a small financing differential (SOXL pays financing, SOXS *earns* on
   cash in high-rate years, so the two nearly cancel), and it is eaten by SOXS borrow cost
   + ~5%/day rebalance turnover. Net positive only if SOXS borrow < ~2.7%/yr.

Neither captures the sigma^2 decay (daily rebalancing resets with the fund); capturing it
means NOT rebalancing, which reintroduces the naive-short blow-up (-224% 2023, -277% 2026).
"""
import os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def daily(f):
    d=pd.read_csv(os.path.join(ROOT,f))
    d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]

def frame():
    m=pd.DataFrame({"L":daily("SOXL_5min_6Years.csv"),"S":daily("SOXS_5min_6Years.csv"),
                    "X":daily("SOXX_5min_6Years.csv")}).dropna()
    for k in ["L","S","X"]: m["r"+k]=m[k].pct_change()
    m=m.dropna(); m=m[(m["rL"].abs()<0.6)&(m["rS"].abs()<0.6)&(m["rX"].abs()<0.6)]
    m["yr"]=m.index.year; return m

def report(m,pnl,label):
    eq=(1+pnl).cumprod(); dd=(eq/eq.cummax()-1).min()*100
    beta=np.polyfit(m["rX"],pnl,1)[0]
    print(f"\n=== {label} | market-neutrality beta_to_SOXX={beta:+.3f} ===")
    for y,g in pnl.groupby(m["yr"]):
        e=(1+g).cumprod(); print(f"  {y}: {g.sum()*100:+6.1f}%/yr  Sharpe {g.mean()/g.std()*np.sqrt(252):5.2f}  maxDD {(e/e.cummax()-1).min()*100:5.1f}%")
    print(f"  FULL: GROSS {pnl.sum()/(len(m)/252)*100:+.1f}%/yr  Sharpe {pnl.mean()/pnl.std()*np.sqrt(252):.2f}  maxDD {dd:.1f}%  worst day {pnl.min()*100:+.1f}%")

def main():
    m=frame()
    # A) index hedge
    report(m,-m["rL"]+3*m["rX"],"A) short $1 SOXL + long $3 SOXX (index hedge)")
    print("   -> minus your funding of the $2 leveraged long (~2x short rate) == NET ~breakeven")
    # B) SOXL/SOXS pair
    pair=-(m["rL"]+m["rS"])
    report(m,pair,"B) short $1 SOXL + short $1 SOXS (pair, no leveraged long to fund)")
    g=pair.sum()/(len(m)/252)*100
    print("   NET after borrow (SOXL ~0.5%) + SOXS borrow sweep:")
    for b in [1,3,5,10,20]: print(f"      SOXS borrow {b:2d}%/yr -> {g-0.5-b:+.1f}%/yr")
    print(f"   daily rebalance turnover ~{((m['rL']-m['rS']).abs()/2).mean()*100:.1f}% of book/day -> ETF spread/impact on top (~2%/yr)")
    print("\n   single-leg naive short SOXL (why you must neutralize):")
    for y,gg in m.groupby("yr"):
        v=(np.prod(1+gg["rL"])-1)*-100; print(f"      {y}: {v:+7.1f}%  {'BLOWN UP' if v<-80 else ''}")

if __name__=="__main__": main()
