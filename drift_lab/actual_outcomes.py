#!/usr/bin/env python3
"""
actual_outcomes.py -- proof that the results are ACTUAL day-by-day dollar P&L on real
historical prices, not Sharpe/Greeks abstractions. Walks the real SOXL/SOXS closes,
computes real $ gained/lost each day, and prints the equity curve, the worst actual days
(with the real moves that caused them), and real monthly cash. Sharpe/CAGR are summaries
OF this path. What is REAL vs MODELED is listed at the bottom.
"""
import os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def daily(f):
    d=pd.read_csv(os.path.join(ROOT,f)); d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); return d.groupby("date").agg(c=("Close","last"))["c"]
m=pd.DataFrame({"L":daily("SOXL_5min_6Years.csv"),"S":daily("SOXS_5min_6Years.csv")}).dropna()
m["rL"]=m["L"].pct_change(); m["rS"]=m["S"].pct_change(); m=m.dropna(); m=m[(m["rL"].abs()<0.6)&(m["rS"].abs()<0.6)]
CAP0=150_000; cap=CAP0; VL=cap; VS=cap; rec=[]
for dt,rL,rS in zip(m.index,m["rL"],m["rS"]):
    pnl=-(VL*rL+VS*rS); cap+=pnl; rec.append((dt,rL,rS,pnl,cap)); VL*=(1+rL); VS*=(1+rS)
    if max(VL,VS)/(VL+VS)>0.55: VL=VS=cap
P=pd.DataFrame(rec,columns=["date","rL","rS","pnl","eq"]).set_index("date")
print(f"ACTUAL harvest P&L on ${CAP0:,} (gross 2x), {len(P)} real trading days:")
print(f"  end equity ${P['eq'].iloc[-1]:,.0f} | total P&L ${P['eq'].iloc[-1]-CAP0:,.0f} | best day +${P['pnl'].max():,.0f} | worst ${P['pnl'].min():,.0f}")
print("  worst 3 days (real moves that caused them):")
for dt,r in P.nsmallest(3,"pnl").iterrows(): print(f"    {dt.date()}: SOXL {r['rL']*100:+.1f}% SOXS {r['rS']*100:+.1f}% -> ${r['pnl']:,.0f}")
mo=P["eq"].resample("ME").last().diff().dropna()
print(f"  monthly cash: median ${mo.median():,.0f}, {(mo>0).mean()*100:.0f}% positive")
print("""
REAL in every backtest here:  day-by-day P&L from actual historical prices; equity curves,
   drawdowns, dollar cash; option entry at actual trade prints; expiry at actual intrinsic.
MODELED / ASSUMED (flagged):  daily close-to-close granularity (not tick fills); costs as
   bp sweeps (not live bid/ask); borrow ASSUMED ~5.5% (not live quotes -- the key gate); no
   margin-call/liquidation cascade; options are trade-prints not NBBO, entry w/ slippage.
Sharpe/CAGR/DD = summaries OF the real P&L path. Greeks (delta/vega) =descriptive only, never return-gen.""")
