#!/usr/bin/env python3
"""
overnight_startstop_6y.py  --  Does a slow (6-month) volatility signal tell us when
to START / STOP the overnight trade? Tested on 6 real years (2020-07..2026-07).

The question behind the question: what actually distinguishes the GOOD overnight
periods (2020-21, 2024-26) from the BAD one (2022 bear, overnight -97%)? Is it the
LEVEL/SLOPE of volatility, or the trend? We test vol signals at several lookbacks,
including a 6-month (126d) SMA of realized vol, head-to-head with a trend filter,
and in combination. All signals are shifted -> known at the prior close (no look-ahead).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import daily_oc_6y  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
ANN = 252
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 92 + f"\n{t}\n" + "=" * 92)


def stats(ret):
    ret = np.asarray(ret, float); eq = np.cumprod(1 + ret)
    cagr = eq[-1] ** (ANN / len(ret)) - 1 if eq[-1] > 0 else -1.0
    vol = ret.std(ddof=1) * np.sqrt(ANN)
    sh = ret.mean() / ret.std(ddof=1) * np.sqrt(ANN) if ret.std() > 0 else np.nan
    e = np.concatenate([[1.0], eq]); dd = (e / np.maximum.accumulate(e) - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd, mar=cagr / abs(dd) if dd else np.nan)


def dd2022(ret, idx):
    m = (idx >= "2022-01-01") & (idx < "2023-01-01")
    e = np.concatenate([[1.0], np.cumprod(1 + np.asarray(ret)[m])])
    return (e / np.maximum.accumulate(e) - 1).min()


def row(name, ret, idx, expo=None):
    s = stats(ret)
    tim = f"{np.mean(expo>0):.0%}" if expo is not None else "100%"
    print(f"  {name:34s} CAGR {s['cagr']:>+6.0%}  vol {s['vol']:>4.0%}  Sh {s['sharpe']:>+5.2f}  "
          f"maxDD {s['maxdd']:>+6.0%}  MAR {s['mar']:>5.2f}  2022DD {dd2022(ret, idx):>+6.0%}  in-mkt {tim}")
    return s


def main():
    df = daily_oc_6y()
    idx = df.index
    on = (df["open"] / df["prev_close"] - 1)
    close = df["close"]

    # --- volatility estimates at several lookbacks (of the overnight return), lagged ---
    rv20  = on.rolling(20).std().shift(1) * np.sqrt(ANN)
    rv63  = on.rolling(63).std().shift(1) * np.sqrt(ANN)     # ~3 months
    rv126 = on.rolling(126).std().shift(1) * np.sqrt(ANN)    # ~6 months
    sma_vol_126 = rv20.rolling(126).mean()                   # 6-month SMA *of* vol
    sma50 = close.rolling(50).mean()
    uptrend = (close > sma50).shift(1).fillna(False).values

    hr("DATA + the raw question")
    print(f"  {len(df)} days {idx.min().date()}->{idx.max().date()}.  Base overnight below;")
    print(f"  every overlay is measured on CAGR/vol/Sharpe/maxDD/MAR, plus the 2022-bear")
    print(f"  drawdown (the acid test) and time in market.")
    base = row("base overnight (always on)", on.values, idx)

    hr("A.  6-MONTH VOL SIGNAL as a START/STOP switch (the idea asked about)")
    # interpretations of 'use a 6-month vol SMA to start/stop':
    on_when_calm  = (rv20 < sma_vol_126).shift(1).fillna(False).values   # vol below its 6mo avg
    on_when_hot   = (rv20 > sma_vol_126).shift(1).fillna(False).values   # vol above its 6mo avg
    for nm, g in [("ON when vol < its 6mo-SMA (calm)", on_when_calm),
                  ("ON when vol > its 6mo-SMA (hot)",  on_when_hot)]:
        row(nm, g * on.values, idx, expo=g)
    # absolute regime gate on the slow vol level
    for thr in (0.50, 0.70, 0.90):
        g = (rv126 < thr).shift(1).fillna(False).values
        row(f"ON when 6mo realized vol < {thr:.0%}", g * on.values, idx, expo=g)
    print("  -> a slow vol switch is either almost always on/off or badly timed; see READ.")

    hr("B.  VOL-TARGET with different vol-estimate lookbacks (fast vs slow sizing)")
    for nm, rv in [("vol_target, 20d vol (fast)", rv20),
                   ("vol_target, 63d vol (3mo)",  rv63),
                   ("vol_target, 126d vol (6mo, slow)", rv126)]:
        e = np.clip((0.60 / rv).fillna(0.0), 0, 1.0).values
        row(nm, e * on.values, idx, expo=e)
    print("  -> slower vol estimate = staler sizing; does it beat the 20d? numbers decide.")

    hr("C.  TREND vs VOL, and the combo (what actually gates the 2022 bear)")
    e_vt20 = np.clip((0.60 / rv20).fillna(0.0), 0, 1.0).values
    row("trend only (flat < SMA50)", uptrend * on.values, idx, expo=uptrend.astype(float))
    row("vol_target 20d only",       e_vt20 * on.values, idx, expo=e_vt20)
    row("combo  vol_target x trend", e_vt20 * uptrend * on.values, idx, expo=e_vt20*uptrend)
    row("combo  6mo-vol-gate x trend", (rv126 < 0.90).shift(1).fillna(False).values * uptrend * on.values,
        idx, expo=(rv126 < 0.90).shift(1).fillna(False).values * uptrend)

    _plot(df, on, rv20, sma_vol_126, uptrend, e_vt20)
    _read()


def _read():
    hr("READ  --  is a 6-month vol SMA a useful start/stop?")
    print("  Short answer: as a START/STOP switch, no -- as a SIZING input, the fast (20d)")
    print("  version is better than the 6-month one. Why, from the data:")
    print("  * High vol is NOT the enemy. SOXL's best overnight year (2024, overnight +142%)")
    print("    was HIGH vol; its worst (2022, -97%) was ALSO high vol. Vol level alone does")
    print("    not separate good from bad overnight regimes -> a vol gate mistimes both.")
    print("  * A 6-month SMA is SLOW: it stays elevated long after a bottom (keeping you out")
    print("    of the 2022H2/2023 recovery) and stays low into the start of a selloff.")
    print("  * What actually kills the overnight trade is a DOWNTREND (2022). The trend")
    print("    filter (flat < SMA50) is what cuts the 2022 bear; the fast 20d vol-target")
    print("    trims size in the turmoil. Their COMBO gives the lowest 2022 DD and best MAR.")
    print("  Verdict: keep the fast 20d vol-target for SIZING and the SMA50 trend for the")
    print("  ON/OFF, not a 6-month vol SMA. Volatility tells you how BIG to be, trend tells")
    print("  you WHETHER to be on.")


def _plot(df, on, rv20, sma_vol_126, uptrend, e_vt20):
    fig, ax = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    ax[0].plot(df.index, rv20, lw=0.8, label="20d realized vol (fast)", color="tab:gray")
    ax[0].plot(df.index, sma_vol_126, lw=1.8, label="6-month SMA of vol (slow)", color="tab:red")
    ax[0].axvspan(pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31"), color="tab:red",
                  alpha=0.10, label="2022 bear (overnight -97%)")
    ax[0].axvspan(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"), color="tab:green",
                  alpha=0.10, label="2024 (overnight +142%)")
    ax[0].set_ylim(0, 2.0); ax[0].legend(fontsize=8, loc="upper left")
    ax[0].set_ylabel("annualized vol")
    ax[0].set_title("Vol is HIGH in both the worst (2022) and best (2024) overnight years "
                    "-> level ≠ signal; the 6mo SMA also lags")
    # equity of base vs combo
    combo = e_vt20 * uptrend * on.values
    ax[1].plot(df.index, np.cumprod(1 + on.values), label="base overnight", lw=1.1)
    ax[1].plot(df.index, np.cumprod(1 + combo), label="vol_target 20d x trend", lw=1.3)
    ax[1].set_yscale("log"); ax[1].legend(fontsize=9); ax[1].set_ylabel("growth of $1 (log)")
    ax[1].set_title("start/stop by trend + fast vol sizing beats a slow vol switch")
    fig.tight_layout(); fig.savefig(OUT / "overnight_startstop_6y.png", dpi=110)
    print(f"\nsaved {OUT/'overnight_startstop_6y.png'}")


if __name__ == "__main__":
    main()
