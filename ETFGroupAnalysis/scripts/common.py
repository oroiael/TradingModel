"""Shared loading and helpers for the ETF group analysis.

Data source: the three 5-minute CSVs live at the repository root as Git LFS
objects (`git lfs pull` required).  Set ETF_DATA_DIR to read them from
somewhere else.  Nothing here mutates or rewrites the source files.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("ETF_DATA_DIR", REPO))
OUT = Path(__file__).resolve().parents[1] / "out"
OUT.mkdir(exist_ok=True)

SYMBOLS = ["SPXL", "FAS", "VXX"]
FILES = {s: f"{s}_5min_6Years.csv" for s in SYMBOLS}

# Full RTH session on this grid is 09:30 -> 15:55 inclusive = 78 bars.
FULL_SESSION_BARS = 78


def load_raw(symbol: str) -> pd.DataFrame:
    """Load one 5-minute file exactly as delivered, with a parsed timestamp.

    The Date column is 'YYYYMMDD HH:MM:SS America/New_York'.  The trailing zone
    name is constant across the file, so it is stripped and the stamp is treated
    as naive New York local time -- which is what every downstream session
    grouping wants.
    """
    p = DATA_DIR / FILES[symbol]
    if p.stat().st_size < 10_000:
        raise RuntimeError(
            f"{p} is {p.stat().st_size} bytes -- still a Git LFS pointer. "
            f"Run: git lfs pull --include='{FILES[symbol]}'")
    df = pd.read_csv(p)
    stamp = df["Date"].str.slice(0, 17)
    df["ts"] = pd.to_datetime(stamp, format="%Y%m%d %H:%M:%S")
    df["session"] = df["ts"].dt.date
    df["tod"] = df["ts"].dt.time
    df = df.drop(columns=["Date"]).sort_values("ts", ignore_index=True)
    for c in ("Open", "High", "Low", "Close", "Volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def session_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse 5-minute bars to one row per session."""
    g = df.groupby("session", sort=True)
    out = pd.DataFrame({
        "open": g["Open"].first(),
        "high": g["High"].max(),
        "low": g["Low"].min(),
        "close": g["Close"].last(),
        "volume": g["Volume"].sum(),
        "bars": g.size(),
        "first_bar": g["ts"].first(),
        "last_bar": g["ts"].last(),
    })
    out.index = pd.to_datetime(out.index)
    return out


def logret(s: pd.Series) -> pd.Series:
    return np.log(s / s.shift(1))


def ann_factor(bars_per_year: float) -> float:
    return np.sqrt(bars_per_year)


TRADING_DAYS = 252.0
BARS_PER_DAY = 78.0


def fmt_pct(x: float, nd: int = 2) -> str:
    return f"{100 * x:.{nd}f}%"


def describe_returns(r: pd.Series, per_year: float) -> dict:
    """Standard moment/risk summary for a return series."""
    r = r.dropna()
    ann_mu = r.mean() * per_year
    ann_sd = r.std(ddof=1) * np.sqrt(per_year)
    return {
        "n": int(r.size),
        "mean_bp": float(r.mean() * 1e4),
        "ann_return": float(ann_mu),
        "ann_vol": float(ann_sd),
        "sharpe": float(ann_mu / ann_sd) if ann_sd > 0 else np.nan,
        "skew": float(r.skew()),
        "kurtosis": float(r.kurtosis()),  # excess
        "min": float(r.min()),
        "max": float(r.max()),
    }


def max_drawdown(cum_log: pd.Series) -> float:
    """Max drawdown from a cumulative *log* return series, returned as a fraction."""
    eq = np.exp(cum_log)
    return float((eq / eq.cummax() - 1.0).min())


def banner(title: str, ch: str = "=", w: int = 78) -> str:
    return f"\n{ch * w}\n{title}\n{ch * w}"


def variance_ratio(x: np.ndarray, q: int):
    """Lo-MacKinlay VR(q) with heteroskedasticity-robust z-statistic."""
    x = np.asarray(x, dtype=float)
    n = x.size
    mu = x.mean()
    var1 = np.sum((x - mu) ** 2) / (n - 1)
    # overlapping q-period sums
    cs = np.concatenate([[0.0], np.cumsum(x)])
    qsum = cs[q:] - cs[:-q]
    m = q * (n - q + 1) * (1 - q / n)
    varq = np.sum((qsum - q * mu) ** 2) / m
    vr = varq / var1
    # Heteroskedasticity-consistent variance (Lo-MacKinlay 1988, eq. 18).
    # delta_j is O(1/n), so theta is O(1/n) and the sqrt(n) scaling of the
    # z-statistic is already embedded -- do NOT multiply delta by n.
    d = (x - mu) ** 2
    denom = np.sum(d) ** 2
    theta = 0.0
    for j in range(1, q):
        delta = np.sum(d[j:] * d[:-j]) / denom
        theta += ((2 * (q - j) / q) ** 2) * delta
    z = (vr - 1) / np.sqrt(theta) if theta > 0 else np.nan
    p = 2 * (1 - stats.norm.cdf(abs(z))) if np.isfinite(z) else np.nan
    return vr, z, p


def dfa_hurst(x: np.ndarray, scales=None):
    """Detrended fluctuation analysis -> Hurst exponent."""
    x = np.asarray(x, dtype=float)
    y = np.cumsum(x - x.mean())
    n = y.size
    if scales is None:
        scales = np.unique(np.logspace(np.log10(16), np.log10(n // 8), 22).astype(int))
    F = []
    for sc in scales:
        nseg = n // sc
        if nseg < 4:
            F.append(np.nan); continue
        seg = y[:nseg * sc].reshape(nseg, sc)
        t = np.arange(sc)
        # detrend each segment linearly
        A = np.vstack([t, np.ones(sc)]).T
        coef, *_ = np.linalg.lstsq(A, seg.T, rcond=None)
        resid = seg.T - A @ coef
        F.append(np.sqrt(np.mean(resid ** 2)))
    F = np.array(F, dtype=float)
    ok = np.isfinite(F) & (F > 0)
    h, _ = np.polyfit(np.log(scales[ok]), np.log(F[ok]), 1)
    return float(h)
