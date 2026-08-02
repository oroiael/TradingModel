"""T2.6 (corrected) -- basket construction + VXX hedge sizing.

The first pass used a fixed-point ERC iteration that produced NaN weights
whenever a risk contribution went negative (which VXX's negative covariance
makes routine under long-only weights).  pandas then skipped those days
silently and reported a Sharpe computed on a subset.  That result was wrong and
is replaced here by a constrained numerical solve that is checked for
convergence, with any failure surfaced rather than swallowed.

Also adds the question that actually matters for this trio: not "equal weight
vs risk parity" but "does ANY small VXX allocation improve a long SPXL/FAS
book, once VXX's -52%/yr drift is paid for?"
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from common import OUT, SYMBOLS, TRADING_DAYS, banner, load_raw, max_drawdown, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)

raw = {s: load_raw(s) for s in SYMBOLS}
sess = {s: session_ohlc(raw[s]) for s in SYMBOLS}
common = sorted(set.intersection(*[set(sess[s].index) for s in SYMBOLS]))
px = pd.DataFrame({s: sess[s].loc[common, "close"] for s in SYMBOLS})
rd = np.log(px / px.shift(1)).dropna()

LOOKBACK = 126
IDX = {s: i for i, s in enumerate(SYMBOLS)}


def stats_of(r: pd.Series, turnover=np.nan) -> dict:
    dd = max_drawdown(r.cumsum())
    return {
        "ann_ret": r.mean() * TRADING_DAYS,
        "ann_vol": r.std() * np.sqrt(TRADING_DAYS),
        "sharpe": (r.mean() * TRADING_DAYS) / (r.std() * np.sqrt(TRADING_DAYS)),
        "max_dd": dd,
        "calmar": (r.mean() * TRADING_DAYS) / abs(dd),
        "cvar95": r[r <= r.quantile(0.05)].mean(),
        "worst_day": r.min(),
        "ann_turnover": turnover,
        "n_days": len(r),
    }


def erc_weights(cov: np.ndarray) -> tuple[np.ndarray, bool]:
    """Equal-risk-contribution weights, long-only, fully invested.

    Solved as a constrained least-squares on risk contributions.  Returns the
    weights and a convergence flag -- the caller must not silently use a
    non-converged result.
    """
    n = cov.shape[0]

    def obj(w):
        rc = w * (cov @ w)
        return float(((rc[:, None] - rc[None, :]) ** 2).sum())

    res = minimize(obj, np.ones(n) / n, method="SLSQP",
                   bounds=[(1e-6, 1.0)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
                   options={"maxiter": 500, "ftol": 1e-14})
    return res.x / res.x.sum(), bool(res.success)


def run_scheme(weight_fn, name):
    rets, ws, prev, tno, fails = [], [], None, 0.0, 0
    months = pd.Series(rd.index).dt.to_period("M").values
    for i in range(LOOKBACK, len(rd)):
        if prev is None or months[i] != months[i - 1]:
            win = rd.iloc[i - LOOKBACK:i]
            w, ok = weight_fn(win)
            if not ok or not np.all(np.isfinite(w)):
                fails += 1
                w = prev if prev is not None else np.ones(3) / 3
            if prev is not None:
                tno += np.abs(w - prev).sum()
            prev = w
        rets.append(float(rd.iloc[i].values @ prev))
        ws.append(prev)
    r = pd.Series(rets, index=rd.index[LOOKBACK:])
    assert r.notna().all(), f"{name}: NaN returns leaked through"
    out = stats_of(r, tno / (len(r) / TRADING_DAYS))
    out["avg_w"] = np.round(np.mean(ws, axis=0), 3)
    out["solver_fails"] = fails
    return name, out, r


print(banner("T2.6 (CORRECTED)  BASKET CONSTRUCTION -- WALK-FORWARD"))
print(f"Trailing {LOOKBACK}d weights, monthly rebalance, applied out-of-sample.")
print(f"Order of weights: {SYMBOLS}\n")

schemes = {
    "equal_weight": lambda w: (np.ones(3) / 3, True),
    "inverse_vol": lambda w: ((1 / w.std().values) / (1 / w.std().values).sum(), True),
    "risk_parity_ERC": lambda w: erc_weights(w.cov().values),
    "min_variance": lambda w: (
        (lambda v: (v / v.sum(), True))(np.linalg.pinv(w.cov().values) @ np.ones(3))),
    "SPXL+FAS_invvol": lambda w: (
        (lambda v: (v / v.sum(), True))(
            np.array([1 / w.std().values[0], 1 / w.std().values[1], 0.0]))),
}

rows, curves = {}, {}
for nm, fn in schemes.items():
    n, out, r = run_scheme(fn, nm)
    rows[n] = out
    curves[n] = r
for s in SYMBOLS:
    rows[f"buyhold_{s}"] = stats_of(rd[s].iloc[LOOKBACK:])
    rows[f"buyhold_{s}"]["avg_w"] = "-"
    rows[f"buyhold_{s}"]["solver_fails"] = 0
    curves[f"buyhold_{s}"] = rd[s].iloc[LOOKBACK:]

tab = pd.DataFrame(rows).T
print(tab.to_string(float_format=lambda x: f"{x:.4f}"))
print("\nsolver_fails must be 0 for the ERC row to be trustworthy.")

# ------------------------------------------------------------------
print(banner("VXX HEDGE SIZING SWEEP  --  the question that actually matters"))
print("Base book = SPXL/FAS 50/50 rebalanced monthly. Add a constant-weight VXX")
print("sleeve funded pro-rata from the base. Daily rebalance of the VXX sleeve is")
print("assumed (a levered/decaying hedge must be rebalanced or it self-liquidates).\n")

base = 0.5 * rd["SPXL"] + 0.5 * rd["FAS"]
rows = []
for vw in [0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20, 0.33]:
    r = (1 - vw) * base + vw * rd["VXX"]
    st = stats_of(r)
    st["vxx_weight"] = vw
    # how much of the worst drawdown did the hedge actually remove?
    rows.append(st)
sw = pd.DataFrame(rows).set_index("vxx_weight")
print(sw[["ann_ret", "ann_vol", "sharpe", "max_dd", "calmar", "cvar95", "worst_day"]]
      .to_string(float_format=lambda x: f"{x:.4f}"))

print("\nSame sweep restricted to the worst 5% of base-book days (does it pay off in tails?):")
worst = base <= base.quantile(0.05)
rows = []
for vw in [0.0, 0.01, 0.02, 0.03, 0.05, 0.10, 0.20, 0.33]:
    r = (1 - vw) * base + vw * rd["VXX"]
    rows.append({"vxx_weight": vw,
                 "mean_on_worst5pct": r[worst].mean(),
                 "worst_single_day": r[worst].min(),
                 "mean_all_other_days": r[~worst].mean(),
                 "annual_cost_of_hedge": (r[~worst].mean() - base[~worst].mean()) * TRADING_DAYS})
print(pd.DataFrame(rows).set_index("vxx_weight").to_string(float_format=lambda x: f"{x:.4f}"))

# ------------------------------------------------------------------
print(banner("SUB-PERIOD STABILITY OF THE BEST BASKETS"))
for nm in ["equal_weight", "risk_parity_ERC", "SPXL+FAS_invvol", "buyhold_SPXL"]:
    r = curves[nm]
    yr = r.groupby(r.index.year).agg(
        ann_ret=lambda x: x.mean() * TRADING_DAYS,
        sharpe=lambda x: (x.mean() * TRADING_DAYS) / (x.std() * np.sqrt(TRADING_DAYS)))
    print(f"\n--- {nm} ---")
    print(yr.to_string(float_format=lambda x: f"{x:.3f}"))

tab.to_csv(OUT / "p2b_baskets_corrected.csv")
sw.to_csv(OUT / "p2b_vxx_hedge_sweep.csv")
print(f"\n[saved] {OUT}/p2b_baskets_corrected.csv, p2b_vxx_hedge_sweep.csv")
