#!/usr/bin/env python3
"""report.py -- turn the full-run outputs into the answer tables."""
import os, numpy as np, pandas as pd
pd.set_option("display.width",200); pd.set_option("display.max_columns",30)
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"out")
MNY_ORDER=["ATM<2%","2-5%","5-10%","10-20%",">20%"]
DTE_ORDER=["0-1","2-3","4-7","8-14","15-30","31-60","60+"]

cov=pd.read_csv(os.path.join(OUT,"coverage_by_year_mny_dte.csv"))
ep=pd.read_parquet(os.path.join(OUT,"episodes.parquet"))
ll=pd.read_parquet(os.path.join(OUT,"leadlag_input.parquet"))

def order(df,col,o): df[col]=pd.Categorical(df[col],o,ordered=True); return df

print("="*90)
print("Q1  HOW OFTEN IS THE OPTION MARK STALE?  (bar-level, pooled 2022-2026)")
print("     pct_traded = 5-min bars with a real trade;  pct_stale_moved = bars where the last")
print("     option print is stale AND the underlying has since moved >=1% (the tradable drift)")
print("="*90)
c=cov.groupby(["mny_b","dte_b"],observed=True)[["n_bars","n_traded","n_priced","n_stale","n_stale_moved"]].sum().reset_index()
c["pct_traded"]=100*c["n_traded"]/c["n_bars"]
c["pct_stale_moved"]=100*c["n_stale_moved"]/c["n_bars"]
for metric in ["pct_traded","pct_stale_moved"]:
    piv=c.pivot(index="mny_b",columns="dte_b",values=metric).reindex(index=MNY_ORDER,columns=DTE_ORDER)
    print(f"\n--- {metric} (%)  rows=|moneyness|, cols=DTE ---")
    print(piv.round(1).to_string())

print("\n"+"="*90)
print("Q2/Q3  HOW BIG & HOW LONG IS THE DRIFT?  (episode-level; only episodes where the")
print("        underlying moved >=1% while the option print was frozen)")
print("="*90)
ep["absmny"]=ep["mny"].abs()
d=ep[ep["u_peak_exc"].abs()>=0.01].copy()
d=order(d,"mny_b",MNY_ORDER); d=order(d,"dte_b",DTE_ORDER)
def agg(g):
    return pd.Series({
        "n_episodes":len(g),
        "dur_med_min":g["dur_min"].median(),
        "dur_p90_min":g["dur_min"].quantile(.90),
        "uexc_med_%":100*g["u_peak_exc"].abs().median(),
        "uexc_p90_%":100*g["u_peak_exc"].abs().quantile(.90),
        "repmove_med_%":100*g["rep_move"].abs().median(),
        "repmove_p90_%":100*g["rep_move"].abs().quantile(.90),
    })
tab=d.groupby(["mny_b","dte_b"],observed=True).apply(agg,include_groups=False).reset_index()
for metric,lab in [("dur_med_min","MEDIAN stale DURATION (min) until reprice"),
                   ("uexc_med_%","MEDIAN underlying move while frozen (%)"),
                   ("repmove_med_%","MEDIAN option catch-up jump when it reprints (%)")]:
    piv=tab.pivot(index="mny_b",columns="dte_b",values=metric).reindex(index=MNY_ORDER,columns=DTE_ORDER)
    print(f"\n--- {lab} ---"); print(piv.round(1).to_string())

print("\n"+"="*90); print("BY YEAR / REGIME  (near-ATM |mny|<5%, underlying moved >=1%)"); print("="*90)
na=d[d["absmny"]<0.05]
yr=na.groupby("year",observed=True).apply(lambda g:pd.Series({
    "n_episodes":len(g),"dur_med_min":g["dur_min"].median(),
    "uexc_med_%":100*g["u_peak_exc"].abs().median(),
    "repmove_med_%":100*g["rep_move"].abs().median()}),include_groups=False)
print(yr.round(1).to_string())

print("\n"+"="*90); print("LEAD-LAG (co-trading consecutive 5-min bars, near-ATM): under-reaction share"); print("="*90)
def ols(y,cols):
    X=np.column_stack([np.ones(len(y))]+cols); b,_,_,_=np.linalg.lstsq(X,y,rcond=None)
    r=y-X@b; s2=(r@r)/(len(y)-X.shape[1]); se=np.sqrt(np.diag(s2*np.linalg.inv(X.T@X))); return b,b/se
for R in ["CALL","PUT"]:
    for yr_ in [None]+sorted(ll["year"].unique()):
        s=ll[(ll["right"]==R)] if yr_ is None else ll[(ll["right"]==R)&(ll["year"]==yr_)]
        s=s.dropna()
        if len(s)<100: continue
        b,t=ols(s["oret"].values,[s["uret"].values,s["ulag"].values])
        tag="ALL " if yr_ is None else str(yr_)
        print(f"{R} {tag}: n={len(s):>7,}  contemp β={b[1]:6.2f}(t={t[1]:>4.0f})  LAG β={b[2]:+6.3f}(t={t[2]:+5.1f})  lag/contemp={b[2]/b[1]:+5.1%}")

# save the two main tables
c.to_csv(os.path.join(OUT,"ANSWER_coverage_mny_dte.csv"),index=False)
tab.to_csv(os.path.join(OUT,"ANSWER_drift_size_duration_mny_dte.csv"),index=False)
print("\nsaved ANSWER_*.csv")
