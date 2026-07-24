#!/usr/bin/env python3
"""
drift_engine.py -- model-free measurement of "stale-mark drift" in SOXL 5-min
option TRADE data vs the 5-min underlying.

DATA SEMANTICS (verified in data_notes; do not change without re-checking):
  * Option files raw_data/SOXL_intraday_5m_exp_<EXP>_<YYYY>_<SEG>.csv are Polygon
    5-min TRADE aggregates: open,high,low,close,volume,count,vwap. NOT bid/ask.
  * count>0  <=>  volume>0  : a trade printed in that 5-min bar (the trade flag).
  * close is the bar's last trade; present on 95.8% of trade bars; OHLC internally
    consistent (low<=open,close<=high) 100%.
  * vwap is CARRIED FORWARD verbatim on no-trade bars and is UNRELIABLE on thin
    (count 1-2) bars (outside the bar's own [low,high] ~80% of the time).
    -> We DO NOT use vwap for price. A usable fresh price exists iff close is present.
  * Grid: 79 bars/day 09:30..16:00 ET. Underlying has 78 (09:30..15:55); we map the
    option 16:00 bar to the 15:55 underlying close.

DEFINITION (pure data, no option-pricing model):
  For each (expiration, strike, right), on the series of PRICED bars (close present):
  a "stale-mark drift run" is the interval between two consecutive priced bars i->j
  WITHIN ONE SESSION with j>i+1 (>=1 bar with no fresh option price in between).
    dur_min      = 5*(j-i-1)               minutes the last option print stayed stale
    U0,U1        = underlying close at i, j
    u_net        = U1/U0-1                  underlying move over the frozen interval
    u_peak_exc   = max|U/U0-1| over [i..j]  largest gap opened while frozen
    C0,C1        = option close at i, j
    rep_move     = C1/C0-1                  the catch-up jump when it finally reprints
  A drift EPISODE (the tradable kind) = a run where the underlying actually moved
  (|u_peak_exc| >= a threshold, default 1%).

CAVEAT (stated in findings): these are TRADES, not quotes. "Stale" = last TRADE is
old; a market-maker QUOTE may have moved. Quote-level repricing latency needs NBBO
data (absent here). 5-min bars also floor the resolution.
"""
from __future__ import annotations
import glob, os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW  = os.path.join(ROOT, "raw_data")
UND  = os.path.join(ROOT, "SOXL_5min_6Years.csv")

def load_underlying():
    u = pd.read_csv(UND)
    u["ts"] = pd.to_datetime(u["Date"].str.replace(" America/New_York","",regex=False),
                             format="%Y%m%d %H:%M:%S")
    u["date"] = u["ts"].dt.date
    # synthetic 16:00 = same-day 15:55 close so option 16:00 bars join
    l = u[u["ts"].dt.strftime("%H:%M")=="15:55"].copy()
    l["ts"] = l["ts"] + pd.Timedelta(minutes=5)
    uu = pd.concat([u[["ts","Close"]], l[["ts","Close"]]], ignore_index=True)
    return uu.set_index("ts")["Close"].sort_index()

def exp_files(exp): return sorted(glob.glob(os.path.join(RAW, f"SOXL_intraday_5m_exp_{exp}_*.csv")))

def all_expirations():
    exps={}
    for p in glob.glob(os.path.join(RAW,"SOXL_intraday_5m_exp_*.csv")):
        if os.path.getsize(p) < 10_000: continue          # skip LFS pointers
        exp = os.path.basename(p).split("_")[4]
        exps.setdefault(exp,[]).append(p)
    return exps

def load_exp(exp, files=None):
    files = files or exp_files(exp)
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    d["ts"]  = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    d["right"]= d["right"].str.upper().str.strip()
    d["date"]= d["ts"].dt.date
    d["exp_date"] = pd.to_datetime(d["expiration"]).dt.tz_localize(None)
    # price ONLY where close present (vwap deliberately unused)
    d["px"]  = pd.to_numeric(d["close"], errors="coerce")
    d["traded"] = pd.to_numeric(d["count"], errors="coerce").fillna(0) > 0
    return d.sort_values(["strike","right","ts"]).reset_index(drop=True)

def contract_runs(g, U):
    """g: one (strike,right) sorted by ts. U: aligned underlying array. Yields episode dicts."""
    px = g["px"].values; dates = g["date"].values; ts = g["ts"].values
    K = g["strike"].iloc[0]; R = g["right"].iloc[0]; exp = g["exp_date"].iloc[0]
    priced = np.where(np.isfinite(px))[0]                 # bars with a real close
    out=[]
    for a,b in zip(priced[:-1], priced[1:]):
        if b<=a+1: continue
        if dates[a]!=dates[b]: continue                   # intraday only
        U0,U1,C0,C1 = U[a],U[b],px[a],px[b]
        if not (np.isfinite(U0) and np.isfinite(U1) and U0>0 and C0>0): continue
        seg = U[a:b+1]; peak = np.nanmax(np.abs(seg/U0-1.0))
        out.append((K,R,int((exp-pd.Timestamp(ts[a])).days), K/U0-1.0,
                    pd.Timestamp(ts[a]), int(b-a-1), int((b-a-1)*5),
                    U0,U1,U1/U0-1.0,peak,C0,C1,C1/C0-1.0))
    return out

COLS=["strike","right","dte","mny","anchor","dur_bars","dur_min","U0","U1",
      "u_net","u_peak_exc","C0","C1","rep_move"]

def episodes_for_exp(exp, umap, files=None):
    d = load_exp(exp, files)
    d["U"] = d["ts"].map(umap)
    rows=[]
    for _,g in d.groupby(["strike","right"], sort=False):
        rows.extend(contract_runs(g, g["U"].values))
    ep = pd.DataFrame(rows, columns=COLS)
    ep["exp"]=exp
    return ep, d

def bar_stats_for_exp(d):
    """bar-level coverage: trade freq & priced freq by moneyness x DTE (for 'how often')."""
    x = d[d["U"].notna()].copy()
    x["dte"] = (x["exp_date"] - x["ts"]).dt.days
    x["absmny"] = (x["strike"]/x["U"]-1).abs()
    return x

if __name__=="__main__":
    import sys
    umap=load_underlying()
    exp=sys.argv[1] if len(sys.argv)>1 else "20240628"
    ep,d=episodes_for_exp(exp,umap)
    print(f"exp {exp}: {len(ep):,} intraday stale-mark runs")
