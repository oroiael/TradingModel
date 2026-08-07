"""Cross-instrument leading indicators: build the aggregated feature panel.

p2 tested 5-minute returns -> returns at lags +/-6 bars and found nothing above
|0.014|.  That test was narrow in two ways this module fixes:

  1. It only used 5-minute aggregation.  Here: last hour of the session, the
     full session, the prior session (a two-day lead), and a 5-day window.
  2. It only predicted DIRECTION.  Direction is the hardest thing to predict.
     "Moves" can also mean MAGNITUDE, which is far more tractable and is where
     cross-asset information usually lives.

Critical control: realized volatility is strongly autocorrelated, so "VXX vol
today predicts SPXL vol tomorrow" is trivially true and tells us nothing -- both
series are persistent and contemporaneously correlated.  Every regression in
p12 therefore includes the TARGET'S OWN LAG as a control, and the question is
only whether the cross-instrument term adds anything beyond it.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from common import OUT, TRADING_DAYS, banner, load_raw, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

SYMS = ["SPXL", "FAS", "VXX"]
BARS_PER_DAY = 78

raw = {s: load_raw(s) for s in SYMS}
sess = {s: session_ohlc(raw[s]) for s in SYMS}
for s in SYMS:
    sess[s] = sess[s][sess[s]["bars"] >= 42]      # drop the truncated SPXL session
common = sorted(set.intersection(*[set(sess[s].index) for s in SYMS]))


def intraday(sym: str) -> pd.DataFrame:
    """5-min bars with intra-session log returns; overnight gap excluded."""
    d = raw[sym].copy()
    d["r"] = np.log(d["Close"] / d["Close"].shift(1))
    d["same"] = d["session"] == d["session"].shift(1)
    d.loc[~d["same"], "r"] = np.nan
    d["session"] = pd.to_datetime(d["session"])
    return d[d["session"].isin(common)]


def window_features(d: pd.DataFrame, lo: str, hi: str, tag: str) -> pd.DataFrame:
    """Features computed over one intraday window, one row per session."""
    m = d[(d["tod"] >= pd.Timestamp(lo).time()) & (d["tod"] <= pd.Timestamp(hi).time())]
    g = m.groupby("session")
    r = g["r"]
    out = pd.DataFrame(index=sorted(m["session"].unique()))

    out[f"{tag}_ret"] = r.sum()
    # realized volatility from 5-min squared returns, annualized
    n_bars = r.count()
    out[f"{tag}_rv"] = np.sqrt(r.apply(lambda x: np.nansum(x ** 2))
                               * (BARS_PER_DAY / n_bars) * TRADING_DAYS)
    out[f"{tag}_logrv"] = np.log(out[f"{tag}_rv"].replace(0, np.nan))
    # bipower variation -> jump share.  BV is robust to jumps, RV is not, so
    # 1 - BV/RV isolates the discontinuous part of the move.  Non-standard for
    # ETFs; standard in the realized-volatility literature.
    def bipow(x):
        a = np.abs(x.values)
        a = a[~np.isnan(a)]
        return (np.pi / 2) * np.nansum(a[1:] * a[:-1]) if a.size > 2 else np.nan
    rv_raw = r.apply(lambda x: np.nansum(x.values ** 2))
    bv_raw = r.apply(bipow)
    out[f"{tag}_ss"] = rv_raw          # raw sum of squared 5-min returns
    out[f"{tag}_jump"] = (1 - bv_raw / rv_raw.replace(0, np.nan)).clip(-1, 1)
    # dollar volume and its own 20d-relative level
    dv = m.assign(dv=m["Close"] * m["Volume"]).groupby("session")["dv"].sum()
    out[f"{tag}_dvol"] = dv
    out[f"{tag}_volratio"] = dv / dv.rolling(20).mean()
    # range and where the window closed inside it
    hi_ = g["High"].max(); lo_ = g["Low"].min(); cl = g["Close"].last()
    out[f"{tag}_range"] = (hi_ - lo_) / cl
    out[f"{tag}_cir"] = (cl - lo_) / (hi_ - lo_).replace(0, np.nan)
    # signed-volume imbalance: share of window volume printed on up bars
    sv = m.assign(s=np.sign(m["r"]).fillna(0) * m["Close"] * m["Volume"])
    out[f"{tag}_ofi"] = sv.groupby("session")["s"].sum() / dv.replace(0, np.nan)
    # dispersion of 5-min returns within the window (intraday churn)
    out[f"{tag}_disp"] = r.std()
    # largest single 5-min absolute move (tail proxy)
    out[f"{tag}_maxabs"] = r.apply(lambda x: np.nanmax(np.abs(x)) if x.notna().any() else np.nan)
    # Amihud: |window return| per $1M traded
    out[f"{tag}_amihud"] = out[f"{tag}_ret"].abs() / (dv / 1e6).replace(0, np.nan)
    out.index = pd.to_datetime(out.index)
    return out


print(banner("BUILDING THE AGGREGATED PANEL"))
panel = {}
for s in SYMS:
    d = intraday(s)
    lasthr = window_features(d, "15:00", "15:55", "lasthr")
    firsthr = window_features(d, "09:30", "10:25", "firsthr")
    fullday = window_features(d, "09:30", "15:55", "day")
    k = sess[s].loc[common]
    extra = pd.DataFrame(index=k.index)
    extra["overnight"] = np.log(k["open"] / k["close"].shift(1))
    extra["cc_ret"] = np.log(k["close"] / k["close"].shift(1))
    p = pd.concat([lasthr, firsthr, fullday, extra], axis=1).reindex(common)
    # multi-day aggregates
    p["d2_ret"] = p["day_ret"].rolling(2).sum()
    p["d5_ret"] = p["day_ret"].rolling(5).sum()
    p["d5_logrv"] = np.log(np.sqrt((p["day_rv"] ** 2).rolling(5).mean()))
    p["d5_volratio"] = p["day_dvol"].rolling(5).mean() / p["day_dvol"].rolling(20).mean()
    # share of the day's total squared return that landed in the last hour.
    # Must use RAW sums of squares -- dividing the ANNUALIZED rv's inflates this
    # by BARS_PER_DAY/12 = 6.5x, which is what a first version of this did.
    p["lasthr_share"] = p["lasthr_ss"] / p["day_ss"].replace(0, np.nan)
    p["firsthr_share"] = p["firsthr_ss"] / p["day_ss"].replace(0, np.nan)
    panel[s] = p
    print(f"  {s}: {p.shape[1]} features x {len(p)} sessions")

full = pd.concat({s: panel[s] for s in SYMS}, axis=1)
full.columns = [f"{a}.{b}" for a, b in full.columns]
full = full.sort_index()
print(f"\nCombined panel: {full.shape[0]} sessions x {full.shape[1]} columns")
print(f"Range: {full.index.min().date()} -> {full.index.max().date()}")

print("\nSanity: annualized realized vol by window (median), should rank VXX>FAS>SPXL")
for s in SYMS:
    p = panel[s]
    print(f"  {s}: lasthr {p['lasthr_rv'].median():.3f}  firsthr {p['firsthr_rv'].median():.3f}  "
          f"day {p['day_rv'].median():.3f}   jump-share median {p['day_jump'].median():.3f}")

print("\nSanity: share of the day's squared return by window (median)")
print("  12 of 77 return-bars = 0.156 if variance were uniform through the session")
for s in SYMS:
    print(f"  {s}: last hour {panel[s]['lasthr_share'].median():.3f}   "
          f"first hour {panel[s]['firsthr_share'].median():.3f}")

full.to_csv(OUT / "p11_panel.csv")
print(f"\n[saved] {OUT}/p11_panel.csv")
