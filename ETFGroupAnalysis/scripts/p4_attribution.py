"""Phase 4b -- attribution and robustness for the one candidate that survived
economically (the vol-gated overnight sleeve), plus two corrections.

Correction 1: the Deflated Sharpe with n_trials=1 is degenerate
(norm.ppf(1 - 1/1) = -inf), which printed DSR=1.000 for buy-and-hold and made
it look like the only strategy that "passed".  With a single trial the correct
statistic is the Probabilistic Sharpe Ratio.  Both are reported here.

Correction 2 (the important one): p3 showed a vol-gated OVERNIGHT sleeve at
Sharpe 0.965.  That does not establish that the *overnight* leg is what
matters.  The gate must be applied to overnight-only, intraday-only and
full-day exposure separately, or the credit is misassigned.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats

from common import OUT, SYMBOLS, TRADING_DAYS, banner, load_raw, max_drawdown, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 230)

raw = {s: load_raw(s) for s in SYMBOLS}
sess = {s: session_ohlc(raw[s]) for s in SYMBOLS}
common = sorted(set.intersection(*[set(sess[s].index) for s in SYMBOLS]))
TRAIN_END = pd.Timestamp("2023-12-31")
EULER = 0.5772156649015329


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if r.std() > 0 else np.nan


def psr(r, benchmark_sr=0.0):
    """Probabilistic Sharpe Ratio: P(true SR > benchmark), skew/kurtosis aware."""
    r = r.dropna(); n = len(r)
    sr = r.mean() / r.std()
    b = benchmark_sr / np.sqrt(TRADING_DAYS)
    g3, g4 = stats.skew(r), stats.kurtosis(r, fisher=False)
    se = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (n - 1))
    return float(stats.norm.cdf((sr - b) / se))


def dsr(r, n_trials):
    r = r.dropna(); n = len(r)
    if n_trials <= 1:
        return np.nan
    sr = r.mean() / r.std()
    g3, g4 = stats.skew(r), stats.kurtosis(r, fisher=False)
    se = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (n - 1))
    e_max = np.sqrt(1.0 / (n - 1)) * (
        (1 - EULER) * stats.norm.ppf(1 - 1 / n_trials)
        + EULER * stats.norm.ppf(1 - 1 / (n_trials * np.e)))
    return float(stats.norm.cdf((sr - e_max) / se))


k = {s: sess[s].loc[common] for s in SYMBOLS}
ov = {s: np.log(k[s]["open"] / k[s]["close"].shift(1)).dropna() for s in SYMBOLS}
idy = {s: np.log(k[s]["close"] / k[s]["open"]).loc[ov[s].index] for s in SYMBOLS}
full = {s: np.log(k[s]["close"] / k[s]["close"].shift(1)).dropna() for s in SYMBOLS}

# The gate: 21-day trailing realized vol of SPXL, known at the 15:55 decision point.
rv21 = full["SPXL"].rolling(21).std() * np.sqrt(TRADING_DAYS)
gate = (rv21.shift(1) < 0.45).reindex(ov["SPXL"].index).fillna(False)
print(f"Gate 'SPXL 21d realized vol < 45%' is ON for {gate.mean():.1%} of sessions.")

# ------------------------------------------------------------------
print(banner("ATTRIBUTION -- is the edge the OVERNIGHT leg, or just VOL TIMING?"))
rows = []
for legname, leg in [("overnight", ov), ("intraday", idy), ("full-day", full)]:
    for sym in ("SPXL", "FAS"):
        base = leg[sym].reindex(ov[sym].index)
        for gname, g in [("ungated", pd.Series(True, index=base.index)), ("gated", gate)]:
            r = base.where(g, 0.0)
            rows.append({
                "leg": legname, "sym": sym, "gate": gname,
                "ann_ret": r.mean() * TRADING_DAYS,
                "ann_vol": r.std() * np.sqrt(TRADING_DAYS),
                "sharpe": sharpe(r),
                "sr_train": sharpe(r[r.index <= TRAIN_END]),
                "sr_test": sharpe(r[r.index > TRAIN_END]),
                "max_dd": max_drawdown(r.cumsum()),
            })
att = pd.DataFrame(rows).set_index(["leg", "sym", "gate"])
print(att.to_string(float_format=lambda x: f"{x:.4f}"))

print("\nSharpe lift from the gate (gated minus ungated), by leg:")
piv = att["sharpe"].unstack("gate")
piv["lift"] = piv["gated"] - piv["ungated"]
print(piv.to_string(float_format=lambda x: f"{x:+.4f}"))

# ------------------------------------------------------------------
print(banner("THRESHOLD SENSITIVITY -- is 45% a cliff or a plateau?"))
rows = []
for thr in [0.30, 0.35, 0.40, 0.425, 0.45, 0.475, 0.50, 0.55, 0.60, 0.70, 99.0]:
    g = (rv21.shift(1) < thr).reindex(ov["SPXL"].index).fillna(False)
    for legname, leg in [("overnight", ov), ("full-day", full)]:
        base = 0.5 * leg["SPXL"].reindex(g.index) + 0.5 * leg["FAS"].reindex(g.index)
        r = base.where(g, 0.0)
        rows.append({"thr": thr, "leg": legname, "exposure": g.mean(),
                     "ann_ret": r.mean() * TRADING_DAYS, "sharpe": sharpe(r),
                     "sr_train": sharpe(r[r.index <= TRAIN_END]),
                     "sr_test": sharpe(r[r.index > TRAIN_END]),
                     "max_dd": max_drawdown(r.cumsum())})
sens = pd.DataFrame(rows).pivot(index="thr", columns="leg",
                                values=["exposure", "sharpe", "sr_test", "max_dd"])
print(sens.to_string(float_format=lambda x: f"{x:.4f}"))
print("\nthr=99 is the ungated control. A plateau across 0.40-0.55 indicates a real")
print("effect; a spike only at 0.45 would indicate threshold mining.")

# ------------------------------------------------------------------
print(banner("YEAR-BY-YEAR -- gated 50/50 overnight vs benchmarks"))
g = gate
base_on = 0.5 * ov["SPXL"] + 0.5 * ov["FAS"]
base_fd = 0.5 * full["SPXL"].reindex(g.index) + 0.5 * full["FAS"].reindex(g.index)
cands = {
    "gated_overnight_5050": base_on.where(g, 0.0),
    "ungated_overnight_5050": base_on,
    "gated_fullday_5050": base_fd.where(g, 0.0),
    "buyhold_SPXL": full["SPXL"],
}
yr = pd.DataFrame({nm: r.groupby(r.index.year).apply(lambda x: x.sum())
                   for nm, r in cands.items()})
print("Cumulative log return by year:")
print(yr.to_string(float_format=lambda x: f"{x:+.4f}"))
print("\nSharpe by year:")
yrs = pd.DataFrame({nm: r.groupby(r.index.year).apply(sharpe) for nm, r in cands.items()})
print(yrs.to_string(float_format=lambda x: f"{x:+.4f}"))

# ------------------------------------------------------------------
print(banner("CORRECTED SIGNIFICANCE TABLE"))
print("PSR = P(true Sharpe > 0), skew/kurtosis-adjusted, single hypothesis.")
print("DSR = same but corrected for the number of variants tried.")
print("n_trials: 22 for anything selected from the gate grid, 3 for the pre-specified")
print("overnight sleeves, 32 for the intraday grid. Buy-and-hold was not selected.\n")
sig = []
for nm, r, nt in [
    ("buyhold_SPXL", full["SPXL"], 1),
    ("overnight_5050 (pre-specified)", base_on, 3),
    ("gated_overnight_5050 (grid-selected)", base_on.where(g, 0.0), 22),
    ("gated_fullday_5050 (grid-selected)", base_fd.where(g, 0.0), 22),
]:
    sig.append({"strategy": nm, "sharpe": sharpe(r),
                "sr_test": sharpe(r[r.index > TRAIN_END]),
                "PSR(SR>0)": psr(r), "PSR(SR>0.5)": psr(r, 0.5),
                "n_trials": nt, "DSR": dsr(r, nt)})
sg = pd.DataFrame(sig).set_index("strategy")
print(sg.to_string(float_format=lambda x: f"{x:.4f}"))
print("\nDSR is NaN for buy-and-hold because a single hypothesis needs no deflation --")
print("the earlier DSR=1.000 for it was a degenerate artifact of norm.ppf(0) = -inf,")
print("not evidence of superiority.")

att.to_csv(OUT / "p4_attribution.csv")
sens.to_csv(OUT / "p4_threshold_sensitivity.csv")
sg.to_csv(OUT / "p4_significance.csv")
print(f"\n[saved] {OUT}/p4_attribution.csv, p4_threshold_sensitivity.csv, p4_significance.csv")
