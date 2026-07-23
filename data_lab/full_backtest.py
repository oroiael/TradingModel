#!/usr/bin/env python3
"""
full_backtest.py  --  ONE unified backtest of the entire book from $100,000, built on
the VALIDATED per-cycle bracket engine (debug_bracket.run / bracket_weekly.run_structure,
which passed the exit audit at +38% intrinsic). A continuous *daily* bracket builder was
tried and DISCARDED: it disagreed with the audited per-cycle number by ~2x (2022 +210%
vs a sane +59%) and could not be validated, so it is not used here.

Book (the "optimistic" exit the user chose):
  A = gated overnight ETF (vol_target x trend)         -- compounded within each week
  B = VRP-gated weekly ATM straddle, delta-hedged,     -- settled at EXERCISE/INTRINSIC
      per-cycle P&L (weekly sizing: set position at entry from equity, hold to expiry)
Weekly rebalance to fixed weights, winnings reinvested, start $100k, cash-collateralized
1x notional. Also shows the PESSIMISTIC (sell-at-bid) bracket so the range is explicit.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "call_spread_lab"))
sys.path.insert(0, str(HERE))
from data_loader import daily_oc_6y  # noqa: E402
from debug_bracket import cycles, run  # validated per-cycle bracket  # noqa: E402
from bracket_weekly import weekly_cycles, run_structure  # gives entry implied vol  # noqa: E402

OUT = HERE / "outputs"; OUT.mkdir(exist_ok=True)
ANN = 252; WKS = 52; CAP0 = 100_000
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 92 + f"\n{t}\n" + "=" * 92)


def wk_stats(path, cap0=CAP0):
    eq = np.concatenate([[cap0], path]); ret = eq[1:] / eq[:-1] - 1
    cagr = (path[-1] / cap0) ** (WKS / len(path)) - 1 if path[-1] > 0 else -1.0
    sh = ret.mean() / ret.std(ddof=1) * np.sqrt(WKS) if ret.std() > 0 else np.nan
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    return dict(final=path[-1], cagr=cagr, vol=ret.std(ddof=1) * np.sqrt(WKS), sharpe=sh,
                maxdd=dd, mar=cagr / abs(dd) if dd else np.nan)


def compound(weekly_ret, cap0=CAP0):
    return cap0 * np.cumprod(1 + np.asarray(weekly_ret, float))


def main():
    hr("BUILD the two sleeves per weekly cycle (validated engine)")
    o = cycles()
    b_intr = run(o, "expiry_intrinsic")[["date", "exp", "pnl"]].rename(columns={"pnl": "b_intr"})
    b_bid = run(o, "expiry_bid")[["date", "exp"]].assign(b_bid=run(o, "expiry_bid")["pnl"].values)
    iv = run_structure(weekly_cycles(__import__("data_loader").load_options()), 0.0, +1)[["date", "iv"]]
    df = b_intr.merge(b_bid[["date", "b_bid"]], on="date").merge(iv, on="date")

    # overnight sleeve (gated vt x trend), compounded within each cycle window
    d = daily_oc_6y()
    on = (d["open"] / d["prev_close"] - 1)
    rv = on.rolling(20).std().shift(1) * np.sqrt(ANN)
    up = (d["close"] > d["close"].rolling(50).mean()).shift(1).fillna(False)
    e_vt = np.clip((0.60 / rv).fillna(0.0), 0, 1.0)
    gated = (e_vt * up * on).dropna()
    cc = np.log(d["close"] / d["close"].shift(1)); trail = cc.rolling(20).std() * np.sqrt(ANN)

    def cyc(t0, exp):
        w = gated[(gated.index > pd.Timestamp(t0)) & (gated.index <= pd.Timestamp(exp))]
        return float((1 + w).prod() - 1) if len(w) else np.nan

    df["on"] = [cyc(df["date"].iloc[i], df["exp"].iloc[i]) for i in range(len(df))]
    df["trv"] = [float(trail.asof(pd.Timestamp(t))) for t in df["date"]]
    df = df.dropna().reset_index(drop=True); df["yr"] = df["date"].dt.year
    # VRP gate on the bracket only (asymmetric, as established)
    gate_on = (df["trv"] >= 0.9 * df["iv"]).values
    df["bg_intr"] = np.where(gate_on, df["b_intr"], 0.0)      # gated bracket, intrinsic
    df["bg_bid"] = np.where(gate_on, df["b_bid"], 0.0)        # gated bracket, bid
    print(f"  {len(df)} weekly cycles {df['date'].min().date()}..{df['date'].max().date()} | "
          f"bracket gate ON {gate_on.mean():.0%} of weeks")

    hr("VALIDATE bracket sleeve vs audit (ungated intrinsic must be ~+38%)")
    s = wk_stats(compound(df["b_intr"]))
    print(f"  ungated bracket @ intrinsic: CAGR {s['cagr']:+.0%}  Sharpe {s['sharpe']:+.2f}  "
          f"{'OK' if abs(s['cagr']-0.38)<0.10 else 'off'}")

    hr("FULL BACKTEST from $100,000 -- OPTIMISTIC exit (exercise @ intrinsic), gated")
    allocs = {"100% overnight": 1.0, "70/30 overnight/bracket": 0.7, "50/50": 0.5,
              "40/60": 0.4, "30/70": 0.3, "100% bracket": 0.0}
    print(f"  {'allocation':24s} {'final $':>12} {'CAGR':>6} {'vol':>5} {'Sharpe':>7} "
          f"{'maxDD(wkly)':>12} {'MAR':>5}")
    paths = {}
    for name, w in allocs.items():
        p = compound(w * df["on"].values + (1 - w) * df["bg_intr"].values); paths[name] = p
        s = wk_stats(p)
        print(f"  {name:24s} {s['final']:>12,.0f} {s['cagr']:>+6.0%} {s['vol']:>5.0%} "
              f"{s['sharpe']:>+7.2f} {s['maxdd']:>+12.0%} {s['mar']:>5.2f}")

    hr("SAME allocations under the PESSIMISTIC exit (sell @ bid) -- the honest floor")
    print(f"  {'allocation':24s} {'final $':>12} {'CAGR':>6} {'Sharpe':>7} {'maxDD(wkly)':>12}")
    for name, w in allocs.items():
        p = compound(w * df["on"].values + (1 - w) * df["bg_bid"].values)
        s = wk_stats(p)
        print(f"  {name:24s} {s['final']:>12,.0f} {s['cagr']:>+6.0%} {s['sharpe']:>+7.2f} {s['maxdd']:>+12.0%}")

    hr("HEADLINE 50/50 book, optimistic exit: by-year")
    w = 0.5; p = compound(w * df["on"].values + (1 - w) * df["bg_intr"].values); s = wk_stats(p)
    df["bl"] = w * df["on"].values + (1 - w) * df["bg_intr"].values
    print(f"  $100,000 -> ${s['final']:,.0f}  CAGR {s['cagr']:+.0%}  Sharpe {s['sharpe']:+.2f}  "
          f"maxDD {s['maxdd']:+.0%} (weekly-sampled)")
    print("  by year: " + "  ".join(f"{y}:{g['bl'].sum():+.0%}" for y, g in df.groupby('yr')))
    # pessimistic headline
    df["blp"] = w * df["on"].values + (1 - w) * df["bg_bid"].values
    sp = wk_stats(compound(df["blp"].values))
    print(f"  same book, SELL-AT-BID exit: $100k -> ${sp['final']:,.0f}  CAGR {sp['cagr']:+.0%}  "
          f"Sharpe {sp['sharpe']:+.2f}")

    _plot(df, paths)
    _read(s, sp)


def _read(s, sp):
    hr("READ")
    print(f"  * Optimistic (exercise) 50/50 book: $100k -> ${s['final']:,.0f}, CAGR {s['cagr']:+.0%}, "
          f"Sharpe {s['sharpe']:+.2f}, maxDD {s['maxdd']:+.0%}.")
    print(f"  * SAME book if you SELL at the expiry bid instead: $100k -> ${sp['final']:,.0f}, "
          f"CAGR {sp['cagr']:+.0%}. That gap IS the exercise assumption -- treat +{s['cagr']:.0%}")
    print("    as the ceiling and the bid number as the floor; reality is in between and depends")
    print("    on your discipline exercising ITM legs and managing assignment.")
    print("  * Drawdown is weekly-sampled here (~equal to daily for this smooth blend). Built on")
    print("    the VALIDATED per-cycle engine; the daily continuous builder was discarded (+2x,")
    print("    unvalidated). Caveats unchanged: 5y / one calm regime, aggressive, in-sample gate.")


def _plot(df, paths):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    x = df["date"]
    for name in ["100% overnight", "50/50", "30/70", "100% bracket"]:
        ax[0].plot(x, paths[name], label=name, lw=1.3)
    ax[0].set_yscale("log"); ax[0].axhline(CAP0, color="k", lw=0.6, ls=":")
    ax[0].legend(fontsize=9); ax[0].set_ylabel("account value $ (log)")
    ax[0].set_title("Full backtest from $100k (exercise@intrinsic, gated, weekly)")
    p = paths["50/50"]; eq = np.concatenate([[CAP0], p]); dd = (eq / np.maximum.accumulate(eq) - 1)[1:] * 100
    ax[1].fill_between(x, dd, 0.0, color="tab:red", alpha=0.5)
    ax[1].set_ylabel("drawdown %"); ax[1].set_title("50/50 book drawdown (weekly-sampled)")
    fig.tight_layout(); fig.savefig(OUT / "full_backtest.png", dpi=110)
    print(f"\nsaved {OUT/'full_backtest.png'}")


if __name__ == "__main__":
    main()
