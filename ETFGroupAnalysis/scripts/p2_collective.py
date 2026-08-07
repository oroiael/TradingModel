"""Phase 2 -- collective / pairwise analysis.  Answers "is this a basket?"

T2.1 correlation across horizons and through time
T2.2 tail / exceedance correlation
T2.3 cointegration and pairs testing (SPXL vs FAS)
T2.4 lead-lag structure
T2.5 PCA / eigenportfolio decomposition
T2.6 basket construction, walk-forward
T2.7 nonlinear dependence
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.decomposition import PCA
from statsmodels.tsa.stattools import adfuller, ccf, coint, grangercausalitytests
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from common import OUT, SYMBOLS, TRADING_DAYS, banner, load_raw, max_drawdown, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 50)

raw = {s: load_raw(s) for s in SYMBOLS}
sess = {s: session_ohlc(raw[s]) for s in SYMBOLS}

# Common session grid -- the only window on which a basket could actually trade.
common = sorted(set.intersection(*[set(sess[s].index) for s in SYMBOLS]))
px = pd.DataFrame({s: sess[s].loc[common, "close"] for s in SYMBOLS})
rd = np.log(px / px.shift(1)).dropna()
print(f"Common daily grid: {px.index.min().date()} -> {px.index.max().date()} "
      f"({len(px)} sessions, {len(rd)} returns)")

# Common intraday grid
ts_common = sorted(set.intersection(*[set(raw[s]["ts"]) for s in SYMBOLS]))
ipx = pd.DataFrame({s: raw[s].set_index("ts")["Close"].reindex(ts_common) for s in SYMBOLS})
ir = np.log(ipx / ipx.shift(1))
same_sess = pd.Series(ipx.index, index=ipx.index).dt.date
ir = ir[same_sess.values == pd.Series(same_sess.shift(1).values, index=ipx.index).values].dropna()
print(f"Common 5-min grid: {len(ir):,} intra-session returns")

# ---------------------------------------------------------------- T2.1
print(banner("T2.1  CORRELATION ACROSS HORIZONS AND THROUGH TIME"))
for lab, r in [("5-min", ir), ("30-min", None), ("daily", rd)]:
    if lab == "30-min":
        r = np.log(ipx.iloc[::6] / ipx.iloc[::6].shift(1)).dropna()
    print(f"\n--- {lab} Pearson ---")
    print(r.corr().to_string(float_format=lambda x: f"{x:.4f}"))
    print(f"--- {lab} Spearman ---")
    print(r.corr(method="spearman").to_string(float_format=lambda x: f"{x:.4f}"))

print("\n60-day rolling correlation (daily returns) -- stability check:")
roll = pd.DataFrame({
    "SPXL~FAS": rd["SPXL"].rolling(60).corr(rd["FAS"]),
    "SPXL~VXX": rd["SPXL"].rolling(60).corr(rd["VXX"]),
    "FAS~VXX": rd["FAS"].rolling(60).corr(rd["VXX"]),
}).dropna()
print(roll.describe().T[["mean", "std", "min", "25%", "50%", "75%", "max"]]
      .to_string(float_format=lambda x: f"{x:.4f}"))
print("\nAnnual mean of the rolling correlations:")
print(roll.groupby(roll.index.year).mean().to_string(float_format=lambda x: f"{x:.4f}"))

# ---------------------------------------------------------------- T2.2
print(banner("T2.2  TAIL / EXCEEDANCE CORRELATION"))
print("Correlation conditional on SPXL being beyond a quantile threshold.")
print("Average correlation is the wrong statistic if the strategy dies in tails.\n")
rows = []
for qlo, qhi, lab in [(0.00, 0.05, "SPXL worst 5%"), (0.00, 0.10, "worst 10%"),
                      (0.00, 0.25, "worst 25%"), (0.25, 0.75, "middle 50%"),
                      (0.75, 1.00, "best 25%"), (0.90, 1.00, "best 10%"),
                      (0.95, 1.00, "best 5%")]:
    lo, hi = rd["SPXL"].quantile([qlo, qhi])
    m = rd[(rd["SPXL"] >= lo) & (rd["SPXL"] <= hi)]
    rows.append({"bucket": lab, "n": len(m),
                 "SPXL~FAS": m["SPXL"].corr(m["FAS"]),
                 "SPXL~VXX": m["SPXL"].corr(m["VXX"]),
                 "FAS~VXX": m["FAS"].corr(m["VXX"])})
print(pd.DataFrame(rows).set_index("bucket").to_string(float_format=lambda x: f"{x:.4f}"))
print("\nNOTE: conditioning on one variable's range mechanically attenuates its own")
print("correlations (range restriction). Compare buckets to each other, not to the")
print("unconditional value. FAS~VXX is NOT range-restricted here and is the clean read.")

# Tail dependence coefficients (empirical, non-parametric)
print("\nEmpirical tail dependence (P[Y extreme | X extreme]) at the 5% level:")
u = rd.rank(pct=True)
for a, b in [("SPXL", "FAS"), ("SPXL", "VXX"), ("FAS", "VXX")]:
    lower = ((u[a] < 0.05) & (u[b] < 0.05)).sum() / max(1, (u[a] < 0.05).sum())
    upper = ((u[a] > 0.95) & (u[b] > 0.95)).sum() / max(1, (u[a] > 0.95).sum())
    opp = ((u[a] < 0.05) & (u[b] > 0.95)).sum() / max(1, (u[a] < 0.05).sum())
    print(f"  {a:4s}~{b:4s}: lower-lower {lower:.3f}   upper-upper {upper:.3f}   "
          f"{a}-crash & {b}-spike {opp:.3f}")

# ---------------------------------------------------------------- T2.3
print(banner("T2.3  COINTEGRATION -- SPXL vs FAS  (levered AND de-levered)"))
lp = np.log(px[["SPXL", "FAS"]])

# de-levered reconstruction: r_1x = r_3x / 3, recompounded
delev = {}
for s in ("SPXL", "FAS"):
    r3 = px[s].pct_change().dropna()
    delev[s] = (1 + r3 / 3).cumprod()
dl = pd.DataFrame(delev).dropna()
ldl = np.log(dl)

for label, frame in [("LEVERED log prices", lp), ("DE-LEVERED (1x) log prices", ldl)]:
    print(f"\n--- {label} ---")
    y, x = frame["SPXL"], frame["FAS"]
    t, p, crit = coint(y, x)
    print(f"  Engle-Granger: t={t:.4f}  p={p:.4f}  crit(1%,5%,10%)={np.round(crit,3)}")
    beta = np.polyfit(x, y, 1)[0]
    spread = y - beta * x
    ad = adfuller(spread, autolag="AIC")
    print(f"  OLS hedge ratio beta={beta:.4f};  ADF on spread: stat={ad[0]:.4f} p={ad[1]:.4f}")
    jo = coint_johansen(frame.values, det_order=0, k_ar_diff=1)
    print(f"  Johansen trace stats={np.round(jo.lr1,3)}  "
          f"5% crit={np.round(jo.cvt[:,1],3)}  -> rank "
          f"{int((jo.lr1 > jo.cvt[:,1]).sum())}")
    # Ornstein-Uhlenbeck half-life of the spread
    ds = spread.diff().dropna()
    slag = spread.shift(1).dropna().loc[ds.index]
    phi = np.polyfit(slag, ds, 1)[0]
    hl = -np.log(2) / phi if phi < 0 else np.inf
    print(f"  OU mean-reversion half-life: {hl:.1f} days"
          f"{'  (no reversion -- phi >= 0)' if phi >= 0 else ''}")
    print(f"  spread range: {spread.min():.4f} .. {spread.max():.4f}  "
          f"std={spread.std():.4f}  |  final-vs-initial drift={spread.iloc[-1]-spread.iloc[0]:+.4f}")

print("\nRatio drift check -- does SPXL/FAS revert or wander?")
ratio = px["SPXL"] / px["FAS"]
print(f"  ratio start {ratio.iloc[0]:.4f}  end {ratio.iloc[-1]:.4f}  "
      f"min {ratio.min():.4f}  max {ratio.max():.4f}")
print(f"  ADF on log ratio: p={adfuller(np.log(ratio), autolag='AIC')[1]:.4f}")

# ---------------------------------------------------------------- T2.4
print(banner("T2.4  LEAD-LAG STRUCTURE"))
print("Cross-correlation of 5-min intra-session returns, lags -6..+6 bars.")
print("ccf[k] = corr(x[t], y[t+k]); positive k means x LEADS y.\n")
for a, b in [("VXX", "SPXL"), ("FAS", "SPXL"), ("VXX", "FAS")]:
    x, y = ir[a].values, ir[b].values
    fwd = ccf(x, y, adjusted=False)[:7]     # x leads y
    bwd = ccf(y, x, adjusted=False)[:7]     # y leads x
    lags = list(range(-6, 7))
    vals = list(bwd[1:7][::-1]) + [fwd[0]] + list(fwd[1:7])
    se = 1.96 / np.sqrt(len(x))
    print(f"  {a} vs {b}  (95% band +/-{se:.4f}):")
    print("    lag  " + "  ".join(f"{l:+3d}" for l in lags))
    print("    ccf  " + "  ".join(f"{v:+.3f}" for v in vals))
    sig = [f"{l:+d}" for l, v in zip(lags, vals) if abs(v) > se and l != 0]
    print(f"    significant non-zero lags: {sig if sig else 'none'}")

print("\nGranger causality on 5-min returns (max lag 3), p-values:")
for a, b in [("VXX", "SPXL"), ("SPXL", "VXX"), ("FAS", "SPXL"), ("SPXL", "FAS")]:
    try:
        res = grangercausalitytests(ir[[b, a]].values, maxlag=3, verbose=False)
        ps = [res[l][0]["ssr_ftest"][1] for l in (1, 2, 3)]
        print(f"  {a} -> {b}: p(lag1)={ps[0]:.3e}  p(lag2)={ps[1]:.3e}  p(lag3)={ps[2]:.3e}")
    except Exception as e:
        print(f"  {a} -> {b}: failed ({e})")
print("\nNOTE: with ~115k observations almost anything is 'significant'. Economic")
print("magnitude (the ccf value) matters, not the p-value.")

# ---------------------------------------------------------------- T2.5
print(banner("T2.5  PCA / EIGENPORTFOLIO DECOMPOSITION"))
for lab, r in [("daily", rd), ("5-min", ir)]:
    z = (r - r.mean()) / r.std()
    p = PCA().fit(z.values)
    print(f"\n--- {lab} ---")
    print(f"  variance explained: {np.round(p.explained_variance_ratio_ * 100, 2)} %")
    print(f"  cumulative        : {np.round(np.cumsum(p.explained_variance_ratio_)*100, 2)} %")
    load = pd.DataFrame(p.components_.T, index=r.columns,
                        columns=[f"PC{i+1}" for i in range(len(r.columns))])
    print(load.to_string(float_format=lambda x: f"{x:+.4f}"))

print("\nRolling 252-day PC1 variance share (is the structure stable?):")
shares = []
for i in range(252, len(rd)):
    w = rd.iloc[i - 252:i]
    z = (w - w.mean()) / w.std()
    shares.append({"date": rd.index[i],
                   "pc1": PCA().fit(z.values).explained_variance_ratio_[0]})
ps = pd.DataFrame(shares).set_index("date")["pc1"]
print(f"  mean {ps.mean():.4f}  min {ps.min():.4f}  max {ps.max():.4f}")
print(ps.groupby(ps.index.year).mean().to_string(float_format=lambda x: f"{x:.4f}"))

# ---------------------------------------------------------------- T2.6
print(banner("T2.6  BASKET CONSTRUCTION -- WALK-FORWARD, NO IN-SAMPLE FITTING"))
print("Weights formed on a trailing 126-day window, applied to the NEXT day,")
print("rebalanced monthly. Long-only where the scheme implies it.\n")

LOOKBACK = 126
rebal = pd.Series(rd.index).dt.to_period("M").values
results = {}


def eval_curve(r: pd.Series, name: str, turnover: float = np.nan) -> dict:
    return {"strategy": name, "ann_ret": r.mean() * TRADING_DAYS,
            "ann_vol": r.std() * np.sqrt(TRADING_DAYS),
            "sharpe": (r.mean() * TRADING_DAYS) / (r.std() * np.sqrt(TRADING_DAYS)),
            "max_dd": max_drawdown(r.cumsum()),
            "calmar": (r.mean() * TRADING_DAYS) / abs(max_drawdown(r.cumsum())),
            "cvar95": r[r <= r.quantile(0.05)].mean(),
            "ann_turnover": turnover}


schemes = ["equal_weight", "inverse_vol", "risk_parity", "min_variance", "long_only_2"]
for scheme in schemes:
    w_hist, rets, prev_w, tno = [], [], None, 0.0
    for i in range(LOOKBACK, len(rd)):
        if prev_w is None or rebal[i] != rebal[i - 1]:
            win = rd.iloc[i - LOOKBACK:i]
            cov = win.cov().values
            vol = win.std().values
            if scheme == "equal_weight":
                w = np.ones(3) / 3
            elif scheme == "inverse_vol":
                w = (1 / vol) / (1 / vol).sum()
            elif scheme == "risk_parity":
                w = np.ones(3) / 3
                for _ in range(500):          # simple ERC fixed point
                    mrc = cov @ w
                    rc = w * mrc
                    w = w * (rc.mean() / rc) ** 0.1
                    w = np.clip(w, 1e-6, None); w /= w.sum()
            elif scheme == "min_variance":
                inv = np.linalg.pinv(cov)
                w = inv @ np.ones(3)
                w /= w.sum()
            elif scheme == "long_only_2":     # SPXL+FAS only, inverse vol, no VXX
                v = vol.copy(); v[SYMBOLS.index("VXX")] = np.inf
                w = (1 / v) / (1 / v).sum()
            if prev_w is not None:
                tno += np.abs(w - prev_w).sum()
            prev_w = w
        rets.append(float(rd.iloc[i].values @ prev_w))
        w_hist.append(prev_w)
    r = pd.Series(rets, index=rd.index[LOOKBACK:])
    yrs = len(r) / TRADING_DAYS
    results[scheme] = eval_curve(r, scheme, tno / yrs)
    results[scheme]["avg_w"] = np.round(np.mean(w_hist, axis=0), 3)

for s in SYMBOLS:
    results[f"buyhold_{s}"] = eval_curve(rd[s].iloc[LOOKBACK:], f"buyhold_{s}")
    results[f"buyhold_{s}"]["avg_w"] = "-"

tab = pd.DataFrame(results).T.set_index("strategy")
print(tab.to_string(float_format=lambda x: f"{x:.4f}"))
print("\nWARNING: min_variance may hold VXX purely as a variance sink while ignoring")
print("its -52%/yr drift. Read ann_ret, not just ann_vol.")

# ---------------------------------------------------------------- T2.7
print(banner("T2.7  NONLINEAR DEPENDENCE (exploratory, P3)"))


def distance_correlation(x, y):
    x = np.asarray(x, float).reshape(-1, 1); y = np.asarray(y, float).reshape(-1, 1)
    n = x.shape[0]
    a = np.abs(x - x.T); b = np.abs(y - y.T)
    A = a - a.mean(0) - a.mean(1)[:, None] + a.mean()
    B = b - b.mean(0) - b.mean(1)[:, None] + b.mean()
    dcov2 = (A * B).sum() / (n * n)
    dvx = (A * A).sum() / (n * n); dvy = (B * B).sum() / (n * n)
    return float(np.sqrt(dcov2 / np.sqrt(dvx * dvy))) if dvx > 0 and dvy > 0 else np.nan


def mutual_info_binned(x, y, bins=12):
    c, _, _ = np.histogram2d(x, y, bins=bins)
    p = c / c.sum()
    px_ = p.sum(1, keepdims=True); py_ = p.sum(0, keepdims=True)
    nz = p > 0
    return float((p[nz] * np.log(p[nz] / (px_ @ py_)[nz])).sum())


print("Daily returns. Compared against |Pearson| to see if anything nonlinear is added.")
print("MI significance from a 500-draw permutation null.\n")
rng = np.random.default_rng(11)
for a, b in [("SPXL", "FAS"), ("SPXL", "VXX"), ("FAS", "VXX")]:
    x, y = rd[a].values, rd[b].values
    dc = distance_correlation(x, y)
    mi = mutual_info_binned(x, y)
    null = np.array([mutual_info_binned(x, rng.permutation(y)) for _ in range(500)])
    pval = (null >= mi).mean()
    print(f"  {a:4s}~{b:4s}: |Pearson|={abs(np.corrcoef(x,y)[0,1]):.4f}  "
          f"dCor={dc:.4f}  MI={mi:.4f} nats (perm p={pval:.3f}, "
          f"null mean {null.mean():.4f})")
print("\nInterpretation guide: dCor materially above |Pearson| would indicate nonlinear")
print("structure. Similar values mean the linear measure already captures the relationship.")

tab.to_csv(OUT / "p2_baskets.csv")
rd.corr().to_csv(OUT / "p2_corr_daily.csv")
roll.to_csv(OUT / "p2_rolling_corr.csv")
print(f"\n[saved] {OUT}/p2_baskets.csv, p2_corr_daily.csv, p2_rolling_corr.csv")
