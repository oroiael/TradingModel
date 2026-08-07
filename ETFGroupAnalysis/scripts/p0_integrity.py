"""Phase 0 -- data integrity and basis.  BLOCKING: nothing downstream is valid
until this passes.

T0.1 session grid completeness
T0.2 corporate-action / adjustment-basis scan
T0.3 cross-file alignment
T0.4 liquidity and capacity profile
T0.5 microstructure noise (signature plot) + spread estimation
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common import (BARS_PER_DAY, FULL_SESSION_BARS, OUT, SYMBOLS, banner,
                    load_raw, logret, session_ohlc)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

raw = {s: load_raw(s) for s in SYMBOLS}
sess = {s: session_ohlc(raw[s]) for s in SYMBOLS}

# ---------------------------------------------------------------- T0.1
print(banner("T0.1  SESSION GRID COMPLETENESS"))
rows = []
for s in SYMBOLS:
    d, k = raw[s], sess[s]
    bar_counts = k["bars"].value_counts().sort_index()
    partial = k[k["bars"] != FULL_SESSION_BARS]
    rows.append({
        "sym": s,
        "bars": len(d),
        "sessions": len(k),
        "first": k.index.min().date(),
        "last": k.index.max().date(),
        "years": round((k.index.max() - k.index.min()).days / 365.25, 2),
        "full_78": int((k["bars"] == FULL_SESSION_BARS).sum()),
        "half_42": int((k["bars"] == 42).sum()),
        "other": int(len(partial) - (k["bars"] == 42).sum()),
        "dup_ts": int(d["ts"].duplicated().sum()),
        "nan_close": int(d["Close"].isna().sum()),
        "nonpos_px": int((d[["Open", "High", "Low", "Close"]] <= 0).any(axis=1).sum()),
        "zero_vol_bars": int((d["Volume"] == 0).sum()),
        "ohlc_viol": int(((d["High"] < d[["Open", "Close"]].max(axis=1)) |
                          (d["Low"] > d[["Open", "Close"]].min(axis=1))).sum()),
    })
grid = pd.DataFrame(rows).set_index("sym")
print(grid.to_string())

print("\nSessions that are neither 78 nor 42 bars (anomalies):")
for s in SYMBOLS:
    k = sess[s]
    odd = k[~k["bars"].isin([FULL_SESSION_BARS, 42])]
    if len(odd) == 0:
        print(f"  {s}: none")
    else:
        print(f"  {s}: {len(odd)} sessions")
        print(odd[["bars", "first_bar", "last_bar", "close"]].tail(12).to_string())

print("\nFirst/last bar-of-day distribution:")
for s in SYMBOLS:
    d = raw[s]
    f = d.groupby("session")["tod"].first().value_counts()
    l = d.groupby("session")["tod"].last().value_counts()
    print(f"  {s}: first={dict(list(f.items())[:3])}  last={dict(list(l.items())[:4])}")

# ---------------------------------------------------------------- T0.2
print(banner("T0.2  CORPORATE ACTION / ADJUSTMENT BASIS SCAN"))
ca = {}
for s in SYMBOLS:
    k = sess[s].copy()
    k["prev_close"] = k["close"].shift(1)
    k["on_ratio"] = k["open"] / k["prev_close"]
    flag = k[(k["on_ratio"] < 0.6) | (k["on_ratio"] > 1.7)].dropna(subset=["on_ratio"])
    ca[s] = flag
    print(f"\n{s}: {len(flag)} session boundaries with open/prev_close outside [0.60, 1.70]")
    if len(flag):
        f = flag[["prev_close", "open", "on_ratio"]].copy()
        f["implied_1_for_N"] = 1.0 / f["on_ratio"]
        f["implied_N_for_1"] = f["on_ratio"]
        print(f.to_string())
    # widest ordinary gaps for context
    ok = k.dropna(subset=["on_ratio"])
    ok = ok[(ok["on_ratio"] >= 0.6) & (ok["on_ratio"] <= 1.7)]
    print(f"  ordinary overnight gap range: {ok['on_ratio'].min():.4f} .. "
          f"{ok['on_ratio'].max():.4f}   (n={len(ok)})")

print("\nPrice level trajectory (year-end close) -- reveals adjustment basis:")
lvl = pd.DataFrame({s: sess[s]["close"].resample("YE").last() for s in SYMBOLS})
print(lvl.to_string(float_format=lambda x: f"{x:,.2f}"))

# ---------------------------------------------------------------- T0.3
print(banner("T0.3  CROSS-FILE ALIGNMENT"))
sets = {s: set(sess[s].index) for s in SYMBOLS}
common = set.intersection(*sets.values())
union = set.union(*sets.values())
print(f"sessions: union={len(union)}  intersection={len(common)}")
for s in SYMBOLS:
    only = sets[s] - set.union(*[sets[o] for o in SYMBOLS if o != s])
    print(f"  {s}: {len(sets[s])} sessions, {len(sets[s] - common)} not in all-three, "
          f"{len(only)} unique to {s}")
missing = {s: sorted(common_d for common_d in (union - sets[s])) for s in SYMBOLS}
for s in SYMBOLS:
    m = missing[s]
    if m:
        print(f"  {s} missing {len(m)} sessions present elsewhere, e.g. "
              f"{[d.date().isoformat() for d in m[:6]]}")

ts_sets = {s: set(raw[s]["ts"]) for s in SYMBOLS}
ts_common = set.intersection(*ts_sets.values())
print(f"\n5-min timestamps: union={len(set.union(*ts_sets.values())):,}  "
      f"intersection={len(ts_common):,}")
for s in SYMBOLS:
    print(f"  {s}: {len(ts_sets[s]):,} stamps, {len(ts_sets[s]) - len(ts_common):,} "
          f"not shared by all three")

common_sessions = sorted(common)
print(f"\nUsable common window: {min(common_sessions).date()} -> "
      f"{max(common_sessions).date()}  ({len(common_sessions)} sessions)")

# ---------------------------------------------------------------- T0.4
print(banner("T0.4  LIQUIDITY AND CAPACITY PROFILE"))
liq_rows = []
for s in SYMBOLS:
    d = raw[s].copy()
    d["notional"] = d["Close"] * d["Volume"]
    # last 2 years only -- capacity today is what matters, not 2020
    recent = d[d["ts"] >= d["ts"].max() - pd.Timedelta(days=730)]
    liq_rows.append({
        "sym": s,
        "med_bar_notional_$": recent["notional"].median(),
        "p05_bar_notional_$": recent["notional"].quantile(0.05),
        "med_daily_notional_$": recent.groupby("session")["notional"].sum().median(),
        "med_bar_shares": recent["Volume"].median(),
        "max_ord_1pct_$": recent["notional"].quantile(0.05) * 0.01,
        "max_ord_5pct_$": recent["notional"].quantile(0.05) * 0.05,
        "last_px": recent["Close"].iloc[-1],
    })
liq = pd.DataFrame(liq_rows).set_index("sym")
print("Trailing 2 years:")
print(liq.to_string(float_format=lambda x: f"{x:,.0f}"))

print("\nMedian bar notional by time of day (trailing 2y, $):")
tod_tab = {}
for s in SYMBOLS:
    d = raw[s].copy()
    d = d[d["ts"] >= d["ts"].max() - pd.Timedelta(days=730)]
    d["notional"] = d["Close"] * d["Volume"]
    tod_tab[s] = d.groupby("tod")["notional"].median()
tod_df = pd.DataFrame(tod_tab)
show = tod_df.iloc[::6]  # every 30 minutes
print(show.to_string(float_format=lambda x: f"{x:,.0f}"))

# Amihud illiquidity: |return| per $1M traded, daily, trailing 2y
print("\nAmihud illiquidity (|daily return| per $1M daily notional, trailing 2y):")
for s in SYMBOLS:
    k = sess[s].copy()
    k["ret"] = k["close"].pct_change()
    d = raw[s].copy()
    d["notional"] = d["Close"] * d["Volume"]
    k["notional"] = d.groupby("session")["notional"].sum().values
    k = k[k.index >= k.index.max() - pd.Timedelta(days=730)]
    am = (k["ret"].abs() / (k["notional"] / 1e6)).median()
    print(f"  {s}: {am:.3e}")

# ---------------------------------------------------------------- T0.5
print(banner("T0.5  MICROSTRUCTURE NOISE -- SIGNATURE PLOT + SPREAD ESTIMATES"))
print("Realized variance annualized (%), by sampling interval.")
print("A flat row = efficient prices. Rising toward the left = bid-ask bounce.\n")
sig_rows = {}
for s in SYMBOLS:
    d = raw[s].set_index("ts")["Close"]
    row = {}
    for k_bars, label in [(1, "5min"), (2, "10min"), (3, "15min"), (6, "30min"),
                          (12, "1h"), (39, "half-day"), (78, "1day")]:
        px = d.iloc[::k_bars]
        r = np.log(px / px.shift(1)).dropna()
        # scale each sampling frequency to an annualized vol
        per_year = 252.0 * (BARS_PER_DAY / k_bars)
        row[label] = float(r.std(ddof=1) * np.sqrt(per_year) * 100)
    sig_rows[s] = row
sig = pd.DataFrame(sig_rows).T
print(sig.to_string(float_format=lambda x: f"{x:.2f}"))

print("\nFirst-order autocorrelation of 5-min returns (Roll's negative-ACF signature):")
roll_rows = []
for s in SYMBOLS:
    d = raw[s]
    r = logret(d["Close"]).dropna()
    ac1 = r.autocorr(lag=1)
    # Roll (1984): spread = 2*sqrt(-cov) when cov < 0
    cov1 = r.cov(r.shift(1))
    roll_spread = 2 * np.sqrt(-cov1) if cov1 < 0 else np.nan
    roll_rows.append({"sym": s, "acf1_5min": ac1, "cov1": cov1,
                      "roll_spread_bp": roll_spread * 1e4 if cov1 < 0 else np.nan})
print(pd.DataFrame(roll_rows).set_index("sym").to_string())


def corwin_schultz(high: pd.Series, low: pd.Series) -> pd.Series:
    """Corwin-Schultz (2012) two-day high-low spread estimator, as a fraction."""
    h2 = np.maximum(high, high.shift(1))
    l2 = np.minimum(low, low.shift(1))
    beta = (np.log(high / low) ** 2) + (np.log(high.shift(1) / low.shift(1)) ** 2)
    gamma = np.log(h2 / l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return s


print("\nCorwin-Schultz spread estimate from daily high/low (trailing 2y):")
cs_rows = []
for s in SYMBOLS:
    k = sess[s]
    k = k[k.index >= k.index.max() - pd.Timedelta(days=730)]
    cs = corwin_schultz(k["high"], k["low"]).dropna()
    cs_pos = cs[cs > 0]  # negative estimates are set to zero per the paper
    cs_rows.append({
        "sym": s,
        "median_bp": float(cs_pos.median() * 1e4),
        "mean_bp": float(np.maximum(cs, 0).mean() * 1e4),
        "pct_negative_est": float((cs <= 0).mean() * 100),
    })
print(pd.DataFrame(cs_rows).set_index("sym").to_string(float_format=lambda x: f"{x:.2f}"))
print("\nNOTE: negative Corwin-Schultz estimates are a known artifact and are floored at 0.")
print("These are ESTIMATES. No quote data exists in this repo to validate them against.")

# persist for later phases
grid.to_csv(OUT / "p0_grid_summary.csv")
sig.to_csv(OUT / "p0_signature_plot.csv")
print(f"\n[saved] {OUT}/p0_grid_summary.csv, p0_signature_plot.csv")
