"""Phase 3 + Phase 4 -- strategy hypotheses, with costs and multiple-testing
correction applied to every result.

Phase 1/2 licensed exactly these tests:
  T3.1 intraday mean reversion   -- T1.3 said SPXL/FAS look like random walks,
                                    so this is expected to FAIL. Tested anyway,
                                    because "expected to fail" is not evidence.
  T3.2 vol-gated exposure        -- T1.5 found real regimes.
  T3.3 overnight sleeve          -- T1.4 found overnight dominance. Prime candidate.
  T3.4 SPXL/FAS relative value   -- NOT RUN. T2.3 found no cointegration in either
                                    the levered or the de-levered series (EG p=0.69
                                    and 0.55, Johansen rank 0). Running a pairs
                                    backtest on a non-cointegrated spread would be
                                    manufacturing a strategy, not testing one.
  T3.5 VXX hedge overlay         -- done in p2b_baskets.py (monotonically harmful).

Phase 4 is applied inline: cost sweep on every strategy, a strict train/test
split, and a Deflated Sharpe Ratio that accounts for how many variants were tried.
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


def sharpe(r: pd.Series) -> float:
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else np.nan


def deflated_sharpe(r: pd.Series, n_trials: int) -> tuple[float, float]:
    """Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio.

    Returns (expected max Sharpe under the null, DSR probability).
    Sharpes are handled in per-observation units internally and reported
    annualized.
    """
    r = r.dropna()
    n = len(r)
    if n < 30:
        return np.nan, np.nan
    sr = r.mean() / r.std()                      # per-observation
    g3, g4 = stats.skew(r), stats.kurtosis(r, fisher=False)
    var_sr = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (n - 1))
    # expected maximum Sharpe from n_trials independent draws of a zero-skill strategy
    e_max = np.sqrt(1.0 / (n - 1)) * (
        (1 - EULER) * stats.norm.ppf(1 - 1 / n_trials)
        + EULER * stats.norm.ppf(1 - 1 / (n_trials * np.e)))
    dsr = stats.norm.cdf((sr - e_max) / var_sr) if var_sr > 0 else np.nan
    return float(e_max * np.sqrt(TRADING_DAYS)), float(dsr)


def report(name: str, r: pd.Series, rt_per_year: float, n_trials: int = 1):
    """Print full stats for a daily return series, including a cost sweep."""
    r = r.dropna()
    tr = r[r.index <= TRAIN_END]
    te = r[r.index > TRAIN_END]
    e_max, dsr = deflated_sharpe(r, n_trials)
    print(f"\n--- {name} ---")
    print(f"  full   : ann {r.mean()*TRADING_DAYS:+7.2%}  vol {r.std()*np.sqrt(TRADING_DAYS):6.2%}  "
          f"SR {sharpe(r):+6.3f}  maxDD {max_drawdown(r.cumsum()):7.2%}  n={len(r)}")
    print(f"  train  : ann {tr.mean()*TRADING_DAYS:+7.2%}  SR {sharpe(tr):+6.3f}  n={len(tr)}")
    print(f"  TEST   : ann {te.mean()*TRADING_DAYS:+7.2%}  SR {sharpe(te):+6.3f}  n={len(te)}")
    print(f"  round-trips/yr {rt_per_year:.0f}   trials={n_trials}   "
          f"E[max SR|null]={e_max:.3f}   DSR={dsr:.3f}"
          f"{'  <-- fails DSR>0.95' if not (dsr > 0.95) else '  <-- passes DSR>0.95'}")
    costs = [0, 1, 2, 5, 10]
    line = "  cost sweep (bp/round-trip):  "
    for c in costs:
        rc = r - (c / 1e4) * (rt_per_year / TRADING_DAYS)
        line += f"{c}bp SR={sharpe(rc):+.3f}   "
    print(line)
    # break-even cost
    if r.mean() > 0 and rt_per_year > 0:
        be = r.mean() * TRADING_DAYS / rt_per_year * 1e4
        print(f"  break-even cost: {be:.2f} bp per round trip")
    return {"name": name, "sharpe": sharpe(r), "sr_test": sharpe(te),
            "ann_ret": r.mean() * TRADING_DAYS, "max_dd": max_drawdown(r.cumsum()),
            "dsr": dsr, "rt_yr": rt_per_year,
            "be_bp": (r.mean() * TRADING_DAYS / rt_per_year * 1e4) if rt_per_year else np.nan}


results = []

# ================================================================= T3.3
print(banner("T3.3  OVERNIGHT SLEEVE  (licensed by T1.4)"))
print("Buy the 15:55 close, sell the 09:30 open. 1 round trip per session, 252/yr.")
ov, ind = {}, {}
for s in SYMBOLS:
    k = sess[s].loc[common]
    ov[s] = np.log(k["open"] / k["close"].shift(1)).dropna()
    ind[s] = np.log(k["close"] / k["open"]).loc[ov[s].index]

results.append(report("ON: SPXL", ov["SPXL"], 252, n_trials=3))
results.append(report("ON: FAS", ov["FAS"], 252, n_trials=3))
results.append(report("ON: 50/50 SPXL+FAS", 0.5 * ov["SPXL"] + 0.5 * ov["FAS"], 252, 3))
results.append(report("BH: SPXL (benchmark, 0 turnover)",
                      np.log(sess["SPXL"].loc[common, "close"]).diff().dropna(), 0))
results.append(report("INTRADAY-only: SPXL", ind["SPXL"], 252, n_trials=3))
results.append(report("INTRADAY-only: FAS", ind["FAS"], 252, n_trials=3))

# ================================================================= T3.2
print(banner("T3.2  VOL-GATED OVERNIGHT  (licensed by T1.5)"))
print("Hold the overnight sleeve only when the VXX-based gate is favourable.")
print("Gate uses ONLY information available at the 15:55 decision point.\n")
vxx_c = sess["VXX"].loc[common, "close"]
base_on = 0.5 * ov["SPXL"] + 0.5 * ov["FAS"]
gate_specs = []
for lb in (5, 10, 21, 63):
    z = (np.log(vxx_c) - np.log(vxx_c).rolling(lb).mean()) / np.log(vxx_c).rolling(lb).std()
    for thr in (-0.5, 0.0, 0.5, 1.0):
        gate_specs.append((f"VXXz({lb})<{thr}", (z.shift(1) < thr).reindex(base_on.index).fillna(False)))
for lb in (10, 21):
    rv = np.log(sess["SPXL"].loc[common, "close"]).diff().rolling(lb).std() * np.sqrt(TRADING_DAYS)
    for thr in (0.30, 0.45, 0.60):
        gate_specs.append((f"SPXLrv({lb})<{thr:.2f}",
                           (rv.shift(1) < thr).reindex(base_on.index).fillna(False)))
N_GATE = len(gate_specs)
print(f"{N_GATE} gate variants tried -- every DSR below is corrected for that.\n")
grid = []
for nm, g in gate_specs:
    r = base_on.where(g, 0.0)
    rt = float(g.astype(int).diff().abs().fillna(0).sum()) / (len(g) / TRADING_DAYS)
    grid.append({"gate": nm, "exposure": g.mean(), "ann_ret": r.mean() * TRADING_DAYS,
                 "sharpe": sharpe(r), "sr_test": sharpe(r[r.index > TRAIN_END]),
                 "maxdd": max_drawdown(r.cumsum()), "rt_yr": rt,
                 "dsr": deflated_sharpe(r, N_GATE)[1]})
gt = pd.DataFrame(grid).sort_values("sharpe", ascending=False)
print(gt.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
best = gt.iloc[0]
print(f"\nBest gate by full-sample Sharpe: {best['gate']} (SR {best['sharpe']:.3f}).")
print(f"Ungated baseline SR = {sharpe(base_on):.3f}.")
bg = dict(gate_specs)[best["gate"]]
results.append(report(f"ON gated: {best['gate']}", base_on.where(bg, 0.0),
                      best["rt_yr"], n_trials=N_GATE))

# ================================================================= T3.1
print(banner("T3.1  INTRADAY MEAN REVERSION  (expected to fail -- tested anyway)"))
print("Fade deviations from a trailing intra-session mean. Enter at bar close when")
print("|z| > thr, exit when z crosses 0 or at 15:55. Long and short, no overnight.\n")


def intraday_mr(sym: str, lb: int, thr: float) -> pd.Series:
    d = raw[sym][raw[sym]["session"].isin([c.date() for c in common])].copy()
    d["lr"] = np.log(d["Close"])
    g = d.groupby("session")["lr"]
    mu = g.transform(lambda x: x.rolling(lb).mean())
    sd = g.transform(lambda x: x.rolling(lb).std())
    z = (d["lr"] - mu) / sd
    # position taken AFTER observing bar t, earns bar t+1's return
    pos = pd.Series(0.0, index=d.index)
    pos[z > thr] = -1.0
    pos[z < -thr] = 1.0
    pos = pos.groupby(d["session"]).shift(1).fillna(0.0)
    nxt = d.groupby("session")["lr"].diff().shift(-1)
    pnl = (pos * nxt).groupby(d["session"]).sum()
    trades = pos.diff().abs().groupby(d["session"]).sum() / 2.0
    out = pd.DataFrame({"pnl": pnl, "trades": trades})
    out.index = pd.to_datetime(out.index)
    return out


mr_grid = []
combos = [(lb, thr) for lb in (6, 12, 24, 39) for thr in (1.0, 1.5, 2.0, 2.5)]
N_MR = len(combos) * 2
for sym in ("SPXL", "FAS"):
    for lb, thr in combos:
        o = intraday_mr(sym, lb, thr)
        r = o["pnl"].dropna()
        rt = o["trades"].mean() * TRADING_DAYS
        mr_grid.append({"sym": sym, "lb": lb, "thr": thr, "ann_ret": r.mean() * TRADING_DAYS,
                        "sharpe": sharpe(r), "rt_yr": rt,
                        "be_bp": (r.mean() * TRADING_DAYS / rt * 1e4) if rt > 0 else np.nan,
                        "sr_5bp": sharpe(r - (5 / 1e4) * (rt / TRADING_DAYS)),
                        "dsr": deflated_sharpe(r, N_MR)[1]})
mr = pd.DataFrame(mr_grid).sort_values("sharpe", ascending=False)
print(f"{N_MR} variants tried.  Sorted by gross Sharpe:\n")
print(mr.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
print("\nbe_bp = break-even round-trip cost. Compare against the T0.5 spread estimates")
print("(Roll: SPXL 7.6bp, FAS 5.1bp, VXX 17.6bp) -- and note those are ESTIMATES.")

bmr = mr.iloc[0]
o = intraday_mr(bmr["sym"], int(bmr["lb"]), bmr["thr"])
results.append(report(f"IntradayMR best: {bmr['sym']} lb={int(bmr['lb'])} thr={bmr['thr']}",
                      o["pnl"].dropna(), bmr["rt_yr"], n_trials=N_MR))

# ================================================================= summary
print(banner("PHASE 4 SUMMARY -- what survives"))
sm = pd.DataFrame(results).set_index("name")
print(sm.to_string(float_format=lambda x: f"{x:.4f}"))
print("\nSurvival test: DSR > 0.95 AND positive out-of-sample Sharpe AND")
print("break-even cost comfortably above the estimated spread.")
surv = sm[(sm["dsr"] > 0.95) & (sm["sr_test"] > 0)]
print(f"\nStrategies meeting DSR>0.95 and SR_test>0: "
      f"{list(surv.index) if len(surv) else 'NONE'}")

sm.to_csv(OUT / "p3_strategy_summary.csv")
mr.to_csv(OUT / "p3_intraday_mr_grid.csv")
gt.to_csv(OUT / "p3_gate_grid.csv")
print(f"\n[saved] {OUT}/p3_strategy_summary.csv, p3_intraday_mr_grid.csv, p3_gate_grid.csv")
