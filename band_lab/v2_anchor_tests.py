"""
V2 entry-anchor program — execution (spec: V2_ANCHOR_TESTS.md).
Corrected engine, start 11:00, dip/target 1%, stop 4% absolute, cap 5,
2-stop breaker, V9 direction filter, ATR5>=6 gate. Only the anchor varies:
  session   -- rolling session high, prior bars (incumbent)
  winN      -- rolling high over the prior N bars only (N=12/24/36)
  vwapD     -- cumulative VWAP (typical price x volume), entry D% below
  pclose    -- prior session close, entry 1% below
  reset     -- session high SINCE THE LAST EXIT (kills instant re-entry)

Outputs: band_lab/out/v2_results.csv + printed report.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars
from v11_sizing_tests import metrics, byyear

OUT = os.path.join(HERE, "out")
START_I, MAXTR, MAXSTOP, DIP, TGT, STP = 18, 5, 2, .01, .01, .04

def sim(o, h, l, c, v, mode, param=None, pclose=None, collect_depth=False):
    n = len(c)
    tp = (h + l + c) / 3
    cum_pv = np.concatenate([[0], np.cumsum(tp * v)])
    cum_v = np.concatenate([[0], np.cumsum(v)])
    def anchor(i, since):
        if mode == "session":
            return h[:i].max()
        if mode == "win":
            return h[max(0, i - param):i].max()
        if mode == "vwap":
            return cum_pv[i] / cum_v[i] if cum_v[i] > 0 else np.nan
        if mode == "pclose":
            return pclose
        if mode == "reset":
            return h[since:i].max() if i > since else np.nan
    dip = param if mode == "vwap" else DIP
    pnl = 0.0; trades = 0; stops = 0
    state = 0; entry = 0.0; entry_i = -1; since = 0
    depths = []
    for i in range(START_I, n):
        if state == 1:
            tgt = entry * (1 + TGT); stp = entry * (1 - STP)
            exited = False
            if l[i] <= stp:
                pnl += -STP if o[i] > stp else o[i] / entry - 1
                stops += 1; state = 0; exited = True
            elif i > entry_i and h[i] >= tgt:
                pnl += TGT if o[i] < tgt else o[i] / entry - 1
                state = 0; exited = True
            if exited:
                since = i + 1
        if state == 0 and trades < MAXTR and stops < MAXSTOP:
            A = anchor(i, since)
            if A is not None and not np.isnan(A):
                trig = A * (1 - dip)
                if l[i] <= trig:
                    entry = min(trig, o[i]); entry_i = i; state = 1; trades += 1
                    if collect_depth:
                        depths.append((A - entry) / A)
                    stp = entry * (1 - STP)
                    if l[i] <= stp:
                        pnl += -STP if o[i] > stp else min(o[i] / entry - 1, -STP)
                        stops += 1; state = 0; since = i + 1
    if state == 1:
        pnl += c[-1] / entry - 1
    return pnl, trades, depths

def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 2 and x.std() > 0 else 0

def main():
    bars = load_bars()
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    daily["atr5"] = daily["range_pct"].rolling(5).mean().shift()
    daily["pc"] = daily["c"].shift()
    or30, pos10 = {}, {}
    for d, gb in g:
        hh = gb["High"].to_numpy()[:6]; ll = gb["Low"].to_numpy()[:6]
        cc = gb["Close"].to_numpy()
        orh, orl = hh.max(), ll.min()
        or30[d] = (orh - orl) / gb["Open"].iloc[0] * 100
        pos10[d] = (cc[5] - orl) / (orh - orl) if orh > orl and len(cc) > 5 else .5
    daily["or30"] = pd.Series(or30); daily["pos10"] = pd.Series(pos10)
    daily["thr80"] = daily["or30"].shift(1).rolling(504, min_periods=120).quantile(.8)
    v9 = daily.index[(daily["or30"] < daily["thr80"]) |
                     ((daily["or30"] >= daily["thr80"]) & (daily["pos10"] >= 2/3))]
    universe = set(daily.index[(daily["atr5"] >= 6)]) & set(v9)
    arrays = {}
    for dd, gb in g:
        if dd in universe and len(gb) >= 20:
            arrays[dd] = tuple(gb[x].to_numpy()
                               for x in ["Open", "High", "Low", "Close", "Volume"])
    udays = sorted(arrays)

    def run(mode, param=None, collect=False):
        p, n, deps = {}, {}, []
        for dd in udays:
            o, h, l, c, v = arrays[dd]
            pnl, tr, dp = sim(o, h, l, c, v, mode, param,
                              pclose=daily.loc[dd, "pc"], collect_depth=collect)
            p[dd] = pnl; n[dd] = tr
            if collect:
                deps += [(dd, x) for x in dp]
        return pd.Series(p), pd.Series(n), deps

    # ---------------- T1 anatomy
    print("=" * 70); print("T1. ENTRY ANATOMY (incumbent anchor)"); print("=" * 70)
    base, ntr, deps = run("session", collect=True)
    dd_ = pd.DataFrame(deps, columns=["date", "depth"])
    # per-trade returns needed: re-simulate collecting per-trade (approx via
    # depth buckets against day pnl is wrong; do a trade-level sim quickly)
    # trade-level: reuse v6-style log with depth
    recs = []
    for dd in udays:
        o, h, l, c, v = arrays[dd]
        roll_hi_hist = None
        # replicate sim inline for per-trade records (session anchor)
        state = 0; entry = 0.0; entry_i = -1; trades = 0; stops = 0
        for i in range(START_I, len(c)):
            if state == 1:
                tgt = entry * (1 + TGT); stp = entry * (1 - STP)
                if l[i] <= stp:
                    r = -STP if o[i] > stp else o[i] / entry - 1
                    recs.append({"date": dd, "depth": dep, "ret": r, "out": "stop"})
                    stops += 1; state = 0
                elif i > entry_i and h[i] >= tgt:
                    r = TGT if o[i] < tgt else o[i] / entry - 1
                    recs.append({"date": dd, "depth": dep, "ret": r, "out": "tgt"})
                    state = 0
            if state == 0 and trades < MAXTR and stops < MAXSTOP:
                A = h[:i].max()
                trig = A * (1 - DIP)
                if l[i] <= trig:
                    entry = min(trig, o[i]); entry_i = i; state = 1; trades += 1
                    dep = (A - entry) / A
                    stp = entry * (1 - STP)
                    if l[i] <= stp:
                        r = -STP if o[i] > stp else min(o[i] / entry - 1, -STP)
                        recs.append({"date": dd, "depth": dep, "ret": r, "out": "stop"})
                        stops += 1; state = 0
        if state == 1:
            recs.append({"date": dd, "depth": dep, "ret": c[-1] / entry - 1,
                         "out": "eod"})
    tl = pd.DataFrame(recs)
    tl["bucket"] = pd.cut(tl["depth"] * 100, [0.9, 1.1, 2, 4, 100],
                          labels=["~1% true dip", "1-2%", "2-4%", ">4% deep"])
    t1 = tl.groupby("bucket", observed=True).agg(
        n=("ret", "size"), mean_bp=("ret", lambda x: round(x.mean() * 1e4, 1)),
        stop_pct=("out", lambda x: round((x == "stop").mean() * 100, 0)),
        tgt_pct=("out", lambda x: round((x == "tgt").mean() * 100, 0)))
    print(t1.to_string())
    t1.to_csv(os.path.join(OUT, "v2_anatomy.csv"))

    # ---------------- T2/T3/T4 variants
    print(); print("=" * 70); print("T2-T4. ANCHOR FAMILY"); print("=" * 70)
    series = {"session (incumbent)": base}
    rows = [dict(metrics(base, "session (incumbent)"),
                 trades_day=round(ntr.mean(), 2))]
    for nm, mode, param in [("win12 (1h)", "win", 12), ("win24 (2h)", "win", 24),
                            ("win36 (3h)", "win", 36),
                            ("vwap-0.5%", "vwap", .005), ("vwap-1%", "vwap", .01),
                            ("vwap-1.5%", "vwap", .015),
                            ("prior-close", "pclose", None),
                            ("reset-after-exit", "reset", None)]:
        ser, nt, _ = run(mode, param)
        series[nm] = ser
        rows.append(dict(metrics(ser, nm), trades_day=round(nt.mean(), 2)))
    print(pd.DataFrame(rows).to_string(index=False))
    for nm in ("session (incumbent)", "win24 (2h)", "vwap-1%", "reset-after-exit"):
        print(f"  {nm:20s} by year:", byyear(series[nm]))

    # ---------------- T5 walk-forward
    print(); print("=" * 70); print("T5. WALK-FORWARD"); print("=" * 70)
    oos = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{year}-01-01"); t1_ = pd.Timestamp(f"{year+1}-01-01")
        best, bs = None, -99
        for nm, ser in series.items():
            tr = ser[ser.index < t0]
            s_ = sharpe(tr)
            if s_ > bs: bs, best = s_, nm
        te = series[best][(series[best].index >= t0) & (series[best].index < t1_)]
        oos.append(te)
        print(f"  {year}: picked {best:20s} -> OOS {te.mean()*1e4:+.1f} bp/day")
    allo = pd.concat(oos).sort_index()
    print(f"  ALL OOS: {allo.mean()*1e4:.1f} bp/day, Sharpe {sharpe(allo):.2f}")
    # reset gap = value of instant re-entry
    gap = (base.mean() - series["reset-after-exit"].mean()) * 1e4
    print(f"\nvalue of instant re-entry (incumbent - reset): {gap:+.1f} bp/day")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "v2_results.csv"), index=False)

if __name__ == "__main__":
    main()
