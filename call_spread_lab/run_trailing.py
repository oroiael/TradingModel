#!/usr/bin/env python3
"""
run_trailing.py  --  the honest test of whether intraday data can add value: a
TRAILING STOP that lets winners run and exits on a pullback (filling at the stop
level, which is achievable), vs the fixed +take% harvest and vs EOD close-harvest.

Trailing rule (per leg): once the leg is up >= arm_pct, ratchet a peak on the daily
highs; exit when the daily low falls trail_pct below the peak, at
peak*(1-trail_pct)*(1-slip). Losing legs never arm -> held (left alone), as before.
The stop is checked against the peak through PRIOR days (no same-day high/low
ordering assumption) -- a realistic, slightly conservative daily-resolution model.

Uses real day-high/low per contract from the full 2022-2026 5-min option set.
"""
from __future__ import annotations
import glob, pickle
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

from data_loader import load_options
from verticals import build_index
from strangle_harvest import HConfig, simulate, stats, compact_index

OUT = Path(__file__).resolve().parent / "outputs"
SCRATCH = Path("/tmp/claude-0/-home-user-TradingModel/3ee6862d-4424-5812-9b50-ba533ce0c5cb/scratchpad")
CACHE = SCRATCH / "real_hilo.pkl"
RAW = Path(__file__).resolve().parent.parent / "raw_data"
SLIP = 0.05
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 84 + f"\n{t}\n" + "=" * 84)


def build_real_hilo():
    if CACHE.exists():
        print(f"loading cached real_hilo from {CACHE}")
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    print("building real_hilo (daily high & low per contract) from raw_data ...")
    files = [p for p in glob.glob(str(RAW / "SOXL_intraday_5m_exp_*.csv"))
             if Path(p).stat().st_size > 10_000]
    parts = []
    for i, p in enumerate(files):
        df = pd.read_csv(p, usecols=["expiration", "strike", "right", "timestamp",
                                     "high", "low", "volume"])
        df = df[df["volume"] > 0]
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(
            "America/New_York").dt.date
        df["right"] = df["right"].str.upper().str.strip()
        df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
        g = df.groupby(["date", "right", "expiration", "strike"]).agg(
            hi=("high", "max"), lo=("low", "min")).reset_index()
        parts.append(g)
        if (i + 1) % 150 == 0:
            print(f"  {i+1}/{len(files)}")
    allg = pd.concat(parts, ignore_index=True)
    d = {(r.date, r.right, r.expiration, float(r.strike)): (float(r.hi), float(r.lo))
         for r in allg.itertuples(index=False)}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(d, f)
    print(f"built {len(d):,} contract-day hi/lo -> cached")
    return d


def by_year(res):
    eq = pd.Series(res["equity"], index=pd.to_datetime(res["dates"]))
    yr = eq.groupby(eq.index.year).agg(["first", "last"])
    return (yr["last"] / yr["first"] - 1).round(3)


def main():
    hr("LOAD")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt); compact = compact_index(idx)
    real_hilo = build_real_hilo()

    for dte in (120, 60):
        base = dict(dte_target=dte, dte_tol=(15 if dte < 90 else 20), dist=0.075,
                    leg_frac=0.15)
        hr(f"{dte} DTE  --  EOD close-harvest (+50%) vs TRAILING-STOP sweep (arm x trail)")
        eod = simulate(idx, HConfig(take=0.50, **base), compact)
        se = stats(eod, HConfig(**base))
        print(f"  BASELINE EOD close-harvest +50%: CAGR {se['cagr']:+.0%}  maxDD {se['max_dd']:+.0%}  "
              f"end ${se['end_equity']:,.0f}  (2023 {by_year(eod).get(2023):+.0%})")
        print(f"\n  {'arm':>4} {'trail':>5} | {'CAGR':>6} {'maxDD':>6} {'end_equity':>12} "
              f"{'2022':>6} {'2023':>6} {'2026':>6} {'vs EOD':>7}")
        best = None
        for arm in (0.25, 0.50, 1.00):
            for trail in (0.15, 0.25, 0.40):
                cfg = HConfig(harvest_mode="trailing", arm_pct=arm, trail_pct=trail, **base)
                r = simulate(idx, cfg, compact, intraday=(None, None, SLIP), real_hilo=real_hilo)
                s = stats(r, cfg); y = by_year(r)
                d = s["cagr"] - se["cagr"]
                print(f"  {arm:>4.0%} {trail:>5.0%} | {s['cagr']:>+6.0%} {s['max_dd']:>+6.0%} "
                      f"{s['end_equity']:>12,.0f} {y.get(2022,float('nan')):>+6.0%} "
                      f"{y.get(2023,float('nan')):>+6.0%} {y.get(2026,float('nan')):>+6.0%} {d:>+7.0%}")
                if best is None or s["cagr"] > best[1]["cagr"]:
                    best = ((arm, trail), s, r)
        (ba, bt), bs, br = best
        print(f"\n  best trailing @ {dte} DTE: arm {ba:.0%} trail {bt:.0%} -> "
              f"CAGR {bs['cagr']:+.0%} vs EOD {se['cagr']:+.0%}  "
              f"({'BEATS' if bs['cagr']>se['cagr'] else 'loses to'} EOD)")
        if dte == 120:
            _plot(eod, br, ba, bt)
            print("\n  by-year (EOD vs best trailing):")
            print(pd.DataFrame({"EOD": by_year(eod), "trailing": by_year(br)}).to_string())

    hr("READ")
    print("Trailing keeps the fat-tail winners (unlike the fixed +50% that caps them) and")
    print("exits at an ACHIEVABLE stop level (not the peak). Compare 'vs EOD': if positive,")
    print("intraday information finally adds value; if not, EOD close-harvest still wins.")


def _plot(eod, trail, arm, tr):
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for lbl, r, c in [("EOD close-harvest +50%", eod, "tab:blue"),
                      (f"trailing stop (arm {arm:.0%}, trail {tr:.0%})", trail, "tab:green")]:
        e = pd.Series(r["equity"], index=pd.to_datetime(r["dates"]))
        ax.plot(e.index, e.values, label=lbl, lw=1.5, color=c)
    ax.axhline(100_000, color="k", lw=0.6, ls="--")
    ax.set_yscale("log"); ax.set_ylabel("equity ($, log)")
    ax.set_title("120 DTE: trailing stop vs EOD close-harvest (real intraday hi/lo, 2022-2026)")
    ax.legend(); fig.tight_layout(); fig.savefig(OUT / "trailing_vs_eod.png", dpi=110)


if __name__ == "__main__":
    main()
