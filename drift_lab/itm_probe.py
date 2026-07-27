import sys; sys.path.insert(0,"drift_lab")
import pandas as pd, numpy as np
from drift_engine import load_underlying, all_expirations, load_exp
umap=load_underlying(); exps=all_expirations()
# use a well-covered 2024 monthly
e="20240621"; d=load_exp(e,exps[e]); d["right"]=d["right"].str.upper()
d["U"]=d["ts"].map(umap); d=d[d["U"].notna()]
d["moneyness"]=d["strike"]/d["U"]-1   # calls: <0 = ITM
# trade frequency by ITM depth for CALLS
c=d[d["right"]=="CALL"].copy()
c["depth"]=pd.cut(-c["moneyness"],[-1,-0.02,0.02,0.10,0.20,0.35,10],
                  labels=["OTM","ATM±2%","2-10% ITM","10-20% ITM","20-35% ITM","deep >35% ITM"])
g=c.groupby("depth",observed=True).apply(lambda x: pd.Series({
    "n_bars":len(x),"pct_traded":100*(x["count"]>0).mean(),
    "med_vol_when_traded":x.loc[x["count"]>0,"volume"].median()}),include_groups=False)
print("=== SOXL CALL liquidity by ITM depth (exp 2024-06-21) ===")
print(g.round(1).to_string())

# extrinsic value of deep ITM calls (option price - intrinsic): how much time premium do you pay?
tr=c[(c["count"]>0)&c["close"].notna()].copy()
tr["intrinsic"]=(tr["U"]-tr["strike"]).clip(lower=0)
tr["extrinsic"]=tr["close"]-tr["intrinsic"]
tr["dte"]=(pd.to_datetime(tr["expiration"]).dt.tz_localize(None)-tr["ts"]).dt.days
deep=tr[(-tr["moneyness"]>0.20)&(tr["dte"].between(20,45))]
atm=tr[(tr["moneyness"].abs()<0.03)&(tr["dte"].between(20,45))]
print(f"\n=== extrinsic (time premium) paid, ~20-45 DTE ===")
print(f"  deep ITM (>20% ITM): median extrinsic ${deep['extrinsic'].median():.2f}  = {deep['extrinsic'].median()/deep['U'].median()*100:.1f}% of spot ; delta~1, ~0 vega")
print(f"  ATM:                 median extrinsic ${atm['extrinsic'].median():.2f}  = {atm['extrinsic'].median()/atm['U'].median()*100:.1f}% of spot  (the IV-rich premium)")
print(f"\n  deep-ITM trades in only ~{g.loc['20-35% ITM','pct_traded'] if '20-35% ITM' in g.index else 0:.0f}% of 5-min bars vs ATM ~{g.loc['ATM±2%','pct_traded']:.0f}% -> execution problem")
