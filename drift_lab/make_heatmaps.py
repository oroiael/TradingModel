#!/usr/bin/env python3
"""3-panel heatmap: how OFTEN / how LONG / how BIG is stale-mark drift, by |moneyness| x DTE."""
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"out")
MNY=["ATM<2%","2-5%","5-10%","10-20%",">20%"]; DTE=["0-1","2-3","4-7","8-14","15-30","31-60","60+"]

cov=pd.read_csv(os.path.join(OUT,"ANSWER_coverage_mny_dte.csv"))
cov["pct_stale_moved"]=100*cov["n_stale_moved"]/cov["n_bars"]
tab=pd.read_csv(os.path.join(OUT,"ANSWER_drift_size_duration_mny_dte.csv"))

def piv(df,val): return df.pivot(index="mny_b",columns="dte_b",values=val).reindex(index=MNY,columns=DTE)
P1=piv(cov,"pct_stale_moved"); P2=piv(tab,"dur_med_min"); P3=piv(tab,"repmove_med_%")

panels=[(P1,"How OFTEN the mark is stale-while-underlying-moved\n(% of 5-min bars, |move|≥1%)","Blues","%.0f"),
        (P2,"How LONG until it reprices\n(median stale duration, minutes)","Greens","%.0f"),
        (P3,"How BIG the catch-up\n(median option jump on reprint, %)","Oranges","%.0f")]
fig,axes=plt.subplots(1,3,figsize=(19,4.6))
for ax,(P,title,cmap,fmt) in zip(axes,panels):
    im=ax.imshow(P.values,cmap=cmap,aspect="auto")
    ax.set_xticks(range(len(DTE))); ax.set_xticklabels(DTE,fontsize=9)
    ax.set_yticks(range(len(MNY))); ax.set_yticklabels(MNY,fontsize=9)
    ax.set_xlabel("days to expiry (DTE)",fontsize=9); ax.set_ylabel("|strike − spot| / spot",fontsize=9)
    ax.set_title(title,fontsize=10.5,pad=8)
    vmax=np.nanmax(P.values)
    for i in range(P.shape[0]):
        for j in range(P.shape[1]):
            v=P.values[i,j]
            if np.isfinite(v):
                ax.text(j,i,fmt%v,ha="center",va="center",fontsize=8.5,
                        color="white" if v>0.62*vmax else "#222")
    cb=fig.colorbar(im,ax=ax,fraction=0.046,pad=0.03); cb.ax.tick_params(labelsize=8)
fig.suptitle("SOXL 5-min options — stale-mark drift vs the underlying (2022–2026, 3.3M episodes, all strikes/expirations)",
             fontsize=12.5,y=1.06,fontweight="bold")
fig.text(0.5,-0.04,"Drift is structural: near-expiry near-money options reprice almost every bar (little drift); "
         "far-dated / far-OTM strikes sit stale for 30–40 min while the underlying moves. Model-free (trade prints, count-based).",
         ha="center",fontsize=8.6,style="italic",color="#555")
plt.tight_layout()
plt.savefig(os.path.join(OUT,"drift_heatmaps.png"),dpi=140,bbox_inches="tight",facecolor="white")
print("wrote",os.path.join(OUT,"drift_heatmaps.png"))
