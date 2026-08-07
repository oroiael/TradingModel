"""Systematic scan for cross-instrument leading indicators.

Question: does an aggregated feature of instrument S on day t-L carry
information about instrument T's move on day t, BEYOND what T's own history
already says?

Specification, for every (S, feature, L, T, target):

    Y_T[t] = a + (own-history controls for T) + c * X_S[t-L] + e

  * direction targets  (close-to-close return, overnight return) control for
    the target's own lagged value.
  * magnitude targets  (|return|, log realized vol) control for a full HAR-RV
    lag structure -- daily, weekly (5d) and monthly (22d) components of the
    TARGET's own realized volatility.  Without that control, any persistent
    volatility series "predicts" any other and the finding is vacuous.

Only c is tested.  All variables standardized, so c is in units of target
standard deviation per predictor standard deviation.

Multiple testing is the whole problem here -- the scan runs 816 specifications.
Three layers of defence:
  1. HAC (Newey-West) standard errors for serial correlation.
  2. Benjamini-Hochberg FDR across the entire scan.
  3. A circular-rotation bootstrap that preserves each series' own
     autocorrelation while destroying cross-alignment, giving the null
     distribution of max|t| across all 816 tests -- a family-wise error rate
     that naive p-values cannot provide.
Anything that does not clear layer 3 is noise, however good its own p-value.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from common import OUT, banner

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)

SYMS = ["SPXL", "FAS", "VXX"]
TRAIN_END = pd.Timestamp("2023-12-31")
rng = np.random.default_rng(20260803)

full = pd.read_csv(OUT / "p11_panel.csv", index_col=0, parse_dates=True)

# HAR components of each instrument's own realized volatility
for s in SYMS:
    lr = full[f"{s}.day_logrv"]
    full[f"{s}.har5"] = lr.rolling(5).mean()
    full[f"{s}.har22"] = lr.rolling(22).mean()
    full[f"{s}.abs_ret"] = full[f"{s}.cc_ret"].abs()

PREDICTORS = [
    "lasthr_ret", "lasthr_logrv", "lasthr_jump", "lasthr_volratio", "lasthr_cir",
    "lasthr_ofi", "lasthr_share",
    "day_ret", "day_logrv", "day_jump", "day_volratio", "day_cir", "day_ofi",
    "day_maxabs",
    "d5_ret", "d5_logrv", "d5_volratio",
]
TARGETS = {
    "cc_ret":     ("direction", ["cc_ret"]),
    "overnight":  ("direction", ["overnight"]),
    "abs_ret":    ("magnitude", ["day_logrv", "har5", "har22"]),
    "day_logrv":  ("magnitude", ["day_logrv", "har5", "har22"]),
}
LAGS = [1, 2]
PAIRS = [(a, b) for a in SYMS for b in SYMS if a != b]


def z(x: pd.Series) -> pd.Series:
    return (x - x.mean()) / x.std()


def fast_t(X: np.ndarray, y: np.ndarray, col: int) -> float:
    """OLS t-statistic on one coefficient, closed form. Used inside the bootstrap."""
    XtX = X.T @ X
    try:
        XtXi = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        return np.nan
    b = XtXi @ (X.T @ y)
    resid = y - X @ b
    s2 = resid @ resid / (X.shape[0] - X.shape[1])
    se = np.sqrt(s2 * XtXi[col, col])
    return float(b[col] / se) if se > 0 else np.nan


# ------------------------------------------------------------------ assemble
specs, designs = [], []
for src, tgt in PAIRS:
    for tname, (kind, ctrl_cols) in TARGETS.items():
        for lag in LAGS:
            for f in PREDICTORS:
                yc = f"{tgt}.{tname}"
                xc = f"{src}.{f}"
                # Build explicitly with distinct names.  When the target IS one of
                # its own HAR controls (target day_logrv, control day_logrv), a
                # shared column label would collide and make y two-dimensional.
                d = pd.DataFrame({"y": full[yc]})
                d["x"] = full[xc].shift(lag)
                for i, c in enumerate(ctrl_cols):
                    d[f"c{i}"] = full[f"{tgt}.{c}"].shift(lag)
                d = d.dropna()
                if len(d) < 300:
                    continue
                y = z(d["y"]).values
                Xp = z(d["x"]).values
                C = np.column_stack([z(d[f"c{i}"]).values for i in range(len(ctrl_cols))])
                X = np.column_stack([np.ones(len(d)), Xp, C])
                specs.append({"src": src, "tgt": tgt, "feature": f, "lag": lag,
                              "target": tname, "kind": kind, "n": len(d),
                              "index": d.index})
                designs.append((X, y))

print(banner(f"SCAN: {len(specs)} specifications"))
print(f"{len(PAIRS)} ordered pairs x {len(TARGETS)} targets x {len(LAGS)} lags "
      f"x {len(PREDICTORS)} features")
print("Direction targets control for own lag; magnitude targets control for HAR-RV "
      "(daily/5d/22d).\n")

# ------------------------------------------------------------------ observed
rows = []
for spec, (X, y) in zip(specs, designs):
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 10})
    idx = spec["index"]
    tr = idx <= TRAIN_END
    rec = dict(spec); rec.pop("index")
    rec["beta"] = m.params[1]
    rec["t_hac"] = m.tvalues[1]
    rec["p_hac"] = m.pvalues[1]
    rec["t_ols"] = fast_t(X, y, 1)
    # partial R2 of the cross term
    m0 = sm.OLS(y, np.delete(X, 1, axis=1)).fit()
    rec["partial_R2_pct"] = (m.rsquared - m0.rsquared) * 100
    # train / test betas, same standardization
    if tr.sum() > 200 and (~tr).sum() > 200:
        bt = sm.OLS(y[tr], X[tr]).fit().params[1]
        be = sm.OLS(y[~tr], X[~tr]).fit().params[1]
        rec["beta_train"], rec["beta_test"] = bt, be
        rec["sign_stable"] = np.sign(bt) == np.sign(be)
    else:
        rec["beta_train"] = rec["beta_test"] = np.nan
        rec["sign_stable"] = False
    rows.append(rec)

R = pd.DataFrame(rows)
R["abs_t"] = R["t_hac"].abs()

# Benjamini-Hochberg FDR
order = np.argsort(R["p_hac"].values)
p_sorted = R["p_hac"].values[order]
n = len(p_sorted)
bh = p_sorted * n / (np.arange(n) + 1)
bh = np.minimum.accumulate(bh[::-1])[::-1]
R.loc[R.index[order], "p_bh"] = np.clip(bh, 0, 1)

print(f"Nominal p<0.05 : {(R['p_hac'] < 0.05).sum()} of {len(R)} "
      f"(expected by chance ~{0.05*len(R):.0f})")
print(f"Nominal p<0.01 : {(R['p_hac'] < 0.01).sum()} (expected ~{0.01*len(R):.0f})")
print(f"BH-FDR q<0.10  : {(R['p_bh'] < 0.10).sum()}")
print(f"BH-FDR q<0.05  : {(R['p_bh'] < 0.05).sum()}")

# ------------------------------------------------------------------ bootstrap
print(banner("FAMILY-WISE NULL: circular-rotation bootstrap on the cross predictor"))
print("Rotating the predictor destroys cross-alignment but preserves its own")
print("autocorrelation exactly. 400 replications; the statistic is max|t| over all")
print(f"{len(specs)} specifications simultaneously.\n")
NBOOT = 400
maxes = np.empty(NBOOT)
N = len(designs)
for b in range(NBOOT):
    best = 0.0
    for (X, y) in designs:
        nrow = X.shape[0]
        off = rng.integers(21, nrow - 21)
        Xb = X.copy()
        Xb[:, 1] = np.roll(X[:, 1], off)
        t = fast_t(Xb, y, 1)
        if np.isfinite(t) and abs(t) > best:
            best = abs(t)
    maxes[b] = best
    if (b + 1) % 100 == 0:
        print(f"  {b+1}/{NBOOT} replications done")

obs_max = R["t_ols"].abs().max()
fw_p = float((maxes >= obs_max).mean())
crit95 = float(np.percentile(maxes, 95))
print(f"\n  observed max|t| across all specs : {obs_max:.3f}")
print(f"  null distribution of max|t|      : median {np.median(maxes):.3f}  "
      f"95th pct {crit95:.3f}  max {maxes.max():.3f}")
print(f"  FAMILY-WISE p-value for the single best finding: {fw_p:.4f}")
print(f"  -> {'SURVIVES' if fw_p < 0.05 else 'DOES NOT SURVIVE'} family-wise correction at 5%")
R["passes_fwer"] = R["t_ols"].abs() >= crit95
print(f"  specifications exceeding the family-wise 95% critical value "
      f"({crit95:.3f}): {int(R['passes_fwer'].sum())}")

# ------------------------------------------------------------------ report
print(banner("TOP 25 BY |HAC t|"))
cols = ["src", "tgt", "feature", "lag", "target", "kind", "beta", "t_hac", "p_hac",
        "p_bh", "partial_R2_pct", "beta_train", "beta_test", "sign_stable",
        "passes_fwer", "n"]
print(R.sort_values("abs_t", ascending=False).head(25)[cols]
      .to_string(index=False, float_format=lambda x: f"{x:.4f}"))

print(banner("BEST FINDING PER TARGET TYPE"))
for k in ["direction", "magnitude"]:
    sub = R[R["kind"] == k].sort_values("abs_t", ascending=False)
    print(f"\n--- {k} targets ({len(sub)} specs) ---")
    print(sub.head(8)[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(f"  nominal p<0.05: {(sub['p_hac']<0.05).sum()} of {len(sub)} "
          f"(chance ~{0.05*len(sub):.0f})   BH q<0.10: {(sub['p_bh']<0.10).sum()}"
          f"   FWER survivors: {int(sub['passes_fwer'].sum())}")

print(banner("WHICH SOURCE -> TARGET DIRECTIONS CARRY ANYTHING?"))
agg = R.groupby(["src", "tgt", "kind"]).agg(
    n_specs=("abs_t", "size"), max_abs_t=("abs_t", "max"),
    mean_abs_t=("abs_t", "mean"), n_p05=("p_hac", lambda x: (x < 0.05).sum()),
    n_fwer=("passes_fwer", "sum")).reset_index()
print(agg.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
print("\nUnder the null, mean|t| ~ 0.8 and n_p05 ~ 5% of n_specs.")

R.to_csv(OUT / "p12_scan_results.csv", index=False)
np.save(OUT / "p12_boot_maxt.npy", maxes)
print(f"\n[saved] {OUT}/p12_scan_results.csv, p12_boot_maxt.npy")
