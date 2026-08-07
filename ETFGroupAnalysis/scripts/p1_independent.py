"""Phase 1 -- independent characterization of each instrument.

T1.1 return distributions and stylized facts
T1.2 intraday seasonality
T1.3 variance ratio + DFA Hurst   <- the central test
T1.4 overnight vs intraday decomposition
T1.5 volatility regimes
T1.6 leverage-drag decomposition (SPXL, FAS)
T1.7 VXX decay and payoff asymmetry
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import acf

from common import (BARS_PER_DAY, OUT, SYMBOLS, TRADING_DAYS, banner,
                    describe_returns, dfa_hurst, load_raw, logret,
                    max_drawdown, session_ohlc, variance_ratio)

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 50)

raw = {s: load_raw(s) for s in SYMBOLS}
sess = {s: session_ohlc(raw[s]) for s in SYMBOLS}

# Intra-session 5-min log returns (overnight gap EXCLUDED -- it is not a 5-min move
# and would contaminate every high-frequency statistic below).
intr = {}
for s in SYMBOLS:
    d = raw[s].copy()
    d["r"] = np.log(d["Close"] / d["Close"].shift(1))
    d["same_session"] = d["session"] == d["session"].shift(1)
    intr[s] = d[d["same_session"]].dropna(subset=["r"]).reset_index(drop=True)

daily = {s: sess[s]["close"] for s in SYMBOLS}
dret = {s: logret(daily[s]).dropna() for s in SYMBOLS}

# ---------------------------------------------------------------- T1.1
print(banner("T1.1  RETURN DISTRIBUTIONS AND STYLIZED FACTS"))
rows = []
for s in SYMBOLS:
    r5 = intr[s]["r"]
    rd = dret[s]
    a = describe_returns(r5, TRADING_DAYS * BARS_PER_DAY)
    b = describe_returns(rd, TRADING_DAYS)
    jb = stats.jarque_bera(rd)
    # Hill tail index on the worst 5% of daily losses
    losses = np.sort(-rd[rd < 0].values)[::-1]
    k = max(10, int(0.05 * len(rd)))
    hill = 1.0 / np.mean(np.log(losses[:k] / losses[k])) if len(losses) > k else np.nan
    rows.append({
        "sym": s,
        "ann_ret_5m": a["ann_return"], "ann_vol_5m": a["ann_vol"],
        "ann_ret_1d": b["ann_return"], "ann_vol_1d": b["ann_vol"],
        "sharpe_1d": b["sharpe"], "skew_1d": b["skew"], "exkurt_1d": b["kurtosis"],
        "worst_day": b["min"], "best_day": b["max"],
        "JB_p": jb.pvalue, "hill_tail_alpha": hill,
        "max_dd": max_drawdown(np.log(daily[s] / daily[s].iloc[0])),
    })
t11 = pd.DataFrame(rows).set_index("sym")
print(t11.to_string(float_format=lambda x: f"{x:.4f}"))

print("\nAutocorrelation structure (5-min intra-session returns):")
for s in SYMBOLS:
    r = intr[s]["r"].values
    ar = acf(r, nlags=12, fft=True)[1:]
    aabs = acf(np.abs(r), nlags=12, fft=True)[1:]
    lb = acorr_ljungbox(r, lags=[12], return_df=True)
    print(f"  {s}: ACF(returns) lags1-6 = {np.round(ar[:6], 4)}")
    print(f"        ACF(|returns|) 1-6  = {np.round(aabs[:6], 4)}   "
          f"Ljung-Box(12) p={lb['lb_pvalue'].iloc[0]:.3e}")

# ---------------------------------------------------------------- T1.2
print(banner("T1.2  INTRADAY SEASONALITY"))
print("Mean return (bp) and realized vol (bp) by 30-min block, with bootstrap 95% CI on mean.\n")
rng = np.random.default_rng(7)
for s in SYMBOLS:
    d = intr[s].copy()
    d["block"] = d["ts"].dt.floor("30min").dt.time
    g = d.groupby("block")["r"]
    tab = pd.DataFrame({"mean_bp": g.mean() * 1e4, "vol_bp": g.std() * 1e4, "n": g.size()})
    los, his = [], []
    for blk, grp in g:
        v = grp.values
        bs = rng.choice(v, size=(2000, v.size), replace=True).mean(axis=1) * 1e4
        los.append(np.percentile(bs, 2.5)); his.append(np.percentile(bs, 97.5))
    tab["ci_lo"], tab["ci_hi"] = los, his
    tab["signif"] = np.where((tab["ci_lo"] > 0) | (tab["ci_hi"] < 0), "***", "")
    print(f"--- {s} ---")
    print(tab.to_string(float_format=lambda x: f"{x:.3f}"))
    print()

# ---------------------------------------------------------------- T1.3
print(banner("T1.3  VARIANCE RATIO (Lo-MacKinlay) AND DFA HURST  [CENTRAL TEST]"))






print("VR(q) on 5-MINUTE intra-session returns.  VR<1 mean-reverting, VR>1 trending.")
print("z is heteroskedasticity-robust; |z|>1.96 is significant at 5%.\n")
vr_rows = []
for s in SYMBOLS:
    x = intr[s]["r"].values
    rec = {"sym": s}
    for q, lab in [(2, "10min"), (3, "15min"), (6, "30min"), (12, "1h"), (39, "half-day")]:
        vr, z, p = variance_ratio(x, q)
        rec[f"VR_{lab}"] = vr
        rec[f"z_{lab}"] = z
    vr_rows.append(rec)
print(pd.DataFrame(vr_rows).set_index("sym").to_string(float_format=lambda x: f"{x:.3f}"))

print("\nVR(q) on DAILY returns (close-to-close, includes overnight).")
vr_rows = []
for s in SYMBOLS:
    x = dret[s].values
    rec = {"sym": s}
    for q, lab in [(2, "2d"), (5, "1w"), (10, "2w"), (21, "1m"), (63, "1q")]:
        vr, z, p = variance_ratio(x, q)
        rec[f"VR_{lab}"] = vr
        rec[f"z_{lab}"] = z
    vr_rows.append(rec)
print(pd.DataFrame(vr_rows).set_index("sym").to_string(float_format=lambda x: f"{x:.3f}"))

print("\nDFA Hurst exponent (0.5 = random walk, <0.5 mean-reverting, >0.5 persistent):")
for s in SYMBOLS:
    h5 = dfa_hurst(intr[s]["r"].values)
    hd = dfa_hurst(dret[s].values)
    print(f"  {s}: 5-min H={h5:.4f}   daily H={hd:.4f}")

# ---------------------------------------------------------------- T1.4
print(banner("T1.4  OVERNIGHT vs INTRADAY DECOMPOSITION"))
dec = {}
for s in SYMBOLS:
    k = sess[s].copy()
    k["overnight"] = np.log(k["open"] / k["close"].shift(1))
    k["intraday"] = np.log(k["close"] / k["open"])
    k["total"] = np.log(k["close"] / k["close"].shift(1))
    dec[s] = k.dropna(subset=["overnight"])
rows = []
for s in SYMBOLS:
    k = dec[s]
    for leg in ("overnight", "intraday", "total"):
        r = k[leg]
        rows.append({
            "sym": s, "leg": leg,
            "cum_log": r.sum(),
            "cum_x": np.exp(r.sum()),
            "ann_ret": r.mean() * TRADING_DAYS,
            "ann_vol": r.std() * np.sqrt(TRADING_DAYS),
            "sharpe": (r.mean() * TRADING_DAYS) / (r.std() * np.sqrt(TRADING_DAYS)),
            "hit_rate": (r > 0).mean(),
            "max_dd": max_drawdown(r.cumsum()),
        })
t14 = pd.DataFrame(rows).set_index(["sym", "leg"])
print(t14.to_string(float_format=lambda x: f"{x:.4f}"))

print("\nYear-by-year cumulative log return split (overnight | intraday):")
yr = []
for s in SYMBOLS:
    k = dec[s]
    g = k.groupby(k.index.year)[["overnight", "intraday", "total"]].sum()
    g["sym"] = s
    yr.append(g.reset_index().rename(columns={"index": "year"}))
ytab = pd.concat(yr).pivot(index="session", columns="sym",
                           values=["overnight", "intraday"])
print(ytab.to_string(float_format=lambda x: f"{x:.3f}"))

# ---------------------------------------------------------------- T1.5
print(banner("T1.5  VOLATILITY REGIMES"))
try:
    from arch import arch_model
    for s in SYMBOLS:
        r = dret[s] * 100
        am = arch_model(r, vol="GARCH", p=1, o=1, q=1, dist="skewt", mean="Constant")
        res = am.fit(disp="off")
        pr = res.params
        alpha = pr.get("alpha[1]", np.nan)
        gamma = pr.get("gamma[1]", np.nan)
        beta = pr.get("beta[1]", np.nan)
        persist = alpha + beta + 0.5 * (gamma if np.isfinite(gamma) else 0)
        print(f"  {s}: GJR-GARCH(1,1,1) skew-t  alpha={alpha:.4f} gamma={gamma:.4f} "
              f"beta={beta:.4f}  persistence={persist:.4f}  "
              f"nu={pr.get('nu', np.nan):.2f} lambda={pr.get('lambda', np.nan):.3f}")
        print(f"        gamma>0 means negative shocks raise vol more (leverage effect)")
except Exception as e:
    print(f"  GARCH unavailable: {e}")

print("\nRealized-vol regimes (terciles of 21-day trailing realized vol, SPXL as reference):")
rv = dret["SPXL"].rolling(21).std() * np.sqrt(TRADING_DAYS)
q1, q2 = rv.quantile([1 / 3, 2 / 3])
reg = pd.cut(rv, [-np.inf, q1, q2, np.inf], labels=["low", "mid", "high"])
print(f"  SPXL 21d realized-vol terciles: low<{q1:.1%}  mid  high>{q2:.1%}")
for s in SYMBOLS:
    r = dret[s].reindex(rv.index)
    tab = r.groupby(reg, observed=True).agg(
        n="size", ann_ret=lambda x: x.mean() * TRADING_DAYS,
        ann_vol=lambda x: x.std() * np.sqrt(TRADING_DAYS))
    tab["sharpe"] = tab["ann_ret"] / tab["ann_vol"]
    print(f"\n  --- {s} by SPXL vol regime ---")
    print(tab.to_string(float_format=lambda x: f"{x:.4f}"))

# ---------------------------------------------------------------- T1.6
print(banner("T1.6  LEVERAGE-DRAG DECOMPOSITION (SPXL, FAS)"))
print("De-lever r_1x = r_3x / 3, recompound, and measure the path-dependency cost.")
print("Theory: drag rate = -0.5*L*(L-1)*sigma_1x^2 = -3*sigma_1x^2 for L=3.\n")
for s in ("SPXL", "FAS"):
    r3 = sess[s]["close"].pct_change().dropna()          # simple daily returns
    r1 = r3 / 3.0                                        # implied 1x index
    p3 = (1 + r3).prod()
    p1 = (1 + r1).prod()
    n_years = len(r3) / TRADING_DAYS
    cagr3 = p3 ** (1 / n_years) - 1
    cagr1 = p1 ** (1 / n_years) - 1
    naive3 = (1 + cagr1) ** 3 - 1     # what "3x" naively implies over a year
    sd1 = r1.std() * np.sqrt(TRADING_DAYS)
    theo_drag = -3.0 * sd1 ** 2
    actual_drag = np.log(p3) / n_years - 3 * np.log(p1) / n_years
    print(f"  {s}:")
    print(f"    reconstructed 1x  : CAGR {cagr1:7.2%}   ann vol {sd1:6.2%}")
    print(f"    actual 3x fund    : CAGR {cagr3:7.2%}   ann vol {r3.std()*np.sqrt(TRADING_DAYS):6.2%}")
    print(f"    3x of 1x CAGR     : {3*cagr1:7.2%}  (naive linear expectation)")
    print(f"    realized log drag : {actual_drag:7.2%} / yr")
    print(f"    theoretical drag  : {theo_drag:7.2%} / yr   (-3*sigma_1x^2)")
    print(f"    agreement         : {abs(actual_drag - theo_drag):.4%} absolute difference")
    # multi-day holding degradation
    print(f"    hold-period decay vs 3x-of-1x, by horizon:")
    for h in (1, 5, 10, 21, 63, 126, 252):
        c3 = (1 + r3).rolling(h).apply(np.prod, raw=True) - 1
        c1 = (1 + r1).rolling(h).apply(np.prod, raw=True) - 1
        gap = (c3 - 3 * c1).dropna()
        print(f"       {h:4d}d: median gap {gap.median():+7.3%}  mean {gap.mean():+7.3%}")
    print()

# ---------------------------------------------------------------- T1.7
print(banner("T1.7  VXX DECAY AND PAYOFF ASYMMETRY"))
v = sess["VXX"]["close"]
vr_ = v.pct_change().dropna()
n_years = len(vr_) / TRADING_DAYS
print(f"VXX {v.index.min().date()} -> {v.index.max().date()}: "
      f"{v.iloc[0]:,.2f} -> {v.iloc[-1]:,.2f}  "
      f"({v.iloc[-1]/v.iloc[0]-1:.2%} total, CAGR {(v.iloc[-1]/v.iloc[0])**(1/n_years)-1:.2%})")
half_life = np.log(0.5) / (np.log(v.iloc[-1] / v.iloc[0]) / n_years)
print(f"Implied half-life at the realized decay rate: {half_life:.2f} years\n")

print("Holding-period return distribution (overlapping windows):")
hp_rows = []
for h in (1, 2, 3, 5, 10, 15, 20, 40, 60):
    c = (v.shift(-h) / v - 1).dropna()
    hp_rows.append({
        "days": h, "n": len(c), "median": c.median(), "mean": c.mean(),
        "hit_rate": (c > 0).mean(), "p05": c.quantile(0.05), "p95": c.quantile(0.95),
        "max": c.max(), "skew": c.skew(),
    })
print(pd.DataFrame(hp_rows).set_index("days").to_string(float_format=lambda x: f"{x:.4f}"))

print("\nVXX conditional payoff on SPXL down days (same-day, common sessions):")
common = sess["SPXL"].index.intersection(sess["VXX"].index)
sp = sess["SPXL"].loc[common, "close"].pct_change()
vx = sess["VXX"].loc[common, "close"].pct_change()
both = pd.DataFrame({"spxl": sp, "vxx": vx}).dropna()
for lo, hi, lab in [(-np.inf, -0.05, "SPXL < -5%"), (-0.05, -0.03, "-5% to -3%"),
                    (-0.03, -0.01, "-3% to -1%"), (-0.01, 0.01, "-1% to +1%"),
                    (0.01, 0.03, "+1% to +3%"), (0.03, np.inf, "SPXL > +3%")]:
    m = both[(both["spxl"] > lo) & (both["spxl"] <= hi)]
    if len(m) == 0:
        continue
    print(f"  {lab:14s} n={len(m):4d}  VXX mean {m['vxx'].mean():+7.2%}  "
          f"median {m['vxx'].median():+7.2%}  max {m['vxx'].max():+7.2%}  "
          f"beta {np.polyfit(m['spxl'], m['vxx'], 1)[0]:+.2f}")

t11.to_csv(OUT / "p1_distributions.csv")
t14.to_csv(OUT / "p1_overnight_intraday.csv")
print(f"\n[saved] {OUT}/p1_distributions.csv, p1_overnight_intraday.csv")
