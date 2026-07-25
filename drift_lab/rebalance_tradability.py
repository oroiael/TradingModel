import pandas as pd, numpy as np
def load(f):
    d=pd.read_csv(f); d["ts"]=pd.to_datetime(d["Date"].str.replace(" America/New_York","",regex=False),format="%Y%m%d %H:%M:%S")
    d["date"]=pd.to_datetime(d["ts"].dt.date); d["hm"]=d["ts"].dt.strftime("%H:%M"); return d
soxx=load("SOXX_5min_6Years.csv")
full=soxx.groupby("date").filter(lambda x:len(x)==78)
piv=full.pivot_table(index="date",columns="hm",values="Close",aggfunc="last")
op =full.pivot_table(index="date",columns="hm",values="Open",aggfunc="first")["09:30"]
d=pd.DataFrame({"op":op,"h1500":piv["15:00"],"h1530":piv["15:30"],"cl":piv["15:55"]}).dropna().sort_index()
d["next_op"]=d["op"].shift(-1)
d["r_to1530"]=np.log(d["h1530"]/d["op"])      # observable signal by 15:30
d["r_last25"]=np.log(d["cl"]/d["h1530"])       # 15:30 -> 15:55 (rebalance run-up)
d["r_overnight"]=np.log(d["next_op"]/d["cl"])  # 15:55 -> next open (impact reversal?)
d["r_day"]=np.log(d["cl"]/d["op"])
d=d.dropna()

# ---- (0) deterministic rebalance flow size ----
AUM=23.0  # $B, SOXL NAV ~ 145.9M sh * ~$158 (2026-07-23 holdings)
print("=== (0) REBALANCE FLOW IS DETERMINISTIC (known from the day's move) ===")
print(f"  3x fund must trade  L*(L-1)*AUM*r = 6*AUM*r  in index exposure at the close (buy if up, sell if down)")
for r in [0.01,0.02,0.03]:
    print(f"    index day move {r*100:.0f}% -> SOXL rebalance ~ ${6*AUM*r:.1f}B of semis into the close (+SOXS adds more, same direction)")
print(f"  timing = fixed (at/near the 16:00 close); size & sign = situational (∝ that day's move). Predictable intraday from SOXX.")

# ---- (1) does the day's move continue into the close? (rebalance momentum) ----
def reg(x,y):
    b=np.polyfit(x,y,1); c=np.corrcoef(x,y)[0,1]; return b[0],c
print("\n=== (1) EOD MOMENTUM in the INDEX (SOXX): does open->15:30 predict 15:30->close? ===")
s,c=reg(d["r_to1530"],d["r_last25"]); print(f"  all days: slope={s:+.3f} corr={c:+.3f} (n={len(d)})")
big=d[d["r_to1530"].abs()>d["r_to1530"].abs().quantile(.8)]
s,c=reg(big["r_to1530"],big["r_last25"]); print(f"  big-move days (>p80): slope={s:+.3f} corr={c:+.3f} mean r_last25={big['r_last25'].mean()*1e4:+.1f}bp (n={len(big)})")
print(f"    up-days last25 mean={d.loc[d.r_to1530>0,'r_last25'].mean()*1e4:+.1f}bp | down-days={d.loc[d.r_to1530<0,'r_last25'].mean()*1e4:+.1f}bp")

# ---- (2) does the close move REVERSE overnight? (mechanical impact => fade-able) ----
print("\n=== (2) REVERSAL: does the rebalance run-up (15:30->close) reverse overnight? ===")
s,c=reg(d["r_last25"],d["r_overnight"]); print(f"  r_last25 -> r_overnight: slope={s:+.3f} corr={c:+.3f}  (negative = reversal/impact)")
s,c=reg(d["r_day"],d["r_overnight"]); print(f"  r_day    -> r_overnight: slope={s:+.3f} corr={c:+.3f}")
# economic size of any reversal on big up-close days
buc=d[d["r_last25"]>d["r_last25"].quantile(.85)]
print(f"  after big up-closes (top15% r_last25): mean overnight={buc['r_overnight'].mean()*1e4:+.1f}bp (n={len(buc)}) vs uncond {d['r_overnight'].mean()*1e4:+.1f}bp")
bdc=d[d["r_last25"]<d["r_last25"].quantile(.15)]
print(f"  after big down-closes (bot15%): mean overnight={bdc['r_overnight'].mean()*1e4:+.1f}bp (n={len(bdc)})")
print("\n  NOTE: underlying 5-min data ends 15:55; the 16:00 closing auction (where MOC rebalancing prints) is NOT captured.")
