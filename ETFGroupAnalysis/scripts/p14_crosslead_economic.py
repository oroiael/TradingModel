"""Is the cross-asset volatility signal economically useful?

p13 established, out of sample, that adding VXX last-hour realized volatility
(and SPXL last-hour RV for the FAS target) to a HAR-RV + leverage model improves
next-day volatility forecasts.  Statistical improvement is not the same as
usefulness, so two economic tests:

  A. Volatility targeting.  Scale a long position by 1/forecast-vol to hold risk
     constant.  Compare sizing off M0 / M1 / M2 forecasts.  Vol targeting helps
     by itself in equities, so the question is only the INCREMENT from the better
     forecast, M2 vs M1 -- not vol targeting versus nothing.

  B. Big-move-day classification.  Directly "a leading indicator of moves":
     can we flag tomorrow as a top-decile absolute-move day?  Logistic
     regression, out-of-sample AUC and precision in the flagged decile.  This is
     the risk-management use, and it does not require directional skill.

All forecasts use expanding windows; nothing is fitted on data it then predicts.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from common import OUT, TRADING_DAYS, banner, max_drawdown

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

SYMS = ["SPXL", "FAS", "VXX"]
full = pd.read_csv(OUT / "p11_panel.csv", index_col=0, parse_dates=True)
for s in SYMS:
    lr = full[f"{s}.day_logrv"]
    full[f"{s}.har5"] = lr.rolling(5).mean()
    full[f"{s}.har22"] = lr.rolling(22).mean()

M0 = ["har1", "har5", "har22"]
M1 = M0 + ["own_ret", "own_cir", "own_negret"]
# Only the cross terms that SURVIVED the leverage-effect control in p13.
# VXX day_ret is deliberately excluded: its t fell from 7.16 to 0.35 once the
# target's own leverage terms were included -- it was the leverage effect.
CROSS = {"SPXL": ["VXX.lasthr_logrv", "VXX.day_cir"],
         "FAS": ["VXX.lasthr_logrv", "VXX.day_cir", "SPXL.lasthr_logrv"]}


def build(tgt: str) -> pd.DataFrame:
    d = pd.DataFrame({"y": full[f"{tgt}.day_logrv"]})
    d["ret"] = full[f"{tgt}.cc_ret"]
    d["har1"] = full[f"{tgt}.day_logrv"].shift(1)
    d["har5"] = full[f"{tgt}.har5"].shift(1)
    d["har22"] = full[f"{tgt}.har22"].shift(1)
    d["own_ret"] = full[f"{tgt}.day_ret"].shift(1)
    d["own_cir"] = full[f"{tgt}.day_cir"].shift(1)
    d["own_negret"] = np.minimum(full[f"{tgt}.day_ret"].shift(1), 0)
    for c in CROSS[tgt]:
        d[f"x_{c}"] = full[c].shift(1)
    return d.dropna()


MIN_TRAIN = 500
TARGET_VOL = 0.20      # 20% annualized risk budget
MAX_LEV = 3.0          # cap so the sizing rule cannot take absurd positions

results, cls_rows = [], []
for tgt in ("SPXL", "FAS"):
    d = build(tgt)
    xc = [f"x_{c}" for c in CROSS[tgt]]
    sets = {"M0": M0, "M1": M1, "M2": M1 + xc}
    n = len(d)
    fc = {k: np.full(n, np.nan) for k in sets}
    for i in range(MIN_TRAIN, n):
        for name, cols in sets.items():
            X = np.column_stack([np.ones(i)] + [d[c].values[:i] for c in cols])
            b, *_ = np.linalg.lstsq(X, d["y"].values[:i], rcond=None)
            fc[name][i] = np.concatenate([[1.0], [d[c].values[i] for c in cols]]) @ b
    m = ~np.isnan(fc["M0"])
    idx = d.index[m]
    ret = d["ret"].values[m]

    print(banner(f"A. VOLATILITY TARGETING -- {tgt}"))
    print(f"{int(m.sum())} out-of-sample days, {idx[0].date()} -> {idx[-1].date()}. "
          f"Target {TARGET_VOL:.0%} annualized, leverage capped at {MAX_LEV:g}x.\n")
    base = pd.Series(ret, index=idx)
    rows = [{"sizing": "constant (1x)", "ann_ret": base.mean() * TRADING_DAYS,
             "ann_vol": base.std() * np.sqrt(TRADING_DAYS),
             "sharpe": base.mean() / base.std() * np.sqrt(TRADING_DAYS),
             "max_dd": max_drawdown(base.cumsum()),
             "avg_lev": 1.0, "turnover": 0.0,
             "realized_vs_target": base.std() * np.sqrt(TRADING_DAYS) / TARGET_VOL}]
    scaled = {}
    for name in sets:
        vol_hat = np.exp(fc[name][m])
        lev = np.clip(TARGET_VOL / vol_hat, 0, MAX_LEV)
        r = pd.Series(lev * ret, index=idx)
        scaled[name] = r
        rows.append({"sizing": f"vol-target off {name}",
                     "ann_ret": r.mean() * TRADING_DAYS,
                     "ann_vol": r.std() * np.sqrt(TRADING_DAYS),
                     "sharpe": r.mean() / r.std() * np.sqrt(TRADING_DAYS),
                     "max_dd": max_drawdown(r.cumsum()),
                     "avg_lev": lev.mean(),
                     "turnover": np.abs(np.diff(lev)).mean() * TRADING_DAYS,
                     "realized_vs_target": r.std() * np.sqrt(TRADING_DAYS) / TARGET_VOL})
    t = pd.DataFrame(rows).set_index("sizing")
    print(t.to_string(float_format=lambda x: f"{x:.4f}"))
    print("\n  'realized_vs_target' near 1.00 means the sizing rule actually delivered")
    print("  the risk it aimed at -- that is the real test of a volatility forecast.")
    d21 = scaled["M2"] - scaled["M1"]
    mm = sm.OLS(d21.values, np.ones(len(d21))).fit(cov_type="HAC", cov_kwds={"maxlags": 10})
    print(f"\n  M2 minus M1 daily return difference: mean {d21.mean()*TRADING_DAYS:+.3%}/yr, "
          f"t = {mm.tvalues[0]:+.3f}, p = {mm.pvalues[0]:.4f}")
    print(f"  Sharpe: M1 {rows[2]['sharpe']:.4f} -> M2 {rows[3]['sharpe']:.4f} "
          f"({rows[3]['sharpe']-rows[2]['sharpe']:+.4f})")
    results.append(t.assign(target=tgt))

    # ---------------- B. classification
    print(banner(f"B. BIG-MOVE-DAY CLASSIFICATION -- {tgt}"))
    absret = np.abs(d["ret"].values)
    for pct, lab in [(90, "top decile"), (95, "top 5%")]:
        preds = {k: np.full(n, np.nan) for k in sets}
        for i in range(MIN_TRAIN, n):
            thr = np.percentile(absret[:i], pct)
            ybin = (absret[:i] > thr).astype(int)
            if ybin.sum() < 20:
                continue
            for name, cols in sets.items():
                X = np.column_stack([d[c].values[:i] for c in cols])
                mu, sd = X.mean(0), X.std(0) + 1e-12
                lr_ = LogisticRegression(max_iter=1000, C=1.0)
                lr_.fit((X - mu) / sd, ybin)
                xr = (np.array([d[c].values[i] for c in cols]) - mu) / sd
                preds[name][i] = lr_.predict_proba(xr.reshape(1, -1))[0, 1]
        mk = ~np.isnan(preds["M0"])
        thr_oos = np.percentile(absret[mk], pct)
        ytrue = (absret[mk] > thr_oos).astype(int)
        print(f"  --- {lab} threshold ({ytrue.mean():.1%} of {int(mk.sum())} OOS days "
              f"are events) ---")
        for name in sets:
            p = preds[name][mk]
            auc = roc_auc_score(ytrue, p)
            top = p >= np.percentile(p, pct)
            prec = ytrue[top].mean()
            print(f"    {name}: AUC = {auc:.4f}   precision in flagged bucket = "
                  f"{prec:.3f}   lift = {prec/ytrue.mean():.2f}x")
            cls_rows.append({"target": tgt, "level": lab, "model": name,
                             "auc": auc, "precision": prec,
                             "lift": prec / ytrue.mean()})
        # DeLong-free comparison: bootstrap the AUC difference M2 - M1
        rng = np.random.default_rng(5)
        p1, p2 = preds["M1"][mk], preds["M2"][mk]
        diffs = []
        for _ in range(1000):
            b = rng.integers(0, len(ytrue), len(ytrue))
            if ytrue[b].sum() in (0, len(b)):
                continue
            diffs.append(roc_auc_score(ytrue[b], p2[b]) - roc_auc_score(ytrue[b], p1[b]))
        diffs = np.array(diffs)
        print(f"    AUC(M2) - AUC(M1) = {roc_auc_score(ytrue,p2)-roc_auc_score(ytrue,p1):+.4f}"
              f"   bootstrap 95% CI [{np.percentile(diffs,2.5):+.4f}, "
              f"{np.percentile(diffs,97.5):+.4f}]"
              f"   P(M2>M1) = {(diffs>0).mean():.3f}")
    print()

pd.concat(results).to_csv(OUT / "p14_voltarget.csv")
pd.DataFrame(cls_rows).to_csv(OUT / "p14_classification.csv", index=False)
print(f"[saved] {OUT}/p14_voltarget.csv, p14_classification.csv")
