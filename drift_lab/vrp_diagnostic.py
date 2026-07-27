import sys; sys.path.insert(0,"drift_lab")
import pandas as pd, numpy as np
from drift_engine import load_underlying, all_expirations, load_exp
umap=load_underlying(); exps=all_expirations()
def u_at(ts):
    try: return umap.loc[ts]
    except KeyError: return np.nan
def opx(d,K,r,day):
    sub=d[(d["strike"]==K)&(d["right"]==r)&(d["date"]==day)]
    tr=sub[(sub["count"]>0)&(sub["ts"]>=pd.Timestamp(f"{day} 10:00"))].sort_values("ts")
    if tr.empty: tr=sub[sub["count"]>0].sort_values("ts")
    if tr.empty: return np.nan
    x=tr.iloc[0]; return x["close"] if pd.notna(x["close"]) else (x["vwap"] if x["vwap"]>0 else np.nan)
rows=[]
for e in sorted(x for x in exps if pd.Timestamp(x).dayofweek==4):   # weekly Fridays
    try: d=load_exp(e,exps[e])
    except: continue
    d["right"]=d["right"].str.upper(); ed=pd.Timestamp(e); S=np.nan
    for b in (4,3,2):
        mon=(ed-pd.Timedelta(days=b)).date(); S=u_at(pd.Timestamp(f"{mon} 10:00"))
        if np.isfinite(S): break
    if not np.isfinite(S): continue
    K=float(round(S))                                  # ATM
    c=opx(d,K,"CALL",mon); p=opx(d,K,"PUT",mon); Se=u_at(pd.Timestamp(f"{ed.date()} 15:55"))
    if not (np.isfinite(c) and np.isfinite(p) and np.isfinite(Se)): continue
    dte=(ed.date()-mon).days
    implied=(c+p)/S                                    # straddle price = implied move over the week
    realized=abs(Se-S)/S                               # actual move
    rows.append(dict(dte=dte,implied=implied,realized=realized, straddle_pnl=(c+p)-abs(Se-K)))
V=pd.DataFrame(rows)
print(f"=== SOXL weekly ATM straddle: IMPLIED vs REALIZED move (n={len(V)} weeks) ===")
print(f"  mean implied move: {V['implied'].mean()*100:.1f}% of spot | mean realized: {V['realized'].mean()*100:.1f}%")
print(f"  implied/realized ratio (variance risk premium): {V['implied'].mean()/V['realized'].mean():.2f}  (>1 => selling vol pays on avg)")
print(f"  median: implied {V['implied'].median()*100:.1f}% vs realized {V['realized'].median()*100:.1f}%")
# delta-neutral straddle P&L (sell ATM straddle, ignore drift ~ delta-hedged approx): premium - |move payoff|
print(f"  short-ATM-straddle raw P&L (proxy for delta-hedged VRP): mean {V['straddle_pnl'].mean():+.3f}/sh  win {100*(V['straddle_pnl']>0).mean():.0f}%")
print(f"    as %/wk on spot: mean {(V['straddle_pnl']/ (V['implied']*0+1)).mean():+.3f}  (need proper daily hedge to isolate VRP)")
# ann implied vol from weekly straddle vs realized
V["iv_ann"]=V["implied"]/0.8*np.sqrt(52)              # rough: straddle~0.8*sigma*sqrt(T)
print(f"  implied ann vol ~{V['iv_ann'].mean()*100:.0f}% vs SOXL realized ann vol ~111%")
