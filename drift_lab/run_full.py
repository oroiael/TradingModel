#!/usr/bin/env python3
"""
run_full.py -- run the drift engine over EVERY available expiration and write the
summary tables that answer: how often / how big / how long is stale-mark drift,
by moneyness x DTE x year x expiration, plus the lead-lag (under-reaction) test.
Memory-safe: processes one expiration at a time; keeps only episodes (downcast) and
pre-binned bar counts.
"""
import os, sys, time, glob
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drift_engine import load_underlying, all_expirations, load_exp, contract_runs, COLS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

MNY_BINS=[0,0.02,0.05,0.10,0.20,10]; MNY_LAB=["ATM<2%","2-5%","5-10%","10-20%",">20%"]
DTE_BINS=[-1,1,3,7,14,30,60,999]; DTE_LAB=["0-1","2-3","4-7","8-14","15-30","31-60","60+"]
MOVE_THRESH=0.01   # "underlying moved" = >=1%

def mny_bucket(a): return pd.cut(a, MNY_BINS, labels=MNY_LAB)
def dte_bucket(a): return pd.cut(a, DTE_BINS, labels=DTE_LAB)

def process():
    umap=load_underlying()
    exps=all_expirations()
    keys=sorted(exps.keys())
    print(f"expirations with real files present: {len(keys)}")
    ep_frames=[]; cov_frames=[]; ll_frames=[]; per_exp=[]
    t0=time.time()
    for i,exp in enumerate(keys):
        try:
            d=load_exp(exp, exps[exp])
        except Exception as e:
            print(f"  !! {exp} load failed: {e}"); continue
        d["U"]=d["ts"].map(umap)
        d=d[d["U"].notna() & (d["U"]>0)].copy()
        if d.empty: continue
        d["dte"]=(d["exp_date"]-d["ts"]).dt.days
        d["absmny"]=(d["strike"]/d["U"]-1).abs()
        d["year"]=pd.to_datetime(d["exp_date"]).dt.year
        # ---- episodes ----
        rows=[]
        for _,g in d.groupby(["strike","right"], sort=False):
            rows.extend(contract_runs(g, g["U"].values))
        ep=pd.DataFrame(rows, columns=COLS)
        if len(ep):
            ep["exp"]=exp; ep["year"]=pd.to_datetime(ep["anchor"]).dt.year
            for c in ["mny","u_net","u_peak_exc","rep_move","U0","U1","C0","C1"]:
                ep[c]=ep[c].astype("float32")
            for c in ["dte","dur_bars","dur_min"]:
                ep[c]=ep[c].astype("int32")
            ep_frames.append(ep.drop(columns=["anchor"]).assign(
                mny_b=mny_bucket(ep["mny"].abs()).astype(str),
                dte_b=dte_bucket(ep["dte"]).astype(str)))
        # ---- bar-level coverage / staleness-while-moved ----
        d=d.sort_values(["strike","right","ts"])
        d["priced"]=d["px"].notna()
        # last priced px & underlying per contract (carry forward)
        grp=d.groupby(["strike","right"], sort=False)
        d["last_px"]=grp["px"].ffill()
        # underlying level at the last priced bar, carried forward
        d["U_at_priced"]=d["U"].where(d["priced"])
        d["U_at_priced"]=grp["U_at_priced"].ffill()
        d["stale"]=(~d["priced"]) & d["last_px"].notna()
        d["u_since"]=(d["U"]/d["U_at_priced"]-1).abs()
        d["stale_moved"]=d["stale"] & (d["u_since"]>=MOVE_THRESH)
        d["mny_b"]=mny_bucket(d["absmny"]).astype(str); d["dte_b"]=dte_bucket(d["dte"]).astype(str)
        cov=d.groupby(["year","mny_b","dte_b"], observed=True).agg(
            n_bars=("ts","size"), n_traded=("traded","sum"),
            n_priced=("priced","sum"), n_stale=("stale","sum"),
            n_stale_moved=("stale_moved","sum")).reset_index()
        cov_frames.append(cov)
        # ---- lead-lag inputs (near-ATM co-trading consecutive priced 5-min bars) ----
        near=d[d["absmny"]<0.05].copy()
        g2=near.groupby(["strike","right"])
        near["pxprev"]=g2["px"].shift(1); near["Uprev"]=g2["U"].shift(1)
        near["tprev"]=g2["ts"].shift(1); near["dprev"]=g2["date"].shift(1); near["Uprev2"]=g2["U"].shift(2)
        m=near[near["px"].notna()&near["pxprev"].notna()&(near["date"]==near["dprev"])&
               ((near["ts"]-near["tprev"]).dt.total_seconds()==300)].copy()
        if len(m):
            m["oret"]=np.log(m["px"]/m["pxprev"]); m["uret"]=np.log(m["U"]/m["Uprev"]); m["ulag"]=np.log(m["Uprev"]/m["Uprev2"])
            ll_frames.append(m[["year","right","oret","uret","ulag"]].replace([np.inf,-np.inf],np.nan).dropna())
        # ---- per-expiration summary ----
        eb=ep[ep["mny"].abs()<0.05] if len(ep) else ep
        per_exp.append(dict(exp=exp, year=int(d["year"].iloc[0]),
            n_bars=int(len(d)), pct_priced=float(d["priced"].mean()*100),
            n_episodes=int(len(ep)), n_drift_moved=int((ep["u_peak_exc"].abs()>=MOVE_THRESH).sum()) if len(ep) else 0,
            atm_pct_stale_moved=float(d.loc[d["absmny"]<0.05,"stale_moved"].mean()*100) if (d["absmny"]<0.05).any() else np.nan))
        if (i+1)%50==0:
            print(f"  {i+1}/{len(keys)} exps  ({time.time()-t0:.0f}s)  episodes so far ~{sum(len(x) for x in ep_frames):,}")
    # ---- write ----
    EP=pd.concat(ep_frames, ignore_index=True); EP.to_parquet(os.path.join(OUT,"episodes.parquet"))
    COV=pd.concat(cov_frames, ignore_index=True).groupby(["year","mny_b","dte_b"],observed=True).sum().reset_index()
    COV.to_csv(os.path.join(OUT,"coverage_by_year_mny_dte.csv"), index=False)
    LL=pd.concat(ll_frames, ignore_index=True); LL.to_parquet(os.path.join(OUT,"leadlag_input.parquet"))
    pd.DataFrame(per_exp).to_csv(os.path.join(OUT,"per_expiration.csv"), index=False)
    print(f"\nDONE in {time.time()-t0:.0f}s | episodes={len(EP):,} | coverage rows={len(COV)} | leadlag rows={len(LL):,}")
    print(f"written to {OUT}")

if __name__=="__main__":
    process()
