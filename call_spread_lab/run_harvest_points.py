#!/usr/bin/env python3
"""
run_harvest_points.py  --  ONE clean comparison, plain rules, realistic fills.

Models the user's actual idea: "sell a leg when it is up X%" = a LIMIT order that
FILLS AT +X% (not at the intraday high). The intraday high is used ONLY to detect
whether the option touched +X% during the day (a yes/no). Sweeps X across several
profit-target "points", and compares to:
   * waiting for the CLOSE and selling if up >= 50% (the realistic EOD baseline)
   * a TRAILING STOP (let the winner run, exit on a pullback at the stop level)
all on REAL 2022-2026 intraday option prices, same fractional sizing, 5% slippage.
The trailing stop uses the committed engine (peak ratchets on the daily high).
"""
from __future__ import annotations
import glob, pickle
from pathlib import Path
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

from data_loader import load_options
from verticals import build_index
from strangle_harvest import HConfig, simulate, stats, compact_index

OUT = Path(__file__).resolve().parent / "outputs"
SCRATCH = Path("/tmp/claude-0/-home-user-TradingModel/3ee6862d-4424-5812-9b50-ba533ce0c5cb/scratchpad")
CACHE = SCRATCH / "real_hlc.pkl"
RAW = Path(__file__).resolve().parent.parent / "raw_data"
SLIP = 0.05
pd.set_option("display.width", 220)


def hr(t): print("\n" + "=" * 90 + f"\n{t}\n" + "=" * 90)


def build_real_hlc():
    if CACHE.exists():
        print(f"loading cached real_hlc from {CACHE}")
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    print("building real high/low/close per contract-day from raw_data (~2-3 min)...")
    files = [p for p in glob.glob(str(RAW / "SOXL_intraday_5m_exp_*.csv"))
             if Path(p).stat().st_size > 10_000]
    parts = []
    for i, p in enumerate(files):
        df = pd.read_csv(p, usecols=["expiration", "strike", "right", "timestamp",
                                     "high", "low", "close", "volume"])
        df = df[df["volume"] > 0]
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(
            "America/New_York").dt.date
        df["right"] = df["right"].str.upper().str.strip()
        df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
        df = df.sort_values("timestamp")
        g = df.groupby(["date", "right", "expiration", "strike"]).agg(
            hi=("high", "max"), lo=("low", "min"), cl=("close", "last")).reset_index()
        parts.append(g)
        if (i + 1) % 150 == 0:
            print(f"  {i+1}/{len(files)}")
    allg = pd.concat(parts, ignore_index=True)
    d = {(r.date, r.right, r.expiration, float(r.strike)): (float(r.hi), float(r.lo), float(r.cl))
         for r in allg.itertuples(index=False)}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(d, f)
    print(f"built {len(d):,} contract-days -> cached")
    return d


def y23(res):
    eq = pd.Series(res["equity"], index=pd.to_datetime(res["dates"]))
    yr = eq.groupby(eq.index.year).agg(["first", "last"])
    return (yr["last"] / yr["first"] - 1).get(2023, float("nan"))


def main():
    hr("LOAD")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt); compact = compact_index(idx)
    hlc = build_real_hlc()
    real_hi = {k: v[0] for k, v in hlc.items()}          # day-high = the touch detector
    real_hilo = {k: (v[0], v[1]) for k, v in hlc.items()}  # (high, low) for the trailing stop

    for dte in (120, 60):
        base = dict(dte_target=dte, dte_tol=(15 if dte < 90 else 20), dist=0.075, leg_frac=0.15)
        hr(f"{dte} DTE strangle (7.5% strikes, 15%/leg, 5% slippage) — 2022–2026")
        print(f"  {'rule':52s} {'CAGR':>6} {'maxDD':>6} {'end $':>11} {'2023':>6}")

        def row(label, res):
            s = stats(res, HConfig(**base))
            print(f"  {label:52s} {s['cagr']:>+6.0%} {s['max_dd']:>+6.0%} "
                  f"{s['end_equity']:>11,.0f} {y23(res):>+6.0%}")
            return s

        eod = simulate(idx, HConfig(take=0.50, **base), compact)
        row("Wait for CLOSE, sell if up >= 50%  (baseline)", eod)
        print("  " + "-" * 82)
        for X in (0.10, 0.25, 0.50, 1.00, 2.00):
            r = simulate(idx, HConfig(take=X, real_exit="limit", **base), compact,
                         intraday=(None, None, SLIP), real_hi=real_hi)
            row(f"Sell intraday the moment it's up +{X:.0%} (fill at +{X:.0%})", r)
        print("  " + "-" * 82)
        for arm, tr in [(0.25, 0.25), (0.50, 0.30), (1.00, 0.40)]:
            r = simulate(idx, HConfig(harvest_mode="trailing", arm_pct=arm, trail_pct=tr, **base),
                         compact, intraday=(None, None, SLIP), real_hilo=real_hilo)
            row(f"Trailing stop: arm at +{arm:.0%}, exit on {tr:.0%} pullback", r)
        if dte == 120:
            _plot(idx, compact, real_hi, real_hilo, base)

    hr("PLAIN-ENGLISH READ")
    print("Low targets (+10/25%) harvest constantly and churn -> worst. Higher targets")
    print("(+100/200%) approach 'just hold'. NONE of the fixed targets beat waiting for the")
    print("close, because selling a winner at a fixed +X% throws away the big runners.")
    print("The TRAILING stop is the only rule that keeps the runners (exit on a pullback,")
    print("not a fixed target) -- that's where intraday info finally helps, at higher drawdown.")


def _plot(idx, compact, real_hi, real_hilo, base):
    eod = simulate(idx, HConfig(take=0.50, **base), compact)
    fixed = simulate(idx, HConfig(take=0.50, real_exit="limit", **base), compact,
                     intraday=(None, None, SLIP), real_hi=real_hi)
    trail = simulate(idx, HConfig(harvest_mode="trailing", arm_pct=0.25, trail_pct=0.25, **base),
                     compact, intraday=(None, None, SLIP), real_hilo=real_hilo)
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for lbl, r, c in [("wait for close, sell if up >=50%", eod, "tab:blue"),
                      ("sell intraday when up +50% (fixed target)", fixed, "tab:red"),
                      ("trailing stop (let winners run)", trail, "tab:green")]:
        e = pd.Series(r["equity"], index=pd.to_datetime(r["dates"]))
        ax.plot(e.index, e.values, label=lbl, lw=1.5, color=c)
    ax.axhline(100_000, color="k", lw=0.6, ls="--")
    ax.set_yscale("log"); ax.set_ylabel("equity ($, log)")
    ax.set_title("120 DTE, real intraday prices: fixed +50% target (red) loses; "
                 "trailing (green) keeps the runners")
    ax.legend(); fig.tight_layout(); fig.savefig(OUT / "harvest_points.png", dpi=110)


if __name__ == "__main__":
    main()
