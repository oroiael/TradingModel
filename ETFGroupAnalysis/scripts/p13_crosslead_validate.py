"""Validate the cross-lead findings: is VXX actually adding information, or is
it proxying for the target's own leverage effect?

p12 found VXX features leading SPXL/FAS next-day realized volatility with
|t| up to 8.85, surviving a family-wise bootstrap.  The controls were HAR-RV:
the target's own realized-volatility history.  That is NOT sufficient.

VXX is -0.73 correlated with SPXL.  "VXX closed near its high" is close to
"SPXL had a down day", and down days predicting higher next-day volatility is
the leverage effect -- a well-known property of SPXL's OWN returns, not
information coming from VXX.  A cross-asset claim that is really the leverage
effect in disguise would be a serious error.

The decisive test is nested:

    M0  HAR-RV only                       (own volatility history)
    M1  M0 + own return + own close-in-range   (own leverage effect)
    M2  M1 + VXX features                      (does VXX add anything?)

If the VXX terms lose significance from M1 to M2, the p12 finding is the
leverage effect and must be retracted.  If they survive, it is real.

Then: out-of-sample forecast evaluation with expanding windows, QLIKE loss and
a Diebold-Mariano test, because statistical significance is not the same thing
as a better forecast.
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

SYMS = ["SPXL", "FAS", "VXX"]
full = pd.read_csv(OUT / "p11_panel.csv", index_col=0, parse_dates=True)
for s in SYMS:
    lr = full[f"{s}.day_logrv"]
    full[f"{s}.har5"] = lr.rolling(5).mean()
    full[f"{s}.har22"] = lr.rolling(22).mean()


def z(x):
    return (x - x.mean()) / x.std()


def build(tgt: str, src: str, vxx_feats: list[str]) -> pd.DataFrame:
    d = pd.DataFrame({"y": full[f"{tgt}.day_logrv"]})
    # M0: HAR-RV of the target itself
    d["har1"] = full[f"{tgt}.day_logrv"].shift(1)
    d["har5"] = full[f"{tgt}.har5"].shift(1)
    d["har22"] = full[f"{tgt}.har22"].shift(1)
    # M1 adds the target's OWN leverage terms
    d["own_ret"] = full[f"{tgt}.day_ret"].shift(1)
    d["own_cir"] = full[f"{tgt}.day_cir"].shift(1)
    d["own_negret"] = np.minimum(full[f"{tgt}.day_ret"].shift(1), 0)   # downside only
    # M2 adds the cross-instrument terms
    for f in vxx_feats:
        d[f"x_{f}"] = full[f"{src}.{f}"].shift(1)
    return d.dropna()


M0 = ["har1", "har5", "har22"]
M1 = M0 + ["own_ret", "own_cir", "own_negret"]

print(banner("NESTED TEST: does the cross term survive the target's own leverage effect?"))
print("Target = next-day log realized volatility. All variables standardized.\n")

CASES = [
    ("SPXL", "VXX", ["day_cir", "day_ret", "lasthr_logrv"]),
    ("FAS", "VXX", ["day_cir", "day_ret", "lasthr_logrv"]),
    ("FAS", "SPXL", ["lasthr_logrv", "day_cir", "day_ret"]),
    ("SPXL", "FAS", ["lasthr_logrv", "day_cir", "day_ret"]),
]

summary = []
for tgt, src, feats in CASES:
    d = build(tgt, src, feats)
    y = z(d["y"]).values
    xcols = [f"x_{f}" for f in feats]
    print(f"===== target {tgt} next-day logRV   <-   source {src} =====  n={len(d)}")
    fits = {}
    for name, cols in [("M0 HAR", M0), ("M1 HAR+own leverage", M1),
                       ("M2 M1+cross", M1 + xcols)]:
        X = np.column_stack([np.ones(len(d))] + [z(d[c]).values for c in cols])
        m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 10})
        fits[name] = (m, cols)
        print(f"  {name:22s} R2 = {m.rsquared*100:6.3f}%   adjR2 = {m.rsquared_adj*100:6.3f}%")
    m1, _ = fits["M1 HAR+own leverage"]
    m2, cols2 = fits["M2 M1+cross"]
    print(f"  incremental R2 from the cross terms: "
          f"{(m2.rsquared - m1.rsquared)*100:.3f} pp")
    # joint F-test that all cross terms are zero
    k = len(xcols)
    Rmat = np.zeros((k, len(cols2) + 1))
    for i in range(k):
        Rmat[i, 1 + len(M1) + i] = 1.0
    ft = m2.f_test(Rmat)
    print(f"  joint Wald test that ALL cross terms = 0: F = {float(ft.statistic):.3f}, "
          f"p = {float(ft.pvalue):.3e}")
    print(f"  {'cross term':<20s} {'M2 beta':>9s} {'M2 t':>7s} {'p':>10s}   "
          f"(alone-vs-HAR t from p12 in brackets)")
    for i, f in enumerate(feats):
        j = 1 + len(M1) + i
        print(f"    x_{f:<17s} {m2.params[j]:9.4f} {m2.tvalues[j]:7.3f} "
              f"{m2.pvalues[j]:10.3e}")
    summary.append({"target": tgt, "source": src,
                    "R2_M0": m1.rsquared * 100 - 0,  # placeholder replaced below
                    "R2_M1": m1.rsquared * 100, "R2_M2": m2.rsquared * 100,
                    "incr_pp": (m2.rsquared - m1.rsquared) * 100,
                    "joint_F": float(ft.statistic), "joint_p": float(ft.pvalue)})
    print()

S = pd.DataFrame(summary)
S["R2_M0"] = [sm.OLS(z(build(t, s, f)["y"]).values,
                     np.column_stack([np.ones(len(build(t, s, f)))]
                                     + [z(build(t, s, f)[c]).values for c in M0])
                     ).fit().rsquared * 100 for t, s, f in CASES]
print(banner("SUMMARY OF NESTED FITS"))
print(S[["target", "source", "R2_M0", "R2_M1", "R2_M2", "incr_pp", "joint_F", "joint_p"]]
      .to_string(index=False, float_format=lambda x: f"{x:.4f}"))

# ------------------------------------------------------------------ OOS
print(banner("OUT-OF-SAMPLE FORECAST EVALUATION (expanding window)"))
print("Refit each model every day on all history to date; forecast next-day logRV.")
print("QLIKE = log(s2) + rv2/s2 on the variance scale -- the standard loss for")
print("volatility forecasts, penalizing under-prediction. Lower is better.")
print("Diebold-Mariano compares M2 against M1 with HAC standard errors.\n")

MIN_TRAIN = 500
for tgt, src, feats in CASES:
    d = build(tgt, src, feats)
    xcols = [f"x_{f}" for f in feats]
    ycol = d["y"].values
    sets = {"M0": M0, "M1": M1, "M2": M1 + xcols}
    preds = {k: np.full(len(d), np.nan) for k in sets}
    for i in range(MIN_TRAIN, len(d)):
        tr = slice(0, i)
        for name, cols in sets.items():
            Xtr = np.column_stack([np.ones(i)] + [d[c].values[tr] for c in cols])
            b, *_ = np.linalg.lstsq(Xtr, ycol[tr], rcond=None)
            xrow = np.concatenate([[1.0], [d[c].values[i] for c in cols]])
            preds[name][i] = xrow @ b
    m = ~np.isnan(preds["M0"])
    act = ycol[m]
    print(f"===== {tgt} <- {src} =====  {int(m.sum())} out-of-sample days "
          f"({d.index[m][0].date()} -> {d.index[m][-1].date()})")
    losses = {}
    for name in sets:
        p = preds[name][m]
        oos_r2 = 1 - ((act - p) ** 2).sum() / ((act - act.mean()) ** 2).sum()
        rmse = np.sqrt(((act - p) ** 2).mean())
        s2 = np.exp(2 * p); rv2 = np.exp(2 * act)
        qlike = np.log(s2) + rv2 / s2
        losses[name] = {"mse": (act - p) ** 2, "qlike": qlike}
        print(f"  {name}: OOS R2 = {oos_r2*100:6.2f}%   RMSE = {rmse:.4f}   "
              f"mean QLIKE = {qlike.mean():.4f}")

    def dm(a, b, label):
        diff = a - b
        mm = sm.OLS(diff, np.ones(len(diff))).fit(cov_type="HAC",
                                                  cov_kwds={"maxlags": 10})
        return (f"    DM {label}: mean diff {diff.mean():+.5f}  "
                f"t = {mm.tvalues[0]:+.3f}  p = {mm.pvalues[0]:.4f}  "
                f"({'M2 better' if diff.mean() < 0 else 'M1 better'})")
    print(dm(losses["M2"]["mse"], losses["M1"]["mse"], "M2-M1 on MSE  "))
    print(dm(losses["M2"]["qlike"], losses["M1"]["qlike"], "M2-M1 on QLIKE"))
    print(dm(losses["M1"]["mse"], losses["M0"]["mse"], "M1-M0 on MSE  "))
    print()
