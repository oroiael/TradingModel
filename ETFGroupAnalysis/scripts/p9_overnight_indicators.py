"""Do any indicators improve the overnight trade?  SPXL and FAS, independently.

Target: the pure overnight log return, 15:55 close -> next 09:30 opening print.
Every predictor is computable at 15:55 on day t.  No lookahead.

13 indicators, pre-specified before running, chosen because each has a stated
economic reason to matter -- not because they were mined:

  1  intraday_ret      open->15:55 same day       intraday reversal into the night
  2  close_in_range    (C-L)/(H-L)                closing strength / auction pressure
  3  rv21              21d realized vol           the volatility-regime hypothesis
  4  rv5_over_rv21     short/long vol ratio       vol expansion vs contraction
  5  rsi14             14d RSI on closes          classic overbought/oversold
  6  dist_sma20        (C - SMA20)/sd20           mean-reversion distance
  7  prior_overnight   previous night's return    overnight autocorrelation
  8  dow               day of week                the weekend effect
  9  volume_ratio      volume / 20d average       participation / conviction
 10  vxx_chg           VXX same-day return        cross-asset stress signal
 11  vxx_level_z       VXX 63d z-score            vol-regime level
 12  last30_ret        15:25->15:55 return        late-day order flow
 13  ret5d             5-day cumulative return    short-term momentum

Protocol, identical to the one that retracted the volatility gate in p7:
  rank every rule on TRAIN only, freeze, evaluate on TEST, and report the
  train->test Spearman rank correlation across all rules.  If that is ~0, the
  selection is noise regardless of how good the winner looks.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from common import OUT, TRADING_DAYS, banner, load_raw, max_drawdown, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)

SYMS = ["SPXL", "FAS"]
TRAIN_END = pd.Timestamp("2023-12-31")

raw = {s: load_raw(s) for s in SYMS + ["VXX"]}
sess = {s: session_ohlc(raw[s]) for s in SYMS + ["VXX"]}
for s in sess:
    sess[s] = sess[s][sess[s]["bars"] >= 42]
common = sorted(set(sess["SPXL"].index) & set(sess["FAS"].index) & set(sess["VXX"].index))


def sharpe(r):
    r = pd.Series(r).dropna()
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if len(r) > 5 and r.std() > 0 else np.nan


def bar_close(sym, t):
    d = raw[sym]
    x = d[d["tod"] == pd.Timestamp(t).time()].set_index("session")["Close"]
    x.index = pd.to_datetime(x.index)
    return x.reindex(common)


def opening_print(sym):
    d = raw[sym]
    x = d[d["tod"] == pd.Timestamp("09:30").time()].set_index("session")["Open"]
    x.index = pd.to_datetime(x.index)
    return x.reindex(common)


def build(sym: str) -> pd.DataFrame:
    k = sess[sym].loc[common]
    c, h, l, o, v = k["close"], k["high"], k["low"], k["open"], k["volume"]
    op_next = opening_print(sym).shift(-1)
    vx = sess["VXX"].loc[common, "close"]
    d = pd.DataFrame(index=k.index)
    d["target"] = np.log(op_next / c)                       # the overnight trade
    d["intraday_ret"] = np.log(c / o)
    rng_ = (h - l).replace(0, np.nan)
    d["close_in_range"] = (c - l) / rng_
    ret = np.log(c / c.shift(1))
    d["rv21"] = ret.rolling(21).std() * np.sqrt(TRADING_DAYS)
    d["rv5_over_rv21"] = (ret.rolling(5).std() / ret.rolling(21).std())
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    d["rsi14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    d["dist_sma20"] = (c - c.rolling(20).mean()) / c.rolling(20).std()
    d["prior_overnight"] = d["target"].shift(1)
    d["dow"] = d.index.dayofweek.astype(float)
    d["volume_ratio"] = v / v.rolling(20).mean()
    d["vxx_chg"] = np.log(vx / vx.shift(1))
    d["vxx_level_z"] = (np.log(vx) - np.log(vx).rolling(63).mean()) / np.log(vx).rolling(63).std()
    d["last30_ret"] = np.log(c / bar_close(sym, "15:25"))
    d["ret5d"] = np.log(c / c.shift(5))
    return d.dropna()


IND = ["intraday_ret", "close_in_range", "rv21", "rv5_over_rv21", "rsi14",
       "dist_sma20", "prior_overnight", "dow", "volume_ratio", "vxx_chg",
       "vxx_level_z", "last30_ret", "ret5d"]

data = {s: build(s) for s in SYMS}
print(f"Rows after feature construction: "
      + ", ".join(f"{s}={len(data[s])}" for s in SYMS))
print(f"Train through {TRAIN_END.date()}, test after.\n")

# ------------------------------------------------------------------ A
print(banner("A.  UNIVARIATE PREDICTIVE REGRESSIONS (HAC standard errors)"))
print("target ~ a + b * z(indicator).  b is in bp of overnight return per 1 sd.")
print("With 13 indicators x 2 symbols = 26 tests, expect ~1.3 false positives at 5%.\n")
for s in SYMS:
    d = data[s]
    rows = []
    for f in IND:
        z = (d[f] - d[f].mean()) / d[f].std()
        X = sm.add_constant(z.values)
        m = sm.OLS(d["target"].values, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
        # same regression on train only, to see if the relationship is stable
        tr = d[d.index <= TRAIN_END]
        zt = (tr[f] - d[f].mean()) / d[f].std()
        mt = sm.OLS(tr["target"].values, sm.add_constant(zt.values)).fit(
            cov_type="HAC", cov_kwds={"maxlags": 5})
        te = d[d.index > TRAIN_END]
        ze = (te[f] - d[f].mean()) / d[f].std()
        me = sm.OLS(te["target"].values, sm.add_constant(ze.values)).fit(
            cov_type="HAC", cov_kwds={"maxlags": 5})
        rows.append({"indicator": f, "beta_bp": m.params[1] * 1e4, "t": m.tvalues[1],
                     "p": m.pvalues[1], "R2_pct": m.rsquared * 100,
                     "beta_train_bp": mt.params[1] * 1e4,
                     "beta_test_bp": me.params[1] * 1e4,
                     "sign_stable": "yes" if np.sign(mt.params[1]) == np.sign(me.params[1]) else "NO"})
    t = pd.DataFrame(rows).sort_values("t", key=abs, ascending=False).set_index("indicator")
    print(f"===== {s} =====")
    print(t.to_string(float_format=lambda x: f"{x:.4f}"))
    print(f"  significant at 5%: {list(t[t['p'] < 0.05].index)}")
    print(f"  ...of which sign-stable across train/test: "
          f"{list(t[(t['p'] < 0.05) & (t['sign_stable'] == 'yes')].index)}\n")

# ------------------------------------------------------------------ B
print(banner("B.  QUINTILE MONOTONICITY"))
print("Mean overnight return (bp) by indicator quintile. A monotone gradient is far")
print("more credible than one bucket standing out. Quintile edges from TRAIN only.\n")
mono = {}
for s in SYMS:
    d = data[s]
    tr = d[d.index <= TRAIN_END]
    rows = []
    for f in IND:
        edges = np.array(tr[f].quantile([0, .2, .4, .6, .8, 1.0]).values, dtype=float, copy=True)
        edges[0], edges[-1] = -np.inf, np.inf
        edges = np.unique(edges)
        if len(edges) < 3:
            continue
        q = pd.cut(d[f], edges, labels=False, duplicates="drop")
        means = d.groupby(q)["target"].mean() * 1e4
        # Spearman of bucket index vs bucket mean = monotonicity score
        rho = stats.spearmanr(means.index.values, means.values).statistic \
            if len(means) > 2 else np.nan
        rec = {"indicator": f}
        for i in range(len(means)):
            rec[f"Q{i+1}"] = means.iloc[i] if i < len(means) else np.nan
        rec["spread_Q5_Q1"] = means.iloc[-1] - means.iloc[0]
        rec["monotonicity"] = rho
        rows.append(rec)
    m = pd.DataFrame(rows).set_index("indicator")
    mono[s] = m
    print(f"===== {s} =====")
    print(m.to_string(float_format=lambda x: f"{x:.2f}"))
    print()

# ------------------------------------------------------------------ C
print(banner("C.  RULE BACKTESTS -- clean train-select / test-evaluate protocol"))
print("Each rule: go long overnight only when the indicator is in the top or bottom")
print("half / tercile, using the TRAIN-period breakpoint. 78 rules per symbol.\n")
for s in SYMS:
    d = data[s]
    tr = d[d.index <= TRAIN_END]
    base = d["target"]
    rules = []
    for f in IND:
        for frac, tag in [(0.5, "top50"), (0.5, "bot50"),
                          (1 / 3, "top33"), (1 / 3, "bot33"),
                          (0.25, "top25"), (0.25, "bot25")]:
            if tag.startswith("top"):
                thr = tr[f].quantile(1 - frac)
                mask = d[f] >= thr
            else:
                thr = tr[f].quantile(frac)
                mask = d[f] <= thr
            r = base.where(mask, 0.0)
            rules.append({
                "rule": f"{f}:{tag}", "exposure": mask.mean(),
                "sr_train": sharpe(r[r.index <= TRAIN_END]),
                "sr_test": sharpe(r[r.index > TRAIN_END]),
                "sr_full": sharpe(r),
                "ann_full": r.mean() * TRADING_DAYS,
                "maxdd": max_drawdown(r.cumsum()),
            })
    R = pd.DataFrame(rules)
    base_full, base_tr, base_te = sharpe(base), sharpe(base[base.index <= TRAIN_END]), \
        sharpe(base[base.index > TRAIN_END])
    R = R.sort_values("sr_train", ascending=False)
    rho = R["sr_train"].corr(R["sr_test"], method="spearman")
    w = R.iloc[0]
    print(f"===== {s} =====")
    print("Top 8 rules by TRAIN Sharpe:")
    print(R.head(8).to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(f"\n  UNGATED overnight baseline: full {base_full:.4f}  "
          f"train {base_tr:.4f}  TEST {base_te:.4f}")
    print(f"  Train-selected winner: {w['rule']}  train {w['sr_train']:.4f}  "
          f"-> TEST {w['sr_test']:.4f}")
    print(f"  Beat the ungated baseline out-of-sample? "
          f"{'YES' if w['sr_test'] > base_te else 'NO'}")
    print(f"  Spearman corr(train SR, test SR) across {len(R)} rules: {rho:+.4f}")
    print(f"  Rules beating baseline in TEST: "
          f"{int((R['sr_test'] > base_te).sum())} of {len(R)} "
          f"({(R['sr_test'] > base_te).mean():.0%}) -- "
          f"expected ~50% by chance if indicators are useless")
    print(f"  Winner's TEST rank: {int((R['sr_test'] > w['sr_test']).sum()) + 1} of {len(R)}\n")
    R.to_csv(OUT / f"p9_rules_{s}.csv", index=False)

# ------------------------------------------------------------------ D
print(banner("D.  MULTIVARIATE -- is there JOINT predictability?"))
print("All 13 indicators together. Fit on train, predict test. If overnight return")
print("is unpredictable, out-of-sample R2 will be <= 0.\n")
for s in SYMS:
    d = data[s]
    tr, te = d[d.index <= TRAIN_END], d[d.index > TRAIN_END]
    mu, sd = tr[IND].mean(), tr[IND].std()
    Xtr = sm.add_constant(((tr[IND] - mu) / sd).values)
    Xte = sm.add_constant(((te[IND] - mu) / sd).values)
    m = sm.OLS(tr["target"].values, Xtr).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    pred = m.predict(Xte)
    ss_res = float(((te["target"].values - pred) ** 2).sum())
    ss_tot = float(((te["target"].values - tr["target"].mean()) ** 2).sum())
    oos_r2 = 1 - ss_res / ss_tot
    # trade the sign of the forecast
    sig = np.sign(pred)
    r_dir = pd.Series(sig * te["target"].values, index=te.index)
    r_long = pd.Series(np.where(pred > 0, te["target"].values, 0.0), index=te.index)
    print(f"===== {s} =====")
    print(f"  in-sample R2 (train) : {m.rsquared*100:.3f}%   F-test p = {m.f_pvalue:.4f}")
    print(f"  OUT-OF-SAMPLE R2     : {oos_r2*100:+.3f}%   "
          f"{'(negative = worse than the train mean)' if oos_r2 < 0 else ''}")
    print(f"  forecast-sign hit rate on test: {(np.sign(pred) == np.sign(te['target'])).mean():.3f}")
    print(f"  trading the sign  : test SR {sharpe(r_dir):+.4f}")
    print(f"  long-when-positive: test SR {sharpe(r_long):+.4f}   "
          f"(ungated test SR {sharpe(te['target']):+.4f})")
    print()

print(banner("E.  DAY OF WEEK  (reported separately -- it is the one calendar effect)"))
for s in SYMS:
    d = data[s]
    lbl = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    g = d.groupby(d.index.dayofweek)["target"]
    t = pd.DataFrame({"n": g.size(), "mean_bp": g.mean() * 1e4,
                      "t_stat": g.mean() / (g.std() / np.sqrt(g.size())),
                      "hit": g.apply(lambda x: (x > 0).mean())})
    tr_ = d[d.index <= TRAIN_END].groupby(d[d.index <= TRAIN_END].index.dayofweek)["target"]
    te_ = d[d.index > TRAIN_END].groupby(d[d.index > TRAIN_END].index.dayofweek)["target"]
    t["mean_train_bp"] = tr_.mean() * 1e4
    t["mean_test_bp"] = te_.mean() * 1e4
    t.index = [lbl.get(i, i) for i in t.index]
    print(f"--- {s} (night FOLLOWING the named day) ---")
    print(t.to_string(float_format=lambda x: f"{x:.2f}"))
    print()
