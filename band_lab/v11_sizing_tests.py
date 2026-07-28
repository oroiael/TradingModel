"""
V11 sizing test program — execution (see V11_SIZING_TESTS.md for the spec).
Order: T4 sequencing -> T1 fraction sweep -> T3 vol-target -> T6 soft gate
-> T2 risk-normalized -> T5 bootstrap Kelly + stress.

Locked core config throughout: dip 1%, target 1%, stop 4% (except T2),
start 10:30, cap 5, orq5 filter, ATR5>=6 gate (except T6).
All rules/parameters were prespecified in the plan doc before running.

Outputs: band_lab/out/v11_*.csv + printed report.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars

OUT = os.path.join(HERE, "out")
rng = np.random.default_rng(7)

def sim_day_trades(o, h, l, c, start_i, d, t, s, max_trades=5):
    """Per-trade records: seq, ret, outcome in {'stop','target','eod'}."""
    trades = []
    roll_hi = h[:start_i].max() if start_i > 0 else h[0]
    state = 0; entry = 0.0
    for i in range(start_i, len(c)):
        roll_hi = max(roll_hi, h[i])
        if state == 0 and len(trades) < max_trades:
            trig = roll_hi * (1 - d)
            if l[i] <= trig:
                entry = min(trig, o[i]); state = 1
        if state == 1:
            tgt = entry * (1 + t); stp = entry * (1 - s)
            if l[i] <= stp:
                r = -s if o[i] > stp else o[i] / entry - 1
                trades.append({"seq": len(trades) + 1, "ret": r, "outcome": "stop"})
                state = 0
            elif h[i] >= tgt:
                r = t if o[i] < tgt else o[i] / entry - 1
                trades.append({"seq": len(trades) + 1, "ret": r, "outcome": "target"})
                state = 0
    if state == 1:
        trades.append({"seq": len(trades) + 1, "ret": c[-1] / entry - 1,
                       "outcome": "eod"})
    return trades

def metrics(day_ret, label):
    eq = (1 + day_ret).cumprod()
    yrs = len(day_ret) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else 0
    dd = ((eq - eq.cummax()) / eq.cummax()).min()
    sh = day_ret.mean() / day_ret.std() * np.sqrt(252) if day_ret.std() > 0 else 0
    return {"variant": label, "bp_day": round(day_ret.mean() * 1e4, 1),
            "cagr_pct": round(cagr * 100, 1), "max_dd_pct": round(dd * 100, 1),
            "worst_day_pct": round(day_ret.min() * 100, 1),
            "sharpe": round(sh, 2)}

def byyear(day_ret):
    return {y: round(v * 1e4, 1) for y, v in
            day_ret.groupby(day_ret.index.year).mean().items()}

def main():
    bars = load_bars()
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    daily["atr5"] = daily["range_pct"].rolling(5).mean().shift()
    or30 = {d: (gb["High"].to_numpy()[:6].max() - gb["Low"].to_numpy()[:6].min())
               / gb["Open"].iloc[0] * 100 for d, gb in g}
    daily["or30"] = pd.Series(or30)
    orq5_ok = daily["or30"] < daily["or30"].quantile(.8)

    # per-trade logs for stop in {2,3,4}% on ALL orq5-pass days (T6 needs
    # sub-6 ATR days; T2 needs the stop variants)
    logs = {}
    for s_ in (.02, .03, .04):
        recs = []
        for dd, gb in g:
            if not orq5_ok.get(dd, False):
                continue
            o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
            if len(c) < 14:
                continue
            for tr in sim_day_trades(o, h, l, c, 12, .01, .01, s_):
                recs.append({"date": dd, **tr})
        logs[s_] = pd.DataFrame(recs)
    log4 = logs[.04]
    gated = daily.index[(daily["atr5"] >= 6) & orq5_ok]
    t4 = log4[log4["date"].isin(gated)]
    all_days = pd.Index(sorted(t4["date"].unique()))
    base = t4.groupby("date")["ret"].sum().reindex(all_days).fillna(0)
    results = []

    # ================= T4: sequencing rules =================
    print("=" * 70); print("T4. INTRADAY SEQUENCING"); print("=" * 70)
    print("edge by trade number (bp, gated days):")
    print((t4.groupby("seq")["ret"].agg(["mean", "count"])
           .assign(mean=lambda x: (x["mean"] * 1e4).round(1))).to_string())
    # conditional recovery after k-th stop
    for k in (1, 2):
        forf = []
        for dd, gtr in t4.groupby("date"):
            stops = np.cumsum(gtr["outcome"].to_numpy() == "stop")
            after = gtr["ret"].to_numpy()[stops >= k]
            # trades strictly after the k-th stop completes:
            idx = np.argmax(stops >= k) if (stops >= k).any() else None
            if idx is not None and (stops >= k).any():
                forf.append(gtr["ret"].to_numpy()[idx + 1:].sum())
        forf = pd.Series(forf)
        print(f"\nafter {k} stop-out(s) ({len(forf)} days): E[rest-of-day] "
              f"{forf.mean()*1e4:+.1f} bp, median {forf.median()*1e4:+.1f} bp, "
              f"positive {((forf>0).mean()*100):.0f}%")

    def day_pnl_rule(gtr, rule):
        f = 1.0; stops = 0; pnl = 0.0
        for _, tr in gtr.iterrows():
            if rule == "breaker1" and stops >= 1: break
            if rule == "breaker2" and stops >= 2: break
            pnl += f * tr["ret"]
            if tr["outcome"] == "stop":
                stops += 1
                if rule == "antimart":
                    f = 0.5
            elif rule == "antimart" and tr["outcome"] == "target":
                f = 1.0
        return pnl

    rules = {}
    for rule in ("breaker1", "breaker2", "antimart"):
        rules[rule] = (t4.groupby("date")
                       .apply(lambda x: day_pnl_rule(x, rule), include_groups=False)
                       .reindex(all_days).fillna(0))
    results.append(metrics(base, "T4 baseline flat100"))
    for rule, ser in rules.items():
        results.append(metrics(ser, f"T4 {rule}"))
    print("\nrule comparison:")
    print(pd.DataFrame(results).to_string(index=False))
    print("\nby year (bp/day): baseline", byyear(base))
    for rule, ser in rules.items():
        print(f"                  {rule:9s}", byyear(ser))

    # ================= T1: fraction sweep =================
    print(); print("=" * 70); print("T1. FIXED-FRACTION SWEEP"); print("=" * 70)
    t1_rows = []
    for f in (0.25, 0.5, 0.75, 1.0, 1.25, 1.33):
        t1_rows.append(metrics(base * f, f"f={f}"))
    t1 = pd.DataFrame(t1_rows)
    print(t1.to_string(index=False))
    results += t1_rows

    # ================= T3: vol-targeted =================
    print(); print("=" * 70); print("T3. VOL-TARGETED"); print("=" * 70)
    j = daily.loc[all_days, ["atr5"]].assign(pnl=base)
    j["bucket"] = pd.qcut(j["atr5"], 4, labels=False) + 1
    tab = j.groupby("bucket").agg(atr_med=("atr5", "median"),
                                  mean_bp=("pnl", lambda x: x.mean() * 1e4),
                                  sd_pct=("pnl", lambda x: x.std() * 100))
    tab["sharpe"] = (tab["mean_bp"] / 1e4) / (tab["sd_pct"] / 100) * np.sqrt(252)
    print("Sharpe by ATR5 bucket (does risk outgrow edge?):")
    print(tab.round(2).to_string())
    for k in (6, 8, 10):
        f_d = np.minimum(1.0, k / j["atr5"])
        results.append(metrics(base * f_d, f"T3 voltarget k={k}"))
    print(pd.DataFrame(results[-3:]).to_string(index=False))

    # ================= T6: soft gate =================
    print(); print("=" * 70); print("T6. SOFT GATE"); print("=" * 70)
    allq = log4.groupby("date")["ret"].sum()
    idx_all = daily.index[orq5_ok & daily["atr5"].notna()]
    allq = allq.reindex(idx_all).fillna(0)
    ramp = np.clip((daily.loc[idx_all, "atr5"] - 5) / 2, 0, 1)
    soft = allq * ramp
    soft_active = soft[ramp > 0]
    results.append(metrics(soft_active, "T6 ramp (5->7 ATR)"))
    print(pd.DataFrame([metrics(base, "cliff gate >=6 (baseline)"),
                        metrics(soft_active, "T6 ramp (5->7)")]).to_string(index=False))

    # ================= T2: risk-normalized (stop x R) =================
    print(); print("=" * 70); print("T2. RISK-NORMALIZED (stop x R)"); print("=" * 70)
    t2_rows = []
    for s_ in (.02, .03, .04):
        ser = (logs[s_][logs[s_]["date"].isin(gated)]
               .groupby("date")["ret"].sum().reindex(all_days).fillna(0))
        for R in (.02, .03, .04):
            f = min(R / s_, 1.33)
            t2_rows.append({**metrics(ser * f, f"stop{s_*100:g} R{R*100:g} f={f:.2f}")})
    print(pd.DataFrame(t2_rows).to_string(index=False))
    results += t2_rows

    # ================= T5: bootstrap Kelly + stress =================
    print(); print("=" * 70); print("T5. BOOTSTRAP KELLY (block=10d, 10k years)")
    print("=" * 70)
    def paths(pool, n=10000, days=252, block=10):
        arr = pool.to_numpy()
        out = np.empty((n, days))
        for p in range(n):
            i = 0
            while i < days:
                st = rng.integers(0, len(arr))
                ln = min(rng.geometric(1 / block), days - i)
                seg = np.take(arr, np.arange(st, st + ln), mode="wrap")
                out[p, i:i + ln] = seg
                i += ln
        return out
    stress = base.copy()
    stress[stress.index.year == 2022] *= 1.5      # harsher 2022
    stress = pd.concat([stress, pd.Series([-0.20])])  # injected halt day
    t5_rows = []
    for pool, pname in [(base, "empirical"), (stress, "stressed")]:
        P = paths(pool)
        for f in (0.5, 0.75, 1.0, 1.25, 1.33, 1.5, 2.0):
            eq = np.cumprod(1 + f * P, axis=1)
            peak = np.maximum.accumulate(eq, axis=1)
            mdd = ((eq - peak) / peak).min(axis=1)
            cagr = eq[:, -1] - 1
            t5_rows.append({"pool": pname, "f": f,
                            "med_yr_ret_pct": round(np.median(cagr) * 100, 1),
                            "p5_yr_ret_pct": round(np.percentile(cagr, 5) * 100, 1),
                            "P(dd<-30%)_pct": round((mdd < -.30).mean() * 100, 1),
                            "med_dd_pct": round(np.median(mdd) * 100, 1)})
    t5 = pd.DataFrame(t5_rows)
    print(t5.to_string(index=False))
    ok = t5[(t5["pool"] == "stressed") & (t5["P(dd<-30%)_pct"] <= 5)]
    print(f"\nmax f with P(maxDD<-30%)<=5% under STRESS pool: "
          f"{ok['f'].max() if len(ok) else '<0.5'}")

    pd.DataFrame(results).to_csv(os.path.join(OUT, "v11_results.csv"), index=False)
    t5.to_csv(os.path.join(OUT, "v11_bootstrap.csv"), index=False)
    log4[log4["date"].isin(gated)].to_csv(os.path.join(OUT, "v11_trades.csv"),
                                          index=False)

if __name__ == "__main__":
    main()
